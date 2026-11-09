"""Report figures checked against the hand-computed world in tests/report_world.py."""

import pytest
from fastapi.testclient import TestClient

from tests.api_helpers import People, bearer
from tests.report_world import World

API = "/api/v1/reports"


def report(api: TestClient, user, name: str, **params) -> dict:
    resp = api.get(f"{API}/{name}", headers=bearer(user), params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def section(rep: dict, key: str) -> dict:
    (found,) = [s for s in rep["sections"] if s["key"] == key]
    return found


def by(rows: list[dict], key: str) -> dict[str, dict]:
    return {r[key]: r for r in rows}


def summary(rep: dict) -> dict:
    return {s["key"]: s["value"] for s in rep["summary"]}


def pick(row: dict, *keys: str) -> dict:
    return {k: row[k] for k in keys}


# ---------- monthly activity ----------


def test_monthly_activity_by_unit(api: TestClient, people: People, world: World) -> None:
    rep = report(api, people.admin, "monthly-activity", month="2026-10")
    assert (rep["key"], rep["period"], rep["scope"]["label"]) == (
        "monthly-activity", "October 2026", "All units"
    )  # fmt: skip
    assert rep["generated_by"]["id"] == str(people.admin.id)

    table = section(rep, "by_unit")
    rows = by(table["rows"], "unit")
    assert set(rows) == {"Unit A", "Unit B", "Central stock"}
    measures = (
        "assigned", "received", "repaired", "returned", "decommissioned",
        "in_workshop", "avg_days", "tickets_opened", "tickets_closed", "disputes",
    )  # fmt: skip
    assert pick(rows["Unit A"], *measures) == {
        "assigned": 0, "received": 4, "repaired": 3, "returned": 2,
        "decommissioned": 0, "in_workshop": 2, "avg_days": 4.6, "tickets_opened": 5,
        "tickets_closed": 1, "disputes": 1,
    }  # fmt: skip
    assert pick(rows["Unit B"], *measures) == {
        "assigned": 1, "received": 1, "repaired": 0, "returned": 1,
        "decommissioned": 1, "in_workshop": 0, "avg_days": 2.6, "tickets_opened": 2,
        "tickets_closed": 2, "disputes": 1,
    }  # fmt: skip
    assert pick(rows["Central stock"], *measures) == {
        "assigned": 0, "received": 0, "repaired": 0, "returned": 0,
        "decommissioned": 1, "in_workshop": 0, "avg_days": None, "tickets_opened": 0,
        "tickets_closed": 0, "disputes": 0,
    }  # fmt: skip
    assert pick(table["totals"], *measures) == {
        "assigned": 1, "received": 5, "repaired": 3, "returned": 3,
        "decommissioned": 2, "in_workshop": 2, "avg_days": 3.9, "tickets_opened": 7,
        "tickets_closed": 3, "disputes": 2,
    }  # fmt: skip
    # The overall average is over all repairs (3.9), not the average of the unit averages (3.6).
    assert summary(rep) == {
        "received": 5, "returned": 3, "in_workshop": 2, "avg_days": 3.9,
        "tickets_opened": 7, "tickets_closed": 3, "disputes": 2,
    }  # fmt: skip


def test_monthly_activity_devices(api: TestClient, people: People, world: World) -> None:
    rep = report(api, people.engineer, "monthly-activity", month="2026-10")
    rows = section(rep, "by_device")["rows"]
    tags = {name: d.asset_tag for name, d in world.devices.items()}
    assert [r["asset_tag"] for r in rows] == [
        tags[k] for k in ("s1", "a1", "a2", "a3", "b1", "b2")
    ]  # Central stock, then Unit A, then Unit B; B3 had no repair activity
    got = {r["asset_tag"]: pick(r, "received", "repaired", "returned",
                                "status_at_month_end") for r in rows}  # fmt: skip
    assert got[tags["a1"]] == {"received": 2, "repaired": 1, "returned": 1,
                               "status_at_month_end": "received for repair"}  # fmt: skip
    assert got[tags["a2"]] == {"received": 1, "repaired": 1, "returned": 1,
                               "status_at_month_end": "assigned"}  # fmt: skip
    assert got[tags["a3"]] == {"received": 1, "repaired": 1, "returned": 0,
                               "status_at_month_end": "repaired"}  # fmt: skip
    assert got[tags["b1"]]["status_at_month_end"] == "decommissioned"
    assert got[tags["b2"]] == {"received": 0, "repaired": 0, "returned": 1,
                               "status_at_month_end": "assigned"}  # fmt: skip
    assert got[tags["s1"]]["status_at_month_end"] == "decommissioned"


def test_month_boundaries_follow_lagos_time(api: TestClient, people: People, world: World) -> None:
    """A2 was received at 00:30 on 1 Nov in Lagos (23:30 UTC on 31 Oct): November's."""
    nov = report(api, people.admin, "monthly-activity", month="2026-11")
    rows = by(section(nov, "by_unit")["rows"], "unit")
    assert pick(rows["Unit A"], "received", "returned", "avg_days", "in_workshop") == {
        "received": 1, "returned": 1, "avg_days": 8.0, "in_workshop": 2
    }  # fmt: skip
    assert rows["Unit B"]["assigned"] == 1 and rows["Unit B"]["in_workshop"] == 0
    assert (rows["Unit A"]["tickets_opened"], rows["Unit B"]["tickets_opened"]) == (1, 2)
    assert section(nov, "by_unit")["totals"]["tickets_closed"] == 0


def test_the_return_just_after_midnight_belongs_to_october(
    api: TestClient, people: People, world: World
) -> None:
    """B2 came back at 00:15 on 1 Oct Lagos time, which is still 30 Sep in UTC."""
    sep = report(api, people.admin, "monthly-activity", month="2026-09")
    oct_ = report(api, people.admin, "monthly-activity", month="2026-10")
    assert by(section(sep, "by_unit")["rows"], "unit")["Unit B"]["returned"] == 0
    assert by(section(oct_, "by_unit")["rows"], "unit")["Unit B"]["returned"] == 1


def test_a_month_without_activity_lists_every_unit_with_zeros(
    api: TestClient, people: People, world: World
) -> None:
    rep = report(api, people.admin, "monthly-activity", month="2025-01")
    rows = section(rep, "by_unit")["rows"]
    assert {r["unit"] for r in rows} == {"Unit A", "Unit B"}
    assert all(r["received"] == 0 and r["avg_days"] is None for r in rows)
    assert section(rep, "by_device")["rows"] == []
    assert summary(rep)["avg_days"] is None


@pytest.mark.parametrize("month", ["2026-13", "2026-00", "202610", "2026-1", "abc", "1999-12", ""])
def test_monthly_activity_rejects_a_bad_month(api: TestClient, people: People, month: str) -> None:
    resp = api.get(f"{API}/monthly-activity", headers=bearer(people.admin), params={"month": month})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] in ("INVALID_MONTH", "VALIDATION_ERROR")


