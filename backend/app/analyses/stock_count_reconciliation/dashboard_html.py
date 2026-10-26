"""Interactive dashboard of the year-end stock count reconciliation."""

import pandas as pd

from app.analyses.stock_count_reconciliation import ABOVE, BELOW
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
    Measure(
        "with_variance", "Lines with a variance", count=True, where=("Direction", (ABOVE, BELOW))
    ),
    Measure("closing", "Closing value (RWF)", "rwf", sum="Closing Value"),
    Measure("counted", "Counted value (RWF)", "rwf", sum="Counted Value"),
    Measure("net", "Net variance (RWF)", "rwf", sum="Variance"),
    Measure("gross", "Gross variance (RWF)", "rwf", sum="Abs"),
    Measure(
        "above", "Count above books (RWF)", "rwf", sum="Variance", where=("Direction", (ABOVE,))
    ),
    Measure(
        "below", "Count below books (RWF)", "rwf", sum="Variance", where=("Direction", (BELOW,))
    ),
    Measure("gross_share", "Gross variance % of closing", "pct", ratio=("gross", "closing")),
    Measure("accuracy", "Accuracy (value)", "pct", complement="gross_share"),
)
COLUMNS = ("lines", "with_variance", "closing", "above", "below", "gross", "accuracy")


def facts(lines: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Plant": [
                f"{p} · {n}" if n else p
                for p, n in zip(lines["Plant"], lines["Plant Name"], strict=True)
            ],
            "Site": lines["Site"],
            "Theme": lines["Theme"],
            "Cause": lines["Cause"],
            "Direction": lines["Direction"],
            "Item": [
                f"{d} [{m}]" if d else m
                for d, m in zip(lines["Description"], lines["Material"], strict=True)
            ],
            "Reason": lines["Reason"],
            **{
                c: lines[c].astype(float)
                for c in ("Closing Value", "Counted Value", "Variance", "Abs")
            },
        }
    ).reset_index(drop=True)


def build(
    lines: pd.DataFrame, title: str, subtitle: str, checks: list[tuple[str, float, float, bool]]
) -> InteractiveDashboard:
    return InteractiveDashboard(
        title=title,
        subtitle=subtitle,
        intro=(
            "Closing stock posted in Finance against the quantities counted, with the reason, "
            "cause and theme of every difference."
        ),
        facts={"lines": facts(lines)},
        measures={"lines": MEASURES},
        filters=(
            Filter("Site", "Site", "All sites"),
            Filter("Plant", "Plant", "All plants"),
            Filter("Theme", "Theme", "All themes"),
            Filter("Cause", "Cause", "All causes"),
            Filter("Direction", "Direction", "All lines"),
        ),
        kpis=(
            KpiTile("Closing value", "closing", "lines", "{lines} lines"),
            KpiTile("Counted value", "counted", "lines", "net {net}"),
            KpiTile("Gross variance", "gross", "lines", "{gross_share} of closing", "red"),
            KpiTile(
                "Accuracy (value)",
                "accuracy",
                "lines",
                "{with_variance} lines with a variance",
                "green",
            ),
        ),
        sections=(
            DashSection(
                "A · Themes and causes",
                blocks=(
                    ChartSpec(
                        "Gross variance by theme",
                        "lines",
                        "Theme",
                        ("gross",),
                        kind="hbar",
                        sort="desc",
                        sort_by="gross",
                    ),
                    TableSpec("By theme", "lines", ("Theme",), COLUMNS, sort_by="gross"),
                    TableSpec("By cause", "lines", ("Cause",), COLUMNS, sort_by="gross"),
                ),
            ),
            DashSection(
                "B · Sites and plants",
                blocks=(
                    ChartSpec(
                        "Count above and below books by plant",
                        "lines",
                        "Plant",
                        ("above", "below"),
                        kind="hbar",
                        sort="desc",
                        sort_by="gross",
                        limit=20,
                    ),
                    TableSpec("By site", "lines", ("Site",), COLUMNS, sort_by="gross"),
                    TableSpec(
                        "By plant",
                        "lines",
                        ("Plant",),
                        COLUMNS,
                        sort_by="gross",
                        bars=("accuracy",),
                        traffic=(0.98, 0.995),
                    ),
                ),
            ),
            DashSection(
                "C · Lines",
                note="Largest difference first; download them as CSV.",
                blocks=(
                    DetailSpec(
                        "Count lines",
                        "lines",
                        (
                            ("Plant", "Plant", "text"),
                            ("Item", "Item", "text"),
                            ("Closing Value", "Closing (RWF)", "rwf"),
                            ("Counted Value", "Counted (RWF)", "rwf"),
                            ("Variance", "Variance (RWF)", "rwf"),
                            ("Reason", "Reason", "text"),
                            ("Theme", "Theme", "text"),
                        ),
                        sort_by="Abs",
                    ),
                ),
            ),
        ),
        footer=(
            "Rwanda Medical Supply · Stock count reconciliation · closing against counted stock."
        ),
        checks=checks,
    )
