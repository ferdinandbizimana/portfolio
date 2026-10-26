"""Spot check accuracy (Ferdinand, 26 October 2026).

The weekly spot check is an EWM bin stock list (storage bin, product, batch,
system quantity "Qty AUoM") with the quantity found on the shelf ("ONHAND QTY"
or "SOH"), the variance and the supervisor's comment. Definitions, from the
spot check progress report and Ferdinand's answers (docs/PLAN.md, Decisions):

- quantity accuracy = 1 - |sum of variances| / sum of system quantities;
- line accuracy = 1 - lines with a variance / lines checked;
- "true" accuracy leaves out variance lines whose comment explains them
  (picked or served for an outbound delivery, delivered, bin to bin, moved,
  corrected: a parameter);
- data-integrity flags: lines whose comment reports a wrong batch, lot,
  expiry date or description (stock present, record wrong: a parameter);
- variance value = "variance on cost" when given, else variance x unit cost;
- the responsible person of each bin comes from the bin list, when given;
- a previous spot check, when given, is measured the same way for comparison.
"""

import re
from datetime import date
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from app.analyses.base import Analysis, AnalysisResult, Check, InputSpec
from app.analyses.dashboard import Chart, Column, Dashboard, Kpi, Series, Table, rows_of
from app.reporting.documents import (
    ReportDocument,
    ReportFile,
    Section,
    TableBlock,
    Templates,
    ValueFormat,
    check_lines,
)
from app.reporting.excel import build_workbook
from app.reporting.interactive import check_rows, dashboard_file
from app.reporting.slides import build_pptx
from app.reporting.word import build_docx

EXPLAINED_KEYWORDS = "PICKED, SERVED, DELIVERED, BIN TO BIN, MOVED, CORRECTED"
INTEGRITY_KEYWORDS = "BATCH, LOT, EXPIR, EX:, DESC"
THIS_CHECK = "This spot check"
NO_WBS, NO_OWNER, NO_TYPE = "No WBS", "No responsible person", "No storage type"

LINE_COLUMNS = [
    "Check",
    "Storage Type",
    "Storage Bin",
    "Product",
    "Product Description",
    "Batch",
    "WBS",
    "Responsible",
    "System Qty",
    "Counted Qty",
    "Variance",
    "Real Variance",
    "Unit Cost",
    "Variance Value",
    "Has Variance",
    "Explained",
    "Real Variance Line",
    "Data Integrity",
    "Comment",
]


class Parameters(BaseModel):
    check_date: date = Field(
        title="Spot check date", description="Day of the spot check, e.g. 17 September 2026."
    )
    previous_label: str = Field(
        default="Previous spot check",
        max_length=80,
        title="Name of the previous spot check",
        description='Shown when a previous spot check is given, e.g. "7 to 11 September".',
    )
    explained_keywords: str = Field(
        default=EXPLAINED_KEYWORDS,
        title="Comments that explain a variance",
        description="Words in the comment that make a variance line explained (comma-separated).",
    )
    integrity_keywords: str = Field(
        default=INTEGRITY_KEYWORDS,
        title="Comments that flag a wrong record",
        description="Words in the comment that flag a wrong batch, expiry or description.",
    )


def _params(params: BaseModel) -> Parameters:
    if not isinstance(params, Parameters):
        raise TypeError("Parameters of the wrong analysis.")
    return params


def _text(values: pd.Series) -> pd.Series:
    text = values.astype("string").str.strip().fillna("")
    return text.str.replace(r"^(\d+)\.0$", r"\1", regex=True).astype(str)


def bin_code(values: pd.Series) -> pd.Series:
    return _text(values).str.upper().str.replace(" ", "", regex=False)


def keyword_pattern(text: str) -> re.Pattern[str] | None:
    """ "BATCH, LOT" -> a pattern that finds either word at the start of a word."""
    words = [w.strip().upper() for w in text.replace(";", ",").split(",") if w.strip()]
    if not words:
        return None
    return re.compile(r"(?<![A-Z])(?:" + "|".join(re.escape(w) for w in words) + ")")


