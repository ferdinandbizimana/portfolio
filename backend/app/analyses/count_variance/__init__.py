"""Physical inventory variance investigation: justification and inventory accuracy.

Rules from the Variance Investigation Report of the 30 June 2026 count
(narrative report and Detailed Variance Report, Variance Management SOP):

- Every stock-adjustment line posted in SAP after the count is a variance
  line. Stock variance = - amount on the inventory difference account: a
  positive variance is physical stock above the SAP quantity, a negative one
  below. Positive and negative are never offset: absolute variance =
  positive - negative.
- Each line is Justified or Not Justified (its final validation status).
- Inventory variance (%) = Σ |Not Justified variance| ÷ total inventory value
  in system (the final closing stock); inventory accuracy = 100% - inventory
  variance. Tolerance 0.5%: accuracy of at least 99.5% is acceptable.
- Root cause and required action per line are used when the file has them
  (columns "Root cause" and "Required action" / "Action category").
- Lines with an amount moved to retained earnings are the historical lines
  proposed for transfer to retained earnings; their variance is minus that
  amount.
"""

from datetime import date
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from app.analyses.base import Analysis, AnalysisResult, Check, InputSpec
from app.analyses.common.closing import NO_WBS, material_code, plant_code
from app.analyses.common.programmes import PROGRAMMES, normalise_category
from app.analyses.count_variance import dashboard_html
from app.analyses.dashboard import Chart, Column, Dashboard, Kpi, Series, Table, rows_of
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

JUSTIFIED, NOT_JUSTIFIED = "Justified", "Not Justified"
PROGRAMME_WBS, OWN_WBS = "RMS-PRG-FND-CP", "RMS-OWN-ESE-RM"
STOCK_CATEGORY = {PROGRAMME_WBS: "Program stock", OWN_WBS: "RMS-own stock"}
OTHER_STOCK = "No WBS / other stock"
NOT_GIVEN = "Not given in the file"
VARIANCE_COLUMN = "Stock Variance (RWF): + excess / - missing"
# Signs used in the SOP formulas, written as in the narrative report.
MINUS, TIMES = "\u2212", "\u00d7"


class Parameters(BaseModel):
    count_date: date = Field(
        title="Count date", description="Date of the physical inventory count, e.g. 30 June 2026."
    )
    tolerance: float = Field(
        default=0.005,
        gt=0,
        lt=1,
        title="Tolerance",
        description="Tolerable inventory variance (0.005 = 0.5%).",
    )


def _params(params: BaseModel) -> Parameters:
    if not isinstance(params, Parameters):
        raise TypeError("Parameters of the wrong analysis.")
    return params


def _text(values: pd.Series) -> pd.Series:
    return values.astype("string").str.strip().fillna("").astype(str)


def status_of(value: str) -> str:
    """Justified (any capitalisation) or Not Justified (anything else)."""
    return JUSTIFIED if value.strip().casefold() == "justified" else NOT_JUSTIFIED


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _variance_block(frame: pd.DataFrame) -> dict[str, float]:
    positive = float(frame["Positive"].sum())
    negative = float(frame["Negative"].sum())
    return {"Positive": positive, "Negative": negative, "Absolute": positive - negative}


