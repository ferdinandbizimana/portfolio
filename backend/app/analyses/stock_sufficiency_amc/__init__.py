"""Stock sufficiency against average monthly consumption (AMC).

Business rules from the legacy scripts `amc.py`, `amc2.py`, `add_amc.py` (w6,
docs/legacy-analysis.md section 4), the RBC report of June 2026 (sheets AMC
Summary, AMC Analysis, AMC Risk List, No AMC - Monitor) and Ferdinand's answer
of 23 October 2026 on the link to SAP:

- weekly report, one sheet per programme: stock at the RMS central warehouse
  (HQ), RMS branches and SDPs, and the AMC; reading a sheet stops at its next
  block ("STOCK STATUS ..." or a repeated header), and total / header lines are
  skipped;
- RMS stock = HQ + branches; national stock = RMS stock + SDPs; months of stock
  (MOS) = stock / AMC, only when the AMC is above zero;
- status on the national MOS: no AMC -> "No AMC reported"; above max ->
  "Overstock"; at least min -> "Stocked to plan"; at least 3 -> "Understock";
  otherwise "Stock-out risk (<3 MOS)". Min / max: 6 / 12, MCCH 9 / 14;
- weekly product code -> SAP material through ZSTOCKREPORT "NPC CODE"; when no
  code matches, through the description;
- value = stock on the WBS in ZSTOCKREPORT (unrestricted + quality inspection +
  blocked) x unit cost; a material listed under two programmes is valued once
  (under the first); monthly consumption value = value / MOS at RMS; value
  above max = value x min(1, (national MOS - max) / MOS at RMS) when the national
  MOS is above max;
- materials in stock on the WBS that no weekly product maps to are listed to be
  monitored ("No AMC data").
"""

from datetime import date
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from app.analyses.base import Analysis, AnalysisResult, Check, InputSpec
from app.analyses.common.closing import material_code, wbs_code
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

NO_AMC, OVERSTOCK, TO_PLAN = "No AMC reported", "Overstock", "Stocked to plan"
UNDERSTOCK, STOCK_OUT = "Understock", "Stock-out risk (<3 MOS)"
STATUSES = [STOCK_OUT, UNDERSTOCK, TO_PLAN, OVERSTOCK, NO_AMC]
STOCK_OUT_MOS = 3.0
DEFAULT_LEVELS = (6.0, 12.0)
# Programme of each weekly sheet (names as in the RBC report of June 2026) and
# its min / max months of stock.
SHEET_PROGRAMMES: list[tuple[str, str, tuple[float, float]]] = [
    ("ARV", "ARV and Opportunistic Infection", DEFAULT_LEVELS),
    ("HEPATITIS", "Hepatitis", DEFAULT_LEVELS),
    ("VMMC", "VMMC", DEFAULT_LEVELS),
    ("LAB", "Laboratory (HIV and program lab)", DEFAULT_LEVELS),
    ("MALARIA", "MALARIA AND NTD", DEFAULT_LEVELS),
    ("TB", "TB", DEFAULT_LEVELS),
    ("MCCH", "MCCH", (9.0, 14.0)),
]
BY_CODE, BY_DESCRIPTION, NOT_FOUND = "NPC CODE", "Description", "Not found in ZSTOCKREPORT"
RBC_WBS = "RMS-PRG-FND-CP"
MIN_VALUE = 0.5  # RWF; smaller or negative balances are not listed as stock without AMC
DASH = "–"  # noqa: RUF001 (en dash, as in the reports)


def programme_of(sheet: str) -> tuple[str, tuple[float, float]]:
    key = sheet.strip().upper()
    for prefix, programme, levels in SHEET_PROGRAMMES:
        if key.startswith(prefix):
            return programme, levels
    return sheet.strip(), DEFAULT_LEVELS


