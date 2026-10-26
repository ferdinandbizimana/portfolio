"""Interactive dashboard of the RBC accountability report.

Opening stock, receipts, goods issues and expired stock scrapped (MB51),
other movements and adjustments, closing stock and the difference (Increase /
Reduction, with percentages).

The layout follows Ferdinand's RBC programme stock dashboard: filters for
programme, plant, item and value, opening against closing by programme and by
plant, the closing stock list with a summary by programme, and every
plant-product line with its difference."""

import pandas as pd

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

# Value bands for the "Minimum value" filter: the larger of opening and closing.
VALUE_BANDS = (
    (1_000_000_000, "RWF 1B and over"),
    (100_000_000, "RWF 100M to 1B"),
    (10_000_000, "RWF 10M to 100M"),
    (1_000_000, "RWF 1M to 10M"),
    (0, "Under RWF 1M"),
)

MEASURES = (
    Measure("lines", "Lines", count=True),
    Measure("materials", "Materials", distinct="Material"),
    Measure(
        "materials_in_stock", "Products in stock", distinct="Material", where=("In stock", ("Yes",))
    ),
    Measure("in_stock", "Lines in stock", count=True, where=("In stock", ("Yes",))),
    Measure("opening", "Opening stock (RWF)", "rwf", sum="Opening Value"),
    Measure("receipts", "Receipts (RWF)", "rwf", sum="Receipts Value"),
    Measure("issues", "Goods issues (RWF)", "rwf", sum="Goods Issues Value"),
    Measure("scrapped", "Scrapped, expired (RWF)", "rwf", sum="Scrapped Value"),
    Measure("other", "Other movements (RWF)", "rwf", sum="Other Movements Value"),
    Measure("closing", "Closing stock (RWF)", "rwf", sum="Closing Value"),
    Measure("difference", "Difference (RWF)", "rwf", diff=("closing", "opening")),
    Measure("change", "Increase / Reduction", "change", ratio=("difference", "opening")),
)
COLUMNS = (
    "opening",
    "receipts",
    "issues",
    "scrapped",
    "other",
    "closing",
    "difference",
    "change",
    "in_stock",
)
CHANGE_COLUMNS = ("opening", "closing", "difference", "change")
CLOSING_MEASURES = (
    Measure("lines", "Lines", count=True),
    Measure("materials", "Materials", distinct="Material"),
    Measure("closing", "Closing stock (RWF)", "rwf", sum="Closing Value"),
)


def value_band(opening: float, closing: float) -> str:
    largest = max(abs(opening), abs(closing))
    return next(name for floor, name in VALUE_BANDS if largest >= floor)


def facts(lines: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Programme": lines["Category"],
            "Plant": [
                f"{p} · {n}" if n else p
                for p, n in zip(lines["Plant"], lines["Plant Name"], strict=True)
            ],
            "Item": [
                f"{d} [{m}]" if d else m
                for d, m in zip(lines["Material Description"], lines["Material"], strict=True)
            ],
            "Material": lines["Material"].astype(str),
            "UoM": lines["Base Unit of Measure"].astype(str),
            "Value": [
                value_band(o, c)
                for o, c in zip(lines["Opening Value"], lines["Closing Value"], strict=True)
            ],
            "Opening Value": lines["Opening Value"].astype(float),
            "Receipts Value": lines["Receipts Value"].astype(float),
            "Goods Issues Value": lines["Goods Issues Value"].astype(float),
            "Scrapped Value": lines["Scrapped Value"].astype(float),
            "Other Movements Value": lines["Other Movements Value"].astype(float),
            "Closing Value": lines["Closing Value"].astype(float),
            "Difference": lines["Difference"].astype(float),
            "Increase / Reduction": lines["Increase / Reduction"].astype(str),
            "Closing Qty": lines["Closing Qty"].astype(float),
            "In stock": (lines["Closing Value"] > 0).map({True: "Yes", False: "No"}),
        }
    ).reset_index(drop=True)


def closing_facts(lines: pd.DataFrame) -> pd.DataFrame:
    """The closing stock list: every plant-material line with stock at closing."""
    frame = facts(lines)
    held = (frame["Closing Value"].round(2) != 0) | (frame["Closing Qty"].round(3) != 0)
    return frame[held].reset_index(drop=True)


