"""SPEC 12.1 tests 6 and 7 (without costs), acknowledgement rules and the pending list."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Acknowledgement, Device, DeviceEvent
from app.models.enums import AckStatus, ComplaintStatus, DeviceStatus, EventType
from tests.api_helpers import People, bearer
from tests.event_helpers import API, acknowledge, ok, post_event
from tests.factories import (
    make_ack,
    make_complaint,
    make_device,
    make_event,
)

S = DeviceStatus


def get(api: TestClient, user, path: str, **params):
    resp = api.get(f"{API}{path}", headers=bearer(user), params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def ticket_of(api: TestClient, people: People, ticket_id: str) -> dict:
    return get(api, people.admin, f"/complaints/{ticket_id}")


def transitions(ticket: dict) -> list[str]:
    import re

    out = []
    for c in ticket["comments"]:
        if c["is_system"]:
            out += [f"{a}>{b}" for a, b in re.findall(r"Status: (\w+) -> (\w+)\.", c["body"])]
    return out


class Scene:
    """Drives one device through its life over HTTP."""

    def __init__(self, api: TestClient, people: People) -> None:
        self.api, self.people = api, people
        self.eng, self.rep = people.engineer, people.rep_a

    def event(self, device_id, event_type, **body) -> dict:
        return ok(post_event(self.api, self.eng, device_id, event_type, **body))

    def register_and_assign(self) -> str:
        device = ok(
            self.api.post(f"{API}/devices", headers=bearer(self.eng),
                          json={"device_type": "laptop", "serial_number": f"SN-{id(self)}"})
        )  # fmt: skip
        self.assign = self.event(
            device["id"], "assigned_to_unit", unit_id=str(self.people.unit_a.id),
            counterparty_name="Ada Obi", counterparty_user_id=str(self.rep.id),
        )  # fmt: skip
        return device["id"]

    def raise_ticket(self, device_id) -> str:
        resp = self.api.post(
            f"{API}/complaints", headers=bearer(self.rep),
            json={"title": "No power", "description": "Dead", "device_id": device_id},
        )  # fmt: skip
        return ok(resp)["id"]

    def repair_cycle(self, device_id, ticket_id) -> dict:
        """Intake to return; returns the interesting events."""
        ev = {}
        ev["intake"] = self.event(device_id, "received_for_repair", complaint_id=ticket_id,
                                  counterparty_name="Ada Obi")  # fmt: skip
        ev["diagnosed"] = self.event(device_id, "diagnosed", diagnosis="Dead battery")
        ev["started"] = self.event(device_id, "repair_started")
        ev["completed"] = self.event(device_id, "repair_completed", notes="Battery replaced")
        ev["returned"] = self.event(device_id, "returned_to_unit", counterparty_name="Ada Obi")
        return ev


@pytest.fixture
def scene(api: TestClient, people: People) -> Scene:
    return Scene(api, people)


# ---------- SPEC 12.1 test 6: complaint -> ... -> ticket closed ----------


def test_full_lifecycle_closes_the_ticket(
    scene: Scene, api: TestClient, people: People, db: Session
) -> None:
    device_id = scene.register_and_assign()
    assert ok(acknowledge(api, people.rep_a, scene.assign["id"]))["ack_state"] == "confirmed"

    ticket_id = scene.raise_ticket(device_id)
    cycle = scene.repair_cycle(device_id, ticket_id)

    mid = ticket_of(api, people, ticket_id)
    assert mid["status"] == "resolved" and mid["resolved_at"] and mid["closed_at"] is None
    assert mid["assigned_to"]["id"] == str(people.engineer.id)  # picked up at intake

    assert ok(acknowledge(api, people.rep_a, cycle["intake"]["id"]))["ack_state"] == "confirmed"
    assert ticket_of(api, people, ticket_id)["status"] == "resolved"  # intake ack changes nothing
    closed = ok(acknowledge(api, people.rep_a, cycle["returned"]["id"]))
    assert closed["ack_state"] == "confirmed" and closed["acknowledgement"]["status"] == "confirmed"

    final = ticket_of(api, people, ticket_id)
    assert final["status"] == "closed" and final["closed_at"]
    assert transitions(final) == ["open>in_progress", "in_progress>resolved", "resolved>closed"]
    # The ticket shows the whole repair, not just intake and return.
    assert [e["event_type"] for e in final["events"]] == [
        "received_for_repair", "diagnosed", "repair_started", "repair_completed", "returned_to_unit"
    ]  # fmt: skip

    timeline = get(api, people.rep_a, f"/devices/{device_id}/timeline")
    assert timeline["device"]["status"] == "assigned"
    assert [(e["event_type"], e["ack_state"]) for e in timeline["events"]] == [
        ("device_registered", "not_required"), ("assigned_to_unit", "confirmed"),
        ("received_for_repair", "confirmed"), ("diagnosed", "not_required"),
        ("repair_started", "not_required"), ("repair_completed", "not_required"),
        ("returned_to_unit", "confirmed"),
    ]  # fmt: skip
    diag = next(e for e in timeline["events"] if e["event_type"] == "diagnosed")
    assert diag["diagnosis"] == "Dead battery"
    assert all("vendor" not in e for e in timeline["events"])  # repairs are in-house
    stamps = [e["occurred_at"] for e in timeline["events"]]
    assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps)

    assert get(api, people.admin, "/acknowledgements/pending")["total"] == 0


# ---------- SPEC 12.1 test 7: the dispute path ----------


def test_disputed_return_reopens_the_ticket_and_a_second_cycle_closes_it(
    scene: Scene, api: TestClient, people: People, db: Session
) -> None:
    device_id = scene.register_and_assign()
    ticket_id = scene.raise_ticket(device_id)
    first = scene.repair_cycle(device_id, ticket_id)

    assert acknowledge(api, people.rep_a, first["returned"]["id"], "disputed").status_code == 422
    disputed = ok(
        acknowledge(
            api, people.rep_a, first["returned"]["id"], "disputed", comment="Still no power"
        )
    )
    assert disputed["ack_state"] == "disputed"
    assert disputed["acknowledgement"]["comment"] == "Still no power"

    reopened = ticket_of(api, people, ticket_id)
    assert reopened["status"] == "reopened" and reopened["resolved_at"] is None
    device = get(api, people.admin, f"/devices/{device_id}")
    assert device["status"] == "assigned"  # a dispute never rewrites the device or the history

    # Engineering answers with a note, then repairs again against the same ticket.
    note = scene.event(
        device_id, "note_added", notes="Re-checking the charger",
        corrects_event_id=first["returned"]["id"], complaint_id=ticket_id,
    )  # fmt: skip
    assert note["corrects_event_id"] == first["returned"]["id"]
    second = scene.repair_cycle(device_id, ticket_id)
    assert ticket_of(api, people, ticket_id)["status"] == "resolved"
    ok(acknowledge(api, people.rep_a, second["returned"]["id"]))

    final = ticket_of(api, people, ticket_id)
    assert final["status"] == "closed"
    assert transitions(final) == [
        "open>in_progress", "in_progress>resolved", "resolved>reopened",
        "reopened>in_progress", "in_progress>resolved", "resolved>closed",
    ]  # fmt: skip
    types = [e["event_type"] for e in final["events"]]
    assert types.count("received_for_repair") == 2 and types.count("returned_to_unit") == 2
    assert "note_added" in types


# ---------- intake effects on the ticket (D1, D2) ----------


def test_intake_links_a_deviceless_ticket_and_assigns_the_engineer(
    scene: Scene, api: TestClient, people: People
) -> None:
    device_id = scene.register_and_assign()
    resp = api.post(f"{API}/complaints", headers=bearer(people.rep_a),
                    json={"title": "PC dead", "description": "Which one? this one"})  # fmt: skip
    ticket_id = ok(resp)["id"]
    scene.event(device_id, "received_for_repair", complaint_id=ticket_id, counterparty_name="Ada")
    ticket = ticket_of(api, people, ticket_id)
    assert ticket["device"]["id"] == device_id
    assert ticket["assigned_to"]["id"] == str(people.engineer.id)
    assert ticket["status"] == "in_progress"
    (note,) = [c["body"] for c in ticket["comments"] if c["is_system"]]
    assert "Linked to device" in note and "Assigned to" in note


# ---------- acknowledgement rules ----------


@pytest.fixture
def awaiting(scene: Scene, api: TestClient, people: People):
    """A device just handed to unit A: one assignment waiting for the unit."""
    device_id = scene.register_and_assign()
    return {"device_id": device_id, "event_id": scene.assign["id"]}


def test_an_event_can_be_acknowledged_only_once(
    api: TestClient, people: People, db: Session, awaiting
) -> None:
    twin = make_user_rep_in_unit_a(db, people)
    ok(acknowledge(api, people.rep_a, awaiting["event_id"]))
    for rep in (people.rep_a, twin):
        again = acknowledge(api, rep, awaiting["event_id"], "disputed", comment="changed my mind")
        assert (again.status_code, again.json()["error"]["code"]) == (409, "ALREADY_ACKNOWLEDGED")
    rows = db.scalars(
        select(Acknowledgement).where(Acknowledgement.event_id == awaiting["event_id"])
    )
    assert [a.status for a in rows] == [AckStatus.confirmed]  # the first answer stands


def make_user_rep_in_unit_a(db: Session, people: People):
    from app.models.enums import UserRole
    from tests.factories import make_user

    user = make_user(db, UserRole.unit_rep, people.unit_a)
    db.commit()
    return user


def test_only_a_rep_of_the_events_unit_may_acknowledge(
    api: TestClient, people: People, awaiting
) -> None:
    eid = awaiting["event_id"]
    other_unit = acknowledge(api, people.rep_b, eid)
    assert (other_unit.status_code, other_unit.json()["error"]["code"]) == (403, "FORBIDDEN")
    for staff in (people.admin, people.engineer, people.auditor):
        assert acknowledge(api, staff, eid).status_code == 403
    assert (
        api.post(f"{API}/events/{eid}/acknowledge", json={"status": "confirmed"}).status_code == 401
    )
    assert get(api, people.admin, f"/events/{eid}")["ack_state"] == "pending"  # still unanswered


@pytest.mark.parametrize("event_type", ["diagnosed", "note_added", "repair_completed"])
def test_events_that_need_no_acknowledgement_reject_one(
    scene: Scene, api: TestClient, people: People, db: Session, event_type: str
) -> None:
    device = make_device(db, people.engineer, unit_id=people.unit_a.id, status=S.in_repair)
    db.commit()
    if event_type == "diagnosed":
        device.status = S.received_for_repair
        db.commit()
        body = {"diagnosis": "x"}
    else:
        body = {"notes": "x"}
    event = scene.event(device.id, event_type, **body)
    resp = acknowledge(api, people.rep_a, event["id"])
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "ACK_NOT_REQUIRED")


def test_acknowledgement_request_validation(api: TestClient, people: People, awaiting) -> None:
    url = f"{API}/events/{awaiting['event_id']}/acknowledge"
    rep = bearer(people.rep_a)
    for body in (
        {}, {"status": "maybe"}, {"status": "disputed"}, {"status": "disputed", "comment": "  "},
        {"status": "confirmed", "acknowledged_by": "x"},
        {"status": "confirmed", "comment": "c" * 2001},
    ):  # fmt: skip
        assert api.post(url, headers=rep, json=body).status_code == 422, body
    missing = acknowledge(api, people.rep_a, 987654321)
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "EVENT_NOT_FOUND")


def test_a_dispute_never_changes_the_event_or_the_device(
    api: TestClient, people: People, db: Session, awaiting
) -> None:
    before = db.get(DeviceEvent, awaiting["event_id"])
    snapshot = (
        before.event_type,
        before.to_status,
        before.unit_id,
        before.notes,
        before.occurred_at,
    )
    ok(acknowledge(api, people.rep_a, awaiting["event_id"], "disputed", comment="Wrong model"))
    db.expire_all()
    after = db.get(DeviceEvent, awaiting["event_id"])
    assert (
        after.event_type,
        after.to_status,
        after.unit_id,
        after.notes,
        after.occurred_at,
    ) == snapshot
    assert db.get(Device, after.device_id).status is S.assigned


# ---------- pending acknowledgements ----------


def backdated(db: Session, people: People, device, event_type, to_status, days: float, **kw):
    return make_event(
        db, device, people.engineer, event_type=event_type, to_status=to_status,
        occurred_at=datetime.now(UTC) - timedelta(days=days), counterparty_name="Ada", **kw,
    )  # fmt: skip


@pytest.fixture
def pending(db: Session, people: People):
    a = make_device(db, people.engineer, unit_id=people.unit_a.id, status=S.assigned)
    b = make_device(db, people.engineer, unit_id=people.unit_b.id, status=S.assigned)
    old = backdated(
        db, people, a, EventType.assigned_to_unit, S.assigned, 10, unit_id=people.unit_a.id
    )
    fresh = backdated(db, people, a, EventType.received_for_repair, S.received_for_repair, 1,
                      unit_id=people.unit_a.id)  # fmt: skip
    answered = backdated(
        db, people, a, EventType.returned_to_unit, S.assigned, 5, unit_id=people.unit_a.id
    )
    make_ack(db, answered, people.rep_a, AckStatus.confirmed)
    not_required = backdated(
        db, people, a, EventType.diagnosed, S.diagnosed, 20,
        unit_id=people.unit_a.id, diagnosis="Battery",
    )  # fmt: skip
    other = backdated(
        db, people, b, EventType.assigned_to_unit, S.assigned, 4, unit_id=people.unit_b.id
    )
    db.commit()
    return {"old": old.id, "fresh": fresh.id, "other": other.id, "answered": answered.id,
            "skipped": not_required.id}  # fmt: skip


def pending_ids(resp: dict) -> list[int]:
    return [i["event_id"] for i in resp["items"]]


def test_pending_list_for_staff(api: TestClient, people: People, pending) -> None:
    for user in (people.admin, people.engineer, people.auditor):
        body = get(api, user, "/acknowledgements/pending")
        assert pending_ids(body) == [
            pending["old"],
            pending["other"],
            pending["fresh"],
        ]  # oldest first
        assert body["total"] == 3
    body = get(api, people.engineer, "/acknowledgements/pending")
    old = body["items"][0]
    assert old["event_type"] == "assigned_to_unit" and old["unit"]["code"] == "A"
    assert old["pending_days"] == 10 and old["overdue"] is True
    assert old["device"]["asset_tag"] and old["actor"]["id"] == str(people.engineer.id)
    fresh = next(i for i in body["items"] if i["event_id"] == pending["fresh"])
    assert fresh["overdue"] is False and fresh["pending_days"] == 1


def test_pending_filters(api: TestClient, people: People, pending) -> None:
    eng = people.engineer
    assert pending_ids(get(api, eng, "/acknowledgements/pending", overdue=True)) == [
        pending["old"],
        pending["other"],
    ]  # 10 and 4 days old (limit is 3)
    assert pending_ids(get(api, eng, "/acknowledgements/pending", overdue=False)) == [
        pending["fresh"]
    ]
    unit_b = get(api, eng, "/acknowledgements/pending", unit_id=str(people.unit_b.id))
    assert pending_ids(unit_b) == [pending["other"]]
    page = get(api, eng, "/acknowledgements/pending", page=2, page_size=2)
    assert pending_ids(page) == [pending["fresh"]] and page["total"] == 3


def test_pending_list_for_a_unit_rep_is_their_units_only(
    api: TestClient, people: People, pending
) -> None:
    mine = get(api, people.rep_a, "/acknowledgements/pending")
    assert pending_ids(mine) == [pending["old"], pending["fresh"]]
    theirs = get(api, people.rep_b, "/acknowledgements/pending")
    assert pending_ids(theirs) == [pending["other"]]
    widened = get(api, people.rep_a, "/acknowledgements/pending", unit_id=str(people.unit_b.id))
    assert pending_ids(widened) == pending_ids(mine)


def test_acknowledging_removes_an_event_from_the_pending_list(
    api: TestClient, people: People, pending
) -> None:
    ok(acknowledge(api, people.rep_a, pending["old"], "disputed", comment="never received"))
    assert pending_ids(get(api, people.rep_a, "/acknowledgements/pending")) == [pending["fresh"]]
    assert get(api, people.admin, f"/events/{pending['old']}")["ack_state"] == "disputed"


def test_nothing_is_ever_auto_confirmed(
    api: TestClient, people: People, db: Session, pending
) -> None:
    get(api, people.admin, "/acknowledgements/pending")
    assert (
        db.scalar(select(Acknowledgement.id).where(Acknowledgement.event_id == pending["old"]))
        is None
    )


# ---------- decommissioning mid-repair (D3) ----------


def test_decommissioning_mid_repair_frees_the_ticket(
    scene: Scene, api: TestClient, people: People
) -> None:
    device_id = scene.register_and_assign()
    ticket_id = scene.raise_ticket(device_id)
    scene.event(device_id, "received_for_repair", complaint_id=ticket_id, counterparty_name="Ada")
    scene.event(device_id, "diagnosed", diagnosis="Motherboard failure")

    stuck = api.patch(f"{API}/complaints/{ticket_id}", headers=bearer(people.engineer),
                      json={"status": "closed", "comment": "cannot fix"})  # fmt: skip
    assert (stuck.status_code, stuck.json()["error"]["code"]) == (409, "DEVICE_IN_REPAIR")

    scene.event(device_id, "decommissioned", notes="Beyond repair")
    done = api.patch(
        f"{API}/complaints/{ticket_id}",
        headers=bearer(people.engineer),
        json={"status": "resolved", "comment": "Decommissioned; replacement issued"},
    )
    assert done.status_code == 200 and done.json()["status"] == "resolved"
    assert get(api, people.admin, f"/devices/{device_id}")["status"] == "decommissioned"


def test_a_ticket_with_no_repair_cycle_is_unaffected_by_decommissioning(
    api: TestClient, people: People, db: Session
) -> None:
    device = make_device(db, people.engineer, unit_id=people.unit_a.id, status=S.assigned)
    ticket = make_complaint(
        db, people.unit_a, people.rep_a, device=device, status=ComplaintStatus.open
    )
    db.commit()
    ok(post_event(api, people.engineer, device, "decommissioned", notes="Retired"))
    resp = api.patch(f"{API}/complaints/{ticket.id}", headers=bearer(people.engineer),
                     json={"status": "closed", "comment": "Device retired"})  # fmt: skip
    assert resp.status_code == 200
