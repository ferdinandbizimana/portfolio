"""Expiry monitoring: two fake ZSTOCKREPORT snapshots, hand-checked figures."""

from datetime import date
from typing import Any

import pandas as pd
import pytest
from pydantic import ValidationError

from app.analyses.expiry_monitoring import (
    ANALYSIS,
    AT_RECEIVER_EXPIRED,
    CLEARED,
    EXPIRED_OUT,
    PARTLY,
    Parameters,
)
from app.jobs.analysis import result_hash
from app.reporting.documents import Templates
from app.reporting.guard import check_report

PRG, OWN = "RMS-PRG-FND-CP", "RMS-OWN-ESE-RM"
COLUMNS = [
    "Plant",
    "Material",
    "Material Description",
    "Batch",
    "Unrestricted",
    "Quality Inspection",
    "Blocked",
    "WBS Element",
    "Unit Cost",
    "Expiry Date",
    "NPC CODE",
]
# Fake batches (invented plants, materials and costs); dates as SAP text, day first.
OPENING = [
    ["1000", "M1", "Drug one", "B1", 100, 0, 0, PRG, 10, "15.05.2026", "N1"],  # due, cleared
    ["1000", "M2", "Drug two", "B2", 50, 0, 0, OWN, 20, "10.06.2026", "N2"],  # due, 20 left
    ["7001", "M3", "Kit three", "B3", 10, 0, 0, OWN, 5, "30.04.2026", "N3"],  # due, moved
    ["1000", "M4", "Drug four", "B4", 30, 0, 0, PRG, 2, "15.08.2026", "N4"],  # date changes
    ["1000", "M6", "Gel six", "B6", 0, 0, 5, PRG, 100, "31.01.2026", "N6"],  # expired earlier
]
CLOSING = [
    ["1000", "M2", "Drug two", "B2", 0, 0, 20, OWN, 20, "10.06.2026", "N2"],  # expired, blocked
    ["7002", "M3", "Kit three", "B3", 10, 0, 0, OWN, 5, "30.04.2026", "N3"],  # expired, not blocked
    ["1000", "M4", "Drug four", "B4", 30, 0, 0, PRG, 2, "15.09.2026", "N4"],  # within 3 months
    ["7001", "M5", "Drug five", "B5", 40, 0, 0, OWN, 3, "01.12.2026", "N5"],  # 3 to 6 months
    ["1000", "M6", "Gel six", "B6", 0, 0, 5, PRG, 100, "31.01.2026", "N6"],  # expired, blocked
]
MB51 = pd.DataFrame(
    [
        ["1000", "M4", "B4", "601", -10, -20, "20.06.2026", None],  # 2.8 months left
        ["7001", "M3", "B3", "641", -10, -50, "10.04.2026", "4500000001"],  # 0.7 months left
        ["7002", "M3", "B3", "101", 10, 50, "12.04.2026", "4500000001"],
        ["1000", "M6", "B6", "551", -1, -100, "15.06.2026", None],  # 135 days after expiry
        ["1000", "M5", "B5", "601", -5, -15, "20.06.2026", None],  # no batch in 1000: no date
    ],
    columns=[
        "Plant",
        "Material",
        "Batch",
        "Movement Type",
        "Quantity",
        "Amt.in Loc.Cur.",
        "Posting Date",
        "Purchase order",
    ],
).assign(**{"WBS Element": PRG, "Material Description": None})
PARAMS = Parameters(
    opening_date=date(2026, 3, 31), closing_date=date(2026, 6, 30), quarantine_plants="7002"
)


