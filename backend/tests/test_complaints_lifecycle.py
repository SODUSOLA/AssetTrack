"""Ticket lifecycle (SPEC 12.1 tests 6 and 7) and the event effects Milestone 6 will call.

Device events cannot be created through the API until Milestone 6, so these tests insert the
events with factories and call the same `on_*` service functions the events module will use.
"""

import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Complaint, Device
from app.models.enums import AckStatus, ComplaintStatus, DeviceStatus, EventType
from app.services import complaints as svc
from tests.api_helpers import People, bearer
from tests.factories import make_ack, make_complaint, make_device, make_event

COMPLAINTS = "/api/v1/complaints"
S = ComplaintStatus
TRANSITION = re.compile(r"Status: (\w+) -> (\w+)\.")


@pytest.fixture
def laptop(db: Session, people: People) -> Device:
    device = make_device(
        db, people.engineer, unit_id=people.unit_a.id, status=DeviceStatus.assigned
    )
    db.commit()
    return device


def transitions(detail) -> list[tuple[str, str]]:
    """Status changes as recorded by the system comments, oldest first."""
    found = []
    for comment in detail.comments:
        if comment.is_system:
            found.extend(TRANSITION.findall(comment.body))
    return found


class Observer:
    """Follows a ticket's actual status so it can be compared with what the comments claim."""

    def __init__(self, db: Session, people: People, ticket_id) -> None:
        self.db, self.people, self.ticket_id = db, people, ticket_id
        self.seen = [self.status()]

    def status(self) -> str:
        return svc.get_complaint(self.db, self.people.admin, self.ticket_id).status.value

    def step(self) -> None:
        self.seen.append(self.status())

    def actual_transitions(self) -> list[tuple[str, str]]:
        return [(a, b) for a, b in zip(self.seen, self.seen[1:], strict=False) if a != b]

    def recorded_transitions(self) -> list[tuple[str, str]]:
        return transitions(svc.get_complaint(self.db, self.people.admin, self.ticket_id))


def intake(db, device, people, ticket):
    e = make_event(
        db, device, people.engineer, event_type=EventType.received_for_repair,
        from_status=DeviceStatus.assigned, to_status=DeviceStatus.received_for_repair,
        counterparty_name="Ada Obi", complaint_id=ticket.id, unit_id=people.unit_a.id,
    )  # fmt: skip
    svc.on_intake(db, ticket.id, people.engineer, e.id)
    db.commit()
    return e


def returned(db, device, people, ticket):
    e = make_event(
        db, device, people.engineer, event_type=EventType.returned_to_unit,
        from_status=DeviceStatus.repaired, to_status=DeviceStatus.assigned,
        counterparty_name="Ada Obi", complaint_id=ticket.id, unit_id=people.unit_a.id,
    )  # fmt: skip
    svc.on_return(db, ticket.id, people.engineer, e.id)
    db.commit()
    return e


def acknowledge(db, e, people, ticket, status):
    make_ack(
        db, e, people.rep_a, status, comment="not fixed" if status is AckStatus.disputed else None
    )
    svc.on_return_acknowledged(db, ticket.id, people.rep_a, e.id, status)
    db.commit()


def test_full_lifecycle_to_closed(api: TestClient, people: People, db: Session, laptop) -> None:
    raised = api.post(
        COMPLAINTS,
        headers=bearer(people.rep_a),
        json={"title": "No power", "description": "Dead", "device_id": str(laptop.id)},
    ).json()
    ticket = db.get(Complaint, raised["id"])
    watch = Observer(db, people, ticket.id)
    assert watch.seen == ["open"]

    in_ = intake(db, laptop, people, ticket)
    watch.step()
    ret = returned(db, laptop, people, ticket)
    watch.step()
    acknowledge(db, ret, people, ticket, AckStatus.confirmed)
    watch.step()

    detail = svc.get_complaint(db, people.admin, ticket.id)
    assert detail.status is S.closed
    assert detail.resolved_at is not None and detail.closed_at is not None
    assert detail.resolved_at <= detail.closed_at
    assert [e.event_type for e in detail.events] == [
        EventType.received_for_repair, EventType.returned_to_unit
    ]  # fmt: skip
    assert transitions(detail) == [
        ("open", "in_progress"), ("in_progress", "resolved"), ("resolved", "closed")
    ]  # fmt: skip
    assert watch.recorded_transitions() == watch.actual_transitions()

    # Each system comment names the event that caused it and was written by the one who acted.
    by_text = {c.body: c for c in detail.comments if c.is_system}
    assert any(f"#{in_.id}" in body for body in by_text)
    assert any(f"#{ret.id}" in body and "confirmed" in body for body in by_text)
    last = detail.comments[-1]
    assert last.is_system and last.author.id == people.rep_a.id


