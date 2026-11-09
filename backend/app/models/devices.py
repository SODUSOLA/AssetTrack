import uuid
from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.core import UUID_PK, Unit, User
from app.models.enums import DeviceStatus, pg_enum


class Device(Base):
    """Current-state snapshot; changed only by the events service, in the event's transaction."""

    __tablename__ = "devices"
    __table_args__ = (
        Index("idx_devices_unit", "unit_id"),
        Index("idx_devices_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **UUID_PK)
    asset_tag: Mapped[str] = mapped_column(
        Text,
        unique=True,
        server_default=text("('LAS-ENG-' || lpad(nextval('asset_tag_seq')::text, 6, '0'))"),
    )
    serial_number: Mapped[str | None] = mapped_column(Text, unique=True)
    device_type: Mapped[str] = mapped_column(Text)
    make: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("units.id"))
    status: Mapped[DeviceStatus] = mapped_column(
        pg_enum(DeviceStatus, "device_status"), server_default=text("'in_stock'")
    )
    acquired_on: Mapped[date | None]
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # lazy="raise_on_sql": a forgotten eager load fails loudly instead of causing N+1 queries.
    unit: Mapped[Unit | None] = relationship(foreign_keys=[unit_id], lazy="raise_on_sql")
    creator: Mapped[User] = relationship(foreign_keys=[created_by], lazy="raise_on_sql")


# Serial numbers are unique regardless of letter case ("sn-1" is "SN-1"); NULLs never collide.
Index("uq_devices_serial_lower", func.lower(Device.serial_number), unique=True)
