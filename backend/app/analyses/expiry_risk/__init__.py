"""Expiry risk: stock on hand by expiry date, against the AMC.

Ferdinand's rule of 23 October 2026: "expiry risk (ZSTOCKREPORT) Risk of
expiries and use it with AMC". Definitions used (see docs/PLAN.md, Decisions):

- each ZSTOCKREPORT line (plant, storage location, batch) is a batch of
  unrestricted + quality inspection + blocked stock, valued at the unit cost;
- expiry bands from the report date: expired, within 3 months, 3 to 6, 6 to
  12, more than 12 months, no expiry date;
- the AMC of a material comes from the weekly stock monitoring report (product
  code -> NPC CODE, otherwise description, as for the stock sufficiency);
- quantity at risk, first expiry first out: the batches of a product are used in
  order of expiry at the AMC; what cannot be used before its expiry date is at
  risk (expired stock is at risk in full);
- products without an AMC are shown by expiry band only.
"""

from datetime import date
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from app.analyses.base import Analysis, AnalysisResult, Check, InputSpec
from app.analyses.common.closing import material_code, plant_code, plant_names
from app.analyses.common.weekly import link_materials, master_codes, norm, read_weekly
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

EXPIRED, NO_DATE = "Expired", "No expiry date"
BANDS = [
    EXPIRED,
    "Within 3 months",
    "3 to 6 months",
    "6 to 12 months",
    "More than 12 months",
    NO_DATE,
]
DAYS_PER_MONTH = 365.25 / 12
NOT_ASSESSED = "No AMC (not assessed)"


def band_of(months: float | None) -> str:
    if months is None or pd.isna(months):
        return NO_DATE
    if months <= 0:
        return EXPIRED
    if months <= 3:
        return BANDS[1]
    if months <= 6:
        return BANDS[2]
    if months <= 12:
        return BANDS[3]
    return BANDS[4]


def at_risk(quantities: list[float], months: list[float | None], amc: float) -> list[float]:
    """Quantity of each batch that cannot be used before it expires.

    Batches are given in order of expiry. Each month the AMC is used from the batch
    that expires first; stock still left at a batch's expiry date is at risk.
    """
    used, risks = 0.0, []
    for quantity, month in zip(quantities, months, strict=True):
        if month is None or pd.isna(month):
            risks.append(0.0)  # no expiry date: not at risk of expiry
            continue
        usable = min(quantity, max(0.0, amc * max(month, 0.0) - used)) if quantity > 0 else quantity
        used += max(usable, 0.0)
        risks.append(quantity - usable)
    return risks


class Parameters(BaseModel):
    report_date: date = Field(
        title="Stock report date", description="Date of the ZSTOCKREPORT stock, e.g. 31 July 2026."
    )
    wbs: str = Field(
        default="",
        title="WBS element",
        description="Only stock on this WBS element (leave empty for all stock).",
    )


def _params(params: BaseModel) -> Parameters:
    if not isinstance(params, Parameters):
        raise TypeError("Parameters of the wrong analysis.")
    return params