def test_dispute_reopens_and_a_second_cycle_closes(
    api: TestClient, people: People, db: Session, laptop
) -> None:
    ticket = make_complaint(db, people.unit_a, people.rep_a, device=laptop)
    db.commit()
    watch = Observer(db, people, ticket.id)

    intake(db, laptop, people, ticket)
    first_return = returned(db, laptop, people, ticket)
    watch.step()
    assert watch.seen[-1] == "resolved"

    acknowledge(db, first_return, people, ticket, AckStatus.disputed)
    watch.step()
    reopened = svc.get_complaint(db, people.admin, ticket.id)
    assert reopened.status is S.reopened
    assert reopened.resolved_at is None and reopened.closed_at is None

    intake(db, laptop, people, ticket)
    second_return = returned(db, laptop, people, ticket)
    acknowledge(db, second_return, people, ticket, AckStatus.confirmed)
    watch.step()

    final = svc.get_complaint(db, people.admin, ticket.id)
    assert final.status is S.closed and final.closed_at is not None
    assert transitions(final) == [
        ("open", "in_progress"), ("in_progress", "resolved"), ("resolved", "reopened"),
        ("reopened", "in_progress"), ("in_progress", "resolved"), ("resolved", "closed"),
    ]  # fmt: skip
    assert len(final.events) == 4


def test_every_state_change_is_explained_by_a_comment(
    api: TestClient, people: People, db: Session, laptop
) -> None:
    """Mixes API actions and event effects; actual status changes must equal recorded ones."""
    ticket = make_complaint(db, people.unit_a, people.rep_a, device=laptop)
    db.commit()
    watch = Observer(db, people, ticket.id)

    def api_call(method, path, user, **body):
        resp = getattr(api, method)(
            f"{COMPLAINTS}/{ticket.id}{path}", headers=bearer(user), json=body
        )
        assert resp.status_code == 200, resp.text
        watch.step()

    api_call("patch", "", people.engineer, assigned_to=str(people.engineer.id))  # -> in_progress
    api_call("patch", "", people.engineer, status="resolved", comment="Fixed remotely")
    api_call("post", "/reopen", people.rep_a, reason="No it is not")  # -> reopened
    intake(db, laptop, people, ticket)
    watch.step()
    ret = returned(db, laptop, people, ticket)
    watch.step()
    acknowledge(db, ret, people, ticket, AckStatus.confirmed)
    watch.step()

    assert watch.actual_transitions() == [
        ("open", "in_progress"), ("in_progress", "resolved"), ("resolved", "reopened"),
        ("reopened", "in_progress"), ("in_progress", "resolved"), ("resolved", "closed"),
    ]  # fmt: skip
    assert watch.recorded_transitions() == watch.actual_transitions()


def test_intake_on_an_assigned_ticket_already_in_progress_adds_nothing(
    people: People, db: Session, laptop
) -> None:
    ticket = make_complaint(
        db, people.unit_a, people.rep_a, device=laptop, status=S.in_progress,
        assigned_to=people.engineer.id,
    )  # fmt: skip
    db.commit()
    e = make_event(
        db, laptop, people.engineer, event_type=EventType.received_for_repair,
        counterparty_name="Ada", to_status=DeviceStatus.received_for_repair, complaint_id=ticket.id,
    )  # fmt: skip
    svc.on_intake(db, ticket.id, people.engineer, e.id)
    assert svc.get_complaint(db, people.admin, ticket.id).comments == []


