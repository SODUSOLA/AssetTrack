import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Complaint, ComplaintComment
from app.models.enums import (
    AckStatus,
    ComplaintStatus,
    DeviceStatus,
    EventType,
    PriorityLevel,
    UserRole,
)
from tests.api_helpers import People, bearer
from tests.factories import (
    make_ack,
    make_complaint,
    make_device,
    make_event,
    make_unit,
    make_user,
)

COMPLAINTS = "/api/v1/complaints"
MISSING = "00000000-0000-0000-0000-000000000099"
S = ComplaintStatus


@pytest.fixture
def devices(db: Session, people: People) -> dict:
    eng = people.engineer
    result = {
        "a": make_device(db, eng, unit_id=people.unit_a.id, status=DeviceStatus.assigned),
        "b": make_device(db, eng, unit_id=people.unit_b.id, status=DeviceStatus.assigned),
        "stock": make_device(db, eng),
        "retired": make_device(
            db, eng, unit_id=people.unit_a.id, status=DeviceStatus.decommissioned
        ),
    }
    db.commit()
    return result


def raise_ticket(api: TestClient, user, **overrides):
    body = {"title": "Laptop will not boot", "description": "Black screen on start"} | overrides
    return api.post(COMPLAINTS, headers=bearer(user), json=body)


def system_comments(api: TestClient, user, complaint_id) -> list[str]:
    resp = api.get(f"{COMPLAINTS}/{complaint_id}/comments", headers=bearer(user))
    return [c["body"] for c in resp.json()["items"] if c["is_system"]]


@pytest.fixture
def ticket(db: Session, people: People):
    """An open unit-A ticket."""
    t = make_complaint(db, people.unit_a, people.rep_a)
    db.commit()
    return t


# ---------- creation ----------


def test_unit_rep_raises_a_complaint_for_their_own_unit(
    api: TestClient, people: People, devices
) -> None:
    resp = raise_ticket(api, people.rep_a, device_id=str(devices["a"].id), priority="high")
    assert resp.status_code == 201
    out = resp.json()
    assert re.fullmatch(rf"TKT-{datetime.now(UTC).year}-\d{{5}}", out["ticket_no"])
    assert out["status"] == "open" and out["priority"] == "high" and out["category"] == "hardware"
    assert out["unit"]["code"] == "A"
    assert out["raised_by"]["id"] == str(people.rep_a.id)
    assert out["device"]["asset_tag"] == devices["a"].asset_tag
    assert out["assigned_to"] is None and out["resolved_at"] is None and out["closed_at"] is None
    assert out["comments"] == [] and out["events"] == []


def test_complaint_without_a_device(api: TestClient, people: People) -> None:
    resp = raise_ticket(api, people.rep_a, category="network", title="  Wi-Fi down  ")
    assert resp.status_code == 201
    assert resp.json()["device"] is None
    assert resp.json()["title"] == "Wi-Fi down" and resp.json()["category"] == "network"


def test_unit_rep_cannot_raise_for_another_unit(api: TestClient, people: People) -> None:
    own = raise_ticket(api, people.rep_a, unit_id=str(people.unit_a.id))
    assert own.status_code == 201 and own.json()["unit"]["code"] == "A"
    other = raise_ticket(api, people.rep_a, unit_id=str(people.unit_b.id))
    assert (other.status_code, other.json()["error"]["code"]) == (403, "FORBIDDEN")


@pytest.mark.parametrize(
    ("device", "status", "code"),
    [
        ("b", 404, "DEVICE_NOT_FOUND"),  # another unit's device
        ("stock", 404, "DEVICE_NOT_FOUND"),  # not held by any unit
        (None, 404, "DEVICE_NOT_FOUND"),  # does not exist
        ("retired", 422, "DEVICE_DECOMMISSIONED"),
    ],
)
def test_unit_rep_device_link_rules(
    api: TestClient, people: People, devices, device, status: int, code: str
) -> None:
    device_id = str(devices[device].id) if device else MISSING
    resp = raise_ticket(api, people.rep_a, device_id=device_id)
    assert (resp.status_code, resp.json()["error"]["code"]) == (status, code)