def _matches(comments: pd.Series, pattern: re.Pattern[str] | None) -> pd.Series:
    if pattern is None:
        return pd.Series(False, index=comments.index)
    return comments.str.upper().map(lambda c: bool(pattern.search(c)))


def _number(frame: pd.DataFrame, column: str) -> pd.Series | None:
    """The column as numbers; None when the file does not have it (all empty)."""
    if column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").astype(float)
    return None if values.isna().all() and len(values) else values


def spot_lines(
    raw: pd.DataFrame,
    check: str,
    owners: dict[str, str],
    explained: re.Pattern[str] | None,
    integrity: re.Pattern[str] | None,
) -> pd.DataFrame:
    """One row per checked line, with the quantities, value and flags."""
    raw = raw[_text(raw["Product"]) != ""]
    given = _number(raw, "Variance")
    variance = (given if given is not None else pd.Series(0.0, index=raw.index)).fillna(0.0)
    counted = _number(raw, "Counted Quantities")
    system = _number(raw, "Qty AUoM")
    if system is None:
        system = _number(raw, "Avail. Qty in AUoM")
    if system is None and counted is not None:
        system = counted - variance
    if system is None:
        system = pd.Series(float("nan"), index=raw.index)
    system = system.fillna(0.0)
    counted = (system + variance) if counted is None else counted.fillna(system + variance)
    unit_cost = _number(raw, "Uunit cost")
    value = _number(raw, "variance on cost")
    if value is None:
        value = variance * unit_cost if unit_cost is not None else pd.Series(0.0, index=raw.index)
    value = value.fillna(0.0)

    def text(column: str, empty: str = "") -> pd.Series:
        if column not in raw.columns:
            return pd.Series(empty, index=raw.index)
        values = _text(raw[column])
        return values.where(values != "", empty)

    comment = text("Comments")
    bins = bin_code(raw["Storage Bin"])
    has_variance = variance.round(6) != 0
    is_explained = has_variance & _matches(comment, explained)
    real = has_variance & ~is_explained
    lines = pd.DataFrame(
        {
            "Check": check,
            "Storage Type": text("Storage Type", NO_TYPE),
            "Storage Bin": bins,
            "Product": _text(raw["Product"]),
            "Product Description": text("Product Description"),
            "Batch": text("Batch"),
            "WBS": text("Stock Reference Doc.", NO_WBS),
            "Responsible": bins.map(owners).fillna(NO_OWNER),
            "System Qty": system,
            "Counted Qty": counted,
            "Variance": variance,
            "Real Variance": variance.where(real, 0.0),
            "Unit Cost": unit_cost if unit_cost is not None else float("nan"),
            "Variance Value": value,
            "Has Variance": has_variance.map({True: "Yes", False: "No"}),
            "Explained": is_explained.map({True: "Yes", False: "No"}),
            "Real Variance Line": real.map({True: "Yes", False: "No"}),
            "Data Integrity": _matches(comment, integrity).map({True: "Yes", False: "No"}),
            "Comment": comment,
        }
    )
    return lines.sort_values(["Storage Bin", "Product", "Batch"], kind="mergesort").reset_index(
        drop=True
    )[LINE_COLUMNS]


def _accuracy(error: float, base: float) -> float | None:
    return 1 - error / base if base else None


