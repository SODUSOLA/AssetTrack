import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Device, DeviceEvent
from app.models.enums import ComplaintStatus, DeviceStatus, EventType, UserRole
from app.services.event_rules import RULES, allowed_events, resulting_status
from tests.api_helpers import People, bearer
from tests.event_helpers import API, ok, post_event
from tests.factories import (
    make_complaint,
    make_device,
    make_event,
    make_user,
)

S = DeviceStatus
MISSING = "00000000-0000-0000-0000-000000000099"


def device_in(db: Session, people: People, status: S, **kw) -> Device:
    unit = None if status is S.in_stock else people.unit_a
    d = make_device(db, people.engineer, unit_id=unit.id if unit else None, status=status, **kw)
    db.commit()
    return d


def events_of(db: Session, device) -> list[DeviceEvent]:
    return list(
        db.scalars(
            select(DeviceEvent).where(DeviceEvent.device_id == device.id).order_by(DeviceEvent.id)
        )
    )


def valid_body(event_type: EventType, people: People, device: Device, ticket) -> dict:
    return {
        "assigned_to_unit": {"unit_id": str(people.unit_b.id), "counterparty_name": "Bola"},
        "received_for_repair": {"complaint_id": str(ticket.id), "counterparty_name": "Ada"},
        "diagnosed": {"diagnosis": "Dead battery"},
        "repair_started": {},
        "parts_requested": {"notes": "Need a battery"},
        "repair_completed": {"notes": "Fixed"},
        "returned_to_unit": {"counterparty_name": "Ada"},
        "decommissioned": {"notes": "Beyond repair"},
        "note_added": {"notes": "FYI"},
    }[event_type.value]


# ---------- every status x every event ----------


@pytest.mark.parametrize("event_type", list(RULES))
@pytest.mark.parametrize("status", list(S))
def test_transition_matrix_over_http(
    api: TestClient, people: People, db: Session, status: S, event_type: EventType
) -> None:
    device = device_in(db, people, status)
    ticket = make_complaint(
        db, people.unit_a, people.rep_a, device=device if device.unit_id else None
    )
    db.commit()
    body = valid_body(event_type, people, device, ticket)
    resp = post_event(api, people.engineer, device, event_type.value, **body)

    if event_type in allowed_events(status):
        out = ok(resp)
        assert out["event_type"] == event_type.value
        assert out["from_status"] == status.value
        assert out["to_status"] == resulting_status(event_type, status).value
        db.refresh(device)
        assert device.status is resulting_status(event_type, status)
        assert len(events_of(db, device)) == 1
    else:
        assert resp.status_code == 409
        err = resp.json()["error"]
        assert err["code"] == "INVALID_TRANSITION"
        assert err["details"] == {
            "current": status.value,
            "attempted": event_type.value,
            "allowed": [e.value for e in allowed_events(status)],
        }
        db.refresh(device)
        assert device.status is status and events_of(db, device) == []


def test_skipping_states_is_rejected(api: TestClient, people: People, db: Session) -> None:
    device = device_in(db, people, S.assigned)
    resp = post_event(api, people.engineer, device, "repair_completed", notes="done already")
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "INVALID_TRANSITION")


# ---------- request shape ----------

BAD_BODIES = {
    "no type": {},
    "unknown type": {"event_type": "teleported"},
    "system-only type": {"event_type": "device_registered"},
    "assign without unit": {"event_type": "assigned_to_unit", "counterparty_name": "A"},
    "assign without receiver": {"event_type": "assigned_to_unit", "unit_id": MISSING},
    "intake without ticket": {"event_type": "received_for_repair", "counterparty_name": "A"},
    "intake without depositor": {"event_type": "received_for_repair", "complaint_id": MISSING},
    "diagnosed without diagnosis": {"event_type": "diagnosed"},
    "diagnosed blank": {"event_type": "diagnosed", "diagnosis": "  "},
    "parts without notes": {"event_type": "parts_requested"},
    "the vendor step no longer exists": {"event_type": "sent_to_vendor", "vendor_id": MISSING},
    "completed without notes": {"event_type": "repair_completed"},
    "return without collector": {"event_type": "returned_to_unit"},
    "decommission without reason": {"event_type": "decommissioned"},
    "note without notes": {"event_type": "note_added"},
    "client time": {"event_type": "repair_started", "occurred_at": "2020-01-01T00:00:00Z"},
    "client actor": {"event_type": "repair_started", "actor_id": MISSING},
    "client status": {"event_type": "repair_started", "to_status": "repaired"},
    "unit on a repair step": {"event_type": "repair_started", "unit_id": MISSING},
    "ticket on a repair step": {
        "event_type": "diagnosed",
        "diagnosis": "x",
        "complaint_id": MISSING,
    },
    "diagnosis on a note": {"event_type": "note_added", "notes": "x", "diagnosis": "y"},
    "vendor id on a note": {"event_type": "note_added", "notes": "x", "vendor_id": MISSING},
    "too long notes": {"event_type": "note_added", "notes": "n" * 2001},
    "bad uuid": {"event_type": "received_for_repair", "complaint_id": "nope"},
}


