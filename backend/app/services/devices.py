import logging
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.pagination import PageParams, paginate
from app.core.timeutil import lagos_range, utcnow
from app.db.session import atomic
from app.models.complaints import Complaint
from app.models.core import Unit, User
from app.models.devices import Device
from app.models.enums import ComplaintStatus, DeviceStatus, EventType
from app.models.events import Acknowledgement, DeviceEvent
from app.schemas.devices import (
    AcknowledgementOut,
    ComplaintRef,
    DeviceCreate,
    DeviceDetail,
    DeviceOut,
    DeviceUpdate,
    Timeline,
    TimelineEvent,
    UnitRef,
    UserRef,
)
from app.services.event_log import ACK_REQUIRED, append_event
from app.services.event_rules import allowed_events
from app.services.scope import can_access_unit, resolve_unit_filter

logger = logging.getLogger("app.devices")

# Tickets engineering still has to act on; `resolved` waits on the unit, `closed` is done.
OPEN_COMPLAINT_STATUSES = (
    ComplaintStatus.open,
    ComplaintStatus.in_progress,
    ComplaintStatus.reopened,
)
# Everything `timeline_event` reads, loaded in a fixed number of queries.
EVENT_LOAD_OPTIONS = (
    joinedload(DeviceEvent.actor),
    joinedload(DeviceEvent.counterparty_user),
    joinedload(DeviceEvent.unit),
    joinedload(DeviceEvent.complaint),
    selectinload(DeviceEvent.acknowledgement).joinedload(Acknowledgement.acknowledger),
)
METADATA_FIELDS = ("device_type", "serial_number", "make", "model", "acquired_on")


def _serial_exists() -> AppError:
    return AppError(409, "SERIAL_EXISTS", "A device with this serial number already exists")


def _not_found() -> AppError:
    # Identical for "no such device" and "not yours", so a unit rep cannot probe for ids.
    return AppError(404, "DEVICE_NOT_FOUND", "Device not found")


def _serial_taken(db: Session, serial: str, exclude_id: uuid.UUID | None = None) -> bool:
    stmt = select(Device.id).where(func.lower(Device.serial_number) == serial.lower())
    if exclude_id is not None:
        stmt = stmt.where(Device.id != exclude_id)
    return db.scalar(stmt) is not None


def _visible_device(db: Session, user: User, device_id: uuid.UUID) -> Device:
    device = db.scalar(
        select(Device)
        .where(Device.id == device_id)
        .options(joinedload(Device.unit), joinedload(Device.creator))
    )
    if device is None or not can_access_unit(user, device.unit_id):
        raise _not_found()
    return device


def _detail(db: Session, device: Device) -> DeviceDetail:
    open_count = db.scalar(
        select(func.count())
        .select_from(Complaint)
        .where(Complaint.device_id == device.id, Complaint.status.in_(OPEN_COMPLAINT_STATUSES))
    )
    return DeviceDetail(
        **DeviceOut.model_validate(device).model_dump(),
        created_by=UserRef.model_validate(device.creator),
        open_complaint_count=open_count or 0,
        allowed_events=allowed_events(device.status),
    )


def get_device(db: Session, user: User, device_id: uuid.UUID) -> DeviceDetail:
    return _detail(db, _visible_device(db, user, device_id))


def register_device(db: Session, actor: User, data: DeviceCreate) -> DeviceDetail:
    """Device row and its `device_registered` event are created in one transaction."""
    if data.serial_number and _serial_taken(db, data.serial_number):
        raise _serial_exists()
    try:
        with atomic(db):
            device = Device(
                device_type=data.device_type,
                serial_number=data.serial_number,
                make=data.make,
                model=data.model,
                acquired_on=data.acquired_on,
                created_by=actor.id,
            )
            db.add(device)
            db.flush()
            append_event(
                db,
                device=device,
                actor=actor,
                event_type=EventType.device_registered,
                from_status=None,
                to_status=DeviceStatus.in_stock,
            )
    except IntegrityError as exc:  # concurrent registration of the same serial
        raise _serial_exists() from exc
    logger.info("device.registered actor=%s device=%s", actor.id, device.id)
    return get_device(db, actor, device.id)


