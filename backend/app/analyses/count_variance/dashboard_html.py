"""Interactive dashboard of the variance investigation (layout of Ferdinand's
"Variance investigation dashboard, PI 30 June 2026")."""

import pandas as pd

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

JUSTIFIED = "Justified"

LINE_MEASURES = (
    Measure("lines", "Variance lines", count=True),
    Measure("justified", "Lines justified", count=True, where=("Explained", (JUSTIFIED,))),
    Measure("pos", "Positive variance: excess (RWF)", "rwf", sum="Positive"),
    Measure("missing", "Negative variance: missing (RWF)", "rwf", sum="Missing"),
    Measure("gross", "Gross absolute (RWF)", "rwf", sum="Absolute"),
    Measure("net", "Net (RWF)", "rwf", sum="Variance"),
    Measure(
        "justified_value",
        "Justified absolute (RWF)",
        "rwf",
        sum="Absolute",
        where=("Explained", (JUSTIFIED,)),
    ),
    Measure(
        "unexplained", "Not Justified absolute (RWF)", "rwf", diff=("gross", "justified_value")
    ),
    Measure("not_justified", "Lines not justified", diff=("lines", "justified")),
    Measure("rate_lines", "Justification rate (lines)", "pct", ratio=("justified", "lines")),
    Measure("rate_value", "Justification rate (value)", "pct", ratio=("justified_value", "gross")),
    Measure("skus", "SKUs", distinct="SKU"),
)
SKU_MEASURES = (
    Measure("skus", "SKUs", count=True),
    Measure("closing", "Closing stock (RWF)", "rwf", sum="Closing value"),
    Measure("abs_before", "Absolute variance (RWF)", "rwf", sum="Absolute variance"),
    Measure("abs_after", "Not Justified variance (RWF)", "rwf", sum="Not Justified variance"),
    Measure("sku_var", "SKUs with a variance", count=True, where=("With variance", ("Yes",))),
    Measure(
        "sku_open",
        "SKUs with a Not Justified variance",
        count=True,
        where=("With Not Justified variance", ("Yes",)),
    ),
    Measure("var_before", "Variance % before", "pct", ratio=("abs_before", "closing")),
    Measure("var_after", "Inventory variance %", "pct", ratio=("abs_after", "closing")),
    Measure(
        "acc_value_before", "Accuracy (value) before justification", "pct", complement="var_before"
    ),
    Measure(
        "acc_value_after", "Accuracy (value) after justification", "pct", complement="var_after"
    ),
    Measure("sku_var_share", "SKUs with a variance %", "pct", ratio=("sku_var", "skus")),
    Measure("sku_open_share", "SKUs not justified %", "pct", ratio=("sku_open", "skus")),
    Measure(
        "acc_sku_before", "Accuracy (SKU) before justification", "pct", complement="sku_var_share"
    ),
    Measure(
        "acc_sku_after", "Accuracy (SKU) after justification", "pct", complement="sku_open_share"
    ),
)


def _plant(code: pd.Series, name: pd.Series) -> list[str]:
    return [f"{c} · {n}" if n and n != c else c for c, n in zip(code, name, strict=True)]


def facts(lines: pd.DataFrame, skus: pd.DataFrame | None) -> dict[str, pd.DataFrame]:
    # "JUSTIFIED" and "Justified" are the same status (any capitals count).
    status = [
        JUSTIFIED if s == JUSTIFIED else (raw or "Not given")
        for s, raw in zip(lines["Status"], lines["Final Validation Status"], strict=True)
    ]
    out = {
        "lines": pd.DataFrame(
            {
                "Plant": _plant(lines["Plant"], lines["Plant Name"]),
                "Stock owner": lines["Stock category"],
                "Validation status": status,
                "Explained": lines["Status"],
                "Root cause": lines["Root cause"],
                "Action": lines["Required action"],
                "Retained earnings": lines["Retained earnings"].map({True: "Yes", False: "No"}),
                "SKU": lines["Plant"] + "|" + lines["Material"] + "|" + lines["WBS"],
                "Document": lines["Document Number"],
                "Posting date": lines["Posting Date"],
                "Material": [
                    f"{d} [{m}]" if d else m
                    for d, m in zip(lines["Material Description"], lines["Material"], strict=True)
                ],
                "WBS": lines["WBS"],
                "Variance": lines["Variance"].astype(float),
                "Positive": lines["Positive"].astype(float),
                "Missing": -lines["Negative"].astype(float),
                "Absolute": lines["Absolute"].astype(float),
                "Amount in SAP": lines["Amount"].astype(float),
            }
        )
    }
    if skus is not None:
        out["skus"] = pd.DataFrame(
            {
                "Plant": _plant(skus["Plant"], skus["Plant Name"]),
                "Stock owner": skus["Stock category"],
                "Closing value": skus["Closing value"].astype(float),
                "Absolute variance": skus["Absolute variance"].astype(float),
                "Not Justified variance": skus["Not Justified variance"].astype(float),
                "With variance": skus["With variance"].map({True: "Yes", False: "No"}),
                "With Not Justified variance": skus["With Not Justified variance"].map(
                    {True: "Yes", False: "No"}
                ),
            }
        )
    return out