# ---------- open tickets ----------


def test_open_tickets(api: TestClient, people: People, world: World) -> None:
    rep = report(api, people.admin, "open-tickets")
    assert rep["period"] == "As at 10 Nov 2026 12:00 (Lagos time)"

    pr = section(rep, "by_priority")
    rows = by(pr["rows"], "unit")
    assert pick(rows["Unit A"], "critical", "high", "medium", "low", "total") == {
        "critical": 1, "high": 1, "medium": 1, "low": 0, "total": 3
    }  # fmt: skip
    assert pick(rows["Unit B"], "critical", "high", "medium", "low", "total") == {
        "critical": 0, "high": 0, "medium": 1, "low": 1, "total": 2
    }  # fmt: skip
    assert pick(pr["totals"], "critical", "high", "medium", "low", "total") == {
        "critical": 1, "high": 1, "medium": 2, "low": 1, "total": 5
    }  # fmt: skip

    ages = section(rep, "by_age")
    rows = by(ages["rows"], "unit")
    assert pick(rows["Unit A"], "d0_2", "d3_7", "d8_14", "d15_plus", "total", "oldest_days") == {
        "d0_2": 0, "d3_7": 1, "d8_14": 0, "d15_plus": 2, "total": 3, "oldest_days": 36
    }  # fmt: skip
    assert pick(rows["Unit B"], "d0_2", "d3_7", "d8_14", "d15_plus", "total", "oldest_days") == {
        "d0_2": 1, "d3_7": 0, "d8_14": 1, "d15_plus": 0, "total": 2, "oldest_days": 11
    }  # fmt: skip
    assert ages["totals"]["oldest_days"] == 36

    status = by(section(rep, "by_status")["rows"], "unit")
    assert pick(status["Unit A"], "open", "in_progress", "reopened") == {
        "open": 1, "in_progress": 1, "reopened": 1
    }  # fmt: skip
    assert pick(status["Unit B"], "open", "in_progress", "reopened") == {
        "open": 1, "in_progress": 1, "reopened": 0
    }  # fmt: skip

    listed = section(rep, "tickets")["rows"]
    assert [r["ticket_no"] for r in listed] == [
        world.tickets[k].ticket_no for k in ("t3", "t2", "t8", "t7", "t6")
    ]  # oldest first
    first = listed[0]
    assert (first["unit"], first["priority"], first["status"], first["age_days"]) == (
        "Unit A", "medium", "reopened", 36
    )  # fmt: skip
    assert first["device"] == world.devices["a2"].asset_tag and first["raised_on"] == "2026-10-05"
    assert listed[1]["assigned_to"] == people.engineer.full_name

    assert summary(rep) == {
        "open": 5, "reopened": 1, "urgent": 2, "awaiting_unit": 3, "oldest_days": 36
    }  # fmt: skip


