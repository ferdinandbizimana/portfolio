"""Order fill rate: sales orders (VA05) against outbound deliveries.

Ferdinand's rule of 23 October 2026: "VA05 and List of Outbound deliveries and
OX10 To do Order fillrate". Definitions used (see docs/PLAN.md, Decisions):

- an order line is a VA05 sales document item; lines with an order quantity of
  zero or less are left out and counted;
- delivered quantity of a line = the "Actual delivery qty" (or, when blank, the
  "Delivery Quantity") of the outbound delivery items whose reference document
  and item are that sales document and item (when the reference item is blank:
  same sales document and material); by default only deliveries with a goods
  movement date (goods issued) count;
- filled quantity = the delivered quantity, at most the ordered quantity;
  delivered value = net value x filled / ordered;
- a line is delivered in full when its delivered quantity reaches the ordered
  quantity; an order when all its lines are;
- line fill rate = lines in full / lines; order fill rate = orders in full /
  orders; quantity and value fill rate = filled / ordered;
- the plant is the delivering plant of the outbound deliveries, named from
  OX10; days to goods issue = from the order date to the last goods issue of a
  line delivered in full.

Ferdinand's answers of 26 October 2026:

- goods-issued deliveries are the ones that count; VA05 also gives the
  confirmed quantity of each line (ordered - confirmed = not delivered), the net
  price (unit price) and the net value (line value);
- sales document types ZRMS and ZSPO are normal sales; ZDON are programme
  commodities sold at a 100% discount (zero value): their distribution value
  comes from MB51 (movement types 601, Y01, Z01, X01) by sales document;
- OX10 gives plant and customer names: "Name 1" is the facility name and
  shows its type (HP health post, CS / HC health centre, DH district hospital,
  RH referral hospital, PH provincial hospital ...), "City" its district and
  "Description" its region; customers are matched to OX10 by the names in the
  outbound delivery list. The fill rate is also shown by facility type, region,
  district and for the districts on the border of Rwanda.

Ferdinand's dashboard "RMS Order Fill Rate Dashboard FY2025/26" (26 October
2026) sets the interactive layout: WBS RMS-OWN-ESE-RM for order types ZRMS and
ZSPO (RMS's own sales: value not delivered is sales revenue not captured) and
RMS-PRG-FND-CP for ZDON (donor orders carry no price, so their shortfall is in
units); financial quarters (July to June); plant / shipping point; items most
requested and not delivered; Delivered-In-Full by order and customer. The
plant of a line is the VA05 plant when the export has it, otherwise the
delivering plant, otherwise the plant that most often delivers to the customer.
"""

import re
from datetime import date
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field, model_validator

from app.analyses.base import Analysis, AnalysisResult, Check, InputSpec
from app.analyses.common.closing import material_code, plant_code, plant_names
from app.analyses.common.periods import fiscal_quarter, fiscal_year
from app.analyses.dashboard import Chart, Column, Dashboard, Kpi, Series, Table, rows_of
from app.analyses.order_fill_rate import dashboard_html
from app.analyses.order_fill_rate.dashboard_html import (
    IN_FULL,
    NOT_DELIVERED,
    PARTLY,
    WBS_OWN,
    WBS_PROGRAMME,
)
from app.reporting.documents import (
    ChartBlock,
    ReportDocument,
    ReportFile,
    Section,
    TableBlock,
    Templates,
    ValueFormat,
    check_lines,
)
from app.reporting.excel import build_workbook
from app.reporting.interactive import build_html
from app.reporting.slides import build_pptx
from app.reporting.word import build_docx

PROGRAMME_TYPES = ("ZDON",)  # programme commodities, 100% discount
DISTRIBUTION_TYPES = ("601", "Y01", "Z01", "X01")  # MB51 goods issue to a customer
SALE, PROGRAMME = "Sale", "Programme commodities (ZDON)"
# Facility type from the abbreviation in the OX10 name (Ferdinand, 26 October 2026).
FACILITY_TYPES = {
    "HP": "Health post",
    "CS": "Health centre",
    "HC": "Health centre",
    "DH": "District hospital",
    "RH": "Referral hospital",
    "PH": "Provincial hospital",
}
OTHER_FACILITY, UNKNOWN = "Other", "Not found in OX10"
# Districts on the border of Rwanda (with the DRC, Uganda, Tanzania and Burundi);
# a parameter, to be confirmed by Ferdinand.
BORDER_DISTRICTS = (
    "Rubavu, Rutsiro, Karongi, Nyamasheke, Rusizi, Nyamagabe, Nyaruguru, Huye, Gisagara, "
    "Bugesera, Kirehe, Kayonza, Nyagatare, Gicumbi, Burera, Musanze"
)
STATUSES = [IN_FULL, PARTLY, NOT_DELIVERED]
NO_DELIVERY = "No delivery"


