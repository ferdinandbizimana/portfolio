"""Interactive HTML dashboards: self-contained, data packed, banned wording caught."""

from typing import Any

import pandas as pd
import pytest

from app.reporting.guard import BannedWordingError, check_report
from app.reporting.interactive import (
    ChartSpec,
    DashSection,
    DetailSpec,
    Filter,
    InteractiveDashboard,
    KpiTile,
    Measure,
    TableSpec,
    build_html,
    read_payload,
)


def dashboard(description: str = "Gloves (fake)") -> InteractiveDashboard:
    facts = pd.DataFrame(
        {
            "Plant": ["P1", "P1", "P2"],
            "Item": [description, "Syringe (fake)", "Syringe (fake)"],
            "Qty": [10.0, 5.0, None],
            "Done": [True, False, True],
        }
    )
    return InteractiveDashboard(
        title="Fake dashboard",
        subtitle="Invented data",
        facts={"lines": facts},
        measures={
            "lines": (
                Measure("n", "Lines", count=True),
                Measure("qty", "Quantity", sum="Qty"),
                Measure("done", "Done", count=True, where=("Done", ("Yes",))),
                Measure("rate", "Done %", "pct", ratio=("done", "n")),
            )
        },
        filters=(Filter("Plant", "Plant", "All plants"),),
        kpis=(KpiTile("Done", "rate", "lines", "{done} of {n} lines"),),
        sections=(
            DashSection(
                "A · Plants",
                blocks=(
                    ChartSpec("By plant", "lines", "Plant", ("rate",), percent=True),
                    TableSpec("By plant", "lines", ("Plant",), ("n", "qty", "rate")),
                    DetailSpec("Lines", "lines", (("Item", "Item", "text"), ("Qty", "Qty", "int"))),
                ),
            ),
        ),
        checks=[("Lines = 3", 3, 3, True)],
    )


def payload(content: bytes) -> dict[str, Any]:
    data = read_payload(content)
    assert data is not None
    return data


def test_self_contained_and_packed() -> None:
    content = build_html(dashboard())
    page = content.decode()
    assert "<title>Fake dashboard</title>" in page
    assert " src=" not in page and "<link" not in page  # nothing loaded from outside
    data = payload(content)
    lines = data["facts"]["lines"]
    assert lines["rows"] == 3
    assert lines["columns"]["Qty"] == {"n": [10, 5, None]}
    done = lines["columns"]["Done"]
    assert [done["d"][i] for i in done["i"]] == ["Yes", "No", "Yes"]
    assert data["sections"][0]["blocks"][0]["type"] == "chart"
    check_report("html", content)


def test_same_dashboard_same_bytes() -> None:
    assert build_html(dashboard()) == build_html(dashboard())


def test_banned_wording_in_the_data_is_caught() -> None:
    with pytest.raises(BannedWordingError):
        check_report("html", build_html(dashboard("Test kit, AI reader")))
