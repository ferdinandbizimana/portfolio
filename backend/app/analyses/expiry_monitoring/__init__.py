"""Expiry monitoring: two monthly ZSTOCKREPORT snapshots of a period.

Ferdinand's rules of 26 October 2026 (docs/PLAN.md, Decisions):

- a batch has expired when the ZSTOCKREPORT shows its expiry date on or
  before the report date; every expired batch must be blocked and sent to the
  quarantine plant (batches that are not are flagged);
- a period (month, quarter, six months, financial year) compares the
  ZSTOCKREPORT of its opening month with the one of its closing month;
- the batches that were to expire during the period (opening snapshot) end as
  cleared (sold, distributed or donated), expired, or partly both; the value
  projected to expire minus the value that did expire is the value saved;
- distributions (all distribution movement types, 641 included) of batches with
  less than three months of shelf life left are flagged; for a 641, the
  receiving plant's closing stock says whether it issued the batch, still holds
  it or let it expire there;
- batches whose expiry date changed between the two snapshots are flagged;
- MB51 scrapping (551 / 555) gives the days from expiry to scrapping;
- commercial stock is on RMS-OWN WBS elements, programme stock on RMS-PRG.

Batches are matched by plant, material and batch; a batch that moved to another
plant is followed by material and batch for the value saved.
"""

from datetime import date

import pandas as pd
from pydantic import BaseModel, Field, model_validator

from app.analyses.base import Analysis, AnalysisResult, Check, InputSpec
from app.analyses.common.closing import material_code, plant_code, plant_names
from app.analyses.dashboard import Chart, Column, Dashboard, Kpi, Series, Table, rows_of
from app.datasets import parse_dates
from app.reporting.documents import (
    ReportDocument,
    ReportFile,
    Section,
    TableBlock,
    Templates,
    ValueFormat,
    check_lines,
)
from app.reporting.excel import build_workbook
from app.reporting.interactive import check_rows, dashboard_file
from app.reporting.slides import build_pptx
from app.reporting.word import build_docx

DAYS_PER_MONTH = 365.25 / 12
EXPIRED, NO_DATE = "Expired", "No expiry date"
BANDS = [
    EXPIRED,
    "Within 3 months",
    "3 to 6 months",
    "6 to 12 months",
    "More than 12 months",
    NO_DATE,
]
COMMERCIAL, PROGRAMME, OTHER_OWNER = "Commercial (RMS-OWN)", "Programme (RMS-PRG)", "Other WBS"
CLEARED, EXPIRED_OUT, PARTLY = "Cleared", "Expired", "Partly cleared, rest expired"
NOT_RECEIVED = "Not received yet"
AT_RECEIVER_EXPIRED = "Expired at the receiving plant"
AT_RECEIVER_STOCK = "Still in stock at the receiving plant"
AT_RECEIVER_ISSUED = "No longer in stock at the receiving plant"
TRANSFER = "641"
GOODS_RECEIPT = "101"


def band_of(months: float | None) -> str:
    if months is None or pd.isna(months):
        return NO_DATE
    if months <= 0:
        return EXPIRED
    if months <= 3:
        return BANDS[1]
    if months <= 6:
        return BANDS[2]
    if months <= 12:
        return BANDS[3]
    return BANDS[4]


def owner_of(wbs: str) -> str:
    text = wbs.strip().upper()
    if text.startswith("RMS-OWN"):
        return COMMERCIAL
    if text.startswith("RMS-PRG"):
        return PROGRAMME
    return OTHER_OWNER


def _codes(text: str) -> list[str]:
    return [c.strip().upper() for c in text.split(",") if c.strip()]


def _text(values: pd.Series) -> pd.Series:
    return values.astype("string").str.strip().fillna("").astype(str)


