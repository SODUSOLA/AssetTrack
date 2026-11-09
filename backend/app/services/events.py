"""Device events and acknowledgements (SPEC section 8): the audit core.

Recording an event is one transaction:
  1. lock the device row (`SELECT ... FOR UPDATE`);
  2. check the transition and the references in the request;
  3. append the event, update the device, run the ticket effects;
  4. commit; any failure rolls everything back.

Only the device row is locked, never an audit row: the production database role may hold just
INSERT and SELECT on the audit tables, and `FOR UPDATE` needs UPDATE.
"""

import logging
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager, joinedload

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.pagination import PageParams
from app.core.timeutil import lagos_range, utcnow
from app.db.session import atomic
from app.models.complaints import Complaint
from app.models.core import Unit, User
from app.models.devices import Device
from app.models.enums import AckStatus, EventType, UserRole
from app.models.events import Acknowledgement, DeviceEvent
from app.schemas.complaints import DeviceRef
from app.schemas.devices import ComplaintRef, UnitRef, UserRef
from app.schemas.events import EventCreate, EventOut, PendingAcknowledgement
from app.services import complaints as complaint_service
from app.services.devices import EVENT_LOAD_OPTIONS, timeline_event
from app.services.event_log import ACK_REQUIRED, append_event
from app.services.event_rules import (
    CYCLE_EVENTS,
    allowed_events,
    is_allowed,
    resulting_status,
)
from app.services.scope import can_access_unit

logger = logging.getLogger("app.events")
E = EventType


# ---------- errors ----------


def _device_not_found() -> AppError:
    return AppError(404, "DEVICE_NOT_FOUND", "Device not found")


def _event_not_found() -> AppError:
    return AppError(404, "EVENT_NOT_FOUND", "Event not found")


def _invalid_transition(device: Device, event_type: EventType) -> AppError:
    return AppError(
        409,
        "INVALID_TRANSITION",
        f"A device that is {device.status.value} cannot take a {event_type.value} event",
        {
            "current": device.status.value,
            "attempted": event_type.value,
            "allowed": [e.value for e in allowed_events(device.status)],
        },
    )


# ---------- recording events ----------


def _lock_device(db: Session, device_id: uuid.UUID) -> Device:
    device = db.scalar(select(Device).where(Device.id == device_id).with_for_update())
    if device is None:
        raise _device_not_found()
    return device


def _check_counterparty_user(db: Session, user_id: uuid.UUID | None, unit_id: uuid.UUID) -> None:
    if user_id is None:
        return
    user = db.get(User, user_id)
    if (
        user is None
        or not user.is_active
        or user.role is not UserRole.unit_rep
        or user.unit_id != unit_id
    ):
        raise AppError(
            422, "COUNTERPARTY_INVALID", "counterparty_user_id must be an active rep of the unit"
        )


def _cycle_complaint_id(db: Session, device_id: uuid.UUID) -> uuid.UUID | None:
    """The ticket of the repair cycle in progress: the one named by the latest intake."""
    return db.scalar(
        select(DeviceEvent.complaint_id)
        .where(DeviceEvent.device_id == device_id, DeviceEvent.event_type == E.received_for_repair)
        .order_by(DeviceEvent.id.desc())
        .limit(1)
    )


