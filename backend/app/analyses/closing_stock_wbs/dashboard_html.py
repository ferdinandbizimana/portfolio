"""Interactive dashboard of the closing stock by WBS (after expired stock scrapped)."""

import pandas as pd

from app.analyses.closing_stock_wbs import FLAG_NEGATIVE, FLAG_WBS, OTHER, OWN, PROGRAMS
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
    Measure("items", "Items", count=True),
    Measure("closing", "Closing value (RWF)", "rwf", sum="Closing Value"),
    Measure("scrapped", "Expired stock scrapped (RWF)", "rwf", sum="Scrapped Value"),
    Measure("final", "Final closing value (RWF)", "rwf", sum="Final Value"),
    Measure("own", OWN, "rwf", sum=OWN),
    Measure("prg", PROGRAMS, "rwf", sum=PROGRAMS),
    Measure("other", OTHER, "rwf", sum=OTHER),
    Measure("flagged", "Items to check", count=True, where=("Checked", ("To check",))),
)


def facts(items: pd.DataFrame) -> pd.DataFrame:
    flags = items["Flag"].astype("string").fillna("").astype(str)
    return pd.DataFrame(
        {
            "Plant": [
                f"{p} · {n}" if n else p
                for p, n in zip(items["Plant"], items["Plant Name"], strict=True)
            ],
            "Main WBS": items["Main WBS"],
            "Flag": flags.replace("", "No flag"),
            "Checked": ["To check" if f in (FLAG_NEGATIVE, FLAG_WBS) else "" for f in flags],
            "Item": [
                f"{d} [{m}]" if d else m
                for d, m in zip(items["Material Description"], items["Material"], strict=True)
            ],
            **{
                c: items[c].astype(float)
                for c in ("Closing Value", "Scrapped Value", "Final Value")
            },
            **{c: items[c].astype(float) for c in (OWN, PROGRAMS, OTHER)},
        }
    ).reset_index(drop=True)


def build(
    items: pd.DataFrame, title: str, subtitle: str, checks: list[tuple[str, float, float, bool]]
) -> InteractiveDashboard:
    split = ("final", "own", "prg", "other")
    return InteractiveDashboard(
        title=title,
        subtitle=subtitle,
        intro=(
            "Closing stock from the G/L stock accounts, less the expired stock scrapped, split "
            "by WBS element and plant."
        ),
        facts={"items": facts(items)},
        measures={"items": MEASURES},
        filters=(
            Filter("Plant", "Plant", "All plants"),
            Filter("Main WBS", "Main WBS", "All WBS"),
            Filter("Flag", "Flag", "All items"),
            Filter("Item", "Item", "All items"),
        ),
        kpis=(
            KpiTile("Closing value", "closing", "items", "{items} items"),
            KpiTile("Expired stock scrapped", "scrapped", "items", "", "red"),
            KpiTile("Final closing value", "final", "items", "", "green"),
            KpiTile("Items to check", "flagged", "items", "", "amber"),
        ),
        sections=(
            DashSection(
                "A · By WBS and plant",
                blocks=(
                    ChartSpec(
                        "Final closing value by plant",
                        "items",
                        "Plant",
                        ("own", "prg", "other"),
                        kind="hbar",
                        sort="desc",
                        sort_by="final",
                        ignore=("Plant",),
                    ),
                    TableSpec(
                        "By plant",
                        "items",
                        ("Plant",),
                        ("closing", "scrapped", *split),
                        ignore=("Plant",),
                        sort_by="final",
                    ),
                    TableSpec(
                        "By flag", "items", ("Flag",), ("items", "closing", "scrapped", "final")
                    ),
                ),
            ),
            DashSection(
                "B · Items",
                note="Largest final value first; download them as CSV.",
                blocks=(
                    DetailSpec(
                        "Items",
                        "items",
                        (
                            ("Plant", "Plant", "text"),
                            ("Item", "Item", "text"),
                            ("Main WBS", "Main WBS", "text"),
                            ("Closing Value", "Closing (RWF)", "rwf"),
                            ("Scrapped Value", "Scrapped (RWF)", "rwf"),
                            ("Final Value", "Final (RWF)", "rwf"),
                            ("Flag", "Flag", "text"),
                        ),
                        sort_by="Final Value",
                    ),
                ),
            ),
        ),
        footer="Rwanda Medical Supply · Closing stock by WBS · G/L line items and MB51 scrapping.",
        checks=checks,
    )
