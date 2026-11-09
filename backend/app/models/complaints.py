import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Identity, Index, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.core import UUID_PK, Unit, User
from app.models.devices import Device
from app.models.enums import (
    ComplaintCategory,
    ComplaintStatus,
    PriorityLevel,
    pg_enum,
)


class Complaint(Base):
    """Current-state snapshot; status changes are justified by an event or comment."""

    __tablename__ = "complaints"
    __table_args__ = (Index("idx_complaints_unit_status", "unit_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **UUID_PK)
    ticket_no: Mapped[str] = mapped_column(
        Text,
        unique=True,
        server_default=text(
            "('TKT-' || to_char(now(), 'YYYY') || '-' || "
            "lpad(nextval('ticket_no_seq')::text, 5, '0'))"
        ),
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"))
    raised_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    device_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id"))
    category: Mapped[ComplaintCategory] = mapped_column(
        pg_enum(ComplaintCategory, "complaint_category"), server_default=text("'hardware'")
    )
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[PriorityLevel] = mapped_column(
        pg_enum(PriorityLevel, "priority_level"), server_default=text("'medium'")
    )
    status: Mapped[ComplaintStatus] = mapped_column(
        pg_enum(ComplaintStatus, "complaint_status"), server_default=text("'open'")
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    unit: Mapped[Unit] = relationship(foreign_keys=[unit_id], lazy="raise_on_sql")
    raiser: Mapped[User] = relationship(foreign_keys=[raised_by], lazy="raise_on_sql")
    device: Mapped[Device | None] = relationship(foreign_keys=[device_id], lazy="raise_on_sql")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assigned_to], lazy="raise_on_sql")


class ComplaintComment(Base):
    """Append-only (enforced by trigger)."""

    __tablename__ = "complaint_comments"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    complaint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("complaints.id"))
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, server_default=text("FALSE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    author: Mapped[User] = relationship(foreign_keys=[author_id], lazy="raise_on_sql")
