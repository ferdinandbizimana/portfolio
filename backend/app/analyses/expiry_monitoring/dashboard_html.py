"""Interactive dashboard of expiry monitoring: the board views of Ferdinand's
"Executive Expiry Dashboard" and "RMS Stock Expiry Dashboard", per plant."""

import pandas as pd

from app.analyses.expiry_monitoring import BANDS, CLEARED, EXPIRED
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

NEXT_SIX = (BANDS[1], BANDS[2])
CLOSING_MEASURES = (
    Measure("batches", "Batches", count=True),
    Measure("value", "Stock value (RWF)", "rwf", sum="Value"),
    Measure(
        "expired", "Expired value (RWF)", "rwf", sum="Value", where=("Expiry band", (EXPIRED,))
    ),
    Measure("expired_n", "Expired batches", count=True, where=("Expiry band", (EXPIRED,))),
    Measure(
        "not_blocked",
        "Expired batches not blocked",
        count=True,
        where=("Expired, not blocked", ("Yes",)),
    ),
    Measure("m3", "Within 3 months (RWF)", "rwf", sum="Value", where=("Expiry band", (BANDS[1],))),
    Measure("m6", "3 to 6 months (RWF)", "rwf", sum="Value", where=("Expiry band", (BANDS[2],))),
    Measure("next6", "Next 6 months (RWF)", "rwf", sum="Value", where=("Expiry band", NEXT_SIX)),
    Measure("next6_qty", "Next 6 months (qty)", sum="Quantity", where=("Expiry band", NEXT_SIX)),
    Measure(
        "next6_skus", "SKUs expiring in 6 months", distinct="Item", where=("Expiry band", NEXT_SIX)
    ),
    Measure("plants6", "Plants", distinct="Plant", where=("Expiry band", NEXT_SIX)),
)
DUE_MEASURES = (
    Measure("orig_qty", "Original units", sum="Quantity"),
    Measure("left_qty", "Units expired", sum="Expired Qty"),
    Measure("projected", "Projected expiries (RWF)", "rwf", sum="Value"),
    Measure("expired", "Expired of projected (RWF)", "rwf", sum="Expired Value"),
    Measure("saved", "Value saved (RWF)", "rwf", diff=("projected", "expired")),
    Measure("saved_pct", "Share saved", "pct", ratio=("saved", "projected")),
    Measure("orig_skus", "Original SKUs", distinct="Item"),
    Measure(
        "left_skus",
        "SKUs that expired",
        distinct="Item",
        where=("Outcome", ("Expired", "Partly cleared, rest expired")),
    ),
    Measure("cleared_skus", "SKUs cleared", distinct="Item", where=("Outcome", (CLEARED,))),
)


def _plant(code: pd.Series, name: pd.Series) -> list[str]:
    return [f"{c} · {n}" if n else c for c, n in zip(code, name.fillna(""), strict=True)]


def _item(material: pd.Series, description: pd.Series) -> list[str]:
    return [f"{d} [{m}]" if d else m for m, d in zip(material, description.fillna(""), strict=True)]


