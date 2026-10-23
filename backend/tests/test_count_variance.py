"""Variance investigation: hand-checked figures on fake data."""

from datetime import date
from typing import Any

import pandas as pd
import pytest

from app.analyses.count_variance import (
    ANALYSIS,
    JUSTIFIED,
    NOT_JUSTIFIED,
    Parameters,
    status_of,
)
from app.jobs.analysis import result_hash
from app.reporting.documents import Templates
from app.reporting.guard import check_report

PRG, OWN = "RMS-PRG-FND-CP", "RMS-OWN-ESE-RM"
PENDING = "Not Justified – Pending"

# Fake variance lines (invented plants, materials and amounts). Variance = - amount.
LINES = pd.DataFrame(
    [
        [
            "1000",
            "Head office",
            "101",
            PRG,
            -100,
            "Justified",
            None,
            "Batch exchange",
            "Documented",
        ],
        ["1000", "Head office", "101", PRG, 300, "JUSTIFIED", None, "Netting-off", "Documented"],
        ["1000", "Head office", "102", OWN, 50, PENDING, None, "Unsupported", "Provide documents"],
        ["7000", "Hub", "201", OWN, -20, PENDING, None, "Unsupported", "Provide documents"],
        ["7000", "Hub", "202", "", 10, "Justified", 10, "Historical", "Retained earnings"],
        ["7000", "Hub", "203", PRG, 0, "Justified", 0, "Historical", "Retained earnings"],
    ],
    columns=[
        "Plant",
        "Plant Description",
        "Material",
        "WBS Element",
        "Amount in Local Currency",
        "Final Validation Status",
        "AMOUNT MOVED TO RETAINED EARNINGS",
        "Root cause",
        "Action category",
    ],
)
OPTIONAL = [
    "Stock Variance (RWF): + excess / - missing",
    "Material Description",
    "Quantity",
    "Document Number",
    "Posting Date",
    "G/L Account",
    "ACTION",
    "REASON",
]
CLOSING = pd.DataFrame(
    [["1000", "101", PRG, 10000], ["1000", "102", OWN, 4000], ["7000", "201", OWN, 6000]],
    columns=["Plant", "Material", "WBS", "Final Value"],
).assign(**{"Final Qty": None, "Plant Name": None, "Material Description": None})
PROGRAMMES = pd.DataFrame(
    {"Valuation Area": ["1000"], "Material": ["101"], "WBS": [PRG], "Category": ["MALARIA"]}
)
PARAMS = Parameters(count_date=date(2026, 6, 30))


def inputs(**extra: pd.DataFrame) -> dict[str, pd.DataFrame]:
    lines = LINES.copy()
    for column in OPTIONAL:
        lines[column] = None
    return {"variance_lines": lines, **extra}


@pytest.fixture(scope="module")
def result() -> Any:
    return ANALYSIS.compute(inputs(closing=CLOSING, programmes=PROGRAMMES), PARAMS)


def test_status_is_justified_in_any_capitals() -> None:
    assert status_of("JUSTIFIED") == JUSTIFIED
    assert status_of(" justified ") == JUSTIFIED
    assert status_of(PENDING) == NOT_JUSTIFIED
    assert status_of("") == NOT_JUSTIFIED


def test_headline_hand_checked(result: Any) -> None:
    head = result.tables["headline"].set_index("Category")
    # positive 100 + 20; negative -300 - 50 - 10; never offset
    assert head.iloc[0][["Lines", "Positive", "Negative", "Absolute"]].tolist() == [
        6,
        120,
        -360,
        480,
    ]
    assert head.loc[JUSTIFIED, ["Lines", "Positive", "Negative", "Absolute"]].tolist() == [
        4,
        100,
        -310,
        410,
    ]
    assert head.loc[NOT_JUSTIFIED, ["Lines", "Absolute"]].tolist() == [2, 70]
    assert head.loc[JUSTIFIED, "% of lines"] == pytest.approx(4 / 6)
    assert head.loc[NOT_JUSTIFIED, "% of absolute value"] == pytest.approx(70 / 480)


def test_justification_by_plant(result: Any) -> None:
    plants = result.tables["by_plant"].set_index("Plant")
    assert list(plants.index) == ["1000", "7000"]  # higher justified % first
    assert plants.loc["1000", ["Lines", "Justified lines", "Not Justified lines"]].tolist() == [
        3,
        2,
        1,
    ]
    assert plants.loc["1000", ["Justified value", "Not Justified value"]].tolist() == [400, 50]
    assert plants.loc["7000", "Justified % of value"] == pytest.approx(10 / 30)


