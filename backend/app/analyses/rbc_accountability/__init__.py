"""RBC accountability report: opening and closing stock of the RBC programmes.

Business rules from the legacy script `w6` (docs/legacy-analysis.md, section 4)
and from the RBC report of June 2026 (version 6), with Ferdinand's rule that
the report shows only opening stock, closing stock and the difference,
labelled "Increase" or "Reduction", with percentages. Receipts, issues and
expired stock never appear anywhere in it.

- Opening = closing stock of the previous RBC report (its "CPDS Report" data
  sheet) on the RBC WBS element only; RMS-OWN-ESE-RM stock is not RBC stock.
- Closing = final closing stock on the same WBS after the period-end
  reconciliation: G/L line items of the stock accounts, less the expired stock
  scrapped at Finance level on that WBS (shared rule, see common/closing.py).
- Category (programme) of each item, first match: previous report same plant,
  previous report other plant, previous report other WBS, item category list,
  otherwise CPDS marked for review. Category names are normalised.
"""

from collections import Counter
from datetime import date, timedelta
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field, model_validator

from app.analyses.base import Analysis, AnalysisResult, Check, InputSpec
from app.analyses.common.closing import (
    SCRAPPING_MOVEMENT_TYPES,
    final_closing,
    material_code,
    movement_types,
    plant_code,
    plant_names,
)
from app.analyses.common.programmes import (
    CATEGORY_NAMES,
    DEFAULT_CATEGORY,
    PROGRAMMES,
    normalise_category,
)
from app.analyses.dashboard import Chart, Column, Dashboard, Kpi, Series, Table, rows_of
from app.analyses.rbc_accountability import dashboard_html
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

RBC_WBS = "RMS-PRG-FND-CP"

# Labels as in the RBC report of June 2026 (with an en dash).
DASH = "\u2013"
SOURCE_SAME_PLANT = f"Previous report {DASH} same plant"
SOURCE_OTHER_PLANT = f"Previous report {DASH} other plant"
SOURCE_OTHER_WBS = f"Previous report {DASH} other WBS"
SOURCE_ITEM_LIST = "ITEM Category list"
SOURCE_NEW = f"New item {DASH} assigned CPDS (review)"
SOURCES = [SOURCE_SAME_PLANT, SOURCE_OTHER_PLANT, SOURCE_OTHER_WBS, SOURCE_ITEM_LIST, SOURCE_NEW]

INCREASE, REDUCTION, NO_CHANGE = "Increase", "Reduction", "No change"


def label(difference: float) -> str:
    rounded = round(difference)
    if rounded > 0:
        return INCREASE
    if rounded < 0:
        return REDUCTION
    return NO_CHANGE


def percent(difference: float, opening: float) -> float | None:
    return difference / opening if opening else None


def _period_text(start: date, end: date) -> str:
    if start.year == end.year:
        return f"{start:%B}{DASH}{end:%B %Y}"
    return f"{start:%B %Y}{DASH}{end:%B %Y}"


class Parameters(BaseModel):
    opening_date: date = Field(
        title="Opening date",
        description="Date of the previous report's closing stock, e.g. 31 March 2026.",
    )
    closing_date: date = Field(
        title="Closing date", description="Date of this report's closing stock, e.g. 30 June 2026."
    )
    wbs: str = Field(
        default=RBC_WBS, title="WBS element", description="WBS element of the RBC programmes."
    )
    scrapping_movement_types: str = Field(
        default=SCRAPPING_MOVEMENT_TYPES,
        title="Scrapping movement types",
        description="MB51 movement types counted as expired stock scrapped (comma-separated).",
    )

    @model_validator(mode="after")
    def _dates_in_order(self) -> "Parameters":
        if self.closing_date <= self.opening_date:
            raise ValueError("The closing date must be after the opening date.")
        return self


def _params(params: BaseModel) -> Parameters:
    if not isinstance(params, Parameters):
        raise TypeError("Parameters of the wrong analysis.")
    return params


def _most_common(values: list[str]) -> str:
    counts = Counter(v for v in values if v)
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _lookup(frame: pd.DataFrame, keys: list[str]) -> dict[Any, str]:
    found: dict[Any, str] = {}
    for key, group in frame.groupby(keys, sort=True):
        category = _most_common(list(group["Category"]))
        if category:
            found[key] = category
    return found


