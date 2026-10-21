"""A simple description of a report, turned into Word and PowerPoint by the builders."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

import pandas as pd

ValueFormat = Literal["number", "integer", "money", "percent", "text", "date"]


@dataclass(frozen=True)
class ReportFile:
    key: str  # stable id, e.g. "workbook"
    title: str  # shown on the download button
    filename: str
    kind: Literal["xlsx", "docx", "pptx"]
    content: bytes


@dataclass(frozen=True)
class Templates:
    """Organisation templates chosen in the admin area (None = built-in layout)."""

    docx: Path | None = None
    pptx: Path | None = None


@dataclass
class TableBlock:
    title: str
    frame: pd.DataFrame
    formats: dict[str, ValueFormat] = field(default_factory=dict)
    total_row: bool = False
    max_rows: int | None = None  # Word/PowerPoint show at most this many rows


@dataclass
class ChartBlock:
    title: str
    categories: list[str]
    series: dict[str, list[float]]
    kind: Literal["bar", "column", "pie"] = "bar"


@dataclass
class Section:
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    tables: list[TableBlock] = field(default_factory=list)
    charts: list[ChartBlock] = field(default_factory=list)


@dataclass
class CheckLine:
    label: str
    expected: float
    actual: float
    passed: bool


@dataclass
class ReportDocument:
    title: str
    subtitle: str
    date_text: str  # the reporting date, written out (never "today")
    sections: list[Section]
    checks: list[CheckLine] = field(default_factory=list)


def format_value(value: object, value_format: ValueFormat) -> str:
    """A value as text for Word and PowerPoint tables."""
    if value is None or value is pd.NA or (isinstance(value, float) and pd.isna(value)):
        return ""
    if value_format in ("number", "money") and isinstance(value, int | float):
        text = f"{abs(value):,.0f}" if value_format == "money" else f"{abs(value):,.2f}"
        return f"({text})" if value < 0 else text
    if value_format == "integer" and isinstance(value, int | float):
        return f"{value:,.0f}"
    if value_format == "percent" and isinstance(value, int | float):
        return f"{value * 100:.1f}%"
    if value_format == "date" and isinstance(value, pd.Timestamp):
        return value.strftime("%d %b %Y")
    return str(value)


class _CheckLike(Protocol):
    label: str
    expected: float
    actual: float

    @property
    def passed(self) -> bool: ...


def check_lines(checks: Sequence[_CheckLike]) -> list[CheckLine]:
    """Convert analysis checks for the report builders."""
    return [CheckLine(c.label, c.expected, c.actual, c.passed) for c in checks]
