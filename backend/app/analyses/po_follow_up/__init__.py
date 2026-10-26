"""Purchase order follow-up: ME2N purchase orders against inbound deliveries.

Ferdinand's rule of 23 October 2026: trace each purchase order from its
creation date to the goods receipt date (delivery period) and say whether it
was delivered in full, comparing ordered and delivered quantities and values.
Definitions used (see docs/PLAN.md, Decisions):

- a PO line is an ME2N purchasing document item created in the period; lines
  with a deletion indicator or an order quantity of zero are left out and
  counted;
- received quantity of a line = the "Actual delivery qty" (or, when blank, the
  "Delivery Quantity") of its inbound delivery items with a goods receipt
  ("Act. Gds Mvmnt Date"); items are matched by purchase order and reference
  item, or by purchase order and material when the reference item is blank;
- received value = net order value x received quantity / order quantity (at
  most the ordered quantity);
- delivered in full when the received quantity reaches the ordered quantity;
- delivery period = goods receipt date - PO creation date (document date): to
  the first receipt, and to the last receipt of a line delivered in full;
- the open quantity from ME2N ("Still to be delivered") is shown next to the
  quantity traced in the inbound deliveries.

Ferdinand's addition of 25 October 2026: the ME2M report (same columns as ME2N)
gives the approval date ("Final Approval Date") and the required delivery date
("Delivery Date") of each PO line, next to its creation date ("Document Date"):

- days to approval = approval date - creation date;
- approval to receipt = last goods receipt - approval date (lines in full);
- on time when the last goods receipt is on or before the required delivery
  date; on time in full = delivered in full and on time, out of the lines
  with a required delivery date;
- an open line is overdue when its required delivery date is before the report
  date.
"""

from datetime import date
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field, model_validator

from app.analyses.base import Analysis, AnalysisResult, Check, InputSpec
from app.analyses.common.closing import material_code, plant_code, plant_names
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

IN_FULL, PARTLY, OPEN = "Delivered in full", "Partly delivered", "Not delivered"
STATUSES = [IN_FULL, PARTLY, OPEN]
PERIOD_BANDS = [
    "Up to 30 days",
    "31 to 60 days",
    "61 to 90 days",
    "91 to 180 days",
    "More than 180 days",
]


def period_band(days: float) -> str:
    for limit, band in zip((30, 60, 90, 180), PERIOD_BANDS, strict=False):
        if days <= limit:
            return band
    return PERIOD_BANDS[-1]


def _code(values: pd.Series) -> pd.Series:
    return material_code(values).astype(str)


def _text(values: pd.Series) -> pd.Series:
    return values.astype("string").str.strip().fillna("").astype(str)


def _rate(part: float, whole: float) -> float | None:
    return part / whole if whole else None


class Parameters(BaseModel):
    period_start: date = Field(title="POs created from", description="e.g. 1 July 2025.")
    period_end: date = Field(title="POs created up to", description="e.g. 30 June 2026.")
    report_date: date = Field(
        title="Report date", description="Date of the exports; open POs are aged to this date."
    )

    @model_validator(mode="after")
    def _order(self) -> "Parameters":
        if self.period_end < self.period_start:
            raise ValueError("The last creation date must not be before the first.")
        return self


def _params(params: BaseModel) -> Parameters:
    if not isinstance(params, Parameters):
        raise TypeError("Parameters of the wrong analysis.")
    return params


