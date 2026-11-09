"""Unit scoping helpers. Endpoint-level two-unit tests arrive with each unit-owned module."""

import uuid

import pytest
from sqlalchemy import select

from app.core.errors import AppError
from app.models.core import User
from app.models.devices import Device
from app.models.enums import UserRole
from app.services.scope import (
    apply_unit_scope,
    can_access_unit,
    ensure_unit_access,
    resolve_unit_filter,
    scoped_unit_id,
)

UNIT_A, UNIT_B = uuid.uuid4(), uuid.uuid4()


def user(role: UserRole, unit_id: uuid.UUID | None = None) -> User:
    return User(id=uuid.uuid4(), role=role, unit_id=unit_id)


REP_A = user(UserRole.unit_rep, UNIT_A)
STAFF = [user(r) for r in (UserRole.admin, UserRole.engineer, UserRole.auditor)]


def test_unit_rep_is_scoped_to_their_unit() -> None:
    assert scoped_unit_id(REP_A) == UNIT_A


@pytest.mark.parametrize("staff", STAFF)
def test_other_roles_are_not_scoped(staff: User) -> None:
    assert scoped_unit_id(staff) is None
    assert resolve_unit_filter(staff, UNIT_B) == UNIT_B
    assert resolve_unit_filter(staff, None) is None
    ensure_unit_access(staff, UNIT_B)  # no exception


def test_client_supplied_unit_filter_is_ignored_for_unit_rep() -> None:
    assert resolve_unit_filter(REP_A, UNIT_B) == UNIT_A
    assert resolve_unit_filter(REP_A, None) == UNIT_A


def test_can_access_unit() -> None:
    assert can_access_unit(REP_A, UNIT_A)
    assert not can_access_unit(REP_A, UNIT_B)
    assert not can_access_unit(REP_A, None)  # central stock is not a unit rep's to see
    for staff in STAFF:
        assert can_access_unit(staff, UNIT_B) and can_access_unit(staff, None)


def test_unit_rep_reaching_for_another_unit_gets_404() -> None:
    ensure_unit_access(REP_A, UNIT_A)
    for other in (UNIT_B, None):
        with pytest.raises(AppError) as exc:
            ensure_unit_access(REP_A, other)
        assert exc.value.status_code == 404  # not 403: existence stays hidden


def test_apply_unit_scope_adds_the_filter_only_for_unit_rep() -> None:
    base = select(Device)
    scoped = str(apply_unit_scope(base, REP_A, Device.unit_id).compile())
    assert "devices.unit_id =" in scoped
    assert str(apply_unit_scope(base, STAFF[0], Device.unit_id).compile()) == str(base.compile())