def test_engineering_raises_on_behalf_of_a_unit(api: TestClient, people: People, devices) -> None:
    missing_unit = raise_ticket(api, people.engineer)
    assert (missing_unit.status_code, missing_unit.json()["error"]["code"]) == (
        422,
        "UNIT_REQUIRED",
    )

    resp = raise_ticket(
        api, people.engineer, unit_id=str(people.unit_a.id), device_id=str(devices["a"].id)
    )
    assert resp.status_code == 201
    out = resp.json()
    assert out["unit"]["code"] == "A" and out["raised_by"]["id"] == str(people.engineer.id)
    (note,) = out["comments"]
    assert note["is_system"] and "on behalf" in note["body"]
    assert note["author"]["id"] == str(people.engineer.id)


def test_on_behalf_device_must_belong_to_that_unit(
    api: TestClient, people: People, devices, db: Session
) -> None:
    mismatch = raise_ticket(
        api, people.admin, unit_id=str(people.unit_a.id), device_id=str(devices["b"].id)
    )
    assert (mismatch.status_code, mismatch.json()["error"]["code"]) == (422, "DEVICE_UNIT_MISMATCH")
    unknown = raise_ticket(api, people.admin, unit_id=str(people.unit_a.id), device_id=MISSING)
    assert unknown.status_code == 404

    people.unit_b.is_active = False
    db.commit()
    for unit_id in (str(people.unit_b.id), MISSING):
        resp = raise_ticket(api, people.admin, unit_id=unit_id)
        assert (resp.status_code, resp.json()["error"]["code"]) == (422, "UNIT_NOT_FOUND")


def test_auditor_cannot_raise_complaints(api: TestClient, people: People) -> None:
    assert raise_ticket(api, people.auditor, unit_id=str(people.unit_a.id)).status_code == 403


@pytest.mark.parametrize(
    "extra",
    [
        {"status": "closed"},
        {"ticket_no": "TKT-1999-00001"},
        {"raised_by": "00000000-0000-0000-0000-000000000001"},
        {"assigned_to": "00000000-0000-0000-0000-000000000001"},
        {"is_system": True},
    ],
)
def test_server_controlled_fields_are_rejected(
    api: TestClient, people: People, extra: dict
) -> None:
    assert raise_ticket(api, people.rep_a, **extra).status_code == 422


@pytest.mark.parametrize(
    "bad",
    [
        {"title": "   "},
        {"title": "t" * 201},
        {"description": ""},
        {"description": "d" * 5001},
        {"category": "plumbing"},
        {"priority": "urgent"},
    ],
)
def test_creation_validation(api: TestClient, people: People, bad: dict) -> None:
    assert raise_ticket(api, people.rep_a, **bad).status_code == 422


# ---------- list ----------


@pytest.fixture
def board(db: Session, people: People, devices) -> dict[str, Complaint]:
    eng, a, b = people.engineer, people.unit_a, people.unit_b
    t = {
        "a_open": make_complaint(db, a, people.rep_a, title="A open", device=devices["a"],
                                 created_at=datetime(2026, 10, 1, 9, tzinfo=UTC)),
        "a_prog": make_complaint(db, a, people.rep_a, title="A progress", status=S.in_progress,
                                 priority=PriorityLevel.high, assigned_to=eng.id,
                                 created_at=datetime(2026, 10, 2, 9, tzinfo=UTC)),
        "a_done": make_complaint(db, a, people.rep_a, title="A closed", status=S.closed,
                                 created_at=datetime(2026, 10, 3, 9, tzinfo=UTC)),
        "b_open": make_complaint(db, b, people.rep_b, title="B open", device=devices["b"],
                                 priority=PriorityLevel.critical,
                                 created_at=datetime(2026, 10, 4, 9, tzinfo=UTC)),
        "b_prog": make_complaint(db, b, people.rep_b, title="B progress", status=S.in_progress,
                                 assigned_to=people.admin.id,
                                 created_at=datetime(2026, 10, 5, 9, tzinfo=UTC)),
    }  # fmt: skip
    db.commit()
    return t


