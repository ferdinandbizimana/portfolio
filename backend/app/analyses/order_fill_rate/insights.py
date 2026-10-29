# ruff: noqa: E501, RUF001  (report prose: long sentences and typographic dashes on purpose)
"""Order fill rate in the style of Ferdinand's "RMS Order Fill Rate — Master Prompt (v3)".

Ferdinand, 29 October 2026: keep the VA05 template, the outbound deliveries and
OX10 (regions, districts, plant names), and adopt the v3 prompt's style:

- data checks first: months present against the 12 fiscal months, rows left
  out by reason (outside the period, customer returns ZRRE, unassigned plant,
  zero quantity), schedule lines counted once, ordered value recomputed as
  quantity x net price and reconciled month by month;
- A loss per WBS element (RM revenue not captured; donor units not delivered),
  B monthly trend, quarters (Q1 Jul-Sep ... Q4 Apr-Jun) with their main items
  and weakest plants, C plants, D items most requested but not delivered (top
  RM by value, top donor by units, most frequently short), E most-missing items
  over time, F Delivered-In-Full per order type, G customers by value not
  delivered;
- an SMT report: executive summary, how to read the figures, sections,
  recommendations (owner and timing) and data notes; shortfalls are positive
  numbers, tables and charts sorted by their own measure, every sentence quotes
  figures of the same run.

Pure functions on the order lines; deterministic.
"""

from typing import Any

import pandas as pd

from app.analyses.common.periods import QUARTERS, fiscal_quarter
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

IN_FULL, NOT_DELIVERED = "Delivered in full", "Not delivered"
WBS_OWN, WBS_PROGRAMME = "RMS-OWN-ESE-RM", "RMS-PRG-FND-CP"
TOP = 10
TOLERANCE = 0.5  # RWF, when reconciling recomputed values


def rwf(value: float) -> str:
    size = abs(value)
    if size >= 1e9:
        return f"RWF {value / 1e9:,.2f}B"
    if size >= 1e6:
        return f"RWF {value / 1e6:,.1f}M"
    return f"RWF {value:,.0f}"


def units(value: float) -> str:
    size = abs(value)
    if size >= 1e6:
        return f"{value / 1e6:,.1f}M units"
    if size >= 1e4:
        return f"{value / 1e3:,.0f}K units"
    return f"{value:,.0f} units"


def pct(share: float | None) -> str:
    return "n/a" if share is None else f"{share * 100:.1f}%"


def _rate(part: float, whole: float) -> float | None:
    return part / whole if whole else None


def _month_label(month: str) -> str:
    """ "2025-07" -> "Jul-25"."""
    return pd.Timestamp(f"{month}-01").strftime("%b-%y")


# --- Data checks ---------------------------------------------------------------------


