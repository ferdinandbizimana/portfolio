"""Warehouse activity from EWM warehouse tasks (all movements for products).

Ferdinand's rule of 23 October 2026: from "All Movement for Products",
calculate dock to stock (time between goods receipt and putaway) and the time
between picking (stock removal) and goods issue. Definitions used (see
docs/PLAN.md, Decisions):

- putaway and stock removal tasks are told apart by the warehouse process
  category ("Putaway", "Stock Removal"; codes 1 and 2); cancelled tasks
  (status A) are left out; a task is done when it has a confirmation date;
- dock to stock (days) = putaway confirmation date - goods receipt date of the
  task;
- picking time (hours) = confirmation - creation of a stock removal task;
- picking to goods issue (hours) = goods issue of the outbound delivery (date and
  time, from the outbound delivery list) - the last picking confirmation of that
  delivery; the task's document is matched to the delivery number;
- open tasks are aged from their creation to the report date.
"""

from datetime import date, timedelta
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from app.analyses.base import Analysis, AnalysisResult, Check, InputSpec
from app.analyses.common.closing import material_code
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

PUTAWAY, PICKING, OTHER = "Putaway", "Stock removal", "Other movement"
KINDS = [PUTAWAY, PICKING, OTHER]
CANCELLED = "A"
DOCK_BANDS = ["Same day", "1 day", "2 to 3 days", "4 to 7 days", "More than 7 days"]


def kind_of(description: str, code: str) -> str:
    text = description.upper()
    if "PUTAWAY" in text or code == "1":
        return PUTAWAY
    if "REMOVAL" in text or "PICK" in text or code == "2":
        return PICKING
    return OTHER


def dock_band(days: float) -> str:
    if days <= 0:
        return DOCK_BANDS[0]
    if days <= 1:
        return DOCK_BANDS[1]
    if days <= 3:
        return DOCK_BANDS[2]
    if days <= 7:
        return DOCK_BANDS[3]
    return DOCK_BANDS[4]


