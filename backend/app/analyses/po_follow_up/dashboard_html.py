"""Interactive dashboard of the purchase order follow-up."""

import pandas as pd

from app.analyses.po_follow_up import IN_FULL, OPEN, PARTLY, STATUSES
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

MEASURES = (
    Measure("lines", "PO lines", count=True),
    Measure("in_full", "Delivered in full", count=True, where=("Status", (IN_FULL,))),
    Measure("open", "Open lines", count=True, where=("Status", (PARTLY, OPEN))),
    Measure("ordered", "Ordered value (RWF)", "rwf", sum="Ordered Value"),
    Measure("received", "Received value (RWF)", "rwf", sum="Received Value"),
    Measure("open_value", "Value still to receive (RWF)", "rwf", diff=("ordered", "received")),
    Measure("value_pct", "Received value %", "pct", ratio=("received", "ordered")),
    Measure("in_full_pct", "Lines in full %", "pct", ratio=("in_full", "lines")),
    Measure("on_time", "On time in full", count=True, where=("On time", ("Yes",))),
    Measure("on_time_pct", "On time in full %", "pct", ratio=("on_time", "lines")),
    Measure("overdue", "Overdue lines", count=True, where=("Overdue", ("Yes",))),
    Measure("period_days", "Delivery days", sum="Delivery days"),
    Measure("period_n", "Lines received", sum="Has delivery days"),
    Measure(
        "avg_period", "Average delivery period (days)", "days", ratio=("period_days", "period_n")
    ),
    Measure("approval_days", "Approval days", sum="Approval days"),
    Measure("approval_n", "Lines approved", sum="Has approval days"),
    Measure(
        "avg_approval", "Average days to approval", "days", ratio=("approval_days", "approval_n")
    ),
)
COLUMNS = ("lines", "ordered", "received", "value_pct", "in_full_pct", "on_time_pct", "avg_period")


def _days(values: pd.Series) -> tuple[pd.Series, pd.Series]:
    days = pd.to_numeric(values, errors="coerce")
    return days.fillna(0.0), days.notna().astype(int)


def facts(lines: pd.DataFrame) -> pd.DataFrame:
    period, has_period = _days(lines["Delivery Period (days)"])
    approval, has_approval = _days(lines["Days to Approval"])
    return pd.DataFrame(
        {
            "Month": month_of(lines["Created"]),
            "Order type": lines["Order Type"],
            "Document type": lines["Doc Type"],
            "Plant": [
                f"{p} · {n}" if n else p
                for p, n in zip(lines["Plant"], lines["Plant Name"], strict=True)
            ],
            "Supplier": [
                f"{n} [{s}]" if n else s
                for s, n in zip(lines["Supplier"], lines["Supplier Name"], strict=True)
            ],
            "Status": lines["Status"],
            "On time": lines["On Time"],
            "Overdue": lines["Overdue"],
            "PO": lines["PO"],
            "Line": lines["Item"],
            "Item": [
                f"{d} [{m}]" if d else m
                for d, m in zip(lines["Description"], lines["Material"], strict=True)
            ],
            "Created": lines["Created"],
            "Ordered Value": lines["Ordered Value"].astype(float),
            "Received Value": lines["Received Value"].astype(float),
            "Delivery days": period,
            "Has delivery days": has_period,
            "Approval days": approval,
            "Has approval days": has_approval,
        }
    ).reset_index(drop=True)


def build(
    lines: pd.DataFrame, title: str, subtitle: str, checks: list[tuple[str, float, float, bool]]
) -> InteractiveDashboard:
    return InteractiveDashboard(
        title=title,
        subtitle=subtitle,
        intro=(
            "Purchase orders and stock transport orders against their receipts: value received, "
            "lines in full, on-time delivery, delivery period and time to approval."
        ),
        facts={"lines": facts(lines)},
        measures={"lines": MEASURES},
        filters=(
            Filter("Month", "Month created", "All months"),
            Filter("Order type", "Order type", "POs and STOs"),
            Filter("Document type", "Document type", "All types"),
            Filter("Plant", "Plant", "All plants"),
            Filter("Supplier", "Supplier", "All suppliers"),
            Filter("Status", "Status", "All statuses", order="given", values=tuple(STATUSES)),
            Filter("Overdue", "Overdue", "All lines"),
        ),
        kpis=(
            KpiTile("Received value %", "value_pct", "lines", "{received} of {ordered}"),
            KpiTile(
                "Lines delivered in full",
                "in_full_pct",
                "lines",
                "{in_full} of {lines} lines",
                "green",
            ),
            KpiTile(
                "On time in full", "on_time_pct", "lines", "{on_time} of {lines} lines", "green"
            ),
            KpiTile("Overdue lines", "overdue", "lines", "{open_value} still to receive", "red"),
            KpiTile(
                "Average delivery period", "avg_period", "lines", "days, order to receipt", "grey"
            ),
            KpiTile("Average days to approval", "avg_approval", "lines", "days", "grey"),
        ),
        sections=(
            DashSection(
                "A · Over time",
                note="By month the order was created (ignores the Month filter).",
                blocks=(
                    ChartSpec(
                        "Value still to receive and received value %",
                        "lines",
                        "Month",
                        ("open_value", "value_pct"),
                        kind="combo",
                        ignore=("Month",),
                    ),
                    TableSpec("By month", "lines", ("Month",), COLUMNS, ignore=("Month",)),
                ),
            ),
            DashSection(
                "B · Suppliers and plants",
                blocks=(
                    ChartSpec(
                        "Suppliers with the most value still to receive",
                        "lines",
                        "Supplier",
                        ("open_value",),
                        kind="hbar",
                        sort="desc",
                        sort_by="open_value",
                        limit=15,
                    ),
                    TableSpec(
                        "By supplier",
                        "lines",
                        ("Supplier",),
                        (*COLUMNS, "open_value"),
                        sort_by="open_value",
                        limit=30,
                    ),
                    TableSpec(
                        "By plant", "lines", ("Plant",), (*COLUMNS, "open_value"), sort_by="ordered"
                    ),
                    TableSpec(
                        "By order type",
                        "lines",
                        ("Order type",),
                        (*COLUMNS, "avg_approval"),
                        sort_by="ordered",
                    ),
                ),
            ),
            DashSection(
                "C · PO lines",
                note="Largest value still to receive first; download them as CSV.",
                blocks=(
                    DetailSpec(
                        "PO lines",
                        "lines",
                        (
                            ("PO", "PO", "text"),
                            ("Line", "Item", "text"),
                            ("Created", "Created", "text"),
                            ("Supplier", "Supplier", "text"),
                            ("Item", "Material", "text"),
                            ("Plant", "Plant", "text"),
                            ("Ordered Value", "Ordered (RWF)", "rwf"),
                            ("Received Value", "Received (RWF)", "rwf"),
                            ("Status", "Status", "text"),
                            ("Overdue", "Overdue", "text"),
                        ),
                        sort_by="Ordered Value",
                    ),
                ),
            ),
        ),
        footer=(
            "Rwanda Medical Supply · Purchase order follow-up · ME2N / ME2M and inbound deliveries."
        ),
        checks=checks,
    )
