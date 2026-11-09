"""Turnaround and repeat-fault reports (SPEC 9.1)."""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select

from app.core.errors import AppError
from app.core.timeutil import lagos_iso, lagos_range, lagos_today
from app.models.devices import Device
from app.models.enums import EventType
from app.models.events import DeviceEvent
from app.schemas.reports import Report
from app.services.reports.common import (
    Ctx,
    col,
    d1,
    date_str,
    finish,
    human,
    item,
    repair_cycles,
    stats,
    table,
)

E = EventType
DEFAULT_SPAN_DAYS = 90
MAX_SPAN_DAYS = 1830  # about five years


def resolve_range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    """Inclusive Lagos days; the last 90 days up to today when nothing is given."""
    last = date_to or lagos_today()
    first = date_from or last - timedelta(days=DEFAULT_SPAN_DAYS - 1)
    if first > last:
        raise AppError(422, "INVALID_RANGE", "from must not be after to")
    if (last - first).days > MAX_SPAN_DAYS:
        raise AppError(422, "RANGE_TOO_LARGE", "Choose a period of five years or less")
    return first, last


def _period(first: date, last: date) -> str:
    return f"{first:%d %b %Y} to {last:%d %b %Y}"


def turnaround(ctx: Ctx, date_from: date | None, date_to: date | None) -> Report:
    first, last = resolve_range(date_from, date_to)
    start, end = lagos_range(first, last)
    cycles = repair_cycles(ctx, start, end)

    by_unit: dict = defaultdict(list)
    for c in cycles:
        by_unit[c.unit_id].append(c.days)

    def stat_row(label_key: str, label: str, days: list[float]) -> dict:
        s = stats(days)
        return {
            label_key: label,
            "repairs": len(days),
            "avg_days": s["avg"],
            "median_days": s["median"],
            "shortest_days": s["min"],
            "longest_days": s["max"],
        }

    stat_columns = [
        col("repairs", "Repairs returned", "int"),
        col("avg_days", "Average days", "number"),
        col("median_days", "Median days", "number"),
        col("shortest_days", "Shortest", "number"),
        col("longest_days", "Longest", "number"),
    ]
    all_days = [c.days for c in cycles]

    unit_rows = [stat_row("unit", ctx.unit_name(u), by_unit[u]) for u in ctx.units_in_scope()]
    unit_section = table(
        "by_unit",
        "By unit",
        [col("unit", "Unit")] + stat_columns,
        unit_rows,
        stat_row("unit", "All units" if ctx.unit_id is None else ctx.scope_label, all_days),
        note="Days from the device being received for repair to its return to the unit.",
    )

    repair_rows = [
        {
            "returned_at": lagos_iso(c.returned_at),
            "unit": ctx.unit_name(c.unit_id),
            "asset_tag": c.asset_tag,
            "device_type": c.device_type,
            "ticket_no": c.ticket_no or "",
            "received_at": lagos_iso(c.received_at),
            "days": d1(c.days),
        }
        for c in cycles
    ]
    repairs_section = table(
        "repairs",
        "Repairs returned in the period",
        [
            col("returned_at", "Returned", "datetime"),
            col("unit", "Unit"),
            col("asset_tag", "Asset tag"),
            col("device_type", "Type"),
            col("ticket_no", "Ticket"),
            col("received_at", "Received", "datetime"),
            col("days", "Days", "number"),
        ],
        repair_rows,
        note="Repairs that ended in decommissioning, and those not yet returned, are not included.",
    )

    overall = stats(all_days)
    return finish(
        ctx,
        key="turnaround",
        title="Repair turnaround",
        period=_period(first, last),
        summary=[
            item("repairs", "Repairs returned", len(cycles)),
            item("avg_days", "Average days", overall["avg"]),
            item("median_days", "Median days", overall["median"]),
            item("shortest_days", "Shortest (days)", overall["min"]),
            item("longest_days", "Longest (days)", overall["max"]),
        ],
        sections=[unit_section, repairs_section],
    )


def repeat_faults(
    ctx: Ctx, date_from: date | None, date_to: date | None, min_repairs: int
) -> Report:
    if not 2 <= min_repairs <= 100:
        raise AppError(422, "INVALID_MIN", "min must be between 2 and 100")
    first, last = resolve_range(date_from, date_to)
    start, end = lagos_range(first, last)
    db = ctx.db

    in_range = (
        DeviceEvent.event_type == E.received_for_repair,
        DeviceEvent.occurred_at >= start,
        DeviceEvent.occurred_at < end,
    )
    stmt = (
        select(
            DeviceEvent.device_id,
            func.count(),
            func.min(DeviceEvent.occurred_at),
            func.max(DeviceEvent.occurred_at),
            func.count(func.distinct(DeviceEvent.complaint_id)),
        )
        .where(*in_range)
        .group_by(DeviceEvent.device_id)
        .having(func.count() >= min_repairs)
    )
    if ctx.unit_id is not None:
        stmt = stmt.where(DeviceEvent.unit_id == ctx.unit_id)
    flagged = db.execute(stmt).all()

    rows: list[dict] = []
    if flagged:
        ids = {r[0] for r in flagged}
        devices = {
            d.id: d
            for d in db.execute(
                select(
                    Device.id, Device.asset_tag, Device.device_type, Device.unit_id, Device.status
                ).where(Device.id.in_(ids))
            )
        }  # fmt: skip
        for device_id, repairs, first_at, last_at, tickets in flagged:
            d = devices[device_id]
            rows.append(
                {
                    "asset_tag": d.asset_tag,
                    "device_type": d.device_type,
                    "unit": ctx.unit_name(d.unit_id),
                    "repairs": repairs,
                    "first_received": date_str(first_at),
                    "last_received": date_str(last_at),
                    "tickets": tickets,
                    "status": human(str(d.status)),
                }
            )
        rows.sort(key=lambda r: (-r["repairs"], r["asset_tag"]))

    section = table(
        "devices",
        f"Devices repaired {min_repairs} or more times",
        [
            col("asset_tag", "Asset tag"),
            col("device_type", "Type"),
            col("unit", "Unit"),
            col("repairs", "Repairs", "int"),
            col("first_received", "First received", "date"),
            col("last_received", "Last received", "date"),
            col("tickets", "Tickets", "int"),
            col("status", "Status now"),
        ],
        rows,
        note="Counts each time a device was received for repair in the period.",
    )
    return finish(
        ctx,
        key="repeat-faults",
        title="Repeat faults",
        period=_period(first, last),
        summary=[
            item("devices", "Devices flagged", len(rows)),
            item("repairs", "Repairs on those devices", sum(r["repairs"] for r in rows)),
            item("min", "Minimum repairs to be flagged", min_repairs),
        ],
        sections=[section],
    )