def prepare_lines(raw: pd.DataFrame) -> pd.DataFrame:
    lines = pd.DataFrame(
        {
            "Plant": plant_code(raw["Plant"]).astype(str),
            "Plant Name": _text(raw["Plant Description"]),
            "Material": material_code(raw["Material"]).astype(str),
            "Material Description": _text(raw["Material Description"]),
            "WBS": _text(raw["WBS Element"]).replace("", NO_WBS),
            "Document Number": _text(raw["Document Number"]),
            "Posting Date": _text(raw["Posting Date"]),
            "G/L Account": _text(raw["G/L Account"]),
            "Amount": raw["Amount in Local Currency"].astype(float).fillna(0.0),
            "ACTION": _text(raw["ACTION"]),
            "REASON": _text(raw["REASON"]),
            "Final Validation Status": _text(raw["Final Validation Status"]),
            "Root cause": _text(raw["Root cause"]).replace("", NOT_GIVEN),
            "Required action": _text(raw["Action category"]).replace("", NOT_GIVEN),
            "Retained earnings amount": raw["AMOUNT MOVED TO RETAINED EARNINGS"].astype(float),
        }
    )
    given = raw[VARIANCE_COLUMN].astype(float)
    # The variance is the opposite of the amount on the difference account.
    lines["Variance"] = given.where(given.notna(), -lines["Amount"])
    lines["Status"] = lines["Final Validation Status"].map(status_of)
    lines["Positive"] = lines["Variance"].clip(lower=0.0)
    lines["Negative"] = lines["Variance"].clip(upper=0.0)
    lines["Absolute"] = lines["Variance"].abs()
    lines["Stock category"] = lines["WBS"].map(STOCK_CATEGORY).fillna(OTHER_STOCK)
    # Lines with an amount moved to retained earnings (zero included), as in the
    # key findings of the June 2026 report.
    lines["Retained earnings"] = lines["Retained earnings amount"].notna()
    names = (
        lines[lines["Plant Name"] != ""]
        .sort_values(["Plant", "Plant Name"], kind="mergesort")
        .drop_duplicates("Plant")
        .set_index("Plant")["Plant Name"]
    )
    lines["Plant Name"] = lines["Plant"].map(names).fillna(lines["Plant"])
    return lines.reset_index(drop=True)


def headline(lines: pd.DataFrame) -> pd.DataFrame:
    """Table 1: all lines, Justified, Not Justified."""
    total = _variance_block(lines)
    rows = []
    for label, part in (
        ("Variance at the count", lines),
        (JUSTIFIED, lines[lines["Status"] == JUSTIFIED]),
        (NOT_JUSTIFIED, lines[lines["Status"] == NOT_JUSTIFIED]),
    ):
        block = _variance_block(part)
        rows.append(
            {
                "Category": label,
                "Lines": len(part),
                "% of lines": _ratio(len(part), len(lines)) if part is not lines else None,
                **block,
                "% of absolute value": _ratio(block["Absolute"], total["Absolute"])
                if part is not lines
                else None,
            }
        )
    return pd.DataFrame(rows)


def by_plant(lines: pd.DataFrame) -> pd.DataFrame:
    """Table 2: justification by plant."""
    justified = lines["Status"] == JUSTIFIED
    table = (
        lines.assign(
            _j=justified.astype(int),
            _n=(~justified).astype(int),
            _jv=lines["Absolute"].where(justified, 0.0),
            _nv=lines["Absolute"].where(~justified, 0.0),
        )
        .groupby(["Plant", "Plant Name"], sort=True)
        .agg(
            Lines=("Material", "size"),
            **{
                "Justified lines": ("_j", "sum"),
                "Not Justified lines": ("_n", "sum"),
                "Justified value": ("_jv", "sum"),
                "Not Justified value": ("_nv", "sum"),
            },
        )
        .reset_index()
    )
    table["Justified % of value"] = [
        _ratio(j, j + n)
        for j, n in zip(table["Justified value"], table["Not Justified value"], strict=True)
    ]
    return table.sort_values(
        ["Justified % of value", "Justified value", "Plant"],
        ascending=[False, False, True],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)


def by_group(lines: pd.DataFrame, column: str) -> pd.DataFrame:
    """Tables 3 and 4: root causes and required actions."""
    justified = lines["Status"] == JUSTIFIED
    table = (
        lines.assign(_j=justified.astype(int), _n=(~justified).astype(int))
        .groupby(column, sort=True)
        .agg(
            Lines=("Material", "size"),
            **{
                "Justified lines": ("_j", "sum"),
                "Not Justified lines": ("_n", "sum"),
                "Positive": ("Positive", "sum"),
                "Negative": ("Negative", "sum"),
                "Absolute": ("Absolute", "sum"),
            },
        )
        .reset_index()
    )
    total = float(lines["Absolute"].sum())
    table["% of absolute value"] = table["Absolute"] / total if total else 0.0
    return table.sort_values(
        ["Absolute", column], ascending=[False, True], kind="mergesort"
    ).reset_index(drop=True)