def measure(lines: pd.DataFrame) -> dict[str, Any]:
    """The accuracy figures of a set of lines."""
    count = len(lines)
    system = float(lines["System Qty"].sum())
    with_variance = int((lines["Has Variance"] == "Yes").sum())
    real = int((lines["Real Variance Line"] == "Yes").sum())
    net = float(lines["Variance"].sum())
    real_net = float(lines["Real Variance"].sum())
    return {
        "Lines": count,
        "System Qty": system,
        "Counted Qty": float(lines["Counted Qty"].sum()),
        "Net Variance": net,
        "Quantity Accuracy": _accuracy(abs(net), system),
        "True Quantity Accuracy": _accuracy(abs(real_net), system),
        "Lines With Variance": with_variance,
        "Explained Lines": with_variance - real,
        "Real Variance Lines": real,
        "Line Accuracy": _accuracy(with_variance, count),
        "True Line Accuracy": _accuracy(real, count),
        "Net Variance Value": float(lines["Variance Value"].sum()),
        "Gross Variance Value": float(lines["Variance Value"].abs().sum()),
        "Data Integrity Lines": int((lines["Data Integrity"] == "Yes").sum()),
    }


def summary(lines: pd.DataFrame, by: str) -> pd.DataFrame:
    rows = [{by: key, **measure(group)} for key, group in lines.groupby(by, sort=True)]
    columns = [by, *measure(lines.head(0)).keys()]
    return pd.DataFrame(rows, columns=columns)