def _text(value: object) -> str:
    """Cell text with single spaces; blank for empty cells."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):  # type: ignore[call-overload]
        return ""
    return " ".join(str(value).split())


def _norm(value: object) -> str:
    """Upper case, single spaces; blank for empty cells."""
    return _text(value).upper()


def _number(values: pd.Series) -> pd.Series:
    text = values.astype("string").str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(text, errors="coerce").astype(float)


def status_of(national_mos: float | None, minimum: float, maximum: float) -> str:
    if national_mos is None or pd.isna(national_mos):
        return NO_AMC
    if national_mos > maximum:
        return OVERSTOCK
    if national_mos >= minimum:
        return TO_PLAN
    if national_mos >= STOCK_OUT_MOS:
        return UNDERSTOCK
    return STOCK_OUT


def read_weekly(weekly: pd.DataFrame) -> pd.DataFrame:
    """Product lines of every programme sheet, in workbook order."""
    rows: list[dict[str, Any]] = []
    sheets = weekly["Sheet"] if "Sheet" in weekly.columns else pd.Series("", index=weekly.index)
    stopped: set[str] = set()
    for position, (_, row) in enumerate(weekly.iterrows()):
        sheet = str(sheets.iloc[position])
        if sheet in stopped:
            continue
        own_code = row.get("code")
        code = _norm(own_code) or _norm(row["Product code"])
        description = _norm(row["Product description"])
        if description.startswith("STOCK STATUS") or code in ("PRODUCT CODE", "CODE"):
            stopped.add(sheet)  # the next block of the sheet starts here
            continue
        if not code and not description:
            continue
        if code.startswith(("TOTAL", "PRODUCT")) or description.startswith("TOTAL"):
            continue
        programme, (minimum, maximum) = programme_of(sheet)
        rows.append(
            {
                "Program": programme,
                "Sheet": sheet,
                "Product Code": code,
                "Product (weekly report)": _text(row["Product description"]),
                "Pack Size": _text(row.get("Unit of measure (Pack Size)")),
                "RMS HQ Stock": row["RMS central warehouse"],
                "RMS Branches Stock": row["RMS Branches"],
                "SDP Stock": row["SDPs"],
                "AMC": row["AMC"],
                "Min MOS": minimum,
                "Max MOS": maximum,
                "_description": description,
            }
        )
    lines = pd.DataFrame(rows)
    if lines.empty:
        return lines
    for column in ("RMS HQ Stock", "RMS Branches Stock", "SDP Stock", "AMC"):
        lines[column] = _number(lines[column])
    stock = ["RMS HQ Stock", "RMS Branches Stock", "SDP Stock"]
    lines[stock] = lines[stock].fillna(0.0)
    lines["RMS Stock"] = lines["RMS HQ Stock"] + lines["RMS Branches Stock"]
    lines["National Stock"] = lines["RMS Stock"] + lines["SDP Stock"]
    with_amc = lines["AMC"] > 0
    lines["MOS at RMS"] = (lines["RMS Stock"] / lines["AMC"]).where(with_amc)
    lines["MOS National"] = (lines["National Stock"] / lines["AMC"]).where(with_amc)
    lines["Status"] = [
        status_of(m, lo, hi)
        for m, lo, hi in zip(lines["MOS National"], lines["Min MOS"], lines["Max MOS"], strict=True)
    ]
    return lines


def link_materials(lines: pd.DataFrame, stock: pd.DataFrame) -> pd.DataFrame:
    """SAP materials of each weekly product: NPC CODE first, then the description."""
    by_code: dict[str, list[str]] = {}
    by_description: dict[str, list[str]] = {}
    for material, code, description in zip(
        stock["Material"], stock["NPC"], stock["Description"], strict=True
    ):
        if code:
            by_code.setdefault(code, [])
            if material not in by_code[code]:
                by_code[code].append(material)
        if description:
            by_description.setdefault(description, [])
            if material not in by_description[description]:
                by_description[description].append(material)
    found, how = [], []
    for code, description in zip(lines["Product Code"], lines["_description"], strict=True):
        if code in by_code:
            found.append(sorted(by_code[code]))
            how.append(BY_CODE)
        elif description in by_description:
            found.append(sorted(by_description[description]))
            how.append(BY_DESCRIPTION)
        else:
            found.append([])
            how.append(NOT_FOUND)
    lines = lines.copy()
    lines["SAP Materials"] = found
    lines["Linked by"] = how
    return lines


class Parameters(BaseModel):
    report_date: date = Field(
        title="Weekly report date", description="Date of the stock figures, e.g. 29 July 2026."
    )
    wbs: str = Field(
        default=RBC_WBS,
        title="WBS element",
        description="WBS of the programme stock valued in ZSTOCKREPORT.",
    )


def _params(params: BaseModel) -> Parameters:
    if not isinstance(params, Parameters):
        raise TypeError("Parameters of the wrong analysis.")
    return params


class StockSufficiencyAmc(Analysis):
    key = "stock_sufficiency_amc"
    title = "Stock sufficiency against AMC"
    version = "1.0.0"
    description = (
        "Months of stock at RMS and nationally for every programme product of the weekly "
        "stock monitoring report, against its average monthly consumption: status "
        "(stock-out risk, understock, stocked to plan, overstock), value above the maximum "
        "level, and programme stock without AMC to monitor."
    )
    inputs = (
        InputSpec(
            "weekly",
            "weekly_stock_monitoring",
            "Weekly stock monitoring report (all programme sheets)",
            all_sheets=True,
        ),
        InputSpec("stock", "zstockreport", "ZSTOCKREPORT stock on hand (NPC codes, value)"),
        InputSpec(
            "closing",
            "final_closing_by_wbs",
            "Final closing stock by WBS (value at closing instead of ZSTOCKREPORT)",
            required=False,
        ),
    )
    Parameters = Parameters

    def compute(self, data: dict[str, pd.DataFrame], params: BaseModel) -> AnalysisResult:
        params = _params(params)
        raw_stock = data["stock"]
        stock = pd.DataFrame(
            {
                "Material": material_code(raw_stock["Material"]).astype(str),
                "NPC": raw_stock["NPC CODE"].map(_norm),
                "Description": raw_stock["Material Description"].map(_norm),
                "SAP Description": raw_stock["Material Description"]
                .astype("string")
                .fillna("")
                .astype(str),
                "WBS": raw_stock["WBS Element"].astype("string").str.strip().fillna(""),
                "Quantity": raw_stock[["Unrestricted", "Quality Inspection", "Blocked"]]
                .astype(float)
                .fillna(0.0)
                .sum(axis=1),
                "Unit Cost": raw_stock["Unit Cost"].astype(float).fillna(0.0),
            }
        )
        stock = stock[stock["Material"] != ""]
        stock["Value"] = stock["Quantity"] * stock["Unit Cost"]
        closing = data.get("closing")
        if closing is not None:  # value at closing, as in the quarterly RBC report
            stock_value = pd.DataFrame(
                {
                    "Material": material_code(closing["Material"]).astype(str),
                    "WBS": wbs_code(closing["WBS"]),
                    "Quantity": closing["Final Qty"].astype(float).fillna(0.0),
                    "Value": closing["Final Value"].astype(float).fillna(0.0),
                    "SAP Description": closing["Material Description"]
                    .astype("string")
                    .fillna("")
                    .astype(str),
                }
            )
            stock_value = stock_value[stock_value["Material"] != ""]
        else:
            stock_value = stock
        on_wbs = stock_value[stock_value["WBS"] == params.wbs.strip()]
        value_by_material = on_wbs.groupby("Material")["Value"].sum()
        names = (
            pd.concat(
                [
                    stock_value[["Material", "SAP Description"]],
                    stock[["Material", "SAP Description"]],
                ]
            )
            .loc[lambda f: f["SAP Description"] != ""]
            .drop_duplicates("Material")
            .set_index("Material")["SAP Description"]
        )

        lines = link_materials(read_weekly(data["weekly"]), stock)
        counted: set[str] = set()
        values, value_notes = [], []
        for materials in lines["SAP Materials"]:
            fresh = [m for m in materials if m not in counted]
            counted.update(materials)
            values.append(float(sum(value_by_material.get(m, 0.0) for m in fresh)))
            repeated = len(fresh) != len(materials)
            value_notes.append("Value counted under an earlier product line" if repeated else "")
        lines["SAP Material"] = ["; ".join(m) for m in lines["SAP Materials"]]
        lines["SAP Description"] = [
            "; ".join(str(names.get(m, "")) for m in ms) for ms in lines["SAP Materials"]
        ]
        lines["Value (RWF)"] = values
        lines["Value note"] = value_notes
        rms_mos = lines["MOS at RMS"]
        lines["Monthly Consumption Value (RWF)"] = (lines["Value (RWF)"] / rms_mos).where(
            rms_mos > 0
        )
        above = (lines["MOS National"] - lines["Max MOS"]) / rms_mos
        lines["Value Above Max Level (RWF)"] = (lines["Value (RWF)"] * above.clip(upper=1.0)).where(
            (lines["MOS National"] > lines["Max MOS"]) & (rms_mos > 0), 0.0
        )

        programmes = [p for _, p, _ in SHEET_PROGRAMMES if p in set(lines["Program"])] + sorted(
            set(lines["Program"]) - {p for _, p, _ in SHEET_PROGRAMMES}
        )
        summary_rows = []
        for programme in programmes:
            part = lines[lines["Program"] == programme]
            with_amc = part[part["Status"] != NO_AMC]
            below = with_amc[with_amc["MOS National"] < with_amc["Min MOS"]]
            value = float(part["Value (RWF)"].sum())
            monthly = float(part["Monthly Consumption Value (RWF)"].fillna(0.0).sum())
            summary_rows.append(
                {
                    "Program": programme,
                    "Products": len(part),
                    **{status: int((part["Status"] == status).sum()) for status in STATUSES},
                    "% Below Min": len(below) / len(with_amc) if len(with_amc) else None,
                    "Value (RWF)": value,
                    "Monthly Consumption Value (RWF)": monthly,
                    "Months of Stock at RMS (value)": value / monthly if monthly else None,
                    "Value Above Max Level (RWF)": float(part["Value Above Max Level (RWF)"].sum()),
                }
            )
        summary = pd.DataFrame(summary_rows)

        risk = lines[lines["Status"] == STOCK_OUT]
        linked = set().union(*lines["SAP Materials"]) if len(lines) else set()
        unlinked = (
            on_wbs[~on_wbs["Material"].isin(linked)]
            .groupby("Material")
            .agg(Quantity=("Quantity", "sum"), Value=("Value", "sum"))
            .reset_index()
        )
        # In stock: quantity above zero and a value of at least RWF 1 once rounded.
        held = (unlinked["Quantity"] > 0) & (unlinked["Value"] >= MIN_VALUE)
        no_amc = unlinked[held].copy()
        value_left_out = float(unlinked.loc[~held, "Value"].sum())
        no_amc["Material Description"] = no_amc["Material"].map(names).fillna("")
        total_no_amc = float(no_amc["Value"].sum())
        no_amc["Share of No-AMC Value"] = no_amc["Value"] / total_no_amc if total_no_amc else 0.0
        no_amc["Monitoring Flag"] = (
            f"No AMC data {DASH} monitor regularly (risk of expiry, understock or stock-out)"
        )
        no_amc = no_amc.sort_values(["Value", "Material"], ascending=[False, True]).reset_index(
            drop=True
        )
        not_linked = lines[lines["Linked by"] == NOT_FOUND]

        value_once = float(sum(value_by_material.get(m, 0.0) for m in linked))
        checks = [
            Check(
                "status_counts",
                "Products counted by status = products in the weekly report",
                expected=len(lines),
                actual=float(summary[STATUSES].to_numpy().sum()) if len(summary) else 0.0,
                tolerance=0,
            ),
            Check(
                "value_once",
                "Value of the products = value of the linked SAP materials (each once)",
                expected=value_once,
                actual=float(lines["Value (RWF)"].sum()),
            ),
            Check(
                "stock_on_wbs",
                "Linked value + value without AMC + other unlinked lines = stock value on the WBS",
                expected=float(on_wbs["Value"].sum()),
                actual=value_once + total_no_amc + value_left_out,
            ),
        ]
        kpis = [
            Kpi(label="Products", value=len(lines), format="integer"),
            Kpi(label=STOCK_OUT, value=int((lines["Status"] == STOCK_OUT).sum()), format="integer"),
            Kpi(
                label=UNDERSTOCK, value=int((lines["Status"] == UNDERSTOCK).sum()), format="integer"
            ),
            Kpi(label=OVERSTOCK, value=int((lines["Status"] == OVERSTOCK).sum()), format="integer"),
            Kpi(
                label="Value above max level",
                value=float(lines["Value Above Max Level (RWF)"].sum()),
                format="money",
                unit="RWF",
            ),
            Kpi(label="Products not linked to SAP", value=len(not_linked), format="integer"),
        ]
        source = "closing stock" if closing is not None else "ZSTOCKREPORT"
        subtitle = (
            f"Weekly stock monitoring of {params.report_date:%d %B %Y} · {params.wbs} · "
            f"value from {source}"
        )
        analysis_columns = [
            "Program",
            "Product Code",
            "Product (weekly report)",
            "SAP Material",
            "SAP Description",
            "Linked by",
            "Pack Size",
            "RMS HQ Stock",
            "RMS Branches Stock",
            "RMS Stock",
            "SDP Stock",
            "National Stock",
            "AMC",
            "MOS at RMS",
            "MOS National",
            "Min MOS",
            "Max MOS",
            "Status",
            "Value (RWF)",
            "Monthly Consumption Value (RWF)",
            "Value Above Max Level (RWF)",
            "Value note",
        ]
        analysis = lines[analysis_columns] if len(lines) else pd.DataFrame(columns=analysis_columns)
        money, number = "money", "number"
        dashboard = Dashboard(
            title=self.title,
            subtitle=subtitle,
            kpis=kpis,
            charts=[
                Chart(
                    id="status-chart",
                    title="Products by status and programme",
                    type="stacked-bar",
                    table="summary",
                    category="Program",
                    series=[Series(name=s, field=s) for s in STATUSES],
                ),
                Chart(
                    id="above-max-chart",
                    title="Value above max level (RWF)",
                    type="bar",
                    table="summary",
                    category="Program",
                    series=[Series(name="Value above max", field="Value Above Max Level (RWF)")],
                    format=money,
                ),
            ],
            tables=[
                Table(
                    id="summary",
                    title="AMC summary by programme",
                    columns=[
                        Column(key="Program", label="Programme"),
                        Column(key="Products", label="Products", format="integer"),
                        *[Column(key=s, label=s, format="integer") for s in STATUSES],
                        Column(key="% Below Min", label="% below min", format="percent"),
                        Column(key="Value (RWF)", label="Value (RWF)", format=money),
                        Column(
                            key="Value Above Max Level (RWF)",
                            label="Value above max (RWF)",
                            format=money,
                        ),
                    ],
                    rows=rows_of(summary),
                ),
                Table(
                    id="risk",
                    title="Products at risk (below 3 months of stock nationally)",
                    columns=[
                        Column(key="Program", label="Programme"),
                        Column(key="Product (weekly report)", label="Product"),
                        Column(key="RMS Stock", label="RMS stock", format=number),
                        Column(key="SDP Stock", label="SDP stock", format=number),
                        Column(key="AMC", label="AMC", format=number),
                        Column(key="MOS at RMS", label="MOS at RMS", format=number),
                        Column(key="MOS National", label="MOS national", format=number),
                    ],
                    rows=rows_of(risk),
                    level="detail",
                ),
                Table(
                    id="analysis",
                    title="Stock sufficiency per product",
                    columns=[
                        Column(key="Program", label="Programme"),
                        Column(key="Product Code", label="Code"),
                        Column(key="Product (weekly report)", label="Product"),
                        Column(key="SAP Material", label="SAP material"),
                        Column(key="National Stock", label="National stock", format=number),
                        Column(key="AMC", label="AMC", format=number),
                        Column(key="MOS at RMS", label="MOS at RMS", format=number),
                        Column(key="MOS National", label="MOS national", format=number),
                        Column(key="Status", label="Status"),
                        Column(key="Value (RWF)", label="Value (RWF)", format=money),
                    ],
                    rows=rows_of(analysis),
                    total_rows=len(analysis),
                    level="detail",
                    filters=["Program", "Status", "Linked by"],
                    searchable=["Product Code", "Product (weekly report)", "SAP Material"],
                ),
                Table(
                    id="no-amc",
                    title="Programme stock without AMC data (monitor)",
                    columns=[
                        Column(key="Material", label="SAP material"),
                        Column(key="Material Description", label="Description"),
                        Column(key="Quantity", label="Quantity", format=number),
                        Column(key="Value", label="Value (RWF)", format=money),
                    ],
                    rows=rows_of(no_amc),
                    total_rows=len(no_amc),
                    level="detail",
                    searchable=["Material", "Material Description"],
                ),
            ],
            checks=[c.out() for c in checks],
            notes=(
                [
                    f"{len(not_linked)} weekly products have no SAP material with the same NPC "
                    "code or description."
                ]
                if len(not_linked)
                else []
            ),
        )
        return AnalysisResult(
            tables={
                "analysis": analysis,
                "summary": summary,
                "risk": risk[analysis_columns] if len(risk) else risk,
                "no_amc": no_amc,
                "not_linked": not_linked[analysis_columns] if len(not_linked) else not_linked,
            },
            metrics=kpis,
            checks=checks,
            dashboard=dashboard,
            extras={"subtitle": subtitle},
        )

    def reports(
        self, result: AnalysisResult, params: BaseModel, templates: Templates
    ) -> list[ReportFile]:
        params = _params(params)
        t = result.tables
        formats: dict[str, ValueFormat] = {
            "Products": "integer",
            **{s: "integer" for s in STATUSES},
            "% Below Min": "percent",
            "Value (RWF)": "money",
            "Monthly Consumption Value (RWF)": "money",
            "Months of Stock at RMS (value)": "number",
            "Value Above Max Level (RWF)": "money",
            "RMS HQ Stock": "number",
            "RMS Branches Stock": "number",
            "RMS Stock": "number",
            "SDP Stock": "number",
            "National Stock": "number",
            "AMC": "number",
            "MOS at RMS": "number",
            "MOS National": "number",
            "Min MOS": "number",
            "Max MOS": "number",
            "Quantity": "number",
            "Value": "money",
            "Share of No-AMC Value": "percent",
        }
        summary = TableBlock("AMC Summary", t["summary"], formats, total_row=True)
        analysis = TableBlock("AMC Analysis", t["analysis"], formats)
        risk = TableBlock("AMC Risk List", t["risk"], formats)
        no_amc = TableBlock("No AMC - Monitor", t["no_amc"], formats, total_row=True)
        not_linked = TableBlock("Not linked to SAP", t["not_linked"], formats)
        kpi = {k.label: k.value for k in result.metrics}
        document = ReportDocument(
            title="Stock sufficiency against average monthly consumption",
            subtitle=str(result.extras["subtitle"]),
            date_text=f"{params.report_date:%d %B %Y}",
            sections=[
                Section(
                    "Summary",
                    paragraphs=[
                        f"{kpi['Products']} programme products were compared with their "
                        f"average monthly consumption: {kpi[STOCK_OUT]} are below 3 months of "
                        f"stock nationally, {kpi[UNDERSTOCK]} are understocked and "
                        f"{kpi[OVERSTOCK]} are overstocked. The value of stock above the "
                        f"maximum level is RWF {float(kpi['Value above max level'] or 0):,.0f}.",
                    ],
                    tables=[summary],
                    charts=[
                        ChartBlock(
                            "Products by status",
                            [str(p) for p in t["summary"]["Program"]] if len(t["summary"]) else [],
                            {s: [float(v) for v in t["summary"][s]] for s in STATUSES}
                            if len(t["summary"])
                            else {},
                        )
                    ],
                ),
                Section("Products at risk", tables=[risk]),
                Section(
                    "Method",
                    bullets=[
                        "RMS stock = central warehouse + branches; national stock = RMS stock "
                        "+ SDPs; months of stock = stock / AMC.",
                        "Status on national months of stock: overstock above the maximum, "
                        "stocked to plan from the minimum, understock from 3 months, otherwise "
                        "stock-out risk. Minimum / maximum: 6 / 12 months (MCCH 9 / 14).",
                        "Weekly products are linked to SAP materials by NPC code, otherwise by "
                        "description; values are taken on the WBS element from the final "
                        "closing stock when it is given, otherwise from ZSTOCKREPORT "
                        "(quantity x unit cost).",
                    ],
                ),
            ],
            checks=check_lines(result.checks),
        )
        stamp = f"{params.report_date:%Y-%m-%d}"
        name = f"Stock_Sufficiency_AMC_{stamp}"
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
                    [summary, analysis, risk, no_amc, not_linked],
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


ANALYSIS = StockSufficiencyAmc()
