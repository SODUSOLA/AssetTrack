import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.common import NonEmptyStr


class UnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    is_active: bool
    created_at: datetime


class UnitCreate(BaseModel):
    name: NonEmptyStr
    code: NonEmptyStr


class UnitUpdate(BaseModel):
    name: NonEmptyStr | None = None
    code: NonEmptyStr | None = None
    is_active: bool | None = None
