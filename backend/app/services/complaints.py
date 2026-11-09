"""Complaint tickets (SPEC section 7).

Status flow:  open -> in_progress -> resolved -> closed, with `reopened` leading back to
in_progress. Every state change, manual or automatic, writes a system comment from the acting
user, so each change is explainable by a comment or by the event it names.

Who moves a ticket
  * engineering (PATCH): open/reopened -> in_progress, in_progress -> resolved (note required),
    open/in_progress -> closed (reason required: duplicate or mistaken ticket);
  * the unit (confirm/reopen): resolved -> closed / reopened, only when no returned device is
    still awaiting its acknowledgement;
  * device events (Milestone 6 calls the `on_*` functions inside its own transaction):
    intake -> in_progress, return -> resolved, confirmed return -> closed, disputed -> reopened.
Engineering can never close a resolved ticket on the unit's behalf.
"""

import logging
import uuid
from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.pagination import PageParams, paginate
from app.core.timeutil import lagos_range, utcnow
from app.db.session import atomic
from app.models.complaints import Complaint, ComplaintComment
from app.models.core import Unit, User
from app.models.devices import Device
from app.models.enums import (
    AckStatus,
    ComplaintStatus,
    DeviceStatus,
    EventType,
    PriorityLevel,
    UserRole,
)
from app.models.events import Acknowledgement, DeviceEvent
from app.schemas.complaints import (
    CommentOut,
    ComplaintCreate,
    ComplaintDetail,
    ComplaintOut,
    ComplaintUpdate,
    DeviceRef,
)
from app.schemas.devices import UnitRef, UserRef
from app.services.devices import EVENT_LOAD_OPTIONS, timeline_event
from app.services.scope import can_access_unit, resolve_unit_filter

logger = logging.getLogger("app.complaints")

S = ComplaintStatus
# Transitions engineering may request through PATCH.
MANUAL_TRANSITIONS: dict[ComplaintStatus, frozenset[ComplaintStatus]] = {
    S.open: frozenset({S.in_progress, S.closed}),
    S.reopened: frozenset({S.in_progress}),
    S.in_progress: frozenset({S.resolved, S.closed}),
    S.resolved: frozenset(),
    S.closed: frozenset(),
}
FINISHED = frozenset({S.resolved, S.closed})


# ---------- helpers ----------


def _not_found() -> AppError:
    # Same answer for "no such ticket" and "another unit's ticket".
    return AppError(404, "COMPLAINT_NOT_FOUND", "Complaint not found")


def _invalid_transition(current: S, requested: S, allowed: Sequence[S] = ()) -> AppError:
    return AppError(
        409,
        "INVALID_TRANSITION",
        f"A {current.value} complaint cannot move to {requested.value}",
        {"current": current.value, "allowed": sorted(s.value for s in allowed)},
    )


def _log(db: Session, complaint: Complaint, actor: User, text: str) -> None:
    """System comment: the readable record of a state change."""
    db.add(
        ComplaintComment(complaint_id=complaint.id, author_id=actor.id, body=text, is_system=True)
    )


def _status_text(old: S, new: S, extra: str | None = None) -> str:
    text = f"Status: {old.value} -> {new.value}."
    return f"{text} {extra}" if extra else text


def _set_status(complaint: Complaint, new: S) -> None:
    now = utcnow()
    if new is S.resolved:
        complaint.resolved_at = now
    elif new is S.closed:
        complaint.closed_at = now
    elif new is S.reopened:
        # These two describe the current state; the system comments keep the history.
        complaint.resolved_at = None
        complaint.closed_at = None
    complaint.status = new


def _lock(db: Session, complaint_id: uuid.UUID) -> Complaint:
    complaint = db.scalar(select(Complaint).where(Complaint.id == complaint_id).with_for_update())
    if complaint is None:
        raise _not_found()
    return complaint


def _lock_visible(db: Session, user: User, complaint_id: uuid.UUID) -> Complaint:
    complaint = _lock(db, complaint_id)
    if not can_access_unit(user, complaint.unit_id):
        raise _not_found()
    return complaint