def ids(resp) -> list[str]:
    return [c["id"] for c in resp.json()["items"]]


def ids_of(board, *names: str) -> list[str]:
    return [str(board[n].id) for n in names]


@pytest.mark.parametrize("role", ["admin", "engineer", "auditor"])
def test_staff_see_all_complaints_newest_first(
    api: TestClient, people: People, board, role: str
) -> None:
    resp = api.get(COMPLAINTS, headers=bearer(people.by_role()[role]))
    assert resp.status_code == 200 and resp.json()["total"] == 5
    assert ids(resp) == ids_of(board, "b_prog", "b_open", "a_done", "a_prog", "a_open")


def test_list_filters(api: TestClient, people: People, board, devices) -> None:
    eng = bearer(people.engineer)

    def get(**params):
        return ids(api.get(COMPLAINTS, headers=eng, params=params))

    assert get(status="in_progress") == ids_of(board, "b_prog", "a_prog")
    assert get(unit_id=str(people.unit_b.id)) == ids_of(board, "b_prog", "b_open")
    assert get(priority="high") == ids_of(board, "a_prog")
    assert get(device_id=str(devices["a"].id)) == ids_of(board, "a_open")
    assert get(assigned_to=str(people.engineer.id)) == ids_of(board, "a_prog")
    assert get(status="in_progress", unit_id=str(people.unit_a.id)) == ids_of(board, "a_prog")
    assert get(status="reopened") == []
    assert get(date_from="2026-10-03", date_to="2026-10-04") == ids_of(board, "b_open", "a_done")
    assert get(date_from="2026-10-05") == ids_of(board, "b_prog")
    assert get(date_to="2026-10-01") == ids_of(board, "a_open")


def test_creation_date_filter_uses_lagos_days(api: TestClient, people: People, db: Session) -> None:
    late = make_complaint(db, people.unit_a, people.rep_a,
                          created_at=datetime(2026, 11, 20, 23, 30, tzinfo=UTC))  # fmt: skip
    db.commit()  # 00:30 on 21 Nov in Lagos
    eng = bearer(people.engineer)
    on_21 = api.get(
        COMPLAINTS, headers=eng, params={"date_from": "2026-11-21", "date_to": "2026-11-21"}
    )
    on_20 = api.get(
        COMPLAINTS, headers=eng, params={"date_from": "2026-11-20", "date_to": "2026-11-20"}
    )
    assert ids(on_21) == [str(late.id)] and ids(on_20) == []


def test_list_pagination_and_validation(api: TestClient, people: People, board) -> None:
    eng = bearer(people.engineer)
    page = api.get(COMPLAINTS, headers=eng, params={"page": 2, "page_size": 2}).json()
    assert (page["total"], page["page"], page["page_size"], len(page["items"])) == (5, 2, 2, 2)
    for params in ({"status": "stuck"}, {"priority": "x"}, {"unit_id": "nope"},
                   {"date_from": "2026-10-05", "date_to": "2026-10-01"}):  # fmt: skip
        assert api.get(COMPLAINTS, headers=eng, params=params).status_code == 422


def test_unit_rep_only_sees_their_units_complaints(api: TestClient, people: People, board) -> None:
    rep_a = api.get(COMPLAINTS, headers=bearer(people.rep_a))
    assert ids(rep_a) == ids_of(board, "a_done", "a_prog", "a_open")
    rep_b = api.get(COMPLAINTS, headers=bearer(people.rep_b))
    assert ids(rep_b) == ids_of(board, "b_prog", "b_open")


def test_unit_rep_cannot_widen_the_list_with_unit_id(
    api: TestClient, people: People, board
) -> None:
    resp = api.get(
        COMPLAINTS, headers=bearer(people.rep_a), params={"unit_id": str(people.unit_b.id)}
    )
    assert ids(resp) == ids_of(board, "a_done", "a_prog", "a_open")


# ---------- detail ----------


