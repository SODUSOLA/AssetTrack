"""Excel export: one summary sheet and one sheet per report section."""

import re
from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.reports.format import display, footer_text, headline
from app.schemas.reports import Column, Report, Section

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HEADER_FILL = PatternFill("solid", start_color="1F3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")
NUMBER_FORMATS = {
    "int": "0",
    "number": "0.0",
    "date": "dd mmm yyyy",
    "datetime": "dd mmm yyyy hh:mm",
}


def _sheet_name(title: str, taken: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", title).strip()[:31] or "Sheet"
    name, n = base, 2
    while name.lower() in taken:
        suffix = f" {n}"
        name, n = base[: 31 - len(suffix)] + suffix, n + 1
    taken.add(name.lower())
    return name


def _put(ws: Worksheet, row: int, column: int, value, type_: str, bold: bool = False) -> None:
    """Write one cell. Text is always stored as text, so user-entered values such as
    `=HYPERLINK(...)` can never run as a formula."""
    cell = ws.cell(row=row, column=column)
    if value is None or value == "":
        cell.value = None
    elif type_ == "int":
        cell.value = int(value)
    elif type_ == "number":
        cell.value = float(value)
    elif type_ == "date":
        cell.value = date.fromisoformat(value)
    elif type_ == "datetime":
        cell.value = datetime.fromisoformat(value).replace(tzinfo=None)  # Lagos wall-clock time
    else:
        cell.value = str(value)
        cell.data_type = "s"
    if type_ in NUMBER_FORMATS:
        cell.number_format = NUMBER_FORMATS[type_]
        cell.alignment = Alignment(horizontal="right")
    if bold:
        cell.font = Font(bold=True)


def _page_setup(ws: Worksheet, footer: str) -> None:
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.oddFooter.left.text = footer
    ws.oddFooter.right.text = "Page &P of &N"


def _widths(ws: Worksheet, columns: list[Column], rows: list[dict], totals: dict | None) -> None:
    for index, column in enumerate(columns, start=1):
        cells = [column.label] + [display(r.get(column.key), column.type) for r in rows]
        if totals:
            cells.append(display(totals.get(column.key), column.type))
        ws.column_dimensions[get_column_letter(index)].width = min(
            max(len(c) for c in cells) + 2, 48
        )


def _section_sheet(wb: Workbook, section: Section, name: str, footer: str) -> None:
    ws = wb.create_sheet(name)
    ws["A1"] = section.title
    ws["A1"].font = Font(bold=True, size=13)
    if section.note:
        ws["A2"] = section.note
        ws["A2"].font = Font(italic=True, color="555555")
    header_row = 4
    for index, column in enumerate(section.columns, start=1):
        cell = ws.cell(row=header_row, column=index, value=column.label)
        cell.font, cell.fill = HEADER_FONT, HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for r, row in enumerate(section.rows, start=header_row + 1):
        for c, column in enumerate(section.columns, start=1):
            _put(ws, r, c, row.get(column.key), column.type)
    last = header_row + len(section.rows)
    if section.totals:
        last += 1
        for c, column in enumerate(section.columns, start=1):
            _put(ws, last, c, section.totals.get(column.key), column.type, bold=True)
    if not section.rows:
        ws.cell(row=header_row + 1, column=1, value="No data for this period.").font = Font(
            italic=True
        )
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    if section.rows:
        end = header_row + len(section.rows)
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(section.columns))}{end}"
    _widths(ws, section.columns, section.rows, section.totals)
    _page_setup(ws, footer)


def render_xlsx(report: Report) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    footer = footer_text(report)
    title, period, scope = headline(report)
    ws["A1"], ws["A1"].font = title, Font(bold=True, size=14)
    ws["A2"], ws["A3"], ws["A4"] = period, scope, footer
    ws["A4"].font = Font(italic=True, color="555555")
    for index, label in enumerate(("Measure", "Value"), start=1):
        cell = ws.cell(row=6, column=index, value=label)
        cell.font, cell.fill = HEADER_FONT, HEADER_FILL
    for r, entry in enumerate(report.summary, start=7):
        ws.cell(row=r, column=1, value=entry.label)
        value = ws.cell(row=r, column=2)
        if isinstance(entry.value, bool) or entry.value is None:
            value.value = entry.value
        elif isinstance(entry.value, int):
            value.value, value.number_format = entry.value, "0"
        elif isinstance(entry.value, float):
            value.value, value.number_format = entry.value, "0.0"
        else:
            value.value, value.data_type = str(entry.value), "s"
        value.alignment = Alignment(horizontal="right")
    ws.column_dimensions["A"].width = (
        max([len(e.label) for e in report.summary] + [len(footer) // 2, 30]) + 2
    )
    ws.column_dimensions["B"].width = 16
    _page_setup(ws, footer)

    taken = {"summary"}
    for section in report.sections:
        _section_sheet(wb, section, _sheet_name(section.title, taken), footer)

    wb.properties.title = report.title
    wb.properties.creator = report.generated_by.full_name
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
