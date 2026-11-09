"""Small helpers for building rows in schema tests."""

import itertools
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import Acknowledgement, Complaint, Device, DeviceEvent, Unit, User
from app.models.enums import AckStatus, ComplaintStatus, DeviceStatus, EventType, UserRole

_counter = itertools.count(1)


def _n() -> int:
    return next(_counter)


def make_unit(db: Session, **kw) -> Unit:
    n = _n()
    unit = Unit(name=kw.pop("name", f"Unit {n}"), code=kw.pop("code", f"U{n}"), **kw)
    db.add(unit)
    db.flush()
    return unit


def make_user(db: Session, role: UserRole = UserRole.engineer, unit: Unit | None = None, **kw):
    n = _n()
    user = User(
        full_name=kw.pop("full_name", f"User {n}"),
        email=kw.pop("email", f"user{n}@example.test"),
        password_hash=kw.pop("password_hash", "x"),
        role=role,
        unit_id=unit.id if unit else None,
        **kw,
    )
    db.add(user)
    db.flush()
    return user


def make_device(db: Session, created_by: User, **kw) -> Device:
    device = Device(device_type=kw.pop("device_type", "laptop"), created_by=created_by.id, **kw)
    db.add(device)
    db.flush()
    db.refresh(device)
    return device


def make_event(db: Session, device: Device, actor: User, **kw) -> DeviceEvent:
    event = DeviceEvent(
        device_id=device.id,
        actor_id=actor.id,
        event_type=kw.pop("event_type", EventType.note_added),
        to_status=kw.pop("to_status", DeviceStatus.in_stock),
        **kw,
    )
    db.add(event)
    db.flush()
    return event


def make_complaint(
    db: Session, unit: Unit, raised_by: User, *, device: Device | None = None, **kw
) -> Complaint:
    complaint = Complaint(
        unit_id=unit.id,
        raised_by=raised_by.id,
        device_id=device.id if device else None,
        title=kw.pop("title", "Will not boot"),
        description=kw.pop("description", "Black screen"),
        status=kw.pop("status", ComplaintStatus.open),
        **kw,
    )
    db.add(complaint)
    db.flush()
    db.refresh(complaint)
    return complaint


def make_ack(
    db: Session, event: DeviceEvent, by: User, status: AckStatus = AckStatus.confirmed, **kw
) -> Acknowledgement:
    ack = Acknowledgement(event_id=event.id, acknowledged_by=by.id, status=status, **kw)
    db.add(ack)
    db.flush()
    return ack


@contextmanager
def db_error(db: Session, sqlstate: str, constraint: str | None = None) -> Iterator[None]:
    """Expect the wrapped statements to fail with `sqlstate`, without poisoning the test txn."""
    with pytest.raises(DBAPIError) as excinfo:
        with db.begin_nested():
            yield
    orig = excinfo.value.orig
    assert orig.sqlstate == sqlstate, f"expected {sqlstate}, got {orig.sqlstate}: {orig}"
    if constraint is not None:
        assert orig.diag.constraint_name == constraint


# SQLSTATE codes used in assertions
RESTRICT_VIOLATION = "23001"  # our immutability guards
NOT_NULL_VIOLATION = "23502"
FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"
