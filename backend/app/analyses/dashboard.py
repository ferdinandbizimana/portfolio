"""The dashboard description an analysis returns; the frontend renders it.

Everything here is plain JSON-able data, so a dashboard can be stored with a
run and, in Phase 6, frozen into a published snapshot. Tables carry a detail
`level` so publishing can drop line-level detail.
"""

import math
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

ValueFormat = Literal["number", "integer", "money", "percent", "text", "date"]

# Dashboards are stored with each run and sent to the browser, so long tables
# keep only their first rows; the full table is in the run and the workbook.
MAX_DASHBOARD_ROWS = 20_000
DetailLevel = Literal["summary", "detail"]


class Kpi(BaseModel):
    label: str
    value: float | int | str | None
    format: ValueFormat = "number"
    unit: str = ""
    note: str = ""


class Column(BaseModel):
    key: str
    label: str
    format: ValueFormat = "text"


class Table(BaseModel):
    id: str
    title: str
    columns: list[Column]
    rows: list[dict[str, Any]]
    level: DetailLevel = "summary"
    total_rows: int | None = None  # set when `rows` holds only the first lines
    # Columns offered as filter drop-downs and included in the search box.
    filters: list[str] = Field(default_factory=list)
    searchable: list[str] = Field(default_factory=list)
    note: str = ""


class Series(BaseModel):
    name: str
    field: str


class Chart(BaseModel):
    id: str
    title: str
    type: Literal["bar", "column", "line", "pie", "stacked-bar"]
    table: str  # id of the table holding the data
    category: str  # field used for the categories (x axis or slices)
    series: list[Series]
    format: ValueFormat = "number"
    limit: int | None = None  # show only the first N categories


class CheckOut(BaseModel):
    key: str
    label: str
    expected: float
    actual: float
    tolerance: float
    passed: bool
    description: str = ""


class Dashboard(BaseModel):
    title: str
    subtitle: str = ""
    kpis: list[Kpi] = Field(default_factory=list)
    charts: list[Chart] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    checks: list[CheckOut] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _json_value(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat() if value == value.normalize() else value.isoformat()
    if hasattr(value, "item"):  # numpy scalar
        return _json_value(value.item())
    return value


def rows_of(frame: pd.DataFrame, limit: int = MAX_DASHBOARD_ROWS) -> list[dict[str, Any]]:
    """The first `limit` DataFrame rows as JSON-safe dictionaries."""
    return [
        {str(k): _json_value(v) for k, v in record.items()}
        for record in frame.head(limit).to_dict(orient="records")
    ]
