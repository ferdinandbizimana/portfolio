"""Stock in transit: STO tracing through MB51, hand-checked on fake data."""

from datetime import date
from typing import Any

import pandas as pd
import pytest

from app.analyses.stock_in_transit import (
    AGE_BANDS,
    ANALYSIS,
    NOT_ISSUED,
    Movement,
    Parameters,
    age_band,
    trace,
)
from app.jobs.analysis import result_hash
from app.reporting.documents import Templates
from app.reporting.guard import check_report

MB51_COLUMNS = [
    "Plant",
    "Material",
    "Movement Type",
    "Quantity",
    "Amt.in Loc.Cur.",
    "WBS Element",
    "Posting Date",
    "Purchase order",
    "Reference",
]
# Fake MB51 lines: plant, material, type, quantity, amount, WBS, posting date, PO, reference
MB51: list[list[Any]] = [
    ["1000", "1001", "641", -10, -1000, "W", "01.07.2026", "4500000001", "0080001"],
    ["1000", "1001", "641", -5, -500, "W", "10.07.2026", "4500000001", "80002"],
    ["7000", "1001", "101", 5, 500, "W", "15.07.2026", "4500000001", "80002"],  # 5 days
    ["7000", "1001", "101", 4, 400, "W", "20.07.2026", "4500000001", None],  # oldest: 19 days
    ["1000", "1002", "641", -8, -80, "W", "2026-05-01", "4500000002", "80003"],
    ["1000", "1002", "642", 3, 30, "W", "2026-05-02", "4500000002", "80003"],  # reversal
    ["7000", "1002", "101", 5, 50, "W", "2026-05-11", "4500000002", "80003"],  # 10 days
    ["1000", "1003", "641", -2, -50, "W", "29.07.2026", "4500000003", "80004"],
    ["1000", "1009", "101", 9, 90, "W", "05.07.2026", "4500009999", None],  # vendor PO
    ["1000", "1009", "551", -1, -10, "W", "05.07.2026", None, None],  # scrapping
]
MB5T_COLUMNS = [
    "Supplying Plant",
    "Purchasing Document",
    "Plant",
    "Material",
    "Material Description",
    "Quantity",
    "Amt.in Loc.Cur.",
]
MB5T: list[list[Any]] = [
    ["1000", "4500000001", "7000", "1001", "Drug A", 6, 600],  # issued 1 July: 30 days
    ["1000", "4500000003", "7000", "1003", "Drug C", 2, 50],  # issued 29 July: 2 days
    ["7000", "4500000004", "1000", "1004", "Drug D", 1, 10],  # no goods issue in MB51
]
PARAMS = Parameters(report_date=date(2026, 7, 31))


def data() -> dict[str, pd.DataFrame]:
    return {
        "movements": pd.DataFrame(MB51, columns=MB51_COLUMNS),
        "in_transit": pd.DataFrame(MB5T, columns=MB5T_COLUMNS),
        "plants": pd.DataFrame({"Plant": ["7000"], "Name 1": ["Kigali Hub"]}),
    }


@pytest.fixture(scope="module")
def result() -> Any:
    return ANALYSIS.compute(data(), PARAMS)


def test_age_bands() -> None:
    up_to_7, up_to_30, up_to_60, up_to_90, longer = AGE_BANDS[:5]
    assert [age_band(d) for d in (None, 0, 7, 8, 30, 31, 90, 91)] == [
        NOT_ISSUED,
        up_to_7,
        up_to_7,
        up_to_30,
        up_to_30,
        up_to_60,
        up_to_90,
        longer,
    ]


def test_receipts_match_the_same_delivery_first() -> None:
    day = pd.Timestamp
    issues = [Movement(day(2026, 7, 1), 10, "A", "1"), Movement(day(2026, 7, 2), 5, "B", "1")]
    receipts = [Movement(day(2026, 7, 5), 5, "B", "2"), Movement(day(2026, 7, 6), 12, "", "2")]
    traced = trace(issues, receipts)
    assert [(leg["Reference"], leg["Quantity"]) for leg in traced.legs] == [("B", 5), ("A", 10)]
    assert traced.receipts_without_issue == 2
    assert traced.open_issues == []


def test_kpis_hand_checked(result: Any) -> None:
    kpis = {k.label: k.value for k in result.metrics}
    assert kpis["Value in transit"] == 660
    assert kpis["Lines in transit"] == 3
    assert kpis["In transit more than 30 days"] == 0  # 30 days is not more than 30
    assert kpis["Average days in transit (open)"] == pytest.approx(23)  # (6 x 30 + 2 x 2) / 8
    # (5 x 5 + 4 x 19 + 5 x 10) / 14
    assert kpis["Average transit time (received)"] == pytest.approx(151 / 14)
    assert kpis["Lines without a goods issue in MB51"] == 1
    assert all(c.passed for c in result.checks), [c.label for c in result.checks if not c.passed]


