from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models import Device, DeviceEvent
from app.models.enums import ComplaintStatus, DeviceStatus, EventType
from tests.api_helpers import People, bearer
from tests.factories import make_complaint, make_device

DEVICES = "/api/v1/devices"


def events_of(db: Session, device_id) -> list[DeviceEvent]:
    return list(
        db.scalars(
            select(DeviceEvent).where(DeviceEvent.device_id == device_id).order_by(DeviceEvent.id)
        )
    )


def count_devices(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Device)) or 0


# ---------- registration ----------


def test_register_creates_device_and_registration_event(
    api: TestClient, people: People, db: Session
) -> None:
    body = {
        "device_type": "  Laptop   Pro ",
        "serial_number": "SN-1001",
        "make": "Dell",
        "model": "Latitude 5440",
        "acquired_on": "2026-09-15",
    }
    resp = api.post(DEVICES, headers=bearer(people.engineer), json=body)
    assert resp.status_code == 201
    out = resp.json()
    assert out["asset_tag"].startswith("LAS-ENG-") and len(out["asset_tag"]) == 14
    assert out["device_type"] == "laptop pro"  # trimmed, collapsed, lower-cased
    assert out["status"] == "in_stock" and out["unit"] is None
    assert out["acquired_on"] == "2026-09-15"
    assert out["created_by"]["id"] == str(people.engineer.id)
    assert out["open_complaint_count"] == 0

    (event,) = events_of(db, out["id"])
    assert event.event_type is EventType.device_registered
    assert event.from_status is None and event.to_status is DeviceStatus.in_stock
    assert event.actor_id == people.engineer.id
    assert event.unit_id is None
    assert event.occurred_at is not None  # stamped by the database


def test_register_with_only_a_type(api: TestClient, people: People) -> None:
    resp = api.post(DEVICES, headers=bearer(people.admin), json={"device_type": "UPS"})
    assert resp.status_code == 201
    out = resp.json()
    assert out["device_type"] == "ups"
    assert out["serial_number"] is None and out["make"] is None and out["acquired_on"] is None


@pytest.mark.parametrize(
    "extra",
    [
        {"status": "assigned"},
        {"unit_id": "00000000-0000-0000-0000-000000000001"},
        {"asset_tag": "LAS-ENG-999999"},
        {"occurred_at": "2020-01-01T00:00:00Z"},
        {"created_by": "00000000-0000-0000-0000-000000000001"},
    ],
)
def test_register_rejects_server_controlled_fields(
    api: TestClient, people: People, db: Session, extra: dict
) -> None:
    before = count_devices(db)
    resp = api.post(
        DEVICES, headers=bearer(people.engineer), json={"device_type": "laptop"} | extra
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert count_devices(db) == before


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"device_type": "   "},
        {"device_type": "x" * 51},
        {"device_type": "a", "make": "m" * 101},
    ],
)
def test_register_validation(api: TestClient, people: People, body: dict) -> None:
    assert api.post(DEVICES, headers=bearer(people.engineer), json=body).status_code == 422


def test_blank_serial_is_stored_as_null_and_does_not_collide(
    api: TestClient, people: People
) -> None:
    for _ in range(2):
        resp = api.post(
            DEVICES,
            headers=bearer(people.engineer),
            json={"device_type": "laptop", "serial_number": "   ", "make": ""},
        )
        assert resp.status_code == 201
        assert resp.json()["serial_number"] is None and resp.json()["make"] is None


@pytest.mark.parametrize("duplicate", ["SN-DUP", "sn-dup", " Sn-Dup "])
def test_duplicate_serial_is_409_even_with_different_case(
    api: TestClient, people: People, db: Session, duplicate: str
) -> None:
    headers = bearer(people.engineer)
    assert api.post(DEVICES, headers=headers, json={"device_type": "a", "serial_number": "SN-DUP"})
    devices_before = count_devices(db)
    events_before = db.scalar(select(func.count()).select_from(DeviceEvent))

    resp = api.post(DEVICES, headers=headers, json={"device_type": "a", "serial_number": duplicate})
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "SERIAL_EXISTS")
    assert count_devices(db) == devices_before
    assert db.scalar(select(func.count()).select_from(DeviceEvent)) == events_before


