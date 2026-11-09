from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models import Device
from app.models.enums import AckStatus, ComplaintStatus, DeviceStatus, EventType
from tests.api_helpers import People, bearer
from tests.factories import (
    make_ack,
    make_complaint,
    make_device,
    make_event,
)

DEVICES = "/api/v1/devices"
NOW = datetime.now(UTC)


def ago(**kw) -> datetime:
    return NOW - timedelta(**kw)


@pytest.fixture
def repaired(db: Session, people: People) -> Device:
    """A laptop that went through a full repair cycle and then a second intake.

    Inserted deliberately out of chronological order (the correction note is added last but
    happened earlier) to prove the timeline sorts by time, not by id.
    """
    eng, rep = people.engineer, people.rep_a
    device = make_device(
        db, eng, unit_id=people.unit_a.id, status=DeviceStatus.received_for_repair,
        serial_number="SN-TL-1",
    )  # fmt: skip
    ticket = make_complaint(db, people.unit_a, rep, device=device, status=ComplaintStatus.reopened)

    def add(event_type, to_status, when, **kw):
        kw.setdefault("unit_id", people.unit_a.id)
        return make_event(
            db, device, eng, event_type=event_type, to_status=to_status, occurred_at=when, **kw
        )

    registered = add(EventType.device_registered, DeviceStatus.in_stock, ago(days=30), unit_id=None)
    assigned = add(
        EventType.assigned_to_unit, DeviceStatus.assigned, ago(days=29),
        from_status=DeviceStatus.in_stock, counterparty_name="Ada Obi",
        counterparty_user_id=rep.id,
    )  # fmt: skip
    make_ack(db, assigned, rep, AckStatus.confirmed, acknowledged_at=ago(days=28))
    intake = add(
        EventType.received_for_repair, DeviceStatus.received_for_repair, ago(days=10),
        from_status=DeviceStatus.assigned, counterparty_name="Ada Obi", complaint_id=ticket.id,
    )  # fmt: skip
    add(EventType.diagnosed, DeviceStatus.diagnosed, ago(days=9),
        from_status=DeviceStatus.received_for_repair, diagnosis="Dead battery")  # fmt: skip
    add(EventType.repair_started, DeviceStatus.in_repair, ago(days=8),
        from_status=DeviceStatus.diagnosed)  # fmt: skip
    add(EventType.repair_completed, DeviceStatus.repaired, ago(days=2),
        from_status=DeviceStatus.in_repair, notes="Battery replaced")  # fmt: skip
    returned = add(
        EventType.returned_to_unit, DeviceStatus.assigned, ago(days=1),
        from_status=DeviceStatus.repaired, counterparty_name="Ada Obi",
    )  # fmt: skip
    make_ack(db, returned, rep, AckStatus.disputed, comment="Still will not boot")
    add(EventType.received_for_repair, DeviceStatus.received_for_repair, ago(hours=12),
        from_status=DeviceStatus.assigned, counterparty_name="Ada Obi")  # fmt: skip
    add(EventType.note_added, DeviceStatus.assigned, ago(days=20),
        from_status=DeviceStatus.assigned, notes="Serial was mistyped",
        corrects_event_id=registered.id)  # fmt: skip
    assert intake.id  # created
    db.commit()
    return device


def get_timeline(api: TestClient, user, device: Device, **params):
    return api.get(f"{DEVICES}/{device.id}/timeline", headers=bearer(user), params=params)


def test_events_are_in_chronological_order(api: TestClient, people: People, repaired) -> None:
    resp = get_timeline(api, people.auditor, repaired)
    assert resp.status_code == 200
    kinds = [e["event_type"] for e in resp.json()["events"]]
    assert kinds == [
        "device_registered", "assigned_to_unit", "note_added", "received_for_repair",
        "diagnosed", "repair_started", "repair_completed", "returned_to_unit",
        "received_for_repair",
    ]  # fmt: skip
    times = [e["occurred_at"] for e in resp.json()["events"]]
    assert times == sorted(times)


def test_timeline_header_describes_the_device(api: TestClient, people: People, repaired) -> None:
    body = get_timeline(api, people.engineer, repaired).json()
    assert body["device"]["asset_tag"] == repaired.asset_tag
    assert body["device"]["unit"]["code"] == "A"
    assert body["device"]["status"] == "received_for_repair"


def test_event_details_include_who_what_and_where(
    api: TestClient, people: People, repaired
) -> None:
    events = {
        (e["event_type"], e["occurred_at"]): e
        for e in get_timeline(api, people.engineer, repaired).json()["events"]
    }
    by_type = {}
    for (kind, _), e in events.items():
        by_type.setdefault(kind, []).append(e)

    registered = by_type["device_registered"][0]
    assert registered["unit"] is None and registered["from_status"] is None
    assert registered["to_status"] == "in_stock"
    assert registered["actor"] == {
        "id": str(people.engineer.id), "full_name": people.engineer.full_name
    }  # fmt: skip

    assigned = by_type["assigned_to_unit"][0]
    assert assigned["unit"]["name"] == "Unit A"
    assert assigned["counterparty_name"] == "Ada Obi"
    assert assigned["counterparty_user"]["id"] == str(people.rep_a.id)

    intake = by_type["received_for_repair"][0]
    assert intake["complaint"]["ticket_no"].startswith("TKT-")

    assert by_type["diagnosed"][0]["diagnosis"] == "Dead battery"
    assert all("vendor" not in e for events in by_type.values() for e in events)
    assert by_type["repair_completed"][0]["notes"] == "Battery replaced"
    note = by_type["note_added"][0]
    assert note["notes"] == "Serial was mistyped" and note["corrects_event_id"] == registered["id"]


