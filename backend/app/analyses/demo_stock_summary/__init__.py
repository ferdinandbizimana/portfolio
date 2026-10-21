"""Demo analysis: stock value by plant, on the fake demo dataset.

It exists to prove and test the engine end to end (upload, validation,
background run, checks, dashboard, reports). It is not an RMS business rule.
"""

from datetime import date

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
    check_lines,
)
from app.reporting.excel import build_workbook
from app.reporting.slides import build_pptx
from app.reporting.word import build_docx


class Parameters(BaseModel):
    period_end: date = Field(title="Period end", description="Date of the stock balance.")


def _params(params: BaseModel) -> Parameters:
    if not isinstance(params, Parameters):
        raise TypeError("Parameters of the wrong analysis.")
    return params


class DemoStockSummary(Analysis):
    key = "demo_stock_summary"
    title = "Demo: stock value by plant"
    version = "1.0.0"
    description = (
        "Totals a stock list by plant, lists the largest items and checks that the "
        "summary agrees with the detail. Runs on the fake demo dataset only."
    )
    inputs = (InputSpec("stock", "demo_stock_balance", "Stock balance (demo file)"),)
    Parameters = Parameters
    demo = True

    def compute(self, data: dict[str, pd.DataFrame], params: BaseModel) -> AnalysisResult:
        params = _params(params)
        lines = (
            data["stock"]
            .assign(**{"Material Description": lambda d: d["Material Description"].fillna("")})
            .sort_values(["Plant", "Material"], kind="mergesort")
            .reset_index(drop=True)
        )
        total_value = float(lines["Value"].sum())

        by_plant = (
            lines.groupby("Plant", sort=True)
            .agg(Lines=("Material", "size"), Quantity=("Quantity", "sum"), Value=("Value", "sum"))
            .reset_index()
        )
        by_plant["Share"] = by_plant["Value"] / total_value if total_value else 0.0
        by_plant = by_plant.sort_values(
            ["Value", "Plant"], ascending=[False, True], kind="mergesort"
        )

        top_items = lines.sort_values(
            ["Value", "Plant", "Material"], ascending=[False, True, True], kind="mergesort"
        ).head(10)
        negative = lines[(lines["Quantity"] < 0) | (lines["Value"] < 0)]

        checks = [
            Check(
                "plant_total_equals_detail",
                "Total of the plant summary equals the total of all lines",
                expected=total_value,
                actual=float(by_plant["Value"].sum()),
            ),
            Check(
                "line_count",
                "Lines counted by plant equal the number of lines",
                expected=len(lines),
                actual=float(by_plant["Lines"].sum()),
                tolerance=0,
            ),
            Check(
                "shares_add_up",
                "Plant shares add up to 100%",
                expected=1.0 if total_value else 0.0,
                actual=float(by_plant["Share"].sum()),
                tolerance=1e-9,
            ),
        ]
        kpis = [
            Kpi(label="Stock value", value=total_value, format="money", unit="RWF"),
            Kpi(label="Lines", value=len(lines), format="integer"),
            Kpi(label="Plants", value=int(by_plant["Plant"].nunique()), format="integer"),
            Kpi(label="Lines with negative stock", value=len(negative), format="integer"),
        ]
        subtitle = f"Stock balance at {params.period_end:%d %B %Y} · RWF"
        dashboard = Dashboard(
            title=self.title,
            subtitle=subtitle,
            kpis=kpis,
            charts=[
                Chart(
                    id="value-by-plant",
                    title="Stock value by plant (RWF)",
                    type="bar",
                    table="by-plant",
                    category="Plant",
                    series=[Series(name="Value", field="Value")],
                    format="money",
                )
            ],
            tables=[
                Table(
                    id="by-plant",
                    title="By plant",
                    columns=[
                        Column(key="Plant", label="Plant"),
                        Column(key="Lines", label="Lines", format="integer"),
                        Column(key="Quantity", label="Quantity", format="number"),
                        Column(key="Value", label="Value (RWF)", format="money"),
                        Column(key="Share", label="Share", format="percent"),
                    ],
                    rows=rows_of(by_plant),
                    level="summary",
                ),
                Table(
                    id="lines",
                    title="All lines",
                    columns=[
                        Column(key="Plant", label="Plant"),
                        Column(key="Material", label="Material"),
                        Column(key="Material Description", label="Description"),
                        Column(key="Quantity", label="Quantity", format="number"),
                        Column(key="Value", label="Value (RWF)", format="money"),
                    ],
                    rows=rows_of(lines),
                    total_rows=len(lines),
                    level="detail",
                    filters=["Plant"],
                    searchable=["Material", "Material Description"],
                ),
            ],
            checks=[c.out() for c in checks],
        )
        return AnalysisResult(
            tables={"lines": lines, "by_plant": by_plant, "top_items": top_items},
            metrics=kpis,
            checks=checks,
            dashboard=dashboard,
            extras={"subtitle": subtitle, "negative_lines": len(negative)},
        )

    def reports(
        self, result: AnalysisResult, params: BaseModel, templates: Templates
    ) -> list[ReportFile]:
        params = _params(params)
        by_plant = result.tables["by_plant"]
        plant_block = TableBlock(
            "Stock value by plant",
            by_plant,
            {"Lines": "integer", "Quantity": "number", "Value": "money", "Share": "percent"},
            total_row=True,
        )
        top_block = TableBlock(
            "Ten largest items",
            result.tables["top_items"][["Plant", "Material", "Material Description", "Value"]],
            {"Value": "money"},
        )
        total = result.metrics[0].value
        document = ReportDocument(
            title="Stock value by plant (demo)",
            subtitle=str(result.extras["subtitle"]),
            date_text=f"{params.period_end:%d %B %Y}",
            sections=[
                Section(
                    "Summary",
                    paragraphs=[
                        f"The stock on hand is RWF {float(total or 0):,.0f} across "
                        f"{len(by_plant)} plants and {len(result.tables['lines'])} lines.",
                        "This report is produced from the demo dataset and shows how the "
                        "analysis engine works.",
                    ],
                    bullets=[
                        f"{row.Plant}: RWF {row.Value:,.0f} ({row.Share:.1%})"
                        for row in by_plant.head(5).itertuples()
                    ],
                    tables=[plant_block],
                    charts=[
                        ChartBlock(
                            "Stock value by plant (RWF)",
                            [str(p) for p in by_plant["Plant"]],
                            {"Value": [float(v) for v in by_plant["Value"]]},
                        )
                    ],
                ),
                Section("Largest items", tables=[top_block]),
            ],
            checks=check_lines(result.checks),
        )
        stamp = f"{params.period_end:%Y-%m-%d}"
        return [
            ReportFile(
                "workbook",
                "Excel workbook",
                f"Demo_Stock_by_Plant_{stamp}.xlsx",
                "xlsx",
                build_workbook(
                    document.title,
                    document.subtitle,
                    [(k.label, k.value, k.format) for k in result.metrics],
                    [
                        plant_block,
                        TableBlock(
                            "All lines",
                            result.tables["lines"],
                            {"Quantity": "number", "Value": "money"},
                            total_row=True,
                        ),
                    ],
                    document.checks,
                ),
            ),
            ReportFile(
                "report",
                "Word report",
                f"Demo_Stock_by_Plant_{stamp}.docx",
                "docx",
                build_docx(document, templates.docx),
            ),
            ReportFile(
                "slides",
                "PowerPoint slides",
                f"Demo_Stock_by_Plant_{stamp}.pptx",
                "pptx",
                build_pptx(document, templates.pptx),
            ),
        ]


ANALYSIS = DemoStockSummary()
