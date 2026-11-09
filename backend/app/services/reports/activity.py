"""Monthly activity report (SPEC 9.1): what happened to repairs in a month, by unit and device."""

import re
import uuid
from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, select

from app.core.errors import AppError
from app.core.timeutil import month_bounds
from app.models.complaints import Complaint
from app.models.devices import Device
from app.models.enums import AckStatus, DeviceStatus, EventType
from app.models.events import Acknowledgement, DeviceEvent
from app.schemas.reports import Report
from app.services.reports.common import (
    WORKSHOP,
    Ctx,
    col,
    d1,
    finish,
    human,
    item,
    repair_cycles,
    table,
)

E = EventType
COUNTED = (
    E.assigned_to_unit,
    E.received_for_repair,
    E.repair_completed,
    E.returned_to_unit,
    E.decommissioned,
)
MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]  # fmt: skip


def parse_month(value: str) -> tuple[int, int]:
    match = MONTH.match(value or "")
    if not match or not 2000 <= int(match[1]) <= 2100:
        raise AppError(422, "INVALID_MONTH", "month must look like 2026-10")
    return int(match[1]), int(match[2])


def _state_at(ctx: Ctx, end: datetime) -> dict[uuid.UUID, tuple[DeviceStatus, uuid.UUID | None]]:
    """device id -> (status, unit id) as the log stood just before `end`."""
    rank = func.row_number().over(
        partition_by=DeviceEvent.device_id,
        order_by=(DeviceEvent.occurred_at.desc(), DeviceEvent.id.desc()),
    )
    latest = (
        select(
            DeviceEvent.device_id.label("device_id"),
            DeviceEvent.to_status.label("status"),
            DeviceEvent.unit_id.label("unit_id"),
            rank.label("rank"),
        )
        .where(DeviceEvent.occurred_at < end)
        .subquery()
    )
    stmt = select(latest.c.device_id, latest.c.status, latest.c.unit_id).where(latest.c.rank == 1)
    return {device: (status, unit) for device, status, unit in ctx.db.execute(stmt)}


