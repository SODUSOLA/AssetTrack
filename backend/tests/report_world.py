"""A small, fully worked repair history with numbers computed by hand.

Times are written in Africa/Lagos wall-clock time (UTC+1) because that is how the reports
read them. "Now" for snapshot reports is frozen at 10 Nov 2026 12:00 Lagos.

Units A and B come from the `people` fixture. Month under test: October 2026.

  A1 laptop   A  assigned 28 Sep (ack) | intake 3 Oct (T1) -> diagnosed -> repair started 5 Oct
              -> completed 9 Oct -> returned 10 Oct 12:00 (7.125 days, ack ok) | intake 20 Oct (T2)
  A2 printer  A  intake 6 Oct (T3) -> diagnosed -> completed 7 Oct -> returned 8 Oct 09:00
              (2.0 days, DISPUTED, ticket T3 reopened) | intake 1 Nov 00:30 (pending)
  A3 monitor  A  intake 25 Oct (T11, ack) -> completed 30 Oct -> returned 2 Nov (pending ack)
  B1 laptop   B  assigned 1 Oct (DISPUTED, no note) | intake 12 Oct (T4, ack) -> diagnosed
              -> repair started 14 Oct -> decommissioned 15 Oct
  B2 monitor  B  intake 28 Sep (T5, DISPUTED then answered by a note) -> returned 1 Oct 00:15
              (2.59375 days, ack ok)
  B3 printer  B  assigned 9 Nov (pending, not overdue)
  S1 UPS      -  decommissioned in stock 10 Oct
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core.timeutil import APP_TIMEZONE
from app.models import Device, DeviceEvent
from app.models.enums import (
    AckStatus,
    ComplaintStatus,
    DeviceStatus,
    EventType,
    PriorityLevel,
)
from tests.api_helpers import People
from tests.factories import make_ack, make_complaint, make_device, make_event

S, E, C = DeviceStatus, EventType, ComplaintStatus


def at(month: int, day: int, hour: int = 9, minute: int = 0, year: int = 2026) -> datetime:
    """Lagos wall-clock time as an aware UTC datetime."""
    return datetime(year, month, day, hour, minute, tzinfo=APP_TIMEZONE).astimezone(UTC)


NOW = at(11, 10, 12, 0)  # snapshot reports are frozen here


@dataclass
class World:
    people: People
    devices: dict[str, Device] = field(default_factory=dict)
    tickets: dict[str, Any] = field(default_factory=dict)
    events: dict[str, DeviceEvent] = field(default_factory=dict)


def build_world(db: Session, people: People) -> World:
    w = World(people)
    eng, rep_a, rep_b = people.engineer, people.rep_a, people.rep_b
    unit_a, unit_b = people.unit_a, people.unit_b

    def device(name, unit, status, device_type):
        d = make_device(db, eng, unit_id=unit.id if unit else None, status=status,
                        device_type=device_type)  # fmt: skip
        w.devices[name] = d
        return d

    def ev(key, dev, event_type, when, to_status, unit, **kw):
        if event_type in (E.assigned_to_unit, E.received_for_repair, E.returned_to_unit):
            kw.setdefault("counterparty_name", "Ada")
        if event_type is E.diagnosed:
            kw.setdefault("diagnosis", "Fault found")
        w.events[key] = make_event(
            db, dev, eng, event_type=event_type, to_status=to_status, occurred_at=when,
            unit_id=unit.id if unit else None, **kw,
        )  # fmt: skip
        return w.events[key]

    def ticket(key, unit, rep, dev, status, created, **kw):
        w.tickets[key] = make_complaint(
            db, unit, rep, device=dev, status=status, created_at=created, **kw
        )
        return w.tickets[key]

    a1 = device("a1", unit_a, S.received_for_repair, "laptop")
    a2 = device("a2", unit_a, S.assigned, "printer")
    a3 = device("a3", unit_a, S.assigned, "monitor")
    b1 = device("b1", unit_b, S.decommissioned, "laptop")
    b2 = device("b2", unit_b, S.assigned, "monitor")
    b3 = device("b3", unit_b, S.assigned, "printer")
    s1 = device("s1", None, S.decommissioned, "ups")

    # --- tickets
    t1 = ticket("t1", unit_a, rep_a, a1, C.closed, at(10, 2, 9), closed_at=at(10, 12, 10),
                resolved_at=at(10, 11, 9))  # fmt: skip
    t2 = ticket("t2", unit_a, rep_a, a1, C.in_progress, at(10, 20, 8), priority=PriorityLevel.high,
                assigned_to=eng.id)  # fmt: skip
    t3 = ticket("t3", unit_a, rep_a, a2, C.reopened, at(10, 5, 8))
    t4 = ticket("t4", unit_b, rep_b, b1, C.closed, at(10, 11, 9), closed_at=at(10, 16, 9))
    t5 = ticket("t5", unit_b, rep_b, b2, C.closed, at(9, 25, 9), closed_at=at(10, 2, 10))
    ticket("t6", unit_b, rep_b, None, C.open, at(11, 8, 9), priority=PriorityLevel.low)
    ticket("t7", unit_a, rep_a, None, C.open, at(11, 5, 9), priority=PriorityLevel.critical)
    ticket("t8", unit_b, rep_b, None, C.in_progress, at(10, 30, 9), assigned_to=eng.id)
    ticket("t9", unit_a, rep_a, None, C.resolved, at(10, 28, 8), resolved_at=at(11, 1, 10))
    ticket("t10", unit_b, rep_b, None, C.resolved, at(11, 6, 9), resolved_at=at(11, 9, 9))
    t11 = ticket("t11", unit_a, rep_a, a3, C.resolved, at(10, 24, 8), resolved_at=at(11, 2, 9))

    # --- A1
    ack = lambda key, by, status=AckStatus.confirmed, when=None, **kw: make_ack(  # noqa: E731
        db, w.events[key], by, status, acknowledged_at=when, **kw
    )
    ev("a1_assign", a1, E.assigned_to_unit, at(9, 28, 10), S.assigned, unit_a)
    ack("a1_assign", rep_a, when=at(9, 29, 9))
    ev("a1_in1", a1, E.received_for_repair, at(10, 3, 9), S.received_for_repair, unit_a,
       complaint_id=t1.id)  # fmt: skip
    ack("a1_in1", rep_a, when=at(10, 3, 10))
    ev("a1_diag", a1, E.diagnosed, at(10, 4, 11), S.diagnosed, unit_a, complaint_id=t1.id)
    ev("a1_start", a1, E.repair_started, at(10, 5, 10), S.in_repair, unit_a, complaint_id=t1.id)
    ev("a1_done", a1, E.repair_completed, at(10, 9, 15), S.repaired, unit_a, complaint_id=t1.id)
    ev("a1_ret1", a1, E.returned_to_unit, at(10, 10, 12), S.assigned, unit_a, complaint_id=t1.id)
    ack("a1_ret1", rep_a, when=at(10, 11, 9))
    ev("a1_in2", a1, E.received_for_repair, at(10, 20, 9), S.received_for_repair, unit_a,
       complaint_id=t2.id)  # fmt: skip

    # --- A2
    ev("a2_in1", a2, E.received_for_repair, at(10, 6, 9), S.received_for_repair, unit_a,
       complaint_id=t3.id)  # fmt: skip
    ack("a2_in1", rep_a, when=at(10, 6, 10))
    ev("a2_diag", a2, E.diagnosed, at(10, 6, 14), S.diagnosed, unit_a, complaint_id=t3.id)
    ev("a2_done", a2, E.repair_completed, at(10, 7, 16), S.repaired, unit_a, complaint_id=t3.id)
    ev("a2_ret1", a2, E.returned_to_unit, at(10, 8, 9), S.assigned, unit_a, complaint_id=t3.id)
    ack("a2_ret1", rep_a, AckStatus.disputed, at(10, 9, 10), comment="Still jams")
    ev("a2_in2", a2, E.received_for_repair, at(11, 1, 0, 30), S.received_for_repair, unit_a,
       complaint_id=t3.id)  # fmt: skip

    # --- A3
    ev("a3_in", a3, E.received_for_repair, at(10, 25, 9), S.received_for_repair, unit_a,
       complaint_id=t11.id)  # fmt: skip
    ack("a3_in", rep_a, when=at(10, 26, 9))
    ev("a3_done", a3, E.repair_completed, at(10, 30, 9), S.repaired, unit_a, complaint_id=t11.id)
    ev("a3_ret", a3, E.returned_to_unit, at(11, 2, 9), S.assigned, unit_a, complaint_id=t11.id)

    # --- B1
    ev("b1_assign", b1, E.assigned_to_unit, at(10, 1, 9), S.assigned, unit_b)
    ack("b1_assign", rep_b, AckStatus.disputed, at(10, 2, 9), comment="Wrong model")
    ev("b1_in", b1, E.received_for_repair, at(10, 12, 10), S.received_for_repair, unit_b,
       complaint_id=t4.id)  # fmt: skip
    ack("b1_in", rep_b, when=at(10, 12, 11))
    ev("b1_diag", b1, E.diagnosed, at(10, 13, 10), S.diagnosed, unit_b, complaint_id=t4.id)
    ev("b1_start", b1, E.repair_started, at(10, 14, 10), S.in_repair, unit_b, complaint_id=t4.id)
    ev("b1_decom", b1, E.decommissioned, at(10, 15, 10), S.decommissioned, unit_b, notes="Dead")

    # --- B2
    ev("b2_in", b2, E.received_for_repair, at(9, 28, 10), S.received_for_repair, unit_b,
       complaint_id=t5.id)  # fmt: skip
    ack("b2_in", rep_b, AckStatus.disputed, at(9, 29, 9), comment="Not our monitor")
    ev("b2_note", b2, E.note_added, at(10, 3, 9), S.assigned, unit_b,
       notes="Checked: it is yours", corrects_event_id=w.events["b2_in"].id)  # fmt: skip
    ev("b2_ret", b2, E.returned_to_unit, at(10, 1, 0, 15), S.assigned, unit_b, complaint_id=t5.id)
    ack("b2_ret", rep_b, when=at(10, 2, 9))

    # --- B3 and S1
    ev("b3_assign", b3, E.assigned_to_unit, at(11, 9, 10), S.assigned, unit_b)
    ev("s1_decom", s1, E.decommissioned, at(10, 10, 9), S.decommissioned, None, notes="Obsolete")

    db.commit()
    return w


@pytest.fixture
def world(db: Session, people: People, monkeypatch: pytest.MonkeyPatch) -> World:
    """The worked example, with the clock frozen at 10 Nov 2026 12:00 Lagos."""
    monkeypatch.setattr("app.services.reports.common.utcnow", lambda: NOW)
    monkeypatch.setattr("app.core.timeutil.utcnow", lambda: NOW)
    return build_world(db, people)