def test_detail_includes_comments_and_linked_events(
    api: TestClient, people: People, db: Session, devices
) -> None:
    t = make_complaint(db, people.unit_a, people.rep_a, device=devices["a"], status=S.in_progress)
    db.add(ComplaintComment(complaint_id=t.id, author_id=people.rep_a.id, body="It is urgent"))
    intake = make_event(
        db, devices["a"], people.engineer, event_type=EventType.received_for_repair,
        to_status=DeviceStatus.received_for_repair, counterparty_name="Ada",
        complaint_id=t.id, unit_id=people.unit_a.id,
    )  # fmt: skip
    make_ack(db, intake, people.rep_a, AckStatus.confirmed)
    make_event(db, devices["a"], people.engineer, event_type=EventType.note_added,
               to_status=DeviceStatus.received_for_repair, notes="unlinked")  # fmt: skip
    db.commit()

    out = api.get(f"{COMPLAINTS}/{t.id}", headers=bearer(people.rep_a)).json()
    assert [c["body"] for c in out["comments"]] == ["It is urgent"]
    assert out["comments"][0]["is_system"] is False
    (event,) = out["events"]  # only the event linked to this ticket
    assert event["event_type"] == "received_for_repair" and event["ack_state"] == "confirmed"
    assert event["complaint"]["ticket_no"] == t.ticket_no


def test_staff_can_read_any_unit_but_a_rep_cannot(api: TestClient, people: People, board) -> None:
    url = f"{COMPLAINTS}/{board['b_open'].id}"
    for user in (people.admin, people.engineer, people.auditor, people.rep_b):
        assert api.get(url, headers=bearer(user)).status_code == 200
    other = api.get(url, headers=bearer(people.rep_a))
    missing = api.get(f"{COMPLAINTS}/{MISSING}", headers=bearer(people.rep_a))
    assert other.status_code == 404 and other.json() == missing.json()
    assert other.json()["error"]["code"] == "COMPLAINT_NOT_FOUND"
    assert api.get(f"{COMPLAINTS}/{MISSING}", headers=bearer(people.admin)).status_code == 404
    assert api.get(f"{COMPLAINTS}/not-a-uuid", headers=bearer(people.admin)).status_code == 422


# ---------- engineering updates ----------


def patch(api: TestClient, user, ticket_id, **body):
    return api.patch(f"{COMPLAINTS}/{ticket_id}", headers=bearer(user), json=body)


def test_assigning_starts_work_and_leaves_a_system_comment(
    api: TestClient, people: People, ticket
) -> None:
    resp = patch(api, people.engineer, ticket.id, assigned_to=str(people.engineer.id))
    assert resp.status_code == 200
    out = resp.json()
    assert out["status"] == "in_progress"
    assert out["assigned_to"]["id"] == str(people.engineer.id)
    (note,) = [c for c in out["comments"] if c["is_system"]]
    assert note["author"]["id"] == str(people.engineer.id)
    assert f"Assigned to {people.engineer.full_name}." in note["body"]
    assert "Status: open -> in_progress." in note["body"]


def test_reassigning_keeps_the_status(api: TestClient, people: People, ticket) -> None:
    patch(api, people.engineer, ticket.id, assigned_to=str(people.engineer.id))
    resp = patch(api, people.engineer, ticket.id, assigned_to=str(people.admin.id))
    assert resp.json()["status"] == "in_progress"
    assert resp.json()["assigned_to"]["id"] == str(people.admin.id)
    assert len(system_comments(api, people.admin, ticket.id)) == 2


def test_reopened_ticket_restarts_when_assigned(
    api: TestClient, people: People, db: Session
) -> None:
    t = make_complaint(db, people.unit_a, people.rep_a, status=S.reopened)
    db.commit()
    resp = patch(api, people.engineer, t.id, assigned_to=str(people.engineer.id))
    assert resp.json()["status"] == "in_progress"


@pytest.mark.parametrize("who", ["rep", "auditor", "inactive", "unknown"])
def test_assignee_must_be_active_engineering_staff(
    api: TestClient, people: People, db: Session, ticket, who: str
) -> None:
    inactive = make_user(db, UserRole.engineer, is_active=False)
    db.commit()
    target = {
        "rep": people.rep_a.id,
        "auditor": people.auditor.id,
        "inactive": inactive.id,
        "unknown": MISSING,
    }[who]
    resp = patch(api, people.engineer, ticket.id, assigned_to=str(target))
    assert (resp.status_code, resp.json()["error"]["code"]) == (422, "ASSIGNEE_INVALID")