def test_registration_is_atomic(
    api: TestClient, people: People, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("event insert failed")

    monkeypatch.setattr("app.services.devices.append_event", boom)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post(
            DEVICES,
            headers=bearer(people.engineer),
            json={"device_type": "laptop", "serial_number": "SN-ATOMIC"},
        )
    assert resp.status_code == 500
    assert (
        db.scalar(
            select(func.count()).select_from(Device).where(Device.serial_number == "SN-ATOMIC")
        )
        == 0
    )


# ---------- fleet fixture ----------


@pytest.fixture
def fleet(db: Session, people: People) -> dict[str, Device]:
    eng = people.engineer
    devices = {
        "laptop_a": make_device(
            db,
            eng,
            unit_id=people.unit_a.id,
            status=DeviceStatus.assigned,
            device_type="laptop",
            serial_number="SN-A1",
            make="Dell",
        ),
        "printer_a": make_device(
            db,
            eng,
            unit_id=people.unit_a.id,
            status=DeviceStatus.in_repair,
            device_type="printer",
            serial_number="SN-A2",
        ),
        "laptop_b": make_device(
            db,
            eng,
            unit_id=people.unit_b.id,
            status=DeviceStatus.assigned,
            device_type="laptop",
            serial_number="SN-B1",
        ),
        "stock": make_device(
            db, eng, status=DeviceStatus.in_stock, device_type="laptop", serial_number="SN-C1"
        ),
        "old_a": make_device(
            db,
            eng,
            unit_id=people.unit_a.id,
            status=DeviceStatus.decommissioned,
            device_type="monitor",
        ),
    }
    db.commit()
    return devices


def tags(resp) -> list[str]:
    return [d["asset_tag"] for d in resp.json()["items"]]


def expected(fleet: dict[str, Device], *names: str) -> list[str]:
    return sorted(fleet[n].asset_tag for n in names)


# ---------- list / search ----------


@pytest.mark.parametrize("role", ["admin", "engineer", "auditor"])
def test_staff_see_every_device(api: TestClient, people: People, fleet, role: str) -> None:
    resp = api.get(DEVICES, headers=bearer(people.by_role()[role]))
    assert resp.status_code == 200
    assert resp.json()["total"] == 5
    assert tags(resp) == expected(fleet, "laptop_a", "printer_a", "laptop_b", "stock", "old_a")


def test_list_item_shape(api: TestClient, people: People, fleet) -> None:
    item = api.get(DEVICES, headers=bearer(people.admin), params={"q": "SN-A1"}).json()["items"][0]
    assert set(item) == {
        "id", "asset_tag", "serial_number", "device_type", "make", "model", "status",
        "acquired_on", "unit", "created_at",
    }  # fmt: skip
    assert item["unit"] == {
        "id": str(people.unit_a.id), "name": "Unit A", "code": "A"
    }  # fmt: skip


def test_list_filters(api: TestClient, people: People, fleet) -> None:
    admin = bearer(people.admin)

    def get(**params):
        return tags(api.get(DEVICES, headers=admin, params=params))

    assert get(unit_id=str(people.unit_a.id)) == expected(fleet, "laptop_a", "printer_a", "old_a")
    assert get(status="decommissioned") == expected(fleet, "old_a")
    assert get(status="in_stock") == expected(fleet, "stock")
    assert get(device_type="laptop") == expected(fleet, "laptop_a", "laptop_b", "stock")
    assert get(device_type=" LAPTOP ") == get(device_type="laptop")
    assert get(device_type="laptop", unit_id=str(people.unit_b.id)) == expected(fleet, "laptop_b")
    assert get(device_type="router") == []


def test_search_matches_asset_tag_and_serial_substrings(
    api: TestClient, people: People, fleet
) -> None:
    admin = bearer(people.admin)

    def search(q):
        return tags(api.get(DEVICES, headers=admin, params={"q": q}))

    assert search("sn-a1") == expected(fleet, "laptop_a")  # case-insensitive
    assert search("-B") == expected(fleet, "laptop_b")
    assert search("SN-") == expected(fleet, "laptop_a", "printer_a", "laptop_b", "stock")
    assert search(fleet["stock"].asset_tag) == expected(fleet, "stock")
    assert search(fleet["stock"].asset_tag[-6:]) == expected(fleet, "stock")
    assert search("   ") == search("")  # blank search is no search


@pytest.mark.parametrize("q", ["%", "_", "\\", "SN%1", "S_-A1"])
def test_search_treats_wildcards_literally(api: TestClient, people: People, fleet, q: str) -> None:
    resp = api.get(DEVICES, headers=bearer(people.admin), params={"q": q})
    assert resp.status_code == 200 and resp.json()["total"] == 0


def test_list_pagination(api: TestClient, people: People, fleet) -> None:
    admin = bearer(people.admin)
    page1 = api.get(DEVICES, headers=admin, params={"page": 1, "page_size": 2}).json()
    page3 = api.get(DEVICES, headers=admin, params={"page": 3, "page_size": 2}).json()
    assert (page1["total"], len(page1["items"]), len(page3["items"])) == (5, 2, 1)
    page2 = api.get(DEVICES, headers=admin, params={"page": 2, "page_size": 2}).json()
    everything = [d["asset_tag"] for p in (page1, page2, page3) for d in p["items"]]
    assert everything == sorted(everything) and len(set(everything)) == 5


@pytest.mark.parametrize("params", [{"status": "broken"}, {"unit_id": "nope"}, {"q": "x" * 101}])
def test_list_rejects_bad_filters(api: TestClient, people: People, params: dict) -> None:
    assert api.get(DEVICES, headers=bearer(people.admin), params=params).status_code == 422


# ---------- unit scoping (SPEC 12.1 test 3) ----------


def test_unit_rep_sees_only_their_units_devices(api: TestClient, people: People, fleet) -> None:
    resp = api.get(DEVICES, headers=bearer(people.rep_a))
    assert resp.json()["total"] == 3
    assert tags(resp) == expected(fleet, "laptop_a", "printer_a", "old_a")  # no B, no stock
    resp_b = api.get(DEVICES, headers=bearer(people.rep_b))
    assert tags(resp_b) == expected(fleet, "laptop_b")


def test_unit_rep_cannot_widen_the_list_with_unit_id(
    api: TestClient, people: People, fleet
) -> None:
    resp = api.get(DEVICES, headers=bearer(people.rep_a), params={"unit_id": str(people.unit_b.id)})
    assert tags(resp) == expected(fleet, "laptop_a", "printer_a", "old_a")  # still unit A's own


def test_unit_rep_filters_stay_inside_their_unit(api: TestClient, people: People, fleet) -> None:
    resp = api.get(DEVICES, headers=bearer(people.rep_a), params={"device_type": "laptop"})
    assert tags(resp) == expected(fleet, "laptop_a")
    resp = api.get(DEVICES, headers=bearer(people.rep_a), params={"q": "SN-B1"})
    assert resp.json()["total"] == 0


def test_unit_rep_gets_404_for_other_units_and_stock_devices(
    api: TestClient, people: People, fleet
) -> None:
    rep = bearer(people.rep_a)
    own = api.get(f"{DEVICES}/{fleet['laptop_a'].id}", headers=rep)
    assert own.status_code == 200

    missing = api.get(f"{DEVICES}/00000000-0000-0000-0000-000000000099", headers=rep)
    for key in ("laptop_b", "stock"):
        resp = api.get(f"{DEVICES}/{fleet[key].id}", headers=rep)
        assert resp.status_code == 404
        assert resp.json() == missing.json()  # indistinguishable from "does not exist"
        assert api.get(f"{DEVICES}/{fleet[key].id}/timeline", headers=rep).status_code == 404
        assert api.patch(f"{DEVICES}/{fleet[key].id}", headers=rep, json={}).status_code == 403


# ---------- detail ----------


def test_detail_fields(api: TestClient, people: People, fleet) -> None:
    resp = api.get(f"{DEVICES}/{fleet['laptop_a'].id}", headers=bearer(people.auditor))
    out = resp.json()
    assert resp.status_code == 200
    assert out["asset_tag"] == fleet["laptop_a"].asset_tag
    assert out["serial_number"] == "SN-A1" and out["make"] == "Dell" and out["status"] == "assigned"
    assert out["unit"]["code"] == "A"
    assert out["created_by"] == {
        "id": str(people.engineer.id),
        "full_name": people.engineer.full_name,
    }
    assert out["open_complaint_count"] == 0


def test_stock_device_has_no_unit(api: TestClient, people: People, fleet) -> None:
    out = api.get(f"{DEVICES}/{fleet['stock'].id}", headers=bearer(people.admin)).json()
    assert out["unit"] is None


def test_open_complaint_count_counts_only_unresolved_tickets(
    api: TestClient, people: People, db: Session, fleet
) -> None:
    device = fleet["laptop_a"]
    for status in ComplaintStatus:
        make_complaint(db, people.unit_a, people.rep_a, device=device, status=status)
    make_complaint(db, people.unit_a, people.rep_a, device=fleet["printer_a"])  # other device
    db.commit()
    out = api.get(f"{DEVICES}/{device.id}", headers=bearer(people.admin)).json()
    assert out["open_complaint_count"] == 3  # open, in_progress, reopened


def test_unknown_device_is_404(api: TestClient, people: People) -> None:
    resp = api.get(f"{DEVICES}/00000000-0000-0000-0000-000000000099", headers=bearer(people.admin))
    assert (resp.status_code, resp.json()["error"]["code"]) == (404, "DEVICE_NOT_FOUND")
    assert api.get(f"{DEVICES}/not-a-uuid", headers=bearer(people.admin)).status_code == 422


# ---------- patch ----------


def test_patch_updates_metadata_and_logs_a_note_event(
    api: TestClient, people: People, db: Session, fleet
) -> None:
    device = fleet["laptop_a"]
    resp = api.patch(
        f"{DEVICES}/{device.id}",
        headers=bearer(people.engineer),
        json={"serial_number": "SN-A1-FIXED", "model": "XPS 13", "acquired_on": "2026-01-02"},
    )
    assert resp.status_code == 200
    out = resp.json()
    assert out["serial_number"] == "SN-A1-FIXED" and out["model"] == "XPS 13"
    assert out["acquired_on"] == "2026-01-02" and out["make"] == "Dell"  # untouched
    assert out["status"] == "assigned" and out["unit"]["code"] == "A"

    (event,) = events_of(db, device.id)
    assert event.event_type is EventType.note_added
    assert event.from_status is DeviceStatus.assigned and event.to_status is DeviceStatus.assigned
    assert event.unit_id == people.unit_a.id
    assert event.actor_id == people.engineer.id
    for fragment in ('serial_number "SN-A1" -> "SN-A1-FIXED"', 'model (none) -> "XPS 13"',
                     "acquired_on (none) -> 2026-01-02"):  # fmt: skip
        assert fragment in event.notes


def test_patch_that_changes_nothing_writes_no_event(
    api: TestClient, people: People, db: Session, fleet
) -> None:
    device = fleet["laptop_a"]
    headers = bearer(people.engineer)
    assert api.patch(f"{DEVICES}/{device.id}", headers=headers, json={}).status_code == 200
    same = {"serial_number": "SN-A1", "make": "Dell", "device_type": "Laptop"}
    assert api.patch(f"{DEVICES}/{device.id}", headers=headers, json=same).status_code == 200
    assert events_of(db, device.id) == []


def test_patch_can_clear_optional_fields(
    api: TestClient, people: People, db: Session, fleet
) -> None:
    device = fleet["laptop_a"]
    resp = api.patch(
        f"{DEVICES}/{device.id}",
        headers=bearer(people.admin),
        json={"make": None, "serial_number": ""},
    )
    assert resp.status_code == 200
    assert resp.json()["make"] is None and resp.json()["serial_number"] is None
    (event,) = events_of(db, device.id)
    assert 'make "Dell" -> (none)' in event.notes


@pytest.mark.parametrize(
    "body",
    [
        {"status": "decommissioned"},
        {"unit_id": "00000000-0000-0000-0000-000000000001"},
        {"asset_tag": "LAS-ENG-000001"},
        {"created_by": "00000000-0000-0000-0000-000000000001"},
        {"device_type": None},
        {"device_type": "   "},
    ],
)
def test_patch_rejects_non_metadata_fields(
    api: TestClient, people: People, db: Session, fleet, body: dict
) -> None:
    device = fleet["laptop_a"]
    resp = api.patch(f"{DEVICES}/{device.id}", headers=bearer(people.engineer), json=body)
    assert resp.status_code == 422
    db.refresh(device)
    assert device.status is DeviceStatus.assigned and device.unit_id == people.unit_a.id
    assert events_of(db, device.id) == []


@pytest.mark.parametrize("serial", ["SN-B1", "sn-b1"])
def test_patch_duplicate_serial_is_409_and_changes_nothing(
    api: TestClient, people: People, db: Session, fleet, serial: str
) -> None:
    device = fleet["laptop_a"]
    resp = api.patch(
        f"{DEVICES}/{device.id}",
        headers=bearer(people.engineer),
        json={"serial_number": serial, "model": "should not stick"},
    )
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "SERIAL_EXISTS")
    db.refresh(device)
    assert device.serial_number == "SN-A1" and device.model is None
    assert events_of(db, device.id) == []


