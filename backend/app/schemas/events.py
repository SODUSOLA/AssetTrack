import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.enums import AckStatus, EventType
from app.schemas.complaints import DeviceRef
from app.schemas.devices import ComplaintRef, TimelineEvent, UnitRef, UserRef

Notes = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Person = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Diagnosis = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class _Event(BaseModel):
    # Each event type accepts exactly its own fields. Anything else (status, occurred_at,
    # actor_id, complaint_id on a repair step...) is rejected, never silently ignored.
    model_config = ConfigDict(extra="forbid")


class AssignedToUnit(_Event):
    event_type: Literal["assigned_to_unit"]
    unit_id: uuid.UUID
    counterparty_name: Person = Field(description="Who in the unit received the device.")
    counterparty_user_id: uuid.UUID | None = Field(
        default=None, description="Optional: that person's account (a unit rep of the unit)."
    )
    notes: Notes | None = None


class ReceivedForRepair(_Event):
    event_type: Literal["received_for_repair"]
    complaint_id: uuid.UUID = Field(description="The ticket this repair is for.")
    counterparty_name: Person = Field(description="Who handed the device in.")
    counterparty_user_id: uuid.UUID | None = None
    notes: Notes | None = None


class Diagnosed(_Event):
    event_type: Literal["diagnosed"]
    diagnosis: Diagnosis
    notes: Notes | None = None


class RepairStarted(_Event):
    event_type: Literal["repair_started"]
    notes: Notes | None = None


class PartsRequested(_Event):
    event_type: Literal["parts_requested"]
    notes: Notes


class RepairCompleted(_Event):
    event_type: Literal["repair_completed"]
    notes: Notes


class ReturnedToUnit(_Event):
    event_type: Literal["returned_to_unit"]
    counterparty_name: Person = Field(description="Who collected the device.")
    counterparty_user_id: uuid.UUID | None = None
    notes: Notes | None = None


class Decommissioned(_Event):
    event_type: Literal["decommissioned"]
    notes: Notes = Field(description="The reason.")


class NoteAdded(_Event):
    event_type: Literal["note_added"]
    notes: Notes
    corrects_event_id: int | None = Field(
        default=None, description="An earlier event of the same device that this note corrects."
    )
    complaint_id: uuid.UUID | None = Field(
        default=None, description="Optional: a ticket of the device's unit this note relates to."
    )


EventCreate = Annotated[
    AssignedToUnit
    | ReceivedForRepair
    | Diagnosed
    | RepairStarted
    | PartsRequested
    | RepairCompleted
    | ReturnedToUnit
    | Decommissioned
    | NoteAdded,
    Field(discriminator="event_type"),
]


class AcknowledgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AckStatus
    comment: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
        | None
    ) = None

    @model_validator(mode="after")
    def _dispute_needs_a_comment(self) -> "AcknowledgeRequest":
        if self.status is AckStatus.disputed and not self.comment:
            raise ValueError("a dispute needs a comment explaining it")
        return self


class EventOut(TimelineEvent):
    device: DeviceRef


class PendingAcknowledgement(BaseModel):
    event_id: int
    event_type: EventType
    occurred_at: datetime
    device: DeviceRef
    unit: UnitRef | None
    actor: UserRef
    counterparty_name: str | None
    complaint: ComplaintRef | None
    pending_days: int
    overdue: bool