def test_assignee_cannot_be_cleared(api: TestClient, people: People, ticket) -> None:
    assert patch(api, people.engineer, ticket.id, assigned_to=None).status_code == 422


def test_in_progress_needs_an_assignee(api: TestClient, people: People, ticket) -> None:
    resp = patch(api, people.engineer, ticket.id, status="in_progress")
    assert (resp.status_code, resp.json()["error"]["code"]) == (422, "ASSIGNEE_REQUIRED")
    both = patch(
        api, people.engineer, ticket.id, status="in_progress", assigned_to=str(people.engineer.id)
    )
    assert both.status_code == 200 and both.json()["status"] == "in_progress"


def test_priority_change_is_recorded(api: TestClient, people: People, ticket) -> None:
    resp = patch(api, people.engineer, ticket.id, priority="critical")
    assert resp.status_code == 200 and resp.json()["priority"] == "critical"
    assert resp.json()["status"] == "open"
    assert system_comments(api, people.admin, ticket.id) == ["Priority: medium -> critical."]


def test_resolving_requires_a_note_and_stamps_the_time(
    api: TestClient, people: People, db: Session
) -> None:
    t = make_complaint(db, people.unit_a, people.rep_a, status=S.in_progress,
                       assigned_to=people.engineer.id)  # fmt: skip
    db.commit()
    no_note = patch(api, people.engineer, t.id, status="resolved")
    assert (no_note.status_code, no_note.json()["error"]["code"]) == (422, "COMMENT_REQUIRED")

    resp = patch(api, people.engineer, t.id, status="resolved", comment="Reseated the RAM")
    out = resp.json()
    assert out["status"] == "resolved" and out["resolved_at"] is not None
    assert out["closed_at"] is None
    assert system_comments(api, people.admin, t.id) == [
        "Status: in_progress -> resolved. Note: Reseated the RAM"
    ]


def test_closing_without_resolution_needs_a_reason(api: TestClient, people: People, ticket) -> None:
    assert patch(api, people.engineer, ticket.id, status="closed").status_code == 422
    resp = patch(api, people.engineer, ticket.id, status="closed", comment="Duplicate of another")
    out = resp.json()
    assert out["status"] == "closed" and out["closed_at"] is not None
    assert out["resolved_at"] is None  # closed without ever being resolved


@pytest.mark.parametrize("current", list(S))
@pytest.mark.parametrize("target", list(S))
def test_manual_status_matrix(
    api: TestClient, people: People, db: Session, current: S, target: S
) -> None:
    t = make_complaint(db, people.unit_a, people.rep_a, status=current,
                       assigned_to=people.engineer.id)  # fmt: skip
    db.commit()
    resp = patch(api, people.engineer, t.id, status=target.value, comment="because")

    allowed = {
        (S.open, S.in_progress), (S.open, S.closed), (S.reopened, S.in_progress),
        (S.in_progress, S.resolved), (S.in_progress, S.closed),
    }  # fmt: skip
    if current is target:
        assert resp.status_code == 422 and resp.json()["error"]["code"] == "COMMENT_WITHOUT_CHANGE"
    elif current in (S.resolved, S.closed):
        assert (resp.status_code, resp.json()["error"]["code"]) == (409, "TICKET_NOT_ACTIVE")
    elif (current, target) in allowed:
        assert resp.status_code == 200 and resp.json()["status"] == target.value
    else:
        assert (resp.status_code, resp.json()["error"]["code"]) == (409, "INVALID_TRANSITION")
        assert resp.json()["error"]["details"]["current"] == current.value


def test_invalid_transition_lists_the_allowed_moves(
    api: TestClient, people: People, ticket
) -> None:
    resp = patch(api, people.engineer, ticket.id, status="resolved", comment="x")
    assert resp.status_code == 409
    assert resp.json()["error"]["details"] == {
        "current": "open",
        "allowed": ["closed", "in_progress"],
    }