def test_open_tickets_lists_what_waits_on_the_unit(
    api: TestClient, people: People, world: World
) -> None:
    rows = section(report(api, people.admin, "open-tickets"), "awaiting_unit")["rows"]
    assert [(r["ticket_no"], r["days_waiting"], r["waiting_for"], r["overdue"]) for r in rows] == [
        (world.tickets["t9"].ticket_no, 9, "Unit confirmation", "Yes"),
        (world.tickets["t11"].ticket_no, 8, "Device acknowledgement", "Yes"),
        (world.tickets["t10"].ticket_no, 1, "Unit confirmation", "No"),
    ]  # fmt: skip


# ---------- turnaround ----------


def test_turnaround_for_october(api: TestClient, people: People, world: World) -> None:
    rep = report(api, people.admin, "turnaround", **{"from": "2026-10-01", "to": "2026-10-31"})
    assert rep["period"] == "01 Oct 2026 to 31 Oct 2026"
    assert summary(rep) == {
        "repairs": 3, "avg_days": 3.9, "median_days": 2.6, "shortest_days": 2.0, "longest_days": 7.1
    }  # fmt: skip
    stat = ("repairs", "avg_days", "median_days", "shortest_days", "longest_days")
    units = section(rep, "by_unit")
    rows = by(units["rows"], "unit")
    assert pick(rows["Unit A"], *stat) == {
        "repairs": 2, "avg_days": 4.6, "median_days": 4.6, "shortest_days": 2.0, "longest_days": 7.1
    }  # fmt: skip
    assert pick(rows["Unit B"], *stat) == {
        "repairs": 1, "avg_days": 2.6, "median_days": 2.6, "shortest_days": 2.6, "longest_days": 2.6
    }  # fmt: skip
    assert units["totals"]["repairs"] == 3 and units["totals"]["avg_days"] == 3.9

    repairs = section(rep, "repairs")["rows"]
    tags = {k: d.asset_tag for k, d in world.devices.items()}
    assert [r["asset_tag"] for r in repairs] == [tags["b2"], tags["a2"], tags["a1"]]  # by return
    a1 = repairs[2]
    assert (a1["days"], a1["unit"]) == (7.1, "Unit A")
    assert "vendors" not in a1
    assert (a1["received_at"], a1["returned_at"]) == (
        "2026-10-03T09:00+01:00", "2026-10-10T12:00+01:00"
    )  # fmt: skip
    assert a1["ticket_no"] == world.tickets["t1"].ticket_no
    assert repairs[0]["received_at"] == "2026-09-28T10:00+01:00"  # received in September


