"""RBC programmes: report order and the names used for them in earlier reports.

Shared by the RBC accountability and count variance analyses. Source: the RBC
report of June 2026 (version 6), sheet "Category Mapping".
"""

import pandas as pd

# Report order of the programmes (RBC report, June 2026).
PROGRAMMES = [
    "CPDS",
    "MALARIA AND NTD",
    "ARV and Opportunistic Infection",
    "MCCH",
    "EI",
    "VMMC",
    "Cross Cutting",
    "Hepatitis",
    "TB",
    "NCDS",
]
DEFAULT_CATEGORY = "CPDS"

# Names found in earlier reports and the programme they are reported under.
CATEGORY_NAMES = {
    "ARV AND OPPORTUNITIC INFECTION": "ARV and Opportunistic Infection",
    "ARV&OI": "ARV and Opportunistic Infection",
    "MALARIA": "MALARIA AND NTD",
    "Program Lab": "CPDS",
    "ESE": "Cross Cutting",
    "Oncology": "Cross Cutting",
    "SPECIALIZED": "Cross Cutting",
}


def _key(text: str) -> str:
    return " ".join(text.split()).upper()


_NAME_LOOKUP = {_key(k): v for k, v in CATEGORY_NAMES.items()} | {_key(p): p for p in PROGRAMMES}


def normalise_category(value: object) -> str:
    text = "" if value is None or value is pd.NA else str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return _NAME_LOOKUP.get(_key(text), text)