def snapshot(rows: list[list[Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=COLUMNS).assign(
        **{"Storage Location": None, "Material Type": None}
    )


def inputs() -> dict[str, pd.DataFrame]:
    return {
        "opening": snapshot(OPENING),
        "closing": snapshot(CLOSING),
        "movements": MB51.copy(),
        "plants": pd.DataFrame({"Plant": ["1000"], "Name 1": ["Head office"]}),
    }


@pytest.fixture(scope="module")
def result() -> Any:
    return ANALYSIS.compute(inputs(), PARAMS)


def test_kpis_hand_checked(result: Any) -> None:
    kpis = {k.label: k.value for k in result.metrics}
    assert kpis["Expired stock at closing"] == 950  # 400 + 50 + 500
    assert kpis["Expired batches"] == 3
    assert kpis["Expired batches not blocked"] == 1  # B3 at 7002
    assert kpis["Expired batches outside the quarantine plant"] == 2  # B2 and B6 at 1000
    assert kpis["Projected expiries in the period"] == 2050  # 1000 + 1000 + 50
    assert kpis["Expired of the projected"] == 450  # 20 x 20 + 10 x 5 (moved to 7002)
    assert kpis["Value saved"] == 1600
    assert kpis["Expiring within 3 months"] == 60
    assert kpis["Expiring in 3 to 6 months"] == 120
    assert kpis["Expiry dates changed"] == 1
    assert kpis["Distributed with a short shelf life"] == 70  # 20 + 50
    assert kpis["Average days from expiry to scrapping"] == 135
    assert all(c.passed for c in result.checks), [c.label for c in result.checks if not c.passed]


def test_outcomes_and_plants(result: Any) -> None:
    due = result.tables["due"].set_index("Batch")
    assert due.loc["B1", "Outcome"] == CLEARED
    assert due.loc["B2", "Outcome"] == PARTLY
    assert due.loc["B3", "Outcome"] == EXPIRED_OUT
    plants = result.tables["by_plant"].set_index("Plant")
    assert plants.loc["1000", "Value Saved"] == 1600
    assert plants.loc["7001", "Value Saved"] == 50
    assert plants.loc["7002", "Value Saved"] == -50  # the moved batch expired there
    assert plants.loc["1000", "Plant Name"] == "Head office"
    owners = result.tables["by_owner"].set_index("Owner")
    assert owners.loc["Commercial (RMS-OWN)", "Expired Value"] == 450
    assert owners.loc["Programme (RMS-PRG)", "Expired Value"] == 500


def test_movements(result: Any) -> None:
    moves = result.tables["distributions"].set_index("Movement Type")
    assert moves.loc["641", "At the Receiving Plant"] == AT_RECEIVER_EXPIRED
    assert moves.loc["641", "Receiving Plant"] == "7002"
    changes = result.tables["expiry_changes"]
    assert changes["Days Changed"].tolist() == [31]


def test_same_inputs_same_result() -> None:
    assert result_hash(ANALYSIS.compute(inputs(), PARAMS)) == result_hash(
        ANALYSIS.compute(inputs(), PARAMS)
    )


def test_reports(result: Any) -> None:
    files = ANALYSIS.reports(result, PARAMS, Templates())
    assert [f.kind for f in files] == ["xlsx", "html", "docx", "pptx"]
    for report in files:
        check_report(report.kind, report.content)


def test_without_movements_or_quarantine() -> None:
    data = inputs()
    del data["movements"]
    params = PARAMS.model_copy(update={"quarantine_plants": ""})
    result = ANALYSIS.compute(data, params)
    kpis = {k.label: k.value for k in result.metrics}
    assert kpis["Expired batches outside the quarantine plant"] is None
    assert kpis["Distributed with a short shelf life"] is None
    assert len(ANALYSIS.reports(result, params, Templates())) == 4


def test_dates_must_be_in_order() -> None:
    with pytest.raises(ValidationError):
        Parameters(opening_date=date(2026, 6, 30), closing_date=date(2026, 3, 31))


def test_quarantine_plant_9900() -> None:
    """Default: the quarantine plant is 9900; another plant starting with 99 is not."""
    data = inputs()
    closing = data["closing"]
    closing.loc[closing["Material"] == "M6", "Plant"] = "9900"  # expired gel moved to quarantine
    params = PARAMS.model_copy(
        update={"quarantine_plants": Parameters.model_fields["quarantine_plants"].default}
    )
    kpis = {k.label: k.value for k in ANALYSIS.compute(data, params).metrics}
    # B2 at 1000 and B3 at 7002 are expired outside quarantine; B6 is at 9900.
    assert kpis["Expired batches outside the quarantine plant"] == 2
    closing.loc[closing["Material"] == "M6", "Plant"] = "9901"  # not the quarantine plant
    kpis = {k.label: k.value for k in ANALYSIS.compute(data, params).metrics}
    assert kpis["Expired batches outside the quarantine plant"] == 3
