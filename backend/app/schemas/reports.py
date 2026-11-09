"""One generic shape for every report, so JSON, Excel and PDF are rendered from the same object.

A report is titled sections of rows plus a few headline figures. Values are plain JSON types:
counts are ints, durations are floats rounded to one decimal, dates are `YYYY-MM-DD` and
date-times are Africa/Lagos wall-clock time with its offset (`2026-10-05T14:30+01:00`).
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.schemas.devices import UserRef

ColumnType = Literal["text", "int", "number", "date", "datetime"]


class Column(BaseModel):
    key: str
    label: str
    type: ColumnType = "text"


class Section(BaseModel):
    key: str
    title: str
    columns: list[Column]
    rows: list[dict[str, Any]]
    totals: dict[str, Any] | None = None
    note: str | None = None


class SummaryItem(BaseModel):
    key: str
    label: str
    value: int | float | str | None


class ReportScope(BaseModel):
    unit_id: uuid.UUID | None
    label: str  # the unit's name, or "All units"


class Report(BaseModel):
    key: str
    title: str
    period: str
    scope: ReportScope
    generated_at: datetime
    generated_by: UserRef
    summary: list[SummaryItem]
    sections: list[Section]