def moment(day: pd.Series, time: pd.Series) -> pd.Series:
    """Date and time of day ("14:05:30"); the start of the day when the time is blank."""
    clock = pd.to_timedelta(
        time.astype("string")
        .str.strip()
        .fillna("")
        .where(lambda t: t.str.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?"), "0:00:00")
        .map(lambda t: t if t.count(":") == 2 else f"{t}:00")
    )
    return pd.to_datetime(day) + clock


def _text(values: pd.Series) -> pd.Series:
    return values.astype("string").str.strip().fillna("").astype(str)


class Parameters(BaseModel):
    report_date: date = Field(
        title="Report date", description="Date of the export; open tasks are aged to this date."
    )
    dock_to_stock_target_days: int = Field(
        default=1,
        ge=0,
        title="Dock to stock target (days)",
        description="Putaways confirmed within this many days of goods receipt are on target.",
    )


def _params(params: BaseModel) -> Parameters:
    if not isinstance(params, Parameters):
        raise TypeError("Parameters of the wrong analysis.")
    return params


def _mean(values: pd.Series) -> float | None:
    values = values.dropna()
    return float(values.mean()) if len(values) else None


class WarehouseActivity(Analysis):
    key = "warehouse_activity"
    title = "Warehouse activity"
    version = "1.0.0"
    description = (
        "EWM warehouse tasks: dock to stock from goods receipt to putaway, picking time, "
        "picking to goods issue (with the outbound delivery list), open tasks and tasks "
        "confirmed per user and month."
    )
    inputs = (
        InputSpec("tasks", "ewm_warehouse_tasks", "Warehouse tasks (All Movement for Products)"),
        InputSpec(
            "deliveries",
            "outbound_deliveries",
            "Outbound deliveries (goods issue date and time)",
            required=False,
        ),
    )
    Parameters = Parameters

    def compute(self, data: dict[str, pd.DataFrame], params: BaseModel) -> AnalysisResult:
        params = _params(params)
        raw = data["tasks"]
        tasks = pd.DataFrame(
            {
                "Warehouse Task": _text(raw["Warehouse Task"]),
                "Item": _text(raw["WT Item"]),
                "Kind": [
                    kind_of(d, c)
                    for d, c in zip(
                        _text(raw["Whse Process Category Desc."]),
                        _text(raw["Whse Proc. Category"]),
                        strict=True,
                    )
                ],
                "Process Type": _text(raw["Whse Process Type"]),
                "Document": material_code(raw["Document"]).astype(str),
                "Product": material_code(raw["Product"]).astype(str),
                "Product Description": _text(raw["Product Description"]),
                "From Bin": _text(raw["Source Storage Bin"]),
                "To Bin": _text(raw["Destination Bin"]),
                "Status": _text(raw["Warehouse Task Status"]).str.upper(),
                "Quantity": raw["Act. Qty Dest. BUoM"].astype(float),
                "Goods Receipt Date": pd.to_datetime(raw["Goods Receipt Date"]),
                "Created": moment(raw["Created On"], raw["Created At"]),
                "Confirmed": moment(raw["Confirmation Date"], raw["Confirmation Time"]),
                "Confirmed By": _text(raw["Confirmed By"]),
            }
        )
        cancelled = int((tasks["Status"] == CANCELLED).sum())
        tasks = tasks[tasks["Status"] != CANCELLED]
        tasks = tasks.drop_duplicates(["Warehouse Task", "Item"]).reset_index(drop=True)
        done = tasks["Confirmed"].notna()
        report = pd.Timestamp(params.report_date + timedelta(days=1))  # end of the day

        putaways = tasks[done & (tasks["Kind"] == PUTAWAY)].copy()
        putaways["Dock to Stock (days)"] = (
            putaways["Confirmed"].dt.normalize() - putaways["Goods Receipt Date"]
        ).dt.days.astype(float)
        putaways["Dock to Stock"] = [
            dock_band(d) if pd.notna(d) else "No goods receipt date"
            for d in putaways["Dock to Stock (days)"]
        ]
        target = params.dock_to_stock_target_days
        measured = putaways["Dock to Stock (days)"].dropna()
        on_target = int((measured <= target).sum())

        picks = tasks[done & (tasks["Kind"] == PICKING)].copy()
        picks["Picking Time (hours)"] = (
            picks["Confirmed"] - picks["Created"]
        ).dt.total_seconds() / 3600
        deliveries = data.get("deliveries")
        to_gi = pd.DataFrame(columns=["Document", "Last Pick", "Goods Issue", "Hours"])
        matched_deliveries = 0
        if deliveries is not None and len(picks):
            issued = (
                pd.DataFrame(
                    {
                        "Document": material_code(deliveries["Delivery"]).astype(str),
                        "Goods Issue": moment(
                            deliveries["Act. Gds Mvmnt Date"].where(
                                deliveries["Act. Gds Mvmnt Date"].notna(),
                                deliveries["Goods Issue Date"],
                            ),
                            deliveries["Goods Issue Time"],
                        ),
                    }
                )
                .dropna()
                .groupby("Document")["Goods Issue"]
                .max()
            )
            last_pick = picks.groupby("Document")["Confirmed"].max()
            joined = pd.DataFrame({"Last Pick": last_pick}).join(issued, how="inner")
            joined["Hours"] = (
                joined["Goods Issue"] - joined["Last Pick"]
            ).dt.total_seconds() / 3600
            to_gi = joined.reset_index().rename(columns={"index": "Document"})
            matched_deliveries = len(to_gi)

        open_tasks = tasks[~done].copy()
        open_tasks["Age (days)"] = (report - open_tasks["Created"]).dt.days.astype(float)
        open_tasks = open_tasks.sort_values(
            ["Age (days)", "Warehouse Task"],
            ascending=[False, True],
            kind="mergesort",
            na_position="last",
        )

        by_kind = pd.DataFrame(
            [
                {
                    "Task Type": kind,
                    "Tasks": int((tasks["Kind"] == kind).sum()),
                    "Confirmed": int((done & (tasks["Kind"] == kind)).sum()),
                    "Open": int((~done & (tasks["Kind"] == kind)).sum()),
                }
                for kind in KINDS
            ]
        )
        by_band = (
            putaways.groupby("Dock to Stock")
            .agg(Putaways=("Warehouse Task", "size"))
            .reindex([*DOCK_BANDS, "No goods receipt date"], fill_value=0)
            .reset_index()
        )
        confirmed = tasks[done].assign(Month=lambda f: f["Confirmed"].dt.strftime("%Y-%m"))
        by_month = (
            (
                confirmed.pivot_table(
                    index="Month",
                    columns="Kind",
                    values="Warehouse Task",
                    aggfunc="count",
                    fill_value=0,
                )
                .reindex(columns=KINDS, fill_value=0)
                .reset_index()
            )
            if len(confirmed)
            else pd.DataFrame(columns=["Month", *KINDS])
        )
        by_month.columns.name = None
        if len(putaways):
            dock = putaways.assign(Month=putaways["Confirmed"].dt.strftime("%Y-%m"))
            by_month = by_month.merge(
                dock.groupby("Month")["Dock to Stock (days)"]
                .mean()
                .rename("Average Dock to Stock (days)"),
                on="Month",
                how="left",
            )
        by_user = (
            (
                confirmed.assign(User=confirmed["Confirmed By"].replace("", "Not recorded"))
                .pivot_table(
                    index="User",
                    columns="Kind",
                    values="Warehouse Task",
                    aggfunc="count",
                    fill_value=0,
                )
                .reindex(columns=KINDS, fill_value=0)
            )
            if len(confirmed)
            else pd.DataFrame(columns=KINDS)
        )
        by_user["Tasks Confirmed"] = by_user[KINDS].sum(axis=1)
        by_user = by_user.reset_index().rename(columns={"index": "User"})
        by_user.columns.name = None
        by_user = by_user.sort_values(
            ["Tasks Confirmed", "User"], ascending=[False, True], kind="mergesort"
        )

        kpis = [
            Kpi(label="Putaways confirmed", value=len(putaways), format="integer"),
            Kpi(
                label="Average dock to stock",
                value=_mean(putaways["Dock to Stock (days)"]),
                format="number",
                unit="days",
                note="Goods receipt to putaway confirmation",
            ),
            Kpi(
                label=f"Putaways within {target} day{'s' if target != 1 else ''}",
                value=on_target / len(measured) if len(measured) else None,
                format="percent",
            ),
            Kpi(label="Picks confirmed", value=len(picks), format="integer"),
            Kpi(
                label="Average picking time",
                value=_mean(picks["Picking Time (hours)"]),
                format="number",
                unit="hours",
                note="Task creation to confirmation",
            ),
            Kpi(
                label="Average picking to goods issue",
                value=_mean(to_gi["Hours"]) if len(to_gi) else None,
                format="number",
                unit="hours",
                note=f"{matched_deliveries} deliveries matched"
                if deliveries is not None
                else "Add the outbound delivery list",
            ),
            Kpi(label="Open tasks", value=len(open_tasks), format="integer"),
        ]
        checks = [
            Check(
                "tasks_by_type",
                "Tasks by type = tasks",
                expected=len(tasks),
                actual=float(by_kind["Tasks"].sum()),
                tolerance=0,
            ),
            Check(
                "confirmed_plus_open",
                "Confirmed + open tasks = tasks",
                expected=len(tasks),
                actual=float(by_kind["Confirmed"].sum() + by_kind["Open"].sum()),
                tolerance=0,
            ),
            Check(
                "putaways_by_band",
                "Putaways by dock-to-stock band = putaways confirmed",
                expected=len(putaways),
                actual=float(by_band["Putaways"].sum()),
                tolerance=0,
            ),
        ]

        def stamp(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
            out = frame.copy()
            for column in columns:
                out[column] = pd.to_datetime(out[column]).dt.strftime("%Y-%m-%d %H:%M")
            return out

        task_columns = [
            "Warehouse Task",
            "Item",
            "Kind",
            "Process Type",
            "Document",
            "Product",
            "Product Description",
            "From Bin",
            "To Bin",
            "Quantity",
            "Created",
            "Confirmed",
            "Confirmed By",
        ]
        putaway_table = stamp(
            putaways[
                [*task_columns, "Goods Receipt Date", "Dock to Stock (days)", "Dock to Stock"]
            ],
            ["Created", "Confirmed"],
        )
        putaway_table["Goods Receipt Date"] = putaway_table["Goods Receipt Date"].dt.strftime(
            "%Y-%m-%d"
        )
        putaway_table = putaway_table.sort_values(
            ["Dock to Stock (days)", "Warehouse Task"],
            ascending=[False, True],
            kind="mergesort",
            na_position="last",
        ).reset_index(drop=True)
        pick_table = stamp(picks[[*task_columns, "Picking Time (hours)"]], ["Created", "Confirmed"])
        to_gi_table = (
            stamp(to_gi, ["Last Pick", "Goods Issue"])
            .sort_values(["Hours", "Document"], ascending=[False, True], kind="mergesort")
            .reset_index(drop=True)
        )
        open_table = stamp(
            open_tasks[[*task_columns, "Age (days)"]], ["Created", "Confirmed"]
        ).reset_index(drop=True)
        subtitle = f"EWM warehouse tasks up to {params.report_date:%d %B %Y}"
        number, integer = "number", "integer"
        dashboard = Dashboard(
            title=self.title,
            subtitle=subtitle,
            kpis=kpis,
            charts=[
                Chart(
                    id="dock-chart",
                    title="Putaways by dock to stock",
                    type="column",
                    table="dock-to-stock",
                    category="Dock to Stock",
                    series=[Series(name="Putaways", field="Putaways")],
                ),
                Chart(
                    id="month-chart",
                    title="Tasks confirmed by month",
                    type="stacked-bar",
                    table="by-month",
                    category="Month",
                    series=[Series(name=k, field=k) for k in KINDS],
                ),
            ],
            tables=[
                Table(
                    id="by-kind",
                    title="Tasks by type",
                    columns=[
                        Column(key="Task Type", label="Type"),
                        Column(key="Tasks", label="Tasks", format=integer),
                        Column(key="Confirmed", label="Confirmed", format=integer),
                        Column(key="Open", label="Open", format=integer),
                    ],
                    rows=rows_of(by_kind),
                ),
                Table(
                    id="dock-to-stock",
                    title="Dock to stock (goods receipt to putaway)",
                    columns=[
                        Column(key="Dock to Stock", label="Time"),
                        Column(key="Putaways", label="Putaways", format=integer),
                    ],
                    rows=rows_of(by_band),
                ),
                Table(
                    id="by-month",
                    title="Tasks confirmed by month",
                    columns=[
                        Column(key="Month", label="Month"),
                        *[Column(key=k, label=k, format=integer) for k in KINDS],
                        Column(
                            key="Average Dock to Stock (days)",
                            label="Dock to stock (days)",
                            format=number,
                        ),
                    ],
                    rows=rows_of(by_month),
                ),
                Table(
                    id="by-user",
                    title="Tasks confirmed by user",
                    columns=[
                        Column(key="User", label="User"),
                        *[Column(key=k, label=k, format=integer) for k in KINDS],
                        Column(key="Tasks Confirmed", label="Total", format=integer),
                    ],
                    rows=rows_of(by_user),
                    level="detail",
                ),
                Table(
                    id="slow-putaways",
                    title="Putaways (longest dock to stock first)",
                    columns=[
                        Column(key="Warehouse Task", label="Task"),
                        Column(key="Document", label="Delivery"),
                        Column(key="Product", label="Product"),
                        Column(key="Product Description", label="Description"),
                        Column(key="Goods Receipt Date", label="Goods receipt", format="date"),
                        Column(key="Confirmed", label="Putaway"),
                        Column(key="Dock to Stock (days)", label="Days", format=number),
                    ],
                    rows=rows_of(putaway_table),
                    total_rows=len(putaway_table),
                    level="detail",
                    filters=["Dock to Stock"],
                    searchable=["Product", "Document", "Warehouse Task"],
                ),
                Table(
                    id="open-tasks",
                    title="Open tasks (oldest first)",
                    columns=[
                        Column(key="Warehouse Task", label="Task"),
                        Column(key="Kind", label="Type"),
                        Column(key="Product", label="Product"),
                        Column(key="From Bin", label="From"),
                        Column(key="To Bin", label="To"),
                        Column(key="Created", label="Created"),
                        Column(key="Age (days)", label="Age (days)", format=number),
                    ],
                    rows=rows_of(open_table),
                    total_rows=len(open_table),
                    level="detail",
                    filters=["Kind"],
                    searchable=["Warehouse Task", "Product"],
                ),
            ],
            checks=[c.out() for c in checks],
            notes=[
                note
                for note in [
                    f"{cancelled} cancelled tasks are left out." if cancelled else "",
                    "Picking to goods issue needs the outbound delivery list."
                    if deliveries is None
                    else "",
                ]
                if note
            ],
        )
        return AnalysisResult(
            tables={
                "by_kind": by_kind,
                "dock_to_stock": by_band,
                "by_month": by_month,
                "by_user": by_user,
                "putaways": putaway_table,
                "picks": pick_table,
                "picking_to_goods_issue": to_gi_table,
                "open_tasks": open_table,
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
            "Tasks": "integer",
            "Confirmed": "integer",
            "Open": "integer",
            "Putaways": "integer",
            **{k: "integer" for k in KINDS},
            "Tasks Confirmed": "integer",
            "Quantity": "number",
            "Average Dock to Stock (days)": "number",
            "Dock to Stock (days)": "number",
            "Picking Time (hours)": "number",
            "Hours": "number",
            "Age (days)": "number",
        }
        by_band = TableBlock("Dock to stock", t["dock_to_stock"], formats, total_row=True)
        by_kind = TableBlock("Tasks by type", t["by_kind"], formats, total_row=True)
        kpi: dict[str, Any] = {k.label: k.value for k in result.metrics}

        def amount(value: object, unit: str) -> str:
            return (
                f"{float(value):.1f} {unit}" if isinstance(value, int | float) else "not available"
            )

        target = params.dock_to_stock_target_days
        within = kpi[f"Putaways within {target} day{'s' if target != 1 else ''}"]
        document = ReportDocument(
            title="Warehouse activity",
            subtitle=str(result.extras["subtitle"]),
            date_text=f"{params.report_date:%d %B %Y}",
            sections=[
                Section(
                    "Summary",
                    paragraphs=[
                        f"{kpi['Putaways confirmed']} putaways were confirmed, on average "
                        f"{amount(kpi['Average dock to stock'], 'days')} after goods receipt"
                        + (
                            f"; {float(within):.1%} within the target of {target} days"
                            if isinstance(within, int | float)
                            else ""
                        )
                        + f". {kpi['Picks confirmed']} picks took "
                        f"{amount(kpi['Average picking time'], 'hours')} on average; from the last "
                        "pick to goods issue: "
                        f"{amount(kpi['Average picking to goods issue'], 'hours')}. "
                        f"Open tasks: {kpi['Open tasks']}.",
                    ],
                    tables=[by_band, by_kind],
                    charts=[
                        ChartBlock(
                            "Putaways by dock to stock",
                            [str(b) for b in t["dock_to_stock"]["Dock to Stock"]],
                            {"Putaways": [float(v) for v in t["dock_to_stock"]["Putaways"]]},
                        )
                    ],
                ),
                Section(
                    "Method",
                    bullets=[
                        "Tasks are typed by warehouse process category (putaway, stock removal); "
                        "cancelled tasks are left out; confirmed tasks have a confirmation date.",
                        "Dock to stock: from the goods receipt date to the putaway confirmation.",
                        "Picking to goods issue: from the last stock removal of a delivery to its "
                        "goods issue in the outbound delivery list.",
                    ],
                ),
            ],
            checks=check_lines(result.checks),
        )
        name = f"Warehouse_Activity_{params.report_date:%Y-%m-%d}"
        blocks = [
            by_kind,
            by_band,
            TableBlock("By month", t["by_month"], formats),
            TableBlock("By user", t["by_user"], formats),
            TableBlock("Putaways", t["putaways"], formats),
            TableBlock("Picking to goods issue", t["picking_to_goods_issue"], formats),
            TableBlock("Open tasks", t["open_tasks"], formats),
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


ANALYSIS = WarehouseActivity()
