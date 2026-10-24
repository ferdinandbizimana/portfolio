"""Year-end stock count reconciliation: counted stock against the closing stock in Finance.

Business rules from the legacy script `w3` (docs/legacy-analysis.md, section 1),
on the "Closing vs Counted branches" sheet of the year-end reconciliation:

- the free-text reason of each line is cleaned and classified into a cause by
  ordered keyword rules (first match wins; misspellings match how reasons are
  typed), and causes are grouped into six SAP root-cause themes;
- plants are grouped into sites (Kigali Hub, Kigali HQ, Quarantine Store,
  Zipline, district branches);
- variance = counted value - closing value; direction above / below books at
  +/- 0.5 RWF; counted value should equal counted quantity x unit cost
  (integrity gap above 1 RWF is flagged); a NO VARIANCE reason with a difference
  above 1 RWF is "mislabelled"; materials whose net difference across plants
  is under 5% of the gross are "offsetting" (for example transfers in transit).
"""

from datetime import date

import pandas as pd
from pydantic import BaseModel, Field

from app.analyses.base import Analysis, AnalysisResult, Check, InputSpec
from app.analyses.common.closing import material_code, plant_code, plant_names
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
from app.reporting.slides import build_pptx
from app.reporting.word import build_docx

DASH = "–"  # noqa: RUF001 (en dash, as in the reports)
NO_VARIANCE = "NO VARIANCE"
RECOUNT = "Recount / duplicate count"
OTHER = "Other"

# (cause, test on the upper-case reason), in the order of the legacy script.
CAUSE_RULES: list[tuple[str, tuple[str, ...], str]] = [
    ("Non-medical stock (outside count scope)", ("NON MEDICAL",), "any"),
    ("Moving average price difference", ("MOVING AVERAGE",), "any"),
    (
        "Counted but not posted (EWM difference analyzer / MM)",
        ("GL LEVEL", "DIFF ANALYSER", "NOT POSTED IN ERP"),
        "any",
    ),
    (RECOUNT, ("RECOUNT", "COUNTED TWICE", "COUNTED,ADJ"), "any"),
    (f"Not counted {DASH} quality inspection (QI)", ("QC PLANT", "QUALITY INSPECTION"), "any"),
    (f"Not counted {DASH} blocked stock", ("BLOCKED", "NOT"), "all"),
    (f"Not counted {DASH} stock in transit", ("TRANSIT", "RANSIT"), "any"),
    (
        f"Not counted {DASH} missed bins / locations",
        ("NOT COUNTED", "NOTE COUNTED", "NOT CONTED"),
        "any",
    ),
    ("Scrapping posted after count", ("SCRAP", "SRAPP"), "any"),
    ("Credit notes / vendor returns after count", ("CREDIT NOTE", "RETURN TO VENDOR"), "any"),
    (
        "Sales / distribution posted after count",
        ("SALES", "SOLD", "DISTRIBUT", "DUSTRIBUT", "STO POSTED"),
        "any",
    ),
    ("Goods receipts posted after count", ("RECEIPT", "POSTED IN JULY"), "any"),
    (
        "Adjustments / posting changes after count",
        ("ADJUST", "VARIANCE", "VARAINCE", "BACKADATED", "POSTING CHANGE"),
        "any",
    ),
    ("Other transactions posted after count", ("TRANSACTIONS POSTED AFTER",), "any"),
]

CUT_OFF = "Period-end cut-off breach"
NON_COUNTABLE = "Non-countable stock status (QI / blocked / transit)"
THEMES = {
    "Goods receipts posted after count": CUT_OFF,
    "Sales / distribution posted after count": CUT_OFF,
    "Scrapping posted after count": CUT_OFF,
    "Adjustments / posting changes after count": CUT_OFF,
    "Credit notes / vendor returns after count": CUT_OFF,
    "Other transactions posted after count": CUT_OFF,
    f"Not counted {DASH} quality inspection (QI)": NON_COUNTABLE,
    f"Not counted {DASH} blocked stock": NON_COUNTABLE,
    f"Not counted {DASH} stock in transit": NON_COUNTABLE,
    f"Not counted {DASH} missed bins / locations": "Count execution & warehouse layout",
    RECOUNT: "Count execution & warehouse layout",
    "Counted but not posted (EWM difference analyzer / MM)": (
        f"EWM{DASH}MM integration / posting failure"
    ),
    "Moving average price difference": "Valuation & master data",
    "Non-medical stock (outside count scope)": "Count scope (non-medical)",
}
NO_THEME = "No variance"

