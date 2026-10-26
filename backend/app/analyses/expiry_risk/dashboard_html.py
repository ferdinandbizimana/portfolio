"""Interactive dashboard of the expiry risk (batches, bands, plants, programmes)."""

import pandas as pd

from app.analyses.expiry_risk import BANDS, EXPIRED
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
    Measure("batches", "Batches", count=True),
    Measure("qty", "Quantity", sum="Quantity"),
    Measure("value", "Stock value (RWF)", "rwf", sum="Value"),
    Measure("at_risk", "Value at risk (RWF)", "rwf", sum="Value at Risk"),
    Measure(
        "expired", "Expired value (RWF)", "rwf", sum="Value", where=("Expiry band", (EXPIRED,))
    ),
    Measure("expired_batches", "Expired batches", count=True, where=("Expiry band", (EXPIRED,))),
    Measure("risk_share", "Share of stock at risk", "pct", ratio=("at_risk", "value")),
)
VALUE_COLUMNS = ("batches", "value", "expired", "at_risk", "risk_share")


def facts(batches: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Plant": [
                f"{p} · {n}" if n else p
                for p, n in zip(batches["Plant"], batches["Plant Name"], strict=True)
            ],
            "Programme": batches["Program"].replace("", "Not in the weekly report"),
            "WBS": batches["WBS"],
            "Expiry band": batches["Expiry Band"],
            "Risk": batches["Risk"],
            "Item": [
                f"{d} [{m}]" if d else m
                for d, m in zip(batches["Material Description"], batches["Material"], strict=True)
            ],
            "Batch": batches["Batch"],
            "Expiry date": batches["Expiry Date"],
            "Months to expiry": batches["Months to Expiry"].astype(float),
            "Quantity": batches["Quantity"].astype(float),
            "Value": batches["Value"].astype(float),
            "Value at Risk": batches["Value at Risk"].astype(float),
        }
    ).reset_index(drop=True)


def build(
    batches: pd.DataFrame, title: str, subtitle: str, checks: list[tuple[str, float, float, bool]]
) -> InteractiveDashboard:
    return InteractiveDashboard(
        title=title,
        subtitle=subtitle,
        intro=(
            "Stock by batch and expiry date: what has expired, what expires in the coming months "
            "and the value that cannot be used before expiry at the AMC."
        ),
        facts={"batches": facts(batches)},
        measures={"batches": MEASURES},
        filters=(
            Filter("Plant", "Plant", "All plants"),
            Filter("Programme", "Programme", "All programmes"),
            Filter("WBS", "WBS element", "All WBS"),
            Filter("Expiry band", "Expiry band", "All bands", order="given", values=tuple(BANDS)),
            Filter("Risk", "Risk", "All batches"),
            Filter("Item", "Item", "All items"),
        ),
        kpis=(
            KpiTile("Stock value", "value", "batches", "{batches} batches"),
            KpiTile("Expired stock", "expired", "batches", "{expired_batches} batches", "red"),
            KpiTile(
                "Value at risk of expiry", "at_risk", "batches", "{risk_share} of stock", "amber"
            ),
        ),
        sections=(
            DashSection(
                "A · Expired stock per plant",
                note="Every expired batch must be blocked and moved to the quarantine plant.",
                blocks=(
                    ChartSpec(
                        "Expired value by plant",
                        "batches",
                        "Plant",
                        ("expired",),
                        kind="hbar",
                        sort="desc",
                        sort_by="expired",
                        ignore=("Plant",),
                    ),
                    TableSpec(
                        "Expired and at-risk stock by plant",
                        "batches",
                        ("Plant",),
                        VALUE_COLUMNS,
                        ignore=("Plant",),
                        sort_by="expired",
                    ),
                ),
            ),
            DashSection(
                "B · Stock by expiry band",
                blocks=(
                    ChartSpec(
                        "Stock value and value at risk by expiry band",
                        "batches",
                        "Expiry band",
                        ("value", "at_risk"),
                        ignore=("Expiry band",),
                    ),
                    TableSpec(
                        "By expiry band",
                        "batches",
                        ("Expiry band",),
                        ("batches", "qty", "value", "at_risk"),
                        ignore=("Expiry band",),
                    ),
                ),
            ),
            DashSection(
                "C · By programme",
                blocks=(
                    TableSpec(
                        "By programme",
                        "batches",
                        ("Programme",),
                        VALUE_COLUMNS,
                        sort_by="at_risk",
                    ),
                ),
            ),
            DashSection(
                "D · Batches",
                note="Largest value at risk first; download them as CSV.",
                blocks=(
                    DetailSpec(
                        "Batches",
                        "batches",
                        (
                            ("Plant", "Plant", "text"),
                            ("Item", "Item", "text"),
                            ("Batch", "Batch", "text"),
                            ("Expiry date", "Expiry date", "text"),
                            ("Expiry band", "Band", "text"),
                            ("Quantity", "Quantity", "int"),
                            ("Value", "Value (RWF)", "rwf"),
                            ("Value at Risk", "At risk (RWF)", "rwf"),
                        ),
                        sort_by="Value at Risk",
                    ),
                ),
            ),
        ),
        footer="Rwanda Medical Supply · Expiry risk · ZSTOCKREPORT batches and the weekly AMC.",
        checks=checks,
    )