def test_intake_assigns_the_engineer_when_nobody_is_assigned(
    people: People, db: Session, laptop
) -> None:
    ticket = make_complaint(db, people.unit_a, people.rep_a, device=laptop)
    db.commit()
    e = make_event(
        db, laptop, people.engineer, event_type=EventType.received_for_repair,
        counterparty_name="Ada", to_status=DeviceStatus.received_for_repair, complaint_id=ticket.id,
    )  # fmt: skip
    svc.on_intake(db, ticket.id, people.engineer, e.id, laptop)
    detail = svc.get_complaint(db, people.admin, ticket.id)
    assert detail.assigned_to is not None and detail.assigned_to.id == people.engineer.id
    (note,) = detail.comments
    assert f"Assigned to {people.engineer.full_name}." in note.body
    assert "Linked to device" not in note.body  # it already had this device


def test_intake_links_a_ticket_raised_without_a_device(people: People, db: Session, laptop) -> None:
    ticket = make_complaint(db, people.unit_a, people.rep_a, assigned_to=people.engineer.id)
    db.commit()
    e = make_event(
        db, laptop, people.engineer, event_type=EventType.received_for_repair,
        counterparty_name="Ada", to_status=DeviceStatus.received_for_repair, complaint_id=ticket.id,
    )  # fmt: skip
    svc.on_intake(db, ticket.id, people.engineer, e.id, laptop)
    detail = svc.get_complaint(db, people.admin, ticket.id)
    assert detail.device is not None and detail.device.id == laptop.id
    assert f"Linked to device {laptop.asset_tag}." in detail.comments[0].body
    assert detail.status is S.in_progress


@pytest.mark.parametrize("status", [S.resolved, S.closed])
@pytest.mark.parametrize("effect", ["on_intake", "on_return"])
def test_effects_refuse_finished_tickets(
    people: People, db: Session, laptop, status: S, effect: str
) -> None:
    ticket = make_complaint(db, people.unit_a, people.rep_a, device=laptop, status=status)
    db.commit()
    with pytest.raises(AppError) as exc:
        getattr(svc, effect)(db, ticket.id, people.engineer, 1)
    assert (exc.value.status_code, exc.value.code) == (409, "TICKET_NOT_ACTIVE")


@pytest.mark.parametrize("verdict", [AckStatus.confirmed, AckStatus.disputed])
@pytest.mark.parametrize("status", [S.in_progress, S.closed, S.reopened])
def test_acknowledgement_never_blocks_but_may_change_nothing(
    people: People, db: Session, laptop, status: S, verdict: AckStatus
) -> None:
    ticket = make_complaint(db, people.unit_a, people.rep_a, device=laptop, status=status)
    db.commit()
    svc.on_return_acknowledged(db, ticket.id, people.rep_a, 7, verdict)
    detail = svc.get_complaint(db, people.admin, ticket.id)
    assert detail.status is status
    (note,) = detail.comments
    assert note.is_system and "status unchanged" in note.body and "#7" in note.body


def test_state_changes_lock_the_ticket_row(api: TestClient, people: People, db: Session) -> None:
    ticket = make_complaint(db, people.unit_a, people.rep_a, status=S.resolved)
    db.commit()
    statements: list[str] = []
    engine = db.get_bind().engine

    def record(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        resp = api.post(f"{COMPLAINTS}/{ticket.id}/confirm", headers=bearer(people.rep_a))
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert resp.status_code == 200
    assert any("FROM complaints" in s and "FOR UPDATE" in s for s in statements)


def test_timestamps_follow_the_status(people: People, db: Session, laptop) -> None:
    ticket = make_complaint(db, people.unit_a, people.rep_a, device=laptop)
    db.commit()
    before = datetime.now(UTC)
    intake(db, laptop, people, ticket)
    assert svc.get_complaint(db, people.admin, ticket.id).resolved_at is None
    returned(db, laptop, people, ticket)
    resolved_at = svc.get_complaint(db, people.admin, ticket.id).resolved_at
    assert resolved_at is not None and resolved_at >= before
