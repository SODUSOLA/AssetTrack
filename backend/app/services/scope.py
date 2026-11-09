"""Unit scoping for `unit_rep` users.

Every service that returns unit-owned data (devices, complaints, events, reports, ...) must filter
through these helpers using the *authenticated user*, and must ignore any unit filter the client
sends when the user is a `unit_rep`.
"""

import uuid
from typing import Any

from sqlalchemy import Select

from app.core.errors import AppError
from app.models.core import User
from app.models.enums import UserRole


def scoped_unit_id(user: User) -> uuid.UUID | None:
    """The only unit this user may see, or None when the user may see every unit."""
    return user.unit_id if user.role is UserRole.unit_rep else None


def apply_unit_scope(stmt: Select[Any], user: User, unit_column: Any) -> Select[Any]:
    unit_id = scoped_unit_id(user)
    return stmt if unit_id is None else stmt.where(unit_column == unit_id)


def resolve_unit_filter(user: User, requested_unit_id: uuid.UUID | None) -> uuid.UUID | None:
    """Effective unit filter for a list endpoint: a unit_rep's own unit overrides the request."""
    own = scoped_unit_id(user)
    return own if own is not None else requested_unit_id


def can_access_unit(user: User, unit_id: uuid.UUID | None) -> bool:
    """False when a unit_rep asks about another unit or about central stock (unit_id None)."""
    own = scoped_unit_id(user)
    return own is None or unit_id == own


def ensure_unit_access(user: User, unit_id: uuid.UUID | None) -> None:
    """Raise 404 (not 403, so existence stays hidden) if a unit_rep reaches for another unit."""
    own = scoped_unit_id(user)
    if own is not None and unit_id != own:
        raise AppError(404, "NOT_FOUND", "Resource not found")
