"""CHECK, UNIQUE and default behaviour defined in the schema."""

import re

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Acknowledgement, Complaint, DeviceEvent, User
from app.models.enums import AckStatus, DeviceStatus, EventType, UserRole
from tests.factories import (
    CHECK_VIOLATION,
    UNIQUE_VIOLATION,
    db_error,
    make_device,
    make_event,
    make_unit,
    make_user,
)


def test_unit_rep_requires_unit(db: Session) -> None:
    with db_error(db, CHECK_VIOLATION, "unit_rep_requires_unit"):
        db.add(
            User(
                full_name="Rep", email="rep@example.test", password_hash="x", role=UserRole.unit_rep
            )
        )
        db.flush()


def test_email_is_case_insensitive_unique(db: Session) -> None:
    make_user(db, email="Head@Example.test")
    with db_error(db, UNIQUE_VIOLATION):
        make_user(db, email="head@example.TEST")


@pytest.mark.parametrize(
    ("event_type", "fields", "constraint"),
    [
        (EventType.diagnosed, {}, "diagnosed_needs_diagnosis"),
        (EventType.returned_to_unit, {}, "return_needs_collector"),
        (EventType.received_for_repair, {}, "intake_needs_depositor"),
    ],
)
def test_event_required_fields(db: Session, event_type, fields, constraint) -> None:
    engineer = make_user(db)
    device = make_device(db, engineer)
    with db_error(db, CHECK_VIOLATION, constraint):
        make_event(db, device, engineer, event_type=event_type, **fields)


def test_event_with_required_fields_is_accepted(db: Session) -> None:
    engineer = make_user(db)
    device = make_device(db, engineer)
    make_event(db, device, engineer, event_type=EventType.diagnosed, diagnosis="Dead battery")
    make_event(
        db,
        device,
        engineer,
        event_type=EventType.returned_to_unit,
        to_status=DeviceStatus.assigned,
        counterparty_name="A. Bello",
    )


def test_event_ids_increase_and_time_is_server_stamped(db: Session) -> None:
    engineer = make_user(db)
    device = make_device(db, engineer)
    first = make_event(db, device, engineer)
    second = make_event(db, device, engineer)
    db.refresh(first)
    db.refresh(second)
    assert second.id > first.id
    assert first.occurred_at is not None
    assert second.occurred_at >= first.occurred_at


def test_one_acknowledgement_per_event(db: Session) -> None:
    unit = make_unit(db)
    rep = make_user(db, UserRole.unit_rep, unit)
    engineer = make_user(db)
    event = make_event(db, make_device(db, engineer), engineer, unit_id=unit.id)
    db.add(Acknowledgement(event_id=event.id, acknowledged_by=rep.id, status=AckStatus.confirmed))
    db.flush()
    with db_error(db, UNIQUE_VIOLATION):
        db.add(
            Acknowledgement(event_id=event.id, acknowledged_by=rep.id, status=AckStatus.confirmed)
        )
        db.flush()


def test_dispute_requires_comment(db: Session) -> None:
    unit = make_unit(db)
    rep = make_user(db, UserRole.unit_rep, unit)
    engineer = make_user(db)
    event = make_event(db, make_device(db, engineer), engineer, unit_id=unit.id)
    with db_error(db, CHECK_VIOLATION, "dispute_needs_comment"):
        db.add(
            Acknowledgement(event_id=event.id, acknowledged_by=rep.id, status=AckStatus.disputed)
        )
        db.flush()


def test_serial_number_unique_when_present_but_null_repeats(db: Session) -> None:
    engineer = make_user(db)
    make_device(db, engineer)
    make_device(db, engineer)  # two NULL serials are fine
    make_device(db, engineer, serial_number="SN-1")
    with db_error(db, UNIQUE_VIOLATION):
        make_device(db, engineer, serial_number="SN-1")


def test_asset_tag_is_generated_and_increasing(db: Session) -> None:
    engineer = make_user(db)
    first = make_device(db, engineer)
    second = make_device(db, engineer)
    assert re.fullmatch(r"LAS-ENG-\d{6}", first.asset_tag)
    assert int(second.asset_tag[-6:]) > int(first.asset_tag[-6:])
    assert first.status is DeviceStatus.in_stock


def test_ticket_number_is_generated(db: Session) -> None:
    unit = make_unit(db)
    rep = make_user(db, UserRole.unit_rep, unit)
    complaint = Complaint(unit_id=unit.id, raised_by=rep.id, title="t", description="d")
    db.add(complaint)
    db.flush()
    db.refresh(complaint)
    year = db.execute(text("SELECT to_char(now(), 'YYYY')")).scalar()
    assert re.fullmatch(rf"TKT-{year}-\d{{5}}", complaint.ticket_no)
    assert complaint.status.value == "open"
    assert complaint.priority.value == "medium"


def test_event_can_reference_a_corrected_event(db: Session) -> None:
    engineer = make_user(db)
    device = make_device(db, engineer)
    original = make_event(db, device, engineer, notes="wrong serial")
    correction = make_event(
        db, device, engineer, notes="serial was X", corrects_event_id=original.id
    )
    assert isinstance(correction, DeviceEvent)
    assert correction.corrects_event_id == original.id
