"""Stock in transit: the management view (lanes, lead times, ageing, actions).

What a supply-chain review looks at, computed from the same lines as the
analysis (Ferdinand, 29 October 2026: "do the best you can as an expert in
supply chain and give the analysis"):

- ageing: stock waiting longer than the limit is not available to customers
  and is exposed to loss and expiry; how much value, where, how old;
- lanes (supplying -> receiving plant): where the value waits, and how long
  the transfers already received took on the same lane (average and the 90th
  percentile, the time within which 9 transfers in 10 arrive);
- lead time split: STO creation -> goods issue (dispatch at the supplying
  warehouse) and goods issue -> goods receipt (transport and posting of the
  receipt), to show where the time is lost;
- data integrity: MB5T lines with no goods issue in MB51, STO lines whose MB5T
  and MB51 quantities differ, receipts without a matching issue;
- actions with a proposed owner and timing, written from the figures.

Pure functions on DataFrames; deterministic (stable sorts with tie-breakers).
"""

from typing import Any

import numpy as np
import pandas as pd

from app.reporting.documents import (
    ChartBlock,
    Highlight,
    KpiCard,
    Recommendation,
    ReportDocument,
    Section,
    TableBlock,
    ValueFormat,
)

TOLERANCE = 0.001
TOP = 10


def rwf(value: float) -> str:
    """RWF 1.23B / RWF 45.6M / RWF 12,345."""
    size = abs(value)
    if size >= 1e9:
        return f"RWF {value / 1e9:,.2f}B"
    if size >= 1e6:
        return f"RWF {value / 1e6:,.1f}M"
    return f"RWF {value:,.0f}"


def lines_text(count: int) -> str:
    return f"{count:,} line" if count == 1 else f"{count:,} lines"


def pct(share: float | None) -> str:
    return "n/a" if share is None else f"{share * 100:.1f}%"


def days(value: float | None) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{value:,.1f} days"


def _label(code: str, names: dict[str, str]) -> str:
    name = names.get(code, "")
    return f"{code} · {name}" if name else code


def _weighted(values: pd.Series, weights: pd.Series) -> float | None:
    known = values.notna() & weights.notna()
    total = float(weights[known].sum())
    return float((values[known] * weights[known]).sum()) / total if total else None


def _p90(values: pd.Series) -> float | None:
    known = values.dropna()
    return float(np.percentile(known.to_numpy(dtype=float), 90)) if len(known) else None


def lanes(transit: pd.DataFrame, received: pd.DataFrame, names: dict[str, str]) -> pd.DataFrame:
    """One row per supplying -> receiving plant pair, largest value waiting first."""
    keys = ["Supplying Plant", "Receiving Plant"]
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for (supplying, receiving), part in transit.groupby(keys, sort=True):
        over = part[part["Long Transit"]]
        rows[(str(supplying), str(receiving))] = {
            "Lines in Transit": len(part),
            "STOs": int(part["STO"].nunique()),
            "Value in Transit": float(part["Value"].sum()),
            "Over Limit Lines": len(over),
            "Over Limit Value": float(over["Value"].sum()),
            "Oldest Days": float(part["Days in Transit"].max())
            if part["Days in Transit"].notna().any()
            else None,
            "Average Days Open": _weighted(part["Days in Transit"], part["Quantity"]),
        }
    for (supplying, receiving), part in received.groupby(keys, sort=True):
        row = rows.setdefault(
            (str(supplying), str(receiving)),
            {
                "Lines in Transit": 0,
                "STOs": 0,
                "Value in Transit": 0.0,
                "Over Limit Lines": 0,
                "Over Limit Value": 0.0,
                "Oldest Days": None,
                "Average Days Open": None,
            },
        )
        row["Received Transfers"] = len(part)
        row["Average Transit Days"] = _weighted(part["Transit Days"], part["Quantity"])
        row["P90 Transit Days"] = _p90(part["Transit Days"])
    columns = [
        "Lane",
        "Supplying Plant",
        "Receiving Plant",
        "Lines in Transit",
        "STOs",
        "Value in Transit",
        "Over Limit Lines",
        "Over Limit Value",
        "Oldest Days",
        "Average Days Open",
        "Received Transfers",
        "Average Transit Days",
        "P90 Transit Days",
    ]
    frame = pd.DataFrame(
        [
            {
                "Lane": f"{_label(s, names)} → {_label(r, names)}",
                "Supplying Plant": s,
                "Receiving Plant": r,
                **values,
            }
            for (s, r), values in rows.items()
        ],
        columns=columns,
    )
    frame["Received Transfers"] = frame["Received Transfers"].fillna(0).astype(int)
    for column in ("Lines in Transit", "STOs", "Over Limit Lines"):
        frame[column] = frame[column].astype(int)
    for column in ("Oldest Days", "Average Days Open", "Average Transit Days", "P90 Transit Days"):
        frame[column] = frame[column].astype(float)
    return frame.sort_values(
        ["Value in Transit", "Lane"], ascending=[False, True], kind="mergesort"
    ).reset_index(drop=True)