def _like_pattern(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _list(
    db: Session,
    params: PageParams,
    *,
    unit_id: uuid.UUID | None,
    status: DeviceStatus | None,
    device_type: str | None,
    q: str | None,
) -> tuple[list[Device], int]:
    stmt = select(Device).options(joinedload(Device.unit)).order_by(Device.asset_tag, Device.id)
    if unit_id is not None:
        stmt = stmt.where(Device.unit_id == unit_id)
    if status is not None:
        stmt = stmt.where(Device.status == status)
    if device_type:
        stmt = stmt.where(func.lower(Device.device_type) == " ".join(device_type.split()).lower())
    if q and q.strip():
        pattern = _like_pattern(q.strip())
        stmt = stmt.where(
            or_(
                Device.asset_tag.ilike(pattern, escape="\\"),
                Device.serial_number.ilike(pattern, escape="\\"),
            )
        )
    return paginate(db, stmt, params)


def list_devices(
    db: Session,
    user: User,
    params: PageParams,
    *,
    unit_id: uuid.UUID | None = None,
    status: DeviceStatus | None = None,
    device_type: str | None = None,
    q: str | None = None,
) -> tuple[list[Device], int]:
    # A unit_rep's own unit always replaces whatever unit_id the client sent.
    effective_unit = resolve_unit_filter(user, unit_id)
    return _list(db, params, unit_id=effective_unit, status=status, device_type=device_type, q=q)


def list_unit_devices(
    db: Session,
    user: User,
    unit_id: uuid.UUID,
    params: PageParams,
    *,
    status: DeviceStatus | None = None,
    device_type: str | None = None,
    q: str | None = None,
) -> tuple[list[Device], int]:
    if db.get(Unit, unit_id) is None or not can_access_unit(user, unit_id):
        raise AppError(404, "UNIT_NOT_FOUND", "Unit not found")
    return _list(db, params, unit_id=unit_id, status=status, device_type=device_type, q=q)


def _describe(value: Any) -> str:
    if value is None:
        return "(none)"
    if isinstance(value, date):
        return value.isoformat()
    return f'"{value}"'


def update_device(
    db: Session, actor: User, device_id: uuid.UUID, data: DeviceUpdate
) -> DeviceDetail:
    """Patch metadata. Each real change is recorded as a `note_added` event; status and unit
    cannot be touched here (they change only through events)."""
    try:
        with atomic(db):
            device = db.scalar(select(Device).where(Device.id == device_id).with_for_update())
            if device is None:
                raise _not_found()

            changes: list[tuple[str, Any, Any]] = []
            for field in METADATA_FIELDS:
                if field not in data.model_fields_set:
                    continue
                new, old = getattr(data, field), getattr(device, field)
                if new != old:
                    changes.append((field, old, new))

            if changes:
                new_serial = next((n for f, _, n in changes if f == "serial_number"), None)
                if new_serial and _serial_taken(db, new_serial, exclude_id=device.id):
                    raise _serial_exists()
                for field, _, new in changes:
                    setattr(device, field, new)
                summary = "; ".join(f"{f} {_describe(o)} -> {_describe(n)}" for f, o, n in changes)
                db.flush()
                append_event(
                    db,
                    device=device,
                    actor=actor,
                    event_type=EventType.note_added,
                    from_status=device.status,
                    to_status=device.status,
                    notes=f"Metadata updated: {summary}",
                )
    except IntegrityError as exc:
        raise _serial_exists() from exc
    if changes:
        logger.info(
            "device.updated actor=%s device=%s fields=%s",
            actor.id,
            device_id,
            [c[0] for c in changes],
        )
    return get_device(db, actor, device_id)


def timeline_event(event: DeviceEvent, now, overdue_after: timedelta) -> TimelineEvent:
    ack: Acknowledgement | None = event.acknowledgement
    if event.event_type not in ACK_REQUIRED:
        state, pending_days, overdue = "not_required", None, False
    elif ack is None:
        age = now - event.occurred_at
        state, pending_days, overdue = "pending", max(age.days, 0), age > overdue_after
    else:
        state, pending_days, overdue = ack.status.value, None, False
    return TimelineEvent(
        id=event.id,
        event_type=event.event_type,
        from_status=event.from_status,
        to_status=event.to_status,
        occurred_at=event.occurred_at,
        actor=UserRef.model_validate(event.actor),
        unit=UnitRef.model_validate(event.unit) if event.unit else None,
        counterparty_name=event.counterparty_name,
        counterparty_user=(
            UserRef.model_validate(event.counterparty_user) if event.counterparty_user else None
        ),
        complaint=ComplaintRef.model_validate(event.complaint) if event.complaint else None,
        diagnosis=event.diagnosis,
        notes=event.notes,
        corrects_event_id=event.corrects_event_id,
        ack_state=state,
        pending_days=pending_days,
        overdue=overdue,
        acknowledgement=(
            AcknowledgementOut(
                status=ack.status,
                comment=ack.comment,
                acknowledged_at=ack.acknowledged_at,
                acknowledged_by=UserRef.model_validate(ack.acknowledger),
            )
            if ack
            else None
        ),
    )


def get_timeline(
    db: Session,
    user: User,
    device_id: uuid.UUID,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Timeline:
    """Chronological events with actor, counterparty, diagnosis and acknowledgement state.

    Dates are inclusive Lagos calendar days. A fixed number of queries however many events.
    """
    if date_from and date_to and date_from > date_to:
        raise AppError(422, "INVALID_RANGE", "date_from must not be after date_to")
    device = _visible_device(db, user, device_id)

    start, end = lagos_range(date_from, date_to)
    stmt = (
        select(DeviceEvent)
        .where(DeviceEvent.device_id == device.id)
        .options(*EVENT_LOAD_OPTIONS)
        .order_by(DeviceEvent.occurred_at, DeviceEvent.id)
    )
    if start is not None:
        stmt = stmt.where(DeviceEvent.occurred_at >= start)
    if end is not None:
        stmt = stmt.where(DeviceEvent.occurred_at < end)

    overdue_after = timedelta(days=get_settings().ack_overdue_days)
    now = utcnow()
    events = db.scalars(stmt).unique().all()
    return Timeline(
        device=DeviceOut.model_validate(device),
        events=[timeline_event(e, now, overdue_after) for e in events],
    )
