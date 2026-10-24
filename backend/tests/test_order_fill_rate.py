"""Order fill rate: hand-checked figures on fake data."""

from datetime import date
from typing import Any

import pandas as pd
import pytest
from pydantic import ValidationError

from app.analyses.order_fill_rate import (
    ANALYSIS,
    IN_FULL,
    NO_DELIVERY,
    NOT_DELIVERED,
    PARTLY,
    Parameters,
)
from app.jobs.analysis import result_hash
from app.reporting.documents import Templates
from app.reporting.guard import check_report

ORDER_COLUMNS = [
    "Sales Document",
    "Sales Document Item",
    "Document Date",
    "Sold-to Party",
    "Material",
    "Order Quantity (Item)",
    "Net Value (Item)",
]
# Fake VA05 lines: order, item, date, customer, material, quantity, value
ORDERS: list[list[Any]] = [
    ["0000000100", "000010", "2026-04-01", "C1", "0001", 10, 1000],
    ["0000000100", "000020", "2026-04-01", "C1", "0002", 5, 500],
    ["200", "10", "2026-05-10", "C2", "1", 8, 800],
    ["300", "10", "2026-06-15", "C2", "3", 4, 400],
    ["400", "10", "2026-07-02", "C2", "3", 4, 400],  # after the period
    ["500", "10", "2026-06-01", "C2", "3", 0, 0],  # zero quantity
]
DELIVERY_COLUMNS = [
    "Delivery",
    "Reference Document",
    "Reference Item",
    "Material",
    "Plant",
    "Actual delivery qty",
    "Delivery Quantity",
    "Act. Gds Mvmnt Date",
    "Sold-to Party Name",
    "Name ship-to party",
]
# Fake outbound delivery items
DELIVERIES: list[list[Any]] = [
    [
        "D1",
        "100",
        "000010",
        "0001",
        "1000",
        10,
        10,
        "2026-04-05",
        "Clinic One",
        None,
    ],  # full, 4 days
    ["D2", "100", "20", "2", "1000", 3, 3, "2026-04-06", "Clinic One", None],  # partly
    ["D3", "200", None, "0001", "7000", None, 9, "2026-05-20", None, "Clinic Two"],  # 9 of 8
    ["D4", "300", "10", "3", "7000", 4, 4, None, None, None],  # not goods issued yet
    ["D5", "999", "10", "3", "1000", 2, 2, "2026-05-01", None, None],  # no such order
]
PARAMS = Parameters(period_start=date(2026, 4, 1), period_end=date(2026, 6, 30))


def frame(rows: list[list[Any]], columns: list[str], dates: list[str]) -> pd.DataFrame:
    data = pd.DataFrame(rows, columns=columns)
    for column in dates:
        data[column] = pd.to_datetime(data[column])
    return data


def data() -> dict[str, pd.DataFrame]:
    deliveries = frame(DELIVERIES, DELIVERY_COLUMNS, ["Act. Gds Mvmnt Date"])
    deliveries["Actual delivery qty"] = deliveries["Actual delivery qty"].astype(float)
    return {
        "orders": frame(ORDERS, ORDER_COLUMNS, ["Document Date"]),
        "deliveries": deliveries,
        "plants": pd.DataFrame({"Plant": ["1000"], "Name 1": ["Kigali HQ"]}),
    }


@pytest.fixture(scope="module")
def result() -> Any:
    return ANALYSIS.compute(data(), PARAMS)


def test_kpis_hand_checked(result: Any) -> None:
    kpis = {k.label: k.value for k in result.metrics}
    assert kpis["Order lines"] == 4
    assert kpis["Line fill rate"] == 0.5
    assert kpis["Order fill rate"] == pytest.approx(1 / 3)  # only order 200
    assert kpis["Quantity fill rate"] == pytest.approx(21 / 27)  # 10 + 3 + 8 (capped) + 0
    assert kpis["Value fill rate"] == pytest.approx(2100 / 2700)  # 1000 + 300 + 800
    assert kpis["Average days to goods issue"] == 7  # (4 + 10) / 2
    assert all(c.passed for c in result.checks), [c.label for c in result.checks if not c.passed]


def test_lines_hand_checked(result: Any) -> None:
    lines = result.tables["lines"].set_index(["Sales Document", "Item"])
    assert lines.loc[("100", "10"), "Status"] == IN_FULL
    assert lines.loc[("100", "20"), "Status"] == PARTLY
    assert lines.loc[("200", "10"), "Status"] == IN_FULL  # matched by order and material
    assert lines.loc[("200", "10"), "Over-delivered Qty"] == 1
    assert lines.loc[("200", "10"), "Customer Name"] == "Clinic Two"
    assert lines.loc[("300", "10"), "Status"] == NOT_DELIVERED  # no goods issue
    assert lines.loc[("300", "10"), "Plant"] == NO_DELIVERY
    assert result.tables["unmatched_deliveries"]["Delivery"].tolist() == ["D5"]


def test_breakdowns_hand_checked(result: Any) -> None:
    plants = result.tables["by_plant"].set_index("Plant")
    assert plants.loc["1000", "Plant Name"] == "Kigali HQ"
    assert plants.loc["1000", "Value Fill Rate"] == pytest.approx(1300 / 1500)
    assert plants.loc["7000", "Value Fill Rate"] == 1
    assert plants.loc[NO_DELIVERY, "Value Fill Rate"] == 0
    months = result.tables["by_month"].set_index("Month")
    assert list(months.index) == ["2026-04", "2026-05", "2026-06"]
    assert months.loc["2026-04", "Line Fill Rate"] == 0.5
    customers = result.tables["by_customer"]
    assert customers["Customer"].tolist() == ["C2", "C1"]  # lowest value fill rate first


def test_all_deliveries_count_when_asked() -> None:
    params = PARAMS.model_copy(update={"goods_issued_only": False})
    lines = ANALYSIS.compute(data(), params).tables["lines"].set_index(["Sales Document", "Item"])
    assert lines.loc[("300", "10"), "Status"] == IN_FULL


def test_period_must_be_in_order() -> None:
    with pytest.raises(ValidationError):
        Parameters(period_start=date(2026, 6, 30), period_end=date(2026, 4, 1))


def test_same_inputs_same_result() -> None:
    assert result_hash(ANALYSIS.compute(data(), PARAMS)) == result_hash(
        ANALYSIS.compute(data(), PARAMS)
    )


def test_reports(result: Any) -> None:
    files = ANALYSIS.reports(result, PARAMS, Templates())
    assert [f.kind for f in files] == ["xlsx", "docx", "pptx"]
    for report in files:
        check_report(report.kind, report.content)