def fiscal_months(start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
    return [m.strftime("%Y-%m") for m in pd.period_range(start, end, freq="M").to_timestamp()]


def data_checks(
    source: pd.DataFrame, orders: pd.DataFrame, schedule_items: int, params: Any
) -> pd.DataFrame:
    """What was read, what was left out and why, and the months present."""
    start, end = pd.Timestamp(params.period_start), pd.Timestamp(params.period_end)
    expected = fiscal_months(start, end)
    kept = source[source["Reason"] == ""]
    present = sorted(set(kept["Order Date"].dt.strftime("%Y-%m").dropna()))
    missing = [m for m in expected if m not in present]
    rows: list[dict[str, Any]] = [
        {"Check": "VA05 rows read", "Value": float(len(source)), "Note": ""},
        {
            "Check": "Months with orders",
            "Value": float(len(present)),
            "Note": f"of {len(expected)} in the period"
            + (f"; missing: {', '.join(_month_label(m) for m in missing)}" if missing else ""),
        },
    ]
    for reason, part in source[source["Reason"] != ""].groupby("Reason", sort=True):
        rows.append({"Check": f"Left out: {reason}", "Value": float(len(part)), "Note": ""})
    rows.append(
        {
            "Check": "Order items with repeated schedule lines",
            "Value": float(schedule_items),
            "Note": "the item quantity and value are counted once",
        }
    )
    rows.append({"Check": "Order lines analysed", "Value": float(len(orders)), "Note": ""})
    if "Source File" in source.columns:
        files = sorted({f for f in source["Source File"] if f})
        if files:
            rows.append(
                {"Check": "VA05 files read", "Value": float(len(files)), "Note": ", ".join(files)}
            )
    return pd.DataFrame(rows, columns=["Check", "Value", "Note"])


def source_check(source: pd.DataFrame) -> pd.DataFrame:
    """VA05 rows per fiscal quarter: read, left out by reason, analysed (v3 Source_Check)."""
    frame = source.assign(
        Quarter=[
            fiscal_quarter(int(m)) if pd.notna(m) else "No order date"
            for m in source["Order Date"].dt.month
        ]
    )
    reasons = sorted({r for r in frame["Reason"] if r})
    rows = []
    for quarter in [*QUARTERS, "No order date"]:
        part = frame[frame["Quarter"] == quarter]
        if part.empty:
            continue
        row: dict[str, Any] = {"Quarter": quarter, "Rows Read": len(part)}
        for reason in reasons:
            row[reason] = int((part["Reason"] == reason).sum())
        row["Rows Analysed"] = int((part["Reason"] == "").sum())
        rows.append(row)
    return pd.DataFrame(rows, columns=["Quarter", "Rows Read", *reasons, "Rows Analysed"])


def value_reconciliation(source: pd.DataFrame) -> pd.DataFrame:
    """Ordered value recomputed as quantity x net price against VA05's net value, by month."""
    columns = ["Month", "Rows", "Net Value (VA05)", "Quantity x Net Price", "Difference"]
    kept = source[(source["Reason"] == "") & source["Net Price"].notna()]
    if kept.empty:
        return pd.DataFrame(columns=columns)
    kept = kept.assign(
        Month=kept["Order Date"].dt.strftime("%Y-%m"),
        Recomputed=kept["Ordered Qty"] * kept["Net Price"],
    )
    rows = []
    for month, part in kept.groupby("Month", sort=True):
        supplied, recomputed = float(part["Ordered Value"].sum()), float(part["Recomputed"].sum())
        rows.append(
            {
                "Month": _month_label(str(month)),
                "Rows": len(part),
                "Net Value (VA05)": supplied,
                "Quantity x Net Price": recomputed,
                "Difference": recomputed - supplied,
            }
        )
    return pd.DataFrame(rows, columns=columns)


# --- Analyses ------------------------------------------------------------------------


def _measures(part: pd.DataFrame) -> dict[str, Any]:
    ordered_qty, filled_qty = float(part["Ordered Qty"].sum()), float(part["Filled Qty"].sum())
    ordered_value, delivered_value = (
        float(part["Ordered Value"].sum()),
        float(part["Delivered Value"].sum()),
    )
    full = part["Status"] == IN_FULL
    return {
        "Order Lines": len(part),
        "Ordered Qty": ordered_qty,
        "Delivered Qty": filled_qty,
        "Not Delivered Qty": ordered_qty - filled_qty,
        "Delivered Qty %": _rate(filled_qty, ordered_qty),
        "Ordered Value": ordered_value,
        "Delivered Value": delivered_value,
        "Value Not Delivered": ordered_value - delivered_value,
        "Delivered Value %": _rate(delivered_value, ordered_value),
        "Line DIF %": _rate(int(full.sum()), len(part)),
        "Lines Nothing Delivered %": _rate(int((part["Status"] == NOT_DELIVERED).sum()), len(part)),
    }


def prepare(lines: pd.DataFrame) -> pd.DataFrame:
    return lines.assign(
        **{
            "Short Qty": lines["Ordered Qty"] - lines["Filled Qty"],
            "Value Not Delivered": lines["Ordered Value"] - lines["Delivered Value"],
            "Short": lines["Status"] != IN_FULL,
        }
    )


def by_wbs(lines: pd.DataFrame) -> pd.DataFrame:
    rows = [{"WBS": wbs, **_measures(part)} for wbs, part in lines.groupby("WBS", sort=True)]
    return pd.DataFrame(rows)


def by_month(lines: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for month, part in lines.groupby("Month", sort=True):
        own = part[part["WBS"] == WBS_OWN]
        donor = part[part["WBS"] == WBS_PROGRAMME]
        rows.append(
            {
                "Month": _month_label(str(month)),
                **_measures(part),
                "RM Value Not Delivered": float(own["Value Not Delivered"].sum()),
                "Donor Units Not Delivered": float(donor["Short Qty"].sum()),
            }
        )
    return pd.DataFrame(rows)


def _plant_label(row: pd.Series) -> str:
    return str(row["Shipping Plant"])


def by_plant(lines: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {"Plant": plant, **_measures(part)}
        for plant, part in lines.groupby("Shipping Plant", sort=True)
    ]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(
        ["Value Not Delivered", "Plant"], ascending=[False, True], kind="mergesort"
    ).reset_index(drop=True)


def _top_item(part: pd.DataFrame, measure: str) -> str:
    if part.empty or float(part[measure].sum()) <= 0:
        return ""
    totals = part.groupby("Item Name")[measure].sum()
    totals = totals[totals > 0].sort_values(ascending=False, kind="mergesort")
    return "; ".join(f"{name}" for name in totals.head(2).index)


def by_quarter(lines: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for quarter in QUARTERS:
        part = lines[lines["Quarter"] == quarter]
        if part.empty:
            continue
        own = part[part["WBS"] == WBS_OWN]
        donor = part[part["WBS"] == WBS_PROGRAMME]
        plants = by_plant(part)
        weakest = (
            plants[plants["Ordered Value"] >= 0.01 * float(part["Ordered Value"].sum())]
            .sort_values(["Delivered Value %", "Plant"], kind="mergesort")
            .head(3)
        )
        rows.append(
            {
                "Quarter": quarter,
                **_measures(part),
                "RM Value Not Delivered": float(own["Value Not Delivered"].sum()),
                "Donor Units Not Delivered": float(donor["Short Qty"].sum()),
                "Main RM Items Short": _top_item(own, "Value Not Delivered"),
                "Main Donor Items Short": _top_item(donor, "Short Qty"),
                "Weakest Plants": "; ".join(
                    f"{p} ({pct(v)})"
                    for p, v in zip(weakest["Plant"], weakest["Delivered Value %"], strict=True)
                ),
            }
        )
    return pd.DataFrame(rows)


def top_items(lines: pd.DataFrame, wbs: str, measure: str) -> pd.DataFrame:
    part = lines[lines["WBS"] == wbs]
    columns = [
        "Item",
        "Ordered Qty",
        "Not Delivered Qty",
        "% Short",
        "Lines Short",
        "Value Not Delivered",
    ]
    if part.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for item, group in part.groupby("Item Name", sort=True):
        ordered = float(group["Ordered Qty"].sum())
        rows.append(
            {
                "Item": item,
                "Ordered Qty": ordered,
                "Not Delivered Qty": float(group["Short Qty"].sum()),
                "% Short": _rate(float(group["Short Qty"].sum()), ordered),
                "Lines Short": int(group["Short"].sum()),
                "Value Not Delivered": float(group["Value Not Delivered"].sum()),
            }
        )
    frame = pd.DataFrame(rows, columns=columns)
    key = "Value Not Delivered" if measure == "value" else "Not Delivered Qty"
    frame = frame[frame[key] > 0]
    return (
        frame.sort_values([key, "Item"], ascending=[False, True], kind="mergesort")
        .head(TOP)
        .reset_index(drop=True)
    )


def frequently_short(lines: pd.DataFrame) -> pd.DataFrame:
    """Items customers order again and again that are often not delivered in full."""
    columns = [
        "Item",
        "Order Lines",
        "Lines Short",
        "% Lines Short",
        "Customers Affected",
        "Months Affected",
        "Value Not Delivered",
    ]
    rows = []
    for item, group in lines.groupby("Item Name", sort=True):
        short = group[group["Short"]]
        if short.empty:
            continue
        rows.append(
            {
                "Item": item,
                "Order Lines": len(group),
                "Lines Short": len(short),
                "% Lines Short": len(short) / len(group),
                "Customers Affected": int(short["Customer"].nunique()),
                "Months Affected": int(short["Month"].nunique()),
                "Value Not Delivered": float(group["Value Not Delivered"].sum()),
            }
        )
    frame = pd.DataFrame(rows, columns=columns)
    return (
        frame.sort_values(["Lines Short", "Item"], ascending=[False, True], kind="mergesort")
        .head(TOP)
        .reset_index(drop=True)
    )


def items_over_time(lines: pd.DataFrame, count: int = 8) -> pd.DataFrame:
    """RM value not delivered by month for the items with the largest total shortfall."""
    own = lines[lines["WBS"] == WBS_OWN]
    totals = own.groupby("Item Name")["Value Not Delivered"].sum()
    totals = totals[totals > 0].sort_values(ascending=False, kind="mergesort").head(count)
    months = sorted(set(lines["Month"]))
    rows = []
    for month in months:
        part = own[own["Month"] == month]
        row: dict[str, Any] = {"Month": _month_label(month)}
        for item in totals.index:
            row[str(item)] = float(part.loc[part["Item Name"] == item, "Value Not Delivered"].sum())
        rows.append(row)
    return pd.DataFrame(rows, columns=["Month", *[str(i) for i in totals.index]])


def dif_by_type(lines: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for kind, part in lines.groupby("Sales Type", sort=True):
        orders = part.groupby("Sales Document")["Status"]
        in_full = orders.agg(lambda s: bool((s == IN_FULL).all()))
        nil = orders.agg(lambda s: bool((s == NOT_DELIVERED).any()))
        rows.append(
            {
                "Order Type": kind or "(blank)",
                "Orders": len(in_full),
                "Orders DIF %": _rate(int(in_full.sum()), len(in_full)),
                "Orders With a Nil-Delivery Line %": _rate(int(nil.sum()), len(nil)),
                "Line DIF %": _rate(int((part["Status"] == IN_FULL).sum()), len(part)),
            }
        )
    return pd.DataFrame(rows)


def lowest_dif_items(lines: pd.DataFrame, minimum_lines: int) -> pd.DataFrame:
    rows = []
    for item, group in lines.groupby("Item Name", sort=True):
        if len(group) < minimum_lines:
            continue
        rows.append(
            {
                "Item": item,
                "Order Lines": len(group),
                "Line DIF %": _rate(int((group["Status"] == IN_FULL).sum()), len(group)),
                "% Short": _rate(
                    float(group["Short Qty"].sum()), float(group["Ordered Qty"].sum())
                ),
            }
        )
    frame = pd.DataFrame(rows, columns=["Item", "Order Lines", "Line DIF %", "% Short"])
    return (
        frame.sort_values(["Line DIF %", "Item"], kind="mergesort").head(TOP).reset_index(drop=True)
    )


def top_customers(lines: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for customer, part in lines.groupby("Customer", sort=True):
        orders = part.groupby("Sales Document")["Status"].agg(lambda s: bool((s == IN_FULL).all()))
        name = str(part["Customer Name"].max() or customer)
        rows.append(
            {
                "Customer": name,
                **_measures(part),
                "Orders": len(orders),
                "Orders DIF %": _rate(int(orders.sum()), len(orders)),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return (
        frame.sort_values(
            ["Value Not Delivered", "Customer"], ascending=[False, True], kind="mergesort"
        )
        .head(TOP)
        .reset_index(drop=True)
    )


def tables(lines: pd.DataFrame) -> dict[str, pd.DataFrame]:
    lines = prepare(lines)
    minimum = max(10, len(lines) // 200)
    return {
        "v3_by_wbs": by_wbs(lines),
        "v3_by_month": by_month(lines),
        "v3_by_quarter": by_quarter(lines),
        "v3_by_plant": by_plant(lines),
        "v3_top_rm_items": top_items(lines, WBS_OWN, "value"),
        "v3_top_donor_items": top_items(lines, WBS_PROGRAMME, "units"),
        "v3_frequently_short": frequently_short(lines),
        "v3_items_over_time": items_over_time(lines),
        "v3_dif_by_type": dif_by_type(lines),
        "v3_lowest_dif_items": lowest_dif_items(lines, minimum),
        "v3_top_customers": top_customers(lines),
    }


def figures(lines: pd.DataFrame) -> dict[str, Any]:
    lines = prepare(lines)
    all_ = _measures(lines)
    own = lines[lines["WBS"] == WBS_OWN]
    donor = lines[lines["WBS"] == WBS_PROGRAMME]
    orders = lines.groupby("Sales Document")["Status"].agg(lambda s: bool((s == IN_FULL).all()))
    own_m, donor_m = _measures(own), _measures(donor)
    short_lines = lines[lines["Short"]]
    nothing = lines[lines["Status"] == NOT_DELIVERED]
    return {
        **{f"all_{k}": v for k, v in all_.items()},
        "lines": len(lines),
        "lines_in_full": int((lines["Status"] == IN_FULL).sum()),
        "orders": len(orders),
        "orders_in_full": int(orders.sum()),
        "rm_ordered_value": own_m["Ordered Value"],
        "rm_value_not_delivered": own_m["Value Not Delivered"],
        "rm_share_not_delivered": _rate(own_m["Value Not Delivered"], own_m["Ordered Value"]),
        "donor_units_ordered": donor_m["Ordered Qty"],
        "donor_units_not_delivered": donor_m["Not Delivered Qty"],
        "donor_share_not_delivered": _rate(donor_m["Not Delivered Qty"], donor_m["Ordered Qty"]),
        "donor_qty_pct": donor_m["Delivered Qty %"],
        "rm_qty_pct": own_m["Delivered Qty %"],
        "short_lines": len(short_lines),
        "short_lines_nothing": len(nothing),
        "share_short_nothing": _rate(len(nothing), len(short_lines)),
        "customers": int(lines["Customer"].nunique()),
        "customers_short": int(short_lines["Customer"].nunique()),
    }


def document(
    t: dict[str, pd.DataFrame],
    f: dict[str, Any],
    data_check_table: pd.DataFrame,
    title: str,
    period: str,
    subtitle: str,
) -> ReportDocument:
    money: ValueFormat = "money"
    formats: dict[str, ValueFormat] = {
        "Order Lines": "integer",
        "Ordered Qty": "integer",
        "Delivered Qty": "integer",
        "Not Delivered Qty": "integer",
        "Delivered Qty %": "percent",
        "Ordered Value": "money",
        "Delivered Value": "money",
        "Value Not Delivered": "money",
        "Delivered Value %": "percent",
        "Line DIF %": "percent",
        "Lines Nothing Delivered %": "percent",
        "RM Value Not Delivered": "money",
        "Donor Units Not Delivered": "integer",
        "% Short": "percent",
        "Lines Short": "integer",
        "% Lines Short": "percent",
        "Customers Affected": "integer",
        "Months Affected": "integer",
        "Orders": "integer",
        "Orders DIF %": "percent",
        "Orders With a Nil-Delivery Line %": "percent",
        "Value": "number",
    }
    wbs = t["v3_by_wbs"]
    month = t["v3_by_month"]
    quarter = t["v3_by_quarter"]
    plants = t["v3_by_plant"]
    rm_items = t["v3_top_rm_items"]
    donor_items = t["v3_top_donor_items"]
    frequent = t["v3_frequently_short"]
    over_time = t["v3_items_over_time"]
    dif = t["v3_dif_by_type"]
    customers = t["v3_top_customers"]

    kpis = [
        KpiCard(
            "Delivered qty of ordered",
            pct(f["all_Delivered Qty %"]),
            f"{f['all_Delivered Qty']:,.0f} of {f['all_Ordered Qty']:,.0f} units",
        ),
        KpiCard(
            "Delivered value of ordered",
            pct(f["all_Delivered Value %"]),
            f"{rwf(f['all_Delivered Value'])} of {rwf(f['all_Ordered Value'])}",
        ),
        KpiCard(
            "Revenue not captured — RM",
            rwf(f["rm_value_not_delivered"]),
            f"{pct(f['rm_share_not_delivered'])} of RM ordered value",
            "red",
        ),
        KpiCard(
            "Donor demand not delivered",
            units(f["donor_units_not_delivered"]),
            f"{pct(f['donor_share_not_delivered'])} of donor units ordered",
            "yellow",
        ),
        KpiCard(
            "Lines Delivered-In-Full",
            pct(_rate(f["lines_in_full"], f["lines"])),
            f"{f['lines_in_full']:,} of {f['lines']:,} lines",
            "green",
        ),
        KpiCard(
            "Orders Delivered-In-Full",
            pct(_rate(f["orders_in_full"], f["orders"])),
            f"{f['orders_in_full']:,} orders",
            "green",
        ),
    ]
    weakest = (
        plants[plants["Ordered Value"] >= 0.01 * f["all_Ordered Value"]]
        .sort_values(["Delivered Value %", "Plant"], kind="mergesort")
        .head(3)
        if len(plants)
        else plants
    )
    weakest_text = ", ".join(
        f"{p} ({pct(v)})"
        for p, v in zip(weakest.get("Plant", []), weakest.get("Delivered Value %", []), strict=True)
    )
    highlights = [
        Highlight(
            "1 · Stock availability drives the loss",
            f"{pct(f['share_short_nothing'])} of the lines delivered short received nothing at all: "
            "the problem is items not available, not partial shipments. "
            f"RM (ZRMS + ZSPO) did not capture {rwf(f['rm_value_not_delivered'])} of sales "
            f"revenue; {f['customers_short']:,} of {f['customers']:,} customers were affected.",
            "red",
        ),
        Highlight(
            "2 · Donor demand is under-forecast",
            f"Donor (ZDON) orders delivered {pct(f['donor_qty_pct'])} of units against "
            f"{pct(f['rm_qty_pct'])} for RM: {units(f['donor_units_not_delivered'])} were ordered "
            "and not delivered. Donor orders carry no price, so the shortfall is in units.",
            "yellow",
        ),
        Highlight(
            "3 · The shortfall is concentrated",
            (
                f"Lowest delivered value among the main plants: {weakest_text}. "
                if weakest_text
                else ""
            )
            + (
                f"The top items by revenue not captured: {', '.join(rm_items['Item'].head(3))}."
                if len(rm_items)
                else ""
            ),
            "grey",
        ),
    ]
    how_to_read = [
        Highlight(
            "1 · Ordered vs delivered quantity",
            "Delivered qty % = delivered units ÷ ordered units. Not delivered qty = ordered − delivered. Delivered is never counted above ordered.",
            "grey",
        ),
        Highlight(
            "2 · Ordered vs delivered value",
            "Delivered value % = delivered value ÷ ordered value. Value not delivered = revenue RMS did not capture.",
            "grey",
        ),
        Highlight(
            "3 · Delivered-In-Full (DIF)",
            "A line is DIF when delivered ≥ ordered. An order is DIF only when every one of its lines is.",
            "grey",
        ),
        Highlight(
            "4 · WBS element",
            f"ZRMS and ZSPO → {WBS_OWN}: RMS own sales, value not delivered is lost revenue. ZDON → {WBS_PROGRAMME}: donor programme, measured in units.",
            "yellow",
        ),
    ]
    sections = [
        Section(
            "How to read the figures",
            message="Four measures, each answering a different management question",
            highlights=how_to_read,
        ),
        Section(
            "A · Loss per WBS element",
            message="RM = RMS losing sales revenue · Donor = forecasting gap",
            charts=[
                ChartBlock(
                    "Delivered % by WBS element",
                    [str(w) for w in wbs["WBS"]],
                    {
                        "Delivered qty %": [float(v or 0) for v in wbs["Delivered Qty %"]],
                        "Delivered value %": [float(v or 0) for v in wbs["Delivered Value %"]],
                        "Line DIF %": [float(v or 0) for v in wbs["Line DIF %"]],
                    },
                    "column",
                    "percent",
                )
            ]
            if len(wbs)
            else [],
            tables=[
                TableBlock(
                    "By WBS element",
                    wbs[
                        [
                            "WBS",
                            "Order Lines",
                            "Ordered Qty",
                            "Delivered Qty",
                            "Not Delivered Qty",
                            "Ordered Value",
                            "Value Not Delivered",
                            "Lines Nothing Delivered %",
                        ]
                    ],
                    formats,
                )
            ]
            if len(wbs)
            else [],
            takeaway=f"RM: every undelivered RWF is revenue RMS could have booked — {rwf(f['rm_value_not_delivered'])} ({pct(f['rm_share_not_delivered'])} of ordered value). Donor: {pct(f['donor_share_not_delivered'])} of requested units were not delivered — the programme forecast does not match what donors then order.",
        ),
    ]
    if len(month):
        peak = month.sort_values(
            ["RM Value Not Delivered", "Month"], ascending=[False, True], kind="mergesort"
        ).iloc[0]
        weakest_month = month.sort_values(["Delivered Value %", "Month"], kind="mergesort").iloc[0]
        sections.append(
            Section(
                "B · Order fill rate over time",
                message=f"The weakest value month was {weakest_month['Month']} ({pct(weakest_month['Delivered Value %'])}); RM revenue not captured peaked in {peak['Month']} ({rwf(peak['RM Value Not Delivered'])})",
                charts=[
                    ChartBlock(
                        "Value not delivered — RM (RWF)",
                        [str(m) for m in month["Month"]],
                        {
                            "RM value not delivered": [
                                float(v) for v in month["RM Value Not Delivered"]
                            ]
                        },
                        "column",
                        money,
                    ),
                    ChartBlock(
                        "Delivered % of ordered, by month",
                        [str(m) for m in month["Month"]],
                        {
                            "Delivered value %": [
                                float(v or 0) for v in month["Delivered Value %"]
                            ],
                            "Delivered qty %": [float(v or 0) for v in month["Delivered Qty %"]],
                        },
                        "line",
                        "percent",
                    ),
                ],
                takeaway=f"Delivered value ranged from {pct(float(month['Delivered Value %'].min()))} to {pct(float(month['Delivered Value %'].max()))} a month; RM revenue not captured ran at {rwf(float(month['RM Value Not Delivered'].min()))}–{rwf(float(month['RM Value Not Delivered'].max()))} a month.",
            )
        )
        sections.append(
            Section(
                "Ordered value vs delivered value",
                message="Monthly ordered and delivered value (RWF)",
                charts=[
                    ChartBlock(
                        "Ordered vs delivered value (RWF)",
                        [str(m) for m in month["Month"]],
                        {
                            "Ordered value": [float(v) for v in month["Ordered Value"]],
                            "Delivered value": [float(v) for v in month["Delivered Value"]],
                        },
                        "column",
                        money,
                    )
                ],
                kpis=[
                    KpiCard("Ordered", rwf(f["all_Ordered Value"]), f"{len(month)} months"),
                    KpiCard(
                        "Delivered",
                        rwf(f["all_Delivered Value"]),
                        f"{pct(f['all_Delivered Value %'])} of ordered",
                        "green",
                    ),
                    KpiCard(
                        "Not delivered",
                        rwf(f["all_Value Not Delivered"]),
                        f"RM {rwf(f['rm_value_not_delivered'])}",
                        "red",
                    ),
                ],
            )
        )
    if len(quarter):
        lowest_q = quarter.sort_values(["Delivered Value %", "Quarter"], kind="mergesort").iloc[0]
        sections.append(
            Section(
                "Order fill rate per quarter",
                message="Fiscal quarters: Q1 Jul–Sep · Q2 Oct–Dec · Q3 Jan–Mar · Q4 Apr–Jun",
                charts=[
                    ChartBlock(
                        "Delivered % of ordered, by quarter",
                        [str(q) for q in quarter["Quarter"]],
                        {
                            "Delivered value %": [
                                float(v or 0) for v in quarter["Delivered Value %"]
                            ],
                            "Delivered qty %": [float(v or 0) for v in quarter["Delivered Qty %"]],
                        },
                        "column",
                        "percent",
                    )
                ],
                tables=[
                    TableBlock(
                        "By quarter",
                        quarter[
                            [
                                "Quarter",
                                "Order Lines",
                                "Ordered Value",
                                "Delivered Value %",
                                "Delivered Qty %",
                                "Line DIF %",
                                "RM Value Not Delivered",
                                "Donor Units Not Delivered",
                            ]
                        ],
                        formats,
                    )
                ],
                takeaway=f"{lowest_q['Quarter']} had the lowest delivered value rate ({pct(lowest_q['Delivered Value %'])}).",
            )
        )
        sections.append(
            Section(
                "What drove each quarter",
                message="Largest RM items by value not delivered, largest donor items by units, and weakest plants",
                highlights=[
                    Highlight(
                        str(r["Quarter"]),
                        "\n".join(
                            line
                            for line in (
                                f"RM — value not delivered: {r['Main RM Items Short']}"
                                if r["Main RM Items Short"]
                                else "",
                                f"Donor — units not delivered: {r['Main Donor Items Short']}"
                                if r["Main Donor Items Short"]
                                else "",
                                f"Weakest plants (value %): {r['Weakest Plants']}"
                                if r["Weakest Plants"]
                                else "",
                            )
                            if line
                        )
                        or "Every line delivered in full.",
                        "blue",
                    )
                    for _, r in quarter.iterrows()
                ],
            )
        )
    if len(plants):
        top_plants = plants.head(12)
        sections.append(
            Section(
                "Order fill rate per plant / shipping point",
                message=f"Value not delivered by plant — {len(plants)} plants with data; the largest are shown",
                charts=[
                    ChartBlock(
                        "Value not delivered by plant (RWF)",
                        [str(p) for p in top_plants["Plant"]],
                        {
                            "Value not delivered": [
                                float(v) for v in top_plants["Value Not Delivered"]
                            ]
                        },
                        "bar",
                        money,
                    )
                ],
                tables=[
                    TableBlock(
                        "Plants (by value not delivered)",
                        top_plants[
                            [
                                "Plant",
                                "Ordered Value",
                                "Value Not Delivered",
                                "Delivered Qty %",
                                "Delivered Value %",
                                "Line DIF %",
                            ]
                        ],
                        formats,
                    )
                ],
                takeaway=(
                    f"Lowest delivered value among the main plants: {weakest_text}."
                    if weakest_text
                    else "All plants delivered close to their orders."
                ),
            )
        )
    if len(rm_items):
        sections.append(
            Section(
                "Items customers requested that were not delivered — RM",
                message="Revenue not captured (ZRMS + ZSPO): top 10 by value not delivered",
                charts=[
                    ChartBlock(
                        "Top 10 by value not delivered (RWF)",
                        [str(i) for i in rm_items["Item"]],
                        {
                            "Value not delivered": [
                                float(v) for v in rm_items["Value Not Delivered"]
                            ]
                        },
                        "bar",
                        money,
                    )
                ],
                tables=[TableBlock("Top RM items", rm_items, formats)],
                takeaway=f"The top 10 RM items account for {rwf(float(rm_items['Value Not Delivered'].sum()))} of the {rwf(f['rm_value_not_delivered'])} not captured.",
            )
        )
    if len(donor_items):
        sections.append(
            Section(
                "Items requested that were not delivered — Donor",
                message="Donor forecasting gap (ZDON): top 10 by units not delivered",
                charts=[
                    ChartBlock(
                        "Top 10 by units not delivered",
                        [str(i) for i in donor_items["Item"]],
                        {
                            "Units not delivered": [
                                float(v) for v in donor_items["Not Delivered Qty"]
                            ]
                        },
                        "bar",
                        "integer",
                    )
                ],
                tables=[
                    TableBlock(
                        "Top donor items",
                        donor_items[
                            ["Item", "Ordered Qty", "Not Delivered Qty", "% Short", "Lines Short"]
                        ],
                        formats,
                    )
                ],
                takeaway="Donor orders carry no price, so shortfalls are shown in units: share these items with the programme and donor planners to reset the forecasts for the next order cycle.",
            )
        )
    if len(frequent):
        sections.append(
            Section(
                "Most frequently requested — and most often short",
                message="Items customers order again and again that RMS did not fully deliver",
                tables=[TableBlock("Frequently short items", frequent, formats)],
                takeaway=f"These everyday items were short on many order lines and reached up to {int(frequent['Customers Affected'].max()):,} customers each: value per line is small, but they erode service and drive repeat orders — the safety-stock candidates.",
            )
        )
    if len(over_time.columns) > 1:
        items = [c for c in over_time.columns if c != "Month"]
        sections.append(
            Section(
                "Most-missing products over time",
                message=f"Value not delivered by month for the {len(items)} items with the largest total shortfall (RWF)",
                charts=[
                    ChartBlock(
                        "Value not delivered (RWF)",
                        [str(m) for m in over_time["Month"]],
                        {i: [float(v) for v in over_time[i]] for i in items},
                        "stacked",
                        money,
                    )
                ],
                takeaway="Shortages come in episodes rather than a steady drain: each bar shows which items were missing in which month.",
            )
        )
    if len(dif):
        sections.append(
            Section(
                "Delivered In Full — per order, per item",
                message="An order is Delivered-In-Full only if every line is delivered in full",
                charts=[
                    ChartBlock(
                        "Orders by order type (%)",
                        [str(k) for k in dif["Order Type"]],
                        {
                            "Orders Delivered-In-Full %": [
                                float(v or 0) for v in dif["Orders DIF %"]
                            ],
                            "Orders with a nil-delivery line %": [
                                float(v or 0) for v in dif["Orders With a Nil-Delivery Line %"]
                            ],
                        },
                        "column",
                        "percent",
                    )
                ],
                tables=[TableBlock("Lowest-DIF items", t["v3_lowest_dif_items"], formats)]
                if len(t["v3_lowest_dif_items"])
                else [],
                takeaway=f"{pct(1 - (_rate(f['orders_in_full'], f['orders']) or 0))} of orders are not delivered in full; the lowest-DIF items are repeat shortfalls on customers' orders.",
            )
        )
    if len(customers):
        sections.append(
            Section(
                "Per customer — who is most affected",
                message="Top 10 customers by value not delivered",
                tables=[
                    TableBlock(
                        "Top customers",
                        customers[
                            [
                                "Customer",
                                "Ordered Value",
                                "Value Not Delivered",
                                "Delivered Value %",
                                "Line DIF %",
                                "Orders",
                                "Orders DIF %",
                            ]
                        ],
                        formats,
                    )
                ],
                takeaway=f"{customers.iloc[0]['Customer']} lost the most value ({rwf(float(customers.iloc[0]['Value Not Delivered']))}, {pct(customers.iloc[0]['Delivered Value %'])} delivered).",
            )
        )

    recommendations = []
    if len(frequent):
        recommendations.append(
            Recommendation(
                f"Hold safety stock for the repeat-short items ({', '.join(frequent['Item'].head(3))}) at the plants serving them",
                "Procurement & Warehouse Managers",
                "30 days",
            )
        )
    if len(donor_items):
        recommendations.append(
            Recommendation(
                f"Reset donor (ZDON) forecasts for the top short items ({', '.join(donor_items['Item'].head(3))}) with programme / donor planners",
                "Programmes / Forecasting",
                "Next order cycle",
            )
        )
    if weakest_text:
        recommendations.append(
            Recommendation(
                f"Supply review for the plants with the lowest delivered value ({weakest_text})",
                "Distribution Manager",
                "45 days",
            )
        )
    if len(rm_items):
        recommendations.append(
            Recommendation(
                f"Confirm the large requests behind the biggest RM losses ({', '.join(rm_items['Item'].head(3))}): fulfil, re-plan or cancel",
                "Sales Ops / Procurement",
                "30 days",
            )
        )
    if len(customers):
        recommendations.append(
            Recommendation(
                f"Follow up the customers with the largest undelivered value ({', '.join(customers['Customer'].head(3))})",
                "Sales Ops",
                "30 days",
            )
        )
    recommendations.append(
        Recommendation(
            "Run this report monthly and track delivered qty %, delivered value %, Order DIF and RM revenue not captured",
            "Inventory & Warehouse Mgmt",
            "Monthly",
        )
    )

    checks_text = "; ".join(
        f"{r['Check']}: {r['Value']:,.0f}" + (f" ({r['Note']})" if r["Note"] else "")
        for _, r in data_check_table.iterrows()
    )
    notes = [
        Highlight("Coverage", checks_text),
        Highlight(
            "Delivered quantity and value",
            "Delivered quantity comes from the goods-issued outbound deliveries of each order line and is never counted above the ordered quantity; delivered value = ordered value × delivered ÷ ordered.",
        ),
        Highlight(
            "Donor orders",
            "ZDON (donor) orders carry no price, so donor shortfalls are measured in units; no value is estimated.",
        ),
        Highlight(
            "Plants",
            "Plant / shipping point named from OX10; only plants with data are listed; lines with an unassigned plant are outside the analysis and counted in the data checks.",
        ),
    ]
    return ReportDocument(
        title=title,
        subtitle=subtitle,
        date_text=period,
        sections=sections,
        summary_message=(
            f"RMS delivered {pct(f['all_Delivered Qty %'])} of the units and {pct(f['all_Delivered Value %'])} "
            "of the value ordered; the gap sits in specific items, plants, customers and the donor programme"
        ),
        kpis=kpis,
        highlights=highlights,
        recommendations=recommendations,
        notes=notes,
        audience="Senior Management Team · Inventory & Warehouse Management",
        draft=True,
    )


def calc_quarters(
    line_columns: list[str], by_quarter_table: pd.DataFrame, sheet: str
) -> pd.DataFrame:
    """A workings sheet with live formulas over the order lines sheet (v3 Calc_* tabs).

    Each figure is a SUMIFS / COUNTIFS on the "Order lines" sheet, so it can be
    audited and recalculated in Excel; the last columns repeat the value computed
    here and the difference, which must be zero.
    """
    from openpyxl.utils import get_column_letter

    def col(name: str) -> str:
        letter = get_column_letter(line_columns.index(name) + 1)
        return f"'{sheet}'!${letter}:${letter}"

    first_row = 5  # the workbook's tables start on row 4 (header), data from row 5
    rows = []
    for i, quarter in enumerate(by_quarter_table["Quarter"]):
        r = first_row + i
        key = f"{col('Quarter')},$A{r}"
        rows.append(
            {
                "Quarter": quarter,
                "Ordered Qty": f"=SUMIFS({col('Ordered Qty')},{key})",
                "Delivered Qty": f"=SUMIFS({col('Filled Qty')},{key})",
                "Delivered Qty %": f"=IF(B{r}=0,0,C{r}/B{r})",
                "Ordered Value": f"=SUMIFS({col('Ordered Value')},{key})",
                "Delivered Value": f"=SUMIFS({col('Delivered Value')},{key})",
                "Delivered Value %": f"=IF(E{r}=0,0,F{r}/E{r})",
                "Order Lines": f"=COUNTIFS({key})",
                "Lines In Full": f'=COUNTIFS({key},{col("Status")},"{IN_FULL}")',
                "Line DIF %": f"=IF(H{r}=0,0,I{r}/H{r})",
                "Delivered Value (check)": float(
                    by_quarter_table.loc[
                        by_quarter_table["Quarter"] == quarter, "Delivered Value"
                    ].sum()
                ),
                "Difference": f"=F{r}-K{r}",
            }
        )
    return pd.DataFrame(rows)


README = [
    "This workbook holds the order fill rate of the period with its workings.",
    "Summary: the key figures. Data checks: rows read, rows left out and why, months present.",
    "Source check: VA05 rows per quarter, left out by reason, analysed.",
    "Value reconciliation: ordered value recomputed as quantity x net price against VA05.",
    "Calc quarters: live SUMIFS / COUNTIFS formulas on the Order lines sheet; Difference must be 0.",
    "WBS loss, By month, By quarter, Plants, Top RM items, Top donor items, Frequently short,",
    "Items over time, DIF by order type, Top customers: the analyses of the SMT report.",
    "Order lines: one row per sales order item, with its delivered quantity and status.",
    "Shortfalls are positive numbers. Donor (ZDON) orders carry no price: their shortfall is in units.",
]