def test_finished_tickets_reject_engineering_changes(
    api: TestClient, people: People, db: Session
) -> None:
    resolved = make_complaint(db, people.unit_a, people.rep_a, status=S.resolved)
    db.commit()
    for body in (
        {"priority": "low"},
        {"assigned_to": str(people.admin.id)},
        {"status": "closed", "comment": "x"},
    ):
        resp = patch(api, people.engineer, resolved.id, **body)
        assert (resp.status_code, resp.json()["error"]["code"]) == (409, "TICKET_NOT_ACTIVE")


def test_noop_patch_changes_nothing(api: TestClient, people: People, ticket) -> None:
    assert patch(api, people.engineer, ticket.id).status_code == 200
    assert patch(api, people.engineer, ticket.id, priority="medium").status_code == 200
    assert system_comments(api, people.admin, ticket.id) == []


def test_comment_alone_is_not_a_patch(api: TestClient, people: People, ticket) -> None:
    resp = patch(api, people.engineer, ticket.id, comment="hello")
    assert (resp.status_code, resp.json()["error"]["code"]) == (422, "COMMENT_WITHOUT_CHANGE")


def test_one_patch_with_several_changes_writes_one_system_comment(
    api: TestClient, people: People, ticket
) -> None:
    patch(api, people.engineer, ticket.id, priority="high", assigned_to=str(people.engineer.id))
    (note,) = system_comments(api, people.admin, ticket.id)
    assert note.startswith("Priority: medium -> high. Assigned to ")
    assert note.endswith("Status: open -> in_progress.")


def test_a_device_in_the_workshop_blocks_resolving_or_closing(
    api: TestClient, people: People, db: Session, devices
) -> None:
    t = make_complaint(db, people.unit_a, people.rep_a, device=devices["a"],
                       status=S.in_progress, assigned_to=people.engineer.id)  # fmt: skip
    intake = dict(event_type=EventType.received_for_repair, counterparty_name="Ada",
                  to_status=DeviceStatus.received_for_repair, complaint_id=t.id)  # fmt: skip
    make_event(db, devices["a"], people.engineer, **intake)
    db.commit()
    for status in ("resolved", "closed"):
        resp = patch(api, people.engineer, t.id, status=status, comment="done")
        assert (resp.status_code, resp.json()["error"]["code"]) == (409, "DEVICE_IN_REPAIR")

    make_event(
        db, devices["a"], people.engineer, event_type=EventType.returned_to_unit,
        counterparty_name="Ada", to_status=DeviceStatus.assigned, complaint_id=t.id,
    )  # fmt: skip
    db.commit()
    assert patch(api, people.engineer, t.id, status="resolved", comment="back").status_code == 200


@pytest.mark.parametrize("user", ["rep_a", "auditor"])
def test_only_engineering_may_patch(api: TestClient, people: People, ticket, user: str) -> None:
    resp = patch(api, getattr(people, user), ticket.id, priority="low")
    assert resp.status_code == 403


def test_patch_unknown_ticket_and_bad_fields(api: TestClient, people: People, ticket) -> None:
    assert patch(api, people.engineer, MISSING, priority="low").status_code == 404
    for body in (
        {"status": "done"},
        {"priority": "urgent"},
        {"title": "new"},
        {"unit_id": MISSING},
    ):
        assert patch(api, people.engineer, ticket.id, **body).status_code == 422


# ---------- comments ----------


def test_both_sides_comment_and_see_each_other(api: TestClient, people: People, ticket) -> None:
    url = f"{COMPLAINTS}/{ticket.id}/comments"
    mine = api.post(url, headers=bearer(people.rep_a), json={"body": "  Still broken  "})
    assert mine.status_code == 201
    assert mine.json()["body"] == "Still broken" and mine.json()["is_system"] is False
    assert mine.json()["author"]["id"] == str(people.rep_a.id)
    reply = api.post(url, headers=bearer(people.engineer), json={"body": "Collecting it today"})
    assert reply.status_code == 201

    for user in (people.rep_a, people.engineer, people.admin, people.auditor):
        listed = api.get(url, headers=bearer(user)).json()
        assert [c["body"] for c in listed["items"]] == ["Still broken", "Collecting it today"]
        assert listed["total"] == 2