def monthly_activity(ctx: Ctx, month: str) -> Report:
    db = ctx.db
    year, number = parse_month(month)
    start, end = month_bounds(year, number)
    in_month = (DeviceEvent.occurred_at >= start, DeviceEvent.occurred_at < end)

    def scoped(stmt, column):
        return stmt if ctx.unit_id is None else stmt.where(column == ctx.unit_id)

    # --- counts of events per unit
    counts: dict[tuple[uuid.UUID | None, EventType], int] = defaultdict(int)
    stmt = scoped(
        select(DeviceEvent.unit_id, DeviceEvent.event_type, func.count())
        .where(*in_month, DeviceEvent.event_type.in_(COUNTED))
        .group_by(DeviceEvent.unit_id, DeviceEvent.event_type),
        DeviceEvent.unit_id,
    )
    for unit_id, event_type, n in db.execute(stmt):
        counts[(unit_id, event_type)] = n

    # --- where every device stood at the end of the month
    state = _state_at(ctx, end)
    workshop: dict[uuid.UUID | None, int] = defaultdict(int)
    for status, unit_id in state.values():
        if status in WORKSHOP and (ctx.unit_id is None or unit_id == ctx.unit_id):
            workshop[unit_id] += 1

    # --- repairs finished in the month
    cycles = repair_cycles(ctx, start, end)
    cycle_days: dict[uuid.UUID | None, list[float]] = defaultdict(list)
    for c in cycles:
        cycle_days[c.unit_id].append(c.days)

    # --- tickets and disputes
    def per_unit(stmt):
        return {unit: n for unit, n in db.execute(stmt)}

    opened = per_unit(
        scoped(
            select(Complaint.unit_id, func.count())
            .where(Complaint.created_at >= start, Complaint.created_at < end)
            .group_by(Complaint.unit_id),
            Complaint.unit_id,
        )
    )
    closed = per_unit(
        scoped(
            select(Complaint.unit_id, func.count())
            .where(Complaint.closed_at >= start, Complaint.closed_at < end)
            .group_by(Complaint.unit_id),
            Complaint.unit_id,
        )
    )
    disputes = per_unit(
        scoped(
            select(DeviceEvent.unit_id, func.count())
            .join(Acknowledgement, Acknowledgement.event_id == DeviceEvent.id)
            .where(
                Acknowledgement.status == AckStatus.disputed,
                Acknowledgement.acknowledged_at >= start,
                Acknowledgement.acknowledged_at < end,
            )
            .group_by(DeviceEvent.unit_id),
            DeviceEvent.unit_id,
        )
    )

    # --- section 1: by unit
    def avg_days(values: list[float]) -> float | None:
        return d1(sum(values) / len(values)) if values else None

    unit_keys: list[uuid.UUID | None] = list(ctx.units_in_scope())
    if ctx.lists_central_stock:
        unit_keys.append(None)
    rows = []
    for unit_id in unit_keys:
        row = {
            "unit": ctx.unit_name(unit_id),
            "assigned": counts[(unit_id, E.assigned_to_unit)],
            "received": counts[(unit_id, E.received_for_repair)],
            "repaired": counts[(unit_id, E.repair_completed)],
            "returned": counts[(unit_id, E.returned_to_unit)],
            "decommissioned": counts[(unit_id, E.decommissioned)],
            "in_workshop": workshop[unit_id],
            "avg_days": avg_days(cycle_days[unit_id]),
            "tickets_opened": opened.get(unit_id, 0),
            "tickets_closed": closed.get(unit_id, 0),
            "disputes": disputes.get(unit_id, 0),
        }
        busy = any(v for k, v in row.items() if k not in ("unit", "avg_days"))
        if unit_id is not None or busy:  # the stock row only appears when something happened
            rows.append(row)

    def total(key: str) -> int:
        return sum(r[key] for r in rows)

    all_days = [c.days for c in cycles]
    totals = {"unit": "Total"} | {
        k: total(k)
        for k in (
            "assigned", "received", "repaired", "returned", "decommissioned",
            "in_workshop", "tickets_opened", "tickets_closed", "disputes",
        )
    }  # fmt: skip
    totals["avg_days"] = avg_days(all_days)

    by_unit = table(
        "by_unit",
        "By unit",
        [
            col("unit", "Unit"),
            col("assigned", "Devices assigned", "int"),
            col("received", "Received for repair", "int"),
            col("repaired", "Repairs completed", "int"),
            col("returned", "Returned to unit", "int"),
            col("decommissioned", "Decommissioned", "int"),
            col("in_workshop", "In the workshop at month end", "int"),
            col("avg_days", "Average days to return", "number"),
            col("tickets_opened", "Tickets opened", "int"),
            col("tickets_closed", "Tickets closed", "int"),
            col("disputes", "Disputes raised", "int"),
        ],
        rows,
        totals,
        note="Turnaround counts repairs returned in the month, from intake to return.",
    )

    # --- section 2: by device
    per_device: dict[uuid.UUID, dict[EventType, int]] = defaultdict(lambda: defaultdict(int))
    stmt = scoped(
        select(DeviceEvent.device_id, DeviceEvent.event_type, func.count())
        .where(*in_month, DeviceEvent.event_type.in_(COUNTED))
        .group_by(DeviceEvent.device_id, DeviceEvent.event_type),
        DeviceEvent.unit_id,
    )
    for device_id, event_type, n in db.execute(stmt):
        per_device[device_id][event_type] = n
    in_workshop_devices = {
        d for d, (status, unit) in state.items()
        if status in WORKSHOP and (ctx.unit_id is None or unit == ctx.unit_id)
    }  # fmt: skip
    listed = {
        d for d, c in per_device.items()
        if any(c[t] for t in (E.received_for_repair, E.repair_completed, E.returned_to_unit,
                              E.decommissioned))
    } | in_workshop_devices  # fmt: skip

    device_rows = []
    if listed:
        info = db.execute(
            select(Device.id, Device.asset_tag, Device.device_type, Device.unit_id).where(
                Device.id.in_(listed)
            )
        ).all()
        for device_id, asset_tag, device_type, unit_id in info:
            c = per_device.get(device_id, {})
            device_rows.append(
                {
                    "unit": ctx.unit_name(unit_id),
                    "asset_tag": asset_tag,
                    "device_type": device_type,
                    "received": c.get(E.received_for_repair, 0),
                    "repaired": c.get(E.repair_completed, 0),
                    "returned": c.get(E.returned_to_unit, 0),
                    "status_at_month_end": human(str(state[device_id][0])),
                }
            )
        device_rows.sort(key=lambda r: (r["unit"], r["asset_tag"]))
    by_device = table(
        "by_device",
        "By device",
        [
            col("unit", "Unit"),
            col("asset_tag", "Asset tag"),
            col("device_type", "Type"),
            col("received", "Received", "int"),
            col("repaired", "Repaired", "int"),
            col("returned", "Returned", "int"),
            col("status_at_month_end", "Status at month end"),
        ],
        device_rows,
        note="Devices with repair activity in the month, plus any still in the workshop.",
    )

    return finish(
        ctx,
        key="monthly-activity",
        title="Monthly repair activity",
        period=f"{MONTH_NAMES[number - 1]} {year}",
        summary=[
            item("received", "Devices received for repair", totals["received"]),
            item("returned", "Devices returned to units", totals["returned"]),
            item("in_workshop", "In the workshop at month end", totals["in_workshop"]),
            item("avg_days", "Average days to return", totals["avg_days"]),
            item("tickets_opened", "Tickets opened", totals["tickets_opened"]),
            item("tickets_closed", "Tickets closed", totals["tickets_closed"]),
            item("disputes", "Disputes raised", totals["disputes"]),
        ],
        sections=[by_unit, by_device],
    )
