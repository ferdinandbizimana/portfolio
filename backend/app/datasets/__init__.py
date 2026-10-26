"""Datasets: the kinds of input file the analyses understand.

A dataset (for example "OX10 plant list") is defined once, with the exact
column headers of the SAP export and the type of each column. Several
analyses can use the same dataset. Uploaded sheets are matched to datasets by
their headers, and the values are converted to the declared types with clear
messages for anything that does not fit.

Never invent a column name here: headers must come from real exports
(described by Ferdinand), see CLAUDE.md.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

ColumnType = Literal["text", "number", "integer", "date"]


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    type: ColumnType = "text"
    required: bool = True
    # Other headers that mean the same column (e.g. a different SAP layout).
    aliases: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    title: str
    description: str
    columns: tuple[ColumnSpec, ...]
    # Sheet names that usually hold this dataset; used to break ties.
    sheet_hints: tuple[str, ...] = ()
    demo: bool = False

    def column(self, name: str) -> ColumnSpec:
        return next(c for c in self.columns if c.name == name)


@dataclass
class ValidationIssue:
    column: str
    message: str
    row: int | None = None  # 1-based row number in the sheet, header row included

    def text(self, file: str, sheet: str) -> str:
        where = f"{file}, sheet {sheet!r}"
        if self.row is not None:
            where += f", row {self.row}"
        return f"{where}, column {self.column!r}: {self.message}"


@dataclass
class Coerced:
    frame: pd.DataFrame
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


_REGISTRY: dict[str, DatasetSpec] = {}

DAY_FIRST = ("%d.%m.%Y", "%d/%m/%Y", "%d.%m.%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S")
MONTH_FIRST = ("%d.%m.%Y", "%m/%d/%Y", "%d.%m.%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S")
SLASH_DATE = r"^(\d{1,2})/(\d{1,2})/\d{4}"
ALL_SHEETS = "*"  # the input takes every recognised sheet of the file


def recognised_sheets(sheets: list[dict[str, Any]], dataset: str) -> list[str]:
    """Names of the sheets recognised as the dataset, in workbook order."""
    return [
        str(s["name"])
        for s in sheets
        if any(m.get("dataset") == dataset for m in s.get("matches", []))
    ]


def register(spec: DatasetSpec) -> DatasetSpec:
    if spec.key in _REGISTRY:
        raise ValueError(f"Dataset {spec.key!r} is defined twice.")
    _REGISTRY[spec.key] = spec
    return spec


def get(key: str) -> DatasetSpec:
    _load_definitions()
    return _REGISTRY[key]


def all_datasets() -> list[DatasetSpec]:
    _load_definitions()
    return sorted(_REGISTRY.values(), key=lambda s: s.title)


def _load_definitions() -> None:
    # Importing the definitions module registers every dataset.
    from app.datasets import definitions  # noqa: F401


def normalise_header(value: str) -> str:
    """Compare headers ignoring case, spaces and punctuation differences."""
    return re.sub(r"[^0-9a-z]+", " ", value.lower()).strip()


def _header_map(spec: DatasetSpec, headers: list[str]) -> dict[str, str]:
    """Spec column name -> actual header in the sheet, for the columns found."""
    by_norm = {normalise_header(h): h for h in headers}
    found: dict[str, str] = {}
    for column in spec.columns:
        for candidate in (column.name, *column.aliases):
            actual = by_norm.get(normalise_header(candidate))
            if actual is not None:
                found[column.name] = actual
                break
    return found


@dataclass
class Match:
    dataset: str
    title: str
    missing: list[str]
    score: float
    required: int = 0  # number of required columns, all found


def match_sheet(headers: list[str], sheet_name: str) -> list[Match]:
    """Datasets whose required columns all appear in the headers, best first."""
    matches: list[Match] = []
    for spec in all_datasets():
        required = [c.name for c in spec.columns if c.required]
        found = _header_map(spec, headers)
        missing = [name for name in required if name not in found]
        if missing:
            continue
        score = len(found) / max(len(spec.columns), 1)
        if normalise_header(sheet_name) in {normalise_header(h) for h in spec.sheet_hints}:
            score += 1
        matches.append(Match(spec.key, spec.title, missing, score, len(required)))
    # The most specific dataset first: the one that needs the most of these columns.
    return sorted(matches, key=lambda m: (-m.required, -m.score, m.dataset))


def source_columns(spec: DatasetSpec, headers: list[str]) -> list[str]:
    """The sheet headers the dataset needs (in sheet order); empty if some are missing."""
    if missing_columns(spec, headers):
        return []
    wanted = set(_header_map(spec, headers).values())
    return [h for h in headers if h in wanted]


def missing_columns(spec: DatasetSpec, headers: list[str]) -> list[str]:
    found = _header_map(spec, headers)
    return [c.name for c in spec.columns if c.required and c.name not in found]


MAX_ISSUES_PER_COLUMN = 5
HEADER_ROW_OFFSET = 1  # data row i is sheet row header_row + 1 + i


def coerce(spec: DatasetSpec, raw: pd.DataFrame, header_row: int) -> Coerced:
    """Select the spec's columns from a raw (all-text) sheet and convert their types.

    The result has exactly the spec's column names, in spec order. Optional
    columns that are absent are filled with missing values.
    """
    headers = [str(c) for c in raw.columns]
    found = _header_map(spec, headers)
    issues = [
        ValidationIssue(name, "this column is missing") for name in missing_columns(spec, headers)
    ]
    if issues:
        return Coerced(pd.DataFrame(), issues)

    out: dict[str, pd.Series] = {}
    for column in spec.columns:
        if column.name not in found:
            out[column.name] = _empty(column.type, len(raw))
            continue
        values = raw[found[column.name]]
        converted, bad = _convert(values, column.type)
        for index in bad[:MAX_ISSUES_PER_COLUMN]:
            issues.append(
                ValidationIssue(
                    column.name,
                    f"{values.iloc[index]!r} is not a valid {column.type}",
                    row=header_row + HEADER_ROW_OFFSET + index,
                )
            )
        if len(bad) > MAX_ISSUES_PER_COLUMN:
            issues.append(
                ValidationIssue(
                    column.name, f"{len(bad) - MAX_ISSUES_PER_COLUMN} more values are not valid"
                )
            )
        out[column.name] = converted
    return Coerced(pd.DataFrame(out).reset_index(drop=True), issues)


def parse_dates(values: pd.Series) -> pd.Series:
    """Dates from text cells (ISO or SAP day first); NaT where a cell is not a date."""
    dates, _ = _convert(values, "date")
    return dates


def _date_formats(text: pd.Series) -> tuple[str, ...]:
    """Formats for dates that are not ISO, decided for the whole column.

    Dots are always day first (SAP: 30.06.2026). With slashes the order depends on
    the export: a first part above 12 means day first (30/06/2026), a second part
    above 12 means month first (6/30/2026, as the EWM exports of RMS). When every
    date fits both, month first is used, like those exports.
    """
    parts = text.str.extract(SLASH_DATE).dropna().astype(int)
    if parts.empty:
        return DAY_FIRST
    if (parts[0] > 12).any():
        return DAY_FIRST
    return MONTH_FIRST


def _empty(column_type: ColumnType, length: int) -> pd.Series:
    """An absent optional column, typed like a present one (all values missing)."""
    if column_type == "number":
        return pd.Series([float("nan")] * length, dtype="float64")
    if column_type == "integer":
        return pd.Series([pd.NA] * length, dtype="Int64")
    if column_type == "date":
        return pd.Series([pd.NaT] * length, dtype="datetime64[ns]")
    return pd.Series([None] * length, dtype="object")


def _convert(values: pd.Series, column_type: ColumnType) -> tuple[pd.Series, list[int]]:
    text = values.astype("string").str.strip()
    empty = text.isna() | (text == "")
    if column_type == "text":
        result = text.astype("object")
        result[empty] = None
        return result, []
    if column_type in ("number", "integer"):
        # SAP exports may use thousands separators; remove them first.
        cleaned = text.str.replace(",", "", regex=False).str.replace(" ", "", regex=False)
        # SAP shows negatives as "1234-" in some layouts.
        trailing_minus = cleaned.str.endswith("-", na=False)
        cleaned = cleaned.where(~trailing_minus, "-" + cleaned.str.rstrip("-"))
        numbers = pd.to_numeric(cleaned, errors="coerce")
        bad_mask = numbers.isna() & ~empty
        if column_type == "integer":
            bad_mask |= numbers.notna() & (numbers % 1 != 0)
            if not bad_mask.any():
                numbers = numbers.round().astype("Int64")
        return numbers, [int(i) for i in bad_mask.to_numpy().nonzero()[0]]
    dates = pd.to_datetime(text, errors="coerce", format="ISO8601")
    for day_first in _date_formats(text[dates.isna() & ~empty]):
        missing = dates.isna() & ~empty
        if not missing.any():
            break
        dates = dates.where(
            ~missing, pd.to_datetime(text.where(missing), errors="coerce", format=day_first)
        )
    bad_mask = dates.isna() & ~empty
    return dates, [int(i) for i in bad_mask.to_numpy().nonzero()[0]]
