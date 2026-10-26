"""Interactive dashboard of stock sufficiency against AMC (months of stock)."""

import pandas as pd

from app.analyses.common.weekly import NO_AMC, OVERSTOCK, STATUSES, STOCK_OUT, TO_PLAN, UNDERSTOCK
from app.reporting.interactive import (
    ChartSpec,
    DashSection,
    DetailSpec,
    Filter,
    InteractiveDashboard,
    KpiTile,
    Measure,
    TableSpec,
)

MEASURES = (
    Measure("products", "Products", count=True),
    Measure("stock_out", "Stock-out risk", count=True, where=("Status", (STOCK_OUT,))),
    Measure("under", "Understock", count=True, where=("Status", (UNDERSTOCK,))),
    Measure("to_plan", "Stocked to plan", count=True, where=("Status", (TO_PLAN,))),
    Measure("over", "Overstock", count=True, where=("Status", (OVERSTOCK,))),
    Measure("no_amc", "No AMC", count=True, where=("Status", (NO_AMC,))),
    Measure("value", "Stock value (RWF)", "rwf", sum="Value"),
    Measure("consumption", "Monthly consumption value (RWF)", "rwf", sum="Monthly consumption"),
    Measure("above_max", "Value above max level (RWF)", "rwf", sum="Value above max"),
    Measure("mos_value", "Months of stock (value)", "num", ratio=("value", "consumption")),
    Measure("risk_share", "Products at stock-out risk", "pct", ratio=("stock_out", "products")),
)


def facts(analysis: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Programme": analysis["Program"],
            "Status": analysis["Status"],
            "Linked by": analysis["Linked by"],
            "Product": [
                f"{d} [{c}]" if d else c
                for d, c in zip(
                    analysis["Product (weekly report)"], analysis["Product Code"], strict=True
                )
            ],
            "SAP material": analysis["SAP Material"],
            "RMS stock": analysis["RMS Stock"].astype(float),
            "National stock": analysis["National Stock"].astype(float),
            "AMC": analysis["AMC"].astype(float),
            "MOS at RMS": analysis["MOS at RMS"].astype(float),
            "MOS national": analysis["MOS National"].astype(float),
            "Value": analysis["Value (RWF)"].astype(float),
            "Monthly consumption": analysis["Monthly Consumption Value (RWF)"].astype(float),
            "Value above max": analysis["Value Above Max Level (RWF)"].astype(float),
        }
    ).reset_index(drop=True)


def build(
    analysis: pd.DataFrame, title: str, subtitle: str, checks: list[tuple[str, float, float, bool]]
) -> InteractiveDashboard:
    status_columns = ("products", "stock_out", "under", "to_plan", "over", "no_amc")
    return InteractiveDashboard(
        title=title,
        subtitle=subtitle,
        intro=(
            "Months of stock (MOS) of every programme product at RMS and nationally, against "
            "the minimum and maximum levels of each programme."
        ),
        facts={"products": facts(analysis)},
        measures={"products": MEASURES},
        filters=(
            Filter("Programme", "Programme", "All programmes"),
            Filter("Status", "Status", "All statuses", order="given", values=tuple(STATUSES)),
            Filter("Linked by", "Linked to SAP by", "All links"),
            Filter("Product", "Product", "All products"),
        ),
        kpis=(
            KpiTile("Programme products", "products", "products"),
            KpiTile(
                "Stock-out risk (<3 MOS)",
                "stock_out",
                "products",
                "{risk_share} of products",
                "red",
            ),
            KpiTile("Overstock", "over", "products", "{above_max} above the maximum", "amber"),
            KpiTile("Stock value", "value", "products", "{mos_value} months of consumption"),
        ),
        sections=(
            DashSection(
                "A · Status by programme",
                blocks=(
                    ChartSpec(
                        "Products by status and programme",
                        "products",
                        "Programme",
                        ("products",),
                        kind="stacked",
                        stack="Status",
                        sort_by="products",
                    ),
                    TableSpec(
                        "Status by programme",
                        "products",
                        ("Programme",),
                        status_columns,
                        sort_by="products",
                    ),
                    TableSpec(
                        "Value by programme",
                        "products",
                        ("Programme",),
                        ("value", "consumption", "mos_value", "above_max"),
                        sort_by="value",
                    ),
                ),
            ),
            DashSection(
                "B · Products",
                note="Lowest months of stock at RMS first; download them as CSV.",
                blocks=(
                    DetailSpec(
                        "Products",
                        "products",
                        (
                            ("Programme", "Programme", "text"),
                            ("Product", "Product", "text"),
                            ("Status", "Status", "text"),
                            ("RMS stock", "RMS stock", "int"),
                            ("National stock", "National stock", "int"),
                            ("AMC", "AMC", "int"),
                            ("MOS at RMS", "MOS at RMS", "num"),
                            ("MOS national", "MOS national", "num"),
                            ("Value", "Value (RWF)", "rwf"),
                        ),
                        sort_by="MOS at RMS",
                        descending=False,
                    ),
                ),
            ),
        ),
        footer="Rwanda Medical Supply · Stock sufficiency against AMC · weekly stock monitoring.",
        checks=checks,
    )