def monthly(received: pd.DataFrame, limit: int) -> pd.DataFrame:
    """Transfers received per month of goods receipt: how long they took."""
    columns = [
        "Month",
        "Receipts",
        "Quantity",
        "Average Transit Days",
        "P90 Transit Days",
        "Over Limit Receipts",
    ]
    if received.empty:
        return pd.DataFrame(columns=columns)
    month = pd.to_datetime(received["Goods Receipt Date"]).dt.strftime("%Y-%m")
    rows = []
    for key, part in received.groupby(month, sort=True):
        rows.append(
            {
                "Month": str(key),
                "Receipts": len(part),
                "Quantity": float(part["Quantity"].sum()),
                "Average Transit Days": _weighted(part["Transit Days"], part["Quantity"]),
                "P90 Transit Days": _p90(part["Transit Days"]),
                "Over Limit Receipts": int((part["Transit Days"] > limit).sum()),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def lead_times(received: pd.DataFrame, names: dict[str, str]) -> pd.DataFrame:
    """Per supplying plant: STO creation -> goods issue -> goods receipt (days)."""
    columns = [
        "Plant",
        "Plant Name",
        "Received Transfers",
        "STO to Goods Issue",
        "Goods Issue to Receipt",
        "STO to Goods Receipt",
        "Share Before Goods Issue",
    ]
    rows = []
    for plant, part in received.groupby("Supplying Plant", sort=True):
        before = _weighted(part["Days STO to Goods Issue"], part["Quantity"])
        transport = _weighted(part["Transit Days"], part["Quantity"])
        total = _weighted(part["Days STO to Goods Receipt"], part["Quantity"])
        rows.append(
            {
                "Plant": str(plant),
                "Plant Name": names.get(str(plant), ""),
                "Received Transfers": len(part),
                "STO to Goods Issue": before,
                "Goods Issue to Receipt": transport,
                "STO to Goods Receipt": total,
                "Share Before Goods Issue": before / total
                if before is not None and total
                else None,
            }
        )
    frame = pd.DataFrame(rows, columns=columns)
    for column in columns[3:]:
        frame[column] = frame[column].astype(float)
    return frame.sort_values(
        ["Received Transfers", "Plant"], ascending=[False, True], kind="mergesort"
    ).reset_index(drop=True)


def oldest(transit: pd.DataFrame, names: dict[str, str], count: int = 15) -> pd.DataFrame:
    """The follow-up list: the lines waiting longest (then the largest value)."""
    dated = transit[transit["Days in Transit"].notna()]
    top = dated.sort_values(
        ["Days in Transit", "Value", "STO", "Material", "MB5T Line"],
        ascending=[False, False, True, True, True],
        kind="mergesort",
    ).head(count)
    return pd.DataFrame(
        {
            "STO": top["STO"],
            "Outbound Delivery": top["Delivery References"],
            "Lane": [
                f"{_label(s, names)} → {_label(r, names)}"
                for s, r in zip(top["Supplying Plant"], top["Receiving Plant"], strict=True)
            ],
            "Material": top["Material"],
            "Description": top["Material Description"],
            "Quantity": top["Quantity"].astype(float),
            "Value": top["Value"].astype(float),
            "Days in Transit": top["Days in Transit"].astype(float),
        }
    ).reset_index(drop=True)


def figures(
    transit: pd.DataFrame,
    received: pd.DataFrame,
    lane_table: pd.DataFrame,
    lead: pd.DataFrame,
    unmatched_receipts: float,
    limit: int,
    has_orders: bool,
) -> dict[str, Any]:
    """The numbers the narrative quotes (all from this run)."""
    total = float(transit["Value"].sum())
    over = transit[transit["Long Transit"]]
    no_issue = transit[transit["Days in Transit"].isna()]
    untraced = transit[transit["Difference with MB51"].abs().fillna(0.0) > TOLERANCE]
    untraced = untraced[transit.loc[untraced.index, "Days in Transit"].notna()]
    receiving = (
        over.groupby("Receiving Plant")["Value"]
        .sum()
        .sort_values(ascending=False, kind="mergesort")
        if len(over)
        else pd.Series(dtype=float)
    )
    average_transit = (
        _weighted(received["Transit Days"], received["Quantity"]) if len(received) else None
    )
    p90 = _p90(received["Transit Days"]) if len(received) else None
    slow = lane_table[
        (lane_table["Received Transfers"] >= 3)
        & (lane_table["Average Transit Days"] > max(limit, 2 * (average_transit or 0.0)))
    ].sort_values(["Average Transit Days", "Lane"], ascending=[False, True], kind="mergesort")
    before = (
        _weighted(received["Days STO to Goods Issue"], received["Quantity"]) if has_orders else None
    )
    whole = (
        _weighted(received["Days STO to Goods Receipt"], received["Quantity"])
        if has_orders
        else None
    )
    top3 = float(lane_table["Value in Transit"].head(3).sum())
    return {
        "total": total,
        "lines": len(transit),
        "stos": int(transit["STO"].nunique()),
        "lanes": int((lane_table["Lines in Transit"] > 0).sum()),
        "over_lines": len(over),
        "over_value": float(over["Value"].sum()),
        "over_share": float(over["Value"].sum()) / total if total else None,
        "oldest": float(transit["Days in Transit"].max())
        if transit["Days in Transit"].notna().any()
        else None,
        "double_limit_lines": int((transit["Days in Transit"] > 2 * limit).sum()),
        "open_days": _weighted(transit["Days in Transit"], transit["Quantity"]),
        "no_issue_lines": len(no_issue),
        "no_issue_value": float(no_issue["Value"].sum()),
        "untraced_lines": len(untraced),
        "unmatched_receipts": unmatched_receipts,
        "receiving_over": [(str(p), float(v)) for p, v in receiving.head(3).items()],
        "top3_share": top3 / total if total else None,
        "top_lanes": list(lane_table["Lane"].head(3)),
        "received": len(received),
        "average_transit": average_transit,
        "p90": p90,
        "slow_lanes": [
            (str(r["Lane"]), float(r["Average Transit Days"])) for _, r in slow.head(3).iterrows()
        ],
        "before_goods_issue": before,
        "sto_to_receipt": whole,
        "share_before": before / whole if before is not None and whole else None,
        "slow_dispatch": [
            (_plant_text(r), float(r["STO to Goods Issue"]))
            for _, r in lead[lead["STO to Goods Issue"].notna()]
            .sort_values(["STO to Goods Issue", "Plant"], ascending=[False, True], kind="mergesort")
            .head(3)
            .iterrows()
        ],
    }


def _plant_text(row: Any) -> str:
    return f"{row['Plant']} · {row['Plant Name']}" if row["Plant Name"] else str(row["Plant"])


def _names_of(items: list[tuple[str, float]], names: dict[str, str]) -> str:
    return ", ".join(_label(code, names) for code, _ in items)


def document(
    tables: dict[str, pd.DataFrame],
    f: dict[str, Any],
    names: dict[str, str],
    limit: int,
    report_date: str,
    subtitle: str,
) -> ReportDocument:
    """The SMT report: executive summary, sections A-H, actions and data notes."""
    money: ValueFormat = "money"
    formats: dict[str, ValueFormat] = {
        "Lines": "integer",
        "Value": "money",
        "Share": "percent",
        "Lines in Transit": "integer",
        "STOs": "integer",
        "Value in Transit": "money",
        "Over Limit Lines": "integer",
        "Over Limit Value": "money",
        "Oldest Days": "integer",
        "Average Days Open": "number",
        "Received Transfers": "integer",
        "Average Transit Days": "number",
        "P90 Transit Days": "number",
        "Receipts": "integer",
        "Quantity": "integer",
        "Over Limit Receipts": "integer",
        "STO to Goods Issue": "number",
        "Goods Issue to Receipt": "number",
        "STO to Goods Receipt": "number",
        "Share Before Goods Issue": "percent",
        "Days in Transit": "integer",
        "OBD Value (MB51)": "money",
        "Long Transit Lines": "integer",
    }
    over_share = f["over_share"] or 0.0
    by_age = tables["by_age"].copy()
    by_age["Share"] = by_age["Value"] / f["total"] if f["total"] else 0.0
    lane_table = tables["by_lane"]
    open_lanes = lane_table[lane_table["Lines in Transit"] > 0]
    receiving = tables["by_receiving"]
    materials = tables["by_material"]
    month = tables["received_by_month"]
    lead = tables["lead_time"]

    kpis = [
        KpiCard(
            "Value in transit", rwf(f["total"]), f"{lines_text(f['lines'])} · {f['stos']:,} STOs"
        ),
        KpiCard(
            f"Over {limit} days",
            lines_text(f["over_lines"]),
            f"{rwf(f['over_value'])} · {pct(f['over_share'])} of value",
            "red" if over_share > 0.2 else "yellow",
        ),
        KpiCard(
            "Average days open",
            days(f["open_days"]).replace(" days", ""),
            "since goods issue",
            "yellow",
        ),
        KpiCard(
            "Transit time received",
            days(f["average_transit"]).replace(" days", ""),
            f"90% within {days(f['p90'])}" if f["p90"] is not None else "no receipts in MB51",
            "green",
        ),
        KpiCard(
            "No goods issue in MB51",
            lines_text(f["no_issue_lines"]),
            rwf(f["no_issue_value"]),
            "grey",
        ),
    ]
    highlights = [
        Highlight(
            "1 · Ageing",
            f"{f['over_lines']:,} of {lines_text(f['lines'])} ({rwf(f['over_value'])}, "
            f"{pct(f['over_share'])} of the value) have been in transit more than {limit} days"
            + (f"; the oldest has waited {days(f['oldest'])}." if f["oldest"] is not None else ".")
            + (
                f" {f['double_limit_lines']:,} lines are past twice the limit."
                if f["double_limit_lines"]
                else ""
            ),
            "red" if over_share > 0.2 else "yellow",
        ),
        Highlight(
            "2 · Where it waits",
            f"The three largest lanes hold {pct(f['top3_share'])} of the value in transit: "
            + "; ".join(f["top_lanes"])
            + "."
            + (
                f" Most value past the limit waits at {_names_of(f['receiving_over'], names)}."
                if f["receiving_over"]
                else ""
            ),
            "yellow",
        ),
        Highlight(
            "3 · Lead time",
            (
                f"Transfers received in the MB51 period took {days(f['average_transit'])} from "
                f"goods issue to goods receipt; 9 in 10 arrived within {days(f['p90'])}."
                if f["received"]
                else "No transfer was received in the MB51 period, so no transit time is measured."
            )
            + (
                f" {pct(f['share_before'])} of the time from STO creation to receipt is spent "
                "before the goods issue."
                if f["share_before"] is not None
                else ""
            ),
            "green",
        ),
    ]
    if f["no_issue_lines"] or f["untraced_lines"]:
        highlights.append(
            Highlight(
                "4 · Data to correct",
                f"{f['no_issue_lines']:,} MB5T lines ({rwf(f['no_issue_value'])}) have no goods "
                f"issue in MB51 and {f['untraced_lines']:,} STO lines show different quantities "
                "in MB5T and MB51.",
                "grey",
            )
        )

    age_chart = ChartBlock(
        "Value in transit by age (RWF)",
        [str(a) for a in by_age["Age"]],
        {"Value": [float(v) for v in by_age["Value"]]},
        "column",
        money,
    )
    top_lanes = open_lanes.head(TOP)
    lane_chart = ChartBlock(
        "Value in transit by lane (RWF), top 10",
        [str(x) for x in top_lanes["Lane"]],
        {"Value": [float(v) for v in top_lanes["Value in Transit"]]},
        "bar",
        money,
    )
    rec_sorted = receiving.sort_values(
        ["Value in Transit", "Plant"], ascending=[False, True], kind="mergesort"
    )
    rec_chart = ChartBlock(
        f"Value past {limit} days by receiving plant (RWF)",
        [_label(str(p), names) for p in rec_sorted["Plant"].head(TOP)],
        {
            "Value past the limit": [
                float(
                    tables["in_transit"]
                    .loc[
                        (tables["in_transit"]["Receiving Plant"] == p)
                        & (tables["in_transit"]["Days in Transit"] > limit),
                        "Value",
                    ]
                    .sum()
                )
                for p in rec_sorted["Plant"].head(TOP)
            ]
        },
        "bar",
        money,
    )
    sections = [
        Section(
            "A · Age of the stock in transit",
            message=(
                f"{pct(f['over_share'])} of the value has waited more than {limit} days "
                "for its goods receipt"
            ),
            charts=[age_chart],
            tables=[
                TableBlock(
                    "By age", by_age[["Age", "Lines", "Value", "Share"]], formats, total_row=True
                )
            ],
            takeaway=(
                "Stock in transit is owned but not available: it cannot be sold, issued or "
                f"counted at either plant. Lines past {limit} days are either received but not "
                "posted (a goods receipt to post), still on the road (a delivery to chase) or "
                "lost (a write-off to investigate); each needs a decision."
            ),
        ),
        Section(
            "B · Lanes: where the stock is waiting",
            message=(
                f"The three largest of {f['lanes']:,} lanes hold {pct(f['top3_share'])} "
                "of the value in transit"
            ),
            charts=[lane_chart],
            tables=[
                TableBlock(
                    "Top lanes",
                    top_lanes[
                        [
                            "Lane",
                            "Lines in Transit",
                            "Value in Transit",
                            "Over Limit Lines",
                            "Oldest Days",
                        ]
                    ],
                    formats,
                )
            ],
            takeaway=(
                "Follow-up is most effective lane by lane: one call between the supplying and "
                "the receiving warehouse clears every STO of the lane."
            ),
        ),
        Section(
            "C · Receiving plants",
            message=(
                f"Most value past the limit waits at {_names_of(f['receiving_over'], names)}"
                if f["receiving_over"]
                else f"No receiving plant has stock past {limit} days"
            ),
            charts=[rec_chart],
            tables=[
                TableBlock(
                    "By receiving plant",
                    rec_sorted[
                        [
                            "Plant",
                            "Plant Name",
                            "Lines in Transit",
                            "Value in Transit",
                            "Long Transit Lines",
                        ]
                    ].head(TOP),
                    formats,
                )
            ],
            takeaway=(
                "The receiving plant closes the transfer: the goods receipt (101) should be "
                "posted the day the truck arrives. Plants with old lines either receive late or "
                "post late; a physical check of the dock and the receiving area tells which."
            ),
        ),
    ]
    if len(month):
        sections.append(
            Section(
                "D · Transit time of the transfers received",
                message=(
                    f"Goods issue to goods receipt took {days(f['average_transit'])} on average; "
                    f"9 in 10 arrived within {days(f['p90'])}"
                ),
                charts=[
                    ChartBlock(
                        "Transit time by month of receipt (days)",
                        [str(m) for m in month["Month"]],
                        {
                            "Average": [
                                float(v) for v in month["Average Transit Days"].fillna(0.0)
                            ],
                            "90% within": [float(v) for v in month["P90 Transit Days"].fillna(0.0)],
                        },
                        "line",
                        "number",
                    )
                ],
                tables=[TableBlock("By month of receipt", month, formats)],
                takeaway=(
                    "The 90% line is the promise a receiving plant can plan on. "
                    + (
                        "The slowest lanes: "
                        + "; ".join(f"{lane} ({d:.1f} days)" for lane, d in f["slow_lanes"])
                        + "."
                        if f["slow_lanes"]
                        else "No lane is much slower than the others."
                    )
                ),
            )
        )
    if f["share_before"] is not None and len(lead):
        top_lead = lead.head(TOP)
        sections.append(
            Section(
                "E · Lead time: dispatch and transport",
                message=(
                    f"{pct(f['share_before'])} of the time from STO creation to goods receipt "
                    "is spent before the goods leave the supplying warehouse"
                ),
                charts=[
                    ChartBlock(
                        "Days from STO creation to receipt, by supplying plant",
                        [_plant_text(r) for _, r in top_lead.iterrows()],
                        {
                            "STO to goods issue": [
                                float(v) for v in top_lead["STO to Goods Issue"].fillna(0.0)
                            ],
                            "Goods issue to receipt": [
                                float(v) for v in top_lead["Goods Issue to Receipt"].fillna(0.0)
                            ],
                        },
                        "stacked",
                        "number",
                    )
                ],
                tables=[TableBlock("Lead time by supplying plant", top_lead, formats)],
                takeaway=(
                    "Time before the goods issue is warehouse time (picking, packing, loading); "
                    "time after it is transport and receipt posting. Each has a different owner."
                ),
            )
        )
    top_materials = materials.head(TOP)
    top_share = float(top_materials["Value in Transit"].sum()) / f["total"] if f["total"] else None
    sections.append(
        Section(
            "F · Materials in transit",
            message=f"The top 10 materials hold {pct(top_share)} of the value in transit",
            charts=[
                ChartBlock(
                    "Value in transit by material (RWF), top 10",
                    [
                        f"{d} [{m}]" if d else str(m)
                        for d, m in zip(
                            top_materials["Material Description"],
                            top_materials["Material"],
                            strict=True,
                        )
                    ],
                    {"Value": [float(v) for v in top_materials["Value in Transit"]]},
                    "bar",
                    money,
                )
            ],
            tables=[
                TableBlock(
                    "Top materials",
                    top_materials[
                        [
                            "Material",
                            "Material Description",
                            "Lines in Transit",
                            "Quantity",
                            "Value in Transit",
                        ]
                    ],
                    formats,
                )
            ],
            takeaway=(
                "High-value and fast-moving materials in transit are stock the receiving plant "
                "cannot issue: if they run short there, receiving them first protects service."
            ),
        )
    )
    sections.append(
        Section(
            "G · Oldest lines: the follow-up list",
            message="The lines waiting longest, to clear one by one",
            tables=[TableBlock("Oldest lines", tables["oldest"], formats, max_rows=12)],
            takeaway=(
                "For each line: confirm with the receiving plant whether the goods arrived; post "
                "the receipt if they did; trace the delivery with the transporter if not."
            ),
        )
    )
    sections.append(
        Section(
            "H · Data integrity",
            message="Lines the system cannot explain yet",
            kpis=[
                KpiCard(
                    "No goods issue in MB51",
                    f"{f['no_issue_lines']:,}",
                    rwf(f["no_issue_value"]),
                    "grey",
                ),
                KpiCard("MB5T and MB51 differ", f"{f['untraced_lines']:,}", "STO lines", "grey"),
                KpiCard(
                    "Receipts without an issue",
                    f"{f['unmatched_receipts']:,.0f}",
                    "units in MB51",
                    "grey",
                ),
            ],
            bullets=[
                "No goods issue in MB51: the 641 was posted before the start of the MB51 export, "
                "or the STO was never shipped.",
                "Different quantities: partial deliveries, reversals (642, 102, 122) or postings "
                "outside the MB51 period.",
                "Receipts without an issue: the goods issue lies before the MB51 period.",
            ],
            takeaway=(
                "Extend MB51 back to the oldest STO date to confirm; what remains unexplained "
                "is a posting to correct."
            ),
        )
    )

    recommendations: list[Recommendation] = []
    if f["over_lines"]:
        where = (
            f" starting with {_names_of(f['receiving_over'], names)}" if f["receiving_over"] else ""
        )
        recommendations.append(
            Recommendation(
                f"Confirm physical receipt and post the goods receipt (101) for the "
                f"{lines_text(f['over_lines'])} in transit more than {limit} days "
                f"({rwf(f['over_value'])}){where}",
                "Receiving plant managers",
                "Within 7 days",
            )
        )
    if f["no_issue_lines"]:
        recommendations.append(
            Recommendation(
                f"Review the {f['no_issue_lines']:,} MB5T "
                f"{'line' if f['no_issue_lines'] == 1 else 'lines'} with no goods issue in MB51 "
                f"({rwf(f['no_issue_value'])}): extend MB51 to the STO dates, then correct or "
                "close the STOs that were never shipped",
                "Inventory control with the SAP MM key user",
                "Within 14 days",
            )
        )
    if f["untraced_lines"]:
        recommendations.append(
            Recommendation(
                f"Reconcile the {f['untraced_lines']:,} STO lines where MB5T and MB51 "
                "quantities differ",
                "Inventory control",
                "Within 14 days",
            )
        )
    if f["slow_lanes"]:
        recommendations.append(
            Recommendation(
                "Agree a transit-time target for the slowest lanes ("
                + "; ".join(f"{lane}: {d:.1f} days" for lane, d in f["slow_lanes"])
                + f") against {days(f['average_transit'])} overall",
                "Distribution manager",
                "Within 30 days",
            )
        )
    if f["share_before"] is not None and f["share_before"] >= 0.5 and f["slow_dispatch"]:
        recommendations.append(
            Recommendation(
                "Shorten the time from STO creation to goods issue at "
                + ", ".join(f"{p} ({d:.1f} days)" for p, d in f["slow_dispatch"])
                + ": most of the lead time is spent before the stock leaves the warehouse",
                "Warehouse managers of the supplying plants",
                "Within 30 days",
            )
        )
    recommendations.append(
        Recommendation(
            f"Review stock in transit every week against the {limit}-day limit and escalate "
            f"lines older than {2 * limit} days to the plant manager",
            "Inventory & Warehouse Management",
            "Weekly",
        )
    )
    notes = [
        Highlight(
            "Sources",
            f"MB5T stock in transit of {report_date}; MB51 goods issues (641) and receipts (101) "
            "with their reversals (642, 102, 122); ME2M STO creation dates when supplied; OX10 "
            "plant names.",
        ),
        Highlight(
            "Value",
            "MB5T value of each line; when MB5T has none, the value of the goods issue (641) of "
            "the outbound delivery in MB51 for the quantity still in transit.",
        ),
        Highlight(
            "Days",
            "Days in transit run from the oldest goods issue still open to the MB5T date. "
            "Transit time runs from goods issue to goods receipt, matched by outbound delivery "
            "first, then oldest issue first.",
        ),
        Highlight(
            "Limit",
            f"A line is past the limit when it has been in transit more than {limit} days "
            "(a parameter of the run).",
        ),
    ]
    return ReportDocument(
        title="Stock in transit",
        subtitle=subtitle,
        date_text=report_date,
        sections=sections,
        summary_message=(
            f"{rwf(f['total'])} is in transit on {lines_text(f['lines'])}; "
            f"{pct(f['over_share'])} of the value has waited more than {limit} days "
            "for its goods receipt"
        ),
        kpis=kpis,
        highlights=highlights,
        recommendations=recommendations,
        notes=notes,
        audience="Senior Management Team · Inventory & Warehouse Management",
        draft=True,
    )