def facts(t: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    closing = t["closing_batches"]
    expired = t["expired"]
    not_blocked = {
        (p, m, b)
        for p, m, b, flag in zip(
            expired["Plant"],
            expired["Material"],
            expired["Batch"],
            expired["Not Blocked"],
            strict=True,
        )
        if flag
    }
    out = {
        "closing": pd.DataFrame(
            {
                "Plant": _plant(closing["Plant"], closing["Plant Name"]),
                "Stock owner": closing["Owner"],
                "WBS": closing["WBS"],
                "Material type": closing["Material Type"],
                "Expiry band": closing["Expiry Band"],
                "Expiry month": closing["Expiry Month"],
                "Item": _item(closing["Material"], closing["Description"]),
                "Batch": closing["Batch"],
                "Expiry date": closing["Expiry Date"],
                "Expired, not blocked": [
                    "Yes" if k in not_blocked else ""
                    for k in zip(
                        closing["Plant"], closing["Material"], closing["Batch"], strict=True
                    )
                ],
                "Quantity": closing["Quantity"].astype(float),
                "Value": closing["Value"].astype(float),
            }
        ),
        "due": pd.DataFrame(
            {
                "Plant": _plant(t["due"]["Plant"], t["due"]["Plant Name"]),
                "Stock owner": t["due"]["Owner"],
                "Material type": t["due"]["Material Type"],
                "Item": _item(t["due"]["Material"], t["due"]["Description"]),
                "Outcome": t["due"]["Outcome"],
                "Quantity": t["due"]["Quantity"].astype(float),
                "Value": t["due"]["Value"].astype(float),
                "Expired Qty": t["due"]["Expired Qty"].astype(float),
                "Expired Value": t["due"]["Expired Value"].astype(float),
            }
        ),
    }
    changes = t["expiry_changes"]
    if len(changes):
        out["changes"] = pd.DataFrame(
            {
                "Plant": _plant(changes["Plant"], changes["Plant Name"]),
                "Item": _item(changes["Material"], changes["Description"]),
                "Batch": changes["Batch"],
                "Old expiry": changes["Expiry Date (opening)"],
                "New expiry": changes["Expiry Date (closing)"],
                "Days changed": changes["Days Changed"].astype(float),
                "Value": changes["Value (closing)"].astype(float),
            }
        )
    moves = t["distributions"]
    if len(moves):
        short = moves[moves["Short Shelf Life"]]
        names = dict(zip(t["by_plant"]["Plant"], t["by_plant"]["Plant Name"], strict=True))
        out["short"] = pd.DataFrame(
            {
                "Plant": _plant(short["Plant"], short["Plant"].map(names)),
                "Movement type": short["Movement Type"],
                "Item": _item(short["Material"], short["Description"]),
                "Batch": short["Batch"],
                "Posting date": short["Posting Date"],
                "Expiry date": short["Expiry Date"],
                "Months left": short["Months Left"].astype(float),
                "Receiving plant": short["Receiving Plant"],
                "At the receiving plant": short["At the Receiving Plant"],
                "Value": short["Value"].astype(float),
            }
        )
    return out


def build(
    t: dict[str, pd.DataFrame],
    title: str,
    subtitle: str,
    short_months: int,
    checks: list[tuple[str, float, float, bool]],
) -> InteractiveDashboard:
    data = facts(t)
    measures: dict[str, tuple[Measure, ...]] = {"closing": CLOSING_MEASURES, "due": DUE_MEASURES}
    sections = [
        DashSection(
            "A · Products to expire in the next six months",
            note="From the closing ZSTOCKREPORT (executive expiry view).",
            blocks=(
                ChartSpec(
                    "Value expiring by month",
                    "closing",
                    "Expiry month",
                    ("next6",),
                    hide_zero=True,
                ),
                ChartSpec(
                    "Expiry value by plant (next six months)",
                    "closing",
                    "Plant",
                    ("m3", "m6"),
                    kind="hbar",
                    sort="desc",
                    sort_by="next6",
                    limit=30,
                    hide_zero=True,
                ),
                TableSpec(
                    "By material type",
                    "closing",
                    ("Material type",),
                    ("next6", "m3", "m6", "next6_skus"),
                    sort_by="next6",
                    hide_zero=True,
                ),
                TableSpec(
                    "By WBS element",
                    "closing",
                    ("WBS",),
                    ("next6", "m3", "m6", "next6_skus"),
                    sort_by="next6",
                    hide_zero=True,
                ),
                TableSpec(
                    "Top 10 items by value",
                    "closing",
                    ("Item",),
                    ("next6", "next6_qty"),
                    sort_by="next6",
                    limit=10,
                    hide_zero=True,
                ),
                TableSpec(
                    "Top 10 items by quantity",
                    "closing",
                    ("Item",),
                    ("next6_qty", "next6"),
                    sort_by="next6_qty",
                    limit=10,
                    hide_zero=True,
                ),
            ),
        ),
        DashSection(
            "B · Expiry intervention: projected against actual expiries",
            note=(
                "Batches of the opening ZSTOCKREPORT due to expire in the period. What is still in "
                "stock at the closing has expired; the rest was cleared (sold, distributed or "
                "donated). Value saved = projected minus expired."
            ),
            blocks=(
                ChartSpec(
                    "Projected and expired value by plant",
                    "due",
                    "Plant",
                    ("projected", "expired"),
                    kind="hbar",
                    sort="desc",
                    sort_by="projected",
                    limit=30,
                ),
                TableSpec(
                    "By plant",
                    "due",
                    ("Plant",),
                    ("orig_skus", "cleared_skus", "projected", "expired", "saved", "saved_pct"),
                    sort_by="projected",
                    bars=("saved_pct",),
                    traffic=(0.5, 0.8),
                ),
                TableSpec(
                    "Top 10 items due to expire (opening against closing)",
                    "due",
                    ("Item",),
                    ("orig_qty", "left_qty", "projected", "expired", "saved"),
                    sort_by="projected",
                    limit=10,
                ),
                TableSpec(
                    "By stock owner",
                    "due",
                    ("Stock owner",),
                    ("projected", "expired", "saved", "saved_pct"),
                    sort_by="projected",
                ),
            ),
        ),
        DashSection(
            "C · Expired stock per plant",
            note="Every expired batch must be blocked and moved to the quarantine plant.",
            blocks=(
                TableSpec(
                    "Expired stock by plant",
                    "closing",
                    ("Plant",),
                    ("expired", "expired_n", "not_blocked"),
                    sort_by="expired",
                ),
                TableSpec(
                    "Commercial and programme stock",
                    "closing",
                    ("Stock owner",),
                    ("expired", "m3", "m6"),
                    sort_by="expired",
                ),
            ),
        ),
    ]
    if "changes" in data:
        measures["changes"] = (
            Measure("changes", "Batches", count=True),
            Measure("value", "Value (RWF)", "rwf", sum="Value"),
        )
        sections.append(
            DashSection(
                "D · Batches whose expiry date changed",
                blocks=(
                    DetailSpec(
                        "Expiry date changes",
                        "changes",
                        (
                            ("Plant", "Plant", "text"),
                            ("Item", "Item", "text"),
                            ("Batch", "Batch", "text"),
                            ("Old expiry", "Old expiry", "text"),
                            ("New expiry", "New expiry", "text"),
                            ("Days changed", "Days", "int"),
                            ("Value", "Value (RWF)", "rwf"),
                        ),
                        sort_by="Value",
                    ),
                ),
            )
        )
    if "short" in data:
        measures["short"] = (
            Measure("lines", "Movements", count=True),
            Measure("value", "Value (RWF)", "rwf", sum="Value"),
        )
        sections.append(
            DashSection(
                f"E · Distributed with less than {short_months} months of shelf life",
                note="For a 641 transfer, what became of the batch at the receiving plant.",
                blocks=(
                    TableSpec(
                        "By movement type and receiving plant status",
                        "short",
                        ("Movement type", "At the receiving plant"),
                        ("lines", "value"),
                        sort_by="value",
                    ),
                    DetailSpec(
                        "Movements",
                        "short",
                        (
                            ("Plant", "Plant", "text"),
                            ("Movement type", "Type", "text"),
                            ("Item", "Item", "text"),
                            ("Batch", "Batch", "text"),
                            ("Posting date", "Posted", "text"),
                            ("Expiry date", "Expiry", "text"),
                            ("Months left", "Months left", "num"),
                            ("Receiving plant", "To", "text"),
                            ("At the receiving plant", "At the receiving plant", "text"),
                            ("Value", "Value (RWF)", "rwf"),
                        ),
                        sort_by="Value",
                    ),
                ),
            )
        )
    sections.append(
        DashSection(
            "F · Closing batches",
            blocks=(
                DetailSpec(
                    "Closing batches",
                    "closing",
                    (
                        ("Plant", "Plant", "text"),
                        ("Item", "Item", "text"),
                        ("Batch", "Batch", "text"),
                        ("Expiry date", "Expiry", "text"),
                        ("Expiry band", "Band", "text"),
                        ("Stock owner", "Owner", "text"),
                        ("Quantity", "Quantity", "int"),
                        ("Value", "Value (RWF)", "rwf"),
                    ),
                    sort_by="Value",
                ),
            ),
        )
    )
    return InteractiveDashboard(
        title=title,
        subtitle=subtitle,
        intro=(
            "Expired stock per plant, the batches due to expire in the period and what became of "
            "them, the value saved, and the 3- and 6-month outlook."
        ),
        facts=data,
        measures=measures,
        filters=(
            Filter("Plant", "Plant", "All plants"),
            Filter("Stock owner", "Stock owner", "Commercial and programme"),
            Filter("Material type", "Material type", "All material types"),
            Filter("WBS", "WBS element", "All WBS"),
            Filter("Expiry band", "Expiry band", "All bands", order="given", values=tuple(BANDS)),
            Filter("Item", "Item", "All items"),
        ),
        kpis=(
            KpiTile("Expired stock at closing", "expired", "closing", "{expired_n} batches", "red"),
            KpiTile("Expired batches not blocked", "not_blocked", "closing", "", "red"),
            KpiTile(
                "Projected expiries in the period", "projected", "due", "{orig_skus} SKUs", "amber"
            ),
            KpiTile(
                "Value saved with intervention", "saved", "due", "{saved_pct} of projected", "green"
            ),
            KpiTile("Expiring within 3 months", "m3", "closing", "", "amber"),
            KpiTile("Expiring in 3 to 6 months", "m6", "closing", "{plants6} plants", "blue"),
        ),
        sections=tuple(sections),
        footer="Rwanda Medical Supply · Expiry monitoring · monthly ZSTOCKREPORT snapshots.",
        checks=checks,
    )
