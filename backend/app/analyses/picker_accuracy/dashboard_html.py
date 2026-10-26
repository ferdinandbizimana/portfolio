"""Interactive dashboard of picker accuracy (lines and discrepancies)."""

import pandas as pd

from app.reporting.interactive import (
    ChartSpec,
    DashSection,
    Filter,
    InteractiveDashboard,
    KpiTile,
    Measure,
    TableSpec,
)

MEASURES = (
    Measure("lines", "Lines picked", sum="Lines"),
    Measure("wrong", "Discrepancies", sum="Discrepancies"),
    Measure("error_rate", "Discrepancy rate", "pct", ratio=("wrong", "lines")),
    Measure("accuracy", "Accuracy", "pct", complement="error_rate"),
)
ORDER_MEASURES = (*MEASURES, Measure("deliveries", "Deliveries", sum="Deliveries"))


def build(
    by_picker_day: pd.DataFrame,
    by_customer: pd.DataFrame,
    by_type: pd.DataFrame,
    target: float,
    title: str,
    subtitle: str,
    checks: list[tuple[str, float, float, bool]],
) -> InteractiveDashboard:
    days = pd.DataFrame(
        {
            "Picker": by_picker_day["Picker"],
            "Day": by_picker_day["Day"].astype(str),
            "Lines": by_picker_day["Lines"].astype(float),
            "Discrepancies": by_picker_day["Discrepancies"].astype(float),
        }
    )
    facts: dict[str, pd.DataFrame] = {"days": days}
    measures: dict[str, tuple[Measure, ...]] = {"days": MEASURES}
    sections = [
        DashSection(
            "A · Pickers",
            note=f"Target {target:.0%}: red below 95%, amber below the target.",
            blocks=(
                ChartSpec(
                    "Accuracy by picker (lowest first)",
                    "days",
                    "Picker",
                    ("accuracy",),
                    kind="hbar",
                    ignore=("Picker",),
                    sort="asc",
                    sort_by="accuracy",
                    percent=True,
                    traffic=(min(0.95, target), target),
                ),
                TableSpec(
                    "By picker",
                    "days",
                    ("Picker",),
                    ("lines", "wrong", "accuracy"),
                    ignore=("Picker",),
                    sort_by="accuracy",
                    descending=False,
                    bars=("accuracy",),
                    traffic=(min(0.95, target), target),
                ),
            ),
        ),
        DashSection(
            "B · Days",
            blocks=(
                ChartSpec(
                    "Accuracy by day",
                    "days",
                    "Day",
                    ("accuracy",),
                    kind="line",
                    ignore=("Day",),
                    percent=True,
                ),
                TableSpec(
                    "By day", "days", ("Day",), ("lines", "wrong", "accuracy"), ignore=("Day",)
                ),
            ),
        ),
    ]
    for key, frame, column in (
        ("customers", by_customer, "Customer"),
        ("types", by_type, "Order Type"),
    ):
        if len(frame):
            facts[key] = pd.DataFrame(
                {
                    column: frame[column].astype(str),
                    "Deliveries": frame["Deliveries"].astype(float),
                    "Lines": frame["Lines"].astype(float),
                    "Discrepancies": frame["Discrepancies"].astype(float),
                }
            )
            measures[key] = ORDER_MEASURES
    if len(by_customer) or len(by_type):
        sections.append(
            DashSection(
                "C · Customers and order types",
                note="From the sheets with one row per outbound delivery (not filtered by picker).",
                blocks=tuple(
                    TableSpec(
                        f"By {column.lower()}",
                        key,
                        (column,),
                        ("deliveries", "lines", "wrong", "accuracy"),
                        sort_by="wrong",
                    )
                    for key, column in (("customers", "Customer"), ("types", "Order Type"))
                    if key in facts
                ),
            )
        )
    return InteractiveDashboard(
        title=title,
        subtitle=subtitle,
        intro="Lines picked and discrepancies per picker and per day, against the accuracy target.",
        facts=facts,
        measures=measures,
        filters=(Filter("Picker", "Picker", "All pickers"), Filter("Day", "Day", "All days")),
        kpis=(
            KpiTile("Picking accuracy", "accuracy", "days", f"target {target:.0%}", "green"),
            KpiTile("Lines picked", "lines", "days"),
            KpiTile("Discrepancies", "wrong", "days", "{error_rate} of lines", "red"),
        ),
        sections=tuple(sections),
        footer="Rwanda Medical Supply · Picker accuracy · picking register.",
        checks=checks,
    )