class Parameters(BaseModel):
    opening_date: date = Field(
        title="Opening date",
        description="Date of the opening ZSTOCKREPORT, e.g. 31 March 2026.",
    )
    closing_date: date = Field(
        title="Closing date",
        description="Date of the closing ZSTOCKREPORT, e.g. 30 June 2026.",
    )
    quarantine_plants: str = Field(
        default="",
        title="Quarantine plant(s)",
        description="Plant codes where expired stock must be (comma-separated).",
    )
    distribution_types: str = Field(
        default="601, Y01, Z01, X01, 641",
        title="Distribution movement types",
        description="MB51 movement types counted as distribution (comma-separated).",
    )
    scrapping_types: str = Field(
        default="551, 555",
        title="Scrapping movement types",
        description="MB51 movement types counted as expired stock scrapped (comma-separated).",
    )
    short_shelf_life_months: int = Field(
        default=3,
        ge=1,
        title="Short shelf life (months)",
        description="Distributions with less shelf life left than this are flagged.",
    )

    @model_validator(mode="after")
    def _order(self) -> "Parameters":
        if self.closing_date <= self.opening_date:
            raise ValueError("The closing date must be after the opening date.")
        return self


def _params(params: BaseModel) -> Parameters:
    if not isinstance(params, Parameters):
        raise TypeError("Parameters of the wrong analysis.")
    return params


def read_batches(raw: pd.DataFrame, report: date, names: dict[str, str]) -> pd.DataFrame:
    """One row per plant, material and batch of a ZSTOCKREPORT, valued at unit cost."""
    quantity = raw[["Unrestricted", "Quality Inspection", "Blocked"]].astype(float).fillna(0.0)
    cost = raw["Unit Cost"].astype(float).fillna(0.0)
    lines = pd.DataFrame(
        {
            "Plant": plant_code(raw["Plant"]).astype(str),
            "Material": material_code(raw["Material"]).astype(str),
            "Batch": _text(raw["Batch"]),
            "Description": _text(raw["Material Description"]),
            "WBS": _text(raw["WBS Element"]),
            "Material Type": _text(raw["Material Type"]).replace("", "Not given"),
            "Expiry Date": parse_dates(raw["Expiry Date"]),
            "Quantity": quantity.sum(axis=1),
            "Blocked": quantity["Blocked"],
            "Value": quantity.sum(axis=1) * cost,
        }
    )
    lines = lines[(lines["Material"] != "") & (lines["Quantity"] != 0)]
    grouped = (
        lines.sort_values(["Plant", "Material", "Batch", "WBS"], kind="mergesort")
        .groupby(["Plant", "Material", "Batch"], sort=True)
        .agg(
            Description=("Description", "max"),
            WBS=("WBS", "first"),
            **{
                "Material Type": ("Material Type", "first"),
                "Expiry Date": ("Expiry Date", "min"),
                "Quantity": ("Quantity", "sum"),
                "Blocked": ("Blocked", "sum"),
                "Value": ("Value", "sum"),
            },
        )
        .reset_index()
    )
    day = pd.Timestamp(report)
    grouped["Months to Expiry"] = (grouped["Expiry Date"] - day).dt.days / DAYS_PER_MONTH
    grouped["Expiry Band"] = [band_of(m) for m in grouped["Months to Expiry"]]
    grouped["Owner"] = grouped["WBS"].map(owner_of)
    grouped["Plant Name"] = grouped["Plant"].map(names).fillna("")
    grouped["Expiry Month"] = grouped["Expiry Date"].dt.strftime("%Y-%m").fillna("")
    return grouped


def _movements(raw: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Plant": plant_code(raw["Plant"]).astype(str),
            "Material": material_code(raw["Material"]).astype(str),
            "Batch": _text(raw["Batch"]),
            "Movement Type": _text(raw["Movement Type"]).str.upper(),
            "Quantity": raw["Quantity"].astype(float).fillna(0.0),
            "Value": raw["Amt.in Loc.Cur."].astype(float).fillna(0.0),
            "Posting Date": parse_dates(raw["Posting Date"]),
            "Purchase Order": material_code(raw["Purchase order"]).astype(str),
            "Description": _text(raw["Material Description"]),
        }
    )


