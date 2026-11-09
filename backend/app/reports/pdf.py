"""PDF export (ReportLab): landscape A4, one table per section, footer on every page."""

import unicodedata
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.reports.format import display, footer_text, headline, summary_display
from app.schemas.reports import Column, Report, Section

PDF_TYPE = "application/pdf"
NAVY = colors.HexColor("#1F3A5F")
STRIPE = colors.HexColor("#F2F5F9")

# Unicode fonts that cover names such as "Ọlá Adéṣọlá". The standard PDF fonts do not.
FONT_CANDIDATES = [
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Debian/Ubuntu: fonts-dejavu-core
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
]


@lru_cache
def fonts() -> tuple[str, str, bool]:
    """(regular, bold, supports_unicode). Falls back to Helvetica with accents simplified."""
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).is_file() and Path(bold).is_file():
            pdfmetrics.registerFont(TTFont("ReportFont", regular))
            pdfmetrics.registerFont(TTFont("ReportFont-Bold", bold))
            return "ReportFont", "ReportFont-Bold", True
    return "Helvetica", "Helvetica-Bold", False


def _plain(value: str) -> str:
    """Without a Unicode font, replace what the standard fonts cannot draw (Ọ becomes O)."""
    if not fonts()[2]:
        try:
            value.encode("cp1252")
        except UnicodeEncodeError:
            decomposed = unicodedata.normalize("NFKD", value)
            value = "".join(c for c in decomposed if not unicodedata.combining(c))
            value = value.encode("ascii", "replace").decode("ascii")
    return value


def _text(value: str) -> str:
    """Text for a Paragraph, which reads ReportLab's mini-markup: `<` and `&` must be escaped."""
    return escape(_plain(value))


def _style(name: str, **kw) -> ParagraphStyle:
    regular, bold, _ = fonts()
    kw.setdefault("fontName", bold if kw.pop("bold", False) else regular)
    return ParagraphStyle(name, **kw)


def _column_widths(columns: list[Column], section: Section, total: float) -> list[float]:
    weights = []
    for column in columns:
        cells = [display(r.get(column.key), column.type) for r in section.rows]
        # Never narrower than the longest word of the heading, so headings do not break mid-word.
        heading_word = max(len(word) for word in column.label.split()) * 1.15
        longest = max([len(c) for c in cells] + [heading_word, 4])
        weights.append(min(max(longest, 6), 40))
    scale = total / sum(weights)
    return [w * scale for w in weights]


def _table(section: Section, width: float) -> Table:
    body = _style("cell", fontSize=8, leading=10)
    right = _style("cell-right", fontSize=8, leading=10, alignment=TA_RIGHT)
    head = _style("head", fontSize=8, leading=10, bold=True, textColor=colors.white)
    head_right = _style("head-right", fontSize=8, leading=10, bold=True, textColor=colors.white,
                        alignment=TA_RIGHT)  # fmt: skip
    strong = _style("total", fontSize=8, leading=10, bold=True)
    strong_right = _style("total-right", fontSize=8, leading=10, bold=True, alignment=TA_RIGHT)

    def numeric(column: Column) -> bool:
        return column.type in ("int", "number")

    data = [
        [Paragraph(_text(c.label), head_right if numeric(c) else head) for c in section.columns]
    ]
    for row in section.rows:
        data.append(
            [
                Paragraph(_text(display(row.get(c.key), c.type)), right if numeric(c) else body)
                for c in section.columns
            ]
        )
    if section.totals:
        data.append(
            [
                Paragraph(
                    _text(display(section.totals.get(c.key), c.type)),
                    strong_right if numeric(c) else strong,
                )
                for c in section.columns
            ]
        )
    table = Table(
        data, colWidths=_column_widths(section.columns, section, width), repeatRows=1, hAlign="LEFT"
    )
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#D5DBE3")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, len(section.rows)), [colors.white, STRIPE]),
    ]
    if section.totals:
        commands.append(("LINEABOVE", (0, -1), (-1, -1), 1, NAVY))
    table.setStyle(TableStyle(commands))
    return table


def render_pdf(report: Report) -> bytes:
    regular, _, _ = fonts()
    page = landscape(A4)
    margin = 14 * mm
    width = page[0] - 2 * margin
    footer = footer_text(report)

    title_style = _style("title", fontSize=18, leading=22, bold=True, textColor=NAVY)
    meta_style = _style("meta", fontSize=10, leading=13, textColor=colors.HexColor("#444444"))
    heading = _style("heading", fontSize=12, leading=15, bold=True, textColor=NAVY, spaceBefore=14)
    note_style = _style("note", fontSize=8, leading=10, textColor=colors.HexColor("#555555"))
    empty_style = _style("empty", fontSize=9, leading=12, textColor=colors.HexColor("#555555"))

    title, period, scope = headline(report)
    story = [
        Paragraph(_text(title), title_style),
        Paragraph(_text(period), meta_style),
        Paragraph(_text(scope), meta_style),
        Spacer(1, 8),
    ]
    summary = Section(
        key="summary",
        title="Summary",
        columns=[
            Column(key="label", label="Measure"),
            Column(key="value", label="Value", type="text"),
        ],
        rows=[{"label": e.label, "value": summary_display(e.value)} for e in report.summary],
    )
    story.append(Paragraph("Summary", heading))
    story.append(_table(summary, width * 0.45))
    for section in report.sections:
        story.append(Paragraph(_text(section.title), heading))
        if section.note:
            story.append(Paragraph(_text(section.note), note_style))
            story.append(Spacer(1, 3))
        if section.rows:
            story.append(_table(section, width))
        else:
            story.append(Paragraph("No data for this period.", empty_style))

    def draw_footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont(regular, 8)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(margin, 8 * mm, _plain(footer))
        canvas.drawRightString(page[0] - margin, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=16 * mm,
        title=report.title,
        author=report.generated_by.full_name,
    )
    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return buffer.getvalue()
