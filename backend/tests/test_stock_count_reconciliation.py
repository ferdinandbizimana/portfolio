"""Stock count reconciliation: cause rules and hand-checked figures on fake data."""

from datetime import date
from typing import Any

import pandas as pd
import pytest

from app.analyses.stock_count_reconciliation import (
    ABOVE,
    ANALYSIS,
    BELOW,
    NO_VARIANCE,
    OTHER,
    RECOUNT,
    Parameters,
    classify,
    clean_reason,
)
from app.jobs.analysis import result_hash
from app.reporting.documents import Templates
from app.reporting.guard import check_report


@pytest.mark.parametrize(
    ("reason", "cause"),
    [
        ("NO VARIANCE", NO_VARIANCE),
        ("no variance", NO_VARIANCE),
        ("NON MEDICAL ITEM", "Non-medical stock (outside count scope)"),
        ("Moving average difference", "Moving average price difference"),
        ("Counted, not posted in ERP", "Counted but not posted (EWM difference analyzer / MM)"),
        ("RECOUNTED", RECOUNT),
        ("QC PLANT NOT COUNTED", "Not counted – quality inspection (QI)"),
        ("Blocked stock not counted", "Not counted – blocked stock"),
        ("Stock in tRANSIT", "Not counted – stock in transit"),
        ("NOTE COUNTED", "Not counted – missed bins / locations"),
        ("SRAPPED AFTER COUNTING", "Scrapping posted after count"),
        ("CREDIT NOTE DONE AFTER COUNTING", "Credit notes / vendor returns after count"),
        ("DUSTRIBUTED AFTER COUNTING", "Sales / distribution posted after count"),
        ("RECEIPT AFTER COUNTING", "Goods receipts posted after count"),
        ("NEGATIVE ADJUSTMENT POSTED AFTER INVENTORY", "Adjustments / posting changes after count"),
        ("TRANSACTIONS POSTED AFTER COUNTING", "Other transactions posted after count"),
        ("Something else", OTHER),
    ],
)
def test_cause_rules_in_legacy_order(reason: str, cause: str) -> None:
    assert classify(clean_reason(reason)) == cause


def test_first_rule_wins() -> None:
    # "RECOUNT" comes before "SCRAP" and "SALES" in the rule order.
    assert classify("RECOUNT AFTER SCRAP AND SALES") == RECOUNT
    assert clean_reason("  sold\nafter count ") == "sold after count"


COLUMNS = [
    "ValA",
    "Material",
    "Description",
    "Sum of Closing Stock Posted In Finance",
    "Sum of Closing Value Posted In Finance",
    "Unit cost",
    "Counted Quantities",
    "Counted Value",
    "Diff Between Counted Value and Closing Value",
    "Reasons for differences where Applicable",
]
# Fake lines: plant, material, description, closing qty/value, unit cost, counted qty/value, diff
ROWS = [
    ["1000", "101", "Gloves", 10, 1000, 100, 10, 1000, 0, "NO VARIANCE"],
    ["1000", "102", "Masks", 10, 500, 50, 12, 600, 100, "RECEIPT AFTER COUNTING"],
    ["7000", "102", "Masks", 10, 500, 50, 8, 400, -100, "SOLD AFTER COUNTING"],  # offsets 1000
    ["7000", "103", "Kits", 5, 500, 100, 5, 700, 200, "RECOUNTED"],  # value not qty x cost
    ["9900", "104", "Tabs", 4, 400, 100, 0, 0, -400, "QC PLANT NOT COUNTED"],
    ["1071", "105", "Syringes", 2, 20, None, 2, 25, 5, "NO VARIANCE"],  # mislabelled
]
PARAMS = Parameters(count_date=date(2026, 6, 30))


def data() -> dict[str, pd.DataFrame]:
    plants = pd.DataFrame({"Plant": ["1000", "7000"], "Name 1": ["Kigali HQ", "Kigali Hub"]})
    return {"lines": pd.DataFrame(ROWS, columns=COLUMNS), "plants": plants}


@pytest.fixture(scope="module")
def result() -> Any:
    return ANALYSIS.compute(data(), PARAMS)


def test_summary_hand_checked(result: Any) -> None:
    summary = dict(
        zip(result.tables["summary"]["Measure"], result.tables["summary"]["Value"], strict=True)
    )
    assert summary["Closing value posted in Finance"] == 2920
    assert summary["Counted value"] == 2725
    assert summary["Total difference (counted - closing)"] == -195
    assert summary["Lines with a reason other than NO VARIANCE"] == 4
    assert summary["Net variance explained by reasons"] == -200  # 100 - 100 + 200 - 400
    assert summary["Gross variance explained by reasons"] == 800
    assert summary["Unexplained (total - explained)"] == 5  # the mislabelled NO VARIANCE line
    assert summary["NO VARIANCE lines with a difference above RWF 1"] == 1
    assert summary["Recount / duplicate count variance"] == 200
    assert summary["Net difference if the recount variance is reversed"] == -395
    assert summary["Offsetting materials (net under 5% of gross, several plants)"] == 1
    assert all(c.passed for c in result.checks), [c.label for c in result.checks if not c.passed]


def test_lines_hand_checked(result: Any) -> None:
    lines = result.tables["variance_lines"].set_index(["Plant", "Material"])
    assert lines.loc[("1000", "102"), "Direction"] == ABOVE
    assert lines.loc[("7000", "102"), "Direction"] == BELOW
    assert lines.loc[("7000", "103"), "Integrity Flag"] == "CHECK"  # 700 vs 5 x 100
    assert lines.loc[("7000", "103"), "Qty/Value Mismatch"]
    assert lines.loc[("9900", "104"), "Site"] == "Quarantine Store (QI)"
    assert lines.loc[("1000", "102"), "Site"] == "Kigali HQ (EWM–MM)"
    assert lines.loc[("1000", "102"), "Plant Name"] == "Kigali HQ"
    themes = result.tables["by_theme"].set_index("Theme")
    assert themes.loc["Period-end cut-off breach", "Gross"] == 200
    assert themes.loc["Non-countable stock status (QI / blocked / transit)", "Gross"] == 400
    assert result.tables["offsetting"]["Material"].tolist() == ["102"]


def test_same_inputs_same_result() -> None:
    assert result_hash(ANALYSIS.compute(data(), PARAMS)) == result_hash(
        ANALYSIS.compute(data(), PARAMS)
    )


def test_reports(result: Any) -> None:
    files = ANALYSIS.reports(result, PARAMS, Templates())
    assert [f.kind for f in files] == ["xlsx", "html", "docx", "pptx"]
    for report in files:
        check_report(report.kind, report.content)
