"""Open-tickets report (SPEC 9.1): the backlog now, by unit, priority and age."""

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.models.complaints import Complaint
from app.models.enums import ComplaintStatus, EventType, PriorityLevel
from app.models.events import Acknowledgement, DeviceEvent
from app.schemas.reports import Report
from app.services.reports.common import (
    Ctx,
    col,
    date_str,
    finish,
    human,
    item,
    snapshot_label,
    table,
)

OPEN = (ComplaintStatus.open, ComplaintStatus.in_progress, ComplaintStatus.reopened)
PRIORITIES = [PriorityLevel.critical, PriorityLevel.high, PriorityLevel.medium, PriorityLevel.low]
AGE_BUCKETS = [("d0_2", 0, 2), ("d3_7", 3, 7), ("d8_14", 8, 14), ("d15_plus", 15, None)]


def unacknowledged_returns(ctx: Ctx, complaint_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    """Tickets whose returned device the unit has not acknowledged yet."""
    if not complaint_ids:
        return set()
    stmt = (
        select(DeviceEvent.complaint_id)
        .outerjoin(Acknowledgement, Acknowledgement.event_id == DeviceEvent.id)
        .where(
            DeviceEvent.complaint_id.in_(complaint_ids),
            DeviceEvent.event_type == EventType.returned_to_unit,
            Acknowledgement.id.is_(None),
        )
    )
    return set(ctx.db.scalars(stmt))


def _bucket(age: int) -> str:
    for key, low, high in AGE_BUCKETS:
        if age >= low and (high is None or age <= high):
            return key
    return AGE_BUCKETS[-1][0]


def open_tickets(ctx: Ctx) -> Report:
    db = ctx.db
    overdue_after = get_settings().ack_overdue_days
    options = (
        joinedload(Complaint.unit),
        joinedload(Complaint.device),
        joinedload(Complaint.assignee),
    )

    def fetch(*conditions):
        stmt = select(Complaint).options(*options).where(*conditions)
        if ctx.unit_id is not None:
            stmt = stmt.where(Complaint.unit_id == ctx.unit_id)
        return db.scalars(stmt).unique().all()

    backlog = fetch(Complaint.status.in_(OPEN))
    resolved = fetch(Complaint.status == ComplaintStatus.resolved)

    def age(ticket: Complaint) -> int:
        return max((ctx.now - ticket.created_at).days, 0)

    unit_ids = ctx.units_in_scope()

    # --- by unit and priority
    by_priority: dict[uuid.UUID, dict[PriorityLevel, int]] = defaultdict(lambda: defaultdict(int))
    by_age: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_status: dict[uuid.UUID, dict[ComplaintStatus, int]] = defaultdict(lambda: defaultdict(int))
    oldest: dict[uuid.UUID, int] = defaultdict(int)
    for t in backlog:
        by_priority[t.unit_id][t.priority] += 1
        by_age[t.unit_id][_bucket(age(t))] += 1
        by_status[t.unit_id][t.status] += 1
        oldest[t.unit_id] = max(oldest[t.unit_id], age(t))

    def sums(rows: list[dict], keys: list[str]) -> dict:
        return {"unit": "Total"} | {k: sum(r[k] for r in rows) for k in keys}

    priority_rows = []
    for u in unit_ids:
        counts = by_priority[u]
        priority_rows.append(
            {"unit": ctx.unit_name(u)}
            | {p.value: counts[p] for p in PRIORITIES}
            | {"total": sum(counts.values())}
        )
    priority_keys = [p.value for p in PRIORITIES] + ["total"]
    priority_section = table(
        "by_priority",
        "By unit and priority",
        [col("unit", "Unit")] + [col(p.value, p.value.capitalize(), "int") for p in PRIORITIES]
        + [col("total", "Total", "int")],
        priority_rows,
        sums(priority_rows, priority_keys),
        note="Open, in-progress and reopened tickets.",
    )  # fmt: skip

    age_rows = []
    for u in unit_ids:
        counts = by_age[u]
        age_rows.append(
            {"unit": ctx.unit_name(u)}
            | {k: counts[k] for k, _, _ in AGE_BUCKETS}
            | {"total": sum(counts.values()), "oldest_days": oldest[u]}
        )
    age_totals = sums(age_rows, [k for k, _, _ in AGE_BUCKETS] + ["total"])
    age_totals["oldest_days"] = max((r["oldest_days"] for r in age_rows), default=0)
    age_section = table(
        "by_age",
        "By unit and age",
        [
            col("unit", "Unit"),
            col("d0_2", "0-2 days", "int"),
            col("d3_7", "3-7 days", "int"),
            col("d8_14", "8-14 days", "int"),
            col("d15_plus", "15+ days", "int"),
            col("total", "Total", "int"),
            col("oldest_days", "Oldest (days)", "int"),
        ],
        age_rows,
        age_totals,
        note="Age is the number of whole days since the ticket was raised.",
    )

    status_rows = []
    for u in unit_ids:
        counts = by_status[u]
        status_rows.append(
            {"unit": ctx.unit_name(u)}
            | {s.value: counts[s] for s in OPEN}
            | {"total": sum(counts.values())}
        )
    status_section = table(
        "by_status",
        "By unit and status",
        [col("unit", "Unit")]
        + [col(s.value, s.value.replace("_", " ").capitalize(), "int") for s in OPEN]
        + [col("total", "Total", "int")],
        status_rows,
        sums(status_rows, [s.value for s in OPEN] + ["total"]),
    )  # fmt: skip

    # --- the tickets themselves, oldest first
    list_rows = [
        {
            "ticket_no": t.ticket_no,
            "unit": t.unit.name,
            "priority": t.priority.value,
            "status": human(t.status.value),
            "title": t.title,
            "device": t.device.asset_tag if t.device else "",
            "assigned_to": t.assignee.full_name if t.assignee else "",
            "raised_on": date_str(t.created_at),
            "age_days": age(t),
        }
        for t in sorted(backlog, key=lambda t: (t.created_at, t.ticket_no))
    ]
    list_section = table(
        "tickets",
        "Open tickets",
        [
            col("ticket_no", "Ticket"),
            col("unit", "Unit"),
            col("priority", "Priority"),
            col("status", "Status"),
            col("title", "Title"),
            col("device", "Device"),
            col("assigned_to", "Assigned to"),
            col("raised_on", "Raised", "date"),
            col("age_days", "Age (days)", "int"),
        ],
        list_rows,
    )

    # --- resolved but not yet confirmed by the unit
    waiting_on_device = unacknowledged_returns(ctx, {t.id for t in resolved})
    waiting_rows = []
    for t in sorted(resolved, key=lambda t: (t.resolved_at or t.created_at, t.ticket_no)):
        since = t.resolved_at or t.created_at
        days = max((ctx.now - since).days, 0)
        waiting_rows.append(
            {
                "ticket_no": t.ticket_no,
                "unit": t.unit.name,
                "title": t.title,
                "device": t.device.asset_tag if t.device else "",
                "resolved_on": date_str(since),
                "days_waiting": days,
                "waiting_for": "Device acknowledgement"
                if t.id in waiting_on_device
                else "Unit confirmation",
                "overdue": "Yes"
                if (ctx.now - since).total_seconds() > overdue_after * 86400
                else "No",
            }
        )
    waiting_section = table(
        "awaiting_unit",
        "Resolved, waiting for the unit",
        [
            col("ticket_no", "Ticket"),
            col("unit", "Unit"),
            col("title", "Title"),
            col("device", "Device"),
            col("resolved_on", "Resolved", "date"),
            col("days_waiting", "Days waiting", "int"),
            col("waiting_for", "Waiting for"),
            col("overdue", "Overdue"),
        ],
        waiting_rows,
        note=f"Overdue after {overdue_after} days. Nothing is closed on the unit's behalf.",
    )

    return finish(
        ctx,
        key="open-tickets",
        title="Open tickets",
        period=snapshot_label(ctx.now),
        summary=[
            item("open", "Open tickets", len(backlog)),
            item(
                "reopened",
                "Reopened",
                sum(1 for t in backlog if t.status is ComplaintStatus.reopened),
            ),
            item(
                "urgent",
                "Critical or high priority",
                sum(
                    1 for t in backlog if t.priority in (PriorityLevel.critical, PriorityLevel.high)
                ),
            ),
            item("awaiting_unit", "Resolved, waiting for the unit", len(resolved)),
            item("oldest_days", "Oldest open ticket (days)", age_totals["oldest_days"]),
        ],
        sections=[priority_section, age_section, status_section, list_section, waiting_section],
    )
