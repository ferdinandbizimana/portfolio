"""Interactive dashboard of warehouse activity (EWM tasks)."""

import pandas as pd

from app.analyses.warehouse_activity import DOCK_BANDS
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

PUTAWAY_MEASURES = (
    Measure("putaways", "Putaways", count=True),
    Measure("on_target", "On target", count=True, where=("On target", ("Yes",))),
    Measure("dated", "With a goods receipt date", count=True, where=("On target", ("Yes", "No"))),
    Measure("target_pct", "Dock to stock on target", "pct", ratio=("on_target", "dated")),
    Measure("dock_days", "Dock to stock days", sum="Dock days"),
    Measure("avg_dock", "Average dock to stock (days)", "days", ratio=("dock_days", "dated")),
)
PICK_MEASURES = (
    Measure("picks", "Picks", count=True),
    Measure("hours", "Picking hours", sum="Hours"),
    Measure("timed", "Timed picks", sum="Timed"),
    Measure("avg_hours", "Average picking time (hours)", "num", ratio=("hours", "timed")),
)
OPEN_MEASURES = (
    Measure("open", "Open tasks", count=True),
    Measure("age", "Age days", sum="Age"),
    Measure("avg_age", "Average age (days)", "days", ratio=("age", "open")),
)


def _numbers(values: pd.Series) -> tuple[pd.Series, pd.Series]:
    numbers = pd.to_numeric(values, errors="coerce")
    return numbers.fillna(0.0), numbers.notna().astype(int)


def facts(
    putaways: pd.DataFrame, picks: pd.DataFrame, open_tasks: pd.DataFrame, target: int
) -> dict[str, pd.DataFrame]:
    dock, has_dock = _numbers(putaways["Dock to Stock (days)"])
    hours, timed = _numbers(picks["Picking Time (hours)"])
    return {
        "putaways": pd.DataFrame(
            {
                "Month": month_of(putaways["Confirmed"]),
                "User": putaways["Confirmed By"],
                "Dock to stock": putaways["Dock to Stock"],
                "On target": [
                    ("Yes" if d <= target else "No") if h else ""
                    for d, h in zip(dock, has_dock, strict=True)
                ],
                "Task": putaways["Warehouse Task"],
                "Product": putaways["Product Description"].where(
                    putaways["Product Description"].astype(str) != "", putaways["Product"]
                ),
                "Goods receipt": putaways["Goods Receipt Date"],
                "Confirmed": putaways["Confirmed"],
                "Dock days": dock,
            }
        ).reset_index(drop=True),
        "picks": pd.DataFrame(
            {
                "Month": month_of(picks["Confirmed"]),
                "User": picks["Confirmed By"],
                "Hours": hours,
                "Timed": timed,
            }
        ).reset_index(drop=True),
        "open": pd.DataFrame(
            {
                "Kind": open_tasks["Kind"],
                "Process type": open_tasks["Process Type"],
                "Age": pd.to_numeric(open_tasks["Age (days)"], errors="coerce").fillna(0.0),
            }
        ).reset_index(drop=True),
    }


def build(
    putaways: pd.DataFrame,
    picks: pd.DataFrame,
    open_tasks: pd.DataFrame,
    target: int,
    title: str,
    subtitle: str,
    checks: list[tuple[str, float, float, bool]],
) -> InteractiveDashboard:
    return InteractiveDashboard(
        title=title,
        subtitle=subtitle,
        intro=(
            f"Putaways against the dock-to-stock target of {target} days, picking time and the "
            "tasks still open, by month and user."
        ),
        facts=facts(putaways, picks, open_tasks, target),
        measures={"putaways": PUTAWAY_MEASURES, "picks": PICK_MEASURES, "open": OPEN_MEASURES},
        filters=(
            Filter("Month", "Month", "All months"),
            Filter("User", "User", "All users"),
            Filter(
                "Dock to stock",
                "Dock to stock",
                "All putaways",
                order="given",
                values=tuple(DOCK_BANDS),
            ),
        ),
        kpis=(
            KpiTile(
                "Dock to stock on target",
                "target_pct",
                "putaways",
                "{on_target} of {dated} putaways",
                "green",
            ),
            KpiTile("Average dock to stock", "avg_dock", "putaways", "days"),
            KpiTile("Average picking time", "avg_hours", "picks", "hours · {picks} picks"),
            KpiTile("Open tasks", "open", "open", "average age {avg_age} days", "amber"),
        ),
        sections=(
            DashSection(
                "A · Dock to stock",
                blocks=(
                    ChartSpec(
                        "Putaways by dock-to-stock time",
                        "putaways",
                        "Dock to stock",
                        ("putaways",),
                        ignore=("Dock to stock",),
                    ),
                    ChartSpec(
                        "Dock to stock on target by month",
                        "putaways",
                        "Month",
                        ("target_pct",),
                        kind="line",
                        ignore=("Month",),
                        percent=True,
                    ),
                    TableSpec(
                        "By user",
                        "putaways",
                        ("User",),
                        ("putaways", "target_pct", "avg_dock"),
                        sort_by="putaways",
                        bars=("target_pct",),
                    ),
                ),
            ),
            DashSection(
                "B · Picking",
                blocks=(
                    TableSpec(
                        "Picking time by user",
                        "picks",
                        ("User",),
                        ("picks", "avg_hours"),
                        sort_by="picks",
                    ),
                    TableSpec(
                        "Picking by month",
                        "picks",
                        ("Month",),
                        ("picks", "avg_hours"),
                        ignore=("Month",),
                    ),
                ),
            ),
            DashSection(
                "C · Open tasks",
                note="Not filtered by month or user.",
                blocks=(
                    TableSpec(
                        "Open tasks by kind and process type",
                        "open",
                        ("Kind", "Process type"),
                        ("open", "avg_age"),
                        sort_by="open",
                    ),
                ),
            ),
            DashSection(
                "D · Putaways",
                note="Slowest first; download them as CSV.",
                blocks=(
                    DetailSpec(
                        "Putaways",
                        "putaways",
                        (
                            ("Task", "Task", "text"),
                            ("Product", "Product", "text"),
                            ("User", "User", "text"),
                            ("Goods receipt", "Goods receipt", "text"),
                            ("Confirmed", "Confirmed", "text"),
                            ("Dock days", "Days", "int"),
                            ("Dock to stock", "Band", "text"),
                        ),
                        sort_by="Dock days",
                    ),
                ),
            ),
        ),
        footer="Rwanda Medical Supply · Warehouse activity · EWM warehouse tasks.",
        checks=checks,
    )
