import re
import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)

from app.models.enums import AckStatus, DeviceStatus, EventType


def _squash(value: object) -> object:
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else value


def _blank_to_none(value: object) -> object:
    value = _squash(value)
    return None if value == "" else value


# Free text where an empty string means "not provided".
OptionalText = Annotated[
    Annotated[str, Field(max_length=100)] | None, BeforeValidator(_blank_to_none)
]
# "Laptop", " laptop " and "LAPTOP" are one device type, so reports do not split them.
DeviceType = Annotated[
    str, BeforeValidator(_squash), AfterValidator(str.lower), Field(min_length=1, max_length=50)
]


class _Strict(BaseModel):
    # Unknown fields (status, unit_id, asset_tag, occurred_at...) are rejected, not ignored:
    # those change only through events, and the server stamps time.
    model_config = ConfigDict(extra="forbid")


class DeviceCreate(_Strict):
    device_type: DeviceType
    serial_number: OptionalText = None
    make: OptionalText = None
    model: OptionalText = None
    acquired_on: date | None = None


class DeviceUpdate(_Strict):
    """Metadata only. Omitted fields are unchanged; null clears serial, make, model or date."""

    device_type: DeviceType | None = None
    serial_number: OptionalText = None
    make: OptionalText = None
    model: OptionalText = None
    acquired_on: date | None = None

    @model_validator(mode="after")
    def _device_type_cannot_be_cleared(self) -> "DeviceUpdate":
        if "device_type" in self.model_fields_set and self.device_type is None:
            raise ValueError("device_type cannot be null")
        return self


class UnitRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    code: str


class UserRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str


class ComplaintRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ticket_no: str


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_tag: str
    serial_number: str | None
    device_type: str
    make: str | None
    model: str | None
    status: DeviceStatus
    acquired_on: date | None
    unit: UnitRef | None
    created_at: datetime


class DeviceDetail(DeviceOut):
    created_by: UserRef
    open_complaint_count: int
    # What an engineer may log next, from the state machine (SPEC 8.1). Never computed by clients.
    allowed_events: list[EventType]


class AcknowledgementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: AckStatus
    comment: str | None
    acknowledged_at: datetime
    acknowledged_by: UserRef


AckState = str  # "not_required" | "pending" | "confirmed" | "disputed"


class TimelineEvent(BaseModel):
    id: int
    event_type: EventType
    from_status: DeviceStatus | None
    to_status: DeviceStatus
    occurred_at: datetime
    actor: UserRef
    unit: UnitRef | None
    counterparty_name: str | None
    counterparty_user: UserRef | None
    complaint: ComplaintRef | None
    diagnosis: str | None
    notes: str | None
    corrects_event_id: int | None
    ack_state: AckState
    pending_days: int | None
    overdue: bool
    acknowledgement: AcknowledgementOut | None


class Timeline(BaseModel):
    device: DeviceOut
    events: list[TimelineEvent]
