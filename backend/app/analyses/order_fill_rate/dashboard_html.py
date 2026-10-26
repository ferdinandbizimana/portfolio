"""Interactive dashboard of the order fill rate (layout of Ferdinand's own
"RMS Order Fill Rate Dashboard FY2025/26", with a regional section added)."""

import pandas as pd

from app.analyses.common.periods import QUARTERS
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

IN_FULL, PARTLY, NOT_DELIVERED = "Delivered in full", "Partly delivered", "Not delivered"
WBS_OWN, WBS_PROGRAMME = "RMS-OWN-ESE-RM", "RMS-PRG-FND-CP"
ORDER_IN_FULL = "Delivered in full"
ORDER_NIL = "Short, with a line not delivered at all"
ORDER_SHORT = "Short, every line partly delivered"

LINE_MEASURES = (
    Measure("lines", "Order lines", count=True),
    Measure("dif_lines", "Lines delivered in full", count=True, where=("Status", (IN_FULL,))),
    Measure(
        "short_lines",
        "Order lines short",
        count=True,
        where=("Status", (PARTLY, NOT_DELIVERED)),
    ),
    Measure("oq", "Ordered qty", sum="Ordered Qty"),
    Measure("cq", "Delivered qty", sum="Delivered Qty"),
    Measure("V", "Ordered value (RWF)", "rwf", sum="Ordered Value"),
    Measure("Vc", "Delivered value (RWF)", "rwf", sum="Delivered Value"),
    Measure("unserved_value", "Value not delivered (RWF)", "rwf", diff=("V", "Vc")),
    Measure("unserved_qty", "Qty not delivered", diff=("oq", "cq")),
    Measure("qty_pct", "Delivered qty %", "pct", ratio=("cq", "oq")),
    Measure("value_pct", "Delivered value %", "pct", ratio=("Vc", "V")),
    Measure("dif_pct", "Line Delivered-In-Full %", "pct", ratio=("dif_lines", "lines")),
    Measure("short_pct", "% short (qty)", "pct", ratio=("unserved_qty", "oq")),
    Measure(
        "V_rm", "Ordered value RM (RWF)", "rwf", sum="Ordered Value", where=("WBS", (WBS_OWN,))
    ),
    Measure(
        "Vc_rm", "Delivered value RM (RWF)", "rwf", sum="Delivered Value", where=("WBS", (WBS_OWN,))
    ),
    Measure("unserved_rm", "RM value not delivered (RWF)", "rwf", diff=("V_rm", "Vc_rm")),
    Measure("oq_don", "Donor units ordered", sum="Ordered Qty", where=("WBS", (WBS_PROGRAMME,))),
    Measure(
        "cq_don", "Donor units delivered", sum="Delivered Qty", where=("WBS", (WBS_PROGRAMME,))
    ),
    Measure("unserved_don", "Donor units not delivered", diff=("oq_don", "cq_don")),
    Measure(
        "unserved_don_pct", "Donor units not delivered %", "pct", ratio=("unserved_don", "oq_don")
    ),
)
ORDER_MEASURES = (
    Measure("orders", "Orders", count=True),
    Measure("orders_dif", "Orders in full", count=True, where=("Outcome", (ORDER_IN_FULL,))),
    Measure("orders_nil", "Orders with a nil line", count=True, where=("Outcome", (ORDER_NIL,))),
    Measure("order_lines", "Order lines", sum="Lines"),
    Measure("order_dif_lines", "Lines in full", sum="Lines In Full"),
    Measure("V", "Ordered (RWF)", "rwf", sum="Ordered Value"),
    Measure("Vc", "Delivered (RWF)", "rwf", sum="Delivered Value"),
    Measure("unserved_value", "Not delivered (RWF)", "rwf", diff=("V", "Vc")),
    Measure("orders_dif_pct", "Orders Delivered-In-Full %", "pct", ratio=("orders_dif", "orders")),
    Measure(
        "orders_nil_pct", "Orders with a nil-delivery line %", "pct", ratio=("orders_nil", "orders")
    ),
    Measure("value_pct", "Delivered value %", "pct", ratio=("Vc", "V")),
    Measure("line_dif_pct", "Line DIF %", "pct", ratio=("order_dif_lines", "order_lines")),
)
SHARED = (
    "Quarter",
    "Month",
    "Plant",
    "WBS",
    "Order type",
    "Customer",
    "Region",
    "District",
    "Border district",
    "Facility type",
)


