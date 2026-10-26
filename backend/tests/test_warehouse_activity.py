"""Warehouse activity: dock to stock and picking times, hand-checked on fake data."""

from datetime import date
from typing import Any

import pandas as pd
import pytest

from app.analyses.warehouse_activity import (
    ANALYSIS,
    DOCK_BANDS,
    OTHER,
    PICKING,
    PUTAWAY,
    Parameters,
    dock_band,
    kind_of,
    moment,
)
from app.jobs.analysis import result_hash
from app.reporting.documents import Templates
from app.reporting.guard import check_report

TASK_COLUMNS = [
    "Warehouse Task",
    "WT Item",
    "Whse Process Category Desc.",
    "Whse Proc. Category",
    "Document",
    "Product",
    "Source Storage Bin",
    "Destination Bin",
    "Warehouse Task Status",
    "Goods Receipt Date",
    "Created On",
    "Created At",
    "Confirmation Date",
    "Confirmation Time",
    "Confirmed By",
]
# Fake tasks: task, item, category, code, document, product, from, to, status, GR date,
# created on / at, confirmed on / at, user
TASKS: list[list[Any]] = [
    [
        "T1",
        "1",
        "Putaway",
        "1",
        "0180000001",
        "1001",
        "GR-ZONE",
        "A-01",
        "C",
        "2026-07-01",
        "2026-07-01",
        "08:00:00",
        "2026-07-01",
        "10:00:00",
        "U3",
    ],  # same day
    [
        "T2",
        "1",
        "Putaway",
        "1",
        "0180000001",
        "1002",
        "GR-ZONE",
        "A-02",
        "C",
        "2026-07-01",
        "2026-07-01",
        "08:00:00",
        "2026-07-03",
        "09:00:00",
        "U3",
    ],  # 2 days
    [
        "T3",
        "1",
        "Putaway",
        "1",
        "0180000002",
        "1003",
        "GR-ZONE",
        "A-03",
        "C",
        None,
        "2026-07-05",
        "08:00:00",
        "2026-07-05",
        "09:00:00",
        "U3",
    ],  # no goods receipt date
    [
        "T4",
        "1",
        "Stock Removal",
        "2",
        "0080000010",
        "1001",
        "A-01",
        "GI-ZONE",
        "C",
        None,
        "2026-07-10",
        "08:00:00",
        "2026-07-10",
        "09:30:00",
        "U1",
    ],  # 1.5 hours
    [
        "T4",
        "1",
        "Stock Removal",
        "2",
        "0080000010",
        "1001",
        "A-01",
        "GI-ZONE",
        "C",
        None,
        "2026-07-10",
        "08:00:00",
        "2026-07-10",
        "09:30:00",
        "U1",
    ],  # same task twice
    [
        "T5",
        "1",
        "Stock Removal",
        "2",
        "0080000010",
        "1002",
        "A-02",
        "GI-ZONE",
        "C",
        None,
        "2026-07-10",
        "09:00",
        "2026-07-10",
        "11:00",
        "U2",
    ],  # 2 hours, last pick 11:00
    [
        "T6",
        "1",
        "Internal Movement",
        "3",
        None,
        "1001",
        "A-01",
        "B-01",
        "C",
        None,
        "2026-07-11",
        "08:00:00",
        "2026-07-11",
        "08:30:00",
        "U1",
    ],
    [
        "T7",
        "1",
        "Putaway",
        "1",
        "0180000003",
        "1004",
        "GR-ZONE",
        "A-04",
        "",
        "2026-07-21",
        "2026-07-21",
        "08:00:00",
        None,
        None,
        None,
    ],  # open, created 21 July
    [
        "T8",
        "1",
        "Putaway",
        "1",
        "0180000004",
        "1005",
        "GR-ZONE",
        "A-05",
        "A",
        None,
        "2026-07-22",
        "08:00:00",
        None,
        None,
        None,
    ],  # cancelled
]
OBD = pd.DataFrame(
    {
        "Delivery": ["80000010"],
        "Act. Gds Mvmnt Date": [pd.Timestamp(2026, 7, 10)],
        "Goods Issue Date": [pd.Timestamp(2026, 7, 10)],
        "Goods Issue Time": ["15:00:00"],
    }
)
PARAMS = Parameters(report_date=date(2026, 7, 31))


def data(with_deliveries: bool = True) -> dict[str, pd.DataFrame]:
    tasks = pd.DataFrame(TASKS, columns=TASK_COLUMNS)
    for column in ("Goods Receipt Date", "Created On", "Confirmation Date"):
        tasks[column] = pd.to_datetime(tasks[column])
    tasks["Product Description"] = None
    tasks["Whse Process Type"] = None
    tasks["Act. Qty Dest. BUoM"] = 1.0
    return {"tasks": tasks, **({"deliveries": OBD.copy()} if with_deliveries else {})}


@pytest.fixture(scope="module")
def result() -> Any:
    return ANALYSIS.compute(data(), PARAMS)