def _prepare(db: Session, device: Device, event_type: EventType, body: Any) -> dict[str, Any]:
    """Validate type-specific references; returns the extra columns for the event row.

    May change `device.unit_id` (assignment). Never touches the device status.
    """
    fields: dict[str, Any] = {}

    if event_type is E.assigned_to_unit:
        unit = db.get(Unit, body.unit_id)
        if unit is None or not unit.is_active:
            raise AppError(422, "UNIT_NOT_FOUND", "Unit does not exist or is inactive")
        _check_counterparty_user(db, body.counterparty_user_id, unit.id)
        device.unit_id = unit.id  # the event's unit snapshot is the unit receiving the device
        fields = {
            "counterparty_name": body.counterparty_name,
            "counterparty_user_id": body.counterparty_user_id,
        }

    elif event_type is E.received_for_repair:
        complaint = db.get(Complaint, body.complaint_id)
        if complaint is None:
            raise AppError(404, "COMPLAINT_NOT_FOUND", "Complaint not found")
        if complaint.unit_id != device.unit_id:
            raise AppError(422, "COMPLAINT_UNIT_MISMATCH", "The complaint belongs to another unit")
        if complaint.device_id not in (None, device.id):
            raise AppError(
                422, "COMPLAINT_DEVICE_MISMATCH", "The complaint is about a different device"
            )
        _check_counterparty_user(db, body.counterparty_user_id, device.unit_id)
        fields = {
            "complaint_id": complaint.id,
            "counterparty_name": body.counterparty_name,
            "counterparty_user_id": body.counterparty_user_id,
        }

    elif event_type is E.diagnosed:
        fields = {"diagnosis": body.diagnosis, "complaint_id": _cycle_complaint_id(db, device.id)}

    elif event_type is E.returned_to_unit:
        _check_counterparty_user(db, body.counterparty_user_id, device.unit_id)
        fields = {
            "counterparty_name": body.counterparty_name,
            "counterparty_user_id": body.counterparty_user_id,
            "complaint_id": _cycle_complaint_id(db, device.id),
        }

    elif event_type is E.note_added:
        if body.corrects_event_id is not None:
            target = db.get(DeviceEvent, body.corrects_event_id)
            if target is None or target.device_id != device.id:
                raise AppError(
                    422,
                    "CORRECTS_EVENT_INVALID",
                    "corrects_event_id must be an event of this device",
                )
            fields["corrects_event_id"] = target.id
        if body.complaint_id is not None:
            complaint = db.get(Complaint, body.complaint_id)
            if complaint is None:
                raise AppError(404, "COMPLAINT_NOT_FOUND", "Complaint not found")
            if device.unit_id is None or complaint.unit_id != device.unit_id:
                raise AppError(
                    422, "COMPLAINT_UNIT_MISMATCH", "The complaint belongs to another unit"
                )
            fields["complaint_id"] = complaint.id

    elif event_type in CYCLE_EVENTS:  # repair_started, parts_requested, repair_completed
        fields = {"complaint_id": _cycle_complaint_id(db, device.id)}

    return fields


def record_event(db: Session, actor: User, device_id: uuid.UUID, body: EventCreate) -> EventOut:
    event_type = EventType(body.event_type)
    with atomic(db):
        device = _lock_device(db, device_id)
        if not is_allowed(event_type, device.status):
            raise _invalid_transition(device, event_type)

        from_status = device.status
        to_status = resulting_status(event_type, from_status)
        fields = _prepare(db, device, event_type, body)
        event = append_event(
            db,
            device=device,
            actor=actor,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            notes=getattr(body, "notes", None),
            **fields,
        )
        device.status = to_status

        complaint_id = fields.get("complaint_id")
        if event_type is E.received_for_repair:
            complaint_service.on_intake(db, complaint_id, actor, event.id, device)
        elif event_type is E.returned_to_unit and complaint_id is not None:
            complaint_service.on_return(db, complaint_id, actor, event.id)
    logger.info(
        "event.recorded actor=%s device=%s event=%s type=%s %s->%s",
        actor.id, device_id, event.id, event_type.value, from_status.value, to_status.value,
    )  # fmt: skip
    return get_event(db, actor, event.id)


# ---------- acknowledgements ----------


def acknowledge(
    db: Session, user: User, event_id: int, status: AckStatus, comment: str | None
) -> EventOut:
    """A unit rep confirms or disputes an event of their unit. History is never changed."""
    event = db.get(DeviceEvent, event_id)
    if event is None:
        raise _event_not_found()
    try:
        with atomic(db):
            # Serialise with everything else happening to this device (and with a twin
            # acknowledgement of the same event) by locking the device, not the audit row.
            _lock_device(db, event.device_id)
            if event.unit_id is None or event.unit_id != user.unit_id:
                raise AppError(403, "FORBIDDEN", "This event belongs to another unit")
            if event.event_type not in ACK_REQUIRED:
                raise AppError(
                    409, "ACK_NOT_REQUIRED", f"A {event.event_type.value} event is not acknowledged"
                )
            already = db.scalar(
                select(Acknowledgement.id).where(Acknowledgement.event_id == event.id)
            )
            if already is not None:
                raise AppError(
                    409, "ALREADY_ACKNOWLEDGED", "This event has already been acknowledged"
                )

            db.add(
                Acknowledgement(
                    event_id=event.id,
                    acknowledged_by=user.id,
                    status=status,
                    comment=comment,
                    acknowledged_at=func.clock_timestamp(),
                )
            )
            db.flush()
            if event.event_type is E.returned_to_unit and event.complaint_id is not None:
                complaint_service.on_return_acknowledged(
                    db, event.complaint_id, user, event.id, status
                )
    except IntegrityError as exc:  # a twin slipped past the lock; the UNIQUE constraint decides
        raise AppError(
            409, "ALREADY_ACKNOWLEDGED", "This event has already been acknowledged"
        ) from exc
    logger.info("event.acknowledged user=%s event=%s status=%s", user.id, event_id, status.value)
    return get_event(db, user, event_id)