class ExpiryMonitoring(Analysis):
    key = "expiry_monitoring"
    title = "Expiry monitoring"
    version = "1.0.0"
    description = (
        "Two monthly ZSTOCKREPORTs (opening and closing month of a period): expired batches "
        "per plant, batches due to expire that were cleared or expired, value saved, the "
        "3- and 6-month outlook, expiry date changes, distributions with a short shelf life "
        "and the days from expiry to scrapping."
    )
    inputs = (
        InputSpec("opening", "zstockreport", "ZSTOCKREPORT of the opening month"),
        InputSpec("closing", "zstockreport", "ZSTOCKREPORT of the closing month"),
        InputSpec(
            "movements",
            "mb51_material_documents",
            "Goods movements (MB51) with batches: distributions and scrapping",
            required=False,
        ),
        InputSpec("plants", "ox10_plants", "Plant names (OX10)", required=False),
    )
    Parameters = Parameters

    def compute(self, data: dict[str, pd.DataFrame], params: BaseModel) -> AnalysisResult:
        params = _params(params)
        names = plant_names(data.get("plants"))
        opening = read_batches(data["opening"], params.opening_date, names)
        closing = read_batches(data["closing"], params.closing_date, names)
        quarantine = set(_codes(params.quarantine_plants))

        # Expired at closing, with the blocking and quarantine flags.
        expired = closing[closing["Expiry Band"] == EXPIRED].copy()
        expired["Not Blocked Qty"] = (expired["Quantity"] - expired["Blocked"]).clip(lower=0.0)
        expired["Not Blocked"] = expired["Not Blocked Qty"] > 0
        expired["Outside Quarantine"] = (
            ~expired["Plant"].str.upper().isin(quarantine) if quarantine else False
        )

        # Batches due to expire during the period, and what became of them.
        start, end = pd.Timestamp(params.opening_date), pd.Timestamp(params.closing_date)
        due = opening[(opening["Expiry Date"] > start) & (opening["Expiry Date"] <= end)].copy()
        due["Unit Cost"] = due["Value"] / due["Quantity"]
        by_batch = closing.groupby(["Material", "Batch"])["Quantity"].sum()
        due_total = due.groupby(["Material", "Batch"])["Quantity"].sum()
        # Share of the opening quantity still in stock (expired) at closing, per batch.
        share = (
            pd.concat([by_batch.rename("closing"), due_total.rename("opening")], axis=1)
            .dropna(subset=["opening"])
            .fillna({"closing": 0.0})
        )
        share["Expired Share"] = (share["closing"] / share["opening"]).clip(upper=1.0, lower=0.0)
        keys = list(zip(due["Material"], due["Batch"], strict=True))
        due["Expired Qty"] = [
            q * float(share["Expired Share"].get(k, 0.0))
            for q, k in zip(due["Quantity"], keys, strict=True)
        ]
        due["Expired Value"] = due["Expired Qty"] * due["Unit Cost"]
        due["Cleared Qty"] = due["Quantity"] - due["Expired Qty"]
        due["Cleared Value"] = due["Value"] - due["Expired Value"]
        due["Outcome"] = [
            CLEARED if e <= 1e-9 else EXPIRED_OUT if c <= 1e-9 else PARTLY
            for e, c in zip(due["Expired Qty"], due["Cleared Qty"], strict=True)
        ]
        # Where those batches stand at closing, plant by plant (moved batches included).
        due_keys = set(keys)
        actual = closing[
            [k in due_keys for k in zip(closing["Material"], closing["Batch"], strict=True)]
        ]

        # Expiry dates changed between the two snapshots.
        both = opening.merge(
            closing[["Plant", "Material", "Batch", "Expiry Date", "Quantity", "Value"]],
            on=["Plant", "Material", "Batch"],
            suffixes=(" (opening)", " (closing)"),
        )
        changed = both[
            both["Expiry Date (opening)"].notna()
            & both["Expiry Date (closing)"].notna()
            & (both["Expiry Date (opening)"] != both["Expiry Date (closing)"])
        ].copy()
        changed["Days Changed"] = (
            changed["Expiry Date (closing)"] - changed["Expiry Date (opening)"]
        ).dt.days

        # Movements: distributions with a short shelf life, and scrapping.
        expiry_of: dict[tuple[str, str], pd.Timestamp] = {}
        for frame in (opening, closing):
            for m, b, d in zip(
                frame["Material"], frame["Batch"], frame["Expiry Date"], strict=True
            ):
                if b and pd.notna(d):
                    expiry_of[(m, b)] = d
        distributions = pd.DataFrame()
        scrapping = pd.DataFrame()
        movements = data.get("movements")
        if movements is not None:
            moves = _movements(movements)
            moves["Expiry Date"] = [
                expiry_of.get((m, b), pd.NaT)
                for m, b in zip(moves["Material"], moves["Batch"], strict=True)
            ]
            in_period = moves["Posting Date"].between(start, end) | moves["Posting Date"].isna()
            kinds = set(_codes(params.distribution_types))
            distributions = moves[moves["Movement Type"].isin(kinds) & in_period].copy()
            distributions["Quantity"] = distributions["Quantity"].abs()
            distributions["Value"] = distributions["Value"].abs()
            distributions["Months Left"] = (
                distributions["Expiry Date"] - distributions["Posting Date"]
            ).dt.days / DAYS_PER_MONTH
            distributions["Short Shelf Life"] = (
                distributions["Months Left"] < params.short_shelf_life_months
            )
            receipts = moves[moves["Movement Type"] == GOODS_RECEIPT]
            receiver = {
                (po, m, b): p
                for po, m, b, p in zip(
                    receipts["Purchase Order"],
                    receipts["Material"],
                    receipts["Batch"],
                    receipts["Plant"],
                    strict=True,
                )
                if po
            }
            closing_band = {
                (p, m, b): band
                for p, m, b, band in zip(
                    closing["Plant"],
                    closing["Material"],
                    closing["Batch"],
                    closing["Expiry Band"],
                    strict=True,
                )
            }
            receiving, status = [], []
            for kind, po, m, b in zip(
                distributions["Movement Type"],
                distributions["Purchase Order"],
                distributions["Material"],
                distributions["Batch"],
                strict=True,
            ):
                if kind != TRANSFER:
                    receiving.append("")
                    status.append("")
                    continue
                plant = receiver.get((po, m, b), "")
                receiving.append(plant)
                band = closing_band.get((plant, m, b)) if plant else None
                status.append(
                    NOT_RECEIVED
                    if not plant
                    else AT_RECEIVER_ISSUED
                    if band is None
                    else AT_RECEIVER_EXPIRED
                    if band == EXPIRED
                    else AT_RECEIVER_STOCK
                )
            distributions["Receiving Plant"] = receiving
            distributions["At the Receiving Plant"] = status
            scrapping = moves[moves["Movement Type"].isin(set(_codes(params.scrapping_types)))]
            scrapping = scrapping[scrapping["Posting Date"].between(start, end)].copy()
            scrapping["Quantity"] = scrapping["Quantity"].abs()
            scrapping["Value"] = scrapping["Value"].abs()
            scrapping["Days Expiry to Scrapping"] = (
                scrapping["Posting Date"] - scrapping["Expiry Date"]
            ).dt.days

        short = (
            distributions[distributions["Short Shelf Life"]]
            if len(distributions)
            else distributions
        )

        # Summaries by plant.
        plants = sorted(set(closing["Plant"]) | set(opening["Plant"]))
        by_plant = pd.DataFrame(
            {
                "Plant": plants,
                "Plant Name": [names.get(p, "") for p in plants],
                "Closing Value": [
                    float(closing.loc[closing["Plant"] == p, "Value"].sum()) for p in plants
                ],
                "Expired Value": [
                    float(expired.loc[expired["Plant"] == p, "Value"].sum()) for p in plants
                ],
                "Expired Batches": [int((expired["Plant"] == p).sum()) for p in plants],
                "Expired Not Blocked": [
                    int(expired.loc[expired["Plant"] == p, "Not Blocked"].sum()) for p in plants
                ],
                "Projected Expiries (opening)": [
                    float(due.loc[due["Plant"] == p, "Value"].sum()) for p in plants
                ],
                "Expired of Projected (closing)": [
                    float(actual.loc[actual["Plant"] == p, "Value"].sum()) for p in plants
                ],
                "Within 3 Months": [
                    float(
                        closing.loc[
                            (closing["Plant"] == p) & (closing["Expiry Band"] == BANDS[1]), "Value"
                        ].sum()
                    )
                    for p in plants
                ],
                "3 to 6 Months": [
                    float(
                        closing.loc[
                            (closing["Plant"] == p) & (closing["Expiry Band"] == BANDS[2]), "Value"
                        ].sum()
                    )
                    for p in plants
                ],
            }
        )
        by_plant["Value Saved"] = (
            by_plant["Projected Expiries (opening)"] - by_plant["Expired of Projected (closing)"]
        )
        by_band = pd.DataFrame(
            [
                {
                    "Expiry Band": band,
                    "Batches": int((closing["Expiry Band"] == band).sum()),
                    "Quantity": float(
                        closing.loc[closing["Expiry Band"] == band, "Quantity"].sum()
                    ),
                    "Value": float(closing.loc[closing["Expiry Band"] == band, "Value"].sum()),
                }
                for band in BANDS
            ]
        )
        by_owner = pd.DataFrame(
            [
                {
                    "Owner": owner,
                    "Expired Value": float(expired.loc[expired["Owner"] == owner, "Value"].sum()),
                    "Within 3 Months": float(
                        closing.loc[
                            (closing["Owner"] == owner) & (closing["Expiry Band"] == BANDS[1]),
                            "Value",
                        ].sum()
                    ),
                    "3 to 6 Months": float(
                        closing.loc[
                            (closing["Owner"] == owner) & (closing["Expiry Band"] == BANDS[2]),
                            "Value",
                        ].sum()
                    ),
                }
                for owner in (COMMERCIAL, PROGRAMME, OTHER_OWNER)
            ]
        )

        projected = float(due["Value"].sum())
        expired_of_projected = float(due["Expired Value"].sum())
        saved = projected - expired_of_projected
        expired_value = float(expired["Value"].sum())
        scrap_days = (
            scrapping["Days Expiry to Scrapping"].dropna()
            if len(scrapping)
            else pd.Series(dtype=float)
        )
        kpis = [
            Kpi(label="Expired stock at closing", value=expired_value, format="money", unit="RWF"),
            Kpi(label="Expired batches", value=len(expired), format="integer"),
            Kpi(
                label="Expired batches not blocked",
                value=int(expired["Not Blocked"].sum()),
                format="integer",
                note="Every expired batch must be blocked",
            ),
            Kpi(
                label="Expired batches outside the quarantine plant",
                value=int(expired["Outside Quarantine"].sum()) if quarantine else None,
                format="integer",
                note="" if quarantine else "Set the quarantine plant in the run",
            ),
            Kpi(
                label="Projected expiries in the period",
                value=projected,
                format="money",
                unit="RWF",
            ),
            Kpi(
                label="Expired of the projected",
                value=expired_of_projected,
                format="money",
                unit="RWF",
            ),
            Kpi(label="Value saved", value=saved, format="money", unit="RWF"),
            Kpi(
                label="Expiring within 3 months",
                value=float(closing.loc[closing["Expiry Band"] == BANDS[1], "Value"].sum()),
                format="money",
                unit="RWF",
            ),
            Kpi(
                label="Expiring in 3 to 6 months",
                value=float(closing.loc[closing["Expiry Band"] == BANDS[2], "Value"].sum()),
                format="money",
                unit="RWF",
            ),
            Kpi(label="Expiry dates changed", value=len(changed), format="integer"),
            Kpi(
                label="Distributed with a short shelf life",
                value=float(short["Value"].sum()) if len(short) else None,
                format="money",
                unit="RWF",
                note=f"Less than {params.short_shelf_life_months} months left"
                if movements is not None
                else "Add MB51",
            ),
            Kpi(
                label="Average days from expiry to scrapping",
                value=float(scrap_days.mean()) if len(scrap_days) else None,
                format="number",
                unit="days",
            ),
        ]
        checks = [
            Check(
                "expired_by_plant",
                "Expired value by plant = expired stock at closing",
                expected=expired_value,
                actual=float(by_plant["Expired Value"].sum()),
            ),
            Check(
                "projected_split",
                "Projected expiries = expired + cleared",
                expected=projected,
                actual=expired_of_projected + float(due["Cleared Value"].sum()),
            ),
            Check(
                "saved_by_plant",
                "Value saved by plant adds up to the value saved",
                expected=saved,
                actual=float(by_plant["Value Saved"].sum()),
                description="Batches moved between plants are counted where they are at closing.",
            ),
            Check(
                "bands",
                "Closing stock by expiry band = closing stock",
                expected=float(closing["Value"].sum()),
                actual=float(by_band["Value"].sum()),
            ),
        ]

        def stamp(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
            out = frame.copy()
            for column in columns:
                out[column] = pd.to_datetime(out[column]).dt.strftime("%Y-%m-%d")
            return out

        batch_columns = [
            "Plant",
            "Plant Name",
            "Material",
            "Description",
            "Batch",
            "WBS",
            "Owner",
            "Material Type",
            "Expiry Date",
            "Expiry Month",
            "Months to Expiry",
            "Expiry Band",
            "Quantity",
            "Blocked",
            "Value",
        ]
        closing_table = stamp(closing[batch_columns], ["Expiry Date"])
        expired_table = stamp(
            expired[[*batch_columns, "Not Blocked Qty", "Not Blocked", "Outside Quarantine"]],
            ["Expiry Date"],
        )
        due_table = stamp(
            due[
                [
                    *batch_columns,
                    "Expired Qty",
                    "Expired Value",
                    "Cleared Qty",
                    "Cleared Value",
                    "Outcome",
                ]
            ],
            ["Expiry Date"],
        )
        changed_table = stamp(
            changed[
                [
                    "Plant",
                    "Plant Name",
                    "Material",
                    "Description",
                    "Batch",
                    "Expiry Date (opening)",
                    "Expiry Date (closing)",
                    "Days Changed",
                    "Quantity (closing)",
                    "Value (closing)",
                ]
            ],
            ["Expiry Date (opening)", "Expiry Date (closing)"],
        )
        move_columns = [
            "Plant",
            "Material",
            "Description",
            "Batch",
            "Movement Type",
            "Posting Date",
            "Expiry Date",
            "Quantity",
            "Value",
        ]
        distribution_table = (
            stamp(
                distributions[
                    [
                        *move_columns,
                        "Months Left",
                        "Short Shelf Life",
                        "Receiving Plant",
                        "At the Receiving Plant",
                    ]
                ],
                ["Posting Date", "Expiry Date"],
            )
            if len(distributions)
            else pd.DataFrame()
        )
        scrapping_table = (
            stamp(
                scrapping[[*move_columns, "Days Expiry to Scrapping"]],
                ["Posting Date", "Expiry Date"],
            )
            if len(scrapping)
            else pd.DataFrame()
        )
        subtitle = (
            f"ZSTOCKREPORT of {params.opening_date:%d %B %Y} against {params.closing_date:%d %B %Y}"
        )
        money, integer = "money", "integer"
        dashboard = Dashboard(
            title=self.title,
            subtitle=subtitle,
            kpis=kpis,
            charts=[
                Chart(
                    id="plant-chart",
                    title="Expired stock at closing by plant",
                    type="bar",
                    table="by-plant",
                    category="Plant",
                    format=money,
                    series=[Series(name="Expired value", field="Expired Value")],
                )
            ],
            tables=[
                Table(
                    id="by-plant",
                    title="By plant",
                    columns=[
                        Column(key="Plant", label="Plant"),
                        Column(key="Plant Name", label="Name"),
                        Column(key="Expired Value", label="Expired", format=money),
                        Column(key="Expired Batches", label="Expired batches", format=integer),
                        Column(key="Expired Not Blocked", label="Not blocked", format=integer),
                        Column(key="Within 3 Months", label="Within 3 months", format=money),
                        Column(key="3 to 6 Months", label="3 to 6 months", format=money),
                        Column(key="Projected Expiries (opening)", label="Projected", format=money),
                        Column(key="Value Saved", label="Saved", format=money),
                    ],
                    rows=rows_of(by_plant),
                ),
                Table(
                    id="by-owner",
                    title="Commercial and programme stock",
                    columns=[
                        Column(key="Owner", label="Stock"),
                        Column(key="Expired Value", label="Expired", format=money),
                        Column(key="Within 3 Months", label="Within 3 months", format=money),
                        Column(key="3 to 6 Months", label="3 to 6 months", format=money),
                    ],
                    rows=rows_of(by_owner),
                ),
            ],
            checks=[c.out() for c in checks],
        )
        return AnalysisResult(
            tables={
                "closing_batches": closing_table,
                "expired": expired_table,
                "due": due_table,
                "expiry_changes": changed_table,
                "distributions": distribution_table,
                "scrapping": scrapping_table,
                "by_plant": by_plant,
                "by_band": by_band,
                "by_owner": by_owner,
            },
            metrics=kpis,
            checks=checks,
            dashboard=dashboard,
            extras={
                "subtitle": subtitle,
                "projected": projected,
                "saved": saved,
                "expired_value": expired_value,
            },
        )

    def reports(
        self, result: AnalysisResult, params: BaseModel, templates: Templates
    ) -> list[ReportFile]:
        from app.analyses.expiry_monitoring import dashboard_html

        params = _params(params)
        t = result.tables
        money_columns = (
            "Value",
            "Expired Value",
            "Cleared Value",
            "Closing Value",
            "Projected Expiries (opening)",
            "Expired of Projected (closing)",
            "Within 3 Months",
            "3 to 6 Months",
            "Value Saved",
            "Value (closing)",
        )
        number_columns = (
            "Quantity",
            "Blocked",
            "Expired Qty",
            "Cleared Qty",
            "Not Blocked Qty",
            "Months to Expiry",
            "Months Left",
            "Quantity (closing)",
        )
        formats: dict[str, ValueFormat] = {}
        formats.update(dict.fromkeys(money_columns, "money"))
        formats.update(dict.fromkeys(number_columns, "number"))
        formats.update(
            dict.fromkeys(("Batches", "Expired Batches", "Expired Not Blocked"), "integer")
        )
        kpi = {k.label: k.value for k in result.metrics}

        def rwf(label: str) -> str:
            value = kpi.get(label)
            return f"RWF {value:,.0f}" if isinstance(value, int | float) else "not available"

        document = ReportDocument(
            title="Expiry monitoring",
            subtitle=str(result.extras["subtitle"]),
            date_text=f"{params.closing_date:%d %B %Y}",
            sections=[
                Section(
                    "Summary",
                    paragraphs=[
                        f"Expired stock at {params.closing_date:%d %B %Y}: "
                        f"{rwf('Expired stock at closing')} in {kpi['Expired batches']} batches; "
                        f"{kpi['Expired batches not blocked']} expired batches are not blocked.",
                        f"Batches due to expire during the period were worth "
                        f"{rwf('Projected expiries in the period')} at the opening; "
                        f"{rwf('Expired of the projected')} did expire, so "
                        f"{rwf('Value saved')} was saved.",
                        f"Outlook: {rwf('Expiring within 3 months')} expires within three months "
                        f"and {rwf('Expiring in 3 to 6 months')} in three to six months.",
                    ],
                    tables=[TableBlock("By plant", t["by_plant"], formats)],
                ),
                Section(
                    "Commercial and programme stock",
                    tables=[TableBlock("By stock owner", t["by_owner"], formats)],
                ),
                Section(
                    "Method",
                    bullets=[
                        "A batch has expired when its expiry date is on or before the report "
                        "date of the ZSTOCKREPORT; every expired batch must be blocked and moved "
                        "to the quarantine plant.",
                        "Projected expiries: batches of the opening ZSTOCKREPORT with an expiry "
                        "date in the period. What is still in stock at the closing (any plant) has "
                        "expired; the rest was cleared. Value saved = projected minus expired.",
                        "Commercial stock: RMS-OWN WBS elements; programme stock: RMS-PRG.",
                    ],
                ),
            ],
            checks=check_lines(result.checks),
        )
        name = f"Expiry_Monitoring_{params.opening_date:%Y-%m-%d}_{params.closing_date:%Y-%m-%d}"
        blocks = [
            TableBlock("By plant", t["by_plant"], formats),
            TableBlock("By expiry band", t["by_band"], formats),
            TableBlock("By stock owner", t["by_owner"], formats),
            TableBlock("Expired batches", t["expired"], formats),
            TableBlock("Due in the period", t["due"], formats),
            TableBlock("Expiry date changes", t["expiry_changes"], formats),
            TableBlock("Closing batches", t["closing_batches"], formats),
        ]
        if len(t["distributions"]):
            blocks.append(TableBlock("Distributions", t["distributions"], formats))
        if len(t["scrapping"]):
            blocks.append(TableBlock("Scrapping", t["scrapping"], formats))
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
                    blocks,
                    document.checks,
                ),
            ),
            dashboard_file(
                name,
                dashboard_html.build(
                    t,
                    f"Expiry monitoring: {params.opening_date:%d %b %Y} to "
                    f"{params.closing_date:%d %b %Y}",
                    document.subtitle,
                    params.short_shelf_life_months,
                    check_rows(result.checks),
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


ANALYSIS = ExpiryMonitoring()