def test_patch_may_change_only_the_case_of_its_own_serial(
    api: TestClient, people: People, fleet
) -> None:
    resp = api.patch(
        f"{DEVICES}/{fleet['laptop_a'].id}",
        headers=bearer(people.engineer),
        json={"serial_number": "sn-a1"},
    )
    assert resp.status_code == 200 and resp.json()["serial_number"] == "sn-a1"


def test_decommissioned_devices_can_still_be_corrected(
    api: TestClient, people: People, fleet
) -> None:
    resp = api.patch(
        f"{DEVICES}/{fleet['old_a'].id}", headers=bearer(people.engineer), json={"make": "HP"}
    )
    assert resp.status_code == 200 and resp.json()["status"] == "decommissioned"


def test_patch_unknown_device_is_404(api: TestClient, people: People) -> None:
    resp = api.patch(
        f"{DEVICES}/00000000-0000-0000-0000-000000000099",
        headers=bearer(people.engineer),
        json={"make": "x"},
    )
    assert resp.status_code == 404


# ---------- /units/{id}/devices ----------


def test_unit_devices_for_staff(api: TestClient, people: People, fleet) -> None:
    resp = api.get(f"/api/v1/units/{people.unit_a.id}/devices", headers=bearer(people.auditor))
    assert resp.status_code == 200
    assert tags(resp) == expected(fleet, "laptop_a", "printer_a", "old_a")
    filtered = api.get(
        f"/api/v1/units/{people.unit_a.id}/devices",
        headers=bearer(people.engineer),
        params={"status": "in_repair", "page_size": 1},
    )
    assert tags(filtered) == expected(fleet, "printer_a")
    assert filtered.json()["page_size"] == 1


