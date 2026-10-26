"""Interactive dashboard of stock in transit between plants (STOs)."""

import pandas as pd

from app.analyses.stock_in_transit import AGE_BANDS
from app.reporting.interactive import (
    ChartSpec,
    DashSection,
    DetailSpec,
    Filter,
    InteractiveDashboard,
    KpiTile,
    Measure,
    TableSpec,
    month_of,
)

OPEN_MEASURES = (
    Measure("lines", "Lines in transit", count=True),
    Measure("stos", "STOs", distinct="STO"),
    Measure("value", "Value in transit (RWF)", "rwf", sum="Value"),
    Measure("days", "Days", sum="Days"),
    Measure("dated", "Dated lines", sum="Dated"),
    Measure("avg_days", "Average days in transit", "days", ratio=("days", "dated")),
)
RECEIVED_MEASURES = (
    Measure("received", "Receipts", count=True),
    Measure("transit_days", "Transit days", sum="Transit days"),
    Measure(
        "avg_transit", "Average transit time (days)", "days", ratio=("transit_days", "received")
    ),
)


def _plant(code: pd.Series, name: pd.Series | None) -> list[str]:
    names = name if name is not None else pd.Series("", index=code.index)
    return [f"{c} · {n}" if n else c for c, n in zip(code, names.fillna(""), strict=True)]


def facts(open_lines: pd.DataFrame, received: pd.DataFrame) -> dict[str, pd.DataFrame]:
    days = pd.to_numeric(open_lines["Days in Transit"], errors="coerce")
    names = dict(
        zip(open_lines["Supplying Plant"], open_lines["Supplying Plant Name"], strict=True)
    ) | dict(zip(open_lines["Receiving Plant"], open_lines["Receiving Plant Name"], strict=True))
    return {
        "open": pd.DataFrame(
            {
                "Supplying plant": _plant(
                    open_lines["Supplying Plant"], open_lines["Supplying Plant Name"]
                ),
                "Receiving plant": _plant(
                    open_lines["Receiving Plant"], open_lines["Receiving Plant Name"]
                ),
                "Age": open_lines["Age"],
                "STO": open_lines["STO"],
                "Item": [
                    f"{d} [{m}]" if d else m
                    for d, m in zip(
                        open_lines["Material Description"], open_lines["Material"], strict=True
                    )
                ],
                "Oldest goods issue": open_lines["Oldest Goods Issue"],
                "Quantity": open_lines["Quantity"].astype(float),
                "Value": open_lines["Value"].astype(float),
                "Days": days.fillna(0.0),
                "Dated": days.notna().astype(int),
            }
        ).reset_index(drop=True),
        "received": pd.DataFrame(
            {
                "Supplying plant": [
                    f"{p} · {names[p]}" if names.get(p) else p for p in received["Supplying Plant"]
                ],
                "Receiving plant": [
                    f"{p} · {names[p]}" if names.get(p) else p for p in received["Receiving Plant"]
                ],
                "Month": month_of(received["Goods Receipt Date"]),
                "Transit days": pd.to_numeric(received["Transit Days"], errors="coerce").fillna(
                    0.0
                ),
            }
        ).reset_index(drop=True),
    }


def build(
    open_lines: pd.DataFrame,
    received: pd.DataFrame,
    title: str,
    subtitle: str,
    checks: list[tuple[str, float, float, bool]],
) -> InteractiveDashboard:
    return InteractiveDashboard(
        title=title,
        subtitle=subtitle,
        intro=(
            "Stock issued by one plant (641) and not yet received by the other (101): value, age "
            "and the plants involved, with the transit time of the STOs already received."
        ),
        facts=facts(open_lines, received),
        measures={"open": OPEN_MEASURES, "received": RECEIVED_MEASURES},
        filters=(
            Filter("Supplying plant", "Supplying plant", "All supplying plants"),
            Filter("Receiving plant", "Receiving plant", "All receiving plants"),
            Filter("Age", "Age in transit", "All ages", order="given", values=tuple(AGE_BANDS)),
        ),
        kpis=(
            KpiTile("Value in transit", "value", "open", "{lines} lines · {stos} STOs"),
            KpiTile(
                "Average days in transit (open)", "avg_days", "open", "since goods issue", "amber"
            ),
            KpiTile(
                "Average transit time (received)", "avg_transit", "received", "{received} receipts"
            ),
        ),
        sections=(
            DashSection(
                "A · Age of the stock in transit",
                blocks=(
                    ChartSpec(
                        "Value in transit by age",
                        "open",
                        "Age",
                        ("value",),
                        ignore=("Age",),
                    ),
                    TableSpec(
                        "By age", "open", ("Age",), ("lines", "stos", "value"), ignore=("Age",)
                    ),
                ),
            ),
            DashSection(
                "B · Plants",
                blocks=(
                    ChartSpec(
                        "Value in transit by receiving plant",
                        "open",
                        "Receiving plant",
                        ("value",),
                        kind="hbar",
                        sort="desc",
                        sort_by="value",
                    ),
                    TableSpec(
                        "By receiving plant",
                        "open",
                        ("Receiving plant",),
                        ("lines", "stos", "value", "avg_days"),
                        sort_by="value",
                    ),
                    TableSpec(
                        "By supplying plant",
                        "open",
                        ("Supplying plant",),
                        ("lines", "stos", "value", "avg_days"),
                        sort_by="value",
                    ),
                    TableSpec(
                        "Transit time of received STOs by receiving plant",
                        "received",
                        ("Receiving plant",),
                        ("received", "avg_transit"),
                        sort_by="avg_transit",
                    ),
                ),
            ),
            DashSection(
                "C · Lines in transit",
                note="Oldest first; download them as CSV.",
                blocks=(
                    DetailSpec(
                        "Lines in transit",
                        "open",
                        (
                            ("STO", "STO", "text"),
                            ("Supplying plant", "From", "text"),
                            ("Receiving plant", "To", "text"),
                            ("Item", "Item", "text"),
                            ("Oldest goods issue", "Goods issue", "text"),
                            ("Days", "Days", "int"),
                            ("Quantity", "Quantity", "int"),
                            ("Value", "Value (RWF)", "rwf"),
                        ),
                        sort_by="Days",
                    ),
                ),
            ),
        ),
        footer="Rwanda Medical Supply · Stock in transit · MB5T and MB51.",
        checks=checks,
    )
