"""What is waiting on the unit, or on engineering to answer the unit (SPEC 9.1)."""

from datetime import timedelta

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import aliased

from app.core.config import get_settings
from app.core.timeutil import lagos_iso
from app.models.complaints import Complaint
from app.models.devices import Device
from app.models.enums import AckStatus, ComplaintStatus, EventType
from app.models.events import Acknowledgement, DeviceEvent
from app.schemas.reports import Report
from app.services.event_log import ACK_REQUIRED
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
from app.services.reports.tickets import unacknowledged_returns

E = EventType


def awaiting_unit(ctx: Ctx, include_recent: bool) -> Report:
    db = ctx.db
    threshold = get_settings().ack_overdue_days
    cutoff = ctx.now - timedelta(days=threshold)

    def scoped(stmt, column):
        return stmt if ctx.unit_id is None else stmt.where(column == ctx.unit_id)

    # --- acknowledgements nobody has answered
    pending_stmt = scoped(
        select(
            DeviceEvent.id,
            DeviceEvent.unit_id,
            Device.asset_tag,
            DeviceEvent.event_type,
            DeviceEvent.occurred_at,
            Complaint.ticket_no,
        )  # fmt: skip
        .join(Device, Device.id == DeviceEvent.device_id)
        .outerjoin(Acknowledgement, Acknowledgement.event_id == DeviceEvent.id)
        .outerjoin(Complaint, Complaint.id == DeviceEvent.complaint_id)
        .where(DeviceEvent.event_type.in_(ACK_REQUIRED), Acknowledgement.id.is_(None))
        .order_by(DeviceEvent.occurred_at, DeviceEvent.id),
        DeviceEvent.unit_id,
    )
    if not include_recent:
        pending_stmt = pending_stmt.where(DeviceEvent.occurred_at < cutoff)
    pending_rows = [
        {
            "event_id": event_id,
            "unit": ctx.unit_name(unit_id),
            "asset_tag": asset_tag,
            "event": human(event_type.value),
            "since": lagos_iso(occurred_at),
            "days_pending": max((ctx.now - occurred_at).days, 0),
            "overdue": "Yes" if occurred_at < cutoff else "No",
            "ticket_no": ticket_no or "",
        }
        for event_id, unit_id, asset_tag, event_type, occurred_at, ticket_no in db.execute(
            pending_stmt
        )
    ]
    pending_section = table(
        "pending",
        "Acknowledgements waiting for the unit",
        [
            col("event_id", "Event", "int"),
            col("unit", "Unit"),
            col("asset_tag", "Device"),
            col("event", "What happened"),
            col("since", "Since", "datetime"),
            col("days_pending", "Days pending", "int"),
            col("overdue", "Overdue"),
            col("ticket_no", "Ticket"),
        ],
        pending_rows,
        note=f"Overdue after {threshold} days. Nothing is ever confirmed on the unit's behalf.",
    )

    # --- disputes engineering has not answered
    note_answers = aliased(DeviceEvent)
    corrected = (
        exists().where(note_answers.corrects_event_id == DeviceEvent.id).correlate(DeviceEvent)
    )
    dispute_stmt = scoped(
        select(
            DeviceEvent.id,
            DeviceEvent.unit_id,
            Device.asset_tag,
            DeviceEvent.event_type,
            Acknowledgement.acknowledged_at,
            Acknowledgement.comment,
            Complaint.ticket_no,
        )  # fmt: skip
        .join(Device, Device.id == DeviceEvent.device_id)
        .join(Acknowledgement, Acknowledgement.event_id == DeviceEvent.id)
        .outerjoin(Complaint, Complaint.id == DeviceEvent.complaint_id)
        .where(
            Acknowledgement.status == AckStatus.disputed,
            or_(
                and_(
                    DeviceEvent.event_type == E.returned_to_unit,
                    Complaint.status == ComplaintStatus.reopened,
                ),
                and_(DeviceEvent.event_type != E.returned_to_unit, ~corrected),
            ),
        )
        .order_by(Acknowledgement.acknowledged_at, DeviceEvent.id),
        DeviceEvent.unit_id,
    )
    dispute_rows = [
        {
            "event_id": event_id,
            "unit": ctx.unit_name(unit_id),
            "asset_tag": asset_tag,
            "event": human(event_type.value),
            "disputed_at": lagos_iso(at),
            "days_open": max((ctx.now - at).days, 0),
            "comment": comment or "",
            "ticket_no": ticket_no or "",
        }
        for event_id, unit_id, asset_tag, event_type, at, comment, ticket_no in db.execute(
            dispute_stmt
        )
    ]
    dispute_section = table(
        "disputes",
        "Disputes engineering has not answered",
        [
            col("event_id", "Event", "int"),
            col("unit", "Unit"),
            col("asset_tag", "Device"),
            col("event", "Disputed event"),
            col("disputed_at", "Disputed", "datetime"),
            col("days_open", "Days open", "int"),
            col("comment", "The unit's comment"),
            col("ticket_no", "Ticket"),
        ],
        dispute_rows,
        note="A disputed return stays here while its ticket is reopened; any other dispute "
        "until engineering adds a note correcting it.",
    )

    # --- resolved tickets the unit has not confirmed
    resolved_stmt = scoped(
        select(Complaint).where(Complaint.status == ComplaintStatus.resolved), Complaint.unit_id
    )
    if not include_recent:
        resolved_stmt = resolved_stmt.where(Complaint.resolved_at < cutoff)
    resolved = db.scalars(resolved_stmt).all()
    # A ticket whose returned device is unacknowledged is already listed in the first section.
    waiting_on_device = unacknowledged_returns(ctx, {t.id for t in resolved})
    devices: dict = {}
    if resolved:
        devices = {
            d.id: d.asset_tag
            for d in db.execute(
                select(Device.id, Device.asset_tag).where(
                    Device.id.in_({t.device_id for t in resolved if t.device_id})
                )
            )
        }
    resolved_rows = []
    for t in sorted(resolved, key=lambda t: (t.resolved_at, t.ticket_no)):
        if t.id in waiting_on_device:
            continue
        resolved_rows.append(
            {
                "ticket_no": t.ticket_no,
                "unit": ctx.unit_name(t.unit_id),
                "title": t.title,
                "device": devices.get(t.device_id, ""),
                "resolved_on": date_str(t.resolved_at),
                "days_waiting": max((ctx.now - t.resolved_at).days, 0),
            }
        )
    resolved_section = table(
        "unconfirmed",
        "Resolved tickets the unit has not confirmed",
        [
            col("ticket_no", "Ticket"),
            col("unit", "Unit"),
            col("title", "Title"),
            col("device", "Device"),
            col("resolved_on", "Resolved", "date"),
            col("days_waiting", "Days waiting", "int"),
        ],
        resolved_rows,
        note="Tickets whose returned device still needs acknowledging appear in the first table.",
    )

    overdue_count = sum(1 for r in pending_rows if r["overdue"] == "Yes")
    return finish(
        ctx,
        key="awaiting-unit",
        title="Waiting on the units",
        period=snapshot_label(ctx.now),
        summary=[
            item("overdue_acknowledgements", "Overdue acknowledgements", overdue_count),
            item("pending_acknowledgements", "Acknowledgements listed", len(pending_rows)),
            item("open_disputes", "Disputes not yet answered", len(dispute_rows)),
            item("unconfirmed_tickets", "Resolved tickets not confirmed", len(resolved_rows)),
        ],
        sections=[pending_section, dispute_section, resolved_section],
    )
