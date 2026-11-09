import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from app.core.deps import CurrentUser, DbSession
from app.reports.excel import XLSX_TYPE, render_xlsx
from app.reports.format import filename
from app.reports.pdf import PDF_TYPE, render_pdf
from app.schemas.reports import Report
from app.services import reports as report_service

router = APIRouter(prefix="/reports", tags=["reports"])

Format = Annotated[
    Literal["json", "xlsx", "pdf"],
    Query(description="`json` (default), `xlsx` (Excel download) or `pdf` (PDF download)."),
]
UnitFilter = Annotated[
    uuid.UUID | None,
    Query(description="Limit to one unit. Ignored for unit reps, who only see their own unit."),
]
Since = Annotated[date | None, Query(alias="from", description="First day, Africa/Lagos.")]
Until = Annotated[date | None, Query(alias="to", description="Last day, Africa/Lagos.")]

_SCOPE_NOTE = (
    "Admin, engineer and auditor see every unit; a unit rep sees only their own unit's figures. "
    "Every format carries the same numbers."
)


def deliver(report: Report, fmt: str) -> Report | Response:
    if fmt == "json":
        return report
    render, media_type = (render_xlsx, XLSX_TYPE) if fmt == "xlsx" else (render_pdf, PDF_TYPE)
    return Response(
        content=render(report),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename(report, fmt)}"',
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/monthly-activity",
    response_model=Report,
    summary="Monthly repair activity",
    description="Per unit and per device for a calendar month in Africa/Lagos: devices assigned, "
    "received for repair, repaired, returned, decommissioned, still "
    "in the workshop at month end, average days to return, tickets opened and closed, and "
    "disputes. " + _SCOPE_NOTE,
)
def monthly_activity(
    user: CurrentUser,
    db: DbSession,
    month: Annotated[str, Query(description="YYYY-MM", examples=["2026-10"])],
    unit_id: UnitFilter = None,
    format: Format = "json",
):
    ctx = report_service.make_ctx(db, user, unit_id)
    return deliver(report_service.monthly_activity(ctx, month), format)


@router.get(
    "/open-tickets",
    response_model=Report,
    summary="Open tickets by unit, priority and age",
    description="The backlog right now (open, in progress, reopened), the tickets themselves, and "
    "resolved tickets still waiting for the unit. " + _SCOPE_NOTE,
)
def open_tickets(
    user: CurrentUser, db: DbSession, unit_id: UnitFilter = None, format: Format = "json"
):
    ctx = report_service.make_ctx(db, user, unit_id)
    return deliver(report_service.open_tickets(ctx), format)


@router.get(
    "/turnaround",
    response_model=Report,
    summary="Repair turnaround",
    description="Days from `received_for_repair` to `returned_to_unit` for repairs returned in the "
    "period: average, median, shortest and longest, by unit, plus "
    "the repairs themselves. Defaults to the last 90 days. " + _SCOPE_NOTE,
)
def turnaround(
    user: CurrentUser,
    db: DbSession,
    date_from: Since = None,
    date_to: Until = None,
    unit_id: UnitFilter = None,
    format: Format = "json",
):
    ctx = report_service.make_ctx(db, user, unit_id)
    return deliver(report_service.turnaround(ctx, date_from, date_to), format)


@router.get(
    "/repeat-faults",
    response_model=Report,
    summary="Devices repaired again and again",
    description="Devices received for repair at least `min` times in the period (default 3). "
    "Defaults to the last 90 days. " + _SCOPE_NOTE,
)
def repeat_faults(
    user: CurrentUser,
    db: DbSession,
    date_from: Since = None,
    date_to: Until = None,
    min: Annotated[int, Query(description="Minimum number of repairs, 2 to 100.")] = 3,
    unit_id: UnitFilter = None,
    format: Format = "json",
):
    ctx = report_service.make_ctx(db, user, unit_id)
    return deliver(report_service.repeat_faults(ctx, date_from, date_to, min), format)


@router.get(
    "/awaiting-unit",
    response_model=Report,
    summary="What is waiting on the units",
    description="Acknowledgements pending longer than `ACK_OVERDUE_DAYS`, disputes engineering "
    "has not answered, and resolved tickets the unit has not confirmed. `include_recent=true` "
    "also lists items that are not overdue yet. Nothing is ever confirmed on a unit's behalf. "
    + _SCOPE_NOTE,
)
def awaiting_unit(
    user: CurrentUser,
    db: DbSession,
    include_recent: bool = False,
    unit_id: UnitFilter = None,
    format: Format = "json",
):
    ctx = report_service.make_ctx(db, user, unit_id)
    return deliver(report_service.awaiting_unit(ctx, include_recent), format)
