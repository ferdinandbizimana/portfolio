"""Picker accuracy from the picking register (Ferdinand, 26 October 2026).

The picking register has one sheet per day with the lines each picker picked
and the discrepancies found in them, and sheets with one row per outbound
delivery (customer, order type, lines, lines with discrepancies, picker).
Definitions used (see docs/PLAN.md, Decisions):

- accuracy = 1 - discrepancies / lines picked, per picker, per day and overall;
- the day of a daily sheet comes from its name ("25nov", "26 NOV", "28TH nov",
  "27112025" = 27/11/2025, "2122025" = 2/12/2025); a name without a year takes
  the year of the other sheets; a delivery row uses its own date;
- the same picker written in different capitals is one picker;
- pickers below the accuracy target (a parameter) are flagged.
"""

import contextlib
import re
from datetime import date
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from app.analyses.base import Analysis, AnalysisResult, Check, InputSpec
from app.analyses.dashboard import Chart, Column, Dashboard, Kpi, Series, Table, rows_of
from app.reporting.documents import (
    ChartBlock,
    ReportDocument,
    ReportFile,
    Section,
    TableBlock,
    Templates,
    ValueFormat,
    check_lines,
)
from app.reporting.excel import build_workbook
from app.reporting.slides import build_pptx
from app.reporting.word import build_docx

MONTHS = {
    m: i
    for i, m in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"],
        start=1,
    )
}
BELOW, ON_TARGET = "Below target", "On target"


def _candidates(name: str, year: int | None) -> list[date]:
    """Possible days for a sheet name; several when the digits can be read two ways."""
    text = name.strip().upper()
    found: list[date] = []
    words = re.fullmatch(r"(\d{1,2})\s*(?:ST|ND|RD|TH)?\s*([A-Z]{3})[A-Z]*\.?\s*(\d{4})?", text)
    if words and words.group(2) in MONTHS:
        y = int(words.group(3)) if words.group(3) else year
        if y is not None:
            with contextlib.suppress(ValueError):
                found.append(date(y, MONTHS[words.group(2)], int(words.group(1))))
        return found
    digits = re.fullmatch(r"(\d{1,2})(\d{1,2})(\d{4})", text)
    if digits:
        whole = text
        y = int(whole[-4:])
        rest = whole[:-4]
        for cut in range(1, len(rest)):
            day, month = int(rest[:cut]), int(rest[cut:])
            try:
                found.append(date(y, month, day))
            except ValueError:
                continue
    return found


