"""Stock sufficiency against AMC: hand-checked figures on fake data."""

from datetime import date
from typing import Any

import pandas as pd
import pytest

from app.analyses.common.weekly import (
    BY_CODE,
    BY_DESCRIPTION,
    NO_AMC,
    NOT_FOUND,
    OVERSTOCK,
    STOCK_OUT,
    TO_PLAN,
    UNDERSTOCK,
    programme_of,
    status_of,
)
from app.analyses.stock_sufficiency_amc import ANALYSIS, Parameters
from app.jobs.analysis import result_hash
from app.reporting.documents import Templates
from app.reporting.guard import check_report

WEEKLY_COLUMNS = [
    "Sheet",
    "Product code",
    "Product description",
    "RMS central warehouse",
    "RMS Branches",
    "SDPs",
    "AMC",
]
# Fake weekly lines: sheet, code, description, HQ, branches, SDPs, AMC
WEEKLY = [
    ["ARV", "npc1", "Drug A", "60", "0", "0", "10"],  # MOS 6 -> to plan
    ["ARV", "NPC2", "Drug B", "100", "50", "1,050", "100"],  # RMS 1.5, national 12 -> to plan
    ["ARV", "NPC6", "Drug E", "100", "50", "50", "10"],  # RMS 15, national 20 -> overstock
    ["ARV", None, "Total ARV", "260", "100", "1,100", None],  # total line, skipped
    ["ARV", "XYZ", "Drug  C", "5", "0", "0", "10"],  # 0.5 -> stock-out, linked by description
    ["ARV", None, "STOCK STATUS AT SDP LEVEL", None, None, None, None],  # next block
    ["ARV", "NPC9", "Ignored", "1", "1", "1", "1"],
    ["MCCH", "NPC4", "Drug D", "80", "0", "0", "10"],  # 8 < min 9 -> understock
    ["MCCH", "NPC5", "Drug F", "40", "0", "0", ""],  # no AMC, not in ZSTOCKREPORT
]
STOCK_COLUMNS = [
    "Material",
    "NPC CODE",
    "Material Description",
    "Plant",
    "Unrestricted",
    "Quality Inspection",
    "Blocked",
    "WBS Element",
    "Unit Cost",
]
WBS = "RMS-PRG-FND-CP"
# Fake ZSTOCKREPORT lines: value = (unrestricted + QI + blocked) x unit cost
STOCK = [
    ["0001001", "NPC1", "Drug A", "1000", 50, 5, 5, WBS, 10.0],  # 600
    ["1002", "NPC2", "Drug B", "1000", 10, 0, 0, WBS, 20.0],  # 200
    ["1006", "NPC6", "Drug E", "1000", 100, 0, 0, WBS, 20.0],  # 2000
    ["1006", "NPC6", "Drug E", "7000", 50, 0, 0, WBS, 20.0],  # 1000
    ["1003", None, "DRUG C", "1000", 5, 0, 0, WBS, 4.0],  # 20
    ["1004", "NPC4", "Drug D", "1000", 80, 0, 0, WBS, 1.0],  # 80
    ["1004", "NPC4", "Drug D", "1000", 10, 0, 0, "RMS-OWN-FND", 1.0],  # other WBS, left out
    ["1009", None, "Other item", "1000", 7, 0, 0, WBS, 3.0],  # 21, no AMC
    ["1010", None, "Tiny item", "1000", 1, 0, 0, WBS, 0.4],  # under RWF 0.5, not listed
    ["1011", None, "Short item", "1000", -2, 0, 0, WBS, 3.0],  # negative, not listed
]
PARAMS = Parameters(report_date=date(2026, 7, 29))


def data() -> dict[str, pd.DataFrame]:
    return {
        "weekly": pd.DataFrame(WEEKLY, columns=WEEKLY_COLUMNS),
        "stock": pd.DataFrame(STOCK, columns=STOCK_COLUMNS),
    }


@pytest.fixture(scope="module")
def result() -> Any:
    return ANALYSIS.compute(data(), PARAMS)


@pytest.mark.parametrize(
    ("mos", "status"),
    [
        (None, NO_AMC),
        (12.01, OVERSTOCK),
        (12, TO_PLAN),
        (6, TO_PLAN),
        (5.9, UNDERSTOCK),
        (3, UNDERSTOCK),
        (2.99, STOCK_OUT),
        (0, STOCK_OUT),
    ],
)
def test_status_thresholds(mos: float | None, status: str) -> None:
    assert status_of(mos, 6, 12) == status


def test_programme_of_sheet() -> None:
    assert programme_of("ARV&OIs_NoChange") == ("ARV and Opportunistic Infection", (6.0, 12.0))
    assert programme_of("LAB ") == ("Laboratory (HIV and program lab)", (6.0, 12.0))
    assert programme_of("MCCH") == ("MCCH", (9.0, 14.0))


