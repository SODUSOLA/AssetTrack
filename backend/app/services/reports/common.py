"""Shared pieces of the report builders: scope, formatting, and repair cycles."""

import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.core.errors import AppError
from app.core.timeutil import APP_TIMEZONE, lagos_iso, utcnow
from app.models.complaints import Complaint
from app.models.core import Unit, User
from app.models.devices import Device
from app.models.enums import DeviceStatus, EventType
from app.models.events import DeviceEvent
from app.schemas.devices import UserRef
from app.schemas.reports import Column, Report, ReportScope, Section, SummaryItem
from app.services.scope import resolve_unit_filter

E = EventType

# Where a device is while engineering has it (or is waiting for the unit to collect it).
WORKSHOP = frozenset(
    {
        DeviceStatus.received_for_repair,
        DeviceStatus.diagnosed,
        DeviceStatus.in_repair,
        DeviceStatus.awaiting_parts,
        DeviceStatus.repaired,
    }
)
STOCK_LABEL = "Central stock"


@dataclass
class Ctx:
    """Who is asking and about which unit. A unit rep is always limited to their own unit."""

    db: Session
    user: User
    unit_id: uuid.UUID | None
    scope_label: str
    now: datetime
    _unit_names: dict[uuid.UUID, str] = field(default_factory=dict)

    def unit_names(self) -> dict[uuid.UUID, str]:
        if not self._unit_names:
            rows = self.db.execute(select(Unit.id, Unit.name).order_by(Unit.name, Unit.id))
            self._unit_names = {uid: name for uid, name in rows}
        return self._unit_names

    def unit_name(self, unit_id: uuid.UUID | None) -> str:
        return STOCK_LABEL if unit_id is None else self.unit_names().get(unit_id, "(unknown unit)")

    def units_in_scope(self) -> list[uuid.UUID]:
        """Unit ids to list, alphabetically; just the one when the report is limited to a unit."""
        if self.unit_id is not None:
            return [self.unit_id]
        return list(self.unit_names())

    @property
    def lists_central_stock(self) -> bool:
        return self.unit_id is None


def make_ctx(db: Session, user: User, requested_unit_id: uuid.UUID | None) -> Ctx:
    unit_id = resolve_unit_filter(user, requested_unit_id)  # a unit rep's own unit wins
    label = "All units"
    if unit_id is not None:
        unit = db.get(Unit, unit_id)
        if unit is None:
            raise AppError(404, "UNIT_NOT_FOUND", "Unit not found")
        label = unit.name
    return Ctx(db=db, user=user, unit_id=unit_id, scope_label=label, now=utcnow())


def finish(
    ctx: Ctx,
    *,
    key: str,
    title: str,
    period: str,
    summary: list[SummaryItem],
    sections: list[Section],
) -> Report:
    return Report(
        key=key,
        title=title,
        period=period,
        scope=ReportScope(unit_id=ctx.unit_id, label=ctx.scope_label),
        generated_at=ctx.now,
        generated_by=UserRef.model_validate(ctx.user),
        summary=summary,
        sections=sections,
    )


def col(key: str, label: str, type_: str = "text") -> Column:
    return Column(key=key, label=label, type=type_)  # type: ignore[arg-type]


def item(key: str, label: str, value: int | float | str | None) -> SummaryItem:
    return SummaryItem(key=key, label=label, value=value)


def human(value: str) -> str:
    """`received_for_repair` -> `received for repair`: labels in a report are read by people."""
    return value.replace("_", " ")


def snapshot_label(now: datetime) -> str:
    return f"As at {now.astimezone(APP_TIMEZONE):%d %b %Y %H:%M} (Lagos time)"


def d1(value: float | None) -> float | None:
    """Durations are shown to one decimal place."""
    return None if value is None else round(value, 1)


def date_str(value: datetime) -> str:
    return lagos_iso(value)[:10]


def stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"avg": None, "median": None, "min": None, "max": None}
    return {
        "avg": d1(statistics.fmean(values)),
        "median": d1(statistics.median(values)),
        "min": d1(min(values)),
        "max": d1(max(values)),
    }


# ---------- repair cycles ----------


@dataclass
class Cycle:
    """One `received_for_repair` paired with the `returned_to_unit` that ended it."""

    return_event_id: int
    device_id: uuid.UUID
    asset_tag: str
    device_type: str
    unit_id: uuid.UUID | None
    ticket_no: str | None
    received_at: datetime
    returned_at: datetime

    @property
    def days(self) -> float:
        return (self.returned_at - self.received_at).total_seconds() / 86400


def repair_cycles(ctx: Ctx, start: datetime, end: datetime) -> list[Cycle]:
    """Cycles whose return falls in [start, end), oldest return first.

    A return is paired with the latest intake of the same device before it. A cycle that ends
    in decommissioning has no return, so it never appears here.
    """
    db = ctx.db
    ret, intake = aliased(DeviceEvent), aliased(DeviceEvent)
    intake_id = (
        select(func.max(DeviceEvent.id))
        .where(
            DeviceEvent.device_id == ret.device_id,
            DeviceEvent.event_type == E.received_for_repair,
            DeviceEvent.id < ret.id,
        )
        .correlate(ret)
        .scalar_subquery()
    )
    stmt = (
        select(
            ret.id,
            ret.device_id,
            ret.unit_id,
            ret.complaint_id,
            ret.occurred_at,
            intake.id,
            intake.occurred_at,
        )  # fmt: skip
        .select_from(ret)
        .join(intake, intake.id == intake_id)
        .where(
            ret.event_type == E.returned_to_unit,
            ret.occurred_at >= start,
            ret.occurred_at < end,
        )
        .order_by(ret.occurred_at, ret.id)
    )
    if ctx.unit_id is not None:
        stmt = stmt.where(ret.unit_id == ctx.unit_id)
    rows = db.execute(stmt).all()
    if not rows:
        return []

    device_ids = {r[1] for r in rows}
    devices = {
        d.id: d
        for d in db.execute(
            select(Device.id, Device.asset_tag, Device.device_type).where(Device.id.in_(device_ids))
        )
    }
    complaint_ids = {r[3] for r in rows if r[3] is not None}
    tickets = (
        dict(
            db.execute(
                select(Complaint.id, Complaint.ticket_no).where(Complaint.id.in_(complaint_ids))
            ).all()
        )
        if complaint_ids
        else {}
    )
    cycles = []
    for (
        return_id,
        device_id,
        unit_id,
        complaint_id,
        returned_at,
        _intake_event_id,
        received_at,
    ) in rows:
        cycles.append(
            Cycle(
                return_event_id=return_id,
                device_id=device_id,
                asset_tag=devices[device_id].asset_tag,
                device_type=devices[device_id].device_type,
                unit_id=unit_id,
                ticket_no=tickets.get(complaint_id),
                received_at=received_at,
                returned_at=returned_at,
            )
        )
    return cycles


def table(
    key: str,
    title: str,
    columns: list[Column],
    rows: list[dict[str, Any]],
    totals: dict[str, Any] | None = None,
    note: str | None = None,
) -> Section:
    return Section(key=key, title=title, columns=columns, rows=rows, totals=totals, note=note)
