"""Frozen dashboard snapshots for visitors.

A snapshot is built once from a run's dashboard and stored on its own. It
keeps only what the chosen detail level allows: with "summary", every table
marked as line detail (and the charts drawn from it) is left out. Checks are
included only when asked. Notes that refer to the private workbook are
reworded, since visitors cannot download it.

Published dashboards are neutral (Ferdinand, 29 October 2026): RMS, Rwanda
Medical Supply, RBC and Rwanda Biomedical Centre are taken out of every text
of the snapshot (titles, labels, notes, table cells), and no logo is ever part
of a snapshot. RMS branding stays in the internal outputs only: downloaded
reports and e-mails.
"""

import re
import secrets
from typing import Any, Literal

from app.analyses.dashboard import Dashboard

DetailLevel = Literal["summary", "detail"]

_WORKBOOK_NOTE = re.compile(r"\s*All lines are in the Excel workbook\.")


_NAMES = [
    (re.compile(r"\bRwanda\s+Medical\s+Supply(\s+Ltd\.?)?", re.IGNORECASE), ""),
    (re.compile(r"\bRwanda\s+Biomedical\s+Cent(er|re)\b", re.IGNORECASE), "the programme partner"),
    (re.compile(r"\bRMS[-_]"), ""),  # WBS codes: RMS-OWN-ESE-RM -> OWN-ESE-RM
    (re.compile(r"\bRMS\b\s*"), ""),
    (re.compile(r"\bRBC\b"), "Programme"),
]
_TIDY = [
    (re.compile(r"\(\s*\)"), ""),
    (re.compile(r"^\s*[·:,\-\u2013]\s*|\s*[·:,\-\u2013]\s*$"), ""),
    (re.compile(r"\s+([·,.:;)])"), r"\1"),
    (re.compile(r"\s*·\s*·\s*"), " · "),
    (re.compile(r"\s{2,}"), " "),
]


def neutral_text(text: str) -> str:
    """The text without the names of the organisation and its programme partner."""
    changed = text
    for pattern, replacement in _NAMES:
        changed = pattern.sub(replacement, changed)
    if changed == text:
        return text
    for pattern, replacement in _TIDY:
        changed = pattern.sub(replacement, changed)
    changed = changed.strip()
    return changed[:1].upper() + changed[1:] if text[:1].isupper() else changed


def neutral(value: Any) -> Any:
    """Every text inside a snapshot (dicts, lists), made neutral; numbers untouched."""
    if isinstance(value, str):
        return neutral_text(value)
    if isinstance(value, dict):
        return {key: neutral(item) for key, item in value.items()}
    if isinstance(value, list):
        return [neutral(item) for item in value]
    return value


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
    return neutral(snapshot.model_dump())  # type: ignore[no-any-return]


def new_token() -> str:
    """An unguessable token for secret links (256 bits)."""
    return secrets.token_urlsafe(32)


def slug_base(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
    return slug or "dashboard"