def _repairs_in_flight(db: Session, complaint_id: uuid.UUID) -> bool:
    """True while a device taken in for this ticket has not been returned.

    A decommissioned device will never come back, so it no longer blocks the ticket: engineering
    can then resolve or close it by hand (for example when the device was beyond repair).
    """
    device_status = db.scalar(
        select(Device.status)
        .join(Complaint, Complaint.device_id == Device.id)
        .where(Complaint.id == complaint_id)
    )
    if device_status is DeviceStatus.decommissioned:
        return False

    def count(event_type: EventType) -> int:
        return (
            db.scalar(
                select(func.count())
                .select_from(DeviceEvent)
                .where(
                    DeviceEvent.complaint_id == complaint_id, DeviceEvent.event_type == event_type
                )
            )
            or 0
        )

    return count(EventType.received_for_repair) > count(EventType.returned_to_unit)


def _return_awaits_acknowledgement(db: Session, complaint_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(DeviceEvent.id)
            .outerjoin(Acknowledgement, Acknowledgement.event_id == DeviceEvent.id)
            .where(
                DeviceEvent.complaint_id == complaint_id,
                DeviceEvent.event_type == EventType.returned_to_unit,
                Acknowledgement.id.is_(None),
            )
            .limit(1)
        )
        is not None
    )


def complaint_out(complaint: Complaint) -> ComplaintOut:
    return ComplaintOut(
        id=complaint.id,
        ticket_no=complaint.ticket_no,
        unit=UnitRef.model_validate(complaint.unit),
        raised_by=UserRef.model_validate(complaint.raiser),
        device=DeviceRef.model_validate(complaint.device) if complaint.device else None,
        category=complaint.category,
        title=complaint.title,
        description=complaint.description,
        priority=complaint.priority,
        status=complaint.status,
        assigned_to=UserRef.model_validate(complaint.assignee) if complaint.assignee else None,
        created_at=complaint.created_at,
        resolved_at=complaint.resolved_at,
        closed_at=complaint.closed_at,
    )


def comment_out(comment: ComplaintComment) -> CommentOut:
    return CommentOut(
        id=comment.id,
        author=UserRef.model_validate(comment.author),
        body=comment.body,
        is_system=comment.is_system,
        created_at=comment.created_at,
    )


_LOAD = (
    joinedload(Complaint.unit),
    joinedload(Complaint.raiser),
    joinedload(Complaint.device),
    joinedload(Complaint.assignee),
)


def _visible(db: Session, user: User, complaint_id: uuid.UUID) -> Complaint:
    complaint = db.scalar(select(Complaint).where(Complaint.id == complaint_id).options(*_LOAD))
    if complaint is None or not can_access_unit(user, complaint.unit_id):
        raise _not_found()
    return complaint


# ---------- read ----------


def get_complaint(db: Session, user: User, complaint_id: uuid.UUID) -> ComplaintDetail:
    complaint = _visible(db, user, complaint_id)
    comments = db.scalars(
        select(ComplaintComment)
        .where(ComplaintComment.complaint_id == complaint.id)
        .options(joinedload(ComplaintComment.author))
        .order_by(ComplaintComment.id)
    ).all()
    events = (
        db.scalars(
            select(DeviceEvent)
            .where(DeviceEvent.complaint_id == complaint.id)
            .options(*EVENT_LOAD_OPTIONS)
            .order_by(DeviceEvent.occurred_at, DeviceEvent.id)
        )
        .unique()
        .all()
    )
    overdue_after = timedelta(days=get_settings().ack_overdue_days)
    now = utcnow()
    return ComplaintDetail(
        **complaint_out(complaint).model_dump(),
        comments=[comment_out(c) for c in comments],
        events=[timeline_event(e, now, overdue_after) for e in events],
    )


