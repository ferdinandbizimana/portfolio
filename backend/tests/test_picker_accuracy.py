"""Picker accuracy: sheet dates and hand-checked figures on fake data."""

from datetime import date
from typing import Any

import pandas as pd
import pytest

from app.analyses.picker_accuracy import ANALYSIS, BELOW, ON_TARGET, Parameters, sheet_days
from app.jobs.analysis import result_hash
from app.reporting.documents import Templates
from app.reporting.guard import check_report


def test_days_from_sheet_names() -> None:
    days = sheet_days(["25nov", "26 NOV", "28TH nov", "27112025", "2122025", "Notes"])
    assert days["25nov"] == date(2025, 11, 25)  # year from the other sheets
    assert days["28TH nov"] == date(2025, 11, 28)
    assert days["27112025"] == date(2025, 11, 27)
    assert days["2122025"] == date(2025, 12, 2)  # not 21 February: nearest the other sheets
    assert days["Notes"] is None


DAILY = pd.DataFrame(
    {
        "Sheet": ["25nov", "25nov", "26nov", "26nov"],
        "Pickers name": ["ALICE", "Bob", "alice ", None],
        "Numbers of lines picked per day": [40.0, 10.0, 60.0, 5.0],
        "Number of descrepancies out of those lines": [0.0, 2.0, 1.0, 0.0],
    }
)
ORDERS = pd.DataFrame(
    {
        "Sheet": ["2122025", "2122025"],
        "Date": pd.to_datetime(["2025-12-02", "2025-12-02"]),
        "Outbound Delivery ( OBD ) Number": ["8700000001", "8700000002"],
        "Number of Lines": [12.0, 8.0],
        "Pickers Name": ["Bob", "Alice"],
        "Number of Lines with descrepancies": [1.0, None],
        "Customer/Branche Name": ["Nyanza", "HUYE"],
        "Type of Order": ["URG", "CP"],
    }
)


@pytest.fixture(scope="module")
def result() -> Any:
    return ANALYSIS.compute({"daily": DAILY, "orders": ORDERS}, Parameters())


def test_hand_checked(result: Any) -> None:
    kpis = {k.label: k.value for k in result.metrics}
    assert kpis["Lines picked"] == 130  # 40 + 10 + 60 + 12 + 8 (the row without a picker is out)
    assert kpis["Lines with discrepancies"] == 4  # 0 + 2 + 1 + 1
    assert kpis["Picking accuracy"] == pytest.approx(1 - 4 / 130)
    assert kpis["Pickers"] == 2  # ALICE / alice / Alice are one picker
    assert kpis["Days"] == 3
    pickers = result.tables["by_picker"].set_index("Picker")
    assert pickers.loc["Alice", "Lines"] == 108
    assert pickers.loc["Alice", "Accuracy"] == pytest.approx(1 - 1 / 108)
    assert pickers.loc["Alice", "Status"] == BELOW  # 99.1% < 100%
    assert pickers.loc["Bob", "Accuracy"] == pytest.approx(1 - 3 / 22)
    assert pickers.loc["Bob", "Status"] == BELOW
    assert list(pickers.index) == ["Bob", "Alice"]  # lowest accuracy first
    customers = result.tables["by_customer"].set_index("Customer")
    assert customers.loc["Nyanza", "Discrepancies"] == 1
    assert customers.loc["Huye", "Accuracy"] == 1
    assert all(c.passed for c in result.checks)


def test_without_delivery_sheets() -> None:
    result = ANALYSIS.compute({"daily": DAILY}, Parameters(target=0.9))
    pickers = result.tables["by_picker"].set_index("Picker")
    assert pickers.loc["Bob", "Status"] == BELOW  # 80% < 90%
    assert result.tables["by_customer"].empty


def test_perfect_picker_meets_the_default_target() -> None:
    daily = DAILY[DAILY["Pickers name"] == "ALICE"]  # 40 lines, no discrepancy
    pickers = ANALYSIS.compute({"daily": daily}, Parameters()).tables["by_picker"]
    assert pickers.set_index("Picker").loc["Alice", "Status"] == ON_TARGET


def test_same_inputs_same_result() -> None:
    data = {"daily": DAILY, "orders": ORDERS}
    assert result_hash(ANALYSIS.compute(data, Parameters())) == result_hash(
        ANALYSIS.compute(data, Parameters())
    )


def test_reports(result: Any) -> None:
    files = ANALYSIS.reports(result, Parameters(), Templates())
    assert [f.kind for f in files] == ["xlsx", "html", "docx", "pptx"]
    for report in files:
        check_report(report.kind, report.content)