def test_turnaround_period_edges_use_lagos_days(
    api: TestClient, people: People, world: World
) -> None:
    def returned(**params):
        rep = report(api, people.admin, "turnaround", **params)
        return summary(rep)["repairs"]

    assert returned(**{"from": "2026-10-01", "to": "2026-10-01"}) == 1  # B2 at 00:15 on the 1st
    assert returned(**{"from": "2026-10-02", "to": "2026-10-31"}) == 2
    assert returned(**{"from": "2026-09-01", "to": "2026-09-30"}) == 0
    assert returned(**{"from": "2026-10-08", "to": "2026-10-08"}) == 1  # A2 returned that day


def test_turnaround_defaults_to_the_last_90_days(
    api: TestClient, people: People, world: World
) -> None:
    rep = report(api, people.admin, "turnaround")
    assert rep["period"] == "13 Aug 2026 to 10 Nov 2026"
    assert summary(rep)["repairs"] == 4  # the three from October plus A3 on 2 Nov
    a3 = [
        r
        for r in section(rep, "repairs")["rows"]
        if r["asset_tag"] == world.devices["a3"].asset_tag
    ]
    assert a3[0]["days"] == 8.0


def test_a_period_with_no_repairs(api: TestClient, people: People, world: World) -> None:
    rep = report(api, people.admin, "turnaround", **{"from": "2025-01-01", "to": "2025-01-31"})
    assert summary(rep) == {
        "repairs": 0, "avg_days": None, "median_days": None, "shortest_days": None,
        "longest_days": None,
    }  # fmt: skip
    assert section(rep, "repairs")["rows"] == []


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"from": "2026-11-02", "to": "2026-11-01"}, "INVALID_RANGE"),
        ({"from": "2010-01-01", "to": "2026-01-01"}, "RANGE_TOO_LARGE"),
        ({"from": "yesterday"}, "VALIDATION_ERROR"),
    ],
)
def test_range_validation(api: TestClient, people: People, params: dict, code: str) -> None:
    for name in ("turnaround", "repeat-faults"):
        resp = api.get(f"{API}/{name}", headers=bearer(people.admin), params=params)
        assert (resp.status_code, resp.json()["error"]["code"]) == (422, code)


# ---------- repeat faults ----------


def test_repeat_faults(api: TestClient, people: People, world: World) -> None:
    window = {"from": "2026-10-01", "to": "2026-10-31"}
    rep = report(api, people.admin, "repeat-faults", min=2, **window)
    (a1,) = section(rep, "devices")["rows"]
    assert (a1["asset_tag"], a1["repairs"], a1["tickets"]) == (world.devices["a1"].asset_tag, 2, 2)
    assert (a1["first_received"], a1["last_received"]) == ("2026-10-03", "2026-10-20")
    assert (a1["unit"], a1["status"]) == ("Unit A", "received for repair")
    assert "vendors" not in a1
    assert summary(rep) == {"devices": 1, "repairs": 2, "min": 2}

    assert section(report(api, people.admin, "repeat-faults", **window), "devices")["rows"] == []
    assert summary(report(api, people.admin, "repeat-faults", **window))["min"] == 3  # the default


def test_repeat_faults_over_a_longer_period(api: TestClient, people: People, world: World) -> None:
    rep = report(api, people.admin, "repeat-faults", min=2,
                 **{"from": "2026-09-01", "to": "2026-11-30"})  # fmt: skip
    rows = section(rep, "devices")["rows"]
    assert [r["asset_tag"] for r in rows] == [
        world.devices["a1"].asset_tag,
        world.devices["a2"].asset_tag,
    ]
    a2 = rows[1]
    assert (a2["repairs"], a2["tickets"], a2["last_received"]) == (2, 1, "2026-11-01")  # Lagos day


@pytest.mark.parametrize("bad", [0, 1, 101, "x"])
def test_repeat_faults_min_validation(api: TestClient, people: People, bad) -> None:
    resp = api.get(f"{API}/repeat-faults", headers=bearer(people.admin), params={"min": bad})
    assert resp.status_code == 422