def list_complaints(
    db: Session,
    user: User,
    params: PageParams,
    *,
    status: ComplaintStatus | None = None,
    unit_id: uuid.UUID | None = None,
    priority: PriorityLevel | None = None,
    device_id: uuid.UUID | None = None,
    assigned_to: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[Complaint], int]:
    if date_from and date_to and date_from > date_to:
        raise AppError(422, "INVALID_RANGE", "date_from must not be after date_to")
    stmt = (
        select(Complaint).options(*_LOAD).order_by(Complaint.created_at.desc(), Complaint.id.desc())
    )
    effective_unit = resolve_unit_filter(user, unit_id)  # a unit rep's own unit wins
    if effective_unit is not None:
        stmt = stmt.where(Complaint.unit_id == effective_unit)
    if status is not None:
        stmt = stmt.where(Complaint.status == status)
    if priority is not None:
        stmt = stmt.where(Complaint.priority == priority)
    if device_id is not None:
        stmt = stmt.where(Complaint.device_id == device_id)
    if assigned_to is not None:
        stmt = stmt.where(Complaint.assigned_to == assigned_to)
    start, end = lagos_range(date_from, date_to)
    if start is not None:
        stmt = stmt.where(Complaint.created_at >= start)
    if end is not None:
        stmt = stmt.where(Complaint.created_at < end)
    return paginate(db, stmt, params)


def list_comments(
    db: Session, user: User, complaint_id: uuid.UUID, params: PageParams
) -> tuple[list[ComplaintComment], int]:
    _visible(db, user, complaint_id)
    stmt = (
        select(ComplaintComment)
        .where(ComplaintComment.complaint_id == complaint_id)
        .options(joinedload(ComplaintComment.author))
        .order_by(ComplaintComment.id)
    )
    return paginate(db, stmt, params)


# ---------- create ----------


def create_complaint(db: Session, user: User, data: ComplaintCreate) -> ComplaintDetail:
    on_behalf = user.role is not UserRole.unit_rep
    if on_behalf:
        if data.unit_id is None:
            raise AppError(422, "UNIT_REQUIRED", "unit_id is required when raising on behalf")
        unit = db.get(Unit, data.unit_id)
        if unit is None or not unit.is_active:
            raise AppError(422, "UNIT_NOT_FOUND", "Unit does not exist or is inactive")
        unit_id = unit.id
    else:
        if data.unit_id is not None and data.unit_id != user.unit_id:
            raise AppError(
                403, "FORBIDDEN", "Unit reps can only raise complaints for their own unit"
            )
        unit_id = user.unit_id

    if data.device_id is not None:
        device = db.get(Device, data.device_id)
        if device is None or (not on_behalf and device.unit_id != unit_id):
            raise AppError(404, "DEVICE_NOT_FOUND", "Device not found")
        if device.unit_id != unit_id:
            raise AppError(422, "DEVICE_UNIT_MISMATCH", "The device does not belong to this unit")
        if device.status is DeviceStatus.decommissioned:
            raise AppError(422, "DEVICE_DECOMMISSIONED", "The device is decommissioned")

    with atomic(db):
        complaint = Complaint(
            unit_id=unit_id,
            raised_by=user.id,
            device_id=data.device_id,
            category=data.category,
            title=data.title,
            description=data.description,
            priority=data.priority,
        )
        db.add(complaint)
        db.flush()
        if on_behalf:
            _log(db, complaint, user, "Raised by engineering on behalf of the unit.")
    logger.info("complaint.created actor=%s complaint=%s unit=%s", user.id, complaint.id, unit_id)
    return get_complaint(db, user, complaint.id)


# ---------- engineering updates ----------


def _validated_assignee(db: Session, assignee_id: uuid.UUID) -> User:
    assignee = db.get(User, assignee_id)
    if (
        assignee is None
        or not assignee.is_active
        or assignee.role not in (UserRole.engineer, UserRole.admin)
    ):
        raise AppError(422, "ASSIGNEE_INVALID", "The assignee must be an active engineer or admin")
    return assignee