def build(
    lines: pd.DataFrame,
    title: str,
    subtitle: str,
    opening_label: str,
    closing_label: str,
    checks: list[tuple[str, float, float, bool]],
) -> InteractiveDashboard:
    return InteractiveDashboard(
        title=title,
        subtitle=subtitle,
        intro=(
            f"Opening stock ({opening_label}), receipts and goods issues (MB51), expired stock "
            f"scrapped, closing stock ({closing_label}) and the difference, labelled Increase "
            "or Reduction, by programme, plant and item."
        ),
        facts={"lines": facts(lines), "closing": closing_facts(lines)},
        measures={"lines": MEASURES, "closing": CLOSING_MEASURES},
        filters=(
            Filter("Programme", "Programme", "All programmes"),
            Filter("Plant", "Plant", "All plants"),
            Filter("Item", "Product", "All products"),
            Filter(
                "Value",
                "Value (larger of opening and closing)",
                "Any value",
                order="given",
                values=tuple(name for _, name in VALUE_BANDS),
            ),
        ),
        kpis=(
            KpiTile(f"Opening stock ({opening_label})", "opening", "lines"),
            KpiTile("Receipts", "receipts", "lines", "MB51, in the period", "green"),
            KpiTile("Goods issues", "issues", "lines", "MB51, in the period", "red"),
            KpiTile("Scrapped (expired)", "scrapped", "lines", "other movements {other}", "grey"),
            KpiTile(f"Closing stock ({closing_label})", "closing", "lines"),
            KpiTile("Difference", "difference", "lines", "{change}", "amber"),
            KpiTile(
                f"Products in stock ({closing_label})",
                "materials_in_stock",
                "lines",
                "distinct SAP materials, on {in_stock} lines",
                "grey",
            ),
        ),
        sections=(
            DashSection(
                "A · By programme",
                blocks=(
                    ChartSpec(
                        "Opening and closing stock by programme",
                        "lines",
                        "Programme",
                        ("opening", "closing"),
                        ignore=("Programme",),
                        sort="desc",
                        sort_by="closing",
                    ),
                    ChartSpec(
                        "Receipts and goods issues by programme",
                        "lines",
                        "Programme",
                        ("receipts", "issues", "scrapped"),
                        ignore=("Programme",),
                        sort="desc",
                        sort_by="receipts",
                    ),
                    TableSpec(
                        "Summary by programme",
                        "lines",
                        ("Programme",),
                        COLUMNS,
                        ignore=("Programme",),
                        sort_by="closing",
                    ),
                ),
            ),
            DashSection(
                "B · By plant",
                blocks=(
                    ChartSpec(
                        "Opening and closing stock by plant (top 15)",
                        "lines",
                        "Plant",
                        ("opening", "closing"),
                        kind="hbar",
                        ignore=("Plant",),
                        sort="desc",
                        sort_by="closing",
                        limit=15,
                    ),
                    TableSpec(
                        "Summary by plant",
                        "lines",
                        ("Plant",),
                        COLUMNS,
                        ignore=("Plant",),
                        sort_by="closing",
                    ),
                ),
            ),
            DashSection(
                "C · Largest changes by item",
                blocks=(
                    TableSpec(
                        "Largest increases",
                        "lines",
                        ("Item",),
                        CHANGE_COLUMNS,
                        sort_by="difference",
                        limit=15,
                    ),
                    TableSpec(
                        "Largest reductions",
                        "lines",
                        ("Item",),
                        CHANGE_COLUMNS,
                        sort_by="difference",
                        descending=False,
                        limit=15,
                    ),
                ),
            ),
            DashSection(
                f"D · Closing stock list ({closing_label})",
                note="Every plant-product line with stock at closing; follows the filters above.",
                blocks=(
                    TableSpec(
                        "Closing stock by programme",
                        "closing",
                        ("Programme",),
                        ("lines", "materials", "closing"),
                        sort_by="closing",
                    ),
                    DetailSpec(
                        "Closing stock list",
                        "closing",
                        (
                            ("Programme", "Programme", "text"),
                            ("Plant", "Plant", "text"),
                            ("Item", "Product", "text"),
                            ("UoM", "UoM", "text"),
                            ("Closing Qty", "Closing quantity", "num"),
                            ("Closing Value", "Closing value (RWF)", "rwf"),
                        ),
                        sort_by="Closing Value",
                    ),
                ),
            ),
            DashSection(
                "E · Products by plant",
                blocks=(
                    DetailSpec(
                        "Opening, movements, closing and difference by plant and product",
                        "lines",
                        (
                            ("Plant", "Plant", "text"),
                            ("Item", "Product", "text"),
                            ("Programme", "Programme", "text"),
                            ("Opening Value", "Opening (RWF)", "rwf"),
                            ("Receipts Value", "Receipts (RWF)", "rwf"),
                            ("Goods Issues Value", "Goods issues (RWF)", "rwf"),
                            ("Scrapped Value", "Scrapped, expired (RWF)", "rwf"),
                            ("Other Movements Value", "Other movements (RWF)", "rwf"),
                            ("Closing Value", "Closing (RWF)", "rwf"),
                            ("Difference", "Difference (RWF)", "rwf"),
                            ("Increase / Reduction", "Increase / reduction", "text"),
                            ("Closing Qty", "Quantity at closing", "num"),
                        ),
                        sort_by="Closing Value",
                    ),
                ),
            ),
        ),
        footer=(
            f"Opening = closing stock reported to RBC at {opening_label}; closing = reconciled "
            f"stock on the RBC WBS at {closing_label}. Receipts and goods issues are MB51 "
            "material documents on the WBS posted in the period; goods issues and scrapping "
            "are negative. Other movements = closing less opening, receipts, goods issues "
            "and scrapping. Difference = closing less opening, shown as an increase or a "
            "reduction. Values in RWF."
        ),
        checks=checks,
    )