def assign_categories(
    lines: pd.DataFrame, previous: pd.DataFrame, items: pd.DataFrame | None, wbs: str
) -> tuple[list[str], list[str]]:
    """Category and its source for each line (plant, material), first match wins."""
    on_wbs = previous[previous["WBS"] == wbs]
    same_plant = _lookup(on_wbs, ["Plant", "Material"])
    other_plant = _lookup(on_wbs, ["Material"])
    other_wbs = _lookup(previous, ["Material"])
    item_list: dict[Any, str] = {}
    if items is not None and not items.empty:
        listed = pd.DataFrame(
            {
                "Material": material_code(items["SAP MATERIAL"]),
                "Category": items["Category"].map(normalise_category),
            }
        )
        item_list = _lookup(listed, ["Material"])

    categories, sources = [], []
    for plant, material in zip(lines["Plant"], lines["Material"], strict=True):
        for table, key, source in (
            (same_plant, (plant, material), SOURCE_SAME_PLANT),
            (other_plant, material, SOURCE_OTHER_PLANT),
            (other_wbs, material, SOURCE_OTHER_WBS),
            (item_list, material, SOURCE_ITEM_LIST),
        ):
            # pandas gives one-key groups as 1-tuples
            found = table.get(key) or table.get((key,))
            if found:
                categories.append(found)
                sources.append(source)
                break
        else:
            categories.append(DEFAULT_CATEGORY)
            sources.append(SOURCE_NEW)
    return categories, sources


def _order(categories: list[str]) -> list[str]:
    known = [p for p in PROGRAMMES if p in categories]
    return known + sorted(set(categories) - set(PROGRAMMES))