def _code(values: pd.Series) -> pd.Series:
    """Document and item numbers without leading zeros."""
    return material_code(values).astype(str)


def _rate(part: float, whole: float) -> float | None:
    return part / whole if whole else None


def _column(frame: pd.DataFrame, name: str) -> pd.Series:
    """An optional column, or empty values when the file does not have it."""
    return frame[name] if name in frame.columns else pd.Series(None, index=frame.index)


def _name(value: object) -> str:
    text = "" if value is None or (not isinstance(value, str) and pd.isna(value)) else str(value)  # type: ignore[call-overload]
    return " ".join(text.upper().split())


def facility_type(name: str) -> str:
    """Facility type from the abbreviation in its name ("CS KIGALI" -> Health centre)."""
    for word in re.split(r"[^A-Z0-9]+", name.upper()):
        if word in FACILITY_TYPES:
            return FACILITY_TYPES[word]
    return OTHER_FACILITY


def _districts(text: str) -> set[str]:
    return {_name(d) for d in text.split(",") if d.strip()}


class Parameters(BaseModel):
    period_start: date = Field(
        title="Orders from", description="First order date counted, e.g. 1 April 2026."
    )
    period_end: date = Field(
        title="Orders up to", description="Last order date counted, e.g. 30 June 2026."
    )
    goods_issued_only: bool = Field(
        default=True,
        title="Count only goods-issued deliveries",
        description="Leave out deliveries without a goods movement date.",
    )
    border_districts: str = Field(
        default=BORDER_DISTRICTS,
        title="Border districts",
        description="Districts on the border of Rwanda, comma-separated.",
    )

    @model_validator(mode="after")
    def _order(self) -> "Parameters":
        if self.period_end < self.period_start:
            raise ValueError("The last order date must not be before the first.")
        return self


def _params(params: BaseModel) -> Parameters:
    if not isinstance(params, Parameters):
        raise TypeError("Parameters of the wrong analysis.")
    return params


def delivered_by_line(deliveries: pd.DataFrame, goods_issued_only: bool) -> pd.DataFrame:
    """Outbound delivery items with normalised keys and the quantity that counts."""
    actual = deliveries["Actual delivery qty"].astype(float)
    quantity = actual.where(actual.notna(), deliveries["Delivery Quantity"].astype(float))
    issued = deliveries["Act. Gds Mvmnt Date"]
    obd = pd.DataFrame(
        {
            "Delivery": deliveries["Delivery"].astype("string").str.strip().fillna("").astype(str),
            "Sales Document": _code(deliveries["Reference Document"]),
            "Item": _code(deliveries["Reference Item"]),
            "Material": _code(deliveries["Material"]),
            "Plant": plant_code(deliveries["Plant"]).astype(str),
            "Delivered Qty": quantity.fillna(0.0),
            "Goods Issue": pd.to_datetime(issued),
            "Material Description": _column(deliveries, "Item Description")
            .astype("string")
            .str.strip()
            .fillna("")
            .astype(str),
            "Customer Name": deliveries["Sold-to Party Name"]
            .where(deliveries["Sold-to Party Name"].notna(), deliveries["Name ship-to party"])
            .astype("string")
            .fillna("")
            .astype(str),
        }
    )
    obd["Goods Issued"] = obd["Goods Issue"].notna()
    if goods_issued_only and deliveries["Act. Gds Mvmnt Date"].notna().any():
        obd = obd[obd["Goods Issued"]]
    return obd.reset_index(drop=True)