def facts(lines: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """One row per order line and one per order (from the "lines" table)."""
    customer = [
        f"{n} [{c}]" if n else c
        for n, c in zip(lines["Customer Name"], lines["Customer"], strict=True)
    ]
    line_facts = pd.DataFrame(
        {
            "Quarter": lines["Quarter"],
            "Month": lines["Month"],
            "Plant": lines["Shipping Plant"],
            "WBS": lines["WBS"],
            "Order type": lines["Sales Type"].replace("", "Not given"),
            "Customer": customer,
            "Item": lines["Item Name"],
            "Region": lines["Region"],
            "District": lines["District"],
            "Border district": lines["Border District"].map({True: "Yes", False: "No"}),
            "Facility type": lines["Facility Type"],
            "Status": lines["Status"],
            "Sales order": lines["Sales Document"],
            "Line": lines["Item"],
            "Order date": lines["Order Date"],
            "Ordered Qty": lines["Ordered Qty"].astype(float),
            "Delivered Qty": lines["Filled Qty"].astype(float),
            "Ordered Value": lines["Ordered Value"].astype(float),
            "Delivered Value": lines["Delivered Value"].astype(float),
        }
    ).reset_index(drop=True)
    line_facts["Not delivered value"] = line_facts["Ordered Value"] - line_facts["Delivered Value"]
    grouped = line_facts.groupby("Sales order", sort=True)
    first = grouped[list(SHARED)].first()
    statuses = grouped["Status"].agg(list)
    order_facts = first.copy()
    order_facts["Lines"] = grouped.size()
    order_facts["Lines In Full"] = grouped["Status"].agg(lambda s: int((s == IN_FULL).sum()))
    order_facts["Ordered Value"] = grouped["Ordered Value"].sum()
    order_facts["Delivered Value"] = grouped["Delivered Value"].sum()
    order_facts["Outcome"] = [
        ORDER_IN_FULL
        if all(s == IN_FULL for s in group)
        else ORDER_NIL
        if NOT_DELIVERED in group
        else ORDER_SHORT
        for group in statuses
    ]
    order_facts = order_facts.reset_index()
    return {"lines": line_facts, "orders": order_facts}


def build(
    lines: pd.DataFrame,
    title: str,
    subtitle: str,
    checks: list[tuple[str, float, float, bool]],
) -> InteractiveDashboard:
    month_free = ("Month", "Quarter")
    rate_cols = ("qty_pct", "value_pct", "dif_pct")
    return InteractiveDashboard(
        title=title,
        subtitle=subtitle,
        intro=(
            "Ordered against delivered quantity and value, Delivered-In-Full by line and by "
            "order, and the sales revenue lost on items that were not available: by WBS, "
            "plant, customer, item, month and region. Every filter applies to every section "
            "unless a section says otherwise."
        ),
        facts=facts(lines),
        measures={"lines": LINE_MEASURES, "orders": ORDER_MEASURES},
        filters=(
            Filter("Quarter", "Quarter", "All quarters", order="given", values=QUARTERS),
            Filter("Month", "Month", "All months"),
            Filter("Plant", "Plant / shipping point", "All plants"),
            Filter("WBS", "WBS element", "All WBS"),
            Filter("Order type", "Order type", "All order types"),
            Filter("Customer", "Customer", "All customers"),
            Filter("Item", "Item (material)", "All items"),
            Filter("Region", "Region", "All regions"),
            Filter("District", "District", "All districts"),
            Filter("Border district", "Border district", "Border and inland"),
            Filter("Facility type", "Facility type", "All facility types"),
        ),
        kpis=(
            KpiTile("Delivered qty % of ordered", "qty_pct", "lines", "{cq} of {oq} units"),
            KpiTile("Delivered value % of ordered", "value_pct", "lines", "{Vc} of {V}"),
            KpiTile(
                "Revenue not captured (RM WBS)",
                "unserved_rm",
                "lines",
                "ZRMS + ZSPO ordered but not delivered",
                tone="red",
            ),
            KpiTile(
                "Donor demand not delivered (units)",
                "unserved_don",
                "lines",
                "ZDON · {unserved_don_pct} of donor units ordered",
                tone="amber",
            ),
            KpiTile(
                "Line Delivered-In-Full",
                "dif_pct",
                "lines",
                "{dif_lines} of {lines} lines",
                "green",
            ),
            KpiTile(
                "Order Delivered-In-Full",
                "orders_dif_pct",
                "orders",
                "{orders_dif} of {orders} orders",
                "green",
            ),
        ),
        sections=(
            DashSection(
                "A · Loss per WBS element",
                note=(
                    f"{WBS_OWN} (order types ZRMS and ZSPO) is RMS's own sales: every RWF ordered "
                    f"but not delivered is sales revenue RMS did not capture. {WBS_PROGRAMME} "
                    "(ZDON donor orders) carries no net price, so donor shortfalls are shown in "
                    "units and point to a donor forecasting gap."
                ),
                blocks=(
                    ChartSpec(
                        "Delivery rates by WBS",
                        "lines",
                        "WBS",
                        rate_cols,
                        note="Delivered qty %, delivered value % and Delivered-In-Full lines",
                        ignore=("WBS",),
                        percent=True,
                    ),
                    TableSpec(
                        "Order fill rate by WBS",
                        "lines",
                        ("WBS",),
                        ("oq", "cq", "unserved_qty", "V", "Vc", "unserved_value"),
                        ignore=("WBS",),
                    ),
                ),
            ),
            DashSection(
                "B · Order fill rate over time",
                note="Monthly trend (ignores the Month and Quarter filters).",
                blocks=(
                    ChartSpec(
                        "Value not delivered and delivered value %",
                        "lines",
                        "Month",
                        ("unserved_value", "value_pct"),
                        kind="combo",
                        note="Bars: value not delivered (left). Line: delivered value % (right).",
                        ignore=month_free,
                    ),
                    ChartSpec(
                        "Delivered against ordered: value, quantity and lines",
                        "lines",
                        "Month",
                        ("value_pct", "qty_pct", "dif_pct"),
                        kind="line",
                        ignore=month_free,
                        percent=True,
                    ),
                ),
            ),
            DashSection(
                "B2 · Order fill rate per quarter",
                note="Financial quarters, July to June (ignores the Month and Quarter filters).",
                blocks=(
                    ChartSpec(
                        "Delivery rates by quarter",
                        "lines",
                        "Quarter",
                        rate_cols,
                        ignore=month_free,
                        percent=True,
                    ),
                    TableSpec(
                        "Delivery rates by quarter",
                        "lines",
                        ("Quarter",),
                        (
                            "oq",
                            "cq",
                            "qty_pct",
                            "V",
                            "Vc",
                            "value_pct",
                            "unserved_rm",
                            "unserved_don",
                            "dif_pct",
                        ),
                        ignore=month_free,
                        sort_by=None,
                    ),
                ),
            ),
            DashSection(
                "C · Order fill rate per plant / shipping point",
                note="Plant names from OX10. Red below 85%, amber below 95%.",
                blocks=(
                    ChartSpec(
                        "Delivered value % by plant (worst first)",
                        "lines",
                        "Plant",
                        ("value_pct",),
                        kind="hbar",
                        ignore=("Plant",),
                        sort="asc",
                        sort_by="value_pct",
                        percent=True,
                        traffic=(0.85, 0.95),
                    ),
                    TableSpec(
                        "Plants by value not delivered",
                        "lines",
                        ("Plant",),
                        ("lines", "V", "unserved_value", "qty_pct", "value_pct", "dif_pct"),
                        ignore=("Plant",),
                        sort_by="unserved_value",
                        bars=("qty_pct", "value_pct"),
                        labels={"Plant": "Plant / shipping point"},
                    ),
                ),
            ),
            DashSection(
                "D · Items most requested and not in stock",
                rank_choices=("unserved_value", "unserved_qty", "short_lines", "oq"),
                blocks=(
                    ChartSpec(
                        "Top 15 items",
                        "lines",
                        "Item",
                        ("rank",),
                        kind="hbar",
                        sort="desc",
                        sort_by="rank",
                        limit=15,
                    ),
                    TableSpec(
                        "Top 40 items",
                        "lines",
                        ("Item", "WBS"),
                        ("oq", "unserved_qty", "short_pct", "short_lines", "unserved_value"),
                        sort_by="rank",
                        limit=40,
                    ),
                ),
            ),
            DashSection(
                "E · Most-missing products over time",
                note="Top 8 items under the current filters (ignores the Month filter).",
                blocks=(
                    ChartSpec(
                        "Value not delivered by month: top 8 items",
                        "lines",
                        "Month",
                        ("unserved_value",),
                        kind="stacked",
                        stack="Item",
                        sort_by="unserved_value",
                        ignore=("Month",),
                    ),
                ),
            ),
            DashSection(
                "F · Delivered In Full: per order, per customer",
                note=(
                    "An order is Delivered-In-Full only if every line is delivered in full. Order "
                    "figures cannot follow the Item filter (one order holds many items)."
                ),
                blocks=(
                    ChartSpec(
                        "Order outcomes by order type",
                        "orders",
                        "Order type",
                        ("orders_dif_pct", "orders_nil_pct"),
                        ignore=("Order type",),
                        percent=True,
                    ),
                    TableSpec(
                        "Customers with the highest value not delivered (top 15)",
                        "orders",
                        ("Customer",),
                        (
                            "orders",
                            "orders_dif_pct",
                            "V",
                            "unserved_value",
                            "value_pct",
                            "line_dif_pct",
                        ),
                        sort_by="unserved_value",
                        limit=15,
                        bars=("value_pct",),
                    ),
                ),
            ),
            DashSection(
                "G · Regional analysis",
                note=(
                    "Customers matched to OX10 by name: district from City, region from "
                    "Description, facility type from the abbreviation in the name. Border "
                    "districts are the run's parameter."
                ),
                blocks=(
                    ChartSpec(
                        "Delivered value % by region",
                        "lines",
                        "Region",
                        ("value_pct",),
                        kind="hbar",
                        ignore=("Region",),
                        sort="asc",
                        sort_by="value_pct",
                        percent=True,
                        traffic=(0.85, 0.95),
                    ),
                    ChartSpec(
                        "Border districts against inland",
                        "lines",
                        "Border district",
                        rate_cols,
                        ignore=("Border district",),
                        percent=True,
                    ),
                    TableSpec(
                        "By region",
                        "lines",
                        ("Region",),
                        ("lines", "V", "unserved_value", "qty_pct", "value_pct", "dif_pct"),
                        ignore=("Region",),
                        sort_by="unserved_value",
                        bars=("value_pct",),
                    ),
                    TableSpec(
                        "By district",
                        "lines",
                        ("District", "Border district"),
                        ("lines", "V", "unserved_value", "qty_pct", "value_pct", "dif_pct"),
                        sort_by="unserved_value",
                        bars=("value_pct",),
                    ),
                    TableSpec(
                        "By facility type",
                        "lines",
                        ("Facility type",),
                        ("lines", "V", "unserved_value", "qty_pct", "value_pct", "dif_pct"),
                        sort_by="unserved_value",
                        bars=("value_pct",),
                    ),
                    TableSpec(
                        "Border customers with the highest value not delivered",
                        "orders",
                        ("Customer", "District"),
                        ("orders", "orders_dif_pct", "V", "unserved_value", "value_pct"),
                        sort_by="unserved_value",
                        limit=25,
                        bars=("value_pct",),
                        note="Set the Border district filter to Yes to list border customers only.",
                    ),
                ),
            ),
            DashSection(
                "H · Order lines",
                note="Every order line under the current filters; download them as CSV.",
                blocks=(
                    DetailSpec(
                        "Order lines",
                        "lines",
                        (
                            ("Sales order", "Sales order", "text"),
                            ("Line", "Item", "text"),
                            ("Order date", "Order date", "text"),
                            ("Order type", "Type", "text"),
                            ("Customer", "Customer", "text"),
                            ("Item", "Material", "text"),
                            ("Plant", "Plant", "text"),
                            ("Ordered Qty", "Ordered", "int"),
                            ("Delivered Qty", "Delivered", "int"),
                            ("Ordered Value", "Ordered (RWF)", "rwf"),
                            ("Not delivered value", "Not delivered (RWF)", "rwf"),
                            ("Status", "Status", "text"),
                        ),
                        sort_by="Not delivered value",
                    ),
                ),
            ),
        ),
        footer=(
            "Rwanda Medical Supply · Order fill rate · VA05 sales orders against goods-issued "
            "outbound deliveries. Donor (ZDON) orders carry no net price, so donor shortfalls "
            "are shown in units."
        ),
        checks=checks,
    )