def test_lines_hand_checked(result: Any) -> None:
    transit = result.tables["in_transit"].set_index("STO")
    assert transit.loc["4500000001", "Days in Transit"] == 30
    assert transit.loc["4500000001", "Open Qty in MB51"] == 6
    assert transit.loc["4500000001", "Delivery References"] == "80001"
    assert transit.loc["4500000001", "Receiving Plant Name"] == "Kigali Hub"
    assert transit.loc["4500000003", "Age"] == AGE_BANDS[0]
    assert transit.loc["4500000004", "Age"] == NOT_ISSUED
    assert transit.loc["4500000004", "Difference with MB51"] == 1
    # The OBD value is shown even where MB5T has a value: 6 open units at RWF 100.
    assert transit.loc["4500000001", "OBD Value (MB51)"] == 600
    assert transit.loc["4500000001", "Value Source"] == "MB5T"
    received = result.tables["received"]
    assert sorted(received["Transit Days"].tolist()) == [5, 10, 19]
    assert received.loc[received["STO"] == "4500000002", "Quantity"].tolist() == [5]  # 8 - 3
    by_age = result.tables["by_age"].set_index("Age")
    assert by_age.loc["8 to 30 days", "Value"] == 600
    receiving = result.tables["by_receiving"].set_index("Plant")
    assert receiving.loc["7000", "Received Transfers"] == 3
    assert receiving.loc["7000", "Lines in Transit"] == 2


def test_long_transit_parameter() -> None:
    params = PARAMS.model_copy(update={"long_transit_days": 20})
    kpis = {k.label: k.value for k in ANALYSIS.compute(data(), params).metrics}
    assert kpis["In transit more than 20 days"] == 1


def test_same_inputs_same_result() -> None:
    assert result_hash(ANALYSIS.compute(data(), PARAMS)) == result_hash(
        ANALYSIS.compute(data(), PARAMS)
    )


def test_reports(result: Any) -> None:
    files = ANALYSIS.reports(result, PARAMS, Templates())
    assert [f.kind for f in files] == ["xlsx", "html", "docx", "pptx"]
    for report in files:
        check_report(report.kind, report.content)


def test_sto_creation_dates_from_me2m() -> None:
    inputs = data()
    inputs["orders"] = pd.DataFrame(
        {
            "Purchasing Document": ["4500000001", "4500000001"],
            "Document Date": pd.to_datetime(["2026-06-25", "2026-06-25"]),
        }
    )
    result = ANALYSIS.compute(inputs, PARAMS)
    kpis = {k.label: k.value for k in result.metrics}
    # Matched legs of STO 1: 5 units issued 10 July, received 15 July; 4 units issued
    # 1 July, received 20 July. Created 25 June.
    assert kpis["Average STO creation to goods issue"] == pytest.approx((5 * 15 + 4 * 6) / 9)
    assert kpis["Average STO creation to goods receipt"] == pytest.approx((5 * 20 + 4 * 25) / 9)
    transit = result.tables["in_transit"].set_index("STO")
    assert transit.loc["4500000001", "Days Since STO Created"] == 36
    assert transit.loc["4500000001", "STO Created"] == "2026-06-25"


def test_return_delivery_122_reverses_a_receipt() -> None:
    rows = [*MB51, ["7000", "1002", "122", -2, -20, "W", "2026-05-12", "4500000002", "80003"]]
    inputs = data()
    inputs["movements"] = pd.DataFrame(rows, columns=MB51_COLUMNS)
    result = ANALYSIS.compute(inputs, PARAMS)
    received = result.tables["received"]
    assert received.loc[received["STO"] == "4500000002", "Quantity"].tolist() == [3]  # 5 - 2
    assert all(c.passed for c in result.checks)


def test_every_mb5t_line_counts_and_missing_values_come_from_mb51() -> None:
    # STO 1 split over two MB5T lines (4 + 2 units), MB5T without values. In MB51 the
    # 6 units still open are from the 1 July goods issue: 10 units for RWF 1,000.
    rows = [
        ["1000", "4500000001", "7000", "1001", "Drug A", 4, 0],
        ["1000", "4500000001", "7000", "1001", "Drug A", 2, 0],
        ["1000", "4500000003", "7000", "1003", "Drug C", 2, 0],  # 641: 2 units, RWF 50
        ["7000", "4500000004", "1000", "1004", "Drug D", 1, 0],  # no goods issue
    ]
    inputs = data()
    inputs["in_transit"] = pd.DataFrame(rows, columns=MB5T_COLUMNS)
    params = PARAMS.model_copy(update={"long_transit_days": 5})
    result = ANALYSIS.compute(inputs, params)
    kpis = {k.label: k.value for k in result.metrics}
    assert kpis["Lines in transit"] == 4  # as many as in MB5T
    assert kpis["Value in transit"] == 650  # 6 x 100 + 2 x 25; Drug D has no value
    assert kpis["In transit more than 5 days"] == 2
    long_note = next(k.note for k in result.metrics if k.label == "In transit more than 5 days")
    assert long_note == "RWF 600"
    transit = result.tables["in_transit"]
    sto1 = transit[transit["STO"] == "4500000001"].sort_values("MB5T Line")
    assert sto1["Value"].tolist() == [400, 200]
    assert set(sto1["Value Source"]) == {"MB51 goods issue"}
    assert sto1["OBD Value (MB51)"].tolist() == [400, 200]
    assert kpis["Value of the outbound deliveries (MB51)"] == 650
    by_material = result.tables["by_material"].set_index("Material")
    assert by_material.loc["1001", "Lines in Transit"] == 2
    assert by_material.loc["1001", "OBD Value (MB51)"] == 600
    assert by_material.loc["1001", "Outbound Deliveries"] == "80001"
    assert by_material.loc["1004", "OBD Value (MB51)"] == 0  # no goods issue in MB51
    # Compared with MB51 once per STO and material: 6 in MB5T, 6 open, nothing untraced.
    assert sto1["Open Qty in MB51"].dropna().tolist() == [6]
    assert sto1["Difference with MB51"].dropna().tolist() == [0]
    assert kpis["Average days in transit (open)"] == pytest.approx(23)  # not counted twice
    assert all(c.passed for c in result.checks), [c.label for c in result.checks if not c.passed]
