"""Final closing stock by WBS element, after the expired stock scrapped at Finance level.

Business rules from the legacy script `w5` (docs/legacy-analysis.md, section 3):
closing stock from the G/L line items of the stock accounts, expired stock
scrapped deducted on its own WBS, value split into RMS-OWN-ESE-RM,
RMS-PRG-FND-CP and "No WBS / other", main WBS and checks per item.

The comparison with counted stock (legacy rules 8 and 9) needs the
reconciliation workbook, whose headers are not known yet; it is not part of
this version.
"""

from datetime import date
from typing import cast

import pandas as pd
from pydantic import BaseModel, Field

from app.analyses.base import Analysis, AnalysisResult, Check, InputSpec
from app.analyses.common.closing import (
    NO_WBS,
    SCRAPPING_MOVEMENT_TYPES,
    final_closing,
    material_code,
    movement_types,
    plant_code,
    plant_names,
)
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

OWN = "RMS-OWN-ESE-RM"
PROGRAMS = "RMS-PRG-FND-CP"
OTHER = "No WBS / other"
SPLIT = [OWN, PROGRAMS, OTHER]

FLAG_NEGATIVE = "Check: negative after scrapping"
FLAG_WBS = "Check: scrapped WBS differs from stock WBS"
FLAG_EXPIRED = "Expired stock removed"
NOT_IN_CLOSING = "Not in closing stock: scrapped at Finance level only"

# Amounts within half a franc are treated as zero (legacy tolerance).
HALF = 0.5


class Parameters(BaseModel):
    period_end: date = Field(
        title="Period end", description="Date of the closing stock, e.g. 30 June 2026."
    )
    scrapping_movement_types: str = Field(
        default=SCRAPPING_MOVEMENT_TYPES,
        title="Scrapping movement types",
        description="MB51 movement types counted as expired stock scrapped (comma-separated).",
    )


def _params(params: BaseModel) -> Parameters:
    if not isinstance(params, Parameters):
        raise TypeError("Parameters of the wrong analysis.")
    return params


def _split_column(wbs: str) -> str:
    return wbs if wbs in (OWN, PROGRAMS) else OTHER


def _main_wbs(group: pd.DataFrame) -> str:
    """The WBS with the largest absolute final value (then value, final qty, qty)."""
    ranked = group.assign(
        _fv=group["Final Value"].abs(),
        _v=group["Closing Value"].abs(),
        _fq=group["Final Qty"].abs(),
        _q=group["Closing Qty"].abs(),
    ).sort_values(
        ["_fv", "_v", "_fq", "_q", "WBS"],
        ascending=[False, False, False, False, True],
        kind="mergesort",
    )
    return str(ranked["WBS"].iloc[0])


