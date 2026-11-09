import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import UserRole
from app.schemas.auth import NewPassword
from app.schemas.common import Email, NonEmptyStr


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    role: UserRole
    unit_id: uuid.UUID | None
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    full_name: NonEmptyStr
    email: Email
    password: NewPassword
    role: UserRole
    unit_id: uuid.UUID | None = None


class UserUpdate(BaseModel):
    """PATCH body. `unit_id: null` clears the unit; omitting it leaves it unchanged.

    For the other fields, null is treated the same as omitted.
    """

    full_name: NonEmptyStr | None = None
    role: UserRole | None = None
    unit_id: uuid.UUID | None = None
    is_active: bool | None = None
    password: NewPassword | None = None  # admin password reset
