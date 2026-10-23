"""Final closing stock per plant, material and WBS element.

Shared by the closing-stock-by-WBS and RBC accountability analyses. Rules from
the legacy script `w5` (docs/legacy-analysis.md, section 3):

- the closing stock is the total of the G/L line items of the stock accounts
  per plant, material and WBS; lines without a material (subtotals) are left
  out and reported;
- the expired stock scrapped at Finance level (MB51 lines, negative) is
  deducted on the WBS shown on each scrapping line, never moved to another WBS;
- final closing = closing + scrapped.
- An MB51 file holds every goods movement; only the scrapping movement types
  are kept (551 GI scrapping project and 555 GI scrapping from blocked project
  stock, the types in the "Scrapped at Fin" sheet of the June 2026
  reconciliation).

Material numbers lose their leading zeros and plant codes are trimmed, so the
same item from both files is matched.
"""

from dataclasses import dataclass

import pandas as pd

NO_WBS = "No WBS in GL"
SCRAPPING_MOVEMENT_TYPES = "551, 555"


def movement_types(text: str) -> set[str]:
    """ "551, 555" -> {"551", "555"}."""
    return {part.strip() for part in text.replace(";", ",").split(",") if part.strip()}


KEYS = ["Plant", "Material", "WBS"]


def material_code(values: pd.Series) -> pd.Series:
    """Material numbers without leading zeros ("000123" and "123" are the same)."""
    text = values.astype("string").str.strip()
    stripped = text.str.lstrip("0")
    return stripped.where(stripped != "", text).fillna("")


def plant_code(values: pd.Series) -> pd.Series:
    return values.astype("string").str.strip().fillna("")


def wbs_code(values: pd.Series) -> pd.Series:
    text = values.astype("string").str.strip()
    return text.where(text.notna() & (text != ""), NO_WBS).astype(str)


@dataclass
class ClosingStock:
    lines: pd.DataFrame  # one row per plant, material and WBS
    gl_lines_used: int
    gl_lines_without_material: int
    gl_value_without_material: float
    gl_value_used: float
    scrap_lines: pd.DataFrame  # the scrapping lines, with normalised keys
    scrap_value: float
    scrap_lines_left_out: int = 0  # MB51 lines of other movement types


def _description(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """First non-empty description per material, in a stable order."""
    named = frame[["Material", column]].dropna()
    named = named[named[column].astype(str).str.strip() != ""]
    return (
        named.sort_values(["Material", column], kind="mergesort")
        .drop_duplicates("Material")
        .rename(columns={column: "Material Description"})
    )


def final_closing(
    gl: pd.DataFrame, scrap: pd.DataFrame, scrap_types: set[str] | None = None
) -> ClosingStock:
    """Closing, scrapped and final quantity and value per plant, material and WBS.

    `gl` has the columns of the dataset gl_stock_lines, `scrap` those of
    mb51_material_documents (only the scrapping lines).
    """
    gl = gl.assign(
        Plant=plant_code(gl["Plant"]),
        Material=material_code(gl["Material"]),
        WBS=wbs_code(gl["WBS Element"]),
        Quantity=gl["Quantity"].astype(float).fillna(0.0),
        Value=gl["Amount in Local Currency"].astype(float).fillna(0.0),
    )
    without_material = gl["Material"] == ""
    used = gl[~without_material]
    closing = (
        used.groupby(KEYS, sort=True)
        .agg(**{"Closing Qty": ("Quantity", "sum"), "Closing Value": ("Value", "sum")})
        .reset_index()
    )

    types = scrap["Movement Type"].astype("string").str.strip().fillna("")
    kept = types.isin(scrap_types) if scrap_types else pd.Series(True, index=scrap.index)
    left_out = int((~kept).sum())
    scrap = scrap[kept.to_numpy()]
    scrap = scrap.assign(
        Plant=plant_code(scrap["Plant"]),
        Material=material_code(scrap["Material"]),
        WBS=wbs_code(scrap["WBS Element"]),
        Quantity=scrap["Quantity"].astype(float).fillna(0.0),
        Value=scrap["Amt.in Loc.Cur."].astype(float).fillna(0.0),
    )
    scrapped = (
        scrap.groupby(KEYS, sort=True)
        .agg(**{"Scrapped Qty": ("Quantity", "sum"), "Scrapped Value": ("Value", "sum")})
        .reset_index()
    )

    lines = closing.merge(scrapped, on=KEYS, how="outer")
    amounts = ["Closing Qty", "Closing Value", "Scrapped Qty", "Scrapped Value"]
    lines[amounts] = lines[amounts].astype(float).fillna(0.0)
    lines["Final Qty"] = lines["Closing Qty"] + lines["Scrapped Qty"]
    lines["Final Value"] = lines["Closing Value"] + lines["Scrapped Value"]

    descriptions = pd.concat(
        [
            _description(used, "Material Description"),
            _description(scrap, "Material Description"),
        ]
    ).drop_duplicates("Material")
    lines = lines.merge(descriptions, on="Material", how="left")
    lines["Material Description"] = lines["Material Description"].fillna("").astype(str)
    lines = lines.sort_values(KEYS, kind="mergesort").reset_index(drop=True)

    return ClosingStock(
        lines=lines,
        gl_lines_used=len(used),
        gl_lines_without_material=int(without_material.sum()),
        gl_value_without_material=float(gl.loc[without_material, "Value"].sum()),
        gl_value_used=float(used["Value"].sum()),
        scrap_lines=scrap,
        scrap_value=float(scrap["Value"].sum()),
        scrap_lines_left_out=left_out,
    )


def plant_names(plants: pd.DataFrame | None) -> dict[str, str]:
    """Plant code -> name from the OX10 list (first name wins)."""
    if plants is None or plants.empty:
        return {}
    codes = plant_code(plants["Plant"])
    names = plants["Name 1"].astype("string").str.strip().fillna("")
    mapping: dict[str, str] = {}
    for code, name in zip(codes, names, strict=True):
        if code and code not in mapping:
            mapping[str(code)] = str(name)
    return mapping
