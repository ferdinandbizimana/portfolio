"""Standard downloads for any run: an Excel workbook and an HTML dashboard.

Every analysis gives at least these two files (Ferdinand, 26 October 2026). An
analysis with its own layout builds them itself; for one that does not, the
engine builds them here from the result tables, the key figures and the checks.
"""

from typing import Any

import pandas as pd

from app.reporting.documents import ReportFile, TableBlock, check_lines
from app.reporting.excel import build_workbook
from app.reporting.interactive import (
    DashSection,
    DetailSpec,
    Filter,
    Fmt,
    InteractiveDashboard,
    Measure,
    build_html,
)

MAX_FILTERS = 6
MAX_FILTER_VALUES = 60


def _title(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


def _format(series: pd.Series) -> Fmt:
    if pd.api.types.is_bool_dtype(series) or not pd.api.types.is_numeric_dtype(series):
        return "text"
    values = series.dropna()
    return "int" if len(values) and bool((values == values.round()).all()) else "num"


def _value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _filters(tables: dict[str, pd.DataFrame]) -> tuple[Filter, ...]:
    """Text columns of the largest table with a few distinct values."""
    if not tables:
        return ()
    largest = max(tables.values(), key=len)
    filters = []
    for column in largest.columns:
        series = largest[column]
        if _format(series) != "text":
            continue
        distinct = series.dropna().astype(str).nunique()
        if 1 < distinct <= MAX_FILTER_VALUES:
            filters.append(Filter(str(column), str(column), "All"))
        if len(filters) == MAX_FILTERS:
            break
    return tuple(filters)


def standard_dashboard(
    title: str,
    subtitle: str,
    tables: dict[str, pd.DataFrame],
    metrics: list[Any],
    checks: list[tuple[str, float, float, bool]],
) -> InteractiveDashboard:
    facts: dict[str, pd.DataFrame] = {}
    sections: list[DashSection] = []
    if metrics:
        facts["key_figures"] = pd.DataFrame(
            {
                "Figure": [m.label for m in metrics],
                "Value": [_value(m.value) for m in metrics],
                "Note": [getattr(m, "note", "") or "" for m in metrics],
            }
        )
        sections.append(
            DashSection(
                "Key figures",
                blocks=(
                    DetailSpec(
                        "Key figures",
                        "key_figures",
                        (
                            ("Figure", "Figure", "text"),
                            ("Value", "Value", "text"),
                            ("Note", "Note", "text"),
                        ),
                    ),
                ),
            )
        )
    for name, frame in tables.items():
        if frame.empty:
            continue
        frame = frame.reset_index(drop=True)
        frame.columns = [str(c) for c in frame.columns]
        key = f"t{len(facts)}"
        facts[key] = frame
        sections.append(
            DashSection(
                _title(name),
                blocks=(
                    DetailSpec(
                        _title(name),
                        key,
                        tuple((str(c), str(c), _format(frame[c])) for c in frame.columns),
                    ),
                ),
            )
        )
    return InteractiveDashboard(
        title=title,
        subtitle=subtitle,
        intro="Every table of this run; filters at the top, search and CSV download per table.",
        facts=facts,
        measures={key: (Measure("rows", "Rows", count=True),) for key in facts},
        filters=_filters({k: v for k, v in facts.items() if k != "key_figures"}),
        kpis=(),
        sections=tuple(sections),
        footer=f"Rwanda Medical Supply · {title}.",
        checks=checks,
    )


def ensure_downloads(
    reports: list[ReportFile],
    *,
    title: str,
    subtitle: str,
    name: str,
    tables: dict[str, pd.DataFrame],
    metrics: list[Any],
    checks: list[Any],
) -> list[ReportFile]:
    """The reports, plus a standard workbook and dashboard when either is missing."""
    kinds = {r.kind for r in reports}
    check_tuples = [(c.label, float(c.expected), float(c.actual), bool(c.passed)) for c in checks]
    extra: list[ReportFile] = []
    if "xlsx" not in kinds:
        extra.append(
            ReportFile(
                "workbook",
                "Excel workbook",
                f"{name}.xlsx",
                "xlsx",
                build_workbook(
                    title,
                    subtitle,
                    [(m.label, m.value, m.format) for m in metrics],
                    [TableBlock(_title(n), f) for n, f in tables.items() if not f.empty],
                    check_lines(checks),
                ),
            )
        )
    if "html" not in kinds:
        extra.append(
            ReportFile(
                "dashboard",
                "Interactive dashboard (HTML)",
                f"{name}.html",
                "html",
                build_html(standard_dashboard(title, subtitle, tables, metrics, check_tuples)),
            )
        )
    return [*reports, *extra]
