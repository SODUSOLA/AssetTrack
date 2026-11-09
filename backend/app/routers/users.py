import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import DbSession, require_roles
from app.core.pagination import Page, Pagination, to_page
from app.models.core import User
from app.models.enums import UserRole
from app.schemas.users import UserCreate, UserOut, UserUpdate
from app.services import users as user_service

router = APIRouter(prefix="/users", tags=["users"])

AdminUser = Annotated[User, Depends(require_roles(UserRole.admin))]


@router.get("", response_model=Page[UserOut], summary="List users (admin)")
def list_users(
    admin: AdminUser,
    db: DbSession,
    params: Pagination,
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> Page[UserOut]:
    rows, total = user_service.list_users(db, params, role=role, is_active=is_active)
    return to_page(UserOut, rows, total, params)


@router.post(
    "",
    response_model=UserOut,
    status_code=201,
    summary="Create a user (admin)",
    description="Accounts are created by an admin only. The admin sets the initial password "
    "(10 to 128 characters). `unit_id` is required for `unit_rep` and rejected for other roles.",
)
def create_user(admin: AdminUser, db: DbSession, body: UserCreate) -> UserOut:
    return UserOut.model_validate(user_service.create_user(db, body, actor=admin))


@router.get("/{user_id}", response_model=UserOut, summary="Get a user (admin)")
def get_user(admin: AdminUser, db: DbSession, user_id: uuid.UUID) -> UserOut:
    return UserOut.model_validate(user_service.get_user(db, user_id))


@router.patch(
    "/{user_id}",
    response_model=UserOut,
    summary="Update role, unit, active flag, name or password (admin)",
    description="Setting `password` resets it. Deactivating a user or resetting the password ends "
    "all of that user's sessions. The last active admin cannot be demoted or deactivated.",
)
def update_user(admin: AdminUser, db: DbSession, user_id: uuid.UUID, body: UserUpdate) -> UserOut:
    return UserOut.model_validate(user_service.update_user(db, admin, user_id, body))
