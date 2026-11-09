import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.pagination import Page, Pagination, to_page
from app.models.core import User
from app.models.enums import DeviceStatus, UserRole
from app.schemas.devices import DeviceCreate, DeviceDetail, DeviceOut, DeviceUpdate, Timeline
from app.services import devices as device_service

router = APIRouter(prefix="/devices", tags=["devices"])

Writer = Annotated[User, Depends(require_roles(UserRole.admin, UserRole.engineer))]

UnitFilter = Annotated[
    uuid.UUID | None,
    Query(description="Ignored for unit reps, who only ever see their own unit's devices."),
]
StatusFilter = Annotated[DeviceStatus | None, Query()]
TypeFilter = Annotated[
    str | None, Query(max_length=50, description="Device type, case-insensitive exact match.")
]
SearchFilter = Annotated[
    str | None,
    Query(max_length=100, description="Substring of the asset tag or serial number."),
]


@router.post(
    "",
    response_model=DeviceDetail,
    status_code=201,
    summary="Register a device (admin, engineer)",
    description="Creates the device (status `in_stock`, in central stock) and its "
    "`device_registered` event in one transaction. The asset tag is generated. Assigning the "
    "device to a unit is done later with an `assigned_to_unit` event.",
)
def register_device(user: Writer, db: DbSession, body: DeviceCreate) -> DeviceDetail:
    return device_service.register_device(db, user, body)


@router.get(
    "",
    response_model=Page[DeviceOut],
    summary="List and search devices",
    description="Admin, engineer and auditor see every device; a unit rep sees only their own "
    "unit's. Ordered by asset tag. Decommissioned devices are included.",
)
def list_devices(
    user: CurrentUser,
    db: DbSession,
    params: Pagination,
    unit_id: UnitFilter = None,
    status: StatusFilter = None,
    device_type: TypeFilter = None,
    q: SearchFilter = None,
) -> Page[DeviceOut]:
    rows, total = device_service.list_devices(
        db, user, params, unit_id=unit_id, status=status, device_type=device_type, q=q
    )
    return to_page(DeviceOut, rows, total, params)


@router.get(
    "/{device_id}",
    response_model=DeviceDetail,
    summary="Device details",
    description="Includes the current unit and the number of open complaints (`open`, "
    "`in_progress` or `reopened`).",
)
def get_device(user: CurrentUser, db: DbSession, device_id: uuid.UUID) -> DeviceDetail:
    return device_service.get_device(db, user, device_id)


@router.patch(
    "/{device_id}",
    response_model=DeviceDetail,
    summary="Correct device metadata (admin, engineer)",
    description="Only `device_type`, `serial_number`, `make`, `model` and `acquired_on`. Status "
    "and unit are rejected (422): they change only through events. Every real change writes a "
    "`note_added` event describing it; a patch that changes nothing writes nothing.",
)
def update_device(
    user: Writer, db: DbSession, device_id: uuid.UUID, body: DeviceUpdate
) -> DeviceDetail:
    return device_service.update_device(db, user, device_id, body)


@router.get(
    "/{device_id}/timeline",
    response_model=Timeline,
    summary="Device timeline",
    description="Events in chronological order with actor, counterparty, diagnosis, "
    "linked ticket and acknowledgement state (`not_required`, `pending`, `confirmed`, "
    "`disputed`; pending events report `pending_days` and `overdue`). `date_from` / `date_to` "
    "are inclusive calendar days in Africa/Lagos.",
)
def device_timeline(
    user: CurrentUser,
    db: DbSession,
    device_id: uuid.UUID,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Timeline:
    return device_service.get_timeline(db, user, device_id, date_from=date_from, date_to=date_to)
