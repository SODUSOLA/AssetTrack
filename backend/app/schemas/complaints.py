import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.enums import ComplaintCategory, ComplaintStatus, PriorityLevel
from app.schemas.devices import TimelineEvent, UnitRef, UserRef

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class _Strict(BaseModel):
    # Unknown fields (status, ticket_no, raised_by, unit...) are rejected, not ignored.
    model_config = ConfigDict(extra="forbid")


class ComplaintCreate(_Strict):
    unit_id: uuid.UUID | None = Field(
        default=None,
        description="Required when engineering raises a ticket on behalf of a unit. "
        "Unit reps must omit it: their own unit is always used.",
    )
    device_id: uuid.UUID | None = None
    category: ComplaintCategory = ComplaintCategory.hardware
    title: Title
    description: Description
    priority: PriorityLevel = PriorityLevel.medium


class ComplaintUpdate(_Strict):
    """Engineering PATCH. Omitted fields are unchanged."""

    assigned_to: uuid.UUID | None = None
    priority: PriorityLevel | None = None
    status: ComplaintStatus | None = None
    comment: Note | None = Field(
        default=None,
        description="Required with status `resolved` (resolution note) or `closed` (reason).",
    )

    @model_validator(mode="after")
    def _assignee_cannot_be_cleared(self) -> "ComplaintUpdate":
        if "assigned_to" in self.model_fields_set and self.assigned_to is None:
            raise ValueError("assigned_to cannot be cleared; reassign instead")
        return self


class ReopenRequest(_Strict):
    reason: Note


class CommentCreate(_Strict):
    body: Note


class CommentOut(BaseModel):
    id: int
    author: UserRef
    body: str
    is_system: bool
    created_at: datetime


class DeviceRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_tag: str
    device_type: str


class ComplaintOut(BaseModel):
    id: uuid.UUID
    ticket_no: str
    unit: UnitRef
    raised_by: UserRef
    device: DeviceRef | None
    category: ComplaintCategory
    title: str
    description: str
    priority: PriorityLevel
    status: ComplaintStatus
    assigned_to: UserRef | None
    created_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None


class ComplaintDetail(ComplaintOut):
    comments: list[CommentOut]
    events: list[TimelineEvent]