class SpotCheckAccuracy(Analysis):
    key = "spot_check_accuracy"
    title = "Spot check accuracy"
    version = "1.0.0"
    description = (
        "Quantity and line accuracy of a weekly spot check (EWM bin stock against the "
        "quantity found), raw and with explained variances left out; variance value, "
        "data-integrity flags (wrong batch, expiry or description), responsible person "
        "per bin and comparison with the previous spot check."
    )
    inputs = (
        InputSpec("spot_check", "spot_check", "Spot check sheet (this week)"),
        InputSpec(
            "previous", "spot_check", "Previous spot check sheet (to compare)", required=False
        ),
        InputSpec("bins", "bin_owners", "Storage bins with responsible person", required=False),
    )
    Parameters = Parameters

    def compute(self, data: dict[str, pd.DataFrame], params: BaseModel) -> AnalysisResult:
        params = _params(params)
        owners: dict[str, str] = {}
        bins = data.get("bins")
        if bins is not None and len(bins):
            names = _text(bins["RESPONSIBLE PERSON"])
            codes = bin_code(bins["Storage Bin"])
            for code, name in zip(codes, names, strict=True):
                if code and name and code not in owners:
                    owners[code] = name
        explained = keyword_pattern(params.explained_keywords)
        integrity = keyword_pattern(params.integrity_keywords)
        lines = spot_lines(data["spot_check"], THIS_CHECK, owners, explained, integrity)
        previous_raw = data.get("previous")
        previous = (
            spot_lines(previous_raw, params.previous_label, owners, explained, integrity)
            if previous_raw is not None and len(previous_raw)
            else lines.head(0)
        )

        figures = measure(lines)
        comparison = pd.DataFrame(
            [
                {"Check": THIS_CHECK, **figures},
                *([{"Check": params.previous_label, **measure(previous)}] if len(previous) else []),
            ]
        )
        by_wbs = summary(lines, "WBS")
        by_type = summary(lines, "Storage Type")
        by_owner = summary(lines, "Responsible")
        variances = lines[lines["Has Variance"] == "Yes"].copy()
        variances["_size"] = variances["Variance Value"].abs()
        variances["_qty"] = variances["Variance"].abs()
        variances = (
            variances.sort_values(
                ["_size", "_qty", "Storage Bin", "Product"],
                ascending=[False, False, True, True],
                kind="mergesort",
            )
            .drop(columns=["_size", "_qty"])
            .reset_index(drop=True)
        )
        integrity_lines = lines[lines["Data Integrity"] == "Yes"].reset_index(drop=True)
        by_product = (
            variances.groupby(["Product", "Product Description"], sort=True)
            .agg(
                Lines=("Storage Bin", "size"),
                **{
                    "Net Variance": ("Variance", "sum"),
                    "Real Variance": ("Real Variance", "sum"),
                    "Variance Value": ("Variance Value", "sum"),
                    "Responsible": (
                        "Responsible",
                        lambda s: ", ".join(sorted(set(s))),
                    ),
                },
            )
            .reset_index()
        )
        if len(by_product):
            by_product["_size"] = by_product["Variance Value"].abs()
            by_product = (
                by_product.sort_values(["_size", "Product"], ascending=[False, True])
                .drop(columns="_size")
                .reset_index(drop=True)
            )

        checks = [
            Check(
                "counted_minus_system",
                "Counted - system quantity = sum of the variances",
                expected=figures["Net Variance"],
                actual=figures["Counted Qty"] - figures["System Qty"],
            ),
            Check(
                "wbs_lines",
                "Lines by WBS = lines checked",
                expected=figures["Lines"],
                actual=float(by_wbs["Lines"].sum()),
                tolerance=0,
            ),
            Check(
                "real_lines",
                "Real + explained variance lines = lines with a variance",
                expected=figures["Lines With Variance"],
                actual=float(figures["Real Variance Lines"] + figures["Explained Lines"]),
                tolerance=0,
            ),
            Check(
                "owner_value",
                "Variance value by responsible person = variance value",
                expected=figures["Net Variance Value"],
                actual=float(by_owner["Net Variance Value"].sum()),
            ),
        ]
        percent, integer, number, money = "percent", "integer", "number", "money"
        kpis = [
            Kpi(label="Lines checked", value=figures["Lines"], format=integer),
            Kpi(
                label="Quantity accuracy",
                value=figures["Quantity Accuracy"],
                format=percent,
                note="1 - |net variance| / system quantity",
            ),
            Kpi(
                label="True quantity accuracy",
                value=figures["True Quantity Accuracy"],
                format=percent,
                note="explained variances left out",
            ),
            Kpi(label="Line accuracy", value=figures["Line Accuracy"], format=percent),
            Kpi(label="True line accuracy", value=figures["True Line Accuracy"], format=percent),
            Kpi(
                label="Lines with a real variance",
                value=figures["Real Variance Lines"],
                format=integer,
            ),
            Kpi(
                label="Net variance value",
                value=figures["Net Variance Value"],
                format=money,
                unit="RWF",
            ),
            Kpi(
                label="Data-integrity flags",
                value=figures["Data Integrity Lines"],
                format=integer,
                note="wrong batch, expiry or description",
            ),
        ]
        if len(previous):
            before = measure(previous)
            kpis.append(
                Kpi(
                    label=f"True line accuracy, {params.previous_label}",
                    value=before["True Line Accuracy"],
                    format=percent,
                )
            )
        subtitle = f"Spot check of {params.check_date:%d %B %Y}"
        rate = [
            Column(key="Lines", label="Lines", format=integer),
            Column(key="Quantity Accuracy", label="Quantity accuracy", format=percent),
            Column(key="True Quantity Accuracy", label="True quantity accuracy", format=percent),
            Column(key="Line Accuracy", label="Line accuracy", format=percent),
            Column(key="True Line Accuracy", label="True line accuracy", format=percent),
            Column(key="Real Variance Lines", label="Real variance lines", format=integer),
            Column(key="Net Variance Value", label="Net variance (RWF)", format=money),
        ]
        line_columns = [
            Column(key="Storage Bin", label="Bin"),
            Column(key="Product", label="Product"),
            Column(key="Product Description", label="Description"),
            Column(key="Batch", label="Batch"),
            Column(key="WBS", label="WBS"),
            Column(key="Responsible", label="Responsible"),
            Column(key="System Qty", label="System", format=number),
            Column(key="Counted Qty", label="Counted", format=number),
            Column(key="Variance", label="Variance", format=number),
            Column(key="Variance Value", label="Value (RWF)", format=money),
            Column(key="Explained", label="Explained"),
            Column(key="Comment", label="Comment"),
        ]
        dashboard = Dashboard(
            title=self.title,
            subtitle=subtitle,
            kpis=kpis,
            charts=[
                Chart(
                    id="compare-chart",
                    title="Accuracy: this spot check and the previous one",
                    type="column",
                    table="comparison",
                    category="Check",
                    format=percent,
                    series=[
                        Series(name="Quantity", field="True Quantity Accuracy"),
                        Series(name="Lines", field="True Line Accuracy"),
                    ],
                ),
                Chart(
                    id="wbs-chart",
                    title="True line accuracy by WBS",
                    type="bar",
                    table="by-wbs",
                    category="WBS",
                    format=percent,
                    series=[Series(name="True line accuracy", field="True Line Accuracy")],
                ),
            ],
            tables=[
                Table(
                    id="comparison",
                    title="This spot check and the previous one",
                    columns=[Column(key="Check", label="Spot check"), *rate],
                    rows=rows_of(comparison),
                ),
                Table(
                    id="by-wbs",
                    title="By WBS",
                    columns=[Column(key="WBS", label="WBS"), *rate],
                    rows=rows_of(by_wbs),
                ),
                Table(
                    id="by-owner",
                    title="By responsible person",
                    columns=[Column(key="Responsible", label="Responsible"), *rate],
                    rows=rows_of(by_owner),
                ),
                Table(
                    id="variances",
                    title="Variance lines (largest value first)",
                    columns=line_columns,
                    rows=rows_of(variances),
                    level="detail",
                    filters=["WBS", "Responsible", "Explained"],
                ),
                Table(
                    id="integrity",
                    title="Data-integrity flags: wrong batch, expiry or description",
                    columns=line_columns,
                    rows=rows_of(integrity_lines),
                    level="detail",
                ),
                Table(
                    id="lines",
                    title="All lines checked",
                    columns=line_columns,
                    rows=rows_of(lines),
                    total_rows=len(lines),
                    level="detail",
                    filters=["WBS", "Responsible", "Has Variance"],
                    searchable=["Product", "Product Description", "Storage Bin"],
                ),
            ],
            checks=[c.out() for c in checks],
            notes=[
                "True accuracy leaves out variance lines whose comment explains them "
                f"({params.explained_keywords}).",
            ],
        )
        return AnalysisResult(
            tables={
                "lines": lines,
                "previous_lines": previous,
                "comparison": comparison,
                "by_wbs": by_wbs,
                "by_storage_type": by_type,
                "by_owner": by_owner,
                "variances": variances,
                "by_product": by_product,
                "integrity": integrity_lines,
            },
            metrics=kpis,
            checks=checks,
            dashboard=dashboard,
            extras={"subtitle": subtitle},
        )

    def reports(
        self, result: AnalysisResult, params: BaseModel, templates: Templates
    ) -> list[ReportFile]:
        from app.analyses.spot_check_accuracy import dashboard_html

        params = _params(params)
        t = result.tables
        formats: dict[str, ValueFormat] = {
            "Lines": "integer",
            "System Qty": "number",
            "Counted Qty": "number",
            "Net Variance": "number",
            "Real Variance": "number",
            "Variance": "number",
            "Quantity Accuracy": "percent",
            "True Quantity Accuracy": "percent",
            "Line Accuracy": "percent",
            "True Line Accuracy": "percent",
            "Lines With Variance": "integer",
            "Explained Lines": "integer",
            "Real Variance Lines": "integer",
            "Net Variance Value": "money",
            "Gross Variance Value": "money",
            "Variance Value": "money",
            "Unit Cost": "money",
            "Data Integrity Lines": "integer",
        }
        rate_columns = [
            "Lines",
            "Quantity Accuracy",
            "True Quantity Accuracy",
            "Line Accuracy",
            "True Line Accuracy",
            "Real Variance Lines",
            "Net Variance Value",
        ]
        line_columns = [
            "Storage Bin",
            "Product",
            "Product Description",
            "Batch",
            "WBS",
            "Responsible",
            "System Qty",
            "Counted Qty",
            "Variance",
            "Variance Value",
            "Explained",
            "Comment",
        ]
        comparison = TableBlock("Spot checks", t["comparison"][["Check", *rate_columns]], formats)
        by_wbs = TableBlock("By WBS", t["by_wbs"][["WBS", *rate_columns]], formats)
        by_owner = TableBlock(
            "By responsible person", t["by_owner"][["Responsible", *rate_columns]], formats
        )
        variances = TableBlock("Variance lines", t["variances"][line_columns], formats, max_rows=40)
        integrity = TableBlock(
            "Data-integrity flags", t["integrity"][line_columns], formats, max_rows=40
        )
        kpi: dict[str, Any] = {k.label: k.value for k in result.metrics}

        def pct(value: Any) -> str:
            return f"{float(value):.1%}" if isinstance(value, int | float) else "not measured"

        document = ReportDocument(
            title="Spot check accuracy",
            subtitle=str(result.extras["subtitle"]),
            date_text=f"{params.check_date:%d %B %Y}",
            sections=[
                Section(
                    "Summary",
                    paragraphs=[
                        f"{int(kpi['Lines checked']):,} lines were checked. Quantity accuracy "
                        f"is {pct(kpi['Quantity accuracy'])} ({pct(kpi['True quantity accuracy'])} "
                        "with explained variances left out); line accuracy is "
                        f"{pct(kpi['Line accuracy'])} ({pct(kpi['True line accuracy'])}).",
                        f"{int(kpi['Lines with a real variance']):,} lines have a variance that "
                        f"is not explained, and {int(kpi['Data-integrity flags']):,} lines show a "
                        "wrong batch, expiry date or description.",
                    ],
                    tables=[comparison],
                ),
                Section("By WBS and responsible person", tables=[by_wbs, by_owner]),
                Section("Variance lines", tables=[variances]),
                Section("Data-integrity flags", tables=[integrity]),
                Section(
                    "Method",
                    bullets=[
                        "Quantity accuracy = 1 - |sum of variances| / sum of system quantities.",
                        "Line accuracy = 1 - lines with a variance / lines checked.",
                        "True accuracy leaves out variance lines whose comment explains them "
                        f"({params.explained_keywords}).",
                        "Data-integrity flags are lines whose comment mentions "
                        f"{params.integrity_keywords}.",
                        "Variance value = variance on cost, or variance x unit cost.",
                    ],
                ),
            ],
            checks=check_lines(result.checks),
        )
        name = f"Spot_Check_Accuracy_{params.check_date:%Y-%m-%d}"
        blocks = [
            comparison,
            by_wbs,
            by_owner,
            TableBlock(
                "By storage type",
                t["by_storage_type"][["Storage Type", *rate_columns]],
                formats,
            ),
            TableBlock("By product", t["by_product"], formats),
            TableBlock("Variance lines", t["variances"][line_columns], formats),
            TableBlock("Data-integrity flags", t["integrity"][line_columns], formats),
            TableBlock("All lines", t["lines"].drop(columns=["Check"]), formats),
        ]
        return [
            ReportFile(
                "workbook",
                "Excel workbook",
                f"{name}.xlsx",
                "xlsx",
                build_workbook(
                    document.title,
                    document.subtitle,
                    [(k.label, k.value, k.format) for k in result.metrics],
                    blocks,
                    document.checks,
                ),
            ),
            dashboard_file(
                name,
                dashboard_html.build(
                    pd.concat([t["lines"], t["previous_lines"]], ignore_index=True),
                    params.previous_label,
                    document.title,
                    document.subtitle,
                    check_rows(result.checks),
                ),
            ),
            ReportFile(
                "report",
                "Word report",
                f"{name}.docx",
                "docx",
                build_docx(document, templates.docx),
            ),
            ReportFile(
                "slides",
                "PowerPoint slides",
                f"{name}.pptx",
                "pptx",
                build_pptx(document, templates.pptx),
            ),
        ]


ANALYSIS = SpotCheckAccuracy()
