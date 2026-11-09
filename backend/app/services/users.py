import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.pagination import PageParams, paginate
from app.core.security import hash_password
from app.models.core import Unit, User
from app.models.enums import UserRole
from app.schemas.users import UserCreate, UserUpdate
from app.services.auth import revoke_all_refresh_tokens

logger = logging.getLogger("app.admin")


def _email_taken() -> AppError:
    return AppError(409, "EMAIL_TAKEN", "A user with this email already exists")


def _require_active_unit(db: Session, unit_id: uuid.UUID) -> None:
    unit = db.get(Unit, unit_id)
    if unit is None or not unit.is_active:
        raise AppError(422, "UNIT_NOT_FOUND", "Unit does not exist or is inactive")


def _normalise_email(email: str) -> str:
    return email.strip()


def create_user(db: Session, data: UserCreate, *, actor: User | None = None) -> User:
    """`actor` is None only for the bootstrap script."""
    if data.role is UserRole.unit_rep:
        if data.unit_id is None:
            raise AppError(422, "UNIT_REQUIRED", "A unit_rep must belong to a unit")
        _require_active_unit(db, data.unit_id)
    elif data.unit_id is not None:
        raise AppError(422, "UNIT_NOT_ALLOWED", "Only unit_rep users belong to a unit")

    email = _normalise_email(data.email)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise _email_taken()

    user = User(
        full_name=data.full_name,
        email=email,
        password_hash=hash_password(data.password),
        role=data.role,
        unit_id=data.unit_id,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:  # lost a race with a concurrent create
        db.rollback()
        raise _email_taken() from exc
    logger.info(
        "user.created actor=%s target=%s role=%s",
        actor.id if actor else "bootstrap",
        user.id,
        user.role,
    )
    return user


def list_users(
    db: Session, params: PageParams, *, role: UserRole | None = None, is_active: bool | None = None
) -> tuple[list[User], int]:
    stmt = select(User).order_by(User.full_name, User.id)
    if role is not None:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    return paginate(db, stmt, params)


def get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "User not found")
    return user


def _ensure_another_active_admin(db: Session, target: User) -> None:
    """Lock the active admins and require one besides `target`."""
    others = db.scalars(
        select(User.id)
        .where(User.role == UserRole.admin, User.is_active.is_(True), User.id != target.id)
        .with_for_update()
    ).all()
    if not others:
        raise AppError(409, "LAST_ADMIN", "At least one active admin must remain")


def update_user(db: Session, actor: User, user_id: uuid.UUID, data: UserUpdate) -> User:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "User not found")

    fields = data.model_fields_set
    new_role = data.role if data.role is not None else user.role
    new_active = data.is_active if data.is_active is not None else user.is_active
    new_unit = data.unit_id if "unit_id" in fields else user.unit_id

    if new_role is UserRole.unit_rep:
        if new_unit is None:
            raise AppError(422, "UNIT_REQUIRED", "A unit_rep must belong to a unit")
        if new_unit != user.unit_id:
            _require_active_unit(db, new_unit)
    else:
        if "unit_id" in fields and data.unit_id is not None:
            raise AppError(422, "UNIT_NOT_ALLOWED", "Only unit_rep users belong to a unit")
        new_unit = None

    loses_admin = user.role is UserRole.admin and user.is_active
    if loses_admin and (new_role is not UserRole.admin or not new_active):
        _ensure_another_active_admin(db, user)

    sessions_end = False
    if data.full_name is not None:
        user.full_name = data.full_name
    if new_role is not user.role:
        logger.info(
            "user.role_changed actor=%s target=%s %s->%s", actor.id, user.id, user.role, new_role
        )
        user.role = new_role
    user.unit_id = new_unit
    if new_active != user.is_active:
        logger.info(
            "user.active_changed actor=%s target=%s active=%s", actor.id, user.id, new_active
        )
        user.is_active = new_active
        sessions_end = not new_active
    if data.password is not None:
        user.password_hash = hash_password(data.password)
        logger.info("user.password_reset actor=%s target=%s", actor.id, user.id)
        sessions_end = True
    if sessions_end:
        revoke_all_refresh_tokens(db, user.id)

    db.commit()
    return user