class OrderFillRate(Analysis):
    key = "order_fill_rate"
    title = "Order fill rate"
    version = "1.2.0"
    description = (
        "Sales orders (VA05) against outbound deliveries: lines and orders delivered in "
        "full, quantity and value fill rate, by delivering plant, customer and month, with "
        "the days from order to goods issue."
    )
    inputs = (
        InputSpec("orders", "va05_sales_orders", "Sales orders (VA05)"),
        InputSpec("deliveries", "outbound_deliveries", "Outbound deliveries (OBDs)"),
        InputSpec(
            "plants",
            "ox10_plants",
            "Plant and customer names, districts and regions (OX10)",
            required=False,
        ),
        InputSpec(
            "movements",
            "mb51_material_documents",
            "Goods movements (MB51), for the value of programme distributions",
            required=False,
        ),
    )
    Parameters = Parameters

    def compute(self, data: dict[str, pd.DataFrame], params: BaseModel) -> AnalysisResult:
        params = _params(params)
        raw = data["orders"]
        orders = pd.DataFrame(
            {
                "Sales Document": _code(raw["Sales Document"]),
                "Item": _code(raw["Sales Document Item"]),
                "Order Date": pd.to_datetime(raw["Document Date"]),
                "Customer": raw["Sold-to Party"]
                .astype("string")
                .str.strip()
                .fillna("")
                .astype(str),
                "Material": _code(raw["Material"]),
                "Ordered Qty": raw["Order Quantity (Item)"].astype(float).fillna(0.0),
                "Ordered Value": raw["Net Value (Item)"].astype(float).fillna(0.0),
                "Sales Type": _column(raw, "Sales Document Type").map(_name),
                "Confirmed Qty": _column(raw, "Confirmed Quantity").astype(float),
                "Net Price": _column(raw, "Net Price").astype(float),
                "Order Plant": plant_code(_column(raw, "Plant")).astype(str),
            }
        )
        start, end = pd.Timestamp(params.period_start), pd.Timestamp(params.period_end)
        in_period = orders["Order Date"].between(start, end)
        outside = int((~in_period).sum())
        orders = orders[in_period]
        zero = orders["Ordered Qty"] <= 0
        zero_lines = int(zero.sum())
        orders = orders[~zero]
        # Several VA05 rows for the same item (schedule lines) are one order line.
        orders = (
            orders.groupby(["Sales Document", "Item"], sort=True)
            .agg(
                **{
                    "Order Date": ("Order Date", "min"),
                    "Customer": ("Customer", "first"),
                    "Material": ("Material", "first"),
                    "Ordered Qty": ("Ordered Qty", "sum"),
                    "Ordered Value": ("Ordered Value", "sum"),
                    "Sales Type": ("Sales Type", "first"),
                    "Confirmed Qty": ("Confirmed Qty", lambda q: q.sum(min_count=1)),
                    "Net Price": ("Net Price", "first"),
                    "Order Plant": ("Order Plant", "first"),
                }
            )
            .reset_index()
        )

        obd = delivered_by_line(data["deliveries"], params.goods_issued_only)
        by_item = obd["Item"] != ""
        parts = [
            obd[by_item].merge(orders[["Sales Document", "Item"]], on=["Sales Document", "Item"]),
            obd[~by_item]
            .drop(columns="Item")
            .merge(
                orders[["Sales Document", "Item", "Material"]], on=["Sales Document", "Material"]
            )
            .drop_duplicates(["Delivery", "Sales Document", "Material", "Delivered Qty"]),
        ]
        # Empty parts are left out of the concatenation (pandas warns on empty dates).
        keyed = pd.concat([p for p in parts if len(p)] or parts[:1], ignore_index=True)
        unmatched = obd[
            ~obd["Sales Document"].isin(set(orders["Sales Document"]))
            | (
                by_item
                & ~obd.set_index(["Sales Document", "Item"]).index.isin(
                    orders.set_index(["Sales Document", "Item"]).index
                )
            )
        ]
        delivered = (
            keyed.groupby(["Sales Document", "Item"], sort=True)
            .agg(
                **{
                    "Delivered Qty": ("Delivered Qty", "sum"),
                    "Deliveries": ("Delivery", "nunique"),
                    "Plant": ("Plant", "min"),
                    "Last Goods Issue": ("Goods Issue", "max"),
                    "Customer Name": ("Customer Name", "max"),
                }
            )
            .reset_index()
        )
        lines = orders.merge(delivered, on=["Sales Document", "Item"], how="left")
        lines["Delivered Qty"] = lines["Delivered Qty"].fillna(0.0)
        lines["Deliveries"] = lines["Deliveries"].fillna(0).astype(int)
        lines["Plant"] = lines["Plant"].fillna(NO_DELIVERY)
        lines["Customer Name"] = lines["Customer Name"].fillna("")
        names = plant_names(data.get("plants"))
        lines["Plant Name"] = [names.get(p, "") for p in lines["Plant"]]
        # Plant / shipping point of every line, also of lines never delivered.
        usual = (
            lines[lines["Plant"] != NO_DELIVERY]
            .groupby(["Customer", "Plant"])
            .size()
            .reset_index(name="n")
            .sort_values(
                ["Customer", "n", "Plant"], ascending=[True, False, True], kind="mergesort"
            )
            .drop_duplicates("Customer")
            .set_index("Customer")["Plant"]
        )
        shipping = [
            o if o else (p if p != NO_DELIVERY else str(usual.get(c, NO_DELIVERY)))
            for o, p, c in zip(lines["Order Plant"], lines["Plant"], lines["Customer"], strict=True)
        ]
        lines["Shipping Plant"] = [f"{s} · {names[s]}" if names.get(s) else s for s in shipping]
        descriptions = (
            obd[obd["Material Description"] != ""]
            .sort_values(["Material", "Material Description"], kind="mergesort")
            .drop_duplicates("Material")
            .set_index("Material")["Material Description"]
        )
        lines["Material Description"] = [str(descriptions.get(m, "")) for m in lines["Material"]]
        lines["Item Name"] = [
            f"{d} [{m}]" if d else m
            for d, m in zip(lines["Material Description"], lines["Material"], strict=True)
        ]
        lines["Filled Qty"] = lines[["Delivered Qty", "Ordered Qty"]].min(axis=1)
        lines["Delivered Value"] = (
            lines["Ordered Value"] * lines["Filled Qty"] / lines["Ordered Qty"]
        )
        lines["Fill Rate"] = lines["Filled Qty"] / lines["Ordered Qty"]
        lines["Status"] = [
            IN_FULL if d >= o else PARTLY if d > 0 else NOT_DELIVERED
            for d, o in zip(lines["Delivered Qty"], lines["Ordered Qty"], strict=True)
        ]
        lines["Over-delivered Qty"] = (lines["Delivered Qty"] - lines["Ordered Qty"]).clip(
            lower=0.0
        )
        full = lines["Status"] == IN_FULL
        lines["Order Kind"] = [
            PROGRAMME if t in PROGRAMME_TYPES else SALE for t in lines["Sales Type"]
        ]
        confirmed = lines["Confirmed Qty"]
        lines["Confirmed (capped)"] = confirmed.clip(upper=lines["Ordered Qty"])
        lines["Not Confirmed Qty"] = (lines["Ordered Qty"] - confirmed).clip(lower=0.0)
        # Distribution value from MB51 (programme commodities have no sales value).
        movements = data.get("movements")
        lines["Distribution Value (MB51)"] = float("nan")
        if movements is not None:
            kinds = movements["Movement Type"].astype("string").str.strip().str.upper()
            issues = movements[kinds.isin(DISTRIBUTION_TYPES).fillna(False).to_numpy()]
            value = pd.DataFrame(
                {
                    "Sales Document": _code(_column(issues, "Sales order")),
                    "Item": _code(_column(issues, "Sales order item")),
                    "Value": issues["Amt.in Loc.Cur."].astype(float).fillna(0.0).abs(),
                }
            )
            value = value[value["Sales Document"] != ""]
            by_item = value[value["Item"] != ""].groupby(["Sales Document", "Item"])["Value"].sum()
            by_order = value[value["Item"] == ""].groupby("Sales Document")["Value"].sum()
            keys = list(zip(lines["Sales Document"], lines["Item"], strict=True))
            from_items = [float(by_item.get(k, 0.0)) for k in keys]
            first_line = ~lines.duplicated("Sales Document")  # order-level value counted once
            from_orders = [
                float(by_order.get(d, 0.0)) if f else 0.0
                for d, f in zip(lines["Sales Document"], first_line, strict=True)
            ]
            lines["Distribution Value (MB51)"] = [
                a + b for a, b in zip(from_items, from_orders, strict=True)
            ]
        # A customer's name from its other deliveries when this line had none.
        known = (
            lines[lines["Customer Name"] != ""]
            .sort_values(["Customer", "Customer Name"], kind="mergesort")
            .drop_duplicates("Customer")
            .set_index("Customer")["Customer Name"]
        )
        lines["Customer Name"] = [
            n if n else str(known.get(c, ""))
            for n, c in zip(lines["Customer Name"], lines["Customer"], strict=True)
        ]
        # Customer location and facility type from OX10, matched by name.
        locations: dict[str, tuple[str, str, str]] = {}
        ox10 = data.get("plants")
        if ox10 is not None:
            for name, district, region in zip(
                ox10["Name 1"].map(_name),
                _column(ox10, "City").map(_name),
                _column(ox10, "Description").map(_name),
                strict=True,
            ):
                if name and name not in locations:
                    locations[name] = (name, district.title(), region.title())
        found = [locations.get(_name(n)) for n in lines["Customer Name"]]
        lines["Facility Type"] = [facility_type(f[0]) if f else UNKNOWN for f in found]
        lines["District"] = [f[1] if f and f[1] else UNKNOWN for f in found]
        lines["Region"] = [f[2] if f and f[2] else UNKNOWN for f in found]
        border = _districts(params.border_districts)
        lines["Border District"] = [_name(d) in border for d in lines["District"]]
        days = (lines["Last Goods Issue"] - lines["Order Date"]).dt.days.astype(float)
        lines["Days to Goods Issue"] = days.where(full)
        lines["Month"] = lines["Order Date"].dt.strftime("%Y-%m")
        lines["Quarter"] = [fiscal_quarter(m) for m in lines["Order Date"].dt.month]
        lines["WBS"] = [
            WBS_PROGRAMME if t in PROGRAMME_TYPES else WBS_OWN for t in lines["Sales Type"]
        ]
        lines = lines.sort_values(["Order Date", "Sales Document", "Item"], kind="mergesort")
        lines = lines.reset_index(drop=True)

        order_full = lines.groupby("Sales Document")["Status"].agg(
            lambda s: bool((s == IN_FULL).all())
        )
        totals = self._group(lines, None)
        order_count, orders_in_full = len(order_full), int(order_full.sum())

        def breakdown(column: str) -> pd.DataFrame:
            return pd.DataFrame(
                [self._group(part, (column, key)) for key, part in lines.groupby(column, sort=True)]
            )

        by_plant = breakdown("Plant")
        if len(by_plant):
            by_plant.insert(1, "Plant Name", [names.get(p, "") for p in by_plant["Plant"]])
        by_customer = breakdown("Customer")
        if len(by_customer):
            customer_names = lines.groupby("Customer")["Customer Name"].max()
            by_customer.insert(
                1, "Customer Name", [customer_names.get(c, "") for c in by_customer["Customer"]]
            )
            by_customer = by_customer.sort_values(["Value Fill Rate", "Customer"], kind="mergesort")
        by_month = breakdown("Month")
        by_kind = breakdown("Order Kind")
        by_facility = breakdown("Facility Type")
        by_region = breakdown("Region")
        by_district = breakdown("District")
        if len(by_district):
            by_district.insert(
                1, "Border District", [_name(d) in border for d in by_district["District"]]
            )
        border_lines = lines[lines["Border District"]]
        border_totals = self._group(border_lines, None) if len(border_lines) else {}
        programme_value = lines.loc[lines["Order Kind"] == PROGRAMME, "Distribution Value (MB51)"]

        line_count = len(lines)
        kpis = [
            Kpi(label="Order lines", value=line_count, format="integer"),
            Kpi(
                label="Line fill rate",
                value=_rate(int(full.sum()), line_count),
                format="percent",
                note="Lines delivered in full",
            ),
            Kpi(
                label="Order fill rate",
                value=_rate(orders_in_full, order_count),
                format="percent",
                note=f"{orders_in_full} of {order_count} orders delivered in full",
            ),
            Kpi(label="Quantity fill rate", value=totals["Quantity Fill Rate"], format="percent"),
            Kpi(
                label="Value fill rate",
                value=totals["Value Fill Rate"],
                format="percent",
                note="Normal sales; programme commodities have no sales value",
            ),
            Kpi(
                label="Quantity confirmed",
                value=totals["Confirmed Fill Rate"],
                format="percent",
                note="VA05 confirmed quantity against ordered quantity",
            ),
            Kpi(
                label="Programme distribution value (ZDON)",
                value=float(programme_value.sum()) if programme_value.notna().any() else None,
                format="money",
                unit="RWF",
                note="MB51 601 / Y01 / Z01 / X01" if movements is not None else "Add MB51",
            ),
            Kpi(
                label="Fill rate in border districts",
                value=border_totals.get("Line Fill Rate"),
                format="percent",
                note=f"{len(border_lines)} order lines",
            ),
            Kpi(
                label="Average days to goods issue",
                value=totals["Average Days to Goods Issue"],
                format="number",
                unit="days",
            ),
        ]
        counted = float(obd["Delivered Qty"].sum())
        checks = [
            Check(
                "lines_by_status",
                "Lines by status = order lines",
                expected=line_count,
                actual=float(sum(int((lines["Status"] == s).sum()) for s in STATUSES)),
                tolerance=0,
            ),
            Check(
                "deliveries_reconcile",
                "Delivered quantity on order lines + deliveries not matched = deliveries counted",
                expected=counted,
                actual=float(lines["Delivered Qty"].sum())
                + float(unmatched["Delivered Qty"].sum()),
            ),
            Check(
                "plants_total",
                "Ordered value by plant = ordered value",
                expected=float(lines["Ordered Value"].sum()),
                actual=float(by_plant["Ordered Value"].sum()) if len(by_plant) else 0.0,
            ),
        ]
        period = f"{params.period_start:%d %B %Y} to {params.period_end:%d %B %Y}"
        subtitle = f"Sales orders of {period}"
        money, percent, number, integer = "money", "percent", "number", "integer"

        def rate_columns(first: list[Column]) -> list[Column]:
            return [
                *first,
                Column(key="Order Lines", label="Lines", format=integer),
                Column(key=IN_FULL, label="In full", format=integer),
                Column(key="Line Fill Rate", label="Line fill rate", format=percent),
                Column(key="Quantity Fill Rate", label="Quantity fill rate", format=percent),
                Column(key="Ordered Value", label="Ordered value", format=money),
                Column(key="Delivered Value", label="Delivered value", format=money),
                Column(key="Value Fill Rate", label="Value fill rate", format=percent),
            ]

        line_columns = [
            "Sales Document",
            "Item",
            "Order Date",
            "Customer",
            "Customer Name",
            "Facility Type",
            "District",
            "Region",
            "Border District",
            "Sales Type",
            "Order Kind",
            "WBS",
            "Material",
            "Material Description",
            "Item Name",
            "Plant",
            "Plant Name",
            "Shipping Plant",
            "Month",
            "Quarter",
            "Ordered Qty",
            "Confirmed Qty",
            "Not Confirmed Qty",
            "Net Price",
            "Delivered Qty",
            "Filled Qty",
            "Over-delivered Qty",
            "Fill Rate",
            "Status",
            "Ordered Value",
            "Delivered Value",
            "Distribution Value (MB51)",
            "Deliveries",
            "Last Goods Issue",
            "Days to Goods Issue",
        ]
        line_table = lines[line_columns].copy()
        line_table["Order Date"] = line_table["Order Date"].dt.strftime("%Y-%m-%d")
        line_table["Last Goods Issue"] = line_table["Last Goods Issue"].dt.strftime("%Y-%m-%d")
        short = line_table[line_table["Status"] != IN_FULL]
        unmatched_table = unmatched[
            ["Delivery", "Sales Document", "Item", "Material", "Plant", "Delivered Qty"]
        ].reset_index(drop=True)
        dashboard = Dashboard(
            title=self.title,
            subtitle=subtitle,
            kpis=kpis,
            charts=[
                Chart(
                    id="plant-chart",
                    title="Value fill rate by delivering plant",
                    type="bar",
                    table="by-plant",
                    category="Plant",
                    format=percent,
                    series=[Series(name="Value fill rate", field="Value Fill Rate")],
                ),
                Chart(
                    id="month-chart",
                    title="Fill rate by order month",
                    type="line",
                    table="by-month",
                    category="Month",
                    format=percent,
                    series=[
                        Series(name="Line fill rate", field="Line Fill Rate"),
                        Series(name="Value fill rate", field="Value Fill Rate"),
                    ],
                ),
            ],
            tables=[
                Table(
                    id="by-plant",
                    title="Fill rate by delivering plant",
                    columns=rate_columns(
                        [Column(key="Plant", label="Plant"), Column(key="Plant Name", label="Name")]
                    ),
                    rows=rows_of(by_plant),
                ),
                Table(
                    id="by-month",
                    title="Fill rate by order month",
                    columns=rate_columns([Column(key="Month", label="Month")]),
                    rows=rows_of(by_month),
                ),
                Table(
                    id="by-kind",
                    title="Sales and programme commodities",
                    columns=[
                        *rate_columns([Column(key="Order Kind", label="Order type")]),
                        Column(
                            key="Confirmed Fill Rate", label="Quantity confirmed", format=percent
                        ),
                        Column(
                            key="Distribution Value (MB51)",
                            label="Distribution value (MB51)",
                            format=money,
                        ),
                    ],
                    rows=rows_of(by_kind),
                ),
                Table(
                    id="by-facility",
                    title="Fill rate by facility type",
                    columns=rate_columns([Column(key="Facility Type", label="Facility type")]),
                    rows=rows_of(by_facility),
                ),
                Table(
                    id="by-region",
                    title="Fill rate by region",
                    columns=rate_columns([Column(key="Region", label="Region")]),
                    rows=rows_of(by_region),
                ),
                Table(
                    id="by-district",
                    title="Fill rate by district (border districts marked)",
                    columns=rate_columns(
                        [
                            Column(key="District", label="District"),
                            Column(key="Border District", label="On the border"),
                        ]
                    ),
                    rows=rows_of(by_district),
                    filters=["Border District"],
                ),
                Table(
                    id="by-customer",
                    title="Fill rate by customer (lowest first)",
                    columns=rate_columns(
                        [
                            Column(key="Customer", label="Customer"),
                            Column(key="Customer Name", label="Name"),
                        ]
                    ),
                    rows=rows_of(by_customer),
                    total_rows=len(by_customer),
                    level="detail",
                    searchable=["Customer", "Customer Name"],
                ),
                Table(
                    id="short-lines",
                    title="Order lines not delivered in full",
                    columns=[
                        Column(key="Sales Document", label="Sales order"),
                        Column(key="Item", label="Item"),
                        Column(key="Order Date", label="Order date", format="date"),
                        Column(key="Customer", label="Customer"),
                        Column(key="Material", label="Material"),
                        Column(key="Plant", label="Plant"),
                        Column(key="Ordered Qty", label="Ordered", format=number),
                        Column(key="Delivered Qty", label="Delivered", format=number),
                        Column(key="Status", label="Status"),
                    ],
                    rows=rows_of(short),
                    total_rows=len(short),
                    level="detail",
                    filters=["Status", "Plant"],
                    searchable=["Sales Document", "Material", "Customer"],
                ),
            ],
            checks=[c.out() for c in checks],
            notes=[
                note
                for note in [
                    f"{zero_lines} order lines with a quantity of zero or less are left out."
                    if zero_lines
                    else "",
                    f"{outside} order lines dated outside the period are left out."
                    if outside
                    else "",
                    f"{len(unmatched)} delivery items refer to no order line of the period."
                    if len(unmatched)
                    else "",
                ]
                if note
            ],
        )
        return AnalysisResult(
            tables={
                "lines": line_table,
                "by_plant": by_plant,
                "by_month": by_month,
                "by_kind": by_kind,
                "by_facility": by_facility,
                "by_region": by_region,
                "by_district": by_district,
                "by_customer": by_customer,
                "short_lines": short,
                "unmatched_deliveries": unmatched_table,
            },
            metrics=kpis,
            checks=checks,
            dashboard=dashboard,
            extras={"subtitle": subtitle, "orders": order_count, "orders_in_full": orders_in_full},
        )

    @staticmethod
    def _group(part: pd.DataFrame, key: tuple[str, Any] | None) -> dict[str, Any]:
        full = part["Status"] == IN_FULL
        ordered_qty, filled_qty = float(part["Ordered Qty"].sum()), float(part["Filled Qty"].sum())
        ordered_value = float(part["Ordered Value"].sum())
        delivered_value = float(part["Delivered Value"].sum())
        days = part["Days to Goods Issue"].dropna()
        row: dict[str, Any] = {key[0]: key[1]} if key else {}
        row.update(
            {
                "Order Lines": len(part),
                **{status: int((part["Status"] == status).sum()) for status in STATUSES},
                "Line Fill Rate": _rate(int(full.sum()), len(part)),
                "Ordered Qty": ordered_qty,
                "Filled Qty": filled_qty,
                "Quantity Fill Rate": _rate(filled_qty, ordered_qty),
                "Ordered Value": ordered_value,
                "Delivered Value": delivered_value,
                "Value Fill Rate": _rate(delivered_value, ordered_value),
                "Average Days to Goods Issue": float(days.mean()) if len(days) else None,
                "Confirmed Fill Rate": _rate(
                    float(part["Confirmed (capped)"].sum()),
                    float(part.loc[part["Confirmed Qty"].notna(), "Ordered Qty"].sum()),
                ),
                "Distribution Value (MB51)": float(
                    part["Distribution Value (MB51)"].sum(min_count=1)
                )
                if part["Distribution Value (MB51)"].notna().any()
                else None,
            }
        )
        return row

    def reports(
        self, result: AnalysisResult, params: BaseModel, templates: Templates
    ) -> list[ReportFile]:
        params = _params(params)
        t = result.tables
        formats: dict[str, ValueFormat] = {
            "Order Lines": "integer",
            **{s: "integer" for s in STATUSES},
            "Confirmed Fill Rate": "percent",
            "Distribution Value (MB51)": "money",
            "Confirmed Qty": "number",
            "Not Confirmed Qty": "number",
            "Net Price": "money",
            "Line Fill Rate": "percent",
            "Quantity Fill Rate": "percent",
            "Value Fill Rate": "percent",
            "Fill Rate": "percent",
            "Ordered Qty": "number",
            "Filled Qty": "number",
            "Delivered Qty": "number",
            "Over-delivered Qty": "number",
            "Ordered Value": "money",
            "Delivered Value": "money",
            "Deliveries": "integer",
            "Average Days to Goods Issue": "number",
            "Days to Goods Issue": "number",
        }
        by_plant = TableBlock("By plant", t["by_plant"], formats)
        by_month = TableBlock("By month", t["by_month"], formats)
        kpi = {k.label: k.value for k in result.metrics}

        def pct(value: object) -> str:
            return f"{float(value):.1%}" if isinstance(value, int | float) else "not available"

        orders, in_full = str(result.extras["orders"]), str(result.extras["orders_in_full"])
        document = ReportDocument(
            title="Order fill rate",
            subtitle=str(result.extras["subtitle"]),
            date_text=f"{params.period_end:%d %B %Y}",
            sections=[
                Section(
                    "Summary",
                    paragraphs=[
                        f"{in_full} of {orders} sales orders ({pct(kpi['Order fill rate'])}) and "
                        f"{pct(kpi['Line fill rate'])} of {kpi['Order lines']} order lines were "
                        f"delivered in full. Quantity fill rate {pct(kpi['Quantity fill rate'])}; "
                        f"value fill rate {pct(kpi['Value fill rate'])}.",
                    ],
                    tables=[by_plant],
                    charts=[
                        ChartBlock(
                            "Value fill rate by plant (%)",
                            [str(p) for p in t["by_plant"]["Plant"]] if len(t["by_plant"]) else [],
                            {
                                "Value fill rate": [
                                    100 * float(v or 0) for v in t["by_plant"]["Value Fill Rate"]
                                ]
                            }
                            if len(t["by_plant"])
                            else {},
                        )
                    ],
                ),
                Section("By month", tables=[by_month]),
                Section(
                    "Facilities and regions",
                    paragraphs=[
                        "Customers are matched to OX10 by name; the facility type comes from the "
                        "abbreviation in the name, the district from City and the region from "
                        "Description."
                    ],
                    tables=[
                        TableBlock("By facility type", t["by_facility"], formats),
                        TableBlock("By region", t["by_region"], formats),
                        TableBlock("By district", t["by_district"], formats),
                    ],
                ),
                Section(
                    "Method",
                    bullets=[
                        "Order lines: VA05 sales order items dated in the period, quantity above "
                        "zero. Deliveries: outbound delivery items referring to the order line"
                        + (", goods issued." if params.goods_issued_only else "."),
                        "A line is delivered in full when the delivered quantity reaches the "
                        "ordered quantity; an order when all its lines are. Quantity and value "
                        "fill rate count delivered quantities up to the ordered quantity.",
                        "Days to goods issue: from the order date to the last goods issue of a "
                        "line delivered in full.",
                    ],
                ),
            ],
            checks=check_lines(result.checks),
        )
        name = f"Order_Fill_Rate_{params.period_start:%Y-%m-%d}_{params.period_end:%Y-%m-%d}"
        whole_year = (params.period_start.month, params.period_start.day) == (7, 1) and (
            params.period_end - params.period_start
        ).days in (364, 365)
        title = (
            f"Order fill rate {fiscal_year(params.period_start)}"
            if whole_year
            else "Order fill rate"
        )
        blocks = [
            by_plant,
            by_month,
            TableBlock("Sales and programme", t["by_kind"], formats),
            TableBlock("By facility type", t["by_facility"], formats),
            TableBlock("By region", t["by_region"], formats),
            TableBlock("By district", t["by_district"], formats),
            TableBlock("By customer", t["by_customer"], formats),
            TableBlock("Order lines", t["lines"], formats),
            TableBlock("Deliveries not matched", t["unmatched_deliveries"], formats),
        ]
        return [
            ReportFile(
                "workbook",
                "Excel workbook",
                f"{name}.xlsx",
                "xlsx",
                build_workbook(
                    document.title,
                    document.subtitle,
                    [(k.label, k.value, k.format) for k in result.metrics],
                    blocks,
                    document.checks,
                ),
            ),
            ReportFile(
                "dashboard",
                "Interactive dashboard (HTML)",
                f"{name}.html",
                "html",
                build_html(
                    dashboard_html.build(
                        t["lines"],
                        title,
                        str(result.extras["subtitle"]),
                        [(c.label, c.expected, c.actual, c.passed) for c in result.checks],
                    )
                ),
            ),
            ReportFile(
                "report",
                "Word report",
                f"{name}.docx",
                "docx",
                build_docx(document, templates.docx),
            ),
            ReportFile(
                "slides",
                "PowerPoint slides",
                f"{name}.pptx",
                "pptx",
                build_pptx(document, templates.pptx),
            ),
        ]


ANALYSIS = OrderFillRate()
