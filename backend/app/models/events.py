"""Audit core. Both tables are append-only (enforced by triggers)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.complaints import Complaint
from app.models.core import Unit, User
from app.models.devices import Device
from app.models.enums import AckStatus, DeviceStatus, EventType, pg_enum


class DeviceEvent(Base):
    __tablename__ = "device_events"
    __table_args__ = (
        CheckConstraint(
            "event_type <> 'diagnosed' OR diagnosis IS NOT NULL", name="diagnosed_needs_diagnosis"
        ),
        CheckConstraint(
            "event_type <> 'returned_to_unit' OR counterparty_name IS NOT NULL",
            name="return_needs_collector",
        ),
        CheckConstraint(
            "event_type <> 'received_for_repair' OR counterparty_name IS NOT NULL",
            name="intake_needs_depositor",
        ),
        Index("idx_events_device_time", "device_id", "occurred_at"),
        Index("idx_events_complaint", "complaint_id"),
        Index("idx_events_unit_time", "unit_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"))
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("complaints.id"))
    unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("units.id"))
    event_type: Mapped[EventType] = mapped_column(pg_enum(EventType, "event_type"))
    from_status: Mapped[DeviceStatus | None] = mapped_column(pg_enum(DeviceStatus, "device_status"))
    to_status: Mapped[DeviceStatus] = mapped_column(pg_enum(DeviceStatus, "device_status"))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    counterparty_name: Mapped[str | None] = mapped_column(Text)
    counterparty_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    diagnosis: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    corrects_event_id: Mapped[int | None] = mapped_column(ForeignKey("device_events.id"))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    device: Mapped[Device] = relationship(foreign_keys=[device_id], lazy="raise_on_sql")
    actor: Mapped[User] = relationship(foreign_keys=[actor_id], lazy="raise_on_sql")
    counterparty_user: Mapped[User | None] = relationship(
        foreign_keys=[counterparty_user_id], lazy="raise_on_sql"
    )
    unit: Mapped[Unit | None] = relationship(foreign_keys=[unit_id], lazy="raise_on_sql")
    complaint: Mapped[Complaint | None] = relationship(
        foreign_keys=[complaint_id], lazy="raise_on_sql"
    )
    acknowledgement: Mapped["Acknowledgement | None"] = relationship(
        back_populates="event", uselist=False, lazy="raise_on_sql"
    )


class Acknowledgement(Base):
    __tablename__ = "acknowledgements"
    __table_args__ = (
        CheckConstraint(
            "status <> 'disputed' OR comment IS NOT NULL", name="dispute_needs_comment"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("device_events.id"), unique=True)
    acknowledged_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[AckStatus] = mapped_column(pg_enum(AckStatus, "ack_status"))
    comment: Mapped[str | None] = mapped_column(Text)
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    event: Mapped[DeviceEvent] = relationship(back_populates="acknowledgement", lazy="raise_on_sql")
    acknowledger: Mapped[User] = relationship(foreign_keys=[acknowledged_by], lazy="raise_on_sql")
