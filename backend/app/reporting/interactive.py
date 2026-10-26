"""Interactive HTML dashboards: one self-contained file per run.

The analysis describes the dashboard (filters, measures, KPI tiles, charts,
tables, detail lists) over one or more "fact" tables (one row per order line,
per order, per batch ...). The file carries the facts and a small script that
aggregates them in the browser under the filters the reader picks, so the
figures always add up to the same totals as the Excel workbook. It works
offline: Chart.js and the data are inside the file; nothing is fetched.
"""

import base64
import gzip
import html
import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from importlib import resources
from typing import Any, Literal

import pandas as pd

Fmt = Literal["int", "num", "rwf", "pct", "text", "days"]


@dataclass(frozen=True)
class Measure:
    """A figure computed on any group of fact rows.

    Exactly one of sum / count / distinct / ratio / diff is used. `where`
    restricts a sum or count to rows whose column holds one of the values.
    """

    key: str
    label: str
    fmt: Fmt = "int"
    sum: str | None = None
    count: bool = False
    distinct: str | None = None
    ratio: tuple[str, str] | None = None  # numerator, denominator (measure keys)
    diff: tuple[str, str] | None = None  # a - b (measure keys)
    where: tuple[str, tuple[str, ...]] | None = None


@dataclass(frozen=True)
class Filter:
    field: str
    label: str
    all_label: str = "All"
    # "alpha": sorted values; "given": the order of `values` (e.g. quarters).
    order: Literal["alpha", "given"] = "alpha"
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class KpiTile:
    label: str
    measure: str
    facts: str
    note: str = ""  # may name measures: "{delivered_qty} of {ordered_qty} units"
    tone: Literal["blue", "red", "amber", "green", "grey"] = "blue"


@dataclass(frozen=True)
class ChartSpec:
    title: str
    facts: str
    group: str
    measures: tuple[str, ...]
    kind: Literal["bar", "hbar", "line", "combo", "stacked"] = "bar"
    note: str = ""
    ignore: tuple[str, ...] = ()  # filters this chart does not follow
    sort: Literal["key", "desc", "asc"] = "key"
    sort_by: str | None = None  # measure key ("rank" = the section's rank choice)
    limit: int | None = None
    stack: str | None = None  # stacked: one series per value of this column (top N)
    stack_limit: int = 8
    percent: bool = False  # values are shares (0-1), axis in %
    traffic: tuple[float, float] | None = None  # hbar colours: red below a, amber below b


@dataclass(frozen=True)
class TableSpec:
    title: str
    facts: str
    group: tuple[str, ...]
    columns: tuple[str, ...]
    note: str = ""
    ignore: tuple[str, ...] = ()
    sort_by: str | None = None  # measure key, or "rank"
    descending: bool = True
    limit: int | None = None
    bars: tuple[str, ...] = ()  # percentage columns drawn with a small bar
    traffic: tuple[float, float] = (0.85, 0.95)
    labels: dict[str, str] = field(default_factory=dict)  # group column -> header


@dataclass(frozen=True)
class DetailSpec:
    title: str
    facts: str
    columns: tuple[tuple[str, str, Fmt], ...]  # column, header, format
    note: str = ""
    sort_by: str | None = None
    descending: bool = True
    limit: int = 100


Block = ChartSpec | TableSpec | DetailSpec


@dataclass(frozen=True)
class DashSection:
    title: str
    blocks: tuple[Block, ...]
    note: str = ""
    rank_choices: tuple[str, ...] = ()  # measure keys offered in a "Rank by" list


@dataclass
class InteractiveDashboard:
    title: str
    subtitle: str
    facts: dict[str, pd.DataFrame]
    measures: dict[str, tuple[Measure, ...]]  # per fact table
    filters: tuple[Filter, ...]
    kpis: tuple[KpiTile, ...]
    sections: tuple[DashSection, ...]
    eyebrow: str = "Rwanda Medical Supply"
    intro: str = ""
    footer: str = ""
    checks: list[tuple[str, float, float, bool]] = field(default_factory=list)


def _cell(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, pd.Timestamp | datetime | date):
        return value.strftime("%Y-%m-%d")
    return value


