"""Frozen dashboard snapshots for visitors.

A snapshot is built once from a run's dashboard and stored on its own. It
keeps only what the chosen detail level allows: with "summary", every table
marked as line detail (and the charts drawn from it) is left out. Checks are
included only when asked. Notes that refer to the private workbook are
reworded, since visitors cannot download it.
"""

import re
import secrets
from typing import Any, Literal

from app.analyses.dashboard import Dashboard

DetailLevel = Literal["summary", "detail"]

_WORKBOOK_NOTE = re.compile(r"\s*All lines are in the Excel workbook\.")


def build_snapshot(
    dashboard: dict[str, Any], detail_level: DetailLevel, include_checks: bool
) -> dict[str, Any]:
    source = Dashboard.model_validate(dashboard)
    tables = [
        table.model_copy(update={"note": _WORKBOOK_NOTE.sub("", table.note).strip()})
        for table in source.tables
        if detail_level == "detail" or table.level == "summary"
    ]
    kept = {table.id for table in tables}
    snapshot = source.model_copy(
        update={
            "tables": tables,
            "charts": [chart for chart in source.charts if chart.table in kept],
            "checks": source.checks if include_checks else [],
        }
    )
    return snapshot.model_dump()


def new_token() -> str:
    """An unguessable token for secret links (256 bits)."""
    return secrets.token_urlsafe(32)


def slug_base(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
    return slug or "dashboard"