@pytest.mark.parametrize("name", sorted(BAD_BODIES))
def test_malformed_requests_are_rejected_without_side_effects(
    api: TestClient, people: People, db: Session, name: str
) -> None:
    device = device_in(db, people, S.assigned)
    resp = api.post(
        f"{API}/devices/{device.id}/events", headers=bearer(people.engineer), json=BAD_BODIES[name]
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    db.refresh(device)
    assert device.status is S.assigned and events_of(db, device) == []


def test_unknown_device_is_404(api: TestClient, people: People) -> None:
    resp = post_event(api, people.engineer, MISSING, "note_added", notes="x")
    assert (resp.status_code, resp.json()["error"]["code"]) == (404, "DEVICE_NOT_FOUND")


@pytest.mark.parametrize("user", ["rep_a", "auditor"])
def test_only_engineering_logs_events(
    api: TestClient, people: People, db: Session, user: str
) -> None:
    device = device_in(db, people, S.assigned)
    resp = post_event(api, getattr(people, user), device, "note_added", notes="x")
    assert resp.status_code == 403 and events_of(db, device) == []


# ---------- what an event records ----------


def test_response_describes_the_event(api: TestClient, people: People, db: Session) -> None:
    device = device_in(db, people, S.assigned)
    ticket = make_complaint(db, people.unit_a, people.rep_a, device=device)
    db.commit()
    out = ok(
        post_event(
            api, people.engineer, device, "received_for_repair",
            complaint_id=str(ticket.id), counterparty_name="Ada Obi", notes="Cracked screen",
            counterparty_user_id=str(people.rep_a.id),
        )
    )  # fmt: skip
    assert out["actor"]["id"] == str(people.engineer.id)
    assert out["unit"]["code"] == "A"
    assert out["device"] == {
        "id": str(device.id), "asset_tag": device.asset_tag, "device_type": device.device_type
    }  # fmt: skip
    assert out["counterparty_name"] == "Ada Obi"
    assert out["counterparty_user"]["id"] == str(people.rep_a.id)
    assert out["complaint"]["ticket_no"] == ticket.ticket_no
    assert out["notes"] == "Cracked screen" and out["diagnosis"] is None
    assert out["ack_state"] == "pending" and out["acknowledgement"] is None
    assert out["occurred_at"]


def test_events_that_need_no_acknowledgement_say_so(
    api: TestClient, people: People, db: Session
) -> None:
    device = device_in(db, people, S.assigned)
    out = ok(post_event(api, people.engineer, device, "note_added", notes="x"))
    assert (out["ack_state"], out["pending_days"], out["overdue"]) == ("not_required", None, False)


def test_the_server_stamps_time_in_the_order_things_happened(
    api: TestClient, people: People, db: Session
) -> None:
    device = device_in(db, people, S.assigned)
    stamps = [
        ok(post_event(api, people.engineer, device, "note_added", notes=f"n{i}"))["occurred_at"]
        for i in range(3)
    ]
    assert stamps == sorted(stamps) and len(set(stamps)) == 3  # strictly increasing


def test_assignment_moves_the_device_into_the_unit(
    api: TestClient, people: People, db: Session
) -> None:
    device = device_in(db, people, S.in_stock)
    out = ok(
        post_event(
            api, people.engineer, device, "assigned_to_unit",
            unit_id=str(people.unit_a.id), counterparty_name="Ada",
            counterparty_user_id=str(people.rep_a.id),
        )
    )  # fmt: skip
    assert out["unit"]["id"] == str(people.unit_a.id)  # the receiving unit is the snapshot
    detail = api.get(f"{API}/devices/{device.id}", headers=bearer(people.rep_a))
    assert detail.status_code == 200  # now visible to the unit
    assert detail.json()["unit"]["code"] == "A" and detail.json()["status"] == "assigned"


@pytest.mark.parametrize("who", ["engineer", "other_unit_rep", "inactive_rep", "unknown"])
def test_counterparty_user_must_be_an_active_rep_of_the_unit(
    api: TestClient, people: People, db: Session, who: str
) -> None:
    inactive = make_user(db, UserRole.unit_rep, people.unit_a, is_active=False)
    db.commit()
    user_id = {
        "engineer": people.engineer.id, "other_unit_rep": people.rep_b.id,
        "inactive_rep": inactive.id, "unknown": MISSING,
    }[who]  # fmt: skip
    device = device_in(db, people, S.in_stock)
    resp = post_event(
        api, people.engineer, device, "assigned_to_unit", unit_id=str(people.unit_a.id),
        counterparty_name="Ada", counterparty_user_id=str(user_id),
    )  # fmt: skip
    assert (resp.status_code, resp.json()["error"]["code"]) == (422, "COUNTERPARTY_INVALID")
    db.refresh(device)
    assert device.unit_id is None and device.status is S.in_stock


@pytest.mark.parametrize("which", ["unknown", "inactive"])
def test_assignment_needs_an_active_unit(
    api: TestClient, people: People, db: Session, which: str
) -> None:
    people.unit_b.is_active = False
    db.commit()
    unit_id = MISSING if which == "unknown" else str(people.unit_b.id)
    device = device_in(db, people, S.in_stock)
    resp = post_event(api, people.engineer, device, "assigned_to_unit", unit_id=unit_id,
                      counterparty_name="Bola")  # fmt: skip
    assert (resp.status_code, resp.json()["error"]["code"]) == (422, "UNIT_NOT_FOUND")


# ---------- intake references ----------


def test_intake_reference_checks(api: TestClient, people: People, db: Session) -> None:
    device = device_in(db, people, S.assigned)
    other_device = device_in(db, people, S.assigned)
    foreign = make_complaint(db, people.unit_b, people.rep_b)
    about_other = make_complaint(db, people.unit_a, people.rep_a, device=other_device)
    db.commit()

    def intake(complaint_id):
        return post_event(api, people.engineer, device, "received_for_repair",
                          complaint_id=str(complaint_id), counterparty_name="Ada")  # fmt: skip

    for complaint_id, status, code in (
        (MISSING, 404, "COMPLAINT_NOT_FOUND"),
        (foreign.id, 422, "COMPLAINT_UNIT_MISMATCH"),
        (about_other.id, 422, "COMPLAINT_DEVICE_MISMATCH"),
    ):
        resp = intake(complaint_id)
        assert (resp.status_code, resp.json()["error"]["code"]) == (status, code)
    assert events_of(db, device) == []


@pytest.mark.parametrize("status", [ComplaintStatus.resolved, ComplaintStatus.closed])
def test_a_finished_ticket_rolls_the_whole_intake_back(
    api: TestClient, people: People, db: Session, status: ComplaintStatus
) -> None:
    device = device_in(db, people, S.assigned)
    ticket = make_complaint(db, people.unit_a, people.rep_a, device=device, status=status)
    db.commit()
    resp = post_event(api, people.engineer, device, "received_for_repair",
                      complaint_id=str(ticket.id), counterparty_name="Ada")  # fmt: skip
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "TICKET_NOT_ACTIVE")
    db.refresh(device)
    assert device.status is S.assigned  # nothing half-done
    assert events_of(db, device) == []


