"""Append-only guarantees enforced by database triggers (SPEC 4.2, 8.5, 12.1 test 1)."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Acknowledgement, Complaint, ComplaintComment
from app.models.enums import AckStatus, UserRole
from tests.factories import (
    RESTRICT_VIOLATION,
    db_error,
    make_device,
    make_event,
    make_unit,
    make_user,
)


@pytest.fixture
def audit_rows(db: Session) -> dict[str, int]:
    """One row in each append-only table; returns their ids."""
    unit = make_unit(db)
    engineer = make_user(db)
    rep = make_user(db, UserRole.unit_rep, unit)
    device = make_device(db, engineer)
    event = make_event(db, device, engineer, unit_id=unit.id, notes="registered")
    complaint = Complaint(unit_id=unit.id, raised_by=rep.id, title="Broken", description="Screen")
    db.add(complaint)
    db.flush()
    ack = Acknowledgement(event_id=event.id, acknowledged_by=rep.id, status=AckStatus.confirmed)
    comment = ComplaintComment(complaint_id=complaint.id, author_id=rep.id, body="Please check")
    db.add_all([ack, comment])
    db.flush()
    return {"device_events": event.id, "acknowledgements": ack.id, "complaint_comments": comment.id}


@pytest.mark.parametrize(
    ("table", "set_clause"),
    [
        ("device_events", "notes = 'tampered'"),
        ("acknowledgements", "comment = 'tampered'"),
        ("complaint_comments", "body = 'tampered'"),
    ],
)
def test_update_and_delete_are_rejected(
    db: Session, audit_rows: dict[str, int], table: str, set_clause: str
) -> None:
    row_id = audit_rows[table]
    with db_error(db, RESTRICT_VIOLATION):
        db.execute(text(f"UPDATE {table} SET {set_clause} WHERE id = :id"), {"id": row_id})
    with db_error(db, RESTRICT_VIOLATION):
        db.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": row_id})
    still_there = db.execute(text(f"SELECT count(*) FROM {table} WHERE id = :id"), {"id": row_id})
    assert still_there.scalar() == 1


@pytest.mark.parametrize("table", ["device_events", "acknowledgements", "complaint_comments"])
def test_truncate_is_rejected(db: Session, audit_rows: dict[str, int], table: str) -> None:
    with db_error(db, RESTRICT_VIOLATION):
        db.execute(text(f"TRUNCATE {table} CASCADE"))


def test_truncate_cascading_from_parent_is_rejected(
    db: Session, audit_rows: dict[str, int]
) -> None:
    with db_error(db, RESTRICT_VIOLATION):
        db.execute(text("TRUNCATE devices CASCADE"))