def test_comment_permissions_and_scoping(api: TestClient, people: People, ticket) -> None:
    url = f"{COMPLAINTS}/{ticket.id}/comments"
    body = {"body": "hi"}
    assert api.post(url, headers=bearer(people.auditor), json=body).status_code == 403
    other_rep = api.post(url, headers=bearer(people.rep_b), json=body)
    assert (
        other_rep.status_code == 404 and other_rep.json()["error"]["code"] == "COMPLAINT_NOT_FOUND"
    )
    assert api.get(url, headers=bearer(people.rep_b)).status_code == 404
    assert api.post(url, headers=bearer(people.admin), json=body).status_code == 201


@pytest.mark.parametrize(
    "body", [{}, {"body": "  "}, {"body": "x" * 2001}, {"body": "ok", "is_system": True}]
)
def test_comment_validation(api: TestClient, people: People, ticket, body: dict) -> None:
    resp = api.post(f"{COMPLAINTS}/{ticket.id}/comments", headers=bearer(people.rep_a), json=body)
    assert resp.status_code == 422


def test_comments_are_allowed_on_closed_tickets_and_paginated(
    api: TestClient, people: People, db: Session
) -> None:
    t = make_complaint(db, people.unit_a, people.rep_a, status=S.closed)
    db.commit()
    url = f"{COMPLAINTS}/{t.id}/comments"
    for i in range(3):
        assert (
            api.post(url, headers=bearer(people.rep_a), json={"body": f"n{i}"}).status_code == 201
        )
    page = api.get(url, headers=bearer(people.rep_a), params={"page": 2, "page_size": 2}).json()
    assert (page["total"], [c["body"] for c in page["items"]]) == (3, ["n2"])


def test_comments_cannot_be_modified_through_the_api(
    api: TestClient, people: People, ticket
) -> None:
    created = api.post(
        f"{COMPLAINTS}/{ticket.id}/comments", headers=bearer(people.rep_a), json={"body": "x"}
    ).json()
    url = f"{COMPLAINTS}/{ticket.id}/comments/{created['id']}"
    for method in ("put", "patch", "delete"):
        assert getattr(api, method)(url, headers=bearer(people.admin)).status_code in (404, 405)


# ---------- the unit's side: confirm / reopen ----------


@pytest.fixture
def resolved(db: Session, people: People):
    t = make_complaint(
        db, people.unit_a, people.rep_a, status=S.resolved, assigned_to=people.engineer.id,
        resolved_at=datetime(2026, 10, 1, tzinfo=UTC),
    )  # fmt: skip
    db.commit()
    return t


def test_unit_confirms_a_resolved_ticket(api: TestClient, people: People, resolved) -> None:
    resp = api.post(f"{COMPLAINTS}/{resolved.id}/confirm", headers=bearer(people.rep_a))
    assert resp.status_code == 200
    out = resp.json()
    assert out["status"] == "closed" and out["closed_at"] is not None
    assert out["resolved_at"] is not None  # kept
    assert system_comments(api, people.admin, resolved.id) == [
        "Status: resolved -> closed. Confirmed by the unit."
    ]
    again = api.post(f"{COMPLAINTS}/{resolved.id}/confirm", headers=bearer(people.rep_a))
    assert (again.status_code, again.json()["error"]["code"]) == (409, "INVALID_TRANSITION")


def test_only_the_units_rep_can_confirm(api: TestClient, people: People, resolved) -> None:
    url = f"{COMPLAINTS}/{resolved.id}/confirm"
    for user in (people.engineer, people.admin, people.auditor):
        assert api.post(url, headers=bearer(user)).status_code == 403  # no closing on their behalf
    assert api.post(url, headers=bearer(people.rep_b)).status_code == 404


def test_confirm_requires_a_resolved_ticket(api: TestClient, people: People, ticket) -> None:
    resp = api.post(f"{COMPLAINTS}/{ticket.id}/confirm", headers=bearer(people.rep_a))
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "INVALID_TRANSITION")


