"""Interactive dashboard of the RBC accountability report.

Only opening stock, closing stock and the difference (Increase / Reduction,
with percentages), as the report rule requires: no receipts, issues or
expired stock anywhere."""

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

MEASURES = (
    Measure("lines", "Lines", count=True),
    Measure("in_stock", "Lines in stock", count=True, where=("In stock", ("Yes",))),
    Measure("opening", "Opening stock (RWF)", "rwf", sum="Opening Value"),
    Measure("closing", "Closing stock (RWF)", "rwf", sum="Closing Value"),
    Measure("difference", "Difference (RWF)", "rwf", diff=("closing", "opening")),
    Measure("change", "Increase / Reduction", "change", ratio=("difference", "opening")),
)
COLUMNS = ("opening", "closing", "difference", "change", "in_stock")


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
            "Opening Value": lines["Opening Value"].astype(float),
            "Closing Value": lines["Closing Value"].astype(float),
            "In stock": (lines["Closing Value"] > 0).map({True: "Yes", False: "No"}),
        }
    ).reset_index(drop=True)


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
            f"Opening stock ({opening_label}), closing stock ({closing_label}) and the difference, "
            "labelled Increase or Reduction, by programme, plant and item."
        ),
        facts={"lines": facts(lines)},
        measures={"lines": MEASURES},
        filters=(
            Filter("Programme", "Programme", "All programmes"),
            Filter("Plant", "Plant", "All plants"),
            Filter("Item", "Item", "All items"),
        ),
        kpis=(
            KpiTile(f"Opening stock ({opening_label})", "opening", "lines"),
            KpiTile(f"Closing stock ({closing_label})", "closing", "lines"),
            KpiTile("Difference", "difference", "lines", "{change}", "amber"),
            KpiTile("Lines in stock", "in_stock", "lines", "of {lines} lines", "grey"),
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
                        "Closing stock by plant",
                        "lines",
                        "Plant",
                        ("closing",),
                        kind="hbar",
                        ignore=("Plant",),
                        sort="desc",
                        sort_by="closing",
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
                        COLUMNS[:4],
                        sort_by="difference",
                        limit=15,
                    ),
                    TableSpec(
                        "Largest reductions",
                        "lines",
                        ("Item",),
                        COLUMNS[:4],
                        sort_by="difference",
                        descending=False,
                        limit=15,
                    ),
                ),
            ),
            DashSection(
                "D · Lines",
                blocks=(
                    DetailSpec(
                        "Stock lines by plant and item",
                        "lines",
                        (
                            ("Programme", "Programme", "text"),
                            ("Plant", "Plant", "text"),
                            ("Item", "Item", "text"),
                            ("Opening Value", "Opening (RWF)", "rwf"),
                            ("Closing Value", "Closing (RWF)", "rwf"),
                        ),
                        sort_by="Closing Value",
                    ),
                ),
            ),
        ),
        footer="Rwanda Medical Supply · RBC accountability report · values in RWF.",
        checks=checks,
    )