def test_lines_hand_checked(result: Any) -> None:
    lines = result.tables["analysis"].set_index("Product Code")
    assert list(lines.index) == ["NPC1", "NPC2", "NPC6", "XYZ", "NPC4", "NPC5"]
    assert lines.loc["NPC1", "Status"] == TO_PLAN
    assert lines.loc["NPC2", "National Stock"] == 1200
    assert lines.loc["NPC2", "MOS at RMS"] == 1.5
    assert lines.loc["NPC6", "Status"] == OVERSTOCK
    assert lines.loc["XYZ", "Status"] == STOCK_OUT
    assert lines.loc["NPC4", "Status"] == UNDERSTOCK
    assert lines.loc["NPC5", "Status"] == NO_AMC
    assert lines.loc["NPC1", "SAP Material"] == "1001"
    assert lines.loc["NPC1", "Linked by"] == BY_CODE
    assert lines.loc["XYZ", "Linked by"] == BY_DESCRIPTION
    assert lines.loc["NPC5", "Linked by"] == NOT_FOUND
    assert lines.loc["NPC1", "Value (RWF)"] == 600
    assert lines.loc["NPC6", "Value (RWF)"] == 3000
    assert lines.loc["NPC4", "Value (RWF)"] == 80  # other WBS left out
    assert lines.loc["NPC6", "Monthly Consumption Value (RWF)"] == 200  # 3000 / 15
    # 3000 x (20 - 12) / 15
    assert lines.loc["NPC6", "Value Above Max Level (RWF)"] == pytest.approx(1600)
    assert lines.loc["NPC2", "Value Above Max Level (RWF)"] == 0
    assert result.tables["risk"]["Product Code"].tolist() == ["XYZ"]


def test_summary_hand_checked(result: Any) -> None:
    summary = result.tables["summary"].set_index("Program")
    arv = summary.loc["ARV and Opportunistic Infection"]
    assert arv["Products"] == 4
    assert (arv[TO_PLAN], arv[OVERSTOCK], arv[STOCK_OUT]) == (2, 1, 1)
    assert arv["% Below Min"] == 0.25
    assert arv["Value (RWF)"] == 3820
    mcch = summary.loc["MCCH"]
    assert (mcch[UNDERSTOCK], mcch[NO_AMC]) == (1, 1)
    assert mcch["% Below Min"] == 1.0
    no_amc = result.tables["no_amc"]
    assert no_amc["Material"].tolist() == ["1009"]
    assert no_amc["Value"].tolist() == [21]
    assert all(c.passed for c in result.checks), [c.label for c in result.checks if not c.passed]


def test_material_valued_once() -> None:
    inputs = data()
    twice = pd.DataFrame(
        [["MCCH", "NPC1", "Drug A again", "10", "0", "0", "10"]], columns=WEEKLY_COLUMNS
    )
    inputs["weekly"] = pd.concat([inputs["weekly"], twice], ignore_index=True)
    lines = ANALYSIS.compute(inputs, PARAMS).tables["analysis"]
    again = lines[lines["Product (weekly report)"] == "Drug A again"].iloc[0]
    assert again["Value (RWF)"] == 0
    assert again["Value note"] != ""


def test_same_inputs_same_result() -> None:
    assert result_hash(ANALYSIS.compute(data(), PARAMS)) == result_hash(
        ANALYSIS.compute(data(), PARAMS)
    )


def test_reports(result: Any) -> None:
    files = ANALYSIS.reports(result, PARAMS, Templates())
    assert [f.kind for f in files] == ["xlsx", "docx", "pptx"]
    for report in files:
        check_report(report.kind, report.content)


def test_value_from_closing_stock() -> None:
    inputs = data()
    inputs["closing"] = pd.DataFrame(
        {
            "Plant": ["1000", "7000", "1000", "1000"],
            "Material": ["001006", "1006", "1001", "1004"],
            "WBS": [WBS, WBS, WBS, "RMS-OWN-FND"],
            "Final Qty": [10.0, 5.0, 1.0, 3.0],
            "Final Value": [700.0, 300.0, 50.0, 30.0],
            "Material Description": ["Drug E", "Drug E", "Drug A", "Drug D"],
        }
    )
    result = ANALYSIS.compute(inputs, PARAMS)
    lines = result.tables["analysis"].set_index("Product Code")
    assert lines.loc["NPC6", "Value (RWF)"] == 1000  # 700 + 300, linked through ZSTOCKREPORT
    assert lines.loc["NPC1", "Value (RWF)"] == 50
    assert lines.loc["NPC4", "Value (RWF)"] == 0  # closing on another WBS
    assert lines.loc["NPC6", "Value Above Max Level (RWF)"] == pytest.approx(1000 * 8 / 15)
    assert result.tables["no_amc"].empty  # 1009 has no closing stock
    assert all(c.passed for c in result.checks)
