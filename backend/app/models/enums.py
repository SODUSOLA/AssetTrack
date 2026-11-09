import enum

from sqlalchemy.dialects.postgresql import ENUM


class UserRole(enum.StrEnum):
    admin = "admin"
    engineer = "engineer"
    unit_rep = "unit_rep"
    auditor = "auditor"


class DeviceStatus(enum.StrEnum):
    in_stock = "in_stock"
    assigned = "assigned"
    received_for_repair = "received_for_repair"
    diagnosed = "diagnosed"
    in_repair = "in_repair"
    awaiting_parts = "awaiting_parts"
    repaired = "repaired"
    decommissioned = "decommissioned"


class EventType(enum.StrEnum):
    device_registered = "device_registered"
    assigned_to_unit = "assigned_to_unit"
    received_for_repair = "received_for_repair"
    diagnosed = "diagnosed"
    repair_started = "repair_started"
    parts_requested = "parts_requested"
    repair_completed = "repair_completed"
    returned_to_unit = "returned_to_unit"
    decommissioned = "decommissioned"
    note_added = "note_added"


class ComplaintStatus(enum.StrEnum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"
    reopened = "reopened"


class ComplaintCategory(enum.StrEnum):
    hardware = "hardware"
    software = "software"
    network = "network"
    other = "other"


class PriorityLevel(enum.StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class AckStatus(enum.StrEnum):
    confirmed = "confirmed"
    disputed = "disputed"


def pg_enum(cls: type[enum.StrEnum], name: str) -> ENUM:
    """PostgreSQL enum column type; the type itself is created by the migration."""
    return ENUM(cls, name=name, create_type=False, values_callable=lambda e: [m.value for m in e])
