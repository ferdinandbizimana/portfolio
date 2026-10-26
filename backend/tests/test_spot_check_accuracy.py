"""Spot check accuracy: hand-checked figures on fake data."""

from datetime import date
from typing import Any

import pandas as pd
import pytest

from app import datasets
from app.analyses.spot_check_accuracy import (
    ANALYSIS,
    NO_OWNER,
    THIS_CHECK,
    Parameters,
    keyword_pattern,
)
from app.jobs.analysis import result_hash
from app.reporting.documents import Templates
from app.reporting.guard import check_report, html_texts

PRG, OWN = "RMS-PRG-FND-CP", "RMS-OWN-ESE-RM"

# Fake spot check, as the dataset gives it (invented bins, products and costs).
THIS_WEEK = pd.DataFrame(
    [
        ["7020", "HQA01A", "P1", "Tabs (fake)", "B1", 100, 100, 0, 10, PRG, "SLOT 3"],
        ["7020", "HQA01B", "P2", "Caps (fake)", "B2", 200, 150, -50, 2, OWN, None],
        ["7020", "HQA02A", "P3", "Syrup (fake)", "B3", 50, 60, 10, 5, OWN, "20 PICKED FOR OBD 1"],
        ["7020", "HQA02B", "P1", "Tabs (fake)", "B4", 100, 100, 0, 10, PRG, "BATCH: B5"],
        ["7020", "hq a03a", "P4", "Gloves (fake)", "B6", 50, 45, -5, 4, PRG, "EXPIRATION: 2027"],
        [None, None, None, None, None, None, None, None, None, None, None],  # blank row
    ],
    columns=[
        "Storage Type",
        "Storage Bin",
        "Product",
        "Product Description",
        "Batch",
        "Qty AUoM",
        "Counted Quantities",
        "Variance",
        "Uunit cost",
        "Stock Reference Doc.",
        "Comments",
    ],
)
# The previous week's layout: available quantity only, no cost.
PREVIOUS = pd.DataFrame(
    {
        "Storage Bin": ["HQX01A", "HQX01B"],
        "Product": ["P1", "P2"],
        "Avail. Qty in AUoM": [100.0, 100.0],
        "Counted Quantities": [90.0, 100.0],
        "Variance": [-10.0, 0.0],
        "Comments": ["SERVED", None],
    }
)
BINS = pd.DataFrame(
    {"RESPONSIBLE PERSON": ["Alice (fake)", "Bob (fake)"], "Storage Bin": ["HQA01B", "HQA03A"]}
)
PARAMS = Parameters(check_date=date(2026, 9, 17), previous_label="Last week")


def coerced(frame: pd.DataFrame, key: str) -> pd.DataFrame:
    """The frame with every column of the dataset, as an upload gives it."""
    spec = datasets.get(key)
    out = frame.copy()
    for column in spec.columns:
        if column.name not in out.columns:
            out[column.name] = None
    return out


def inputs() -> dict[str, pd.DataFrame]:
    return {
        "spot_check": coerced(THIS_WEEK, "spot_check"),
        "previous": coerced(PREVIOUS, "spot_check"),
        "bins": BINS,
    }


@pytest.fixture(scope="module")
def result() -> Any:
    return ANALYSIS.compute(inputs(), PARAMS)


def test_lines_flags_and_owners(result: Any) -> None:
    lines = result.tables["lines"].set_index("Storage Bin")
    assert len(lines) == 5  # the blank row is left out
    assert lines.at["HQA03A", "Responsible"] == "Bob (fake)"  # "hq a03a" read as HQA03A
    assert lines.at["HQA01A", "Responsible"] == NO_OWNER
    assert lines.at["HQA02A", "Explained"] == "Yes"  # picked for an OBD
    assert lines.at["HQA01B", "Real Variance Line"] == "Yes"
    assert lines.at["HQA02B", "Data Integrity"] == "Yes"  # wrong batch, no variance
    assert lines.at["HQA01A", "Data Integrity"] == "No"  # "SLOT" is not "LOT"
    assert lines.at["HQA01B", "Variance Value"] == -100  # -50 x 2
    assert lines.at["HQA02A", "Real Variance"] == 0


def test_accuracy_hand_checked(result: Any) -> None:
    kpi = {k.label: k.value for k in result.metrics}
    # System 500, net variance -45, real net -55 (the explained +10 left out).
    assert kpi["Quantity accuracy"] == pytest.approx(1 - 45 / 500)
    assert kpi["True quantity accuracy"] == pytest.approx(1 - 55 / 500)
    # 3 of 5 lines with a variance, 2 not explained.
    assert kpi["Line accuracy"] == pytest.approx(0.4)
    assert kpi["True line accuracy"] == pytest.approx(0.6)
    assert kpi["Lines with a real variance"] == 2
    assert kpi["Net variance value"] == -70
    assert kpi["Data-integrity flags"] == 2
    assert kpi["True line accuracy, Last week"] == pytest.approx(1.0)
    assert all(c.passed for c in result.checks), [c.label for c in result.checks if not c.passed]


def test_previous_spot_check_and_summaries(result: Any) -> None:
    comparison = result.tables["comparison"].set_index("Check")
    assert list(comparison.index) == [THIS_CHECK, "Last week"]
    last = comparison.loc["Last week"]
    assert last["System Qty"] == 200  # from the available quantity
    assert last["Quantity Accuracy"] == pytest.approx(0.95)
    assert (last["Line Accuracy"], last["True Line Accuracy"]) == (0.5, 1.0)
    assert last["Net Variance Value"] == 0  # no cost in that file
    owners = result.tables["by_owner"].set_index("Responsible")
    assert owners.at["Alice (fake)", "Net Variance Value"] == -100
    assert owners.at["Bob (fake)", "Real Variance Lines"] == 1
    variances = result.tables["variances"]
    assert list(variances["Storage Bin"]) == ["HQA01B", "HQA02A", "HQA03A"]  # by |value|
    wbs = result.tables["by_wbs"].set_index("WBS")
    assert wbs.at[PRG, "Lines"] == 3


def test_keywords() -> None:
    pattern = keyword_pattern("BATCH, EX:")
    assert pattern is not None
    assert pattern.search("WRONG BATCH") and pattern.search("EX:31/05/2028")
    assert not pattern.search("NEXT:")  # EX: inside a word
    assert keyword_pattern(" , ") is None


def test_real_headers_are_recognised() -> None:
    """Both layouts of Ferdinand's spot check sheets are read as the spot check."""
    detail = [
        "Storage Type",
        "Storage Bin",
        "Product",
        "Product Description",
        "Stock Type",
        "Batch",
        "Qty AUoM",
        "Uunit cost",
        "Stock Reference Doc.",
        "ONHAND QTY",
        "VARIANCE",
        "variance on cost",
        "COMMENT",
    ]
    compiled = ["Storage Bin", "Product", "Batch", "Avail. Qty in AUoM", "SOH", "variance"]
    for headers in (detail, compiled):
        assert "spot_check" in [m.dataset for m in datasets.match_sheet(headers, "DETAIL")]


def test_reports_and_determinism(result: Any) -> None:
    files = ANALYSIS.reports(result, PARAMS, Templates())
    assert {f.kind for f in files} == {"xlsx", "html", "docx", "pptx"}
    for report in files:
        check_report(report.kind, report.content)
    page = next(f for f in files if f.kind == "html")
    assert "Data-integrity flags" in " ".join(html_texts(page.content))
    assert result_hash(ANALYSIS.compute(inputs(), PARAMS)) == result_hash(result)
