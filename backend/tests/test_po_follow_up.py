"""Purchase order follow-up: hand-checked figures on fake data."""

from datetime import date
from typing import Any

import pandas as pd
import pytest
from pydantic import ValidationError

from app.analyses.po_follow_up import (
    ANALYSIS,
    IN_FULL,
    OPEN,
    PARTLY,
    PERIOD_BANDS,
    PURCHASE_ORDER,
    STO,
    Parameters,
    period_band,
)
from app.jobs.analysis import result_hash
from app.reporting.documents import Templates
from app.reporting.guard import check_report

ME2N_COLUMNS = [
    "Purchasing Document",
    "Item",
    "Document Date",
    "Delivery Date",
    "Supplier/Supplying Plant",
    "Name of Supplier",
    "Material",
    "Short Text",
    "Plant",
    "Order Quantity",
    "Net Order Value",
    "Still to be delivered (qty)",
    "Deletion Indicator",
]
# Fake PO lines: PO, item, created, delivery date, supplier, name, material, text, plant,
# quantity, value, still to be delivered, deletion indicator
ME2N: list[list[Any]] = [
    [
        "4100000001",
        "00010",
        "2026-01-10",
        "2026-02-01",
        "V1",
        "Supplier One",
        "1001",
        "Gloves",
        "1000",
        100,
        10000,
        0,
        None,
    ],
    [
        "4100000001",
        "00020",
        "2026-01-10",
        "2026-02-01",
        "V1",
        "Supplier One",
        "1002",
        "Masks",
        "1000",
        50,
        5000,
        20,
        None,
    ],
    [
        "4100000002",
        "00010",
        "2026-03-01",
        None,
        "V2",
        "Supplier Two",
        "1003",
        "Kits",
        "7000",
        10,
        1000,
        10,
        None,
    ],
    [
        "4100000003",
        "00010",
        "2026-04-01",
        None,
        "V2",
        "Supplier Two",
        "1003",
        "Kits",
        "7000",
        10,
        1000,
        10,
        "L",
    ],  # deleted
    [
        "4100000004",
        "00010",
        "2025-06-01",
        None,
        "V2",
        "Supplier Two",
        "1003",
        "Kits",
        "7000",
        10,
        1000,
        0,
        None,
    ],  # before the period
]
INBOUND_COLUMNS = [
    "Delivery",
    "Purchasing Document",
    "Reference Item",
    "Material",
    "Vendor",
    "Delivery Quantity",
    "Actual delivery qty",
    "Act. Gds Mvmnt Date",
]
INBOUND: list[list[Any]] = [
    ["IB1", "4100000001", "000010", "1001", "V1", 60, 60, "2026-02-09"],  # 30 days
    ["IB2", "4100000001", "10", "1001", "V1", 40, 40, "2026-03-11"],  # 60 days: in full
    ["IB3", "4100000001", None, "1002", "V1", 30, None, "2026-02-20"],  # by material
    ["IB4", "4100000002", "10", "1003", "V2", 10, 10, None],  # no goods receipt yet
    ["IB5", "4100009999", "10", "1009", "V3", 5, 5, "2026-05-01"],  # no such PO line
]
PARAMS = Parameters(
    period_start=date(2025, 7, 1), period_end=date(2026, 6, 30), report_date=date(2026, 7, 31)
)


def data() -> dict[str, pd.DataFrame]:
    orders = pd.DataFrame(ME2N, columns=ME2N_COLUMNS)
    # ME2M dates: final approval of the first PO after 5 days; the second PO is not
    # approved yet and required after the report date.
    orders["Final Approval Date"] = ["2026-01-15", "2026-01-15", None, None, None]
    orders["Purchasing Doc. Type"] = ["ZNAT", "ZNAT", "ZSTO", "ZNAT", "ZNAT"]  # PO 2 is an STO
    orders.loc[2, "Delivery Date"] = "2026-08-15"
    for column in ("Document Date", "Delivery Date", "Final Approval Date"):
        orders[column] = pd.to_datetime(orders[column])
    inbound = pd.DataFrame(INBOUND, columns=INBOUND_COLUMNS)
    inbound["Act. Gds Mvmnt Date"] = pd.to_datetime(inbound["Act. Gds Mvmnt Date"])
    inbound["Actual delivery qty"] = inbound["Actual delivery qty"].astype(float)
    return {
        "orders": orders,
        "deliveries": inbound,
        "plants": pd.DataFrame({"Plant": ["1000"], "Name 1": ["Kigali HQ"]}),
    }


@pytest.fixture(scope="module")
def result() -> Any:
    return ANALYSIS.compute(data(), PARAMS)


def test_period_bands() -> None:
    assert [period_band(d) for d in (0, 30, 31, 90, 180, 181)] == [
        PERIOD_BANDS[0],
        PERIOD_BANDS[0],
        PERIOD_BANDS[1],
        PERIOD_BANDS[2],
        PERIOD_BANDS[3],
        PERIOD_BANDS[4],
    ]