def test_inventory_accuracy(result: Any) -> None:
    cat = result.tables["by_category"].set_index("Category")
    # all stock: 70 Not Justified / 20,000 inventory value
    assert cat.loc["All stock", "Total inventory value"] == 20000
    assert cat.loc["All stock", "Inventory variance"] == pytest.approx(0.0035)
    assert cat.loc["All stock", "Inventory accuracy"] == pytest.approx(0.9965)
    assert cat.loc["All stock", "Within tolerance"] == "Yes"
    assert cat.loc["RMS-own stock", "Inventory variance"] == pytest.approx(70 / 10000)
    assert cat.loc["RMS-own stock", "Within tolerance"] == "No"
    assert cat.loc["Program stock", "Inventory accuracy"] == 1
    assert cat.loc["  MALARIA AND NTD", "Total inventory value"] == 10000
    plants = result.tables["plant_accuracy"]
    assert list(plants["Plant"]) == ["Head office", "Hub"]
    assert plants["Inventory variance"].tolist() == pytest.approx([50 / 14000, 20 / 6000])
    kpi = {k.label: k.value for k in result.metrics}
    assert kpi["Inventory accuracy"] == pytest.approx(0.9965)


def test_root_causes_actions_and_retained(result: Any) -> None:
    causes = result.tables["root_causes"].set_index("Root cause")
    assert causes.loc["Netting-off", "Absolute"] == 300
    assert causes.loc["Unsupported", ["Lines", "Not Justified lines"]].tolist() == [2, 2]
    assert result.tables["actions"]["Lines"].sum() == 6
    # zero counts as a line; the variance is minus the amount moved
    assert result.extras["retained"] == {"Lines": 2, "Positive": 0, "Negative": -10, "Net": -10}
    assert all(c.passed for c in result.checks), [c.label for c in result.checks if not c.passed]


def test_without_closing_stock_there_is_no_accuracy() -> None:
    result = ANALYSIS.compute(inputs(), PARAMS)
    labels = [k.label for k in result.metrics]
    assert "Inventory accuracy" not in labels
    assert any("final closing stock" in n for n in result.dashboard.notes)
    assert all(c.passed for c in result.checks)


def test_given_stock_variance_column_is_checked_against_the_amount() -> None:
    data = inputs()
    data["variance_lines"]["Stock Variance (RWF): + excess / - missing"] = -data["variance_lines"][
        "Amount in Local Currency"
    ].astype(float)
    data["variance_lines"].loc[0, "Stock Variance (RWF): + excess / - missing"] = 999
    result = ANALYSIS.compute(data, PARAMS)
    sign = next(c for c in result.checks if c.key == "sign")
    assert (sign.actual, sign.passed) == (1, False)


def test_same_inputs_same_result() -> None:
    first = ANALYSIS.compute(inputs(closing=CLOSING), PARAMS)
    second = ANALYSIS.compute(inputs(closing=CLOSING), PARAMS)
    assert result_hash(first) == result_hash(second)


def test_reports(result: Any) -> None:
    files = ANALYSIS.reports(result, PARAMS, Templates())
    assert [f.kind for f in files] == ["xlsx", "docx", "pptx"]
    for report in files:
        check_report(report.kind, report.content)


def test_closing_stock_workbook_feeds_the_accuracy(tmp_path: Any) -> None:
    """The "Closing by ID and WBS" sheet made by this application is read back as closing."""
    import pyarrow.parquet as pq

    from app import datasets
    from app.analyses.closing_stock_wbs import ANALYSIS as CLOSING_ANALYSIS
    from app.analyses.closing_stock_wbs import Parameters as ClosingParameters
    from app.ingest.parse import parse_file
    from tests.test_closing_stock_wbs import inputs as closing_inputs

    closing_params = ClosingParameters(period_end=date(2026, 6, 30))
    closing_result = CLOSING_ANALYSIS.compute(closing_inputs(), closing_params)
    workbook = CLOSING_ANALYSIS.reports(closing_result, closing_params, Templates())[0].content
    path = tmp_path / "closing.xlsx"
    path.write_bytes(workbook)
    sheet = next(
        s for s in parse_file(path, tmp_path / "parsed") if s.name == "Closing by ID and WBS"
    )
    raw = pq.read_table(tmp_path / "parsed" / sheet.parquet_path).to_pandas()
    coerced = datasets.coerce(datasets.get("final_closing_by_wbs"), raw, sheet.header_row)
    assert coerced.ok, [i.message for i in coerced.issues]

    result = ANALYSIS.compute(inputs(closing=coerced.frame), PARAMS)
    kpi = {k.label: k.value for k in result.metrics}
    assert kpi["Total inventory value"] == 15100  # final closing of the closing-stock test
    assert all(c.passed for c in result.checks)


def test_runs_on_a_file_without_the_optional_columns() -> None:
    """As uploaded: only the required columns, everything read as text."""
    from app import datasets

    raw = LINES[
        ["Plant", "Material", "WBS Element", "Amount in Local Currency", "Final Validation Status"]
    ].astype(str)
    coerced = datasets.coerce(datasets.get("gl_variance_lines"), raw, header_row=1)
    assert coerced.ok
    result = ANALYSIS.compute({"variance_lines": coerced.frame}, PARAMS)
    retained: dict[str, float] = result.extras["retained"]  # type: ignore[assignment]
    assert retained["Lines"] == 0
    assert all(c.passed for c in result.checks)