def update_complaint(
    db: Session, actor: User, complaint_id: uuid.UUID, data: ComplaintUpdate
) -> ComplaintDetail:
    with atomic(db):
        complaint = _lock(db, complaint_id)
        current = complaint.status
        fields = data.model_fields_set

        assignee = _validated_assignee(db, data.assigned_to) if "assigned_to" in fields else None
        new_assignee = assignee if assignee and assignee.id != complaint.assigned_to else None
        new_priority = data.priority if data.priority not in (None, complaint.priority) else None
        new_status = data.status if data.status not in (None, current) else None

        # Naming an assignee picks the ticket up: open/reopened tickets start work, even when
        # the named engineer is already the assignee (the usual case after a reopen).
        if new_status is None and assignee is not None and current in (S.open, S.reopened):
            new_status = S.in_progress

        changes = [x for x in (new_assignee, new_priority, new_status) if x is not None]
        if data.comment is not None and not changes:
            raise AppError(
                422,
                "COMMENT_WITHOUT_CHANGE",
                "comment only accompanies a status change; use POST /comments for a plain comment",
            )
        if not changes:
            return get_complaint(db, actor, complaint_id)

        if current in FINISHED:
            raise AppError(
                409,
                "TICKET_NOT_ACTIVE",
                f"A {current.value} complaint can no longer be changed by engineering",
                {"status": current.value},
            )

        if new_status is not None:
            allowed = MANUAL_TRANSITIONS[current]
            if new_status not in allowed:
                raise _invalid_transition(current, new_status, sorted(allowed, key=str))
            if new_status in (S.resolved, S.closed):
                if data.comment is None:
                    raise AppError(
                        422,
                        "COMMENT_REQUIRED",
                        f"A note is required to mark a complaint {new_status.value}",
                    )
                if _repairs_in_flight(db, complaint.id):
                    raise AppError(
                        409,
                        "DEVICE_IN_REPAIR",
                        "A device taken in for this complaint has not been returned yet",
                    )
            if (
                new_status is S.in_progress
                and complaint.assigned_to is None
                and new_assignee is None
            ):
                raise AppError(422, "ASSIGNEE_REQUIRED", "Assign an engineer to start work")

        parts: list[str] = []
        if new_priority is not None:
            parts.append(f"Priority: {complaint.priority.value} -> {new_priority.value}.")
            complaint.priority = new_priority
        if new_assignee is not None:
            parts.append(f"Assigned to {new_assignee.full_name}.")
            complaint.assigned_to = new_assignee.id
        if new_status is not None:
            parts.append(_status_text(current, new_status))
            _set_status(complaint, new_status)
        if data.comment is not None:
            parts.append(f"Note: {data.comment}")
        _log(db, complaint, actor, " ".join(parts))
    logger.info("complaint.updated actor=%s complaint=%s", actor.id, complaint_id)
    return get_complaint(db, actor, complaint_id)


# ---------- comments ----------


def add_comment(db: Session, user: User, complaint_id: uuid.UUID, body: str) -> CommentOut:
    with atomic(db):
        complaint = _lock_visible(db, user, complaint_id)
        comment = ComplaintComment(complaint_id=complaint.id, author_id=user.id, body=body)
        db.add(comment)
        db.flush()
    # Built from `user` directly: assigning comment.author would make SQLAlchemy UPDATE the row,
    # which the append-only trigger (rightly) refuses.
    return CommentOut(
        id=comment.id,
        author=UserRef.model_validate(user),
        body=comment.body,
        is_system=comment.is_system,
        created_at=comment.created_at,
    )


# ---------- the unit's side: confirm / reopen ----------


def confirm_resolution(db: Session, user: User, complaint_id: uuid.UUID) -> ComplaintDetail:
    with atomic(db):
        complaint = _lock_visible(db, user, complaint_id)
        if complaint.status is not S.resolved:
            raise _invalid_transition(complaint.status, S.closed)
        if _return_awaits_acknowledgement(db, complaint.id):
            raise AppError(
                409,
                "AWAITS_ACKNOWLEDGEMENT",
                "Acknowledge the returned device to close this complaint",
            )
        _set_status(complaint, S.closed)
        _log(db, complaint, user, _status_text(S.resolved, S.closed, "Confirmed by the unit."))
    return get_complaint(db, user, complaint_id)


