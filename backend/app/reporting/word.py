"""Word reports, on an uploaded organisation template or a clean built-in layout.

Template convention (documented in docs/operations.md): the .docx may contain
`{{ title }}`, `{{ subtitle }}` and `{{ report_date }}` anywhere (cover,
header, footer), and must contain a paragraph with only `{{p body }}` where
the report content goes. Everything else in the template (logo, styles,
cover, header, footer) is kept as designed.
"""

import io
from pathlib import Path
from typing import Any

import pandas as pd
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from docxtpl import DocxTemplate

from app.reporting.documents import ReportDocument, TableBlock, format_value

NAVY = RGBColor(0x1F, 0x38, 0x64)


class TemplateError(Exception):
    pass


def _add_table(container: Any, block: TableBlock) -> None:
    frame = block.frame if block.max_rows is None else block.frame.head(block.max_rows)
    columns = [str(c) for c in frame.columns]
    table = container.add_table(rows=1, cols=len(columns))
    table.style = "Table Grid"
    for j, name in enumerate(columns):
        cell = table.rows[0].cells[j]
        cell.text = name
        for run in cell.paragraphs[0].runs:
            run.bold = True
    numeric = {
        c for c in columns if block.formats.get(c) in ("money", "number", "integer", "percent")
    }
    for record in frame.itertuples(index=False):
        cells = table.add_row().cells
        for j, value in enumerate(record):
            cells[j].text = format_value(value, block.formats.get(columns[j], "text"))
            if columns[j] in numeric:
                cells[j].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    if block.total_row and len(frame):
        cells = table.add_row().cells
        cells[0].text = "Total"
        for j, name in enumerate(columns[1:], start=1):
            if block.formats.get(name) in ("money", "number", "integer"):
                total = block.frame[name].sum()
                cells[j].text = format_value(total, block.formats[name])
                cells[j].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for cell in cells:
            for run in cell.paragraphs[0].runs:
                run.bold = True
    if block.max_rows is not None and len(block.frame) > block.max_rows:
        container.add_paragraph(
            f"Showing the first {block.max_rows} of {len(block.frame)} lines; "
            "the full list is in the Excel workbook."
        ).runs[0].italic = True


def _fill(container: Any, document: ReportDocument) -> None:
    for section in document.sections:
        container.add_heading(section.heading, level=1)
        for paragraph in section.paragraphs:
            container.add_paragraph(paragraph)
        for bullet in section.bullets:
            container.add_paragraph(bullet, style="List Bullet")
        for block in section.tables:
            caption = container.add_paragraph(block.title)
            caption.runs[0].bold = True
            _add_table(container, block)
            container.add_paragraph("")
    if document.checks:
        container.add_heading("Report checks", level=1)
        checks = TableBlock(
            "Checks",
            frame=pd.DataFrame(
                [
                    {
                        "Check": c.label,
                        "Expected": c.expected,
                        "Actual": c.actual,
                        "Result": "Passed" if c.passed else "Failed",
                    }
                    for c in document.checks
                ]
            ),
            formats={"Expected": "number", "Actual": "number"},
        )
        _add_table(container, checks)


def build_docx(document: ReportDocument, template: Path | None = None) -> bytes:
    buffer = io.BytesIO()
    if template is None:
        doc = Document()
        doc.styles["Normal"].font.name = "Calibri"
        doc.styles["Normal"].font.size = Pt(11)
        title = doc.add_heading(document.title, level=0)
        title.runs[0].font.color.rgb = NAVY
        doc.add_paragraph(document.subtitle).runs[0].italic = True
        doc.add_paragraph(document.date_text)
        _fill(doc, document)
        doc.save(buffer)
        return buffer.getvalue()

    tpl = DocxTemplate(str(template))
    variables = tpl.get_undeclared_template_variables()
    if "body" not in variables:
        raise TemplateError(
            "The Word template has no {{p body }} placeholder for the report content."
        )
    body = tpl.new_subdoc()
    _fill(body, document)
    tpl.render(
        {
            "title": document.title,
            "subtitle": document.subtitle,
            "report_date": document.date_text,
            "body": body,
        }
    )
    tpl.save(buffer)
    return buffer.getvalue()