def test_task_types_and_bands() -> None:
    assert kind_of("Putaway", "") == PUTAWAY
    assert kind_of("", "2") == PICKING
    assert kind_of("Internal Movement", "3") == OTHER
    assert [dock_band(d) for d in (0, 1, 2, 3, 4, 7, 8)] == [
        DOCK_BANDS[0],
        DOCK_BANDS[1],
        DOCK_BANDS[2],
        DOCK_BANDS[2],
        DOCK_BANDS[3],
        DOCK_BANDS[3],
        DOCK_BANDS[4],
    ]
    times = moment(pd.Series([pd.Timestamp(2026, 7, 1)] * 3), pd.Series(["14:05:30", "9:15", None]))
    assert times.tolist() == [
        pd.Timestamp(2026, 7, 1, 14, 5, 30),
        pd.Timestamp(2026, 7, 1, 9, 15),
        pd.Timestamp(2026, 7, 1),
    ]


def test_kpis_hand_checked(result: Any) -> None:
    kpis = {k.label: k.value for k in result.metrics}
    assert kpis["Putaways confirmed"] == 3
    assert kpis["Average dock to stock"] == 1  # (0 + 2) / 2
    assert kpis["Putaways within 2 days"] == 1  # 0 and 2 days, target 2 days
    assert kpis["Picks confirmed"] == 2  # T4 counted once
    assert kpis["Average picking time"] == pytest.approx(1.75)
    assert kpis["Average picking to goods issue"] == pytest.approx(4)  # 11:00 to 15:00
    assert kpis["Open tasks"] == 1
    assert all(c.passed for c in result.checks), [c.label for c in result.checks if not c.passed]


def test_tables_hand_checked(result: Any) -> None:
    kinds = result.tables["by_kind"].set_index("Task Type")
    assert kinds.loc[PUTAWAY].tolist() == [4, 3, 1]  # T8 cancelled
    assert kinds.loc[PICKING].tolist() == [2, 2, 0]
    bands = result.tables["dock_to_stock"].set_index("Dock to Stock")["Putaways"]
    assert (bands["Same day"], bands["2 to 3 days"], bands["No goods receipt date"]) == (1, 1, 1)
    assert result.tables["putaways"]["Warehouse Task"].tolist() == ["T2", "T1", "T3"]
    assert result.tables["open_tasks"]["Age (days)"].tolist() == [10]
    users = result.tables["by_user"]
    assert users["User"].tolist() == ["U3", "U1", "U2"]
    assert users["Tasks Confirmed"].tolist() == [3, 2, 1]
    assert result.tables["picking_to_goods_issue"]["Document"].tolist() == ["80000010"]


def test_without_the_delivery_list() -> None:
    kpis = {k.label: k.value for k in ANALYSIS.compute(data(False), PARAMS).metrics}
    assert kpis["Average picking to goods issue"] is None


def test_same_inputs_same_result() -> None:
    assert result_hash(ANALYSIS.compute(data(), PARAMS)) == result_hash(
        ANALYSIS.compute(data(), PARAMS)
    )


def test_reports(result: Any) -> None:
    files = ANALYSIS.reports(result, PARAMS, Templates())
    assert [f.kind for f in files] == ["xlsx", "docx", "pptx"]
    for report in files:
        check_report(report.kind, report.content)


MB51_COLUMNS = [
    "Plant",
    "Material",
    "Movement Type",
    "Quantity",
    "Amt.in Loc.Cur.",
    "WBS Element",
    "Reference",
]


def test_ewm_postings_missing_in_mb51() -> None:
    inputs = data()
    # The outbound delivery 80000010 was goods-issued in ERP (601); the inbound delivery
    # 180000001 (putaways T1, T2) has no goods receipt 101 in MB51.
    inputs["movements"] = pd.DataFrame(
        [
            ["1000", "1001", "601", -1, -10, "W", "0080000010"],
            ["1000", "1002", "101", 1, 10, "W", "189999999"],
        ],
        columns=MB51_COLUMNS,
    )
    result = ANALYSIS.compute(inputs, PARAMS)
    kpis = {k.label: k.value for k in result.metrics}
    assert kpis["Inbound deliveries without 101 in MB51"] == 1
    assert kpis["Outbound deliveries without goods issue in MB51"] == 0
    sync = result.tables["sync_issues"]
    assert sync["Document"].tolist() == ["180000001"]
    assert sync["Posting"].tolist() == ["Goods receipt"]
    files = ANALYSIS.reports(result, PARAMS, Templates())
    for report in files:
        check_report(report.kind, report.content)


def test_goods_issue_missing_in_mb51() -> None:
    inputs = data()
    inputs["movements"] = pd.DataFrame(
        [["1000", "1001", "101", 1, 10, "W", "180000001"]], columns=MB51_COLUMNS
    )
    kpis = {k.label: k.value for k in ANALYSIS.compute(inputs, PARAMS).metrics}
    assert kpis["Inbound deliveries without 101 in MB51"] == 0
    assert kpis["Outbound deliveries without goods issue in MB51"] == 1  # 80000010
    no_mb51 = {k.label: k.value for k in ANALYSIS.compute(data(), PARAMS).metrics}
    assert no_mb51["Inbound deliveries without 101 in MB51"] is None