def item_table(by_wbs: pd.DataFrame, names: dict[str, str]) -> pd.DataFrame:
    """One line per item (plant + material), with the WBS split and flags."""
    if by_wbs.empty:
        return pd.DataFrame(
            columns=[
                "ID",
                "Plant",
                "Plant Name",
                "Material",
                "Material Description",
                "Closing Qty",
                "Closing Value",
                "Scrapped Qty",
                "Scrapped Value",
                "Final Qty",
                "Final Value",
                *SPLIT,
                "Main WBS",
                "All WBS with balance",
                "WBS count",
                "In closing stock",
                "Flag",
            ]
        )
    work = by_wbs.assign(Split=by_wbs["WBS"].map(_split_column))
    keys = ["Plant", "Material"]
    totals = (
        work.groupby(keys, sort=True)
        .agg(
            **{
                "Material Description": ("Material Description", "first"),
                "Closing Qty": ("Closing Qty", "sum"),
                "Closing Value": ("Closing Value", "sum"),
                "Scrapped Qty": ("Scrapped Qty", "sum"),
                "Scrapped Value": ("Scrapped Value", "sum"),
                "Final Qty": ("Final Qty", "sum"),
                "Final Value": ("Final Value", "sum"),
            }
        )
        .reset_index()
    )
    split = (
        work.pivot_table(
            index=keys, columns="Split", values="Final Value", aggfunc="sum", fill_value=0.0
        )
        .reindex(columns=SPLIT, fill_value=0.0)
        .reset_index()
    )
    split.columns.name = None
    items = totals.merge(split, on=keys, how="left")

    main, balances, counts, negative_wbs = {}, {}, {}, {}
    for (plant, material), group in work.groupby(keys, sort=True):
        key = (str(plant), str(material))
        main[key] = _main_wbs(group)
        with_balance = sorted(group.loc[group["Final Value"].abs() > HALF, "WBS"].astype(str))
        balances[key] = "; ".join(with_balance)
        counts[key] = len(with_balance)
        negative_wbs[key] = bool((group["Final Value"] < -HALF).any())

    pairs = list(zip(items["Plant"].astype(str), items["Material"].astype(str), strict=True))
    items["Main WBS"] = [main[p] for p in pairs]
    items["All WBS with balance"] = [balances[p] for p in pairs]
    items["WBS count"] = [counts[p] for p in pairs]
    in_closing = (items["Closing Qty"].abs() > 0) | (items["Closing Value"].abs() > HALF)
    items["In closing stock"] = in_closing.map({True: "Yes", False: "No"})

    def flag(row: pd.Series, key: tuple[str, str]) -> str:
        if row["Final Qty"] < 0 or row["Final Value"] < -HALF:
            return FLAG_NEGATIVE
        if negative_wbs[key]:
            return FLAG_WBS
        if abs(row["Scrapped Value"]) > HALF or row["Scrapped Qty"] != 0:
            return NOT_IN_CLOSING if row["In closing stock"] == "No" else FLAG_EXPIRED
        return ""

    items["Flag"] = [flag(row, key) for (_, row), key in zip(items.iterrows(), pairs, strict=True)]
    items.insert(0, "ID", items["Plant"].astype(str) + items["Material"].astype(str))
    items.insert(2, "Plant Name", items["Plant"].map(names).fillna(""))
    return items.sort_values(["Plant", "Material"], kind="mergesort").reset_index(drop=True)