def test_kpis_hand_checked(result: Any) -> None:
    kpis = {k.label: k.value for k in result.metrics}
    assert kpis["PO lines"] == 3
    assert kpis["Lines delivered in full"] == pytest.approx(1 / 3)
    assert kpis["Quantity received"] == pytest.approx(130 / 160)  # 100 + 30 + 0
    assert kpis["Value received"] == pytest.approx(13000 / 16000)  # 10000 + 3000
    assert kpis["Average delivery period"] == 60
    assert kpis["Open value"] == pytest.approx(3000)  # 5000 - 3000 + 1000
    assert kpis["Average days to approval"] == 5
    assert kpis["On time in full"] == 0  # the only line in full came 38 days late
    assert kpis["Delivered on time"] == 0
    assert kpis["Open lines past required date"] == 1  # item 20, required 1 February
    assert all(c.passed for c in result.checks), [c.label for c in result.checks if not c.passed]


def test_lines_hand_checked(result: Any) -> None:
    lines = result.tables["lines"].set_index(["PO", "Item"])
    first = lines.loc[("4100000001", "10")]
    assert first["Status"] == IN_FULL
    assert first["Receipts"] == 2
    assert first["Days to First Receipt"] == 30
    assert first["Delivery Period (days)"] == 60
    assert first["Days Late"] == 38  # planned 1 February, received 11 March
    assert first["Plant Name"] == "Kigali HQ"
    second = lines.loc[("4100000001", "20")]
    assert second["Status"] == PARTLY
    assert second["Received Qty"] == 30
    assert second["Not Traced vs ME2N"] == 0  # 50 - 30 - 20 still to be delivered
    assert lines.loc[("4100000002", "10"), "Status"] == OPEN
    open_lines = result.tables["open_lines"]
    assert open_lines["PO"].tolist() == ["4100000001", "4100000002"]  # oldest first
    assert open_lines["Age of Open PO (days)"].tolist() == [202, 152]
    assert result.tables["unmatched_receipts"]["Delivery"].tolist() == ["IB5"]


def test_breakdowns_hand_checked(result: Any) -> None:
    periods = result.tables["by_period"].set_index("Delivery Period")
    assert periods.loc["31 to 60 days", "PO Lines"] == 1
    assert periods["PO Lines"].sum() == 1
    suppliers = result.tables["by_supplier"]
    assert suppliers["Supplier"].tolist() == ["V2", "V1"]  # lowest value received first
    assert suppliers.set_index("Supplier").loc["V1", "Value Received"] == pytest.approx(13 / 15)


def test_period_must_be_in_order() -> None:
    with pytest.raises(ValidationError):
        Parameters(
            period_start=date(2026, 6, 30),
            period_end=date(2026, 1, 1),
            report_date=date(2026, 7, 1),
        )


def test_same_inputs_same_result() -> None:
    assert result_hash(ANALYSIS.compute(data(), PARAMS)) == result_hash(
        ANALYSIS.compute(data(), PARAMS)
    )


def test_reports(result: Any) -> None:
    files = ANALYSIS.reports(result, PARAMS, Templates())
    assert [f.kind for f in files] == ["xlsx", "html", "docx", "pptx"]
    for report in files:
        check_report(report.kind, report.content)


def test_on_time_against_the_required_date() -> None:
    inputs = data()
    inputs["orders"].loc[0, "Delivery Date"] = pd.Timestamp(2026, 3, 31)  # received 11 March
    result = ANALYSIS.compute(inputs, PARAMS)
    kpis = {k.label: k.value for k in result.metrics}
    assert kpis["On time in full"] == pytest.approx(1 / 3)
    assert kpis["Delivered on time"] == 1
    lines = result.tables["lines"].set_index(["PO", "Item"])
    assert lines.loc[("4100000001", "10"), "Approval to Receipt (days)"] == 55
    assert lines.loc[("4100000001", "10"), "Days Late"] == -20
    assert not lines.loc[("4100000002", "10"), "Overdue"]  # required 15 August


def test_stos_are_kept_and_flagged(result: Any) -> None:
    lines = result.tables["lines"].set_index(["PO", "Item"])
    assert lines.loc[("4100000002", "10"), "Order Type"] == STO
    assert lines.loc[("4100000001", "10"), "Order Type"] == PURCHASE_ORDER
    types = result.tables["by_order_type"].set_index("Order Type")
    assert types.loc[STO, "PO Lines"] == 1
    assert types.loc[PURCHASE_ORDER, "PO Lines"] == 2
    inputs = data()
    inputs["orders"].loc[0, "Purchasing Document"] = "7100000001"  # STO number range
    flagged = ANALYSIS.compute(inputs, PARAMS).tables["lines"]
    assert flagged.loc[flagged["PO"] == "7100000001", "Order Type"].tolist() == [STO]
