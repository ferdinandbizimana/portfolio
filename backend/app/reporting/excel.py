"""Excel workbooks with a summary sheet, data sheets (live totals) and the checks.

Written in openpyxl's streaming (write-only) mode, so a sheet with a million
rows does not have to be held in memory.
"""

import io
import re
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.cell import Cell, WriteOnlyCell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.reporting.documents import CheckLine, TableBlock, ValueFormat

FONT = "Arial"
NAVY = "1F3864"
HEADER_FILL = PatternFill("solid", fgColor=NAVY)
HEADER_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
BODY_FONT = Font(name=FONT, size=10)
BOLD_FONT = Font(name=FONT, size=10, bold=True)
TITLE_FONT = Font(name=FONT, bold=True, size=14, color=NAVY)
SUBTITLE_FONT = Font(name=FONT, italic=True, size=9, color="595959")
WARNING_FONT = Font(name=FONT, italic=True, size=9, color="C00000")
TOTAL_FILL = PatternFill("solid", fgColor="D9E1F2")
PASS_FILL = PatternFill("solid", fgColor="E2EFDA")
FAIL_FILL = PatternFill("solid", fgColor="F8CBAD")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)

NUMBER_FORMATS: dict[ValueFormat, str] = {
    "money": "#,##0;(#,##0);-",
    "number": "#,##0.00;(#,##0.00);-",
    "integer": "#,##0",
    "percent": "0.0%",
    "date": "dd.mm.yyyy",
    "text": "General",
}

# openpyxl's write-only sheet. Its type stubs lack column_dimensions and
# auto_filter, which exist and work (checked by tests), hence Any.
Sheet = Any

EXCEL_MAX_ROWS = 1_048_576
FIRST_TABLE_ROW = 4  # rows 1-2 title, row 3 note, row 4 header


def _sheet_title(title: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", title).strip()[:31] or "Sheet"
    name, n = base, 2
    while name.lower() in used:
        suffix = f" ({n})"
        name = base[: 31 - len(suffix)] + suffix
        n += 1
    used.add(name.lower())
    return name


def _cell(
    sheet: Sheet,
    value: Any,
    font: Font = BODY_FONT,
    number_format: str | None = None,
    fill: PatternFill | None = None,
    border: Border | None = None,
    wrap: bool = False,
) -> Cell:
    cell = WriteOnlyCell(sheet, value=value)
    cell.font = font
    if number_format:
        cell.number_format = number_format
    if fill:
        cell.fill = fill
    if border:
        cell.border = border
    if wrap:
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    return cell


def _title_rows(sheet: Sheet, title: str, subtitle: str, note: str = "") -> None:
    sheet.append([_cell(sheet, title, TITLE_FONT)])
    sheet.append([_cell(sheet, subtitle, SUBTITLE_FONT)] if subtitle else [])
    sheet.append([_cell(sheet, note, WARNING_FONT)] if note else [])


def _plain(value: Any) -> Any:
    if value is pd.NA or value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if hasattr(value, "item"):  # numpy scalar
        return value.item()
    return value


def _widths(frame: pd.DataFrame) -> list[float]:
    widths: list[float] = []
    for j, name in enumerate(frame.columns):
        sample = [len(str(name))] + [len(str(v)) for v in frame.iloc[:200, j]]
        widths.append(min(max(sample) + 2, 60))
    return widths


def _table_sheet(sheet: Sheet, block: TableBlock, subtitle: str) -> None:
    frame = block.frame
    room = EXCEL_MAX_ROWS - FIRST_TABLE_ROW - 1  # header and total rows
    note = ""
    if len(frame) > room:
        note = (
            f"Excel holds at most {room:,} lines per sheet: showing the first {room:,} "
            f"of {len(frame):,}."
        )
        frame = frame.head(room)
    columns = [str(c) for c in frame.columns]
    formats = [NUMBER_FORMATS[block.formats.get(c, "text")] for c in columns]

    for j, width in enumerate(_widths(frame), start=1):
        sheet.column_dimensions[get_column_letter(j)].width = width
    sheet.freeze_panes = f"A{FIRST_TABLE_ROW + 1}"
    last = FIRST_TABLE_ROW + len(frame)
    if len(frame):
        sheet.auto_filter.ref = f"A{FIRST_TABLE_ROW}:{get_column_letter(len(columns))}{last}"

    _title_rows(sheet, block.title, subtitle, note)
    sheet.append(
        [_cell(sheet, c, HEADER_FONT, fill=HEADER_FILL, border=BORDER, wrap=True) for c in columns]
    )
    for record in frame.itertuples(index=False, name=None):
        sheet.append(
            [_cell(sheet, _plain(v), number_format=f) for v, f in zip(record, formats, strict=True)]
        )
    if block.total_row and len(frame):
        total: list[Cell] = []
        for j, name in enumerate(columns, start=1):
            value_format = block.formats.get(name, "text")
            value: Any = None
            if j == 1:
                value = "TOTAL"
            elif value_format in ("money", "number", "integer"):
                letter = get_column_letter(j)
                value = f"=SUBTOTAL(9,{letter}{FIRST_TABLE_ROW + 1}:{letter}{last})"
            total.append(
                _cell(sheet, value, BOLD_FONT, NUMBER_FORMATS[value_format], fill=TOTAL_FILL)
            )
        sheet.append(total)


def build_workbook(
    title: str,
    subtitle: str,
    summary: list[tuple[str, float | int | str | None, ValueFormat]],
    tables: list[TableBlock],
    checks: list[CheckLine],
) -> bytes:
    workbook = Workbook(write_only=True)
    used: set[str] = set()

    sheet = workbook.create_sheet(_sheet_title("Summary", used))
    sheet.column_dimensions["A"].width = 48
    sheet.column_dimensions["B"].width = 22
    _title_rows(sheet, title, subtitle)
    for label, value, value_format in summary:
        sheet.append(
            [
                _cell(sheet, label),
                _cell(sheet, _plain(value), BOLD_FONT, NUMBER_FORMATS[value_format]),
            ]
        )

    for block in tables:
        _table_sheet(workbook.create_sheet(_sheet_title(block.title, used)), block, subtitle)

    check_sheet = workbook.create_sheet(_sheet_title("Checks", used))
    check_sheet.column_dimensions["A"].width = 60
    for letter in "BCD":
        check_sheet.column_dimensions[letter].width = 20
    _title_rows(check_sheet, "Report checks", "Each check must pass before the report is used.")
    check_sheet.append(
        [
            _cell(check_sheet, h, HEADER_FONT, fill=HEADER_FILL, border=BORDER)
            for h in ("Check", "Expected", "Actual", "Result")
        ]
    )
    for check in checks:
        check_sheet.append(
            [
                _cell(check_sheet, check.label),
                _cell(check_sheet, check.expected, number_format=NUMBER_FORMATS["number"]),
                _cell(check_sheet, check.actual, number_format=NUMBER_FORMATS["number"]),
                _cell(
                    check_sheet,
                    "Passed" if check.passed else "Failed",
                    BOLD_FONT,
                    fill=PASS_FILL if check.passed else FAIL_FILL,
                ),
            ]
        )

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
