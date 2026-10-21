"""Fake sample files built in code (no real data, nothing committed as a file)."""

import io
from datetime import date
from typing import Any

from openpyxl import Workbook

DEMO_HEADERS = ["Plant", "Material", "Material Description", "Quantity", "Value"]

DEMO_ROWS: list[list[Any]] = [
    ["P100", "M-0001", "Gloves, nitrile, medium", 1200, 360000],
    ["P100", "M-0002", "Syringe 5 ml", 5000, 250000.5],
    ["P200", "M-0001", "Gloves, nitrile, medium", 300, 90000],
    ["P200", "M-0003", "Test kit", -2, -15000],
    ["P300", "M-0004", None, 10, 1000],
]


def demo_workbook(
    rows: list[list[Any]] | None = None,
    headers: list[str] | None = None,
    title_rows: int = 2,
    sheet: str = "Stock",
) -> bytes:
    """An Excel file shaped like an SAP export: title lines, then the header row."""
    workbook = Workbook()
    ws = workbook.active
    assert ws is not None
    ws.title = sheet
    for i in range(title_rows):
        ws.append([f"Stock list - fake demo data, line {i + 1}"])
    ws.append(headers or DEMO_HEADERS)
    for row in rows if rows is not None else DEMO_ROWS:
        ws.append(row)
    ws.append([])  # trailing blank line
    notes = workbook.create_sheet("Notes")
    notes.append(["Prepared on", date(2026, 7, 1)])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def demo_csv(separator: str = ";", encoding: str = "utf-8") -> bytes:
    lines = [separator.join(DEMO_HEADERS)]
    for row in DEMO_ROWS:
        lines.append(separator.join("" if v is None else str(v) for v in row))
    return ("\n".join(lines) + "\n").encode(encoding)
