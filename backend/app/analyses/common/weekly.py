"""The weekly stock monitoring report and its link to SAP materials.

Shared by the stock sufficiency (AMC) and expiry risk analyses. Rules from the
legacy w6 scripts and Ferdinand's answer of 23 October 2026 (Q3): weekly
product codes are linked to SAP materials through ZSTOCKREPORT "NPC CODE",
otherwise through the description; answer of 26 October 2026: the material
master (MARA) "Old material number" is the NPC code of each SAP "Material", and
is looked up first.
"""

from typing import Any

import pandas as pd

from app.analyses.common.closing import material_code

NO_AMC, OVERSTOCK, TO_PLAN = "No AMC reported", "Overstock", "Stocked to plan"
UNDERSTOCK, STOCK_OUT = "Understock", "Stock-out risk (<3 MOS)"
STATUSES = [STOCK_OUT, UNDERSTOCK, TO_PLAN, OVERSTOCK, NO_AMC]
STOCK_OUT_MOS = 3.0
DEFAULT_LEVELS = (6.0, 12.0)
# Programme of each weekly sheet (names as in the RBC report of June 2026) and
# its min / max months of stock.
SHEET_PROGRAMMES: list[tuple[str, str, tuple[float, float]]] = [
    ("ARV", "ARV and Opportunistic Infection", DEFAULT_LEVELS),
    ("HEPATITIS", "Hepatitis", DEFAULT_LEVELS),
    ("VMMC", "VMMC", DEFAULT_LEVELS),
    ("LAB", "Laboratory (HIV and program lab)", DEFAULT_LEVELS),
    ("MALARIA", "MALARIA AND NTD", DEFAULT_LEVELS),
    ("TB", "TB", DEFAULT_LEVELS),
    ("MCCH", "MCCH", (9.0, 14.0)),
]
BY_MASTER = "Old material number (MARA)"
BY_CODE, BY_DESCRIPTION, NOT_FOUND = "NPC CODE", "Description", "No SAP material found"


def programme_of(sheet: str) -> tuple[str, tuple[float, float]]:
    key = sheet.strip().upper()
    for prefix, programme, levels in SHEET_PROGRAMMES:
        if key.startswith(prefix):
            return programme, levels
    return sheet.strip(), DEFAULT_LEVELS


def _text(value: object) -> str:
    """Cell text with single spaces; blank for empty cells."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):  # type: ignore[call-overload]
        return ""
    return " ".join(str(value).split())


def norm(value: object) -> str:
    """Upper case, single spaces; blank for empty cells."""
    return _text(value).upper()


def _number(values: pd.Series) -> pd.Series:
    text = values.astype("string").str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(text, errors="coerce").astype(float)


def status_of(national_mos: float | None, minimum: float, maximum: float) -> str:
    if national_mos is None or pd.isna(national_mos):
        return NO_AMC
    if national_mos > maximum:
        return OVERSTOCK
    if national_mos >= minimum:
        return TO_PLAN
    if national_mos >= STOCK_OUT_MOS:
        return UNDERSTOCK
    return STOCK_OUT


def read_weekly(weekly: pd.DataFrame) -> pd.DataFrame:
    """Product lines of every programme sheet, in workbook order."""
    rows: list[dict[str, Any]] = []
    sheets = weekly["Sheet"] if "Sheet" in weekly.columns else pd.Series("", index=weekly.index)
    stopped: set[str] = set()
    for position, (_, row) in enumerate(weekly.iterrows()):
        sheet = str(sheets.iloc[position])
        if sheet in stopped:
            continue
        own_code = row.get("code")
        code = norm(own_code) or norm(row["Product code"])
        description = norm(row["Product description"])
        if description.startswith("STOCK STATUS") or code in ("PRODUCT CODE", "CODE"):
            stopped.add(sheet)  # the next block of the sheet starts here
            continue
        if not code and not description:
            continue
        if code.startswith(("TOTAL", "PRODUCT")) or description.startswith("TOTAL"):
            continue
        programme, (minimum, maximum) = programme_of(sheet)
        rows.append(
            {
                "Program": programme,
                "Sheet": sheet,
                "Product Code": code,
                "Product (weekly report)": _text(row["Product description"]),
                "Pack Size": _text(row.get("Unit of measure (Pack Size)")),
                "RMS HQ Stock": row["RMS central warehouse"],
                "RMS Branches Stock": row["RMS Branches"],
                "SDP Stock": row["SDPs"],
                "AMC": row["AMC"],
                "Min MOS": minimum,
                "Max MOS": maximum,
                "_description": description,
            }
        )
    lines = pd.DataFrame(rows)
    if lines.empty:
        return lines
    for column in ("RMS HQ Stock", "RMS Branches Stock", "SDP Stock", "AMC"):
        lines[column] = _number(lines[column])
    stock = ["RMS HQ Stock", "RMS Branches Stock", "SDP Stock"]
    lines[stock] = lines[stock].fillna(0.0)
    lines["RMS Stock"] = lines["RMS HQ Stock"] + lines["RMS Branches Stock"]
    lines["National Stock"] = lines["RMS Stock"] + lines["SDP Stock"]
    with_amc = lines["AMC"] > 0
    lines["MOS at RMS"] = (lines["RMS Stock"] / lines["AMC"]).where(with_amc)
    lines["MOS National"] = (lines["National Stock"] / lines["AMC"]).where(with_amc)
    lines["Status"] = [
        status_of(m, lo, hi)
        for m, lo, hi in zip(lines["MOS National"], lines["Min MOS"], lines["Max MOS"], strict=True)
    ]
    return lines


def _index(materials: pd.Series, keys: pd.Series) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for material, key in zip(materials, keys, strict=True):
        if key and material:
            found.setdefault(key, [])
            if material not in found[key]:
                found[key].append(material)
    return found


def master_codes(master: pd.DataFrame | None) -> pd.DataFrame:
    """Material master (MARA): SAP material, NPC code ("Old material number"), description."""
    if master is None:
        return pd.DataFrame(columns=["Material", "NPC", "Description"])
    return pd.DataFrame(
        {
            "Material": material_code(master["Material"]).astype(str),
            "NPC": master["Old material number"].map(norm),
            "Description": master["Material Description"].map(norm),
        }
    )


def link_materials(
    lines: pd.DataFrame, stock: pd.DataFrame, master: pd.DataFrame | None = None
) -> pd.DataFrame:
    """SAP materials of each weekly product.

    The NPC code is looked up in the material master (old material number) first,
    then in ZSTOCKREPORT "NPC CODE"; when neither has it, the description is used.
    `stock` and `master` have the columns Material, NPC and Description.
    """
    master = master if master is not None else master_codes(None)
    by_master = _index(master["Material"], master["NPC"])
    by_code = _index(stock["Material"], stock["NPC"])
    by_description = _index(
        pd.concat([master["Material"], stock["Material"]], ignore_index=True),
        pd.concat([master["Description"], stock["Description"]], ignore_index=True),
    )
    found, how = [], []
    for code, description in zip(lines["Product Code"], lines["_description"], strict=True):
        if code in by_master:
            found.append(sorted(by_master[code]))
            how.append(BY_MASTER)
        elif code in by_code:
            found.append(sorted(by_code[code]))
            how.append(BY_CODE)
        elif description in by_description:
            found.append(sorted(by_description[description]))
            how.append(BY_DESCRIPTION)
        else:
            found.append([])
            how.append(NOT_FOUND)
    lines = lines.copy()
    lines["SAP Materials"] = found
    lines["Linked by"] = how
    return lines