# ---------- what is waiting on the units ----------


def test_awaiting_unit(api: TestClient, people: People, world: World) -> None:
    rep = report(api, people.admin, "awaiting-unit")
    assert summary(rep) == {
        "overdue_acknowledgements": 3, "pending_acknowledgements": 3,
        "open_disputes": 2, "unconfirmed_tickets": 1,
    }  # fmt: skip

    pending = section(rep, "pending")["rows"]
    assert [(r["event_id"], r["event"], r["days_pending"], r["overdue"]) for r in pending] == [
        (world.events["a1_in2"].id, "received for repair", 21, "Yes"),
        (world.events["a2_in2"].id, "received for repair", 9, "Yes"),
        (world.events["a3_ret"].id, "returned to unit", 8, "Yes"),
    ]  # fmt: skip
    assert (
        pending[0]["unit"] == "Unit A" and pending[0]["ticket_no"] == world.tickets["t2"].ticket_no
    )
    assert pending[1]["since"] == "2026-11-01T00:30+01:00"

    disputes = section(rep, "disputes")["rows"]
    assert [(r["event_id"], r["unit"], r["days_open"], r["comment"]) for r in disputes] == [
        (world.events["b1_assign"].id, "Unit B", 39, "Wrong model"),
        (world.events["a2_ret1"].id, "Unit A", 32, "Still jams"),
    ]  # fmt: skip
    # B2's disputed intake was answered by a correcting note, so it is not listed.
    assert world.events["b2_in"].id not in [r["event_id"] for r in disputes]
    assert disputes[1]["ticket_no"] == world.tickets["t3"].ticket_no

    (unconfirmed,) = section(rep, "unconfirmed")["rows"]
    assert (unconfirmed["ticket_no"], unconfirmed["days_waiting"]) == (
        world.tickets["t9"].ticket_no,
        9,
    )
    # T11 is not repeated: its returned device is already in the first table.


def test_awaiting_unit_can_include_what_is_not_overdue_yet(
    api: TestClient, people: People, world: World
) -> None:
    rep = report(api, people.admin, "awaiting-unit", include_recent=True)
    pending = section(rep, "pending")["rows"]
    assert len(pending) == 4 and pending[-1]["event"] == "assigned to unit"
    assert (pending[-1]["overdue"], pending[-1]["days_pending"]) == ("No", 1)
    assert summary(rep)["overdue_acknowledgements"] == 3  # still only the overdue ones
    assert [r["ticket_no"] for r in section(rep, "unconfirmed")["rows"]] == [
        world.tickets["t9"].ticket_no, world.tickets["t10"].ticket_no
    ]  # fmt: skip


def test_a_dispute_stops_being_listed_once_answered(
    api: TestClient, people: People, db, world: World
) -> None:
    from app.models.enums import DeviceStatus, EventType
    from tests.factories import make_event

    b1 = world.devices["b1"]
    make_event(db, b1, people.engineer, event_type=EventType.note_added,
               to_status=DeviceStatus.decommissioned, notes="Model confirmed",
               corrects_event_id=world.events["b1_assign"].id)  # fmt: skip
    world.tickets["t3"].status = world.tickets["t3"].status.__class__.in_progress
    db.commit()
    rep = report(api, people.admin, "awaiting-unit")
    assert section(rep, "disputes")["rows"] == []
    assert summary(rep)["open_disputes"] == 0


# ---------- repairs are in-house: no report mentions vendors ----------

ALL_REPORTS = (
    ("monthly-activity", {"month": "2026-10"}),
    ("open-tickets", {}),
    ("turnaround", {"from": "2026-10-01", "to": "2026-10-31"}),
    ("repeat-faults", {"from": "2026-10-01", "to": "2026-10-31", "min": 2}),
    ("awaiting-unit", {}),
)


@pytest.mark.parametrize(("name", "params"), ALL_REPORTS)
def test_no_report_mentions_vendors(
    api: TestClient, people: People, world: World, name: str, params: dict
) -> None:
    import json

    assert "vendor" not in json.dumps(report(api, people.admin, name, **params)).lower()