@pytest.mark.parametrize("user", ["rep_a", "engineer", "admin"])
def test_reopening_a_resolved_ticket(api: TestClient, people: People, resolved, user: str) -> None:
    resp = api.post(
        f"{COMPLAINTS}/{resolved.id}/reopen",
        headers=bearer(getattr(people, user)),
        json={"reason": "Fault is back"},
    )
    assert resp.status_code == 200
    out = resp.json()
    assert out["status"] == "reopened"
    assert out["resolved_at"] is None and out["closed_at"] is None
    assert system_comments(api, people.admin, resolved.id) == [
        "Status: resolved -> reopened. Reason: Fault is back"
    ]
    # ...and engineering can pick it up again.
    again = patch(api, people.engineer, resolved.id, assigned_to=str(people.engineer.id))
    assert again.json()["status"] == "in_progress"


def test_reopen_rules(api: TestClient, people: People, resolved, ticket) -> None:
    url = f"{COMPLAINTS}/{resolved.id}/reopen"
    assert api.post(url, headers=bearer(people.rep_a), json={}).status_code == 422
    assert api.post(url, headers=bearer(people.rep_a), json={"reason": " "}).status_code == 422
    assert api.post(url, headers=bearer(people.auditor), json={"reason": "x"}).status_code == 403
    assert api.post(url, headers=bearer(people.rep_b), json={"reason": "x"}).status_code == 404
    not_resolved = api.post(
        f"{COMPLAINTS}/{ticket.id}/reopen", headers=bearer(people.rep_a), json={"reason": "x"}
    )
    assert (not_resolved.status_code, not_resolved.json()["error"]["code"]) == (
        409,
        "INVALID_TRANSITION",
    )


def test_returned_device_must_be_acknowledged_not_confirmed(
    api: TestClient, people: People, db: Session, devices
) -> None:
    t = make_complaint(db, people.unit_a, people.rep_a, device=devices["a"], status=S.resolved)
    returned = make_event(
        db, devices["a"], people.engineer, event_type=EventType.returned_to_unit,
        counterparty_name="Ada", to_status=DeviceStatus.assigned, complaint_id=t.id,
        unit_id=people.unit_a.id,
    )  # fmt: skip
    db.commit()
    for action, body in (("confirm", None), ("reopen", {"reason": "still faulty"})):
        resp = api.post(f"{COMPLAINTS}/{t.id}/{action}", headers=bearer(people.rep_a), json=body)
        assert (resp.status_code, resp.json()["error"]["code"]) == (409, "AWAITS_ACKNOWLEDGEMENT")

    make_ack(
        db, returned, people.rep_a, AckStatus.confirmed
    )  # once acknowledged, no longer blocked
    db.commit()
    assert api.post(f"{COMPLAINTS}/{t.id}/confirm", headers=bearer(people.rep_a)).status_code == 200


def test_unknown_ticket_for_unit_actions(api: TestClient, people: People) -> None:
    assert (
        api.post(f"{COMPLAINTS}/{MISSING}/confirm", headers=bearer(people.rep_a)).status_code == 404
    )
    reopen = api.post(
        f"{COMPLAINTS}/{MISSING}/reopen", headers=bearer(people.rep_a), json={"reason": "x"}
    )
    assert reopen.status_code == 404


def test_other_units_tickets_stay_untouched(
    api: TestClient, people: People, db: Session, resolved
) -> None:
    api.post(f"{COMPLAINTS}/{resolved.id}/confirm", headers=bearer(people.rep_b))
    api.post(
        f"{COMPLAINTS}/{resolved.id}/reopen", headers=bearer(people.rep_b), json={"reason": "x"}
    )
    db.refresh(resolved)
    assert resolved.status is S.resolved
    assert (
        db.scalars(
            select(ComplaintComment).where(ComplaintComment.complaint_id == resolved.id)
        ).all()
        == []
    )


def test_unit_creation_of_helper_units(db: Session) -> None:
    assert make_unit(db).id  # factories still work alongside the people fixture
