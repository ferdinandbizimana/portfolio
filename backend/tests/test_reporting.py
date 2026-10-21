import io
from pathlib import Path

import pandas as pd
import pytest
from docx import Document

from app.reporting.documents import ReportDocument, Section, TableBlock, format_value
from app.reporting.guard import (
    BannedWordingError,
    check_report,
    docx_texts,
    find_banned,
    pptx_texts,
)
from app.reporting.slides import build_pptx
from app.reporting.word import TemplateError, build_docx

DOC = ReportDocument(
    title="Stock report",
    subtitle="Fake data",
    date_text="30 June 2026",
    sections=[
        Section(
            "Summary",
            paragraphs=["Total stock is RWF 1,000."],
            tables=[
                TableBlock(
                    "By plant",
                    pd.DataFrame({"Plant": ["P1", "P2"], "Value": [600.0, 400.0]}),
                    {"Value": "money"},
                    total_row=True,
                )
            ],
        )
    ],
)


def test_banned_wording_is_found() -> None:
    assert find_banned(["Prepared with AI support"])
    assert find_banned(["Amount To Be Confirmed later"])
    assert find_banned(["AID kit", "Kigali", "maintain", "the ai word in lower case"]) == []


def test_values_are_formatted_for_reports() -> None:
    assert format_value(-1234.4, "money") == "(1,234)"
    assert format_value(0.0891, "percent") == "8.9%"
    assert format_value(None, "money") == ""


def test_word_report_without_template() -> None:
    content = build_docx(DOC)
    texts = docx_texts(content)
    assert "Stock report" in texts
    assert "Total" in texts and "1,000" in texts  # total row of the table
    check_report("docx", content)


def _template(tmp_path: Path, body: str) -> Path:
    document = Document()
    document.add_paragraph("RMS LETTERHEAD")
    document.add_paragraph("{{ title }} - {{ report_date }}")
    document.add_paragraph(body)
    document.add_paragraph("End of template")
    path = tmp_path / "template.docx"
    document.save(str(path))
    return path


def test_word_report_on_an_organisation_template(tmp_path: Path) -> None:
    content = build_docx(DOC, _template(tmp_path, "{{p body }}"))
    texts = docx_texts(content)
    assert texts[0] == "RMS LETTERHEAD"
    assert "Stock report - 30 June 2026" in texts
    assert "Total stock is RWF 1,000." in texts
    assert texts[-1] == "End of template" or "End of template" in texts


def test_word_template_without_body_placeholder_is_refused(tmp_path: Path) -> None:
    with pytest.raises(TemplateError, match="body"):
        build_docx(DOC, _template(tmp_path, "no placeholder here"))


def test_powerpoint_deck() -> None:
    content = build_pptx(DOC)
    texts = pptx_texts(content)
    assert "Stock report" in texts
    assert "By plant" in texts
    check_report("pptx", content)


def test_guard_rejects_a_report_with_banned_wording() -> None:
    bad = ReportDocument("Plan", "AI generated summary", "30 June 2026", sections=[])
    with pytest.raises(BannedWordingError, match="AI"):
        check_report("docx", build_docx(bad))
    buffer = io.BytesIO(build_pptx(bad))
    with pytest.raises(BannedWordingError):
        check_report("pptx", buffer.getvalue())


def test_long_dashboard_tables_are_capped() -> None:
    from app.analyses.dashboard import MAX_DASHBOARD_ROWS, Column, Dashboard, Table
    from app.jobs.analysis import cap_dashboard

    rows = [{"n": i} for i in range(MAX_DASHBOARD_ROWS + 10)]
    dashboard = Dashboard(
        title="t",
        tables=[Table(id="x", title="x", columns=[Column(key="n", label="n")], rows=rows)],
    )
    capped = cap_dashboard(dashboard).tables[0]
    assert len(capped.rows) == MAX_DASHBOARD_ROWS
    assert "All lines are in the Excel workbook" in capped.note
    assert len(dashboard.tables[0].rows) == MAX_DASHBOARD_ROWS + 10  # original untouched


def test_excel_sheet_row_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    import io as _io

    from openpyxl import load_workbook

    from app.reporting import excel

    monkeypatch.setattr(excel, "EXCEL_MAX_ROWS", 20)
    frame = pd.DataFrame({"n": range(50)})
    content = excel.build_workbook("t", "s", [], [TableBlock("Lines", frame)], [])
    sheet = load_workbook(_io.BytesIO(content))["Lines"]
    assert "showing the first 15 of 50" in str(sheet["A3"].value)
    assert sheet.max_row <= 20
