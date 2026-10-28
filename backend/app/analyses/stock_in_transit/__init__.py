"""Stock in transit between plants: MB5T, traced through MB51.

Ferdinand's rule of 23 October 2026: monitor the stock that stays long without
being received by the receiving plant. In MB51, trace each stock transport
order (STO: the purchase order of the goods issue, movement type 641) and map
it to the STO in MB5T to see how long the stock stays in transit; the time from
goods issue (641) to goods receipt (101) is the transit time. The common ID is
the outbound delivery reference and the STO.

Definitions used (see docs/PLAN.md, Decisions):

- MB51 lines of movement types 641 (goods issue for the STO) and 101 (goods
  receipt) with the same purchase order and material; reversals 642 and 102
  reduce the latest issue or receipt (same reference first);
- receipts are matched to issues with the same reference (outbound delivery)
  first, then to the oldest issues still open (first in, first out);
- transit time = receipt posting date - issue posting date, per quantity matched;
- days in transit of an MB5T line = report date - the oldest posting date of the
  issues still open for its STO and material.

Ferdinand's answers of 26 October 2026: the outbound delivery is in "Reference"
on 641, 101 and their reversals 642, 102 and 122; the STO creation date comes
from the ME2M report (document date of the purchase order), so the analysis
also measures STO creation -> goods issue (641) -> goods receipt (101).

Ferdinand's corrections of 28 October 2026: every MB5T line is a line in transit
(the count matches the MB5T document; lines of the same STO and material are not
merged), and when MB5T gives no value for a line, its value is taken from the
goods issue (641) of the outbound delivery in MB51: the open quantity at the
641's value per unit. The value of the outbound delivery (OBD) in MB51 is shown on
every line and per material, also where MB5T has a value.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from app.analyses.base import Analysis, AnalysisResult, Check, InputSpec
from app.analyses.common.closing import material_code, plant_code, plant_names
from app.analyses.dashboard import Chart, Column, Dashboard, Kpi, Series, Table, rows_of
from app.datasets import parse_dates
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
from app.reporting.interactive import check_rows, dashboard_file
from app.reporting.slides import build_pptx
from app.reporting.word import build_docx

GOODS_ISSUE, ISSUE_REVERSAL, GOODS_RECEIPT = "641", "642", "101"
RECEIPT_REVERSALS = ("102", "122")  # reversal of the goods receipt, return delivery
NOT_ISSUED = "No goods issue in MB51"
AGE_BANDS = [
    "Up to 7 days",
    "8 to 30 days",
    "31 to 60 days",
    "61 to 90 days",
    "More than 90 days",
    NOT_ISSUED,
]
TOLERANCE_QTY = 0.001


def age_band(days: float | None) -> str:
    if days is None or pd.isna(days):
        return NOT_ISSUED
    for limit, band in zip((7, 30, 60, 90), AGE_BANDS, strict=False):
        if days <= limit:
            return band
    return AGE_BANDS[4]


@dataclass
class Movement:
    day: pd.Timestamp
    quantity: float
    reference: str
    plant: str
    unit_value: float = 0.0  # RWF per unit (641: amount / quantity)


@dataclass
class Traced:
    legs: list[dict[str, Any]] = field(default_factory=list)  # received quantities
    open_issues: list[Movement] = field(default_factory=list)
    receipts_without_issue: float = 0.0


def _reverse(lines: list[Movement], reversals: list[Movement]) -> list[Movement]:
    """Take each reversal off the latest line with its reference, else the latest line."""
    lines = [Movement(m.day, m.quantity, m.reference, m.plant, m.unit_value) for m in lines]
    for reversal in reversals:
        left = reversal.quantity
        for same_reference in (True, False):
            for line in reversed(lines):
                if left <= 0:
                    break
                if same_reference and line.reference != reversal.reference:
                    continue
                taken = min(line.quantity, left)
                line.quantity -= taken
                left -= taken
    return [m for m in lines if m.quantity > TOLERANCE_QTY]


def trace(issues: list[Movement], receipts: list[Movement]) -> Traced:
    """Match receipts to issues: same reference first, then oldest issue first."""
    issues = sorted(issues, key=lambda m: (m.day, m.reference))
    open_qty = [m.quantity for m in issues]
    traced = Traced()
    for receipt in sorted(receipts, key=lambda m: (m.day, m.reference)):
        left = receipt.quantity
        for same_reference in (True, False):
            for index, issue in enumerate(issues):
                if left <= TOLERANCE_QTY:
                    break
                if open_qty[index] <= TOLERANCE_QTY:
                    continue
                if same_reference and issue.reference != receipt.reference:
                    continue
                taken = min(open_qty[index], left)
                open_qty[index] -= taken
                left -= taken
                traced.legs.append(
                    {
                        "Reference": issue.reference,
                        "Supplying Plant": issue.plant,
                        "Receiving Plant": receipt.plant,
                        "Goods Issue Date": issue.day,
                        "Goods Receipt Date": receipt.day,
                        "Quantity": taken,
                        "Transit Days": float((receipt.day - issue.day).days),
                    }
                )
        traced.receipts_without_issue += max(left, 0.0)
    traced.open_issues = [
        Movement(m.day, q, m.reference, m.plant, m.unit_value)
        for m, q in zip(issues, open_qty, strict=True)
        if q > TOLERANCE_QTY
    ]
    return traced


class Parameters(BaseModel):
    report_date: date = Field(
        title="MB5T report date",
        description="Date of the MB5T stock in transit, e.g. 31 July 2026.",
    )
    long_transit_days: int = Field(
        default=30,
        ge=1,
        title="Long transit (days)",
        description="Stock in transit longer than this is flagged.",
    )


def _params(params: BaseModel) -> Parameters:
    if not isinstance(params, Parameters):
        raise TypeError("Parameters of the wrong analysis.")
    return params


def _code(values: pd.Series) -> pd.Series:
    return material_code(values).astype(str)


class StockInTransit(Analysis):
    key = "stock_in_transit"
    title = "Stock in transit"
    version = "1.4.0"
    description = (
        "Stock in transit between plants (MB5T) with the days since its goods issue, traced "
        "in MB51 by STO and outbound delivery (641 goods issue, 101 goods receipt), and the "
        "transit time of the transfers already received, by supplying and receiving plant."
    )
    inputs = (
        InputSpec("in_transit", "mb5t_stock_in_transit", "Stock in transit (MB5T)"),
        InputSpec("movements", "mb51_material_documents", "Goods movements (MB51)"),
        InputSpec(
            "orders",
            "me2n_purchase_orders",
            "STO creation dates (ME2M / ME2N)",
            required=False,
        ),
        InputSpec("plants", "ox10_plants", "Plant names (OX10)", required=False),
    )
    Parameters = Parameters

    def compute(self, data: dict[str, pd.DataFrame], params: BaseModel) -> AnalysisResult:
        params = _params(params)
        report = pd.Timestamp(params.report_date)
        names = plant_names(data.get("plants"))
        raw = data["movements"]
        moves = pd.DataFrame(
            {
                "Type": raw["Movement Type"].astype("string").str.strip().fillna("").astype(str),
                "STO": _code(raw["Purchase order"]),
                "Reference": _code(raw["Reference"]),
                "Material": _code(raw["Material"]),
                "Plant": plant_code(raw["Plant"]).astype(str),
                "Day": parse_dates(raw["Posting Date"]),
                "Quantity": raw["Quantity"].astype(float).fillna(0.0).abs(),
                "Amount": raw["Amt.in Loc.Cur."].astype(float).fillna(0.0).abs(),
            }
        )
        types = {GOODS_ISSUE, ISSUE_REVERSAL, GOODS_RECEIPT, *RECEIPT_REVERSALS}
        moves = moves[moves["Type"].isin(types) & (moves["STO"] != "") & moves["Day"].notna()]
        stos = set(moves.loc[moves["Type"] == GOODS_ISSUE, "STO"])
        moves = moves[moves["STO"].isin(stos)]

        legs: list[dict[str, Any]] = []
        open_rows: list[dict[str, Any]] = []
        unmatched_receipts = 0.0
        for (sto, material), part in moves.groupby(["STO", "Material"], sort=True):

            def lines(kind: str, part: pd.DataFrame = part) -> list[Movement]:
                chosen = part[part["Type"] == kind]
                return [
                    Movement(d, q, r, p, a / q if q else 0.0)
                    for d, q, r, p, a in zip(
                        chosen["Day"],
                        chosen["Quantity"],
                        chosen["Reference"],
                        chosen["Plant"],
                        chosen["Amount"],
                        strict=True,
                    )
                ]

            issues = _reverse(lines(GOODS_ISSUE), lines(ISSUE_REVERSAL))
            receipts = _reverse(
                lines(GOODS_RECEIPT), [m for kind in RECEIPT_REVERSALS for m in lines(kind)]
            )
            traced = trace(issues, receipts)
            unmatched_receipts += traced.receipts_without_issue
            legs += [{"STO": sto, "Material": material, **leg} for leg in traced.legs]
            open_rows += [
                {
                    "STO": sto,
                    "Material": material,
                    "Reference": m.reference,
                    "Supplying Plant": m.plant,
                    "Goods Issue Date": m.day,
                    "Open Qty": m.quantity,
                    "Open Value": m.quantity * m.unit_value,
                }
                for m in traced.open_issues
            ]
        leg_columns = [
            "STO",
            "Material",
            "Reference",
            "Supplying Plant",
            "Receiving Plant",
            "Goods Issue Date",
            "Goods Receipt Date",
            "Quantity",
            "Transit Days",
        ]
        received = pd.DataFrame(legs, columns=leg_columns)
        # STO creation date (ME2M / ME2N document date) of each purchase order.
        orders = data.get("orders")
        created: dict[str, pd.Timestamp] = {}
        if orders is not None:
            dates = pd.DataFrame(
                {
                    "STO": _code(orders["Purchasing Document"]),
                    "Created": pd.to_datetime(orders["Document Date"]),
                }
            ).dropna()
            created = {str(k): v for k, v in dates.groupby("STO")["Created"].min().items()}
        received["STO Created"] = pd.to_datetime(received["STO"].map(created))
        received["Days STO to Goods Issue"] = (
            received["Goods Issue Date"] - received["STO Created"]
        ).dt.days.astype(float)
        received["Days STO to Goods Receipt"] = (
            received["Goods Receipt Date"] - received["STO Created"]
        ).dt.days.astype(float)
        still_open = pd.DataFrame(
            open_rows,
            columns=[
                "STO",
                "Material",
                "Reference",
                "Supplying Plant",
                "Goods Issue Date",
                "Open Qty",
                "Open Value",
            ],
        )

        # MB5T lines (every line, as in the document) with the age of the issues still
        # open in MB51 for their STO and material.
        mb5t = data["in_transit"]
        items = mb5t["Item"] if "Item" in mb5t else pd.Series("", index=mb5t.index)
        transit = pd.DataFrame(
            {
                "MB5T Line": range(1, len(mb5t) + 1),
                "STO": _code(mb5t["Purchasing Document"]),
                "Item": _code(items),
                "Supplying Plant": plant_code(mb5t["Supplying Plant"]).astype(str),
                "Receiving Plant": plant_code(mb5t["Plant"]).astype(str),
                "Material": _code(mb5t["Material"]),
                "Material Description": mb5t["Material Description"]
                .astype("string")
                .fillna("")
                .astype(str),
                "Quantity": mb5t["Quantity"].astype(float).fillna(0.0).to_numpy(),
                "MB5T Value": mb5t["Amt.in Loc.Cur."].astype(float).fillna(0.0).to_numpy(),
            }
        )
        open_columns = [
            "Oldest Goods Issue",
            "Open Qty in MB51",
            "Open Value in MB51",
            "Average Days in Transit",
            "Delivery References",
        ]
        if len(still_open):
            open_by_line = (
                still_open.assign(
                    Weighted=still_open["Open Qty"]
                    * (report - still_open["Goods Issue Date"]).dt.days
                )
                .groupby(["STO", "Material"], sort=True)
                .agg(
                    **{
                        "Oldest Goods Issue": ("Goods Issue Date", "min"),
                        "Open Qty in MB51": ("Open Qty", "sum"),
                        "Open Value in MB51": ("Open Value", "sum"),
                        "Weighted": ("Weighted", "sum"),
                        "Delivery References": (
                            "Reference",
                            lambda r: "; ".join(sorted({x for x in r if x})),
                        ),
                    }
                )
                .reset_index()
            )
            open_by_line["Average Days in Transit"] = (
                open_by_line["Weighted"] / open_by_line["Open Qty in MB51"]
            )
            transit = transit.merge(
                open_by_line.drop(columns="Weighted"), on=["STO", "Material"], how="left"
            )
        else:
            for column in open_columns:
                transit[column] = None
            transit["Oldest Goods Issue"] = pd.to_datetime(transit["Oldest Goods Issue"])
        for column in ("Open Qty in MB51", "Open Value in MB51", "Average Days in Transit"):
            transit[column] = transit[column].astype(float)
        # Value: MB5T's amount; when MB5T has none, the MB51 goods issue value of the
        # STO and material, shared over its MB5T lines by quantity.
        group = ["STO", "Material"]
        group_qty = transit.groupby(group)["Quantity"].transform("sum")
        group_lines = transit.groupby(group)["Quantity"].transform("size")
        share = (transit["Quantity"] / group_qty).where(group_qty != 0, 1.0 / group_lines)
        mb51_value = (transit["Open Value in MB51"].fillna(0.0) * share).astype(float)
        from_mb51 = (transit["MB5T Value"].abs() <= TOLERANCE_QTY) & (mb51_value > 0)
        transit["Value"] = transit["MB5T Value"].where(~from_mb51, mb51_value)
        transit["OBD Value (MB51)"] = mb51_value
        transit["Value Source"] = ["MB51 goods issue" if m else "MB5T" for m in from_mb51]
        # The MB51 comparison is per STO and material: shown on its first MB5T line only,
        # so the totals are not counted twice.
        first = ~transit.duplicated(group)
        transit["Difference with MB51"] = (
            group_qty - transit["Open Qty in MB51"].fillna(0.0)
        ).where(first)
        transit["Open Qty in MB51"] = transit["Open Qty in MB51"].where(first)
        transit = transit.drop(columns=["Open Value in MB51"])
        transit["Days in Transit"] = (report - transit["Oldest Goods Issue"]).dt.days.astype(float)
        transit["STO Created"] = pd.to_datetime(transit["STO"].map(created))
        transit["Days Since STO Created"] = (report - transit["STO Created"]).dt.days.astype(float)
        transit["Age"] = [age_band(d) for d in transit["Days in Transit"]]
        transit["Long Transit"] = transit["Days in Transit"] > params.long_transit_days
        transit["Delivery References"] = transit["Delivery References"].fillna("")
        for column in ("Supplying", "Receiving"):
            transit[f"{column} Plant Name"] = [names.get(p, "") for p in transit[f"{column} Plant"]]
        transit = transit.sort_values(
            ["Days in Transit", "Value", "STO", "Material", "MB5T Line"],
            ascending=[False, False, True, True, True],
            kind="mergesort",
            na_position="first",
        ).reset_index(drop=True)

        by_age = (
            transit.groupby("Age")
            .agg(**{"Lines": ("STO", "size"), "Value": ("Value", "sum")})
            .reindex(AGE_BANDS, fill_value=0)
            .reset_index()
        )
        by_age["Lines"] = by_age["Lines"].astype(int)

        def plant_summary(column: str) -> pd.DataFrame:
            in_transit = transit.groupby(column).agg(
                **{
                    "Lines in Transit": ("STO", "size"),
                    "Value in Transit": ("Value", "sum"),
                    "Long Transit Lines": ("Long Transit", "sum"),
                }
            )
            if len(received):
                weighted = received.assign(W=received["Quantity"] * received["Transit Days"])
                done = weighted.groupby(column).agg(
                    **{
                        "Received Transfers": ("STO", "size"),
                        "W": ("W", "sum"),
                        "Received Qty": ("Quantity", "sum"),
                        "Longest Transit Days": ("Transit Days", "max"),
                    }
                )
                done["Average Transit Days"] = done["W"] / done["Received Qty"]
                done = done.drop(columns=["W", "Received Qty"])
            else:
                done = pd.DataFrame(
                    columns=["Received Transfers", "Longest Transit Days", "Average Transit Days"]
                )
            out = in_transit.join(done, how="outer").reset_index().rename(columns={"index": column})
            out = out.rename(columns={out.columns[0]: "Plant"})
            out.insert(1, "Plant Name", [names.get(str(p), "") for p in out["Plant"]])
            for count in ("Lines in Transit", "Long Transit Lines", "Received Transfers"):
                out[count] = out[count].fillna(0).astype(int)
            out["Value in Transit"] = out["Value in Transit"].astype(float).fillna(0.0)
            return out.sort_values("Plant", kind="mergesort").reset_index(drop=True)

        by_material = (
            transit.groupby("Material", sort=True)
            .agg(
                **{
                    "Material Description": ("Material Description", "max"),
                    "Lines in Transit": ("STO", "size"),
                    "STOs": ("STO", "nunique"),
                    "Quantity": ("Quantity", "sum"),
                    "MB5T Value": ("MB5T Value", "sum"),
                    "OBD Value (MB51)": ("OBD Value (MB51)", "sum"),
                    "Value in Transit": ("Value", "sum"),
                    "Long Transit Lines": ("Long Transit", "sum"),
                    "Outbound Deliveries": (
                        "Delivery References",
                        lambda r: "; ".join(
                            sorted({x for refs in r for x in str(refs).split("; ") if x})
                        ),
                    ),
                }
            )
            .reset_index()
        )
        by_material["Long Transit Lines"] = by_material["Long Transit Lines"].astype(int)
        by_material = by_material.sort_values(
            ["Value in Transit", "Material"], ascending=[False, True], kind="mergesort"
        ).reset_index(drop=True)

        by_receiving = plant_summary("Receiving Plant")
        by_supplying = plant_summary("Supplying Plant")

        total_value = float(transit["Value"].sum())
        long_lines = transit[transit["Long Transit"]]
        received_qty = float(received["Quantity"].sum())
        average_transit = (
            float((received["Quantity"] * received["Transit Days"]).sum()) / received_qty
            if received_qty
            else None
        )

        def weighted(days: str) -> float | None:
            known = received[received[days].notna()]
            quantity = float(known["Quantity"].sum())
            return float((known["Quantity"] * known[days]).sum()) / quantity if quantity else None

        open_mask = transit["Open Qty in MB51"].notna() & transit["Average Days in Transit"].notna()
        open_qty = float(transit.loc[open_mask, "Open Qty in MB51"].sum())
        average_open = (
            float(
                (
                    transit.loc[open_mask, "Open Qty in MB51"]
                    * transit.loc[open_mask, "Average Days in Transit"]
                ).sum()
            )
            / open_qty
            if open_qty
            else None
        )
        long = params.long_transit_days
        kpis = [
            Kpi(label="Value in transit", value=total_value, format="money", unit="RWF"),
            Kpi(label="Lines in transit", value=len(transit), format="integer"),
            Kpi(
                label="Value of the outbound deliveries (MB51)",
                value=float(transit["OBD Value (MB51)"].sum()),
                format="money",
                unit="RWF",
                note="641 goods issue value of the quantity still in transit",
            ),
            Kpi(
                label=f"In transit more than {long} days",
                value=len(long_lines),
                format="integer",
                note=f"RWF {float(long_lines['Value'].sum()):,.0f}",
            ),
            Kpi(
                label="Average days in transit (open)",
                value=average_open,
                format="number",
                unit="days",
            ),
            Kpi(
                label="Average transit time (received)",
                value=average_transit,
                format="number",
                unit="days",
                note="From goods issue (641) to goods receipt (101)",
            ),
            Kpi(
                label="Average STO creation to goods issue",
                value=weighted("Days STO to Goods Issue"),
                format="number",
                unit="days",
                note="ME2M document date to 641" if created else "Add the ME2M report",
            ),
            Kpi(
                label="Average STO creation to goods receipt",
                value=weighted("Days STO to Goods Receipt"),
                format="number",
                unit="days",
                note="ME2M document date to 101" if created else "Add the ME2M report",
            ),
            Kpi(
                label="Lines without a goods issue in MB51",
                value=int((transit["Age"] == NOT_ISSUED).sum()),
                format="integer",
            ),
        ]
        issued = float(moves.loc[moves["Type"] == GOODS_ISSUE, "Quantity"].sum()) - float(
            moves.loc[moves["Type"] == ISSUE_REVERSAL, "Quantity"].sum()
        )
        checks = [
            Check(
                "age_total",
                "Value by age = value in transit",
                expected=total_value,
                actual=float(by_age["Value"].sum()),
            ),
            Check(
                "issues_traced",
                "Issued quantity = received quantity matched + quantity still open",
                expected=issued,
                actual=received_qty + float(still_open["Open Qty"].sum()),
            ),
            Check(
                "materials_total",
                "Value in transit by material = value in transit",
                expected=total_value,
                actual=float(by_material["Value in Transit"].sum()),
            ),
            Check(
                "plants_total",
                "Value in transit by receiving plant = value in transit",
                expected=total_value,
                actual=float(by_receiving["Value in Transit"].sum()) if len(by_receiving) else 0.0,
            ),
        ]

        transit_table = transit.drop(columns=["Long Transit"]).copy()
        for column in ("Oldest Goods Issue", "STO Created"):
            transit_table[column] = transit_table[column].dt.strftime("%Y-%m-%d")
        received_table = received.copy()
        for column in ("STO Created", "Goods Issue Date", "Goods Receipt Date"):
            received_table[column] = pd.to_datetime(received_table[column]).dt.strftime("%Y-%m-%d")
        received_table = received_table.sort_values(
            ["Transit Days", "STO", "Material"], ascending=[False, True, True], kind="mergesort"
        ).reset_index(drop=True)
        subtitle = f"MB5T of {params.report_date:%d %B %Y}"
        money, number = "money", "number"
        plant_columns = [
            Column(key="Plant", label="Plant"),
            Column(key="Plant Name", label="Name"),
            Column(key="Lines in Transit", label="Lines in transit", format="integer"),
            Column(key="Value in Transit", label="Value in transit (RWF)", format=money),
            Column(key="Long Transit Lines", label=f"Over {long} days", format="integer"),
            Column(key="Received Transfers", label="Received", format="integer"),
            Column(key="Average Transit Days", label="Average transit days", format=number),
            Column(key="Longest Transit Days", label="Longest", format=number),
        ]
        dashboard = Dashboard(
            title=self.title,
            subtitle=subtitle,
            kpis=kpis,
            charts=[
                Chart(
                    id="age-chart",
                    title="Value in transit by age (RWF)",
                    type="column",
                    table="by-age",
                    category="Age",
                    format=money,
                    series=[Series(name="Value", field="Value")],
                ),
                Chart(
                    id="receiving-chart",
                    title="Average transit time by receiving plant (days)",
                    type="bar",
                    table="by-receiving",
                    category="Plant",
                    limit=15,
                    series=[Series(name="Average transit days", field="Average Transit Days")],
                ),
            ],
            tables=[
                Table(
                    id="by-age",
                    title="Stock in transit by age",
                    columns=[
                        Column(key="Age", label="Days since goods issue"),
                        Column(key="Lines", label="Lines", format="integer"),
                        Column(key="Value", label="Value (RWF)", format=money),
                    ],
                    rows=rows_of(by_age),
                ),
                Table(
                    id="by-material",
                    title="By material",
                    columns=[
                        Column(key="Material", label="Material"),
                        Column(key="Material Description", label="Description"),
                        Column(key="Lines in Transit", label="Lines", format="integer"),
                        Column(key="Quantity", label="Quantity", format=number),
                        Column(key="MB5T Value", label="MB5T value (RWF)", format=money),
                        Column(key="OBD Value (MB51)", label="OBD value, MB51 (RWF)", format=money),
                        Column(
                            key="Value in Transit", label="Value in transit (RWF)", format=money
                        ),
                        Column(
                            key="Long Transit Lines", label=f"Over {long} days", format="integer"
                        ),
                        Column(key="Outbound Deliveries", label="Outbound deliveries"),
                    ],
                    rows=rows_of(by_material),
                    searchable=["Material", "Material Description", "Outbound Deliveries"],
                ),
                Table(
                    id="by-receiving",
                    title="By receiving plant",
                    columns=plant_columns,
                    rows=rows_of(by_receiving),
                ),
                Table(
                    id="by-supplying",
                    title="By supplying plant",
                    columns=plant_columns,
                    rows=rows_of(by_supplying),
                ),
                Table(
                    id="in-transit",
                    title="Stock in transit (longest first)",
                    columns=[
                        Column(key="STO", label="STO"),
                        Column(key="Delivery References", label="Outbound delivery"),
                        Column(key="Supplying Plant", label="From"),
                        Column(key="Receiving Plant", label="To"),
                        Column(key="Material", label="Material"),
                        Column(key="Material Description", label="Description"),
                        Column(key="Quantity", label="Quantity", format=number),
                        Column(key="Value", label="Value (RWF)", format=money),
                        Column(key="OBD Value (MB51)", label="OBD value, MB51 (RWF)", format=money),
                        Column(key="Value Source", label="Value from"),
                        Column(key="Oldest Goods Issue", label="Goods issue", format="date"),
                        Column(key="Days in Transit", label="Days", format=number),
                        Column(key="Difference with MB51", label="Qty not traced", format=number),
                    ],
                    rows=rows_of(transit_table),
                    total_rows=len(transit_table),
                    level="detail",
                    filters=["Age", "Receiving Plant", "Supplying Plant"],
                    searchable=["STO", "Material", "Material Description", "Delivery References"],
                ),
            ],
            checks=[c.out() for c in checks],
            notes=[
                note
                for note in [
                    f"Receipts of {unmatched_receipts:,.0f} units have no matching goods issue "
                    "in MB51."
                    if unmatched_receipts > TOLERANCE_QTY
                    else "",
                    f"{int(from_mb51.sum())} lines have no value in MB5T: their value is "
                    "that of the goods issue (641) of the outbound delivery in MB51."
                    if from_mb51.any()
                    else "",
                ]
                if note
            ],
        )
        return AnalysisResult(
            tables={
                "in_transit": transit_table,
                "by_age": by_age,
                "by_material": by_material,
                "by_receiving": by_receiving,
                "by_supplying": by_supplying,
                "received": received_table,
            },
            metrics=kpis,
            checks=checks,
            dashboard=dashboard,
            extras={"subtitle": subtitle},
        )

    def reports(
        self, result: AnalysisResult, params: BaseModel, templates: Templates
    ) -> list[ReportFile]:
        from app.analyses.stock_in_transit import dashboard_html

        params = _params(params)
        t = result.tables
        formats: dict[str, ValueFormat] = {
            "Lines": "integer",
            "Value": "money",
            "Quantity": "number",
            "Lines in Transit": "integer",
            "Value in Transit": "money",
            "Long Transit Lines": "integer",
            "Received Transfers": "integer",
            "Average Transit Days": "number",
            "Longest Transit Days": "number",
            "Open Qty in MB51": "number",
            "Average Days in Transit": "number",
            "Days in Transit": "number",
            "Difference with MB51": "number",
            "MB5T Value": "money",
            "OBD Value (MB51)": "money",
            "STOs": "integer",
            "Days Since STO Created": "number",
            "Days STO to Goods Issue": "number",
            "Days STO to Goods Receipt": "number",
            "Transit Days": "number",
        }
        by_age = TableBlock("By age", t["by_age"], formats, total_row=True)
        by_receiving = TableBlock("By receiving plant", t["by_receiving"], formats)
        kpi: dict[str, Any] = {k.label: k.value for k in result.metrics}
        long = params.long_transit_days

        def days(value: object) -> str:
            return f"{float(value):.1f} days" if isinstance(value, int | float) else "not available"

        document = ReportDocument(
            title="Stock in transit",
            subtitle=str(result.extras["subtitle"]),
            date_text=f"{params.report_date:%d %B %Y}",
            sections=[
                Section(
                    "Summary",
                    paragraphs=[
                        f"Stock worth RWF {float(kpi['Value in transit'] or 0):,.0f} is in transit "
                        f"on {kpi['Lines in transit']} lines; "
                        f"{kpi[f'In transit more than {long} days']} "
                        f"lines have been in transit for more than {long} days. Transfers already "
                        f"received took {days(kpi['Average transit time (received)'])} on average "
                        "from goods issue to goods receipt.",
                    ],
                    tables=[by_age],
                    charts=[
                        ChartBlock(
                            "Value in transit by age (RWF)",
                            [str(a) for a in t["by_age"]["Age"]],
                            {"Value": [float(v) for v in t["by_age"]["Value"]]},
                        )
                    ],
                ),
                Section("By receiving plant", tables=[by_receiving]),
                Section(
                    "Method",
                    bullets=[
                        "Stock in transit: MB5T. Goods issues (641) and receipts (101) of each "
                        "STO and material come from MB51; reversals (642, 102) are taken off.",
                        "Receipts are matched to the goods issue with the same outbound delivery "
                        "first, then to the oldest issue still open.",
                        "Every MB5T line is a line in transit. When MB5T gives no value, the "
                        "value is that of the goods issue (641) of the outbound delivery in "
                        "MB51, for the quantity still in transit.",
                        "Days in transit run from the oldest open goods issue to the MB5T date; "
                        "transit time runs from goods issue to goods receipt.",
                    ],
                ),
            ],
            checks=check_lines(result.checks),
        )
        name = f"Stock_In_Transit_{params.report_date:%Y-%m-%d}"
        blocks = [
            by_age,
            TableBlock("By material", t["by_material"], formats, total_row=True),
            by_receiving,
            TableBlock("By supplying plant", t["by_supplying"], formats),
            TableBlock("Stock in transit", t["in_transit"], formats),
            TableBlock("Received transfers", t["received"], formats),
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
                    result.tables["in_transit"],
                    result.tables["received"],
                    f"Stock in transit: {params.report_date:%d %B %Y}",
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


ANALYSIS = StockInTransit()