# ---------- notes and corrections ----------


def test_a_note_can_correct_an_earlier_event_of_the_same_device(
    api: TestClient, people: People, db: Session
) -> None:
    device = device_in(db, people, S.assigned)
    first = ok(post_event(api, people.engineer, device, "note_added", notes="serial typo"))
    fix = ok(
        post_event(
            api, people.engineer, device, "note_added", notes="serial is X1",
            corrects_event_id=first["id"],
        )
    )  # fmt: skip
    assert fix["corrects_event_id"] == first["id"]
    assert fix["to_status"] == "assigned" and fix["from_status"] == "assigned"


def test_a_note_cannot_correct_another_devices_event(
    api: TestClient, people: People, db: Session
) -> None:
    mine, theirs = device_in(db, people, S.assigned), device_in(db, people, S.assigned)
    foreign_event = make_event(db, theirs, people.engineer, to_status=S.assigned)
    db.commit()
    for event_id in (foreign_event.id, 999999999):
        resp = post_event(api, people.engineer, mine, "note_added", notes="x",
                          corrects_event_id=event_id)  # fmt: skip
        assert (resp.status_code, resp.json()["error"]["code"]) == (422, "CORRECTS_EVENT_INVALID")


def test_a_note_may_name_a_ticket_of_the_devices_unit(
    api: TestClient, people: People, db: Session
) -> None:
    device = device_in(db, people, S.assigned)
    ticket = make_complaint(db, people.unit_a, people.rep_a)
    foreign = make_complaint(db, people.unit_b, people.rep_b)
    db.commit()
    out = ok(post_event(api, people.engineer, device, "note_added", notes="x",
                        complaint_id=str(ticket.id)))  # fmt: skip
    assert out["complaint"]["ticket_no"] == ticket.ticket_no
    bad = post_event(
        api, people.engineer, device, "note_added", notes="x", complaint_id=str(foreign.id)
    )
    assert (bad.status_code, bad.json()["error"]["code"]) == (422, "COMPLAINT_UNIT_MISMATCH")
    stock = device_in(db, people, S.in_stock)
    no_unit = post_event(
        api, people.engineer, stock, "note_added", notes="x", complaint_id=str(ticket.id)
    )
    assert no_unit.status_code == 422


