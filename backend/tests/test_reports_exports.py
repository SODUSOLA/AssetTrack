"""Excel and PDF exports carry the same numbers as the JSON, and are safe and scoped."""

import re
import unicodedata
from datetime import date, datetime
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy import event

from app.models.enums import DeviceStatus, EventType
from app.reports.format import display, footer_text
from app.reports.pdf import fonts
from app.schemas.reports import Report
from tests.api_helpers import People, bearer
from tests.factories import make_device, make_event
from tests.report_world import World, at

API = "/api/v1/reports"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

REPORTS = [
    ("monthly-activity", {"month": "2026-10"}),
    ("open-tickets", {}),
    ("turnaround", {"from": "2026-10-01", "to": "2026-10-31"}),
    ("repeat-faults", {"min": 2, "from": "2026-09-01", "to": "2026-11-30"}),
    ("awaiting-unit", {"include_recent": "true"}),
]
IDS = [name for name, _ in REPORTS]


def fetch(api: TestClient, user, name: str, params: dict, fmt: str = "json"):
    return api.get(f"{API}/{name}", headers=bearer(user), params={**params, "format": fmt})


def xlsx_workbook(content: bytes):
    return load_workbook(BytesIO(content))


def pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    return unicodedata.normalize("NFC", "\n".join(page.extract_text() for page in reader.pages))


def expected_cell(value, type_: str):
    if value is None or value == "":
        return None
    return {
        "int": int,
        "number": float,
        "date": date.fromisoformat,
        "datetime": lambda v: datetime.fromisoformat(v).replace(tzinfo=None),
    }.get(type_, str)(value)


def actual_cell(cell, type_: str):
    value = cell.value
    return value.date() if type_ == "date" and isinstance(value, datetime) else value


# ---------- Excel equals JSON ----------


@pytest.mark.parametrize(("name", "params"), REPORTS, ids=IDS)
def test_xlsx_has_the_same_numbers_as_the_json(
    api: TestClient, people: People, world: World, name: str, params: dict
) -> None:
    data = fetch(api, people.admin, name, params).json()
    resp = fetch(api, people.admin, name, params, "xlsx")
    assert resp.status_code == 200 and resp.headers["content-type"] == XLSX
    wb = xlsx_workbook(resp.content)
    report = Report.model_validate(data)

    summary = wb["Summary"]
    assert summary["A1"].value == report.title and summary["A2"].value == report.period
    assert summary["A3"].value == f"Scope: {report.scope.label}"
    assert summary["A4"].value == footer_text(report)
    assert [(summary.cell(r, 1).value, summary.cell(r, 2).value)
            for r in range(7, 7 + len(report.summary))] == [
        (s.label, s.value) for s in report.summary
    ]  # fmt: skip

    assert len(wb.worksheets) == 1 + len(report.sections)
    for ws, section in zip(wb.worksheets[1:], report.sections, strict=True):
        assert ws["A1"].value == section.title
        assert [ws.cell(4, c).value for c in range(1, len(section.columns) + 1)] == [
            c.label for c in section.columns
        ]
        for r, row in enumerate(section.rows, start=5):
            got = [actual_cell(ws.cell(r, c), col.type) for c, col in enumerate(section.columns, 1)]
            want = [expected_cell(row.get(col.key), col.type) for col in section.columns]
            assert got == want, (section.key, r)
        after = 5 + len(section.rows)
        if section.totals:
            got = [ws.cell(after, c).value for c in range(1, len(section.columns) + 1)]
            want = [expected_cell(section.totals.get(c.key), c.type) for c in section.columns]
            assert got == want
        elif not section.rows:
            assert ws.cell(5, 1).value == "No data for this period."


@pytest.mark.parametrize(("name", "params"), REPORTS, ids=IDS)
def test_xlsx_numbers_are_numbers_and_dates_are_dates(
    api: TestClient, people: People, world: World, name: str, params: dict
) -> None:
    report = Report.model_validate(fetch(api, people.admin, name, params).json())
    wb = xlsx_workbook(fetch(api, people.admin, name, params, "xlsx").content)
    for ws, section in zip(wb.worksheets[1:], report.sections, strict=True):
        for r in range(5, 5 + len(section.rows)):
            for c, column in enumerate(section.columns, start=1):
                cell = ws.cell(r, c)
                if cell.value is None:
                    continue
                if column.type == "int":
                    assert isinstance(cell.value, int) and not isinstance(cell.value, bool)
                elif column.type == "number":
                    assert isinstance(cell.value, float | int) and cell.number_format == "0.0"
                elif column.type in ("date", "datetime"):
                    assert isinstance(cell.value, datetime)
                else:
                    assert isinstance(cell.value, str) and cell.data_type == "s"