class PoFollowUp(Analysis):
    key = "po_follow_up"
    title = "Purchase order follow-up"
    version = "1.1.0"
    description = (
        "Purchase orders (ME2N) against inbound deliveries: delivery period from PO creation "
        "to goods receipt, lines delivered in full, received against ordered quantity and "
        "value, by supplier, plant and month, and the open POs with their age."
    )
    inputs = (
        InputSpec("orders", "me2n_purchase_orders", "Purchase orders (ME2N)"),
        InputSpec("deliveries", "inbound_deliveries", "Inbound deliveries"),
        InputSpec("plants", "ox10_plants", "Plant names (OX10)", required=False),
    )
    Parameters = Parameters

    def compute(self, data: dict[str, pd.DataFrame], params: BaseModel) -> AnalysisResult:
        params = _params(params)
        raw = data["orders"]
        supplier_name = _text(raw["Name of Supplier"])
        orders = pd.DataFrame(
            {
                "PO": _code(raw["Purchasing Document"]),
                "Item": _code(raw["Item"]),
                "Created": pd.to_datetime(raw["Document Date"]),
                "Approved": pd.to_datetime(raw["Final Approval Date"]),
                "Required Delivery": pd.to_datetime(raw["Delivery Date"]),
                "Supplier": _text(raw["Supplier/Supplying Plant"]),
                "Supplier Name": supplier_name,
                "Material": _code(raw["Material"]),
                "Description": _text(raw["Short Text"]),
                "Plant": plant_code(raw["Plant"]).astype(str),
                "Ordered Qty": raw["Order Quantity"].astype(float).fillna(0.0),
                "Ordered Value": raw["Net Order Value"].astype(float).fillna(0.0),
                "Open Qty (ME2N)": raw["Still to be delivered (qty)"].astype(float).fillna(0.0),
                "Deleted": _text(raw["Deletion Indicator"]) != "",
            }
        )
        start, end = pd.Timestamp(params.period_start), pd.Timestamp(params.period_end)
        in_period = orders["Created"].between(start, end)
        outside = int((~in_period).sum())
        orders = orders[in_period]
        left_out = orders["Deleted"] | (orders["Ordered Qty"] <= 0)
        deleted_or_zero = int(left_out.sum())
        orders = orders[~left_out].drop(columns="Deleted")
        orders = (
            orders.groupby(["PO", "Item"], sort=True)
            .agg(
                **{
                    c: (c, "first")
                    for c in [
                        "Created",
                        "Approved",
                        "Required Delivery",
                        "Supplier",
                        "Supplier Name",
                        "Material",
                        "Description",
                        "Plant",
                    ]
                },
                **{c: (c, "sum") for c in ["Ordered Qty", "Ordered Value", "Open Qty (ME2N)"]},
            )
            .reset_index()
        )

        inbound = data["deliveries"]
        actual = inbound["Actual delivery qty"].astype(float)
        gr = pd.DataFrame(
            {
                "Delivery": _text(inbound["Delivery"]),
                "PO": _code(inbound["Purchasing Document"]),
                "Item": _code(inbound["Reference Item"]),
                "Material": _code(inbound["Material"]),
                "Received Qty": actual.where(
                    actual.notna(), inbound["Delivery Quantity"].astype(float)
                ).fillna(0.0),
                "Receipt Date": pd.to_datetime(inbound["Act. Gds Mvmnt Date"]),
            }
        )
        not_received = int(gr["Receipt Date"].isna().sum())
        gr = gr[gr["Receipt Date"].notna() & (gr["PO"] != "")]
        by_item = gr["Item"] != ""
        keys = orders[["PO", "Item", "Material"]]
        matched = pd.concat(
            [
                gr[by_item].merge(keys.drop(columns="Material"), on=["PO", "Item"]),
                gr[~by_item]
                .drop(columns="Item")
                .merge(keys, on=["PO", "Material"])
                .drop_duplicates(["Delivery", "PO", "Material", "Received Qty", "Receipt Date"]),
            ],
            ignore_index=True,
        )
        order_index = pd.MultiIndex.from_frame(orders[["PO", "Item"]])
        unmatched = gr[
            ~gr["PO"].isin(set(orders["PO"]))
            | (by_item & ~pd.MultiIndex.from_frame(gr[["PO", "Item"]]).isin(order_index))
        ]
        receipts = (
            matched.groupby(["PO", "Item"], sort=True)
            .agg(
                **{
                    "Received Qty": ("Received Qty", "sum"),
                    "Receipts": ("Delivery", "nunique"),
                    "First Receipt": ("Receipt Date", "min"),
                    "Last Receipt": ("Receipt Date", "max"),
                }
            )
            .reset_index()
        )
        lines = orders.merge(receipts, on=["PO", "Item"], how="left")
        lines["Received Qty"] = lines["Received Qty"].fillna(0.0)
        lines["Receipts"] = lines["Receipts"].fillna(0).astype(int)
        lines["Filled Qty"] = lines[["Received Qty", "Ordered Qty"]].min(axis=1)
        lines["Received Value"] = (
            lines["Ordered Value"] * lines["Filled Qty"] / lines["Ordered Qty"]
        )
        lines["Status"] = [
            IN_FULL if r >= o else PARTLY if r > 0 else OPEN
            for r, o in zip(lines["Received Qty"], lines["Ordered Qty"], strict=True)
        ]
        full = lines["Status"] == IN_FULL
        lines["Days to First Receipt"] = (lines["First Receipt"] - lines["Created"]).dt.days.astype(
            float
        )
        lines["Delivery Period (days)"] = (
            (lines["Last Receipt"] - lines["Created"]).dt.days.astype(float).where(full)
        )
        lines["Days Late"] = (
            (lines["Last Receipt"] - lines["Required Delivery"]).dt.days.astype(float).where(full)
        )
        lines["Days to Approval"] = (lines["Approved"] - lines["Created"]).dt.days.astype(float)
        lines["Approval to Receipt (days)"] = (
            (lines["Last Receipt"] - lines["Approved"]).dt.days.astype(float).where(full)
        )
        lines["On Time"] = full & (lines["Days Late"] <= 0)
        report = pd.Timestamp(params.report_date)
        lines["Overdue"] = ~full & (lines["Required Delivery"] < report)
        lines["Age of Open PO (days)"] = (
            (report - lines["Created"]).dt.days.astype(float).where(~full)
        )
        lines["Not Traced vs ME2N"] = (
            lines["Ordered Qty"] - lines["Received Qty"] - lines["Open Qty (ME2N)"]
        )
        names = plant_names(data.get("plants"))
        lines["Plant Name"] = [names.get(p, "") for p in lines["Plant"]]
        lines["Month"] = lines["Created"].dt.strftime("%Y-%m")
        lines = lines.sort_values(["Created", "PO", "Item"], kind="mergesort").reset_index(
            drop=True
        )

        def group(part: pd.DataFrame) -> dict[str, Any]:
            done = part["Status"] == IN_FULL
            periods = part["Delivery Period (days)"].dropna()
            ordered, filled = float(part["Ordered Qty"].sum()), float(part["Filled Qty"].sum())
            ordered_value = float(part["Ordered Value"].sum())
            received_value = float(part["Received Value"].sum())
            return {
                "PO Lines": len(part),
                **{s: int((part["Status"] == s).sum()) for s in STATUSES},
                "Lines in Full": _rate(int(done.sum()), len(part)),
                "Quantity Received": _rate(filled, ordered),
                "Ordered Value": ordered_value,
                "Received Value": received_value,
                "Value Received": _rate(received_value, ordered_value),
                "Average Delivery Period (days)": float(periods.mean()) if len(periods) else None,
                "Longest Delivery Period (days)": float(periods.max()) if len(periods) else None,
            }

        def breakdown(columns: list[str]) -> pd.DataFrame:
            rows = [
                {
                    **dict(zip(columns, key if isinstance(key, tuple) else (key,), strict=True)),
                    **group(part),
                }
                for key, part in lines.groupby(columns, sort=True)
            ]
            return pd.DataFrame(rows)

        by_supplier = breakdown(["Supplier", "Supplier Name"]) if len(lines) else pd.DataFrame()
        if len(by_supplier):
            by_supplier = by_supplier.sort_values(["Value Received", "Supplier"], kind="mergesort")
        by_plant = breakdown(["Plant", "Plant Name"]) if len(lines) else pd.DataFrame()
        by_month = breakdown(["Month"]) if len(lines) else pd.DataFrame()
        delivered = lines[full]
        bands = pd.Series([period_band(d) for d in delivered["Delivery Period (days)"]], dtype=str)
        by_period = (
            pd.DataFrame(
                {"Delivery Period": bands, "Value": delivered["Received Value"].to_numpy()}
            )
            .groupby("Delivery Period")
            .agg(**{"PO Lines": ("Value", "size"), "Value": ("Value", "sum")})
            .reindex(PERIOD_BANDS, fill_value=0)
            .reset_index()
        )
        by_period["PO Lines"] = by_period["PO Lines"].astype(int)
        totals = group(lines) if len(lines) else {}
        open_lines = lines[~full].sort_values(
            ["Age of Open PO (days)", "PO", "Item"], ascending=[False, True, True], kind="mergesort"
        )

        with_required = lines["Required Delivery"].notna()
        full_with_required = full & with_required
        days_to_approval = lines["Days to Approval"].dropna()
        kpis = [
            Kpi(label="PO lines", value=len(lines), format="integer"),
            Kpi(
                label="Average days to approval",
                value=float(days_to_approval.mean()) if len(days_to_approval) else None,
                format="number",
                unit="days",
                note=f"PO creation to final approval; {int(lines['Approved'].isna().sum())} "
                "lines without an approval date",
            ),
            Kpi(
                label="On time in full",
                value=_rate(int(lines["On Time"].sum()), int(with_required.sum())),
                format="percent",
                note="Received in full by the required delivery date",
            ),
            Kpi(
                label="Delivered on time",
                value=_rate(
                    int((lines["On Time"] & with_required).sum()), int(full_with_required.sum())
                ),
                format="percent",
                note="Of the lines delivered in full",
            ),
            Kpi(
                label="Open lines past required date",
                value=int(lines["Overdue"].sum()),
                format="integer",
            ),
            Kpi(
                label="Lines delivered in full", value=totals.get("Lines in Full"), format="percent"
            ),
            Kpi(
                label="Quantity received",
                value=totals.get("Quantity Received"),
                format="percent",
                note="Received up to the ordered quantity",
            ),
            Kpi(label="Value received", value=totals.get("Value Received"), format="percent"),
            Kpi(
                label="Average delivery period",
                value=totals.get("Average Delivery Period (days)"),
                format="number",
                unit="days",
                note="PO creation to last goods receipt",
            ),
            Kpi(
                label="Open value",
                value=float((open_lines["Ordered Value"] - open_lines["Received Value"]).sum()),
                format="money",
                unit="RWF",
            ),
        ]
        traced = float(gr["Received Qty"].sum())
        checks = [
            Check(
                "lines_by_status",
                "Lines by status = PO lines",
                expected=len(lines),
                actual=float(sum((lines["Status"] == s).sum() for s in STATUSES)),
                tolerance=0,
            ),
            Check(
                "receipts_reconcile",
                "Received on PO lines + receipts not matched = goods receipts counted",
                expected=traced,
                actual=float(lines["Received Qty"].sum()) + float(unmatched["Received Qty"].sum()),
            ),
            Check(
                "suppliers_total",
                "Ordered value by supplier = ordered value",
                expected=float(lines["Ordered Value"].sum()),
                actual=float(by_supplier["Ordered Value"].sum()) if len(by_supplier) else 0.0,
            ),
        ]

        def dated(frame: pd.DataFrame) -> pd.DataFrame:
            out = frame.copy()
            for column in (
                "Created",
                "Approved",
                "Required Delivery",
                "First Receipt",
                "Last Receipt",
            ):
                out[column] = pd.to_datetime(out[column]).dt.strftime("%Y-%m-%d")
            return out

        line_columns = [
            "PO",
            "Item",
            "Created",
            "Approved",
            "Required Delivery",
            "Supplier",
            "Supplier Name",
            "Material",
            "Description",
            "Plant",
            "Plant Name",
            "Ordered Qty",
            "Received Qty",
            "Open Qty (ME2N)",
            "Not Traced vs ME2N",
            "Ordered Value",
            "Received Value",
            "Status",
            "Receipts",
            "First Receipt",
            "Last Receipt",
            "Days to First Receipt",
            "Delivery Period (days)",
            "Days Late",
            "On Time",
            "Days to Approval",
            "Approval to Receipt (days)",
            "Overdue",
            "Age of Open PO (days)",
        ]
        line_table = dated(lines[line_columns])
        open_table = dated(open_lines[line_columns])
        unmatched_table = unmatched.assign(
            **{"Receipt Date": unmatched["Receipt Date"].dt.strftime("%Y-%m-%d")}
        ).reset_index(drop=True)
        period = f"{params.period_start:%d %B %Y} to {params.period_end:%d %B %Y}"
        subtitle = f"Purchase orders created {period}"
        money, percent, number, integer = "money", "percent", "number", "integer"

        def rate_columns(first: list[Column]) -> list[Column]:
            return [
                *first,
                Column(key="PO Lines", label="Lines", format=integer),
                Column(key="Lines in Full", label="In full", format=percent),
                Column(key="Quantity Received", label="Quantity received", format=percent),
                Column(key="Ordered Value", label="Ordered (RWF)", format=money),
                Column(key="Value Received", label="Value received", format=percent),
                Column(key="Average Delivery Period (days)", label="Average days", format=number),
            ]

        dashboard = Dashboard(
            title=self.title,
            subtitle=subtitle,
            kpis=kpis,
            charts=[
                Chart(
                    id="period-chart",
                    title="Lines delivered in full by delivery period",
                    type="column",
                    table="by-period",
                    category="Delivery Period",
                    series=[Series(name="PO lines", field="PO Lines")],
                ),
                Chart(
                    id="month-chart",
                    title="Average delivery period by PO month (days)",
                    type="line",
                    table="by-month",
                    category="Month",
                    series=[Series(name="Average days", field="Average Delivery Period (days)")],
                ),
            ],
            tables=[
                Table(
                    id="by-period",
                    title="Delivery period (lines delivered in full)",
                    columns=[
                        Column(key="Delivery Period", label="PO creation to receipt"),
                        Column(key="PO Lines", label="Lines", format=integer),
                        Column(key="Value", label="Value (RWF)", format=money),
                    ],
                    rows=rows_of(by_period),
                ),
                Table(
                    id="by-month",
                    title="By PO month",
                    columns=rate_columns([Column(key="Month", label="Month")]),
                    rows=rows_of(by_month),
                ),
                Table(
                    id="by-plant",
                    title="By plant",
                    columns=rate_columns(
                        [Column(key="Plant", label="Plant"), Column(key="Plant Name", label="Name")]
                    ),
                    rows=rows_of(by_plant),
                ),
                Table(
                    id="by-supplier",
                    title="By supplier (lowest value received first)",
                    columns=rate_columns(
                        [
                            Column(key="Supplier", label="Supplier"),
                            Column(key="Supplier Name", label="Name"),
                        ]
                    ),
                    rows=rows_of(by_supplier),
                    total_rows=len(by_supplier),
                    level="detail",
                    searchable=["Supplier", "Supplier Name"],
                ),
                Table(
                    id="open-lines",
                    title="PO lines not delivered in full (oldest first)",
                    columns=[
                        Column(key="PO", label="PO"),
                        Column(key="Item", label="Item"),
                        Column(key="Created", label="Created", format="date"),
                        Column(key="Approved", label="Approved", format="date"),
                        Column(key="Required Delivery", label="Required by", format="date"),
                        Column(key="Supplier Name", label="Supplier"),
                        Column(key="Material", label="Material"),
                        Column(key="Description", label="Description"),
                        Column(key="Ordered Qty", label="Ordered", format=number),
                        Column(key="Received Qty", label="Received", format=number),
                        Column(key="Status", label="Status"),
                        Column(key="Age of Open PO (days)", label="Age (days)", format=number),
                    ],
                    rows=rows_of(open_table),
                    total_rows=len(open_table),
                    level="detail",
                    filters=["Status", "Plant"],
                    searchable=["PO", "Material", "Supplier Name"],
                ),
            ],
            checks=[c.out() for c in checks],
            notes=[
                note
                for note in [
                    f"{deleted_or_zero} PO lines deleted or with no quantity are left out."
                    if deleted_or_zero
                    else "",
                    f"{outside} PO lines created outside the period are left out."
                    if outside
                    else "",
                    f"{not_received} inbound delivery items without a goods receipt are left out."
                    if not_received
                    else "",
                    f"{len(unmatched)} goods receipts refer to no PO line of the period."
                    if len(unmatched)
                    else "",
                ]
                if note
            ],
        )
        return AnalysisResult(
            tables={
                "lines": line_table,
                "open_lines": open_table,
                "by_period": by_period,
                "by_month": by_month,
                "by_plant": by_plant,
                "by_supplier": by_supplier,
                "unmatched_receipts": unmatched_table,
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
            "PO Lines": "integer",
            **{s: "integer" for s in STATUSES},
            "Lines in Full": "percent",
            "Quantity Received": "percent",
            "Value Received": "percent",
            "Ordered Value": "money",
            "Received Value": "money",
            "Value": "money",
            "Ordered Qty": "number",
            "Received Qty": "number",
            "Open Qty (ME2N)": "number",
            "Not Traced vs ME2N": "number",
            "Receipts": "integer",
            "Average Delivery Period (days)": "number",
            "Longest Delivery Period (days)": "number",
            "Days to First Receipt": "number",
            "Delivery Period (days)": "number",
            "Days Late": "number",
            "Days to Approval": "number",
            "Approval to Receipt (days)": "number",
            "Age of Open PO (days)": "number",
        }
        by_period = TableBlock("Delivery period", t["by_period"], formats, total_row=True)
        by_plant = TableBlock("By plant", t["by_plant"], formats)
        kpi: dict[str, Any] = {k.label: k.value for k in result.metrics}

        def pct(value: object) -> str:
            return f"{float(value):.1%}" if isinstance(value, int | float) else "not available"

        average = kpi["Average delivery period"]
        approval = kpi["Average days to approval"]
        document = ReportDocument(
            title="Purchase order follow-up",
            subtitle=str(result.extras["subtitle"]),
            date_text=f"{params.report_date:%d %B %Y}",
            sections=[
                Section(
                    "Summary",
                    paragraphs=[
                        f"{pct(kpi['Lines delivered in full'])} of {kpi['PO lines']} PO lines were "
                        f"delivered in full; {pct(kpi['Quantity received'])} of the ordered "
                        f"quantity and {pct(kpi['Value received'])} of the ordered value were "
                        "received. "
                        + (
                            f"Lines delivered in full took {float(average):.0f} days on average "
                            "from PO creation to the last goods receipt. "
                            if isinstance(average, int | float)
                            else ""
                        )
                        + f"Value still open: RWF {float(kpi['Open value'] or 0):,.0f}.",
                        f"{pct(kpi['On time in full'])} of the lines with a required delivery "
                        "date were received in full by that date; "
                        f"{kpi['Open lines past required date']} open lines are past it. "
                        + (
                            f"Approval took {float(approval):.0f} days on average after PO "
                            "creation."
                            if isinstance(approval, int | float)
                            else ""
                        ),
                    ],
                    tables=[by_period],
                    charts=[
                        ChartBlock(
                            "Lines delivered in full by delivery period",
                            [str(b) for b in t["by_period"]["Delivery Period"]],
                            {"PO lines": [float(v) for v in t["by_period"]["PO Lines"]]},
                        )
                    ],
                ),
                Section("By plant", tables=[by_plant]),
                Section(
                    "Method",
                    bullets=[
                        "PO lines: ME2N items created in the period, not deleted. Receipts: "
                        "inbound delivery items with a goods receipt, matched by purchase order "
                        "and item (or material).",
                        "Delivered in full: received quantity at least the ordered quantity. "
                        "Received value = net order value x received / ordered quantity.",
                        "Delivery period: from the PO document date to the last goods receipt. "
                        "Approval: the final approval date (ME2M / ME2N). On time: last goods "
                        "receipt on or before the required delivery date.",
                    ],
                ),
            ],
            checks=check_lines(result.checks),
        )
        name = f"PO_Follow_Up_{params.period_start:%Y-%m-%d}_{params.period_end:%Y-%m-%d}"
        blocks = [
            by_period,
            TableBlock("By month", t["by_month"], formats),
            by_plant,
            TableBlock("By supplier", t["by_supplier"], formats),
            TableBlock("Open PO lines", t["open_lines"], formats),
            TableBlock("PO lines", t["lines"], formats),
            TableBlock("Receipts not matched", t["unmatched_receipts"], formats),
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


ANALYSIS = PoFollowUp()