# ---------- reading ----------


def _overdue_after() -> timedelta:
    return timedelta(days=get_settings().ack_overdue_days)


def _event_out(event: DeviceEvent, now, overdue_after: timedelta) -> EventOut:
    return EventOut(
        **timeline_event(event, now, overdue_after).model_dump(),
        device=DeviceRef.model_validate(event.device),
    )


def get_event(db: Session, user: User, event_id: int) -> EventOut:
    event = db.scalar(
        select(DeviceEvent)
        .where(DeviceEvent.id == event_id)
        .options(*EVENT_LOAD_OPTIONS, joinedload(DeviceEvent.device))
    )
    if event is None or not can_access_unit(user, event.device.unit_id):
        raise _event_not_found()
    return _event_out(event, utcnow(), _overdue_after())


def list_events(
    db: Session,
    user: User,
    params: PageParams,
    *,
    device_id: uuid.UUID | None = None,
    unit_id: uuid.UUID | None = None,
    event_type: EventType | None = None,
    actor_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[EventOut], int]:
    if date_from and date_to and date_from > date_to:
        raise AppError(422, "INVALID_RANGE", "date_from must not be after date_to")
    base = select(DeviceEvent).join(Device, Device.id == DeviceEvent.device_id)
    if user.role is UserRole.unit_rep:
        base = base.where(Device.unit_id == user.unit_id)  # their devices; client filter ignored
    elif unit_id is not None:
        base = base.where(DeviceEvent.unit_id == unit_id)
    if device_id is not None:
        base = base.where(DeviceEvent.device_id == device_id)
    if event_type is not None:
        base = base.where(DeviceEvent.event_type == event_type)
    if actor_id is not None:
        base = base.where(DeviceEvent.actor_id == actor_id)
    start, end = lagos_range(date_from, date_to)
    if start is not None:
        base = base.where(DeviceEvent.occurred_at >= start)
    if end is not None:
        base = base.where(DeviceEvent.occurred_at < end)

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (
        db.scalars(
            base.options(*EVENT_LOAD_OPTIONS, contains_eager(DeviceEvent.device))
            .order_by(DeviceEvent.occurred_at.desc(), DeviceEvent.id.desc())
            .limit(params.page_size)
            .offset(params.offset)
        )
        .unique()
        .all()
    )
    now, overdue_after = utcnow(), _overdue_after()
    return [_event_out(e, now, overdue_after) for e in rows], total


def pending_acknowledgements(
    db: Session,
    user: User,
    params: PageParams,
    *,
    unit_id: uuid.UUID | None = None,
    overdue: bool | None = None,
) -> tuple[list[PendingAcknowledgement], int]:
    """Acknowledgement-required events with no acknowledgement yet, oldest first."""
    overdue_after = _overdue_after()
    now = utcnow()
    base = (
        select(DeviceEvent)
        .join(Device, Device.id == DeviceEvent.device_id)
        .outerjoin(Acknowledgement, Acknowledgement.event_id == DeviceEvent.id)
        .where(DeviceEvent.event_type.in_(ACK_REQUIRED), Acknowledgement.id.is_(None))
    )
    if user.role is UserRole.unit_rep:
        base = base.where(DeviceEvent.unit_id == user.unit_id)
    elif unit_id is not None:
        base = base.where(DeviceEvent.unit_id == unit_id)
    if overdue is True:
        base = base.where(DeviceEvent.occurred_at < now - overdue_after)
    elif overdue is False:
        base = base.where(DeviceEvent.occurred_at >= now - overdue_after)

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (
        db.scalars(
            base.options(
                joinedload(DeviceEvent.actor),
                joinedload(DeviceEvent.unit),
                joinedload(DeviceEvent.complaint),
                contains_eager(DeviceEvent.device),
            )
            .order_by(DeviceEvent.occurred_at, DeviceEvent.id)
            .limit(params.page_size)
            .offset(params.offset)
        )
        .unique()
        .all()
    )
    items = []
    for e in rows:
        age = now - e.occurred_at
        items.append(
            PendingAcknowledgement(
                event_id=e.id,
                event_type=e.event_type,
                occurred_at=e.occurred_at,
                device=DeviceRef.model_validate(e.device),
                unit=UnitRef.model_validate(e.unit) if e.unit else None,
                actor=UserRef.model_validate(e.actor),
                counterparty_name=e.counterparty_name,
                complaint=ComplaintRef.model_validate(e.complaint) if e.complaint else None,
                pending_days=max(age.days, 0),
                overdue=age > overdue_after,
            )
        )
    return items, total
