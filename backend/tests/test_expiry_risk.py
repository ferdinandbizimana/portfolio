"""Expiry risk: first expiry first out at the AMC, hand-checked on fake data."""

from datetime import date, timedelta
from typing import Any

import pandas as pd
import pytest

from app.analyses.expiry_risk import (
    ANALYSIS,
    BANDS,
    EXPIRED,
    NO_DATE,
    NOT_ASSESSED,
    Parameters,
    at_risk,
    band_of,
)
from app.jobs.analysis import result_hash
from app.reporting.documents import Templates
from app.reporting.guard import check_report

WBS = "RMS-PRG-FND-CP"
REPORT = pd.Timestamp(2026, 7, 31)
# An AMC of 30.4375 (365.25 / 12) uses exactly one unit a day.
DAILY = 365.25 / 12


def day(offset: int | None) -> Any:
    return None if offset is None else REPORT + timedelta(days=offset)


STOCK_COLUMNS = [
    "Material",
    "NPC CODE",
    "Material Description",
    "Plant",
    "Storage Location",
    "Batch",
    "Unrestricted",
    "Quality Inspection",
    "Blocked",
    "WBS Element",
    "Expiry Date",
    "Unit Cost",
]
# Fake batches: material, NPC, description, plant, sloc, batch, qty (3), WBS, expiry, cost
STOCK: list[list[Any]] = [
    ["1001", "NPC1", "Drug A", "1000", "S1", "B1", 20, 0, 0, WBS, day(-30), 2.0],  # expired
    ["1001", "NPC1", "Drug A", "7000", "S1", "B2", 25, 5, 0, WBS, day(20), 2.0],  # 20 of 30 used
    ["1001", "NPC1", "Drug A", "1000", "S2", "B3", 50, 0, 0, WBS, day(100), 2.0],  # all used
    ["1001", "NPC1", "Drug A", "1000", "S2", "B4", 5, 0, 0, WBS, day(None), 2.0],  # no date
    ["1002", None, "Drug B", "1000", "S1", "C1", 10, 0, 0, WBS, day(400), 3.0],  # AMC 0
    ["1003", None, "Drug C", "7000", "S1", "D1", 4, 0, 0, "RMS-OWN", day(-1), 5.0],  # expired
    ["1004", None, "Drug D", "7000", "S1", "E1", 0, 0, 0, WBS, day(10), 5.0],  # no stock
]
WEEKLY = pd.DataFrame(
    {
        "Sheet": ["ARV", "ARV"],
        "Product code": ["NPC1", "XX2"],
        "Product description": ["Drug A", "Drug B"],
        "RMS central warehouse": ["100", "10"],
        "RMS Branches": ["0", "0"],
        "SDPs": ["0", "0"],
        "AMC": [str(DAILY), "0"],
    }
)
PARAMS = Parameters(report_date=date(2026, 7, 31))


def data() -> dict[str, pd.DataFrame]:
    stock = pd.DataFrame(STOCK, columns=STOCK_COLUMNS)
    stock["Expiry Date"] = pd.to_datetime(stock["Expiry Date"])
    return {
        "stock": stock,
        "weekly": WEEKLY.copy(),
        "plants": pd.DataFrame({"Plant": ["7000"], "Name 1": ["Kigali Hub"]}),
    }


@pytest.fixture(scope="module")
def result() -> Any:
    return ANALYSIS.compute(data(), PARAMS)


def test_bands() -> None:
    assert [band_of(m) for m in (None, -1, 0, 0.5, 3, 3.1, 6, 12, 12.5)] == [
        NO_DATE,
        EXPIRED,
        EXPIRED,
        BANDS[1],
        BANDS[1],
        BANDS[2],
        BANDS[2],
        BANDS[3],
        BANDS[4],
    ]


def test_first_expiry_first_out() -> None:
    # AMC 10: 2 months can use 20 of the first batch, 30 more by month 5.
    assert at_risk([30, 40, 5], [2, 5, None], 10) == [10, 10, 0]
    assert at_risk([5, 5], [-1, 1], 10) == [5, 0]  # expired stock does not use the AMC


def test_kpis_hand_checked(result: Any) -> None:
    kpis = {k.label: k.value for k in result.metrics}
    assert kpis["Stock value"] == pytest.approx(260)  # 40 + 60 + 100 + 10 + 30 + 20
    assert kpis["Expired stock"] == pytest.approx(60)  # B1 and D1
    assert kpis["Expiring within 6 months"] == pytest.approx(160)  # B2 and B3
    assert kpis["Value at risk of expiry"] == pytest.approx(80)  # 40 + 10 x 2 + 20
    assert kpis["Batches not assessed (no AMC)"] == 1  # C1; D1 is expired
    assert all(c.passed for c in result.checks), [c.label for c in result.checks if not c.passed]


def test_batches_hand_checked(result: Any) -> None:
    batches = result.tables["batches"].set_index("Batch")
    assert batches.loc["B2", "Qty at Risk"] == pytest.approx(10)
    assert batches.loc["B3", "Qty at Risk"] == pytest.approx(0)
    assert batches.loc["B4", "Expiry Band"] == NO_DATE
    assert batches.loc["C1", "Risk"] == NOT_ASSESSED
    assert batches.loc["D1", "Risk"] == "Expired"
    assert batches.loc["D1", "Program"] == ""
    assert batches.loc["B2", "Plant Name"] == "Kigali Hub"
    assert "E1" not in batches.index  # no stock
    assert result.tables["at_risk"]["Batch"].tolist() == ["B1", "D1", "B2"]  # highest value first
    bands = result.tables["by_band"].set_index("Expiry Band")
    assert list(bands.index) == BANDS
    assert bands.loc["3 to 6 months", "Value"] == 100
    programmes = result.tables["by_programme"].set_index("Program")
    assert programmes.loc["Not in the weekly report", "Value at Risk"] == 20


def test_wbs_filter() -> None:
    params = PARAMS.model_copy(update={"wbs": WBS})
    kpis = {k.label: k.value for k in ANALYSIS.compute(data(), params).metrics}
    assert kpis["Stock value"] == pytest.approx(240)  # without D1


def test_same_inputs_same_result() -> None:
    assert result_hash(ANALYSIS.compute(data(), PARAMS)) == result_hash(
        ANALYSIS.compute(data(), PARAMS)
    )


def test_reports(result: Any) -> None:
    files = ANALYSIS.reports(result, PARAMS, Templates())
    assert [f.kind for f in files] == ["xlsx", "html", "docx", "pptx"]
    for report in files:
        check_report(report.kind, report.content)
