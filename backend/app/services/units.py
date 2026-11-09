import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.pagination import PageParams, paginate
from app.models.core import Unit, User
from app.schemas.units import UnitCreate, UnitUpdate

logger = logging.getLogger("app.admin")


def _duplicate() -> AppError:
    return AppError(409, "UNIT_EXISTS", "A unit with this name or code already exists")


def list_units(
    db: Session, params: PageParams, *, is_active: bool | None = None
) -> tuple[list[Unit], int]:
    stmt = select(Unit).order_by(Unit.name, Unit.id)
    if is_active is not None:
        stmt = stmt.where(Unit.is_active == is_active)
    return paginate(db, stmt, params)


def create_unit(db: Session, actor: User, data: UnitCreate) -> Unit:
    unit = Unit(name=data.name, code=data.code)
    db.add(unit)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _duplicate() from exc
    logger.info("unit.created actor=%s unit=%s", actor.id, unit.id)
    return unit


def update_unit(db: Session, actor: User, unit_id: uuid.UUID, data: UnitUpdate) -> Unit:
    unit = db.get(Unit, unit_id)
    if unit is None:
        raise AppError(404, "UNIT_NOT_FOUND", "Unit not found")
    if data.name is not None:
        unit.name = data.name
    if data.code is not None:
        unit.code = data.code
    if data.is_active is not None:
        unit.is_active = data.is_active
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _duplicate() from exc
    logger.info("unit.updated actor=%s unit=%s", actor.id, unit.id)
    return unit