def test_unit_devices_for_unit_rep_are_limited_to_their_unit(
    api: TestClient, people: People, fleet
) -> None:
    own = api.get(f"/api/v1/units/{people.unit_a.id}/devices", headers=bearer(people.rep_a))
    assert own.status_code == 200 and own.json()["total"] == 3

    other = api.get(f"/api/v1/units/{people.unit_b.id}/devices", headers=bearer(people.rep_a))
    unknown = api.get(
        "/api/v1/units/00000000-0000-0000-0000-000000000099/devices", headers=bearer(people.rep_a)
    )
    assert other.status_code == 404 == unknown.status_code
    assert other.json() == unknown.json()
    assert other.json()["error"]["code"] == "UNIT_NOT_FOUND"


def test_unit_devices_unknown_unit_is_404_for_staff(api: TestClient, people: People) -> None:
    resp = api.get(
        "/api/v1/units/00000000-0000-0000-0000-000000000099/devices", headers=bearer(people.admin)
    )
    assert (resp.status_code, resp.json()["error"]["code"]) == (404, "UNIT_NOT_FOUND")


def test_acquired_on_round_trips_as_a_date(api: TestClient, people: People) -> None:
    resp = api.post(
        DEVICES,
        headers=bearer(people.admin),
        json={"device_type": "laptop", "acquired_on": date(2025, 12, 31).isoformat()},
    )
    assert resp.json()["acquired_on"] == "2025-12-31"