def sku_accuracy(lines: pd.DataFrame, values: pd.DataFrame) -> pd.DataFrame:
    """One row per SKU (plant, material, WBS) of the final closing stock or with
    variance lines: closing value, absolute variance and absolute Not Justified
    variance (for accuracy before and after justification)."""
    keys = ["Plant", "Material", "WBS"]
    variance = (
        lines.assign(_nj=lines["Absolute"].where(lines["Status"] == NOT_JUSTIFIED, 0.0))
        .groupby(keys, sort=True)
        .agg(
            **{
                "Absolute variance": ("Absolute", "sum"),
                "Not Justified variance": ("_nj", "sum"),
            }
        )
        .reset_index()
    )
    closing = values.groupby(keys, sort=True)["Value"].sum().rename("Closing value").reset_index()
    skus = closing.merge(variance, on=keys, how="outer").fillna(
        {"Closing value": 0.0, "Absolute variance": 0.0, "Not Justified variance": 0.0}
    )
    names = {
        **dict(zip(values["Plant"], values["Plant Name"], strict=True)),
        **dict(zip(lines["Plant"], lines["Plant Name"], strict=True)),
    }
    skus["Plant Name"] = [names.get(p, "") or p for p in skus["Plant"]]
    skus["Stock category"] = skus["WBS"].map(STOCK_CATEGORY).fillna(OTHER_STOCK)
    skus["With variance"] = skus["Absolute variance"] > 0
    skus["With Not Justified variance"] = skus["Not Justified variance"] > 0
    return skus.sort_values(keys, kind="mergesort").reset_index(drop=True)


def accuracy_rows(
    groups: list[tuple[str, pd.DataFrame, float | None]], tolerance: float
) -> pd.DataFrame:
    rows = []
    for label, part, value in groups:
        not_justified = part[part["Status"] == NOT_JUSTIFIED]
        block = _variance_block(not_justified)
        variance = _ratio(block["Absolute"], value) if value is not None else None
        rows.append(
            {
                "Category": label,
                "Total inventory value": value,
                "Not Justified lines": len(not_justified),
                **block,
                "Inventory variance": variance,
                "Inventory accuracy": 1 - variance if variance is not None else None,
                "Within tolerance": (
                    "" if variance is None else ("Yes" if variance <= tolerance else "No")
                ),
            }
        )
    return pd.DataFrame(rows)


