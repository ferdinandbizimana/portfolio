"""Interactive dashboard of the spot check: accuracy, variances and data-integrity flags."""

import pandas as pd

from app.reporting.interactive import (
    ChartSpec,
    DashSection,
    DetailSpec,
    Filter,
    Fmt,
    InteractiveDashboard,
    KpiTile,
    Measure,
    TableSpec,
)

MEASURES = (
    Measure("lines", "Lines", count=True),
    Measure(
        "variance_lines", "Lines with a variance", count=True, where=("Has Variance", ("Yes",))
    ),
    Measure(
        "real_lines", "Real variance lines", count=True, where=("Real Variance Line", ("Yes",))
    ),
    Measure("explained", "Explained lines", count=True, where=("Explained", ("Yes",))),
    Measure("integrity", "Data-integrity flags", count=True, where=("Data Integrity", ("Yes",))),
    Measure("system", "System quantity", "num", sum="System Qty"),
    Measure("net", "Net variance", "num", sum="Variance"),
    Measure("real_net", "Real net variance", "num", sum="Real Variance"),
    Measure("net_size", "Size of net variance", "num", absolute="net"),
    Measure("real_size", "Size of real net variance", "num", absolute="real_net"),
    Measure("qty_error", "Quantity error", "pct", ratio=("net_size", "system")),
    Measure("true_qty_error", "True quantity error", "pct", ratio=("real_size", "system")),
    Measure("qty_accuracy", "Quantity accuracy", "pct", complement="qty_error"),
    Measure("true_qty_accuracy", "True quantity accuracy", "pct", complement="true_qty_error"),
    Measure("line_error", "Line error", "pct", ratio=("variance_lines", "lines")),
    Measure("true_line_error", "True line error", "pct", ratio=("real_lines", "lines")),
    Measure("line_accuracy", "Line accuracy", "pct", complement="line_error"),
    Measure("true_line_accuracy", "True line accuracy", "pct", complement="true_line_error"),
    Measure("value", "Net variance (RWF)", "rwf", sum="Variance Value"),
)
COLUMNS = (
    "lines",
    "qty_accuracy",
    "true_qty_accuracy",
    "line_accuracy",
    "true_line_accuracy",
    "real_lines",
    "integrity",
    "value",
)
LINE_COLUMNS: tuple[tuple[str, str, Fmt], ...] = (
    ("Check", "Spot check", "text"),
    ("Storage Bin", "Bin", "text"),
    ("Item", "Product", "text"),
    ("Batch", "Batch", "text"),
    ("WBS", "WBS", "text"),
    ("Responsible", "Responsible", "text"),
    ("System Qty", "System", "num"),
    ("Counted Qty", "Counted", "num"),
    ("Variance", "Variance", "num"),
    ("Variance Value", "Value (RWF)", "rwf"),
    ("Explained", "Explained", "text"),
    ("Comment", "Comment", "text"),
)


def facts(lines: pd.DataFrame) -> pd.DataFrame:
    frame = lines.drop(columns=["Unit Cost"]).copy()
    frame["Item"] = [
        f"{d} [{p}]" if d else p
        for d, p in zip(frame["Product Description"], frame["Product"], strict=True)
    ]
    return frame.reset_index(drop=True)