# ---------- PDF equals JSON ----------


@pytest.mark.parametrize(("name", "params"), REPORTS, ids=IDS)
def test_pdf_shows_the_same_numbers_as_the_json(
    api: TestClient, people: People, world: World, name: str, params: dict
) -> None:
    data = fetch(api, people.admin, name, params).json()
    resp = fetch(api, people.admin, name, params, "pdf")
    assert resp.status_code == 200 and resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    text = pdf_text(resp.content)
    words = set(re.findall(r"\S+", text))
    report = Report.model_validate(data)

    for line in (report.title, report.period, f"Scope: {report.scope.label}", footer_text(report)):
        assert all(w in words for w in line.split()), line
    for entry in report.summary:
        assert entry.label.split()[0] in words
    for section in report.sections:
        assert section.title.split()[0] in words
        for row in section.rows:
            for column in section.columns:
                shown = display(row.get(column.key), column.type)
                missing = [w for w in shown.split() if w not in words]
                assert not missing, (section.key, column.key, shown, missing)
        if not section.rows:
            assert "No data for this period." in text.replace("\n", " ")


# ---------- response headers ----------


def test_download_headers(api: TestClient, people: People, world: World) -> None:
    month = fetch(api, people.admin, "monthly-activity", {"month": "2026-10"}, "xlsx")
    assert month.headers["content-disposition"] == (
        'attachment; filename="lasrra-monthly-activity-october-2026.xlsx"'
    )
    assert month.headers["cache-control"] == "no-store"
    snapshot = fetch(api, people.admin, "open-tickets", {}, "pdf")
    assert snapshot.headers["content-disposition"] == (
        'attachment; filename="lasrra-open-tickets-2026-11-10.pdf"'
    )
    ranged = fetch(
        api, people.admin, "turnaround", {"from": "2026-10-01", "to": "2026-10-31"}, "pdf"
    )
    assert (
        "lasrra-turnaround-01-oct-2026-to-31-oct-2026.pdf" in ranged.headers["content-disposition"]
    )


def test_json_is_the_default_and_other_formats_are_rejected(
    api: TestClient, people: People, world: World
) -> None:
    default = api.get(f"{API}/open-tickets", headers=bearer(people.admin))
    assert default.headers["content-type"].startswith("application/json")
    assert api.get(f"{API}/open-tickets", headers=bearer(people.admin),
                   params={"format": "docx"}).status_code == 422  # fmt: skip
    assert api.get(f"{API}/open-tickets", params={"format": "xlsx"}).status_code == 401


# ---------- scoping ----------


@pytest.mark.parametrize(("name", "params"), REPORTS, ids=IDS)
@pytest.mark.parametrize("fmt", ["json", "xlsx", "pdf"])
def test_a_unit_rep_never_receives_another_units_figures(
    api: TestClient, people: People, world: World, name: str, params: dict, fmt: str
) -> None:
    other_unit = {"unit_id": str(people.unit_b.id)}  # a unit rep cannot widen the report
    resp = fetch(api, people.rep_a, name, {**params, **other_unit}, fmt)
    assert resp.status_code == 200
    if fmt == "json":
        text = resp.text
    elif fmt == "xlsx":
        wb = xlsx_workbook(resp.content)
        text = " ".join(str(c.value) for ws in wb for row in ws.iter_rows() for c in row if c.value)
    else:
        text = pdf_text(resp.content)
    assert "Unit A" in text or name == "repeat-faults"
    for leaked in (
        "Unit B",
        "QuickTech",
        *(world.devices[k].asset_tag for k in ("b1", "b2", "b3", "s1")),
    ):
        assert leaked not in text, f"{leaked} leaked into the {fmt} of {name}"
    assert world.tickets["t4"].ticket_no not in text and world.tickets["t6"].ticket_no not in text


def test_staff_can_narrow_a_report_to_one_unit(
    api: TestClient, people: People, world: World
) -> None:
    rep = fetch(api, people.engineer, "monthly-activity",
                {"month": "2026-10", "unit_id": str(people.unit_b.id)}).json()  # fmt: skip
    assert rep["scope"]["label"] == "Unit B"
    rows = [r["unit"] for r in rep["sections"][0]["rows"]]
    assert rows == ["Unit B"]
    assert rep["sections"][0]["totals"]["received"] == 1
    missing = fetch(api, people.engineer, "open-tickets",
                    {"unit_id": "00000000-0000-0000-0000-000000000099"})  # fmt: skip
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "UNIT_NOT_FOUND")