# ---------- allowed_events (what the UI offers an engineer next) ----------


@pytest.mark.parametrize("status", list(DeviceStatus))
def test_detail_lists_the_events_allowed_next(
    api: TestClient, people: People, db: Session, status: DeviceStatus
) -> None:
    from app.services.event_rules import allowed_events

    device = make_device(db, people.engineer, unit_id=people.unit_a.id, status=status)
    db.commit()
    for user in (people.engineer, people.rep_a, people.auditor):
        out = api.get(f"{DEVICES}/{device.id}", headers=bearer(user)).json()
        assert out["allowed_events"] == [e.value for e in allowed_events(status)]


def test_allowed_events_follow_the_device_through_its_life(api: TestClient, people: People) -> None:
    created = api.post(
        DEVICES, headers=bearer(people.engineer), json={"device_type": "laptop"}
    ).json()
    assert created["allowed_events"] == ["assigned_to_unit", "decommissioned", "note_added"]
    api.post(
        f"{DEVICES}/{created['id']}/events", headers=bearer(people.engineer),
        json={"event_type": "assigned_to_unit", "unit_id": str(people.unit_a.id),
              "counterparty_name": "Ada"},
    )  # fmt: skip
    after = api.get(f"{DEVICES}/{created['id']}", headers=bearer(people.engineer)).json()
    assert after["allowed_events"] == ["received_for_repair", "decommissioned", "note_added"]
