"""The device event log: the single place that appends rows to `device_events`.

This module is deliberately small and does no validation of transitions. The state machine,
locking and ticket effects live in `app.services.events`; registration and metadata patches in
`app.services.devices` also append through here.
"""

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.core import User
from app.models.devices import Device
from app.models.enums import DeviceStatus, EventType
from app.models.events import DeviceEvent

# Events the unit must confirm or dispute (SPEC 8.3).
ACK_REQUIRED = frozenset(
    {EventType.assigned_to_unit, EventType.received_for_repair, EventType.returned_to_unit}
)

_OPTIONAL_FIELDS = frozenset(
    {
        "complaint_id",
        "counterparty_name",
        "counterparty_user_id",
        "diagnosis",
        "corrects_event_id",
    }
)


def append_event(
    db: Session,
    *,
    device: Device,
    actor: User,
    event_type: EventType,
    to_status: DeviceStatus,
    from_status: DeviceStatus | None = None,
    notes: str | None = None,
    **fields: Any,
) -> DeviceEvent:
    """Insert one event (flushed, not committed).

    * The unit is snapshotted from the device, so set `device.unit_id` first when assigning.
    * Time is stamped by the database with `clock_timestamp()`, never by the client. Unlike
      `now()` (the start of the transaction) it is read at insert time, after the device lock
      is held, so events of one device are timestamped in the order they really happened.
    """
    unknown = set(fields) - _OPTIONAL_FIELDS
    if unknown:
        raise TypeError(f"unknown event fields: {sorted(unknown)}")
    event = DeviceEvent(
        device_id=device.id,
        unit_id=device.unit_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_id=actor.id,
        notes=notes,
        occurred_at=func.clock_timestamp(),
        **fields,
    )
    db.add(event)
    db.flush()
    return event