def build(
    lines: pd.DataFrame,
    skus: pd.DataFrame | None,
    title: str,
    subtitle: str,
    tolerance: float,
    checks: list[tuple[str, float, float, bool]],
) -> InteractiveDashboard:
    accuracy = 1 - tolerance
    kpis = [
        KpiTile("Variance lines", "lines", "lines", "{skus} SKUs"),
        KpiTile(
            "Justification rate (lines)", "rate_lines", "lines", "{justified} of {lines} lines"
        ),
        KpiTile(
            "Justification rate (value)", "rate_value", "lines", "{justified_value} of {gross}"
        ),
        KpiTile("Lines not justified", "not_justified", "lines", "{unexplained} absolute", "red"),
        KpiTile("Positive variance: excess", "pos", "lines", "found above book", "green"),
        KpiTile("Negative variance: missing", "missing", "lines", "found below book", "red"),
        KpiTile(
            "Gross absolute variance", "gross", "lines", "net {net} (information only)", "grey"
        ),
    ]
    sections: list[DashSection] = []
    if skus is not None:
        kpis = [
            KpiTile(
                "Inventory accuracy (value) before justification",
                "acc_value_before",
                "skus",
                "raw count · closing {closing}",
            ),
            KpiTile(
                "Inventory accuracy (value) after justification",
                "acc_value_after",
                "skus",
                f"standard at least {accuracy:.1%}",
                "green",
            ),
            KpiTile(
                "Inventory accuracy (SKU) before justification",
                "acc_sku_before",
                "skus",
                "{sku_var} of {skus} SKUs with a variance",
            ),
            KpiTile(
                "Inventory accuracy (SKU) after justification",
                "acc_sku_after",
                "skus",
                "{sku_open} SKUs not justified",
                "green",
            ),
            *kpis,
        ]
        sections.append(
            DashSection(
                "A · Inventory accuracy before and after justification",
                note=(
                    "Follows the plant and stock owner filters. Value accuracy = 1 − absolute "  # noqa: RUF001
                    "variance ÷ final closing stock (after justification: Not Justified variance "
                    "only, Variance Management SOP). SKU accuracy = share of SKUs without a "
                    "variance (after: without a Not Justified variance)."
                ),
                blocks=(
                    TableSpec(
                        "Inventory accuracy by plant",
                        "skus",
                        ("Plant",),
                        (
                            "closing",
                            "abs_before",
                            "abs_after",
                            "acc_value_before",
                            "acc_value_after",
                            "acc_sku_before",
                            "acc_sku_after",
                        ),
                        sort_by="abs_after",
                        bars=("acc_value_after", "acc_sku_after"),
                        traffic=(0.98, accuracy),
                    ),
                    TableSpec(
                        "Inventory accuracy by stock owner",
                        "skus",
                        ("Stock owner",),
                        (
                            "closing",
                            "abs_after",
                            "acc_value_before",
                            "acc_value_after",
                            "acc_sku_after",
                        ),
                        sort_by="closing",
                        bars=("acc_value_after",),
                        traffic=(0.98, accuracy),
                    ),
                ),
            )
        )
    sections += [
        DashSection(
            "B · Justification",
            blocks=(
                ChartSpec(
                    "Lines by final validation status",
                    "lines",
                    "Validation status",
                    ("lines",),
                    kind="hbar",
                    sort="desc",
                    sort_by="lines",
                ),
                ChartSpec(
                    "Justification rate by plant (lines)",
                    "lines",
                    "Plant",
                    ("rate_lines",),
                    kind="hbar",
                    note="Red below 85%, amber below 95%.",
                    sort="asc",
                    sort_by="rate_lines",
                    percent=True,
                    traffic=(0.85, 0.95),
                ),
                TableSpec(
                    "Justification by plant",
                    "lines",
                    ("Plant",),
                    ("lines", "justified", "rate_lines", "gross", "unexplained", "rate_value"),
                    sort_by="unexplained",
                    bars=("rate_lines", "rate_value"),
                ),
            ),
        ),
        DashSection(
            "C · Value and exposure",
            note=(
                "Positive = excess (found above book). Negative = missing (found below book). "
                "Never netted."
            ),
            blocks=(
                ChartSpec(
                    "Gross positive and negative variance by plant",
                    "lines",
                    "Plant",
                    ("pos", "missing"),
                    kind="hbar",
                    sort="desc",
                    sort_by="gross",
                    limit=20,
                ),
                ChartSpec(
                    "Variance by stock owner",
                    "lines",
                    "Stock owner",
                    ("pos", "missing"),
                    sort="desc",
                    sort_by="gross",
                ),
            ),
        ),
        DashSection(
            "D · Root causes and actions",
            blocks=(
                ChartSpec(
                    "Root causes (gross absolute value)",
                    "lines",
                    "Root cause",
                    ("gross",),
                    kind="hbar",
                    sort="desc",
                    sort_by="gross",
                ),
                ChartSpec(
                    "Required action (gross absolute value)",
                    "lines",
                    "Action",
                    ("gross",),
                    kind="hbar",
                    sort="desc",
                    sort_by="gross",
                ),
                TableSpec(
                    "Root causes",
                    "lines",
                    ("Root cause",),
                    ("lines", "justified", "pos", "missing", "gross"),
                    sort_by="gross",
                ),
                TableSpec(
                    "Required actions",
                    "lines",
                    ("Action",),
                    ("lines", "justified", "pos", "missing", "gross", "net"),
                    sort_by="gross",
                ),
            ),
        ),
        DashSection(
            "E · Variance lines",
            note="Filtered lines, largest first. Search by document, material or reason.",
            blocks=(
                DetailSpec(
                    "Variance lines",
                    "lines",
                    (
                        ("Document", "Document", "text"),
                        ("Plant", "Plant", "text"),
                        ("Stock owner", "Owner", "text"),
                        ("Material", "Material", "text"),
                        ("Variance", "Variance (+ excess / − missing)", "rwf"),  # noqa: RUF001
                        ("Amount in SAP", "SAP amount", "rwf"),
                        ("Validation status", "Status", "text"),
                        ("Root cause", "Root cause", "text"),
                        ("Action", "Action", "text"),
                    ),
                    sort_by="Absolute",
                ),
            ),
        ),
    ]
    return InteractiveDashboard(
        title=title,
        subtitle=subtitle,
        intro=(
            "Every stock adjustment posted after the count, its justification, root cause and "
            "required action, and the inventory accuracy before and after justification."
        ),
        facts=facts(lines, skus),
        measures={"lines": LINE_MEASURES, "skus": SKU_MEASURES},
        filters=(
            Filter("Plant", "Plant", "All plants"),
            Filter("Stock owner", "Stock owner", "All owners"),
            Filter("Validation status", "Validation status", "All statuses"),
            Filter("Explained", "Justified or not", "All lines"),
            Filter("Root cause", "Root cause", "All root causes"),
            Filter("Action", "Action", "All actions"),
            Filter("Retained earnings", "Retained earnings", "All lines"),
        ),
        kpis=tuple(kpis),
        sections=tuple(sections),
        footer=(
            "Rwanda Medical Supply · Physical inventory variance investigation · stock variance = "
            "minus the amount on the inventory difference account."
        ),
        checks=checks,
    )
