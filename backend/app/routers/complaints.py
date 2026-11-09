import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.pagination import Page, Pagination
from app.models.core import User
from app.models.enums import ComplaintStatus, PriorityLevel, UserRole
from app.schemas.complaints import (
    CommentCreate,
    CommentOut,
    ComplaintCreate,
    ComplaintDetail,
    ComplaintOut,
    ComplaintUpdate,
    ReopenRequest,
)
from app.services import complaints as complaint_service

router = APIRouter(prefix="/complaints", tags=["complaints"])

R = UserRole
Raiser = Annotated[User, Depends(require_roles(R.admin, R.engineer, R.unit_rep))]
Engineering = Annotated[User, Depends(require_roles(R.admin, R.engineer))]
UnitRep = Annotated[User, Depends(require_roles(R.unit_rep))]


@router.post(
    "",
    response_model=ComplaintDetail,
    status_code=201,
    summary="Raise a complaint (unit rep, admin, engineer)",
    description="A unit rep raises it for their own unit (`unit_id` is taken from their account). "
    "Admin or engineer raises it on behalf of a unit and must pass `unit_id`. `device_id` is "
    "optional and must be a device currently held by the same unit.",
)
def create_complaint(user: Raiser, db: DbSession, body: ComplaintCreate) -> ComplaintDetail:
    return complaint_service.create_complaint(db, user, body)


@router.get(
    "",
    response_model=Page[ComplaintOut],
    summary="List complaints",
    description="Newest first. A unit rep sees only their own unit's complaints; a `unit_id` "
    "filter from a unit rep is ignored. `date_from` / `date_to` are inclusive Africa/Lagos days "
    "on the creation date.",
)
def list_complaints(
    user: CurrentUser,
    db: DbSession,
    params: Pagination,
    status: ComplaintStatus | None = None,
    unit_id: uuid.UUID | None = None,
    priority: PriorityLevel | None = None,
    device_id: uuid.UUID | None = None,
    assigned_to: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Page[ComplaintOut]:
    rows, total = complaint_service.list_complaints(
        db, user, params, status=status, unit_id=unit_id, priority=priority,
        device_id=device_id, assigned_to=assigned_to, date_from=date_from, date_to=date_to,
    )  # fmt: skip
    return Page[ComplaintOut](
        items=[complaint_service.complaint_out(c) for c in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get(
    "/{complaint_id}",
    response_model=ComplaintDetail,
    summary="Complaint with its comments and linked device events",
)
def get_complaint(user: CurrentUser, db: DbSession, complaint_id: uuid.UUID) -> ComplaintDetail:
    return complaint_service.get_complaint(db, user, complaint_id)


@router.patch(
    "/{complaint_id}",
    response_model=ComplaintDetail,
    summary="Assign, prioritise or move a complaint (admin, engineer)",
    description="Assigning an `open` or `reopened` complaint starts work (`in_progress`). "
    "Manual moves: `open`/`reopened` -> `in_progress`; `in_progress` -> `resolved` (note "
    "required); `open`/`in_progress` -> `closed` (reason required, for duplicates or mistakes). "
    "Engineering cannot close a `resolved` complaint: the unit does, by acknowledging the "
    "returned device or with `confirm`. Every change writes a system comment.",
)
def update_complaint(
    user: Engineering, db: DbSession, complaint_id: uuid.UUID, body: ComplaintUpdate
) -> ComplaintDetail:
    return complaint_service.update_complaint(db, user, complaint_id, body)


@router.get(
    "/{complaint_id}/comments",
    response_model=Page[CommentOut],
    summary="Comments, oldest first",
    description="Includes system comments (`is_system: true`) that record each state change.",
)
def list_comments(
    user: CurrentUser, db: DbSession, complaint_id: uuid.UUID, params: Pagination
) -> Page[CommentOut]:
    rows, total = complaint_service.list_comments(db, user, complaint_id, params)
    return Page[CommentOut](
        items=[complaint_service.comment_out(c) for c in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post(
    "/{complaint_id}/comments",
    response_model=CommentOut,
    status_code=201,
    summary="Add a comment (unit rep of the unit, admin, engineer)",
    description="Comments are append-only and visible to both the unit and engineering.",
)
def add_comment(
    user: Raiser, db: DbSession, complaint_id: uuid.UUID, body: CommentCreate
) -> CommentOut:
    return complaint_service.add_comment(db, user, complaint_id, body.body)


@router.post(
    "/{complaint_id}/confirm",
    response_model=ComplaintDetail,
    summary="Unit confirms a resolved complaint (unit rep)",
    description="`resolved` -> `closed`. Returns 409 `AWAITS_ACKNOWLEDGEMENT` when a returned "
    "device must be acknowledged instead.",
)
def confirm_complaint(user: UnitRep, db: DbSession, complaint_id: uuid.UUID) -> ComplaintDetail:
    return complaint_service.confirm_resolution(db, user, complaint_id)


@router.post(
    "/{complaint_id}/reopen",
    response_model=ComplaintDetail,
    summary="Reopen a resolved complaint (unit rep, admin, engineer)",
    description="`resolved` -> `reopened`, with a required reason. Returns 409 "
    "`AWAITS_ACKNOWLEDGEMENT` when a returned device must be disputed instead.",
)
def reopen_complaint(
    user: Raiser, db: DbSession, complaint_id: uuid.UUID, body: ReopenRequest
) -> ComplaintDetail:
    return complaint_service.reopen_complaint(db, user, complaint_id, body.reason)