def reopen_complaint(
    db: Session, user: User, complaint_id: uuid.UUID, reason: str
) -> ComplaintDetail:
    with atomic(db):
        complaint = _lock_visible(db, user, complaint_id)
        if complaint.status is not S.resolved:
            raise _invalid_transition(complaint.status, S.reopened)
        if _return_awaits_acknowledgement(db, complaint.id):
            raise AppError(
                409,
                "AWAITS_ACKNOWLEDGEMENT",
                "Dispute the returned device to reopen this complaint",
            )
        _set_status(complaint, S.reopened)
        _log(db, complaint, user, _status_text(S.resolved, S.reopened, f"Reason: {reason}"))
    return get_complaint(db, user, complaint_id)


# ---------- effects of device events (called by Milestone 6 inside its transaction) ----------


def _event_ref(event_id: int) -> str:
    return f"(device event #{event_id})"


def on_intake(
    db: Session,
    complaint_id: uuid.UUID,
    actor: User,
    event_id: int,
    device: Device | None = None,
) -> None:
    """`received_for_repair` linked to this ticket: work has started.

    A ticket raised without a device is linked to the device taken in, and a ticket nobody was
    assigned to goes to the engineer who logged the intake.
    """
    complaint = _lock(db, complaint_id)
    if complaint.status in FINISHED:
        raise AppError(
            409,
            "TICKET_NOT_ACTIVE",
            "This complaint is already resolved or closed",
            {"status": complaint.status.value},
        )
    parts: list[str] = []
    if device is not None and complaint.device_id is None:
        complaint.device_id = device.id
        parts.append(f"Linked to device {device.asset_tag}.")
    if complaint.assigned_to is None:
        complaint.assigned_to = actor.id
        parts.append(f"Assigned to {actor.full_name}.")
    old = complaint.status
    if old is not S.in_progress:
        _set_status(complaint, S.in_progress)
        parts.append(
            _status_text(old, S.in_progress, f"Device received for repair {_event_ref(event_id)}.")
        )
    if parts:
        _log(db, complaint, actor, " ".join(parts))


def on_return(db: Session, complaint_id: uuid.UUID, actor: User, event_id: int) -> None:
    """`returned_to_unit` linked to this ticket: resolved, waiting for the unit."""
    complaint = _lock(db, complaint_id)
    if complaint.status in FINISHED:
        raise AppError(
            409,
            "TICKET_NOT_ACTIVE",
            "This complaint is already resolved or closed",
            {"status": complaint.status.value},
        )
    old = complaint.status
    _set_status(complaint, S.resolved)
    _log(
        db,
        complaint,
        actor,
        _status_text(old, S.resolved, f"Device returned to the unit {_event_ref(event_id)}."),
    )


def on_return_acknowledged(
    db: Session, complaint_id: uuid.UUID, actor: User, event_id: int, status: AckStatus
) -> None:
    """The unit confirmed (-> closed) or disputed (-> reopened) a returned device."""
    complaint = _lock(db, complaint_id)
    verdict = "confirmed" if status is AckStatus.confirmed else "disputed"
    if complaint.status is not S.resolved:
        # Never block an acknowledgement; just record that it changed nothing.
        _log(
            db,
            complaint,
            actor,
            f"Return {verdict} by the unit {_event_ref(event_id)}; "
            f"complaint was {complaint.status.value}, status unchanged.",
        )
        return
    target = S.closed if status is AckStatus.confirmed else S.reopened
    _set_status(complaint, target)
    _log(
        db,
        complaint,
        actor,
        _status_text(S.resolved, target, f"Return {verdict} by the unit {_event_ref(event_id)}."),
    )