def build(
    lines: pd.DataFrame,
    previous_label: str,
    title: str,
    subtitle: str,
    checks: list[tuple[str, float, float, bool]],
) -> InteractiveDashboard:
    data = facts(lines)
    checks_present = list(dict.fromkeys(data["Check"]))
    this = checks_present[0] if checks_present else ""
    variance_rows = data[data["Has Variance"] == "Yes"].reset_index(drop=True)
    integrity_rows = data[data["Data Integrity"] == "Yes"].reset_index(drop=True)
    return InteractiveDashboard(
        title=title,
        subtitle=subtitle,
        intro=(
            "Quantity accuracy = 1 - |net variance| / system quantity; line accuracy = 1 - lines "
            "with a variance / lines checked. True accuracy leaves out variances explained by "
            "the supervisor's comment."
        ),
        facts={"lines": data, "variances": variance_rows, "integrity": integrity_rows},
        measures={"lines": MEASURES, "variances": MEASURES, "integrity": MEASURES},
        filters=(
            Filter(
                "Check",
                "Spot check",
                "Both spot checks",
                order="given",
                values=tuple(checks_present),
            ),
            Filter("WBS", "WBS", "All WBS"),
            Filter("Storage Type", "Storage type", "All storage types"),
            Filter("Responsible", "Responsible", "Everyone"),
        ),
        kpis=(
            KpiTile("Lines checked", "lines", "lines", "{variance_lines} with a variance"),
            KpiTile("Quantity accuracy", "qty_accuracy", "lines", "true: {true_qty_accuracy}"),
            KpiTile("Line accuracy", "line_accuracy", "lines", "true: {true_line_accuracy}"),
            KpiTile(
                "Real variance lines",
                "real_lines",
                "lines",
                "{explained} explained by a comment",
                "red",
            ),
            KpiTile("Net variance", "value", "lines", "RWF, counted less system", "amber"),
            KpiTile(
                "Data-integrity flags",
                "integrity",
                "lines",
                "wrong batch, expiry or description",
                "grey",
            ),
        ),
        sections=(
            DashSection(
                "A · Spot checks compared",
                note=f"{this} against {previous_label} when both are loaded.",
                blocks=(
                    ChartSpec(
                        "Accuracy by spot check",
                        "lines",
                        "Check",
                        (
                            "qty_accuracy",
                            "true_qty_accuracy",
                            "line_accuracy",
                            "true_line_accuracy",
                        ),
                        ignore=("Check",),
                        percent=True,
                    ),
                    TableSpec("By spot check", "lines", ("Check",), COLUMNS, ignore=("Check",)),
                ),
            ),
            DashSection(
                "B · By WBS, storage type and responsible person",
                blocks=(
                    ChartSpec(
                        "True line accuracy by responsible person (lowest first)",
                        "lines",
                        "Responsible",
                        ("true_line_accuracy",),
                        kind="hbar",
                        ignore=("Responsible",),
                        sort="asc",
                        sort_by="true_line_accuracy",
                        percent=True,
                        traffic=(0.95, 1.0),
                    ),
                    TableSpec("By WBS", "lines", ("WBS",), COLUMNS, ignore=("WBS",)),
                    TableSpec(
                        "By storage type",
                        "lines",
                        ("Storage Type",),
                        COLUMNS,
                        ignore=("Storage Type",),
                    ),
                    TableSpec(
                        "By responsible person",
                        "lines",
                        ("Responsible",),
                        COLUMNS,
                        ignore=("Responsible",),
                        sort_by="real_lines",
                    ),
                ),
            ),
            DashSection(
                "C · Variances",
                blocks=(
                    TableSpec(
                        "Products with the largest net variance",
                        "variances",
                        ("Item",),
                        ("variance_lines", "net", "real_net", "value"),
                        sort_by="value",
                        limit=20,
                        labels={"Item": "Product"},
                    ),
                    DetailSpec(
                        "Variance lines",
                        "variances",
                        LINE_COLUMNS,
                        sort_by="Variance Value",
                    ),
                ),
            ),
            DashSection(
                "D · Data-integrity flags",
                note="Stock present but its record was wrong: batch, expiry date or description.",
                blocks=(
                    DetailSpec(
                        "Lines flagged by the comment",
                        "integrity",
                        LINE_COLUMNS,
                    ),
                ),
            ),
            DashSection(
                "E · All lines",
                blocks=(
                    DetailSpec(
                        "Every line checked",
                        "lines",
                        LINE_COLUMNS,
                        sort_by="Variance Value",
                    ),
                ),
            ),
        ),
        footer="Rwanda Medical Supply · spot check accuracy · quantities in the unit of the bin.",
        checks=checks,
    )
