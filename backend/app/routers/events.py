import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.pagination import Page, Pagination
from app.models.core import User
from app.models.enums import EventType, UserRole
from app.schemas.events import (
    AcknowledgeRequest,
    EventCreate,
    EventOut,
    PendingAcknowledgement,
)
from app.services import events as event_service

router = APIRouter(tags=["events"])

R = UserRole
Engineering = Annotated[User, Depends(require_roles(R.admin, R.engineer))]
UnitRep = Annotated[User, Depends(require_roles(R.unit_rep))]


@router.post(
    "/devices/{device_id}/events",
    response_model=EventOut,
    status_code=201,
    summary="Log a device event (admin, engineer)",
    description="Moves the device through its life cycle. Each `event_type` takes exactly its own "
    "fields; unknown fields are rejected and the server stamps the time. An event that does not "
    "fit the device's current status returns `409 INVALID_TRANSITION` listing the allowed "
    "events. The device row is locked, so two simultaneous events cannot both succeed from the "
    "same state. `assigned_to_unit`, `received_for_repair` and `returned_to_unit` must then be "
    "acknowledged by the unit. `returned_to_unit` and the steps between intake and return are "
    "linked to the repair's ticket automatically.",
)
def record_event(
    user: Engineering, db: DbSession, device_id: uuid.UUID, body: EventCreate
) -> EventOut:
    return event_service.record_event(db, user, device_id, body)


@router.get(
    "/events",
    response_model=Page[EventOut],
    summary="Event log",
    description="Newest first. A unit rep sees only events of devices in their own unit; a "
    "`unit_id` filter from a unit rep is ignored. For staff, `unit_id` matches the unit recorded "
    "on the event. `date_from` / `date_to` are inclusive Africa/Lagos days.",
)
def list_events(
    user: CurrentUser,
    db: DbSession,
    params: Pagination,
    device_id: uuid.UUID | None = None,
    unit_id: uuid.UUID | None = None,
    event_type: EventType | None = None,
    actor_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Page[EventOut]:
    items, total = event_service.list_events(
        db, user, params, device_id=device_id, unit_id=unit_id, event_type=event_type,
        actor_id=actor_id, date_from=date_from, date_to=date_to,
    )  # fmt: skip
    return Page[EventOut](items=items, total=total, page=params.page, page_size=params.page_size)


@router.get(
    "/events/{event_id}", response_model=EventOut, summary="One event with its acknowledgement"
)
def get_event(user: CurrentUser, db: DbSession, event_id: int) -> EventOut:
    return event_service.get_event(db, user, event_id)


@router.post(
    "/events/{event_id}/acknowledge",
    response_model=EventOut,
    status_code=201,
    summary="Confirm or dispute an event (unit rep of that unit)",
    description="Only for `assigned_to_unit`, `received_for_repair` and `returned_to_unit`, once "
    "per event. A dispute needs a comment and never changes history: engineering answers with a "
    "`note_added` event. Disputing a returned device reopens its ticket; confirming it closes "
    "the ticket. Another unit's event returns 403; an acknowledged one returns 409.",
)
def acknowledge_event(
    user: UnitRep, db: DbSession, event_id: int, body: AcknowledgeRequest
) -> EventOut:
    return event_service.acknowledge(db, user, event_id, body.status, body.comment)


@router.get(
    "/acknowledgements/pending",
    response_model=Page[PendingAcknowledgement],
    summary="Events waiting for acknowledgement",
    description="Oldest first, with `pending_days` and `overdue` (older than `ACK_OVERDUE_DAYS`). "
    "A unit rep sees their own unit's; everyone else sees all and may filter by `unit_id` or "
    "`overdue`. Nothing is ever auto-confirmed.",
)
def pending_acknowledgements(
    user: CurrentUser,
    db: DbSession,
    params: Pagination,
    unit_id: uuid.UUID | None = None,
    overdue: bool | None = None,
) -> Page[PendingAcknowledgement]:
    items, total = event_service.pending_acknowledgements(
        db, user, params, unit_id=unit_id, overdue=overdue
    )
    return Page[PendingAcknowledgement](
        items=items, total=total, page=params.page, page_size=params.page_size
    )