def sheet_days(names: list[str], known: list[date] | None = None) -> dict[str, date | None]:
    """The day of each daily sheet, read from its name.

    `known` are dates found elsewhere in the register (rows per delivery): they give
    the year of names without one and settle names that can be read two ways.
    """
    years = [c.year for n in names for c in _candidates(n, None)] + [d.year for d in known or []]
    year = max(set(years), key=years.count) if years else None
    options = {n: _candidates(n, year) for n in names}
    sure = [o[0] for o in options.values() if len(o) == 1] + list(known or [])
    middle = sorted(sure)[len(sure) // 2] if sure else None
    days: dict[str, date | None] = {}
    for name, found in options.items():
        if not found:
            days[name] = None
        elif len(found) == 1 or middle is None:
            days[name] = found[0]
        else:  # "2122025": 2/12 or 21/2 -> the one nearest the other sheets
            days[name] = min(found, key=lambda d: abs((d - middle).days))
    return days


def _picker(value: object) -> str:
    text = "" if value is None or (not isinstance(value, str) and pd.isna(value)) else str(value)  # type: ignore[call-overload]
    return " ".join(text.split()).title()


class Parameters(BaseModel):
    target: float = Field(
        default=0.98,
        ge=0,
        le=1,
        title="Accuracy target",
        description="Share of lines without discrepancy expected from each picker (0.98 = 98%).",
    )


def _params(params: BaseModel) -> Parameters:
    if not isinstance(params, Parameters):
        raise TypeError("Parameters of the wrong analysis.")
    return params


def _accuracy(lines: float, wrong: float) -> float | None:
    return 1 - wrong / lines if lines else None


class PickerAccuracy(Analysis):
    key = "picker_accuracy"
    title = "Picker accuracy"
    version = "1.0.0"
    description = (
        "Lines picked and discrepancies per picker and per day from the picking register, "
        "accuracy against a target, and by customer and order type where the register has "
        "one row per outbound delivery."
    )
    inputs = (
        InputSpec(
            "daily",
            "picker_daily",
            "Picking register: daily sheets (lines and discrepancies per picker)",
            all_sheets=True,
        ),
        InputSpec(
            "orders",
            "picker_orders",
            "Picking register: sheets with one row per outbound delivery",
            required=False,
            all_sheets=True,
        ),
    )
    Parameters = Parameters

    def compute(self, data: dict[str, pd.DataFrame], params: BaseModel) -> AnalysisResult:
        params = _params(params)
        orders_raw = data.get("orders")
        orders = pd.DataFrame(
            columns=[
                "Day",
                "Sheet",
                "Picker",
                "Lines",
                "Discrepancies",
                "Customer",
                "Order Type",
                "Delivery",
            ]
        )
        if orders_raw is not None and len(orders_raw):
            wrong = (
                orders_raw["Number of Lines with descrepancies"]
                if "Number of Lines with descrepancies" in orders_raw
                else pd.Series(0.0, index=orders_raw.index)
            )
            orders = pd.DataFrame(
                {
                    "Day": [
                        d.date() if pd.notna(d) else None
                        for d in pd.to_datetime(orders_raw["Date"])
                    ],
                    "Sheet": orders_raw["Sheet"].astype(str) if "Sheet" in orders_raw else "",
                    "Picker": orders_raw["Pickers Name"].map(_picker),
                    "Lines": orders_raw["Number of Lines"].astype(float).fillna(0.0),
                    "Discrepancies": wrong.astype(float).fillna(0.0),
                    "Customer": orders_raw.get(
                        "Customer/Branche Name", pd.Series("", index=orders_raw.index)
                    ).map(_picker),
                    "Order Type": orders_raw.get(
                        "Type of Order", pd.Series("", index=orders_raw.index)
                    )
                    .astype("string")
                    .fillna("")
                    .str.strip()
                    .astype(str),
                    "Delivery": orders_raw["Outbound Delivery ( OBD ) Number"]
                    .astype("string")
                    .fillna("")
                    .astype(str),
                }
            )
        raw = data["daily"]
        sheets = (
            raw["Sheet"].astype(str) if "Sheet" in raw.columns else pd.Series("", index=raw.index)
        )
        days = sheet_days(sorted(set(sheets)), [d for d in orders["Day"] if d is not None])
        daily = pd.DataFrame(
            {
                "Day": [days.get(s) for s in sheets],
                "Sheet": sheets,
                "Picker": raw["Pickers name"].map(_picker),
                "Lines": raw["Numbers of lines picked per day"].astype(float).fillna(0.0),
                "Discrepancies": raw["Number of descrepancies out of those lines"]
                .astype(float)
                .fillna(0.0),
                "Source": "Daily sheet",
            }
        )
        no_picker = int((daily["Picker"] == "").sum()) + int((orders["Picker"] == "").sum())
        daily = daily[daily["Picker"] != ""]
        orders = orders[orders["Picker"] != ""]
        columns = ["Day", "Sheet", "Picker", "Lines", "Discrepancies"]
        parts = [frame[columns] for frame in (daily, orders) if len(frame)]
        lines = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns)

        def summary(by: list[str]) -> pd.DataFrame:
            if lines.empty:
                return pd.DataFrame(columns=[*by, "Lines", "Discrepancies", "Accuracy"])
            grouped = (
                lines.assign(Day=lines["Day"].astype("string").fillna("Unknown day"))
                .groupby(by, sort=True)[["Lines", "Discrepancies"]]
                .sum()
                .reset_index()
            )
            grouped["Accuracy"] = [
                _accuracy(n, w)
                for n, w in zip(grouped["Lines"], grouped["Discrepancies"], strict=True)
            ]
            return grouped

        by_picker = summary(["Picker"])
        if len(by_picker):
            by_picker["Days"] = [
                int(lines.loc[lines["Picker"] == p, "Day"].nunique()) for p in by_picker["Picker"]
            ]
            by_picker["Status"] = [
                ON_TARGET if a is not None and a >= params.target else BELOW
                for a in by_picker["Accuracy"]
            ]
            by_picker = by_picker.sort_values(["Accuracy", "Picker"], kind="mergesort").reset_index(
                drop=True
            )
        by_day = summary(["Day"])
        by_picker_day = summary(["Day", "Picker"])
        by_customer = pd.DataFrame()
        by_type = pd.DataFrame()
        if len(orders):

            def group(column: str) -> pd.DataFrame:
                g = (
                    orders.groupby(column, sort=True)
                    .agg(
                        Deliveries=("Delivery", "nunique"),
                        Lines=("Lines", "sum"),
                        Discrepancies=("Discrepancies", "sum"),
                    )
                    .reset_index()
                )
                g["Accuracy"] = [
                    _accuracy(n, w) for n, w in zip(g["Lines"], g["Discrepancies"], strict=True)
                ]
                return g

            by_customer = group("Customer")
            by_type = group("Order Type")

        total_lines = float(lines["Lines"].sum())
        total_wrong = float(lines["Discrepancies"].sum())
        below = by_picker[by_picker["Status"] == BELOW] if len(by_picker) else by_picker
        kpis = [
            Kpi(label="Lines picked", value=total_lines, format="integer"),
            Kpi(label="Lines with discrepancies", value=total_wrong, format="integer"),
            Kpi(
                label="Picking accuracy",
                value=_accuracy(total_lines, total_wrong),
                format="percent",
            ),
            Kpi(label="Pickers", value=len(by_picker), format="integer"),
            Kpi(
                label="Pickers below target",
                value=len(below),
                format="integer",
                note=f"Target {params.target:.0%}",
            ),
            Kpi(label="Days", value=int(lines["Day"].nunique()), format="integer"),
        ]
        checks = [
            Check(
                "pickers_total",
                "Lines by picker = lines picked",
                expected=total_lines,
                actual=float(by_picker["Lines"].sum()) if len(by_picker) else 0.0,
            ),
            Check(
                "days_total",
                "Discrepancies by day = discrepancies",
                expected=total_wrong,
                actual=float(by_day["Discrepancies"].sum()) if len(by_day) else 0.0,
            ),
            Check(
                "within_lines",
                "Pickers with more discrepancies than lines",
                expected=0,
                actual=float((by_picker_day["Discrepancies"] > by_picker_day["Lines"]).sum())
                if len(by_picker_day)
                else 0.0,
                tolerance=0,
            ),
        ]
        first, last = (
            (lines["Day"].dropna().min(), lines["Day"].dropna().max())
            if lines["Day"].notna().any()
            else (None, None)
        )
        subtitle = (
            f"Picking register, {first:%d %B %Y} to {last:%d %B %Y}"
            if first
            else "Picking register"
        )
        percent, integer = "percent", "integer"
        rate_columns = [
            Column(key="Lines", label="Lines", format=integer),
            Column(key="Discrepancies", label="Discrepancies", format=integer),
            Column(key="Accuracy", label="Accuracy", format=percent),
        ]
        by_day_out = by_day.copy()
        dashboard = Dashboard(
            title=self.title,
            subtitle=subtitle,
            kpis=kpis,
            charts=[
                Chart(
                    id="picker-chart",
                    title="Accuracy by picker",
                    type="bar",
                    table="by-picker",
                    category="Picker",
                    format=percent,
                    series=[Series(name="Accuracy", field="Accuracy")],
                ),
                Chart(
                    id="day-chart",
                    title="Accuracy by day",
                    type="line",
                    table="by-day",
                    category="Day",
                    format=percent,
                    series=[Series(name="Accuracy", field="Accuracy")],
                ),
            ],
            tables=[
                Table(
                    id="by-picker",
                    title="By picker (lowest accuracy first)",
                    columns=[
                        Column(key="Picker", label="Picker"),
                        Column(key="Days", label="Days", format=integer),
                        *rate_columns,
                        Column(key="Status", label=f"Target {params.target:.0%}"),
                    ],
                    rows=rows_of(by_picker),
                ),
                Table(
                    id="by-day",
                    title="By day",
                    columns=[Column(key="Day", label="Day"), *rate_columns],
                    rows=rows_of(by_day_out),
                ),
                Table(
                    id="by-picker-day",
                    title="By picker and day",
                    columns=[
                        Column(key="Day", label="Day"),
                        Column(key="Picker", label="Picker"),
                        *rate_columns,
                    ],
                    rows=rows_of(by_picker_day),
                    level="detail",
                    filters=["Picker"],
                ),
                *(
                    [
                        Table(
                            id="by-customer",
                            title="By customer or branch",
                            columns=[
                                Column(key="Customer", label="Customer or branch"),
                                Column(key="Deliveries", label="Deliveries", format=integer),
                                *rate_columns,
                            ],
                            rows=rows_of(by_customer),
                            level="detail",
                        ),
                        Table(
                            id="by-type",
                            title="By order type",
                            columns=[
                                Column(key="Order Type", label="Order type"),
                                Column(key="Deliveries", label="Deliveries", format=integer),
                                *rate_columns,
                            ],
                            rows=rows_of(by_type),
                        ),
                    ]
                    if len(by_customer)
                    else []
                ),
            ],
            checks=[c.out() for c in checks],
            notes=[f"{no_picker} rows without a picker name are left out."] if no_picker else [],
        )
        return AnalysisResult(
            tables={
                "by_picker": by_picker,
                "by_day": by_day,
                "by_picker_day": by_picker_day,
                "by_customer": by_customer,
                "by_type": by_type,
            },
            metrics=kpis,
            checks=checks,
            dashboard=dashboard,
            extras={"subtitle": subtitle},
        )

    def reports(
        self, result: AnalysisResult, params: BaseModel, templates: Templates
    ) -> list[ReportFile]:
        params = _params(params)
        t = result.tables
        formats: dict[str, ValueFormat] = {
            "Lines": "integer",
            "Discrepancies": "integer",
            "Accuracy": "percent",
            "Days": "integer",
            "Deliveries": "integer",
        }
        by_picker = TableBlock("By picker", t["by_picker"], formats)
        by_day = TableBlock("By day", t["by_day"], formats)
        kpi: dict[str, Any] = {k.label: k.value for k in result.metrics}
        accuracy = kpi["Picking accuracy"]
        document = ReportDocument(
            title="Picker accuracy",
            subtitle=str(result.extras["subtitle"]),
            date_text=str(result.extras["subtitle"]).split(" to ")[-1]
            if " to " in str(result.extras["subtitle"])
            else "",
            sections=[
                Section(
                    "Summary",
                    paragraphs=[
                        f"{int(kpi['Lines picked'] or 0):,} lines were picked with "
                        f"{int(kpi['Lines with discrepancies'] or 0):,} discrepancies"
                        + (
                            f": an accuracy of {float(accuracy):.1%}"
                            if isinstance(accuracy, int | float)
                            else ""
                        )
                        + f". {kpi['Pickers below target']} of {kpi['Pickers']} pickers are below "
                        f"the target of {params.target:.0%}.",
                    ],
                    tables=[by_picker],
                    charts=[
                        ChartBlock(
                            "Accuracy by picker (%)",
                            [str(p) for p in t["by_picker"]["Picker"]],
                            {"Accuracy": [100 * float(a or 0) for a in t["by_picker"]["Accuracy"]]},
                        )
                    ]
                    if len(t["by_picker"])
                    else [],
                ),
                Section("By day", tables=[by_day]),
                Section(
                    "Method",
                    bullets=[
                        "Accuracy = 1 - lines with discrepancies / lines picked.",
                        "Days are read from the names of the daily sheets; rows per outbound "
                        "delivery use their own date.",
                    ],
                ),
            ],
            checks=check_lines(result.checks),
        )
        blocks = [by_picker, by_day, TableBlock("By picker and day", t["by_picker_day"], formats)]
        if len(t["by_customer"]):
            blocks += [
                TableBlock("By customer", t["by_customer"], formats),
                TableBlock("By order type", t["by_type"], formats),
            ]
        name = "Picker_Accuracy"
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


ANALYSIS = PickerAccuracy()