SITES = {
    "7000": f"Kigali Hub (EWM{DASH}MM)",
    "1000": f"Kigali HQ (EWM{DASH}MM)",
    "9900": "Quarantine Store (QI)",
    "1002": "Zipline",
}
BRANCHES = "District branches (MM)"

ABOVE, BELOW, LEVEL = "Count above books", "Count below books", "No value difference"
HALF, ONE = 0.5, 1.0


def clean_reason(value: object) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def classify(reason: str) -> str:
    """The cause of a reason (already cleaned), first matching rule wins."""
    upper = reason.upper()
    if upper == NO_VARIANCE:
        return NO_VARIANCE
    for cause, words, mode in CAUSE_RULES:
        hits = [w in upper for w in words]
        if (mode == "all" and all(hits)) or (mode == "any" and any(hits)):
            return cause
    return OTHER


class Parameters(BaseModel):
    count_date: date = Field(
        title="Count date", description="Date of the year-end count, e.g. 30 June 2026."
    )


def _params(params: BaseModel) -> Parameters:
    if not isinstance(params, Parameters):
        raise TypeError("Parameters of the wrong analysis.")
    return params


def _grouped(frame: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    table = (
        frame.groupby(by, sort=True)
        .agg(
            Lines=("Material", "size"),
            Net=("Variance", "sum"),
            Gross=("Abs", "sum"),
            Plants=("Plant", "nunique"),
        )
        .reset_index()
    )
    gross, lines = float(table["Gross"].sum()), float(table["Lines"].sum())
    table["% of gross"] = table["Gross"] / gross if gross else 0.0
    table["% of lines"] = table["Lines"] / lines if lines else 0.0
    return table.sort_values(
        ["Gross", *by], ascending=[False, *[True] * len(by)], kind="mergesort"
    ).reset_index(drop=True)


class StockCountReconciliation(Analysis):
    key = "stock_count_reconciliation"
    title = "Stock count reconciliation"
    version = "1.0.0"
    description = (
        "Counted stock against the closing stock posted in Finance, per plant and material: "
        "differences classified by cause and SAP root-cause theme, by site and plant, with "
        "data integrity checks (counted value against counted quantity times unit cost)."
    )
    inputs = (
        InputSpec(
            "lines",
            "closing_vs_counted",
            'Closing vs counted stock ("Closing vs Counted branches")',
        ),
        InputSpec("plants", "ox10_plants", "Plant names (OX10)", required=False),
    )
    Parameters = Parameters

    def compute(self, data: dict[str, pd.DataFrame], params: BaseModel) -> AnalysisResult:
        params = _params(params)
        raw = data["lines"]
        names = plant_names(data.get("plants"))
        d = pd.DataFrame(
            {
                "Plant": plant_code(raw["ValA"]).astype(str),
                "Material": material_code(raw["Material"]).astype(str),
                "Description": raw["Description"].astype("string").fillna("").astype(str),
                "Closing Qty": raw["Sum of Closing Stock Posted In Finance"]
                .astype(float)
                .fillna(0.0),
                "Closing Value": raw["Sum of Closing Value Posted In Finance"]
                .astype(float)
                .fillna(0.0),
                "Unit Cost": raw["Unit cost"].astype(float),
                "Counted Qty": raw["Counted Quantities"].astype(float).fillna(0.0),
                "Counted Value": raw["Counted Value"].astype(float).fillna(0.0),
                "Variance": raw["Diff Between Counted Value and Closing Value"]
                .astype(float)
                .fillna(0.0),
                "Reason": raw["Reasons for differences where Applicable"].map(clean_reason),
            }
        )
        d = d[(d["Plant"] != "") & (d["Material"] != "")].reset_index(drop=True)
        d.insert(1, "Plant Name", d["Plant"].map(names).fillna(""))
        d.insert(2, "Site", d["Plant"].map(SITES).fillna(BRANCHES))
        d["Cause"] = d["Reason"].map(classify)
        d["Theme"] = d["Cause"].map(THEMES).fillna(NO_THEME)
        d["Qty Difference"] = d["Counted Qty"] - d["Closing Qty"]
        d["Abs"] = d["Variance"].abs()
        d["Direction"] = [
            ABOVE if v > HALF else BELOW if v < -HALF else LEVEL for v in d["Variance"]
        ]
        expected = d["Counted Qty"] * d["Unit Cost"]
        d["Counted Qty x Unit Cost"] = expected.where(d["Unit Cost"].notna(), d["Counted Value"])
        d["Integrity Gap"] = d["Counted Value"] - d["Counted Qty x Unit Cost"]
        d["Integrity Flag"] = ["CHECK" if abs(g) > ONE else "OK" for g in d["Integrity Gap"]]
        d["Qty/Value Mismatch"] = (d["Qty Difference"] == 0) & (d["Abs"] > ONE)

        explained = d[d["Cause"] != NO_VARIANCE].copy()
        mislabelled = d[(d["Cause"] == NO_VARIANCE) & (d["Abs"] > ONE)]
        closing_value = float(d["Closing Value"].sum())
        counted_value = float(d["Counted Value"].sum())
        total = counted_value - closing_value
        net_explained = float(explained["Variance"].sum())
        recount = float(explained.loc[explained["Cause"] == RECOUNT, "Variance"].sum())

        by_theme = _grouped(explained, ["Theme"])
        by_cause = _grouped(explained, ["Cause", "Theme"])
        by_site = _grouped(explained, ["Site"])
        by_plant = _grouped(explained, ["Plant", "Plant Name", "Site"])
        by_direction = _grouped(explained, ["Direction"])
        matrix = explained.pivot_table(
            index=["Plant", "Plant Name"],
            columns="Theme",
            values="Abs",
            aggfunc="sum",
            fill_value=0.0,
        ).reset_index()
        matrix.columns.name = None
        integrity = explained[explained["Integrity Flag"] == "CHECK"].sort_values(
            ["Abs", "Plant", "Material"], ascending=[False, True, True], kind="mergesort"
        )
        materials = (
            explained.groupby("Material", sort=True)
            .agg(
                Description=("Description", "first"),
                Net=("Variance", "sum"),
                Gross=("Abs", "sum"),
                Plants=("Plant", "nunique"),
            )
            .reset_index()
        )
        offsetting = materials[
            (materials["Plants"] > 1) & (materials["Net"].abs() < 0.05 * materials["Gross"])
        ].sort_values(["Gross", "Material"], ascending=[False, True], kind="mergesort")
        top = explained.sort_values(
            ["Abs", "Plant", "Material"], ascending=[False, True, True], kind="mergesort"
        ).head(15)
        summary = pd.DataFrame(
            [
                ["Closing value posted in Finance", closing_value],
                ["Counted value", counted_value],
                ["Total difference (counted - closing)", total],
                [
                    "Difference as % of closing value",
                    total / closing_value if closing_value else 0.0,
                ],
                ["Lines", len(d)],
                ["Lines with a reason other than NO VARIANCE", len(explained)],
                ["Net variance explained by reasons", net_explained],
                ["Gross variance explained by reasons", float(explained["Abs"].sum())],
                ["Unexplained (total - explained)", total - net_explained],
                ["NO VARIANCE lines with a difference above RWF 1", len(mislabelled)],
                [
                    "Lines failing the value integrity check",
                    int((explained["Integrity Flag"] == "CHECK").sum()),
                ],
                ["Recount / duplicate count variance", recount],
                ["Net difference if the recount variance is reversed", total - recount],
                [
                    "Lines with a value difference but no quantity difference",
                    int(explained["Qty/Value Mismatch"].sum()),
                ],
                ["Offsetting materials (net under 5% of gross, several plants)", len(offsetting)],
            ],
            columns=["Measure", "Value"],
        )

        line_gap = float(
            ((d["Variance"] - (d["Counted Value"] - d["Closing Value"])).abs() > ONE).sum()
        )
        checks = [
            Check(
                "total_difference",
                "Total of the line differences = counted value - closing value",
                expected=total,
                actual=float(d["Variance"].sum()),
            ),
            Check(
                "line_difference",
                "Lines whose difference is not counted value - closing value",
                expected=0,
                actual=line_gap,
                tolerance=0,
            ),
            Check(
                "explained_plus_mislabelled",
                "Explained variance + NO VARIANCE lines = total difference",
                expected=total,
                actual=net_explained + float(d.loc[d["Cause"] == NO_VARIANCE, "Variance"].sum()),
            ),
            Check(
                "causes",
                "Variance by cause adds up to the variance explained by reasons",
                expected=net_explained,
                actual=float(by_cause["Net"].sum()),
            ),
            Check(
                "plants",
                "Gross variance by plant adds up to the gross explained",
                expected=float(explained["Abs"].sum()),
                actual=float(by_plant["Gross"].sum()),
            ),
        ]
        kpis = [
            Kpi(label="Closing value (Finance)", value=closing_value, format="money", unit="RWF"),
            Kpi(label="Counted value", value=counted_value, format="money", unit="RWF"),
            Kpi(label="Total difference", value=total, format="money", unit="RWF"),
            Kpi(
                label="Gross variance explained",
                value=float(explained["Abs"].sum()),
                format="money",
                unit="RWF",
            ),
            Kpi(label="Variance lines", value=len(explained), format="integer"),
            Kpi(
                label="Lines to check (integrity)",
                value=int((explained["Integrity Flag"] == "CHECK").sum()),
                format="integer",
            ),
        ]
        subtitle = f"Count of {params.count_date:%d %B %Y} against closing stock in Finance · RWF"
        money = "money"
        group_columns = [
            Column(key="Lines", label="Lines", format="integer"),
            Column(key="Net", label="Net (RWF)", format=money),
            Column(key="Gross", label="Gross (RWF)", format=money),
            Column(key="% of gross", label="% of gross", format="percent"),
        ]
        dashboard = Dashboard(
            title=self.title,
            subtitle=subtitle,
            kpis=kpis,
            charts=[
                Chart(
                    id="theme-chart",
                    title="Gross variance by root-cause theme (RWF)",
                    type="bar",
                    table="by-theme",
                    category="Theme",
                    series=[Series(name="Gross", field="Gross")],
                    format=money,
                ),
                Chart(
                    id="site-chart",
                    title="Gross variance by site (RWF)",
                    type="bar",
                    table="by-site",
                    category="Site",
                    series=[Series(name="Gross", field="Gross")],
                    format=money,
                ),
                Chart(
                    id="plant-chart",
                    title="Gross variance by plant (RWF)",
                    type="bar",
                    table="by-plant",
                    category="Plant Name",
                    series=[Series(name="Gross", field="Gross")],
                    format=money,
                    limit=15,
                ),
            ],
            tables=[
                Table(
                    id="summary",
                    title="Summary",
                    columns=[
                        Column(key="Measure", label="Measure"),
                        Column(key="Value", label="Value", format="number"),
                    ],
                    rows=rows_of(summary),
                ),
                Table(
                    id="by-theme",
                    title="By SAP root-cause theme",
                    columns=[Column(key="Theme", label="Theme"), *group_columns],
                    rows=rows_of(by_theme),
                ),
                Table(
                    id="by-cause",
                    title="By cause",
                    columns=[
                        Column(key="Cause", label="Cause"),
                        Column(key="Theme", label="Theme"),
                        *group_columns,
                    ],
                    rows=rows_of(by_cause),
                ),
                Table(
                    id="by-site",
                    title="By site",
                    columns=[Column(key="Site", label="Site"), *group_columns],
                    rows=rows_of(by_site),
                ),
                Table(
                    id="by-plant",
                    title="By plant",
                    columns=[
                        Column(key="Plant", label="Plant"),
                        Column(key="Plant Name", label="Plant name"),
                        Column(key="Site", label="Site"),
                        *group_columns,
                    ],
                    rows=rows_of(by_plant),
                ),
                Table(
                    id="lines",
                    title="Variance lines",
                    columns=[
                        Column(key="Plant Name", label="Plant"),
                        Column(key="Material", label="Material"),
                        Column(key="Description", label="Description"),
                        Column(key="Closing Qty", label="Closing qty", format="number"),
                        Column(key="Counted Qty", label="Counted qty", format="number"),
                        Column(key="Variance", label="Variance (RWF)", format=money),
                        Column(key="Cause", label="Cause"),
                        Column(key="Theme", label="Theme"),
                        Column(key="Integrity Flag", label="Integrity"),
                        Column(key="Reason", label="Reason"),
                    ],
                    rows=rows_of(explained),
                    total_rows=len(explained),
                    level="detail",
                    filters=["Site", "Plant Name", "Theme", "Cause", "Direction", "Integrity Flag"],
                    searchable=["Material", "Description", "Reason"],
                ),
            ],
            checks=[c.out() for c in checks],
            notes=(
                [f"{len(mislabelled)} lines say NO VARIANCE but differ by more than RWF 1."]
                if len(mislabelled)
                else []
            ),
        )
        return AnalysisResult(
            tables={
                "lines": d,
                "variance_lines": explained,
                "summary": summary,
                "by_theme": by_theme,
                "by_cause": by_cause,
                "by_site": by_site,
                "by_plant": by_plant,
                "by_direction": by_direction,
                "theme_by_plant": matrix,
                "integrity": integrity,
                "mislabelled": mislabelled,
                "offsetting": offsetting,
                "top_lines": top,
            },
            metrics=kpis,
            checks=checks,
            dashboard=dashboard,
            extras={
                "subtitle": subtitle,
                "total": total,
                "closing": closing_value,
                "counted": counted_value,
                "recount": recount,
            },
        )

    def reports(
        self, result: AnalysisResult, params: BaseModel, templates: Templates
    ) -> list[ReportFile]:
        params = _params(params)
        t = result.tables
        group: dict[str, ValueFormat] = {
            "Lines": "integer",
            "Net": "money",
            "Gross": "money",
            "Plants": "integer",
            "% of gross": "percent",
            "% of lines": "percent",
        }
        line_formats: dict[str, ValueFormat] = {
            "Closing Qty": "number",
            "Closing Value": "money",
            "Unit Cost": "money",
            "Counted Qty": "number",
            "Counted Value": "money",
            "Variance": "money",
            "Qty Difference": "number",
            "Abs": "money",
            "Counted Qty x Unit Cost": "money",
            "Integrity Gap": "money",
        }
        line_columns = [
            "Plant",
            "Plant Name",
            "Site",
            "Material",
            "Description",
            "Closing Qty",
            "Counted Qty",
            "Qty Difference",
            "Unit Cost",
            "Closing Value",
            "Counted Value",
            "Variance",
            "Abs",
            "Direction",
            "Cause",
            "Theme",
            "Counted Qty x Unit Cost",
            "Integrity Gap",
            "Integrity Flag",
            "Reason",
        ]
        summary = TableBlock("Summary of the count", t["summary"], {"Value": "number"})
        themes = TableBlock("By theme", t["by_theme"], group, total_row=True)
        causes = TableBlock("By cause", t["by_cause"], group, total_row=True)
        sites = TableBlock("By site", t["by_site"], group, total_row=True)
        plants = TableBlock("By plant", t["by_plant"], group, total_row=True, max_rows=40)
        matrix_frame = t["theme_by_plant"]
        matrix = TableBlock(
            "Theme x Plant",
            matrix_frame,
            {c: "money" for c in matrix_frame.columns if c not in ("Plant", "Plant Name")},
            total_row=True,
        )
        integrity = TableBlock(
            "Data Integrity", t["integrity"][line_columns], line_formats, total_row=True
        )
        offsetting = TableBlock(
            "Offsetting Materials",
            t["offsetting"],
            {"Net": "money", "Gross": "money", "Plants": "integer"},
        )
        top = TableBlock(
            "Largest variances",
            t["top_lines"][
                ["Plant Name", "Description", "Closing Qty", "Counted Qty", "Variance", "Cause"]
            ],
            line_formats,
        )
        lines = TableBlock(
            "Variance Lines", t["variance_lines"][line_columns], line_formats, total_row=True
        )
        extras = result.extras
        total = float(extras["total"])  # type: ignore[arg-type]
        closing = float(extras["closing"])  # type: ignore[arg-type]
        counted = float(extras["counted"])  # type: ignore[arg-type]
        theme_rows = t["by_theme"]
        document = ReportDocument(
            title="Year-end stock count reconciliation",
            subtitle=str(extras["subtitle"]),
            date_text=f"{params.count_date:%d %B %Y}",
            sections=[
                Section(
                    "Summary",
                    paragraphs=[
                        f"The counted stock is RWF {counted:,.0f} against a closing stock of "
                        f"RWF {closing:,.0f} posted in Finance: a difference of RWF {total:,.0f} "
                        f"({total / closing:.3%} of the closing value)."
                        if closing
                        else "",
                        f"{len(t['variance_lines']):,} lines carry a reason other than NO "
                        f"VARIANCE, with a gross variance of RWF "
                        f"{t['variance_lines']['Abs'].sum():,.0f}.",
                    ],
                    bullets=[
                        f"{row['Theme']}: {row['% of gross']:.1%} of the gross variance "
                        f"({int(row['Lines'])} lines)"
                        for _, row in theme_rows.iterrows()
                    ],
                    tables=[summary],
                    charts=[
                        ChartBlock(
                            "Gross variance by theme (RWF)",
                            [str(v) for v in theme_rows["Theme"]],
                            {"Gross": [float(v) for v in theme_rows["Gross"]]},
                        )
                    ],
                ),
                Section("Findings by theme and cause", tables=[themes, causes]),
                Section("Findings by site and plant", tables=[sites, plants]),
                Section("Largest variances", tables=[top]),
                Section(
                    "Data integrity",
                    paragraphs=[
                        f"{len(t['integrity'])} variance lines carry a counted value that is not "
                        "counted quantity x unit cost (gap above RWF 1). For recount lines the "
                        "counted quantity was set back to book but the counted value still "
                        f"holds the original count: RWF {float(extras['recount']):,.0f}."  # type: ignore[arg-type]
                    ],
                ),
                Section(
                    "Method",
                    bullets=[
                        "Variance = counted value - closing value posted in Finance.",
                        "Each reason is classified into one cause by keyword rules, first match "
                        "wins; causes are grouped into SAP root-cause themes.",
                        "Direction: above books when the variance is above RWF 0.5, below "
                        "books when under RWF -0.5.",
                        "Offsetting materials: held in several plants with a net variance under "
                        "5% of the gross variance (for example transfers in transit).",
                    ],
                ),
            ],
            checks=check_lines(result.checks),
        )
        stamp = f"{params.count_date:%Y-%m-%d}"
        name = f"Stock_Count_Reconciliation_{stamp}"
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
                    [summary, themes, causes, sites, plants, matrix, integrity, offsetting, lines],
                    document.checks,
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


ANALYSIS = StockCountReconciliation()