def add_counted(
    items: pd.DataFrame, counted: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Counted stock per item, without the expired stock scrapped (legacy w5 rules 8 and 9).

    When an item had expired stock scrapped and its counted quantity covers the
    scrapped quantity, the scrapped quantity and value are also taken off the
    counted stock. Difference after scrapping = counted value excluding expired
    - final closing value.
    """
    count = pd.DataFrame(
        {
            "Plant": plant_code(counted["ValA"]).astype(str),
            "Material": material_code(counted["Material"]).astype(str),
            "Counted Qty": counted["Counted Quantities"].astype(float).fillna(0.0),
            "Counted Value": counted["Counted Value"].astype(float).fillna(0.0),
            "Count Reason": counted["Reasons for differences where Applicable"]
            .astype("string")
            .fillna("")
            .astype(str),
        }
    )
    count = (
        count.groupby(["Plant", "Material"], sort=True)
        .agg(
            **{
                "Counted Qty": ("Counted Qty", "sum"),
                "Counted Value": ("Counted Value", "sum"),
                "Count Reason": ("Count Reason", "first"),
            }
        )
        .reset_index()
    )
    merged = items.merge(count, on=["Plant", "Material"], how="left")
    found = merged["Counted Value"].notna()
    merged[["Counted Qty", "Counted Value"]] = merged[["Counted Qty", "Counted Value"]].fillna(0.0)
    merged["Count Reason"] = merged["Count Reason"].fillna("")
    scrapped = merged["Scrapped Qty"] != 0
    covers = merged["Counted Qty"] >= merged["Scrapped Qty"].abs()
    remove = scrapped & covers
    merged["Counted Qty excl. Expired"] = merged["Counted Qty"].where(
        ~remove, merged["Counted Qty"] + merged["Scrapped Qty"]
    )
    merged["Counted Value excl. Expired"] = merged["Counted Value"].where(
        ~remove, merged["Counted Value"] + merged["Scrapped Value"]
    )
    merged["Difference after Scrapping"] = (
        merged["Counted Value excl. Expired"] - merged["Final Value"]
    )
    summary = {
        "counted": float(merged["Counted Value"].sum()),
        "counted_excl": float(merged["Counted Value excl. Expired"].sum()),
        "removed": float(merged.loc[remove, "Scrapped Value"].sum()),
        "difference": float(merged["Difference after Scrapping"].sum()),
        "items_not_counted": float((~found).sum()),
        "counted_total_in_file": float(count["Counted Value"].sum()),
    }
    return merged, summary


class ClosingStockByWbs(Analysis):
    key = "closing_stock_wbs"
    title = "Closing stock by WBS"
    version = "1.0.0"
    description = (
        "Final closing stock per plant, material and WBS element: closing stock from the "
        "G/L line items of the stock accounts, less the expired stock scrapped at Finance "
        "level on its own WBS. Shows the split between RMS-OWN-ESE-RM, RMS-PRG-FND-CP and "
        "other WBS, and flags items to check."
    )
    inputs = (
        InputSpec("gl_lines", "gl_stock_lines", "G/L line items of the stock accounts"),
        InputSpec("scrapping", "mb51_material_documents", "Expired stock scrapped (MB51 lines)"),
        InputSpec("plants", "ox10_plants", "Plant names (OX10)", required=False),
        InputSpec(
            "counted",
            "closing_vs_counted",
            'Counted stock ("Closing vs Counted branches"), to compare',
            required=False,
        ),
    )
    Parameters = Parameters

    def compute(self, data: dict[str, pd.DataFrame], params: BaseModel) -> AnalysisResult:
        params = _params(params)
        names = plant_names(data.get("plants"))
        stock = final_closing(
            data["gl_lines"], data["scrapping"], movement_types(params.scrapping_movement_types)
        )
        by_wbs = stock.lines.copy()
        by_wbs.insert(1, "Plant Name", by_wbs["Plant"].map(names).fillna(""))
        items = item_table(stock.lines, names)
        counted_summary: dict[str, float] = {}
        if "counted" in data:
            items, counted_summary = add_counted(items, data["counted"])

        closing_value = float(by_wbs["Closing Value"].sum())
        scrapped_value = float(by_wbs["Scrapped Value"].sum())
        final_value = float(by_wbs["Final Value"].sum())

        bridge = pd.DataFrame(
            [
                ["Closing stock (G/L line items)", by_wbs["Closing Qty"].sum(), closing_value],
                ["Expired stock scrapped", by_wbs["Scrapped Qty"].sum(), scrapped_value],
                ["Final closing stock", by_wbs["Final Qty"].sum(), final_value],
            ],
            columns=["Step", "Quantity", "Value (RWF)"],
        )

        by_wbs_total = (
            by_wbs.groupby("WBS", sort=True)
            .agg(
                Items=("Material", "size"),
                **{
                    "Closing Value": ("Closing Value", "sum"),
                    "Scrapped Value": ("Scrapped Value", "sum"),
                    "Final Value": ("Final Value", "sum"),
                },
            )
            .reset_index()
        )
        by_wbs_total["Share"] = by_wbs_total["Final Value"] / final_value if final_value else 0.0
        by_wbs_total = by_wbs_total.sort_values(
            ["Final Value", "WBS"], ascending=[False, True], kind="mergesort"
        ).reset_index(drop=True)

        by_split = pd.DataFrame(
            {
                "WBS": SPLIT,
                "Final Value": [float(items[c].sum()) if not items.empty else 0.0 for c in SPLIT],
            }
        )
        other_wbs = sorted(set(by_wbs["WBS"]) - {OWN, PROGRAMS})

        by_plant = (
            items.groupby(["Plant", "Plant Name"], sort=True)
            .agg(
                Items=("Material", "size"),
                **{
                    "Closing Value": ("Closing Value", "sum"),
                    "Scrapped Value": ("Scrapped Value", "sum"),
                    "Final Value": ("Final Value", "sum"),
                    OWN: (OWN, "sum"),
                    PROGRAMS: (PROGRAMS, "sum"),
                    OTHER: (OTHER, "sum"),
                },
            )
            .reset_index()
        )

        flagged = items[items["Flag"] != ""]
        flag_counts = (
            flagged.groupby("Flag", sort=True)
            .agg(Items=("ID", "size"), **{"Final Value": ("Final Value", "sum")})
            .reset_index()
        )
        scrap_lines = stock.scrap_lines.copy()
        closing_keys = set(
            zip(
                by_wbs.loc[by_wbs["Closing Value"].abs() > HALF, "Plant"],
                by_wbs.loc[by_wbs["Closing Value"].abs() > HALF, "Material"],
                strict=True,
            )
        )
        scrap_lines["In closing stock?"] = [
            "Yes" if (p, m) in closing_keys else "No"
            for p, m in zip(scrap_lines["Plant"], scrap_lines["Material"], strict=True)
        ]
        scrap_view = scrap_lines[
            [
                c
                for c in [
                    "Plant",
                    "Storage Location",
                    "Material",
                    "Material Description",
                    "Batch",
                    "Movement Type",
                    "Movement Type Text",
                    "Posting Date",
                    "Material Document",
                    "WBS",
                    "Quantity",
                    "Value",
                    "In closing stock?",
                ]
                if c in scrap_lines.columns
            ]
        ].rename(columns={"Value": "Amount (RWF)"})

        counts = pd.DataFrame(
            [
                ["Items (plant + material)", len(items)],
                [
                    "Items with expired stock removed",
                    int((items["Scrapped Value"].abs() > HALF).sum()),
                ],
                ["Items with more than one WBS", int((items["WBS count"] > 1).sum())],
                ["Items negative after scrapping", int((items["Flag"] == FLAG_NEGATIVE).sum())],
                ["Items whose scrapping WBS differs", int((items["Flag"] == FLAG_WBS).sum())],
                [
                    "Scrapped items with no closing balance",
                    int((items["In closing stock"] == "No").sum()),
                ],
                ["MB51 lines of other movement types (left out)", stock.scrap_lines_left_out],
                ["G/L lines used", stock.gl_lines_used],
                ["G/L lines without a material (left out)", stock.gl_lines_without_material],
            ],
            columns=["Count", "Number"],
        )

        split_gap = (
            float((items["Final Value"] - items[SPLIT].sum(axis=1)).abs().sum())
            if not items.empty
            else 0.0
        )
        checks = [
            Check(
                "bridge",
                "Closing stock + expired stock scrapped = final closing stock",
                expected=closing_value + scrapped_value,
                actual=final_value,
            ),
            Check(
                "gl_total",
                "Closing stock equals the G/L line items with a material",
                expected=stock.gl_value_used,
                actual=closing_value,
            ),
            Check(
                "scrapping_total",
                "Expired stock deducted equals the scrapping list",
                expected=stock.scrap_value,
                actual=scrapped_value,
            ),
            Check(
                "item_total",
                "Total of the item list equals the total by WBS",
                expected=final_value,
                actual=float(items["Final Value"].sum()),
            ),
            Check(
                "wbs_split",
                "On every item, the WBS split adds up to the final value (sum of gaps)",
                expected=0.0,
                actual=split_gap,
            ),
            Check(
                "wbs_totals",
                "Totals by WBS add up to the final closing stock",
                expected=final_value,
                actual=float(by_wbs_total["Final Value"].sum()),
            ),
        ]

        if counted_summary:
            checks.append(
                Check(
                    "counted_excluding_expired",
                    "Counted value excluding expired = counted value + scrapped value taken off",
                    expected=counted_summary["counted"] + counted_summary["removed"],
                    actual=counted_summary["counted_excl"],
                )
            )
        to_check = int(items["Flag"].isin([FLAG_NEGATIVE, FLAG_WBS]).sum())
        kpis = [
            Kpi(label="Final closing stock", value=final_value, format="money", unit="RWF"),
            Kpi(label="Closing stock (G/L)", value=closing_value, format="money", unit="RWF"),
            Kpi(label="Expired stock scrapped", value=scrapped_value, format="money", unit="RWF"),
            Kpi(label="Items", value=len(items), format="integer"),
            Kpi(label="Items to check", value=to_check, format="integer"),
        ]
        if counted_summary:
            kpis += [
                Kpi(
                    label="Counted value excl. expired",
                    value=counted_summary["counted_excl"],
                    format="money",
                    unit="RWF",
                ),
                Kpi(
                    label="Difference after scrapping",
                    value=counted_summary["difference"],
                    format="money",
                    unit="RWF",
                ),
            ]
        subtitle = f"Closing stock at {params.period_end:%d %B %Y} · RWF"
        notes = []
        if other_wbs and set(other_wbs) != {NO_WBS}:
            listed = ", ".join(w for w in other_wbs if w != NO_WBS)
            notes.append(f'Other WBS elements, shown under "{OTHER}": {listed}.')
        if stock.gl_lines_without_material:
            notes.append(
                f"{stock.gl_lines_without_material} G/L lines without a material "
                f"(RWF {stock.gl_value_without_material:,.0f}) are left out as subtotals."
            )

        money = "money"
        dashboard = Dashboard(
            title=self.title,
            subtitle=subtitle,
            kpis=kpis,
            charts=[
                Chart(
                    id="final-by-wbs-chart",
                    title="Final closing stock by WBS (RWF)",
                    type="bar",
                    table="by-wbs",
                    category="WBS",
                    series=[Series(name="Final value", field="Final Value")],
                    format=money,
                ),
                Chart(
                    id="final-by-plant-chart",
                    title="Final closing stock by plant (RWF)",
                    type="stacked-bar",
                    table="by-plant",
                    category="Plant Name",
                    series=[Series(name=c, field=c) for c in SPLIT],
                    format=money,
                    limit=15,
                ),
            ],
            tables=[
                Table(
                    id="bridge",
                    title="From closing stock to final closing stock",
                    columns=[
                        Column(key="Step", label="Step"),
                        Column(key="Quantity", label="Quantity", format="number"),
                        Column(key="Value (RWF)", label="Value (RWF)", format=money),
                    ],
                    rows=rows_of(bridge),
                ),
                Table(
                    id="by-wbs",
                    title="By WBS element",
                    columns=[
                        Column(key="WBS", label="WBS"),
                        Column(key="Items", label="Items", format="integer"),
                        Column(key="Closing Value", label="Closing (RWF)", format=money),
                        Column(key="Scrapped Value", label="Scrapped (RWF)", format=money),
                        Column(key="Final Value", label="Final (RWF)", format=money),
                        Column(key="Share", label="Share", format="percent"),
                    ],
                    rows=rows_of(by_wbs_total),
                ),
                Table(
                    id="by-plant",
                    title="By plant",
                    columns=[
                        Column(key="Plant", label="Plant"),
                        Column(key="Plant Name", label="Plant name"),
                        Column(key="Items", label="Items", format="integer"),
                        Column(key="Closing Value", label="Closing (RWF)", format=money),
                        Column(key="Scrapped Value", label="Scrapped (RWF)", format=money),
                        Column(key="Final Value", label="Final (RWF)", format=money),
                        *[Column(key=c, label=c, format=money) for c in SPLIT],
                    ],
                    rows=rows_of(by_plant),
                ),
                Table(
                    id="flags",
                    title="Items to review",
                    columns=[
                        Column(key="Flag", label="Flag"),
                        Column(key="Items", label="Items", format="integer"),
                        Column(key="Final Value", label="Final value (RWF)", format=money),
                    ],
                    rows=rows_of(flag_counts),
                ),
                Table(
                    id="items",
                    title="Final closing stock per item",
                    columns=[
                        Column(key="Plant", label="Plant"),
                        Column(key="Plant Name", label="Plant name"),
                        Column(key="Material", label="Material"),
                        Column(key="Material Description", label="Description"),
                        Column(key="Closing Value", label="Closing (RWF)", format=money),
                        Column(key="Scrapped Value", label="Scrapped (RWF)", format=money),
                        Column(key="Final Qty", label="Final qty", format="number"),
                        Column(key="Final Value", label="Final (RWF)", format=money),
                        Column(key="Main WBS", label="Main WBS"),
                        Column(key="Flag", label="Flag"),
                    ],
                    rows=rows_of(items),
                    total_rows=len(items),
                    level="detail",
                    filters=["Plant Name", "Main WBS", "Flag"],
                    searchable=["Material", "Material Description"],
                ),
            ],
            checks=[c.out() for c in checks],
            notes=notes,
        )
        return AnalysisResult(
            tables={
                "items": items,
                "by_wbs_lines": by_wbs,
                "by_wbs": by_wbs_total,
                "by_split": by_split,
                "by_plant": by_plant,
                "bridge": bridge,
                "flags": flag_counts,
                "counts": counts,
                "scrapping": scrap_view,
            },
            metrics=kpis,
            checks=checks,
            dashboard=dashboard,
            extras={"subtitle": subtitle, "notes": notes, "other_wbs": other_wbs},
        )

    def reports(
        self, result: AnalysisResult, params: BaseModel, templates: Templates
    ) -> list[ReportFile]:
        params = _params(params)
        t = result.tables
        money: dict[str, ValueFormat] = {
            "Closing Value": "money",
            "Scrapped Value": "money",
            "Final Value": "money",
            "Counted Qty": "number",
            "Counted Value": "money",
            "Counted Qty excl. Expired": "number",
            "Counted Value excl. Expired": "money",
            "Difference after Scrapping": "money",
            OWN: "money",
            PROGRAMS: "money",
            OTHER: "money",
            "Closing Qty": "number",
            "Scrapped Qty": "number",
            "Final Qty": "number",
        }
        bridge = TableBlock(
            "Closing to final", t["bridge"], {"Quantity": "number", "Value (RWF)": "money"}
        )
        by_wbs = TableBlock(
            "By WBS",
            t["by_wbs"],
            {**money, "Items": "integer", "Share": "percent"},
            total_row=True,
        )
        by_plant = TableBlock(
            "By plant", t["by_plant"], {**money, "Items": "integer"}, total_row=True, max_rows=40
        )
        flags = TableBlock(
            "Items to review", t["flags"], {"Items": "integer", "Final Value": "money"}
        )
        counts = TableBlock("Counts", t["counts"], {"Number": "integer"})
        # No total row: this sheet is read back by the count variance analysis.
        items = TableBlock("Final Closing Stock", t["items"], {**money, "WBS count": "integer"})
        # No total row: this sheet is read back by the count variance analysis.
        lines = TableBlock("Closing by ID and WBS", t["by_wbs_lines"], money)
        scrapping = TableBlock(
            "Expired Scrapped",
            t["scrapping"],
            {"Quantity": "number", "Amount (RWF)": "money"},
            total_row=True,
        )
        kpi = {k.label: float(k.value or 0) for k in result.metrics}
        final = kpi["Final closing stock"]
        split = t["by_split"]
        split_text = [
            f"{wbs}: RWF {value:,.0f} ({value / final:.1%})" if final else f"{wbs}: RWF 0"
            for wbs, value in zip(split["WBS"], split["Final Value"], strict=True)
        ]
        notes = [str(n) for n in cast(list[str], result.extras["notes"])]
        document = ReportDocument(
            title="Final closing stock by WBS",
            subtitle=str(result.extras["subtitle"]),
            date_text=f"{params.period_end:%d %B %Y}",
            sections=[
                Section(
                    "Summary",
                    paragraphs=[
                        f"The closing stock from the G/L line items of the stock accounts is "
                        f"RWF {kpi['Closing stock (G/L)']:,.0f}. Expired stock scrapped at "
                        f"Finance level of RWF {abs(kpi['Expired stock scrapped']):,.0f} is "
                        f"deducted on the WBS shown on each scrapping line, giving a final "
                        f"closing stock of RWF {final:,.0f} across {int(kpi['Items']):,} items.",
                        f"{int(kpi['Items to check']):,} items need a check (negative after "
                        "scrapping, or scrapped on a WBS without stock).",
                        *notes,
                    ],
                    bullets=split_text,
                    tables=[bridge, by_wbs],
                    charts=[
                        ChartBlock(
                            "Final closing stock by WBS (RWF)",
                            [str(w) for w in split["WBS"]],
                            {"Final value": [float(v) for v in split["Final Value"]]},
                        )
                    ],
                ),
                Section("By plant", tables=[by_plant]),
                Section(
                    "Items to review",
                    paragraphs=[
                        "Items are flagged when the final stock is negative after scrapping, "
                        "when expired stock was scrapped on a WBS that holds no stock of the "
                        "item, or when expired stock was removed.",
                    ],
                    tables=[flags, counts],
                ),
                Section(
                    "Method",
                    bullets=[
                        "Closing stock = total of the G/L line items per plant, material and "
                        "WBS element; lines without a material are left out as subtotals.",
                        "Expired stock scrapped (MB51 lines) is deducted on its own WBS and "
                        "never moved to another WBS.",
                        "Final closing stock = closing stock + scrapped (scrapped is negative).",
                        "Main WBS = the WBS with the largest absolute final value.",
                    ],
                ),
            ],
            checks=check_lines(result.checks),
        )
        stamp = f"{params.period_end:%Y-%m-%d}"
        name = f"Closing_Stock_by_WBS_{stamp}"
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
                    [bridge, by_wbs, by_plant, flags, counts, items, lines, scrapping],
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


ANALYSIS = ClosingStockByWbs()