# ---------- decommissioning ----------


def test_a_decommissioned_device_only_takes_notes(
    api: TestClient, people: People, db: Session
) -> None:
    device = device_in(db, people, S.in_repair)
    ok(post_event(api, people.engineer, device, "decommissioned", notes="Water damage"))
    assert ok(post_event(api, people.engineer, device, "note_added", notes="Disposed"))
    for event_type in ("repair_completed", "assigned_to_unit", "decommissioned"):
        resp = post_event(api, people.engineer, device, event_type, notes="x")
        assert resp.status_code in (409, 422)
    again = post_event(api, people.engineer, device, "decommissioned", notes="again")
    assert again.json()["error"]["details"]["allowed"] == ["note_added"]
    db.refresh(device)
    assert device.status is S.decommissioned and device.unit_id == people.unit_a.id  # unit kept


# ---------- reading ----------


@pytest.fixture
def history(api: TestClient, people: People, db: Session):
    """Unit A device through intake, diagnosis and repair start; one device in unit B."""
    a = device_in(db, people, S.in_stock)
    b = device_in(db, people, S.in_stock)
    eng = people.engineer
    ids = {}
    ids["assign_a"] = ok(post_event(api, eng, a, "assigned_to_unit", unit_id=str(people.unit_a.id),
                                    counterparty_name="Ada"))["id"]  # fmt: skip
    ticket = make_complaint(db, people.unit_a, people.rep_a, device=a)
    db.commit()
    ids["intake"] = ok(post_event(api, eng, a, "received_for_repair", complaint_id=str(ticket.id),
                                  counterparty_name="Ada"))["id"]  # fmt: skip
    ids["diag"] = ok(post_event(api, eng, a, "diagnosed", diagnosis="Battery"))["id"]
    ids["start"] = ok(post_event(api, eng, a, "repair_started"))["id"]
    assign_b = post_event(
        api, people.admin, b, "assigned_to_unit",
        unit_id=str(people.unit_b.id), counterparty_name="Bola",
    )  # fmt: skip
    ids["assign_b"] = ok(assign_b)["id"]
    return {"a": a, "b": b, "ids": ids, "ticket": ticket}