@pytest.mark.parametrize("user", ["admin", "engineer", "auditor"])
def test_every_staff_role_can_export(
    api: TestClient, people: People, world: World, user: str
) -> None:
    for fmt in ("xlsx", "pdf"):
        assert fetch(api, getattr(people, user), "open-tickets", {}, fmt).status_code == 200


# ---------- safety: user text in cells ----------


@pytest.fixture
def hostile(db, people: People, world: World):
    """Two kinds of device whose names try to be a spreadsheet formula and PDF markup."""
    eng = people.engineer
    unit = people.unit_a.id

    def log(device, event_type, status, when, **kw):
        make_event(db, device, eng, event_type=event_type, to_status=status,
                   occurred_at=when, unit_id=unit, **kw)  # fmt: skip

    kinds = ('=HYPERLINK("http://evil.example","click")', "<b>Bold</b> & <i>Co</i> <unclosed")
    for index, kind in enumerate(kinds):
        device = make_device(db, eng, unit_id=unit, status=DeviceStatus.assigned, device_type=kind)
        day = 14 + index
        log(device, EventType.received_for_repair, DeviceStatus.received_for_repair,
            at(10, day, 9), counterparty_name="Ada")  # fmt: skip
        log(device, EventType.repair_started, DeviceStatus.in_repair, at(10, day, 10))
        log(device, EventType.returned_to_unit, DeviceStatus.assigned, at(10, day + 2, 9),
            counterparty_name="Ada")  # fmt: skip
    db.commit()


def test_user_text_can_never_run_as_a_formula(api: TestClient, people: People, hostile) -> None:
    for name, params in (REPORTS[0], REPORTS[2]):
        wb = xlsx_workbook(fetch(api, people.admin, name, params, "xlsx").content)
        cells = [c for ws in wb for row in ws.iter_rows() for c in row if c.value is not None]
        assert not [c for c in cells if c.data_type == "f"], name  # no formula anywhere
        evil = [c for c in cells if str(c.value).startswith("=HYPERLINK")]
        assert evil and all(c.data_type == "s" for c in evil)


def test_user_text_is_drawn_literally_in_pdfs(api: TestClient, people: People, hostile) -> None:
    resp = fetch(api, people.admin, "turnaround", {"from": "2026-10-01", "to": "2026-10-31"}, "pdf")
    assert resp.status_code == 200
    text = pdf_text(resp.content)
    assert (
        "<b>Bold</b>" in text and "&" in text and "<unclosed" in text
    )  # not interpreted as markup


def test_names_with_accents_survive_the_exports(
    api: TestClient, people: People, db, world: World
) -> None:
    name = "Ọlá Ẹlẹ́gbẹ́ Unit"
    people.unit_a.name = name
    db.commit()
    xlsx = xlsx_workbook(fetch(api, people.admin, "open-tickets", {}, "xlsx").content)
    assert any(c.value == name for row in xlsx["By unit and priority"].iter_rows() for c in row)
    pdf = fetch(api, people.admin, "open-tickets", {}, "pdf")
    assert pdf.status_code == 200  # never fails, even without a Unicode font
    if fonts()[2]:  # DejaVu (Docker) or Arial (macOS) found: the real characters are kept
        assert name in pdf_text(pdf.content)


# ---------- empty and bounded ----------


@pytest.mark.parametrize("fmt", ["xlsx", "pdf"])
def test_an_empty_period_still_exports(
    api: TestClient, people: People, world: World, fmt: str
) -> None:
    resp = fetch(api, people.admin, "turnaround", {"from": "2025-01-01", "to": "2025-01-31"}, fmt)
    assert resp.status_code == 200
    if fmt == "xlsx":
        assert xlsx_workbook(resp.content)["Repairs returned in the period"]["A5"].value == (
            "No data for this period."
        )
    else:
        assert "No data for this period." in pdf_text(resp.content).replace("\n", " ")


@pytest.mark.parametrize(("name", "params"), REPORTS, ids=IDS)
def test_reports_use_a_fixed_number_of_queries(
    api: TestClient, people: People, db, world: World, name: str, params: dict
) -> None:
    engine = db.get_bind().engine
    statements: list[str] = []

    def record(conn, cursor, statement, *args):
        statements.append(statement)

    fetch(api, people.admin, name, params)  # warm-up (opens the test savepoint)
    event.listen(engine, "before_cursor_execute", record)
    try:
        assert fetch(api, people.admin, name, params).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert len(statements) <= 30, len(statements)