def _summary(lines: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    grouped = (
        lines.groupby(by, sort=True)
        .agg(
            **{
                "Opening Value": ("Opening Value", "sum"),
                "Closing Value": ("Closing Value", "sum"),
            }
        )
        .reset_index()
    )
    return _with_difference(grouped)


def _with_difference(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["Difference"] = frame["Closing Value"] - frame["Opening Value"]
    frame["Difference %"] = [
        percent(d, o) for d, o in zip(frame["Difference"], frame["Opening Value"], strict=True)
    ]
    frame["Increase / Reduction"] = frame["Difference"].map(label)
    return frame


def _total_row(frame: pd.DataFrame, first: str) -> pd.DataFrame:
    """The frame with a "Total" line: sums, and the difference recalculated."""
    total: dict[str, object] = {c: None for c in frame.columns}
    total[first] = "Total"
    for column in (
        "Opening Value",
        "Closing Value",
        "Lines in stock",
        "Share of opening",
        "Share of closing",
    ):
        if column in frame.columns:
            total[column] = float(frame[column].sum())
    opening = float(frame["Opening Value"].sum())
    difference = float(frame["Closing Value"].sum()) - opening
    total["Difference"] = difference
    total["Difference %"] = percent(difference, opening)
    total["Increase / Reduction"] = label(difference)
    return pd.concat([frame, pd.DataFrame([total])], ignore_index=True)


class RbcAccountability(Analysis):
    key = "rbc_accountability"
    title = "RBC accountability report"
    version = "1.1.0"
    description = (
        "Opening and closing stock of the RBC programmes (WBS RMS-PRG-FND-CP) by programme, "
        "plant and product, with the difference labelled Increase or Reduction. Opening "
        "comes from the previous RBC report; closing is the reconciled closing stock."
    )
    inputs = (
        InputSpec(
            "previous_report",
            "rbc_previous_report",
            'Previous RBC report, data sheet ("CPDS Report")',
        ),
        InputSpec("gl_lines", "gl_stock_lines", "G/L line items of the stock accounts"),
        InputSpec("scrapping", "mb51_material_documents", "Expired stock scrapped (MB51 lines)"),
        InputSpec("plants", "ox10_plants", "Plant names (OX10)", required=False),
        InputSpec("item_categories", "rbc_item_categories", "Item category list", required=False),
    )
    Parameters = Parameters

    def compute(self, data: dict[str, pd.DataFrame], params: BaseModel) -> AnalysisResult:
        params = _params(params)
        wbs = params.wbs.strip()
        names = plant_names(data.get("plants"))

        raw_previous = data["previous_report"]
        previous = pd.DataFrame(
            {
                "Plant": plant_code(raw_previous["Valuation Area"]),
                "Material": material_code(raw_previous["Material"]),
                "WBS": raw_previous["WBS"].astype("string").str.strip().fillna(""),
                "Category": raw_previous["Category"].map(normalise_category),
                "Description": raw_previous["Material Description"].astype("string").fillna(""),
                "UoM": raw_previous["Base Unit of Measure"].astype("string").fillna(""),
                "Closing Stock": raw_previous["Closing Stock"].astype(float).fillna(0.0),
                "Closing Value": raw_previous["Closing Value"].astype(float).fillna(0.0),
            }
        )
        previous = previous[previous["Material"] != ""]
        # Opening = the previous report's lines on the RBC WBS only: stock on
        # RMS-OWN-ESE-RM is not RBC stock (Ferdinand, 23 October 2026).
        on_wbs = previous[previous["WBS"] == wbs]
        opening = (
            on_wbs.groupby(["Plant", "Material"], sort=True)
            .agg(
                **{
                    "Opening Qty": ("Closing Stock", "sum"),
                    "Opening Value": ("Closing Value", "sum"),
                }
            )
            .reset_index()
        )

        stock = final_closing(
            data["gl_lines"], data["scrapping"], movement_types(params.scrapping_movement_types)
        )
        on_wbs_closing = stock.lines[stock.lines["WBS"] == wbs]
        closing = (
            on_wbs_closing.groupby(["Plant", "Material"], sort=True)
            .agg(**{"Closing Qty": ("Final Qty", "sum"), "Closing Value": ("Final Value", "sum")})
            .reset_index()
        )

        lines = opening.merge(closing, on=["Plant", "Material"], how="outer")
        amounts = ["Opening Qty", "Opening Value", "Closing Qty", "Closing Value"]
        lines[amounts] = lines[amounts].astype(float).fillna(0.0)
        lines = lines[(lines[amounts].round(6) != 0).any(axis=1)]
        lines = lines.sort_values(["Plant", "Material"], kind="mergesort").reset_index(drop=True)

        descriptions = {
            **dict(zip(previous["Material"], previous["Description"], strict=True)),
            **{
                m: d
                for m, d in zip(
                    stock.lines["Material"], stock.lines["Material Description"], strict=True
                )
                if d
            },
        }
        units = {m: u for m, u in zip(previous["Material"], previous["UoM"], strict=True) if u}
        lines["Material Description"] = lines["Material"].map(descriptions).fillna("")
        lines["Base Unit of Measure"] = lines["Material"].map(units).fillna("")
        lines["Plant Name"] = lines["Plant"].map(names).fillna("")
        categories, sources = assign_categories(lines, previous, data.get("item_categories"), wbs)
        lines["Category"] = categories
        lines["Category Source"] = sources
        lines["Difference Qty"] = lines["Closing Qty"] - lines["Opening Qty"]
        lines = _with_difference(lines)
        order = _order(list(lines["Category"]))
        rank = {c: i for i, c in enumerate(order)}

        opening_total = float(lines["Opening Value"].sum())
        closing_total = float(lines["Closing Value"].sum())
        difference_total = closing_total - opening_total

        # By programme, in report order, with shares and lines in stock.
        by_programme = _summary(lines, ["Category"])
        by_programme["Share of opening"] = (
            by_programme["Opening Value"] / opening_total if opening_total else 0.0
        )
        by_programme["Share of closing"] = (
            by_programme["Closing Value"] / closing_total if closing_total else 0.0
        )
        in_stock = lines[lines["Closing Value"] > 0].groupby("Category").size()
        by_programme["Lines in stock"] = (
            by_programme["Category"].map(in_stock).fillna(0).astype(int)
        )
        by_programme = by_programme.sort_values(
            "Category", key=lambda s: s.map(rank), kind="mergesort"
        ).reset_index(drop=True)
        summary = _total_row(
            by_programme[
                [
                    "Category",
                    "Opening Value",
                    "Closing Value",
                    "Difference",
                    "Difference %",
                    "Increase / Reduction",
                ]
            ],
            "Category",
        )
        metrics = _total_row(by_programme, "Category")

        by_plant = _summary(lines, ["Plant", "Plant Name"])
        by_plant["Share of closing"] = (
            by_plant["Closing Value"] / closing_total if closing_total else 0.0
        )
        by_plant = by_plant.sort_values(
            ["Closing Value", "Plant"], ascending=[False, True], kind="mergesort"
        ).reset_index(drop=True)

        products = _summary(lines, ["Material", "Material Description"])
        products["Category"] = (
            products["Material"]
            .map(
                lines.sort_values(["Closing Value", "Plant"], ascending=[False, True])
                .drop_duplicates("Material")
                .set_index("Material")["Category"]
            )
            .fillna("")
        )
        products["New product"] = [
            "Yes" if o == 0 and c > 0 else ""
            for o, c in zip(products["Opening Value"], products["Closing Value"], strict=True)
        ]
        product_columns = [
            "Material",
            "Material Description",
            "Category",
            "Opening Value",
            "Closing Value",
            "Difference",
            "Difference %",
            "Increase / Reduction",
            "New product",
        ]
        top_products = products.sort_values(
            ["Closing Value", "Material"], ascending=[False, True], kind="mergesort"
        ).head(25)[product_columns]
        top_increases = (
            products[products["Difference"] > 0.5]
            .sort_values(["Difference", "Material"], ascending=[False, True], kind="mergesort")
            .head(15)[product_columns]
        )
        top_reductions = (
            products[products["Difference"] < -0.5]
            .sort_values(["Difference", "Material"], ascending=[True, True], kind="mergesort")
            .head(15)[product_columns]
        )

        # Detailed closing stock list and closing by material (lines with stock).
        held = lines[lines["Closing Value"].abs() > 0.5].copy()
        held["Average Unit Cost"] = [
            v / q if q else None
            for v, q in zip(held["Closing Value"], held["Closing Qty"], strict=True)
        ]
        held["% of RBC Closing"] = held["Closing Value"] / closing_total if closing_total else 0.0
        held["_rank"] = held["Category"].map(rank)
        closing_list = held.sort_values(
            ["_rank", "Closing Value", "Plant", "Material"],
            ascending=[True, False, True, True],
            kind="mergesort",
        )[
            [
                "Category",
                "Plant",
                "Plant Name",
                "Material",
                "Material Description",
                "Base Unit of Measure",
                "Closing Qty",
                "Average Unit Cost",
                "Closing Value",
                "% of RBC Closing",
            ]
        ].rename(
            columns={
                "Category": "Program",
                "Material": "SAP Material",
                "Base Unit of Measure": "UoM",
            }
        )
        closing_list.insert(0, "#", range(1, len(closing_list) + 1))
        by_material = (
            held.groupby(["Category", "Material", "Material Description"], sort=True)
            .agg(
                **{
                    "UoM": ("Base Unit of Measure", "first"),
                    "Plants Holding": ("Plant", "nunique"),
                    "Closing Qty": ("Closing Qty", "sum"),
                    "Closing Value": ("Closing Value", "sum"),
                }
            )
            .reset_index()
        )
        by_material["% of RBC Closing"] = (
            by_material["Closing Value"] / closing_total if closing_total else 0.0
        )
        by_material["_rank"] = by_material["Category"].map(rank)
        by_material = (
            by_material.sort_values(
                ["_rank", "Closing Value", "Material"],
                ascending=[True, False, True],
                kind="mergesort",
            )
            .drop(columns="_rank")
            .rename(columns={"Category": "Program", "Material": "SAP Material"})
            .reset_index(drop=True)
        )

        # Data sheet in the layout of the "CPDS Report": next quarter's opening.
        period_start = params.opening_date + timedelta(days=1)
        data_sheet = pd.DataFrame(
            {
                "Valuation Area": lines["Plant"],
                "Plant Name": lines["Plant Name"],
                "From Date": period_start.isoformat(),
                "To Date": params.closing_date.isoformat(),
                "Material": lines["Material"],
                "Material Description": lines["Material Description"],
                "WBS": wbs,
                "Category": lines["Category"],
                "Category Source": lines["Category Source"],
                "Opening Stock": lines["Opening Qty"],
                "Closing Stock": lines["Closing Qty"],
                "Base Unit of Measure": lines["Base Unit of Measure"],
                "Opening Value": lines["Opening Value"],
                "Closing Value": lines["Closing Value"],
                "Currency": "RWF",
                "Difference Value": lines["Difference"],
                "Increase / Reduction": lines["Increase / Reduction"],
            }
        )

        mapping = (
            lines.groupby("Category Source", sort=False)
            .agg(Lines=("Material", "size"), **{"Closing Value": ("Closing Value", "sum")})
            .reindex(SOURCES)
            .dropna(how="all")
            .reset_index()
        )
        mapping["Lines"] = mapping["Lines"].astype(int)
        names_table = pd.DataFrame(
            {
                "Name in earlier reports": list(CATEGORY_NAMES),
                "Reported under": list(CATEGORY_NAMES.values()),
            }
        )

        previous_total = float(on_wbs["Closing Value"].sum())
        closing_on_wbs = float(on_wbs_closing["Final Value"].sum())
        checks = [
            Check(
                "opening_total",
                "Opening stock equals the previous report's closing stock on the WBS",
                expected=previous_total,
                actual=opening_total,
            ),
            Check(
                "closing_total",
                "Closing stock equals the reconciled closing stock on the WBS",
                expected=closing_on_wbs,
                actual=closing_total,
            ),
            Check(
                "difference",
                "Opening stock + difference = closing stock",
                expected=closing_total,
                actual=opening_total + float(lines["Difference"].sum()),
            ),
            Check(
                "programme_total",
                "Summary by programme adds up to the closing stock",
                expected=closing_total,
                actual=float(by_programme["Closing Value"].sum()),
            ),
            Check(
                "plant_total",
                "Stock by plant adds up to the closing stock",
                expected=closing_total,
                actual=float(by_plant["Closing Value"].sum()),
            ),
            Check(
                "material_total",
                "Closing stock by material adds up to the closing stock",
                expected=closing_total,
                actual=float(by_material["Closing Value"].sum()),
            ),
        ]
        new_items = int((lines["Category Source"] == SOURCE_NEW).sum())
        overall = percent(difference_total, opening_total)
        kpis = [
            Kpi(
                label=f"Opening stock ({params.opening_date:%d %b %Y})",
                value=opening_total,
                format="money",
                unit="RWF",
            ),
            Kpi(
                label=f"Closing stock ({params.closing_date:%d %b %Y})",
                value=closing_total,
                format="money",
                unit="RWF",
            ),
            Kpi(
                label="Difference",
                value=difference_total,
                format="money",
                unit="RWF",
                note=label(difference_total),
            ),
            Kpi(label="Difference %", value=overall, format="percent"),
            Kpi(
                label="Lines in stock",
                value=int((lines["Closing Value"] > 0).sum()),
                format="integer",
            ),
            Kpi(label="New items to review", value=new_items, format="integer"),
        ]
        period = _period_text(period_start, params.closing_date)
        subtitle = f"{wbs} · {period} · RWF"
        position = (
            f"{label(difference_total)} of {abs(overall):.1%}"
            if overall is not None
            else label(difference_total)
        )

        money = "money"
        diff_columns = [
            Column(
                key="Opening Value", label=f"Opening {params.opening_date:%d %b %Y}", format=money
            ),
            Column(
                key="Closing Value", label=f"Closing {params.closing_date:%d %b %Y}", format=money
            ),
            Column(key="Difference", label="Difference (RWF)", format=money),
            Column(key="Difference %", label="Difference %", format="percent"),
            Column(key="Increase / Reduction", label="Increase / Reduction"),
        ]
        dashboard = Dashboard(
            title=f"RBC accountability {DASH} {period}",
            subtitle=subtitle,
            kpis=kpis,
            charts=[
                Chart(
                    id="programme-chart",
                    title="Opening and closing stock by programme (RWF)",
                    type="column",
                    table="by-programme",
                    category="Category",
                    series=[
                        Series(name="Opening", field="Opening Value"),
                        Series(name="Closing", field="Closing Value"),
                    ],
                    format=money,
                ),
                Chart(
                    id="plant-chart",
                    title="Closing stock by plant (RWF)",
                    type="bar",
                    table="by-plant",
                    category="Plant Name",
                    series=[Series(name="Closing", field="Closing Value")],
                    format=money,
                    limit=15,
                ),
            ],
            tables=[
                Table(
                    id="by-programme",
                    title="Summary by programme",
                    columns=[
                        Column(key="Category", label="Programme"),
                        *diff_columns,
                        Column(key="Share of closing", label="Share", format="percent"),
                        Column(key="Lines in stock", label="Lines in stock", format="integer"),
                    ],
                    rows=rows_of(by_programme),
                ),
                Table(
                    id="by-plant",
                    title="By plant",
                    columns=[
                        Column(key="Plant", label="Plant"),
                        Column(key="Plant Name", label="Plant name"),
                        *diff_columns,
                        Column(key="Share of closing", label="Share", format="percent"),
                    ],
                    rows=rows_of(by_plant),
                ),
                Table(
                    id="top-products",
                    title="Top 25 products by closing stock (all plants)",
                    columns=[
                        Column(key="Material", label="Material"),
                        Column(key="Material Description", label="Description"),
                        Column(key="Category", label="Programme"),
                        *diff_columns,
                    ],
                    rows=rows_of(top_products),
                    level="detail",
                ),
                Table(
                    id="lines",
                    title="Stock per plant and product",
                    columns=[
                        Column(key="Category", label="Programme"),
                        Column(key="Plant Name", label="Plant"),
                        Column(key="Material", label="Material"),
                        Column(key="Material Description", label="Description"),
                        *diff_columns,
                        Column(key="Category Source", label="Category source"),
                    ],
                    rows=rows_of(lines),
                    total_rows=len(lines),
                    level="detail",
                    filters=["Category", "Plant Name", "Increase / Reduction"],
                    searchable=["Material", "Material Description"],
                ),
            ],
            checks=[c.out() for c in checks],
            notes=[f"Overall stock position: {position}."]
            + (
                [
                    f"{new_items} items have no category in earlier reports and are shown under "
                    "CPDS for review."
                ]
                if new_items
                else []
            ),
        )
        return AnalysisResult(
            tables={
                "lines": lines,
                "summary": summary,
                "metrics": metrics,
                "by_plant": by_plant,
                "top_products": top_products,
                "top_increases": top_increases,
                "top_reductions": top_reductions,
                "closing_list": closing_list,
                "by_material": by_material,
                "data_sheet": data_sheet,
                "category_sources": mapping,
                "category_names": names_table,
            },
            metrics=kpis,
            checks=checks,
            dashboard=dashboard,
            extras={
                "period": period,
                "subtitle": subtitle,
                "position": position,
                "new_items": new_items,
                "opening_total": opening_total,
                "closing_total": closing_total,
            },
        )

    def reports(
        self, result: AnalysisResult, params: BaseModel, templates: Templates
    ) -> list[ReportFile]:
        params = _params(params)
        t = result.tables
        period = str(result.extras["period"])
        opening_label = f"Opening Value ({params.opening_date:%d %b %Y})"
        closing_label = f"Closing Value ({params.closing_date:%d %b %Y})"
        renamed = {"Opening Value": opening_label, "Closing Value": closing_label}
        diff: dict[str, ValueFormat] = {
            opening_label: "money",
            closing_label: "money",
            "Difference": "money",
            "Difference %": "percent",
            "Share of opening": "percent",
            "Share of closing": "percent",
            "Lines in stock": "integer",
        }

        def block(
            title: str,
            frame: pd.DataFrame,
            extra: dict[str, ValueFormat] | None = None,
            **options: Any,
        ) -> TableBlock:
            return TableBlock(
                title, frame.rename(columns=renamed), {**diff, **(extra or {})}, **options
            )

        summary = block("SUMMARY Report", t["summary"])
        metrics = block("Metrics", t["metrics"])
        by_plant = block("By Plant", t["by_plant"], max_rows=40)
        top = block("Top Products", t["top_products"])
        increases = block("Largest Increases", t["top_increases"])
        reductions = block("Largest Reductions", t["top_reductions"])
        closing_list = TableBlock(
            f"Closing Stock {params.closing_date:%d %b %Y}",
            t["closing_list"],
            {
                "#": "integer",
                "Closing Qty": "number",
                "Average Unit Cost": "money",
                "Closing Value": "money",
                "% of RBC Closing": "percent",
            },
            total_row=True,
        )
        by_material = TableBlock(
            "Closing by Material",
            t["by_material"],
            {
                "Plants Holding": "integer",
                "Closing Qty": "number",
                "Closing Value": "money",
                "% of RBC Closing": "percent",
            },
            total_row=True,
        )
        # No total row on the data sheet: it is read back as next quarter's opening.
        data_sheet = TableBlock(
            "CPDS Report",
            t["data_sheet"],
            {
                "Opening Stock": "number",
                "Closing Stock": "number",
                "Opening Value": "money",
                "Closing Value": "money",
                "Difference Value": "money",
            },
        )
        mapping = TableBlock(
            "Category Mapping",
            t["category_sources"],
            {"Lines": "integer", "Closing Value": "money"},
        )
        names = TableBlock("Category Names", t["category_names"])

        opening_total = float(result.extras["opening_total"])  # type: ignore[arg-type]
        closing_total = float(result.extras["closing_total"])  # type: ignore[arg-type]
        position = str(result.extras["position"])
        programmes = t["summary"][t["summary"]["Category"] != "Total"]
        bullets = [
            f"{row['Category']}: RWF {row['Opening Value']:,.0f} to RWF "
            f"{row['Closing Value']:,.0f}, "
            + (
                f"{row['Increase / Reduction'].lower()} of {abs(row['Difference %']):.1%}"
                if row["Difference %"] is not None and not pd.isna(row["Difference %"])
                else str(row["Increase / Reduction"]).lower()
            )
            for _, row in programmes.iterrows()
        ]
        document = ReportDocument(
            title="RBC accountability report",
            subtitle=f"Stock of the RBC programmes ({params.wbs}), {period}",
            date_text=f"{params.closing_date:%d %B %Y}",
            sections=[
                Section(
                    "Summary",
                    paragraphs=[
                        f"The stock of the RBC programmes was RWF {opening_total:,.0f} on "
                        f"{params.opening_date:%d %B %Y} and RWF {closing_total:,.0f} on "
                        f"{params.closing_date:%d %B %Y}: an overall {position.lower()}.",
                    ],
                    bullets=bullets,
                    tables=[summary],
                    charts=[
                        ChartBlock(
                            "Opening and closing stock by programme (RWF)",
                            [str(c) for c in programmes["Category"]],
                            {
                                "Opening": [float(v) for v in programmes["Opening Value"]],
                                "Closing": [float(v) for v in programmes["Closing Value"]],
                            },
                            kind="column",
                        )
                    ],
                ),
                Section("Stock by programme", tables=[metrics]),
                Section("Stock by plant", tables=[by_plant]),
                Section("Products", tables=[top, increases, reductions]),
                Section(
                    "Method",
                    bullets=[
                        "Opening stock is the closing stock reported in the previous RBC report.",
                        "Closing stock is the reconciled closing stock on the WBS element at "
                        "the closing date.",
                        "Difference = closing stock minus opening stock; it is labelled "
                        "Increase or Reduction, and the percentage is the difference divided "
                        "by the opening stock.",
                        "Each product keeps the programme it had in earlier reports; products "
                        "seen for the first time are shown under CPDS for review.",
                    ],
                ),
            ],
            checks=check_lines(result.checks),
        )
        stamp = f"{params.closing_date:%Y-%m-%d}"
        name = f"RBC_Accountability_Report_{stamp}"
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
                        summary,
                        metrics,
                        by_plant,
                        top,
                        increases,
                        reductions,
                        closing_list,
                        by_material,
                        data_sheet,
                        mapping,
                        names,
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
                        f"RBC accountability: {params.wbs}",
                        f"{params.opening_date:%d %B %Y} to {params.closing_date:%d %B %Y}",
                        f"{params.opening_date:%d %b %Y}",
                        f"{params.closing_date:%d %b %Y}",
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


ANALYSIS = RbcAccountability()