def _encode(frame: pd.DataFrame) -> dict[str, Any]:
    """Columnar data; text columns as a dictionary plus indices (much smaller)."""
    columns: dict[str, Any] = {}
    for name in frame.columns:
        series = frame[name]
        values = [_cell(v) for v in series.tolist()]
        numeric = pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)
        if numeric:
            columns[str(name)] = {
                "n": [
                    None if v is None else (int(v) if float(v).is_integer() else float(v))
                    for v in values
                ]
            }
        else:
            texts = ["" if v is None else str(v) for v in values]
            dictionary = sorted(set(texts))
            index = {t: i for i, t in enumerate(dictionary)}
            columns[str(name)] = {"d": dictionary, "i": [index[t] for t in texts]}
    return {"rows": len(frame), "columns": columns}


def _strip(obj: Any) -> Any:
    """Dataclass dicts without empty optional fields (smaller, easier to read)."""
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if v not in (None, (), [], {}, "")}
    if isinstance(obj, list | tuple):
        return [_strip(v) for v in obj]
    return obj


def _block(block: Block) -> dict[str, Any]:
    kind = {ChartSpec: "chart", TableSpec: "table", DetailSpec: "detail"}[type(block)]
    return {"type": kind, **_strip(asdict(block))}


def payload(dashboard: InteractiveDashboard) -> dict[str, Any]:
    return {
        "facts": {name: _encode(frame) for name, frame in dashboard.facts.items()},
        "measures": {
            name: [_strip(asdict(m)) for m in measures]
            for name, measures in dashboard.measures.items()
        },
        "filters": [_strip(asdict(f)) for f in dashboard.filters],
        "kpis": [_strip(asdict(k)) for k in dashboard.kpis],
        "sections": [
            {
                "title": s.title,
                "note": s.note,
                "rank": list(s.rank_choices),
                "blocks": [_block(b) for b in s.blocks],
            }
            for s in dashboard.sections
        ],
    }


def _asset(name: str) -> str:
    return resources.files("app.reporting").joinpath("assets", name).read_text(encoding="utf-8")


def pack(data: dict[str, Any]) -> str:
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return base64.b64encode(gzip.compress(raw.encode("utf-8"), mtime=0)).decode("ascii")


def unpack(text: str) -> Any:
    return json.loads(gzip.decompress(base64.b64decode(text.strip())))


def read_payload(content: bytes) -> dict[str, Any] | None:
    """The data packed in a dashboard file (None when it has none)."""
    found = re.search(r'<script id="data"[^>]*>(.*?)</script>', content.decode("utf-8"), re.S)
    data = unpack(found.group(1)) if found else None
    return data if isinstance(data, dict) else None


def build_html(dashboard: InteractiveDashboard) -> bytes:
    e = html.escape
    checks = "".join(
        f'<tr><td>{e(label)}</td><td class="n">{expected:,.2f}</td>'
        f'<td class="n">{actual:,.2f}</td><td>{"Passed" if ok else "Failed"}</td></tr>'
        for label, expected, actual, ok in dashboard.checks
    )
    check_block = (
        '<section class="sec"><h2>Self-checks</h2><div class="tw"><table class="tb">'
        "<thead><tr><th>Check</th><th>Expected</th><th>Actual</th><th>Result</th></tr></thead>"
        f"<tbody>{checks}</tbody></table></div></section>"
        if dashboard.checks
        else ""
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(dashboard.title)}</title>
<style>{_asset("dashboard.css")}</style>
</head><body>
<header class="hd"><div class="wrap">
<div class="eyebrow">{e(dashboard.eyebrow)}</div>
<h1>{e(dashboard.title)}</h1>
<p class="sub">{e(dashboard.subtitle)}</p>
{f'<p class="intro">{e(dashboard.intro)}</p>' if dashboard.intro else ""}
</div></header>
<nav class="flt" aria-label="Filters"><div class="wrap" id="filters"></div></nav>
<main class="wrap">
<p id="active" class="active"></p>
<div id="loading" class="loading">Loading the data…</div>
<section class="kpis" id="kpis" aria-label="Key figures"></section>
<div id="sections"></div>
{check_block}
<footer class="ft">{e(dashboard.footer)}</footer>
</main>
<script id="data" type="application/octet-stream">{pack(payload(dashboard))}</script>
<script>{_asset("chart.umd.js")}</script>
<script>{_asset("dashboard.js")}</script>
</body></html>
"""
    return page.encode("utf-8")