def event_ids(resp) -> list[int]:
    return [e["id"] for e in resp.json()["items"]]


def test_the_log_is_newest_first_and_filterable(api: TestClient, people: People, history) -> None:
    ids, a = history["ids"], history["a"]
    eng = bearer(people.engineer)

    def get(**params):
        resp = api.get(f"{API}/events", headers=eng, params=params)
        assert resp.status_code == 200, resp.text
        return event_ids(resp)

    every = get()
    assert every[:5] == [
        ids["assign_b"],
        ids["start"],
        ids["diag"],
        ids["intake"],
        ids["assign_a"],
    ]
    assert get(device_id=str(a.id)) == [ids["start"], ids["diag"], ids["intake"], ids["assign_a"]]
    assert get(event_type="assigned_to_unit") == [ids["assign_b"], ids["assign_a"]]
    assert get(actor_id=str(people.admin.id)) == [ids["assign_b"]]
    assert get(unit_id=str(people.unit_b.id)) == [ids["assign_b"]]
    assert get(device_id=str(a.id), event_type="diagnosed") == [ids["diag"]]
    assert get(date_from="2000-01-01", date_to="2000-01-02") == []
    assert len(get(date_from="2020-01-01")) == len(every)


def test_log_pagination_and_validation(api: TestClient, people: People, history) -> None:
    eng = bearer(people.auditor)
    page = api.get(f"{API}/events", headers=eng, params={"page_size": 2, "page": 2}).json()
    assert (page["page"], page["page_size"], len(page["items"])) == (2, 2, 2)
    assert page["total"] >= 5
    for params in (
        {"event_type": "x"},
        {"device_id": "n"},
        {"date_from": "2026-11-02", "date_to": "2026-11-01"},
    ):
        assert api.get(f"{API}/events", headers=eng, params=params).status_code == 422


def test_unit_rep_sees_only_events_of_their_devices(
    api: TestClient, people: People, history
) -> None:
    ids = history["ids"]
    rep_a = api.get(f"{API}/events", headers=bearer(people.rep_a))
    assert set(event_ids(rep_a)) == {ids["assign_a"], ids["intake"], ids["diag"], ids["start"]}
    rep_b = api.get(f"{API}/events", headers=bearer(people.rep_b))
    assert event_ids(rep_b) == [ids["assign_b"]]
    widened = api.get(f"{API}/events", headers=bearer(people.rep_a),
                      params={"unit_id": str(people.unit_b.id)})  # fmt: skip
    assert set(event_ids(widened)) == set(event_ids(rep_a))
    other_device = api.get(f"{API}/events", headers=bearer(people.rep_a),
                           params={"device_id": str(history["b"].id)})  # fmt: skip
    assert other_device.json()["total"] == 0


def test_one_event_and_its_visibility(api: TestClient, people: People, history) -> None:
    ids = history["ids"]
    url = f"{API}/events/{ids['intake']}"
    for user in (people.admin, people.engineer, people.auditor, people.rep_a):
        resp = api.get(url, headers=bearer(user))
        assert resp.status_code == 200 and resp.json()["event_type"] == "received_for_repair"
    hidden = api.get(url, headers=bearer(people.rep_b))
    gone = api.get(f"{API}/events/987654321", headers=bearer(people.rep_b))
    assert hidden.status_code == 404 == gone.status_code
    assert hidden.json() == gone.json() and hidden.json()["error"]["code"] == "EVENT_NOT_FOUND"
    assert api.get(f"{API}/events/not-a-number", headers=bearer(people.admin)).status_code == 422


def test_cycle_steps_are_linked_to_the_repairs_ticket(
    api: TestClient, people: People, history
) -> None:
    ticket = history["ticket"]
    log = api.get(f"{API}/events", headers=bearer(people.engineer),
                  params={"device_id": str(history["a"].id)}).json()["items"]  # fmt: skip
    linked = {e["event_type"]: (e["complaint"] or {}).get("ticket_no") for e in log}
    assert linked["received_for_repair"] == ticket.ticket_no
    assert linked["diagnosed"] == ticket.ticket_no and linked["repair_started"] == ticket.ticket_no
    assert linked["assigned_to_unit"] is None