class ExpiryRisk(Analysis):
    key = "expiry_risk"
    title = "Expiry risk"
    version = "1.2.0"
    description = (
        "Stock on hand (ZSTOCKREPORT) by expiry date and the quantity and value that cannot "
        "be used before expiry at the average monthly consumption of the weekly stock "
        "monitoring report, first expiry first out; by plant, programme and product."
    )
    inputs = (
        InputSpec("stock", "zstockreport", "ZSTOCKREPORT stock on hand (batches, expiry dates)"),
        InputSpec(
            "weekly",
            "weekly_stock_monitoring",
            "Weekly stock monitoring report (AMC, all programme sheets)",
            all_sheets=True,
        ),
        InputSpec(
            "master",
            "material_master",
            "Material master (MARA): NPC code of each SAP material",
            required=False,
        ),
        InputSpec("plants", "ox10_plants", "Plant names (OX10)", required=False),
    )
    Parameters = Parameters

    def compute(self, data: dict[str, pd.DataFrame], params: BaseModel) -> AnalysisResult:
        params = _params(params)
        raw = data["stock"]
        # Text dates are read as SAP writes them (30.06.2026 is day first).
        expiry = parse_dates(raw["Expiry Date"])
        batches = pd.DataFrame(
            {
                "Plant": plant_code(raw["Plant"]).astype(str),
                "Storage Location": raw["Storage Location"].astype("string").fillna("").astype(str),
                "Material": material_code(raw["Material"]).astype(str),
                "Material Description": raw["Material Description"]
                .astype("string")
                .fillna("")
                .astype(str),
                "NPC": raw["NPC CODE"].map(norm),
                "Description": raw["Material Description"].map(norm),
                "Batch": raw["Batch"].astype("string").fillna("").astype(str),
                "WBS": raw["WBS Element"].astype("string").str.strip().fillna("").astype(str),
                "Expiry Date": expiry,
                "Quantity": raw[["Unrestricted", "Quality Inspection", "Blocked"]]
                .astype(float)
                .fillna(0.0)
                .sum(axis=1),
                "Unit Cost": raw["Unit Cost"].astype(float).fillna(0.0),
            }
        )
        batches = batches[batches["Material"] != ""]
        if params.wbs.strip():
            batches = batches[batches["WBS"] == params.wbs.strip()]
        batches = batches[batches["Quantity"] != 0].copy()
        batches["Value"] = batches["Quantity"] * batches["Unit Cost"]
        report = pd.Timestamp(params.report_date)
        batches["Months to Expiry"] = (batches["Expiry Date"] - report).dt.days / DAYS_PER_MONTH
        batches["Expiry Band"] = [band_of(m) for m in batches["Months to Expiry"]]

        # AMC per product of the weekly report, and the product of each material.
        weekly = link_materials(
            read_weekly(data["weekly"]), batches, master_codes(data.get("master"))
        )
        product_of: dict[str, int] = {}
        for index, materials in enumerate(weekly["SAP Materials"] if len(weekly) else []):
            for material in materials:
                product_of.setdefault(material, index)  # first product line wins
        batches["Product"] = batches["Material"].map(product_of)
        amc = weekly["AMC"] if len(weekly) else pd.Series(dtype=float)
        batches["Program"] = (
            batches["Product"].map(weekly["Program"] if len(weekly) else {}).fillna("")
        )
        batches["AMC"] = batches["Product"].map(amc)
        batches = batches.sort_values(
            ["Product", "Expiry Date", "Material", "Plant", "Storage Location", "Batch"],
            kind="mergesort",
            na_position="last",
        ).reset_index(drop=True)
        batches["Qty at Risk"] = 0.0
        for product in sorted(batches["Product"].dropna().unique()):
            part = batches[batches["Product"] == product]
            product_amc = float(amc.iloc[int(product)])
            if not product_amc > 0:
                continue
            risks = at_risk(
                part["Quantity"].tolist(), part["Months to Expiry"].tolist(), product_amc
            )
            batches.loc[part.index, "Qty at Risk"] = risks
        assessed = batches["AMC"] > 0
        expired = batches["Expiry Band"] == EXPIRED
        batches.loc[expired, "Qty at Risk"] = batches.loc[expired, "Quantity"]
        batches["Risk"] = [
            "Expired"
            if e
            else ("At risk" if r > 0 else "Usable before expiry")
            if a
            else NOT_ASSESSED
            for e, a, r in zip(expired, assessed, batches["Qty at Risk"], strict=True)
        ]
        batches["Value at Risk"] = batches["Qty at Risk"] * batches["Unit Cost"]
        names = plant_names(data.get("plants"))
        batches["Plant Name"] = [names.get(p, "") for p in batches["Plant"]]
        batches = batches.sort_values(
            ["Value at Risk", "Expiry Date", "Material", "Plant", "Batch"],
            ascending=[False, True, True, True, True],
            kind="mergesort",
            na_position="last",
        ).reset_index(drop=True)

        def summary(column: str, order: list[str] | None = None) -> pd.DataFrame:
            grouped = (
                batches.groupby(column, sort=True)
                .agg(
                    **{
                        "Batches": ("Material", "size"),
                        "Quantity": ("Quantity", "sum"),
                        "Value": ("Value", "sum"),
                        "Value at Risk": ("Value at Risk", "sum"),
                    }
                )
                .reset_index()
            )
            if order is not None:
                grouped = grouped.set_index(column).reindex(order, fill_value=0).reset_index()
            total = float(grouped["Value"].sum())
            grouped["Share of Value"] = grouped["Value"] / total if total else 0.0
            return grouped

        by_band = summary("Expiry Band", BANDS)
        by_band["Batches"] = by_band["Batches"].astype(int)
        by_plant = summary("Plant")
        if len(by_plant):
            by_plant.insert(1, "Plant Name", [names.get(p, "") for p in by_plant["Plant"]])
            by_plant = by_plant.sort_values(["Value at Risk", "Plant"], ascending=[False, True])
        programme = batches.assign(
            Program=batches["Program"].replace("", "Not in the weekly report")
        )
        by_programme = (
            programme.groupby("Program", sort=True)
            .agg(
                **{
                    "Quantity": ("Quantity", "sum"),
                    "Value": ("Value", "sum"),
                    "Value at Risk": ("Value at Risk", "sum"),
                }
            )
            .reset_index()
        )

        batch_columns = [
            "Plant",
            "Plant Name",
            "Storage Location",
            "Material",
            "Material Description",
            "Batch",
            "WBS",
            "Program",
            "Expiry Date",
            "Months to Expiry",
            "Expiry Band",
            "Quantity",
            "Unit Cost",
            "Value",
            "AMC",
            "Qty at Risk",
            "Value at Risk",
            "Risk",
        ]
        batch_table = batches[batch_columns].copy()
        batch_table["Expiry Date"] = batch_table["Expiry Date"].dt.strftime("%Y-%m-%d")
        risky = batch_table[batch_table["Value at Risk"] > 0]
        not_assessed = batch_table[batch_table["Risk"] == NOT_ASSESSED]

        total_value = float(batches["Value"].sum())
        value_at_risk = float(batches["Value at Risk"].sum())
        expired_value = float(batches.loc[batches["Expiry Band"] == EXPIRED, "Value"].sum())
        soon = batches["Expiry Band"].isin(BANDS[1:3])
        kpis = [
            Kpi(label="Stock value", value=total_value, format="money", unit="RWF"),
            Kpi(label="Expired stock", value=expired_value, format="money", unit="RWF"),
            Kpi(
                label="Expiring within 6 months",
                value=float(batches.loc[soon, "Value"].sum()),
                format="money",
                unit="RWF",
            ),
            Kpi(
                label="Value at risk of expiry",
                value=value_at_risk,
                format="money",
                unit="RWF",
                note="Expired stock and stock that the AMC cannot use before expiry",
            ),
            Kpi(
                label="Share of stock at risk",
                value=value_at_risk / total_value if total_value else None,
                format="percent",
            ),
            Kpi(label="Batches not assessed (no AMC)", value=len(not_assessed), format="integer"),
        ]
        checks = [
            Check(
                "bands_total",
                "Value by expiry band = stock value",
                expected=total_value,
                actual=float(by_band["Value"].sum()),
            ),
            Check(
                "risk_within_stock",
                "Batches whose quantity at risk exceeds their quantity",
                expected=0,
                actual=float((batches["Qty at Risk"] > batches["Quantity"] + 1e-9).sum()),
                tolerance=0,
            ),
            Check(
                "plants_total",
                "Value at risk by plant = value at risk",
                expected=value_at_risk,
                actual=float(by_plant["Value at Risk"].sum()) if len(by_plant) else 0.0,
            ),
        ]
        scope = params.wbs.strip() or "all WBS elements"
        subtitle = f"Stock on {params.report_date:%d %B %Y} · {scope}"
        money, number = "money", "number"
        dashboard = Dashboard(
            title=self.title,
            subtitle=subtitle,
            kpis=kpis,
            charts=[
                Chart(
                    id="band-chart",
                    title="Stock value by expiry band (RWF)",
                    type="column",
                    table="by-band",
                    category="Expiry Band",
                    format=money,
                    series=[
                        Series(name="Value", field="Value"),
                        Series(name="Value at risk", field="Value at Risk"),
                    ],
                ),
                Chart(
                    id="plant-chart",
                    title="Value at risk by plant (RWF)",
                    type="bar",
                    table="by-plant",
                    category="Plant",
                    format=money,
                    limit=15,
                    series=[Series(name="Value at risk", field="Value at Risk")],
                ),
            ],
            tables=[
                Table(
                    id="by-band",
                    title="Stock by expiry band",
                    columns=[
                        Column(key="Expiry Band", label="Expiry"),
                        Column(key="Batches", label="Batches", format="integer"),
                        Column(key="Value", label="Value (RWF)", format=money),
                        Column(key="Share of Value", label="Share", format="percent"),
                        Column(key="Value at Risk", label="Value at risk (RWF)", format=money),
                    ],
                    rows=rows_of(by_band),
                ),
                Table(
                    id="by-programme",
                    title="Value at risk by programme",
                    columns=[
                        Column(key="Program", label="Programme"),
                        Column(key="Value", label="Value (RWF)", format=money),
                        Column(key="Value at Risk", label="Value at risk (RWF)", format=money),
                    ],
                    rows=rows_of(by_programme),
                ),
                Table(
                    id="by-plant",
                    title="Value at risk by plant",
                    columns=[
                        Column(key="Plant", label="Plant"),
                        Column(key="Plant Name", label="Name"),
                        Column(key="Value", label="Value (RWF)", format=money),
                        Column(key="Value at Risk", label="Value at risk (RWF)", format=money),
                    ],
                    rows=rows_of(by_plant),
                ),
                Table(
                    id="batches-at-risk",
                    title="Batches at risk of expiry (highest value first)",
                    columns=[
                        Column(key="Plant", label="Plant"),
                        Column(key="Material", label="Material"),
                        Column(key="Material Description", label="Description"),
                        Column(key="Batch", label="Batch"),
                        Column(key="Expiry Date", label="Expiry", format="date"),
                        Column(key="Quantity", label="Quantity", format=number),
                        Column(key="AMC", label="AMC", format=number),
                        Column(key="Qty at Risk", label="Qty at risk", format=number),
                        Column(key="Value at Risk", label="Value at risk (RWF)", format=money),
                        Column(key="Risk", label="Risk"),
                    ],
                    rows=rows_of(risky),
                    total_rows=len(risky),
                    level="detail",
                    filters=["Plant", "Risk", "Program"],
                    searchable=["Material", "Material Description", "Batch"],
                ),
            ],
            checks=[c.out() for c in checks],
            notes=[
                "The AMC is the national average monthly consumption of the weekly report; "
                "quantities are compared in the units of ZSTOCKREPORT.",
            ],
        )
        return AnalysisResult(
            tables={
                "batches": batch_table,
                "by_band": by_band,
                "by_plant": by_plant,
                "by_programme": by_programme,
                "at_risk": risky,
                "not_assessed": not_assessed,
            },
            metrics=kpis,
            checks=checks,
            dashboard=dashboard,
            extras={"subtitle": subtitle},
        )

    def reports(
        self, result: AnalysisResult, params: BaseModel, templates: Templates
    ) -> list[ReportFile]:
        from app.analyses.expiry_risk import dashboard_html

        params = _params(params)
        t = result.tables
        formats: dict[str, ValueFormat] = {
            "Batches": "integer",
            "Quantity": "number",
            "Value": "money",
            "Share of Value": "percent",
            "Value at Risk": "money",
            "Unit Cost": "money",
            "Months to Expiry": "number",
            "AMC": "number",
            "Qty at Risk": "number",
        }
        by_band = TableBlock("By expiry band", t["by_band"], formats, total_row=True)
        by_programme = TableBlock("By programme", t["by_programme"], formats, total_row=True)
        kpi: dict[str, Any] = {k.label: k.value for k in result.metrics}

        def rwf(label: str) -> str:
            return f"RWF {float(kpi[label] or 0):,.0f}"

        share = kpi["Share of stock at risk"]
        document = ReportDocument(
            title="Expiry risk",
            subtitle=str(result.extras["subtitle"]),
            date_text=f"{params.report_date:%d %B %Y}",
            sections=[
                Section(
                    "Summary",
                    paragraphs=[
                        f"Stock on hand is worth {rwf('Stock value')}; {rwf('Expired stock')} has "
                        f"expired and {rwf('Expiring within 6 months')} expires within six months. "
                        f"At the average monthly consumption, {rwf('Value at risk of expiry')} "
                        + (f"({float(share):.1%} of the stock) " if share is not None else "")
                        + "is expired or cannot be used before its expiry date.",
                    ],
                    tables=[by_band],
                    charts=[
                        ChartBlock(
                            "Value by expiry band (RWF)",
                            [str(b) for b in t["by_band"]["Expiry Band"]],
                            {
                                "Value": [float(v) for v in t["by_band"]["Value"]],
                                "Value at risk": [float(v) for v in t["by_band"]["Value at Risk"]],
                            },
                        )
                    ],
                ),
                Section("By programme", tables=[by_programme]),
                Section(
                    "Method",
                    bullets=[
                        "Stock: ZSTOCKREPORT unrestricted, quality inspection and blocked stock "
                        "per batch, at the unit cost; expiry bands from the stock report date.",
                        "The batches of each product are used in order of expiry at the average "
                        "monthly consumption of the weekly stock monitoring report; what is "
                        "left at the expiry date is at risk. Expired stock is at risk in full.",
                        "Products are linked by NPC code, otherwise by description. Products "
                        "without AMC are shown by expiry band only.",
                    ],
                ),
            ],
            checks=check_lines(result.checks),
        )
        name = f"Expiry_Risk_{params.report_date:%Y-%m-%d}"
        blocks = [
            by_band,
            by_programme,
            TableBlock("By plant", t["by_plant"], formats),
            TableBlock("Batches at risk", t["at_risk"], formats),
            TableBlock("Not assessed (no AMC)", t["not_assessed"], formats),
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
                    result.tables["batches"],
                    f"Expiry risk: {params.report_date:%d %B %Y}",
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


ANALYSIS = ExpiryRisk()