class CountVariance(Analysis):
    key = "count_variance"
    title = "Physical inventory variance investigation"
    version = "1.1.0"
    description = (
        "Justification of the stock variances posted after a physical inventory count: "
        "positive and negative variances by status, plant, root cause and required action, "
        "and the inventory accuracy (Variance Management SOP) when the final closing stock "
        "is given."
    )
    inputs = (
        InputSpec("variance_lines", "gl_variance_lines", "Variance lines with their investigation"),
        InputSpec(
            "closing",
            "final_closing_by_wbs",
            "Final closing stock per item and WBS (for inventory accuracy)",
            required=False,
        ),
        InputSpec(
            "programmes",
            "rbc_previous_report",
            'RBC report data, for programme names ("CPDS Report")',
            required=False,
        ),
    )
    Parameters = Parameters

    def compute(self, data: dict[str, pd.DataFrame], params: BaseModel) -> AnalysisResult:
        params = _params(params)
        lines = prepare_lines(data["variance_lines"])
        closing = data.get("closing")
        values: pd.DataFrame | None = None
        if closing is not None:
            values = pd.DataFrame(
                {
                    "Plant": plant_code(closing["Plant"]).astype(str),
                    "Material": material_code(closing["Material"]).astype(str),
                    "WBS": _text(closing["WBS"]).replace("", NO_WBS),
                    "Value": closing["Final Value"].astype(float).fillna(0.0),
                    "Plant Name": _text(closing["Plant Name"]),
                }
            )
            values = values[values["Material"] != ""]
            values["Stock category"] = values["WBS"].map(STOCK_CATEGORY).fillna(OTHER_STOCK)

        totals = _variance_block(lines)
        skus = sku_accuracy(lines, values) if values is not None else None
        main = headline(lines)
        plants = by_plant(lines)
        causes = by_group(lines, "Root cause")
        actions = by_group(lines, "Required action")
        has_causes = (lines["Root cause"] != NOT_GIVEN).any()
        has_actions = (lines["Required action"] != NOT_GIVEN).any()
        # Their variance is the opposite of the amount moved to retained earnings.
        retained = lines[lines["Retained earnings"]].copy()
        moved = -retained["Retained earnings amount"]
        retained_block = {
            "Lines": len(retained),
            "Positive": float(moved.clip(lower=0.0).sum()),
            "Negative": float(moved.clip(upper=0.0).sum()),
        }
        retained_block["Net"] = retained_block["Positive"] + retained_block["Negative"]
        justified_lines = int((lines["Status"] == JUSTIFIED).sum())
        not_justified = lines[lines["Status"] == NOT_JUSTIFIED]

        # Inventory accuracy (needs the final closing stock).
        total_value = float(values["Value"].sum()) if values is not None else None
        category_groups: list[tuple[str, pd.DataFrame, float | None]] = [
            ("All stock", lines, total_value)
        ]
        for category in ("Program stock", "RMS-own stock", OTHER_STOCK):
            part = lines[lines["Stock category"] == category]
            value = (
                float(values.loc[values["Stock category"] == category, "Value"].sum())
                if values is not None
                else None
            )
            if len(part) or (value is not None and value != 0):
                category_groups.append((category, part, value))
                if category == "Program stock" and "programmes" in data and values is not None:
                    category_groups += self._programme_groups(
                        data["programmes"], part, values[values["Stock category"] == category]
                    )
        by_category = accuracy_rows(category_groups, params.tolerance)

        plant_groups: list[tuple[str, pd.DataFrame, float | None]] = []
        plants_with_open = sorted(set(not_justified["Plant"]))
        for plant in plants_with_open:
            part = lines[lines["Plant"] == plant]
            name = str(part["Plant Name"].iloc[0])
            value = (
                float(values.loc[values["Plant"] == plant, "Value"].sum())
                if values is not None
                else None
            )
            plant_groups.append((name, part, value))
        by_plant_accuracy = accuracy_rows(plant_groups, params.tolerance).rename(
            columns={"Category": "Plant"}
        )
        by_plant_accuracy = by_plant_accuracy.sort_values(
            ["Inventory variance", "Absolute", "Plant"],
            ascending=[False, False, True],
            kind="mergesort",
            na_position="last",
        ).reset_index(drop=True)

        overall = by_category.iloc[0]
        variance_pct = overall["Inventory variance"]
        accuracy = overall["Inventory accuracy"]
        has_value = variance_pct is not None and not pd.isna(variance_pct)

        checks = [
            Check(
                "status_split",
                "Justified lines + Not Justified lines = all lines",
                expected=len(lines),
                actual=float(main["Lines"].iloc[1] + main["Lines"].iloc[2]),
                tolerance=0,
            ),
            Check(
                "absolute_split",
                "Justified + Not Justified absolute variance = total absolute variance",
                expected=totals["Absolute"],
                actual=float(main["Absolute"].iloc[1] + main["Absolute"].iloc[2]),
            ),
            Check(
                "positive_negative",
                "Positive + negative variance = net of all lines",
                expected=float(lines["Variance"].sum()),
                actual=totals["Positive"] + totals["Negative"],
            ),
            Check(
                "sign",
                "Stock variance = minus the amount on every line (lines that differ)",
                expected=0,
                actual=float(((lines["Variance"] + lines["Amount"]).abs() > 0.01).sum()),
                tolerance=0,
                description="A positive variance is stock found above the SAP quantity.",
            ),
            Check(
                "plants",
                "Justification by plant adds up to all lines",
                expected=len(lines),
                actual=float(plants["Lines"].sum()),
                tolerance=0,
            ),
            Check(
                "plant_value",
                "Justified and Not Justified value by plant add up to the absolute variance",
                expected=totals["Absolute"],
                actual=float(plants["Justified value"].sum() + plants["Not Justified value"].sum()),
            ),
        ]
        if values is not None:
            categories = by_category[
                by_category["Category"].isin(["Program stock", "RMS-own stock", OTHER_STOCK])
            ]
            checks.append(
                Check(
                    "category_value",
                    "Inventory value by stock category adds up to the total inventory value",
                    expected=float(total_value or 0),
                    actual=float(categories["Total inventory value"].sum()),
                )
            )

        kpis = [
            Kpi(label="Variance lines", value=len(lines), format="integer"),
            Kpi(
                label="Justified lines",
                value=_ratio(justified_lines, len(lines)),
                format="percent",
                note=f"{justified_lines:,} of {len(lines):,}",
            ),
            Kpi(label="Not Justified lines", value=len(not_justified), format="integer"),
            Kpi(label="Absolute variance", value=totals["Absolute"], format="money", unit="RWF"),
            Kpi(
                label="Not Justified absolute variance",
                value=float(not_justified["Absolute"].sum()),
                format="money",
                unit="RWF",
            ),
        ]
        if has_value:
            kpis += [
                Kpi(label="Total inventory value", value=total_value, format="money", unit="RWF"),
                Kpi(
                    label="Inventory variance",
                    value=float(variance_pct),
                    format="percent",
                    note=f"tolerance {params.tolerance:.1%}",
                ),
                Kpi(label="Inventory accuracy", value=float(accuracy), format="percent"),
            ]

        notes = []
        if not has_value:
            notes.append(
                "Inventory accuracy needs the final closing stock per item and WBS; it was not "
                "given for this run."
            )
        if not has_causes:
            notes.append("The file has no root cause per line; the root cause table is empty.")
        if not has_actions:
            notes.append("The file has no required action per line; the action table is empty.")

        money = "money"
        variance_columns = [
            Column(key="Positive", label="Positive (RWF)", format=money),
            Column(key="Negative", label="Negative (RWF)", format=money),
            Column(key="Absolute", label="Absolute (RWF)", format=money),
        ]
        accuracy_columns = [
            Column(key="Total inventory value", label="Inventory value (RWF)", format=money),
            Column(key="Not Justified lines", label="Not Justified lines", format="integer"),
            *variance_columns,
            Column(key="Inventory variance", label="Inventory variance", format="percent"),
            Column(key="Inventory accuracy", label="Inventory accuracy", format="percent"),
        ]
        subtitle = f"Physical inventory count of {params.count_date:%d %B %Y} · RWF"
        tables = [
            Table(
                id="headline",
                title="Headline results",
                columns=[
                    Column(key="Category", label="Category"),
                    Column(key="Lines", label="Lines", format="integer"),
                    Column(key="% of lines", label="% of lines", format="percent"),
                    *variance_columns,
                    Column(
                        key="% of absolute value", label="% of absolute value", format="percent"
                    ),
                ],
                rows=rows_of(main),
            ),
            Table(
                id="by-plant",
                title="Justification by plant",
                columns=[
                    Column(key="Plant Name", label="Plant"),
                    Column(key="Lines", label="Lines", format="integer"),
                    Column(key="Justified lines", label="Justified lines", format="integer"),
                    Column(
                        key="Not Justified lines", label="Not Justified lines", format="integer"
                    ),
                    Column(key="Justified value", label="Justified value (RWF)", format=money),
                    Column(
                        key="Not Justified value", label="Not Justified value (RWF)", format=money
                    ),
                    Column(
                        key="Justified % of value", label="Justified % of value", format="percent"
                    ),
                ],
                rows=rows_of(plants),
            ),
        ]
        for table_id, title, frame, column in (
            ("root-causes", "Root causes", causes, "Root cause"),
            ("actions", "Required actions", actions, "Required action"),
        ):
            tables.append(
                Table(
                    id=table_id,
                    title=title,
                    columns=[
                        Column(key=column, label=column),
                        Column(key="Lines", label="Lines", format="integer"),
                        Column(key="Justified lines", label="Justified", format="integer"),
                        Column(key="Not Justified lines", label="Not Justified", format="integer"),
                        *variance_columns,
                        Column(
                            key="% of absolute value", label="% of absolute value", format="percent"
                        ),
                    ],
                    rows=rows_of(frame),
                )
            )
        tables += [
            Table(
                id="by-category",
                title="Inventory accuracy by stock category",
                columns=[Column(key="Category", label="Stock category"), *accuracy_columns],
                rows=rows_of(by_category),
            ),
            Table(
                id="plant-accuracy",
                title="Inventory accuracy of the plants with Not Justified lines",
                columns=[Column(key="Plant", label="Plant"), *accuracy_columns],
                rows=rows_of(by_plant_accuracy),
                note="All other plants have no Not Justified lines (100% accuracy).",
            ),
            Table(
                id="lines",
                title="Detailed variance report",
                columns=[
                    Column(key="Plant Name", label="Plant"),
                    Column(key="Material", label="Material"),
                    Column(key="Material Description", label="Description"),
                    Column(key="WBS", label="WBS"),
                    Column(key="Variance", label="Variance (RWF)", format=money),
                    Column(key="Status", label="Status"),
                    Column(key="Root cause", label="Root cause"),
                    Column(key="ACTION", label="ACTION"),
                    Column(key="REASON", label="REASON"),
                ],
                rows=rows_of(lines),
                total_rows=len(lines),
                level="detail",
                filters=["Plant Name", "Status", "WBS", "Root cause"],
                searchable=["Material", "Material Description", "ACTION", "REASON"],
            ),
        ]
        charts = [
            Chart(
                id="plant-chart",
                title="Absolute variance by plant: Justified and Not Justified (RWF)",
                type="stacked-bar",
                table="by-plant",
                category="Plant Name",
                series=[
                    Series(name="Justified", field="Justified value"),
                    Series(name="Not Justified", field="Not Justified value"),
                ],
                format=money,
                limit=15,
            )
        ]
        if has_causes:
            charts.append(
                Chart(
                    id="cause-chart",
                    title="Absolute variance by root cause (RWF)",
                    type="bar",
                    table="root-causes",
                    category="Root cause",
                    series=[Series(name="Absolute", field="Absolute")],
                    format=money,
                )
            )
        dashboard = Dashboard(
            title="Variance investigation report",
            subtitle=subtitle,
            kpis=kpis,
            charts=charts,
            tables=tables,
            checks=[c.out() for c in checks],
            notes=notes,
        )
        return AnalysisResult(
            tables={
                "lines": lines,
                "headline": main,
                "by_plant": plants,
                "root_causes": causes,
                "actions": actions,
                "by_category": by_category,
                "plant_accuracy": by_plant_accuracy,
                "retained": retained,
                **({"sku_accuracy": skus} if skus is not None else {}),
            },
            metrics=kpis,
            checks=checks,
            dashboard=dashboard,
            extras={
                "subtitle": subtitle,
                "retained": retained_block,
                "has_causes": bool(has_causes),
                "has_actions": bool(has_actions),
                "notes": notes,
                "total_value": total_value,
                "plants": int(lines["Plant"].nunique()),
            },
        )

    @staticmethod
    def _programme_groups(
        programmes: pd.DataFrame, lines: pd.DataFrame, values: pd.DataFrame
    ) -> list[tuple[str, pd.DataFrame, float | None]]:
        """Programme stock split by RBC programme (category of each material)."""
        names = pd.DataFrame(
            {
                "Material": material_code(programmes["Material"]).astype(str),
                "Category": programmes["Category"].map(normalise_category),
            }
        )
        names = names[names["Category"] != ""]
        category = (
            names.groupby(["Material", "Category"])
            .size()
            .reset_index(name="n")
            .sort_values(["Material", "n", "Category"], ascending=[True, False, True])
            .drop_duplicates("Material")
            .set_index("Material")["Category"]
        )
        unknown = "Programme not known"
        tagged_lines = lines.assign(Programme=lines["Material"].map(category).fillna(unknown))
        tagged_values = values.assign(Programme=values["Material"].map(category).fillna(unknown))
        found = set(tagged_lines["Programme"]) | set(tagged_values["Programme"])
        order = [p for p in PROGRAMMES if p in found] + sorted(found - set(PROGRAMMES))
        return [
            (
                f"  {programme}",
                tagged_lines[tagged_lines["Programme"] == programme],
                float(tagged_values.loc[tagged_values["Programme"] == programme, "Value"].sum()),
            )
            for programme in order
        ]

    def reports(
        self, result: AnalysisResult, params: BaseModel, templates: Templates
    ) -> list[ReportFile]:
        params = _params(params)
        t = result.tables
        extras: dict[str, Any] = result.extras
        money: dict[str, ValueFormat] = {
            "Positive": "money",
            "Negative": "money",
            "Absolute": "money",
            "% of lines": "percent",
            "% of absolute value": "percent",
            "Lines": "integer",
            "Justified lines": "integer",
            "Not Justified lines": "integer",
            "Justified value": "money",
            "Not Justified value": "money",
            "Justified % of value": "percent",
            "Total inventory value": "money",
            "Inventory variance": "percent",
            "Inventory accuracy": "percent",
        }
        headline_block = TableBlock("Headline results", t["headline"], money)
        plant_block = TableBlock(
            "Justification by plant",
            t["by_plant"].drop(columns=["Plant"]).rename(columns={"Plant Name": "Plant"}),
            money,
            total_row=True,
        )
        cause_block = TableBlock("Root causes", t["root_causes"], money, total_row=True)
        action_block = TableBlock("Required actions", t["actions"], money, total_row=True)
        category_block = TableBlock("Accuracy by stock category", t["by_category"], money)
        plant_accuracy = TableBlock("Accuracy by plant", t["plant_accuracy"], money)
        detail_columns = [
            "Plant",
            "Plant Name",
            "Material",
            "Material Description",
            "WBS",
            "G/L Account",
            "Document Number",
            "Posting Date",
            "Amount",
            "Variance",
            "Final Validation Status",
            "Status",
            "Root cause",
            "Required action",
            "ACTION",
            "REASON",
            "Retained earnings amount",
        ]
        detail = TableBlock(
            "Detailed Variance Report",
            t["lines"][detail_columns],
            {"Amount": "money", "Variance": "money", "Retained earnings amount": "money"},
            total_row=True,
        )

        main = t["headline"].set_index("Category")
        total_lines = int(main["Lines"].iloc[0])
        justified = main.loc[JUSTIFIED]
        open_ = main.loc[NOT_JUSTIFIED]
        retained = extras["retained"]
        findings = [
            f"Justification. {int(justified['Lines']):,} of {total_lines:,} lines "
            f"({justified['% of lines']:.1%}) are justified, covering "
            f"{justified['% of absolute value']:.1%} of absolute variance value. "
            f"{int(open_['Lines']):,} lines remain Not Justified, with an absolute variance of "
            f"RWF {open_['Absolute']:,.0f}.",
        ]
        category = t["by_category"].set_index("Category")
        if extras["total_value"] is not None:
            overall = category.loc["All stock"]
            within = overall["Inventory variance"] <= params.tolerance
            findings.append(
                f"Inventory accuracy. The Not Justified variance is "
                f"{overall['Inventory variance']:.2%} of the total inventory value in system "
                f"(RWF {extras['total_value']:,.0f}), "
                + ("within" if within else "above")
                + f" the {params.tolerance:.1%} tolerance. Inventory accuracy is "
                f"{overall['Inventory accuracy']:.2%}."
            )
            parts = [
                f"{name}: {category.loc[name, 'Inventory accuracy']:.2%}"
                for name in ("RMS-own stock", "Program stock")
                if name in category.index and not pd.isna(category.loc[name, "Inventory accuracy"])
            ]
            if parts:
                findings.append("Stock categories. Inventory accuracy " + "; ".join(parts) + ".")
        if retained["Lines"]:
            findings.append(
                f"Retained earnings. {retained['Lines']:,} historical lines are proposed for "
                f"transfer to retained earnings: positive variance RWF "
                f"{retained['Positive']:,.0f}, negative variance RWF "
                f"({abs(retained['Negative']):,.0f}), net RWF {retained['Net']:,.0f}."
            )

        sections = [
            Section(
                "Introduction",
                paragraphs=[
                    f"Every stock-adjustment line posted in SAP after the physical inventory count "
                    f"of {params.count_date:%d %B %Y} was examined: {total_lines:,} lines across "
                    f"{extras['plants']} plants. A positive variance is physical stock above the "
                    "SAP quantity and a negative variance is physical stock below the SAP "
                    "quantity; the two are never offset against each other. Each line has a "
                    "final status of Justified or Not Justified.",
                ],
                tables=[headline_block],
            ),
            Section("Key findings", bullets=findings),
            Section(
                "Justification by plant",
                paragraphs=[
                    "For each plant: the number of variance lines and how much absolute "
                    "variance value was justified."
                ],
                tables=[plant_block],
                charts=[
                    ChartBlock(
                        "Absolute variance by plant (RWF)",
                        [str(p) for p in t["by_plant"]["Plant Name"].head(12)],
                        {
                            "Justified": [
                                float(v) for v in t["by_plant"]["Justified value"].head(12)
                            ],
                            "Not Justified": [
                                float(v) for v in t["by_plant"]["Not Justified value"].head(12)
                            ],
                        },
                    )
                ],
            ),
        ]
        variance_tables = []
        if extras["has_causes"]:
            variance_tables.append(cause_block)
        if extras["has_actions"]:
            variance_tables.append(action_block)
        sections.append(
            Section(
                "Variance analysis",
                paragraphs=[
                    "Each variance line has one root cause and one required action, taken from "
                    "its ACTION and REASON."
                    if variance_tables
                    else "The variance file has no root cause or required action per line."
                ],
                tables=variance_tables,
            )
        )
        sections.append(
            Section(
                "Inventory accuracy after justification",
                paragraphs=[
                    "Inventory variance (%) = Σ |Not Justified variance (RWF)| ÷ total inventory "
                    f"value in system (RWF) {TIMES} 100. Inventory accuracy (%) = 100% {MINUS} "
                    "inventory variance (%). The tolerable inventory variance is "
                    f"{params.tolerance:.1%}, "
                    f"so inventory accuracy of at least {1 - params.tolerance:.1%} is acceptable.",
                    *[str(n) for n in extras["notes"] if "closing stock" in str(n)],
                ],
                tables=[category_block, plant_accuracy],
            )
        )
        document = ReportDocument(
            title="Variance investigation report",
            subtitle=f"Physical inventory count of {params.count_date:%d %B %Y}",
            date_text=f"{params.count_date:%d %B %Y}",
            sections=sections,
            checks=check_lines(result.checks),
        )
        stamp = f"{params.count_date:%Y-%m-%d}"
        name = f"Variance_Investigation_Report_{stamp}"
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
                    [
                        headline_block,
                        plant_block,
                        cause_block,
                        action_block,
                        category_block,
                        plant_accuracy,
                        detail,
                    ],
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
                        t.get("sku_accuracy"),
                        f"Variance investigation dashboard: PI {params.count_date:%d %B %Y}",
                        document.subtitle,
                        params.tolerance,
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


ANALYSIS = CountVariance()
