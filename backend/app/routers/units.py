import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.pagination import Page, Pagination, to_page
from app.models.core import User
from app.models.enums import DeviceStatus, UserRole
from app.schemas.devices import DeviceOut
from app.schemas.units import UnitCreate, UnitOut, UnitUpdate
from app.services import devices as device_service
from app.services import units as unit_service

router = APIRouter(prefix="/units", tags=["units"])

AdminUser = Annotated[User, Depends(require_roles(UserRole.admin))]


@router.get(
    "",
    response_model=Page[UnitOut],
    summary="List units",
    description="Any signed-in user may list units (names and codes only).",
)
def list_units(
    user: CurrentUser, db: DbSession, params: Pagination, is_active: bool | None = None
) -> Page[UnitOut]:
    rows, total = unit_service.list_units(db, params, is_active=is_active)
    return to_page(UnitOut, rows, total, params)


@router.post("", response_model=UnitOut, status_code=201, summary="Create a unit (admin)")
def create_unit(admin: AdminUser, db: DbSession, body: UnitCreate) -> UnitOut:
    return UnitOut.model_validate(unit_service.create_unit(db, admin, body))


@router.patch("/{unit_id}", response_model=UnitOut, summary="Update a unit (admin)")
def update_unit(admin: AdminUser, db: DbSession, unit_id: uuid.UUID, body: UnitUpdate) -> UnitOut:
    return UnitOut.model_validate(unit_service.update_unit(db, admin, unit_id, body))


@router.get(
    "/{unit_id}/devices",
    response_model=Page[DeviceOut],
    summary="Devices currently held by a unit",
    description="Same filters as `GET /devices`. A unit rep may only ask about their own unit; "
    "any other unit answers 404.",
)
def list_unit_devices(
    user: CurrentUser,
    db: DbSession,
    unit_id: uuid.UUID,
    params: Pagination,
    status: DeviceStatus | None = None,
    device_type: Annotated[str | None, Query(max_length=50)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[DeviceOut]:
    rows, total = device_service.list_unit_devices(
        db, user, unit_id, params, status=status, device_type=device_type, q=q
    )
    return to_page(DeviceOut, rows, total, params)