def test_acknowledgement_states(api: TestClient, people: People, repaired) -> None:
    events = get_timeline(api, people.engineer, repaired).json()["events"]
    state = lambda i: (events[i]["ack_state"], events[i]["overdue"], events[i]["pending_days"])  # noqa: E731

    assert state(0) == ("not_required", False, None)  # device_registered
    assert state(1)[0] == "confirmed"  # assigned_to_unit
    ack = events[1]["acknowledgement"]
    assert ack["status"] == "confirmed" and ack["acknowledged_by"]["id"] == str(people.rep_a.id)

    assert state(3) == ("pending", True, 10)  # intake 10 days ago, ACK_OVERDUE_DAYS = 3
    assert events[3]["acknowledgement"] is None
    assert state(4) == ("not_required", False, None)  # diagnosed

    assert events[7]["ack_state"] == "disputed"  # returned_to_unit
    assert events[7]["acknowledgement"]["comment"] == "Still will not boot"
    assert events[7]["overdue"] is False

    assert state(8) == ("pending", False, 0)  # second intake, 12 hours old


def test_date_filters_use_lagos_calendar_days(db: Session, api: TestClient, people: People) -> None:
    device = make_device(db, people.engineer)
    moments = {
        "late_oct31_lagos": datetime(2026, 10, 31, 22, 30, tzinfo=UTC),  # 23:30 Lagos, Oct 31
        "early_nov1_lagos": datetime(2026, 10, 31, 23, 30, tzinfo=UTC),  # 00:30 Lagos, Nov 1
        "late_nov1_lagos": datetime(2026, 11, 1, 22, 59, tzinfo=UTC),  # 23:59 Lagos, Nov 1
        "early_nov2_lagos": datetime(2026, 11, 1, 23, 0, tzinfo=UTC),  # 00:00 Lagos, Nov 2
    }
    ids = {
        name: make_event(db, device, people.engineer, occurred_at=when).id
        for name, when in moments.items()
    }
    db.commit()

    def ids_for(**params):
        events = get_timeline(api, people.admin, device, **params).json()["events"]
        return [e["id"] for e in events]

    nov1 = ids_for(date_from="2026-11-01", date_to="2026-11-01")
    assert nov1 == [ids["early_nov1_lagos"], ids["late_nov1_lagos"]]
    assert ids_for(date_to="2026-10-31") == [ids["late_oct31_lagos"]]
    assert ids_for(date_from="2026-11-02") == [ids["early_nov2_lagos"]]
    assert len(ids_for()) == 4


@pytest.mark.parametrize(
    "params", [{"date_from": "2026-11-02", "date_to": "2026-11-01"}, {"date_from": "yesterday"}]
)
def test_bad_date_filters_are_422(api: TestClient, people: People, repaired, params: dict) -> None:
    resp = get_timeline(api, people.admin, repaired, **params)
    assert resp.status_code == 422


def test_timeline_scoping(api: TestClient, people: People, repaired, db: Session) -> None:
    for user in (people.admin, people.engineer, people.auditor, people.rep_a):
        assert get_timeline(api, user, repaired).status_code == 200
    # A unit rep sees the whole history of a device that is in their unit, including the
    # registration from before it was assigned.
    events = get_timeline(api, people.rep_a, repaired).json()["events"]
    assert events[0]["event_type"] == "device_registered"

    other = get_timeline(api, people.rep_b, repaired)
    missing = api.get(
        f"{DEVICES}/00000000-0000-0000-0000-000000000099/timeline", headers=bearer(people.rep_b)
    )
    assert other.status_code == 404 and other.json() == missing.json()


def test_unknown_device_timeline_is_404(api: TestClient, people: People) -> None:
    resp = api.get(
        f"{DEVICES}/00000000-0000-0000-0000-000000000099/timeline", headers=bearer(people.admin)
    )
    assert (resp.status_code, resp.json()["error"]["code"]) == (404, "DEVICE_NOT_FOUND")


def test_empty_timeline(api: TestClient, people: People, db: Session) -> None:
    device = make_device(db, people.engineer)
    db.commit()
    assert get_timeline(api, people.admin, device).json()["events"] == []


def test_query_count_does_not_grow_with_the_number_of_events(
    api: TestClient, people: People, db: Session
) -> None:
    def build(n_events: int) -> Device:
        device = make_device(db, people.engineer, unit_id=people.unit_a.id)
        for i in range(n_events):
            e = make_event(
                db, device, people.engineer, event_type=EventType.received_for_repair,
                to_status=DeviceStatus.received_for_repair, counterparty_name="Ada",
                counterparty_user_id=people.rep_a.id, unit_id=people.unit_a.id,
                occurred_at=ago(hours=i + 1),
            )  # fmt: skip
            if i % 2:
                make_ack(db, e, people.rep_a)
        db.commit()
        return device

    engine = db.get_bind().engine
    counted: list[str] = []

    def count(conn, cursor, statement, *args):
        counted.append(statement)

    def queries_for(device: Device) -> int:
        counted.clear()
        event.listen(engine, "before_cursor_execute", count)
        try:
            assert get_timeline(api, people.engineer, device).status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", count)
        return len(counted)

    small, large = build(2), build(25)
    # The first request after a commit also opens the test session's savepoint; warm that up.
    assert len(get_timeline(api, people.engineer, large).json()["events"]) == 25
    assert len(get_timeline(api, people.engineer, small).json()["events"]) == 2
    assert queries_for(small) == queries_for(large)
    assert queries_for(large) <= 8
