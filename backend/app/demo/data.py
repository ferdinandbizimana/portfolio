"""Fake SAP exports for every analysis: invented materials, plants, people and figures.

The files use the real SAP column headers so they are recognised like real
exports, but every material, plant name, customer, batch, quantity and value is
invented (fixed random seed: the same files every time). Nothing here comes from
RMS data. Dates cover the financial year July 2025 to June 2026, with the
reports at 30 June 2026 and the spot checks in September 2026.
"""

# Fake data from a fixed seed: the standard random generator is what is wanted here.
# ruff: noqa: S311
import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd

PRG, OWN = "RMS-PRG-FND-CP", "RMS-OWN-ESE-RM"
OPENING, CLOSING = date(2026, 3, 31), date(2026, 6, 30)
QUARTER_START = date(2026, 4, 1)
YEAR_START = date(2025, 7, 1)


@dataclass(frozen=True)
class Plant:
    code: str
    name: str
    city: str
    region: str


@dataclass(frozen=True)
class Material:
    code: str
    npc: str
    name: str
    unit: str
    cost: float
    programme: str  # weekly report sheet / programme category
    wbs: str
    amc: float  # national average monthly consumption, in units


@dataclass(frozen=True)
class Customer:
    code: str
    name: str
    district: str
    region: str


PLANTS = [
    Plant("1000", "Central warehouse (demo)", "Kicukiro", "City of Kigali"),
    Plant("7000", "Kigali hub (demo)", "Gasabo", "City of Kigali"),
    Plant("1002", "Drone delivery hub (demo)", "Muhanga", "Southern Province"),
    Plant("1071", "North branch (demo)", "Musanze", "Northern Province"),
    Plant("1072", "South branch (demo)", "Huye", "Southern Province"),
    Plant("1073", "East branch (demo)", "Kayonza", "Eastern Province"),
    Plant("1074", "West branch (demo)", "Rusizi", "Western Province"),
    Plant("9900", "Quarantine store (demo)", "Kicukiro", "City of Kigali"),
]
STOCK_PLANTS = [p.code for p in PLANTS if p.code != "9900"]
BRANCHES = ["1071", "1072", "1073", "1074"]

_ITEMS: list[tuple[str, str, float, str]] = [
    # name, unit, unit cost (RWF), weekly sheet
    ("Tenofovir/Lamivudine/Dolutegravir tab B/30", "EA", 6200, "ARV"),
    ("Abacavir/Lamivudine 120/60mg disp tab B/30", "EA", 4100, "ARV"),
    ("Atazanavir/Ritonavir 300/100mg tab B/30", "EA", 9800, "ARV"),
    ("Cotrimoxazole 960mg tab B/100", "EA", 1450, "ARV"),
    ("Fluconazole 200mg caps B/100", "EA", 2300, "ARV"),
    ("Artemether/Lumefantrine 20/120mg tab B/24", "EA", 1800, "MALARIA"),
    ("Malaria rapid diagnostic test kit B/25", "EA", 7600, "MALARIA"),
    ("Artesunate 60mg injection vial", "EA", 2100, "MALARIA"),
    ("Albendazole 400mg tab B/100", "EA", 2600, "MALARIA"),
    ("Long-lasting insecticide net", "EA", 3900, "MALARIA"),
    ("Rifampicin/Isoniazid 150/75mg tab B/672", "EA", 15200, "TB"),
    ("Ethambutol 400mg tab B/672", "EA", 9400, "TB"),
    ("TB sputum container 50ml", "EA", 85, "TB"),
    ("Oxytocin 10 IU/ml injection ampoule", "EA", 450, "MCCH"),
    ("Amoxicillin 250mg disp tab B/100", "EA", 2900, "MCCH"),
    ("Oral rehydration salts sachet", "EA", 120, "MCCH"),
    ("Zinc 20mg disp tab B/100", "EA", 1700, "MCCH"),
    ("Magnesium sulphate 50% injection vial", "EA", 780, "MCCH"),
    ("Paracetamol 500mg tab B/1000", "EA", 6400, "CPDS"),
    ("Examination gloves latex medium B/100", "EA", 4800, "CPDS"),
    ("Syringe 5ml with needle 21G", "EA", 65, "CPDS"),
    ("Sodium chloride 0.9% infusion 500ml", "EA", 690, "CPDS"),
    ("Surgical mask 3-ply B/50", "EA", 2500, "CPDS"),
    ("Metformin 500mg tab B/100", "EA", 1900, "NCDS"),
    ("Amlodipine 5mg tab B/100", "EA", 1600, "NCDS"),
    ("Insulin soluble 100 IU/ml vial 10ml", "EA", 5200, "NCDS"),
    ("Hepatitis B rapid test kit B/40", "EA", 18500, "HEPATITIS"),
    ("Ceftriaxone 1g injection vial", "EA", 610, "CPDS"),
    ("Ibuprofen 400mg tab B/100", "EA", 1350, "CPDS"),
    ("Captopril 25mg tab B/100", "EA", 1150, "NCDS"),
]
_SHEET_CATEGORY = {
    "ARV": "ARV and Opportunistic Infection",
    "MALARIA": "MALARIA AND NTD",
    "TB": "TB",
    "MCCH": "MCCH",
    "CPDS": "CPDS",
    "NCDS": "NCDS",
    "HEPATITIS": "Hepatitis",
}
_FACILITY_NAMES = [
    "CS Amahoro", "CS Umucyo", "CS Ubumwe", "CS Icyizere", "CS Imena", "CS Ituze",
    "HP Agaciro", "HP Ingabo", "HP Inyange", "DH Isangano", "DH Urumuri", "DH Inkingi",
    "RH Indatwa", "PH Ineza", "CS Umutekano", "CS Iriba", "CS Inganzo", "HP Uruyange",
]  # fmt: skip
_DISTRICTS = [
    ("Rusizi", "Western Province"), ("Rubavu", "Western Province"),
    ("Nyagatare", "Eastern Province"), ("Kayonza", "Eastern Province"),
    ("Huye", "Southern Province"), ("Muhanga", "Southern Province"),
    ("Musanze", "Northern Province"), ("Gicumbi", "Northern Province"),
    ("Gasabo", "City of Kigali"), ("Kicukiro", "City of Kigali"),
]  # fmt: skip
STAFF = ["Alice Demo", "Bosco Demo", "Claire Demo", "Didier Demo", "Esther Demo", "Fabrice Demo"]
PICKERS = ["Grace Demo", "Henri Demo", "Ines Demo", "Jean Demo", "Kevin Demo"]


def _materials() -> list[Material]:
    rng = random.Random(11)
    items = []
    for index, (name, unit, cost, sheet) in enumerate(_ITEMS, start=1):
        wbs = OWN if sheet in ("NCDS",) or (sheet == "CPDS" and index % 2) else PRG
        amc = float(rng.choice([300, 800, 1500, 4000, 9000, 20000]))
        items.append(
            Material(
                code=f"9100{index:04d}",
                npc=f"DEMO{index:03d}",
                name=f"{name} (demo)",
                unit=unit,
                cost=float(cost),
                programme=sheet,
                wbs=wbs,
                amc=amc,
            )
        )
    return items


MATERIALS = _materials()
CUSTOMERS = [
    Customer(f"C{index:04d}", f"{name} (demo)", *_DISTRICTS[index % len(_DISTRICTS)])
    for index, name in enumerate(_FACILITY_NAMES, start=1)
]


def sap_date(day: date) -> str:
    """SAP text date, day first (30.06.2026)."""
    return day.strftime("%d.%m.%Y")


def _days(start: date, end: date, rng: random.Random) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def category_of(material: Material) -> str:
    return _SHEET_CATEGORY[material.programme]


# --- Stock positions -----------------------------------------------------------------------


def stock_positions(day: date, seed: int) -> list[dict[str, Any]]:
    """Quantity per plant, material and WBS on a day (the same layout for every snapshot)."""
    rng = random.Random(seed)
    rows = []
    for material in MATERIALS:
        for plant in STOCK_PLANTS:
            if plant != "1000" and rng.random() < 0.35:
                continue
            scale = 1.0 if plant == "1000" else 0.15
            if int(material.code[-2:]) % 5 == 0:
                scale *= 6  # overstocked: more months of stock than shelf life
            quantity = round(material.amc * rng.uniform(0.5, 6.0) * scale)
            rows.append(
                {"plant": plant, "material": material, "wbs": material.wbs, "qty": quantity}
            )
    return rows


def gl_stock_lines() -> pd.DataFrame:
    """G/L line items of the stock accounts: one balance line per plant, material and WBS."""
    rows = []
    for position in stock_positions(CLOSING, 30):
        material = position["material"]
        rows.append(
            {
                "Plant": position["plant"],
                "Material": material.code,
                "Material Description": material.name,
                "WBS Element": position["wbs"],
                "Quantity": position["qty"],
                "Amount in Local Currency": round(position["qty"] * material.cost, 2),
                "G/L Account": "1310000",
                "Year/Month": "2025/12",
            }
        )
    return pd.DataFrame(rows)


def rbc_previous_report() -> pd.DataFrame:
    """The previous quarter's report data sheet (closing at 31 March = this opening)."""
    rows = []
    for position in stock_positions(OPENING, 31):
        material = position["material"]
        rows.append(
            {
                "Valuation Area": position["plant"],
                "Material": material.code,
                "Material Description": material.name,
                "WBS": position["wbs"],
                "Category": category_of(material),
                "Closing Stock": position["qty"],
                "Closing Value": round(position["qty"] * material.cost, 2),
                "Base Unit of Measure": material.unit,
            }
        )
    return pd.DataFrame(rows)


def item_categories() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SAP MATERIAL": [m.code for m in MATERIALS],
            "Category": [category_of(m) for m in MATERIALS],
            "Product description": [m.name for m in MATERIALS],
        }
    )


def ox10_plants() -> pd.DataFrame:
    rows = [
        {"Plant": p.code, "Name 1": p.name, "City": p.city, "Description": p.region} for p in PLANTS
    ]
    rows += [
        {"Plant": c.code, "Name 1": c.name, "City": c.district, "Description": c.region}
        for c in CUSTOMERS
    ]
    return pd.DataFrame(rows)


def material_master() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Material": [m.code for m in MATERIALS],
            "Old material number": [m.npc for m in MATERIALS],
            "Material Description": [m.name for m in MATERIALS],
            "Base Unit of Measure": [m.unit for m in MATERIALS],
        }
    )


# --- MB51: every goods movement of the year --------------------------------------------------


def mb51() -> pd.DataFrame:
    """Receipts, transfers between plants, customer deliveries and scrapping (Jul 25-Jun 26)."""
    rng = random.Random(51)
    rows: list[dict[str, Any]] = []
    document = 4900000000

    def add(plant: str, material: Material, kind: str, qty: float, day: date, **extra: Any) -> None:
        nonlocal document
        document += 1
        rows.append(
            {
                "Material Document": str(document),
                "Plant": plant,
                "Material": material.code,
                "Material Description": material.name,
                "Movement Type": kind,
                "Quantity": qty,
                "Amt.in Loc.Cur.": round(qty * material.cost, 2),
                "WBS Element": material.wbs,
                "Posting Date": sap_date(day),
                "Base Unit of Measure": material.unit,
                "Batch": extra.get("batch", ""),
                "Purchase order": extra.get("po", ""),
                "Reference": extra.get("reference", ""),
                "Sales order": extra.get("sales_order", ""),
                "Sales order item": extra.get("sales_item", ""),
            }
        )

    for index, material in enumerate(MATERIALS):
        for month in range(12):
            first = date(2025 + (6 + month) // 12, (6 + month) % 12 + 1, 1)
            last = first + timedelta(days=27)
            # Receipt from a supplier at the central warehouse.
            add(
                "1000",
                material,
                "101",
                round(material.amc * rng.uniform(0.6, 1.4)),
                _days(first, last, rng),
                batch=f"B{index:02d}{month:02d}",
                po=f"4100{index:03d}{month:03d}",
            )
            # Transfer to a branch: 641 at the central warehouse, 101 at the branch.
            branch = rng.choice(BRANCHES)
            qty = round(material.amc * rng.uniform(0.1, 0.3))
            sent = _days(first, last, rng)
            obd = f"87{index:03d}{month:05d}"
            sto = f"4500{index:03d}{month:03d}"
            add(
                "1000",
                material,
                "641",
                -qty,
                sent,
                batch=f"B{index:02d}{month:02d}",
                po=sto,
                reference=obd,
            )
            if month < 11 or rng.random() < 0.5:  # some June transfers still in transit
                add(
                    branch,
                    material,
                    "101",
                    qty,
                    sent + timedelta(days=rng.randint(2, 20)),
                    batch=f"B{index:02d}{month:02d}",
                    po=sto,
                    reference=obd,
                )
            # Customer deliveries.
            for kind in ("601", "Y01"):
                add(
                    rng.choice(["1000", *BRANCHES]),
                    material,
                    kind,
                    -round(material.amc * rng.uniform(0.2, 0.4)),
                    _days(first, last, rng),
                    batch=f"B{index:02d}{month:02d}",
                    reference=f"80{index:03d}{month:05d}",
                    sales_order=f"2{index:03d}{month:05d}",
                    sales_item="10",
                )
        # Expired stock scrapped, a few times a year.
        if index % 4 == 0:
            add(
                "9900",
                material,
                "551",
                -round(material.amc * 0.05),
                date(2026, 6, rng.randint(5, 28)),
                batch=f"BX{index:02d}",
            )
    return pd.DataFrame(rows)


# --- Year-end count -------------------------------------------------------------------------

_REASONS = [
    ("NO VARIANCE", 0.0),
    ("NO VARIANCE", 0.0),
    ("NO VARIANCE", 0.0),
    ("SALES POSTED AFTER COUNT", -1.0),
    ("STO POSTED AFTER THE COUNT", -1.0),
    ("GOODS RECEIPT POSTED IN JULY", 1.0),
    ("SCRAPPING POSTED AFTER COUNT", -1.0),
    ("STOCK IN TRANSIT NOT COUNTED", -1.0),
    ("ITEM IN QUALITY INSPECTION NOT COUNTED (QC PLANT)", -1.0),
    ("RECOUNT DONE AFTER FIRST COUNT", 1.0),
    ("ADJUSTMENT POSTED AFTER COUNT", -1.0),
    ("MOVING AVERAGE PRICE DIFFERENCE", 1.0),
]


def closing_vs_counted() -> pd.DataFrame:
    rng = random.Random(61)
    rows = []
    for position in stock_positions(CLOSING, 30):
        material = position["material"]
        closing_qty = position["qty"]
        reason, sign = rng.choice(_REASONS)
        difference = 0 if sign == 0 else round(sign * closing_qty * rng.uniform(0.01, 0.08))
        counted = closing_qty + difference
        closing_value = round(closing_qty * material.cost, 2)
        counted_value = round(counted * material.cost, 2)
        rows.append(
            {
                "ID": f"{position['plant']}{material.code}",
                "ValA": position["plant"],
                "Material": material.code,
                "Description": material.name,
                "Unit cost": material.cost,
                "Sum of Closing Stock Posted In Finance": closing_qty,
                "Sum of Closing Value Posted In Finance": closing_value,
                "Counted Quantities": counted,
                "Counted Value": counted_value,
                "Diff Between Counted Value and Closing Value": round(
                    counted_value - closing_value, 2
                ),
                "Reasons for differences where Applicable": reason,
            }
        )
    return pd.DataFrame(rows)


_ROOT_CAUSES = [
    ("Counting error / recount", "Recount and regularise in SAP"),
    ("Picking error", "Retrain the picking team"),
    ("Batch exchange (no material loss)", "Documented, no further action"),
    ("Goods receipt not posted", "Post the receipt and reconcile"),
    ("Prior adjustment reversal", "Documented, no further action"),
]


def gl_variance_lines() -> pd.DataFrame:
    """Stock adjustments posted after the physical inventory, with their investigation."""
    rng = random.Random(71)
    rows = []
    for number, position in enumerate(stock_positions(CLOSING, 30)):
        if rng.random() > 0.3:
            continue
        material = position["material"]
        amount = round(material.cost * rng.randint(-40, 40), 2) or material.cost
        status = rng.choices(["Justified", "Not Justified"], weights=[8, 2])[0]
        cause, action = rng.choice(_ROOT_CAUSES)
        rows.append(
            {
                "Plant": position["plant"],
                "Material": material.code,
                "Material Description": material.name,
                "WBS Element": position["wbs"],
                "Document Number": f"21200{number:05d}",
                "Posting Date": sap_date(date(2026, 7, rng.randint(1, 20))),
                "Quantity": round(-amount / material.cost),
                # G/L sign: a negative posting raises the stock (excess found).
                "Amount in Local Currency": -amount,
                "Final Validation Status": status,
                "Root cause": cause if status == "Justified" else "",
                "Action category": action if status == "Justified" else "",
                "REASON": cause.upper() if status == "Justified" else "",
            }
        )
    return pd.DataFrame(rows)


def final_closing_by_wbs() -> pd.DataFrame:
    rows = []
    for position in stock_positions(CLOSING, 30):
        material = position["material"]
        rows.append(
            {
                "Plant": position["plant"],
                "Material": material.code,
                "Material Description": material.name,
                "WBS": position["wbs"],
                "Final Qty": position["qty"],
                "Final Value": round(position["qty"] * material.cost, 2),
            }
        )
    return pd.DataFrame(rows)


# --- ZSTOCKREPORT snapshots and the weekly report -------------------------------------------


def zstockreport(day: date, seed: int) -> pd.DataFrame:
    """Batches on hand with expiry dates; some expired, some near expiry."""
    rng = random.Random(seed)
    rows = []
    for position in stock_positions(day, seed):
        material = position["material"]
        remaining = position["qty"]
        for batch_no in range(rng.randint(1, 3)):
            qty = remaining if batch_no == 2 else round(remaining * rng.uniform(0.3, 0.7))
            remaining -= qty
            if qty <= 0:
                continue
            months = rng.choices(
                [-2, 1, 2, 4, 5, 8, 14, 20, 30], weights=[1, 2, 2, 3, 3, 5, 6, 5, 4]
            )[0]
            rows.append(
                _batch(
                    material,
                    position,
                    f"{position['plant']}-{material.code[-3:]}-{batch_no}",
                    qty,
                    day + timedelta(days=round(months * 30.4)),
                )
            )
    return pd.DataFrame(rows)


def _batch(
    material: Material, position: dict[str, Any], batch: str, qty: float, expiry: date
) -> dict[str, Any]:
    return {
        "Material": material.code,
        "NPC CODE": material.npc,
        "Material Description": material.name,
        "Plant": position["plant"],
        "Storage Location": "0001",
        "Batch": batch,
        "Unrestricted": qty,
        "Quality Inspection": 0,
        "Blocked": 0,
        "WBS Element": position["wbs"],
        "Expiry Date": sap_date(expiry),
        "Unit Cost": material.cost,
        "Base Unit of Measure": material.unit,
    }


def zstockreport_after(opening: pd.DataFrame, day: date, seed: int) -> pd.DataFrame:
    """The next snapshot: batches used, cleared or expired since, and new receipts.

    Most batches that expired are blocked and moved to the quarantine plant 9900;
    a few are left where they are, as the monitoring should flag them.
    """
    rng = random.Random(seed)
    by_code = {m.code: m for m in MATERIALS}
    rows = []
    for _, line in opening.iterrows():
        expiry = pd.to_datetime(line["Expiry Date"], format="%d.%m.%Y").date()
        qty = float(line["Unrestricted"] + line["Blocked"])
        row: dict[str, Any] = {str(k): v for k, v in line.items()}
        if expiry <= day:
            if rng.random() < 0.75:
                continue  # sold, distributed or donated before it expired
            row["Unrestricted"], row["Blocked"] = 0, qty
            if rng.random() < 0.8:
                row["Plant"] = "9900"
            elif rng.random() < 0.5:
                row["Unrestricted"], row["Blocked"] = qty, 0
        else:
            left = round(qty * rng.uniform(0.3, 1.0))
            if left <= 0:
                continue
            row["Unrestricted"], row["Blocked"] = left, 0
            if rng.random() < 0.03:  # expiry date corrected after a batch check
                row["Expiry Date"] = sap_date(expiry + timedelta(days=rng.choice([-31, 61])))
        rows.append(row)
    for position in stock_positions(day, seed):
        if rng.random() < 0.5:
            material = by_code[position["material"].code]
            months = rng.choice([3, 5, 12, 18, 24, 36])
            rows.append(
                _batch(
                    material,
                    position,
                    f"{position['plant']}-{material.code[-3:]}-N",
                    round(position["qty"] * 0.5) or 1,
                    day + timedelta(days=round(months * 30.4)),
                )
            )
    return pd.DataFrame(rows)


def weekly_stock_monitoring() -> dict[str, pd.DataFrame]:
    """One sheet per programme: stock at the central warehouse, branches, SDPs and AMC."""
    rng = random.Random(81)
    sheets: dict[str, list[dict[str, Any]]] = {}
    for material in MATERIALS:
        sheet = material.programme if material.programme != "CPDS" else "LAB"
        if material.wbs == OWN:
            continue  # the weekly report follows programme products only
        central = round(material.amc * rng.uniform(0.2, 8))
        if int(material.code[-2:]) % 5 == 0:
            central *= 4  # far above the maximum level
        branches = round(material.amc * rng.uniform(0.1, 1))
        sdps = round(material.amc * rng.uniform(0.5, 3))
        sheets.setdefault(sheet, []).append(
            {
                "Product code": material.npc,
                "Product description": material.name.upper(),
                "Unit of measure (Pack Size)": "X1",
                "RMS central warehouse": central,
                "RMS Branches": branches,
                "SDPs": sdps,
                "Total": central + branches + sdps,
                "AMC": material.amc,
            }
        )
    return {name: pd.DataFrame(rows) for name, rows in sheets.items()}


def donations(opening: pd.DataFrame, closing: pd.DataFrame) -> pd.DataFrame:
    """Sales' list of products donated to save them from expiring (ZSTOCKREPORT lines).

    Batches that were due to expire in the quarter and are gone at closing, plus one
    pending request.
    """
    expiry = pd.to_datetime(opening["Expiry Date"], format="%d.%m.%Y").dt.date
    due = opening[(expiry > OPENING) & (expiry <= CLOSING)]
    left = set(zip(closing["Material"], closing["Batch"], strict=True))
    gone = due[[(m, b) not in left for m, b in zip(due["Material"], due["Batch"], strict=True)]]
    rows = gone.head(10).copy()
    rows["Total Value"] = (rows["Unrestricted"] + rows["Blocked"]) * rows["Unit Cost"]
    reasons = ["Short expiry", "Overstock at the branch", "Programme request"]
    rows["Status"] = ["Donated" if i < len(rows) - 1 else "Pending" for i in range(len(rows))]
    rows["Customer"] = [CUSTOMERS[i].name if i % 3 else "" for i in range(len(rows))]
    rows["Reason for Donation"] = [reasons[i % len(reasons)] for i in range(len(rows))]
    return rows.reset_index(drop=True)


def batch_movements(opening: pd.DataFrame, closing: pd.DataFrame) -> pd.DataFrame:
    """MB51 lines on the snapshot batches: short-dated distributions and scrapping."""
    rng = random.Random(53)
    by_code = {m.code: m for m in MATERIALS}
    expiry = pd.to_datetime(opening["Expiry Date"], format="%d.%m.%Y").dt.date
    soon = opening[(expiry > QUARTER_START) & (expiry <= CLOSING + timedelta(days=60))]
    rows: list[dict[str, Any]] = []

    def line(row: pd.Series, kind: str, qty: float, day: date) -> dict[str, Any]:
        material = by_code[row["Material"]]
        return {
            "Material Document": f"495{len(rows):07d}",
            "Plant": row["Plant"],
            "Material": material.code,
            "Material Description": material.name,
            "Movement Type": kind,
            "Quantity": qty,
            "Amt.in Loc.Cur.": round(qty * material.cost, 2),
            "WBS Element": row["WBS Element"],
            "Posting Date": sap_date(day),
            "Base Unit of Measure": material.unit,
            "Batch": row["Batch"],
            "Purchase order": "",
            "Reference": f"81{len(rows):06d}",
            "Sales order": "",
            "Sales order item": "",
        }

    for _, row in soon.head(12).iterrows():
        rows.append(
            line(
                row,
                rng.choice(["601", "Y01"]),
                -max(1.0, round(row["Unrestricted"] * 0.3)),
                _days(QUARTER_START, CLOSING - timedelta(days=30), rng),
            )
        )
    closing_expiry = pd.to_datetime(closing["Expiry Date"], format="%d.%m.%Y").dt.date
    expired = closing[(closing["Plant"] == "9900") & (closing_expiry <= CLOSING)]
    for _, row in expired.head(8).iterrows():
        when = min(
            CLOSING,
            pd.to_datetime(row["Expiry Date"], format="%d.%m.%Y").date()
            + timedelta(days=rng.randint(10, 80)),
        )
        rows.append(line(row, "551", -max(1.0, round(row["Blocked"] * 0.5)), when))
    return pd.DataFrame(rows)


def programme_issues(orders: pd.DataFrame, deliveries: pd.DataFrame) -> pd.DataFrame:
    """MB51 goods issues (601) of the programme (ZDON) deliveries, valued at cost."""
    costs = {m.code: m for m in MATERIALS}
    zdon = orders[orders["Sales Document Type"] == "ZDON"][
        ["Sales Document", "Sales Document Item"]
    ]
    lines = deliveries.merge(
        zdon,
        left_on=["Reference Document", "Reference Item"],
        right_on=["Sales Document", "Sales Document Item"],
    )
    rows = []
    for _, line in lines.iterrows():
        material = costs[line["Material"]]
        qty = -float(line["Actual delivery qty"])
        rows.append(
            {
                "Material Document": f"49{line['Delivery']}",
                "Plant": line["Plant"],
                "Material": material.code,
                "Material Description": material.name,
                "Movement Type": "601",
                "Quantity": qty,
                "Amt.in Loc.Cur.": round(qty * material.cost, 2),
                "WBS Element": PRG,
                "Posting Date": sap_date(date.fromisoformat(line["Goods Issue Date"])),
                "Base Unit of Measure": material.unit,
                "Batch": "",
                "Purchase order": "",
                "Reference": line["Delivery"],
                "Sales order": line["Reference Document"],
                "Sales order item": line["Reference Item"],
            }
        )
    return pd.DataFrame(rows)


# --- Sales orders, deliveries, purchase orders, transit, warehouse --------------------------


def va05_and_deliveries() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = random.Random(91)
    orders, deliveries = [], []
    delivery_no = 8000100000
    for number in range(1, 181):
        customer = rng.choice(CUSTOMERS)
        day = _days(QUARTER_START, CLOSING, rng)
        kind = rng.choices(["ZRMS", "ZSPO", "ZDON"], weights=[6, 2, 2])[0]
        plant = rng.choice(["1000", "1000", *BRANCHES])
        document = f"21{number:06d}"
        delivery_no += 1
        for item in range(1, rng.randint(2, 6)):
            material = rng.choice(MATERIALS)
            qty = rng.randint(5, 400)
            price = 0.0 if kind == "ZDON" else material.cost
            orders.append(
                {
                    "Sales Document": document,
                    "Sales Document Item": f"{item * 10:06d}",
                    "Sales Document Type": kind,
                    "Document Date": day.isoformat(),
                    "Sold-to Party": customer.code,
                    "Material": material.code,
                    "Order Quantity (Item)": qty,
                    "Confirmed Quantity": qty,
                    "Net Price": price,
                    "Net Value (Item)": round(qty * price, 2),
                    "Plant": plant,
                }
            )
            outcome = rng.random()
            if outcome < 0.08:
                continue  # not delivered
            delivered = qty if outcome > 0.25 else round(qty * rng.uniform(0.3, 0.9))
            issued = day + timedelta(days=rng.randint(1, 10))
            deliveries.append(
                {
                    "Delivery": str(delivery_no),
                    "Reference Document": document,
                    "Reference Item": f"{item * 10:06d}",
                    "Material": material.code,
                    "Item Description": material.name,
                    "Plant": plant,
                    "Delivery Quantity": delivered,
                    "Actual delivery qty": delivered,
                    "Goods Issue Date": issued.isoformat(),
                    "Act. Gds Mvmnt Date": issued.isoformat() if issued <= CLOSING else "",
                    "Ship-to Party": customer.code,
                    "Name ship-to party": customer.name,
                    "Sold-to Party Name": customer.name,
                    "Delivery Type": "LF",
                }
            )
    return pd.DataFrame(orders), pd.DataFrame(deliveries)


def purchase_orders_and_receipts() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = random.Random(101)
    suppliers = [("V100", "Supplier Alpha (demo)"), ("V200", "Supplier Beta (demo)"),
                 ("V300", "Supplier Gamma (demo)")]  # fmt: skip
    orders, receipts = [], []
    for number in range(1, 61):
        supplier, name = rng.choice(suppliers)
        created = _days(date(2026, 1, 1), date(2026, 6, 15), rng)
        approved = created + timedelta(days=rng.randint(1, 12))
        required = approved + timedelta(days=rng.randint(20, 60))
        po = f"41000{number:05d}"
        for item in range(1, rng.randint(2, 4)):
            material = rng.choice(MATERIALS)
            qty = round(material.amc * rng.uniform(0.5, 2))
            received = qty if rng.random() < 0.7 else round(qty * rng.uniform(0, 0.8))
            orders.append(
                {
                    "Purchasing Document": po,
                    "Item": f"{item * 10:05d}",
                    "Purchasing Doc. Type": "ZNB",
                    "Document Date": created.isoformat(),
                    "Final Approval Date": approved.isoformat(),
                    "Delivery Date": required.isoformat(),
                    "Supplier/Supplying Plant": supplier,
                    "Name of Supplier": name,
                    "Material": material.code,
                    "Short Text": material.name,
                    "Plant": "1000",
                    "Order Quantity": qty,
                    "Net Order Value": round(qty * material.cost, 2),
                    "Still to be delivered (qty)": qty - received,
                    "Still to be delivered (value)": round((qty - received) * material.cost, 2),
                }
            )
            if received:
                day = approved + timedelta(days=rng.randint(10, 75))
                if day > CLOSING:
                    day = CLOSING
                receipts.append(
                    {
                        "Delivery": f"18000{number:05d}",
                        "Purchasing Document": po,
                        "Reference Item": f"{item * 10:05d}",
                        "Material": material.code,
                        "Plant": "1000",
                        "Vendor": supplier,
                        "Supplier Name": name,
                        "Delivery Quantity": qty,
                        "Actual delivery qty": received,
                        "Goods receipt date": day.isoformat(),
                        "Act. Gds Mvmnt Date": day.isoformat(),
                    }
                )
    return pd.DataFrame(orders), pd.DataFrame(receipts)


def mb5t(movements: pd.DataFrame) -> pd.DataFrame:
    """Transfers issued (641) without a receipt yet: what MB5T shows at 30 June."""
    issued = movements[movements["Movement Type"] == "641"]
    received = set(movements.loc[movements["Movement Type"] == "101", "Reference"])
    open_lines = issued[~issued["Reference"].isin(received)]
    rows = []
    for _, line in open_lines.iterrows():
        rows.append(
            {
                "Supplying Plant": line["Plant"],
                "Purchasing Document": line["Purchase order"],
                "Plant": BRANCHES[int(line["Material"][-1]) % len(BRANCHES)],
                "Name 1": "",
                "Material": line["Material"],
                "Material Description": line["Material Description"],
                "Quantity": -line["Quantity"],
                "Amt.in Loc.Cur.": -line["Amt.in Loc.Cur."],
                "Base Unit of Measure": line["Base Unit of Measure"],
            }
        )
    return pd.DataFrame(rows)


def warehouse_tasks(deliveries: pd.DataFrame) -> pd.DataFrame:
    rng = random.Random(111)
    rows = []
    task = 300000
    for number in range(1, 121):
        material = rng.choice(MATERIALS)
        received = _days(QUARTER_START, CLOSING - timedelta(days=5), rng)
        task += 1
        done = received + timedelta(days=rng.choice([0, 0, 1, 1, 2, 3, 5]))
        rows.append(
            {
                "Warehouse Task": str(task),
                "WT Item": "1",
                "Whse Process Category Desc.": "Putaway",
                "Whse Proc. Category": "1",
                "Whse Process Type": "1011",
                "Document": f"18000{number:05d}",
                "Product": material.code,
                "Product Description": material.name,
                "Source Storage Bin": "GR-ZONE",
                "Destination Bin": f"HQ{rng.choice('ABCDE')}{rng.randint(1, 40):02d}A",
                "Warehouse Task Status": "C",
                "Goods Receipt Date": received.isoformat(),
                "Created On": received.isoformat(),
                "Created At": "08:30:00",
                "Confirmation Date": done.isoformat(),
                "Confirmation Time": f"{rng.randint(9, 16):02d}:15:00",
                "Confirmed By": rng.choice(STAFF).upper().replace(" ", ""),
                "Act. Qty Dest. BUoM": rng.randint(10, 500),
            }
        )
    for _, line in deliveries.head(150).iterrows():
        task += 1
        issued = date.fromisoformat(line["Goods Issue Date"])
        created = issued - timedelta(days=rng.randint(0, 2))
        rows.append(
            {
                "Warehouse Task": str(task),
                "WT Item": "1",
                "Whse Process Category Desc.": "Stock Removal",
                "Whse Proc. Category": "2",
                "Whse Process Type": "2010",
                "Document": line["Delivery"],
                "Product": line["Material"],
                "Product Description": line["Item Description"],
                "Source Storage Bin": f"HQ{rng.choice('ABCDE')}{rng.randint(1, 40):02d}B",
                "Destination Bin": "GI-ZONE",
                "Warehouse Task Status": rng.choices(["C", "A"], weights=[19, 1])[0],
                "Goods Receipt Date": "",
                "Created On": created.isoformat(),
                "Created At": "07:45:00",
                "Confirmation Date": created.isoformat(),
                "Confirmation Time": f"{rng.randint(8, 15):02d}:30:00",
                "Confirmed By": rng.choice(PICKERS).upper().replace(" ", ""),
                "Act. Qty Dest. BUoM": line["Delivery Quantity"],
            }
        )
    return pd.DataFrame(rows)


# --- Picking register and spot checks --------------------------------------------------------


def picking_register() -> dict[str, pd.DataFrame]:
    """Daily sheets (lines and discrepancies per picker) and one sheet per delivery."""
    rng = random.Random(121)
    sheets: dict[str, pd.DataFrame] = {}
    for day in range(1, 21):
        if date(2026, 6, day).weekday() >= 5:
            continue
        rows = []
        for picker in PICKERS:
            lines = rng.randint(30, 90)
            rows.append(
                {
                    "Pickers name": picker,
                    "Numbers of lines picked per day": lines,
                    "Number of descrepancies out of those lines": rng.choices(
                        [0, 1, 2, 3], weights=[10, 4, 2, 1]
                    )[0],
                }
            )
        sheets[f"{day}jun"] = pd.DataFrame(rows)
    orders = []
    for number in range(1, 61):
        orders.append(
            {
                "Date": date(2026, 6, rng.randint(1, 20)).isoformat(),
                "Outbound Delivery ( OBD ) Number": f"87000{number:05d}",
                "Number of Lines": rng.randint(3, 25),
                "Number of Lines with descrepancies": rng.choices([0, 1, 2], weights=[8, 2, 1])[0],
                "Pickers Name": rng.choice(PICKERS),
                "Customer/Branche Name": rng.choice(CUSTOMERS).name,
                "Type of Order": rng.choice(["ZRMS", "ZSPO", "ZDON", "STO"]),
                "Work Breakdown Structure ( WBS )": rng.choice([PRG, OWN]),
            }
        )
    sheets["OBD register"] = pd.DataFrame(orders)
    return sheets


_EXPLAINED = ["PICKED FOR OBD 87001234", "BIN TO BIN TO HQA05B", "SERVED TO CUSTOMER", "CORRECTED"]
_INTEGRITY = ["BATCH: B0991", "EXPIRATION: 31.10.2028", "DESCRIPTION DIFFERENT ON THE SHELF"]


def spot_check(seed: int, check_day: date) -> pd.DataFrame:
    """A week's spot check: EWM bin stock with the quantity found and the comment."""
    rng = random.Random(seed)
    rows = []
    for line in range(1, 181):
        material = rng.choice(MATERIALS)
        system = rng.randint(20, 3000)
        roll = rng.random()
        variance, comment = 0, ""
        if roll < 0.06:
            variance = rng.choice([-1, 1]) * rng.randint(1, 60)
        elif roll < 0.08:
            variance = -rng.randint(5, 50)
            comment = rng.choice(_EXPLAINED)
        elif roll < 0.11:
            comment = rng.choice(_INTEGRITY)
        rows.append(
            {
                "Storage Type": "7020",
                "Storage Bin": (
                    f"HQ{rng.choice('ABCDEFGH')}{rng.randint(1, 40):02d}{rng.choice('ABC')}"
                ),
                "Product": material.code,
                "Product Description": material.name,
                "Stock Type": "F2",
                "Batch": f"B{line:04d}",
                "Qty AUoM": system,
                "Uunit cost": material.cost,
                "Stock Reference Doc.": material.wbs,
                "Shelf Life Expiration Date": (
                    check_day + timedelta(days=rng.randint(60, 900))
                ).isoformat(),
                "Goods Receipt Date": (
                    check_day - timedelta(days=rng.randint(10, 300))
                ).isoformat(),
                "ONHAND QTY": system + variance,
                "VARIANCE": variance,
                "variance on cost": round(variance * material.cost, 2),
                "COMMENT": comment,
            }
        )
    return pd.DataFrame(rows)


def bin_owners(*checks: pd.DataFrame) -> pd.DataFrame:
    """Each bin of the spot checks with the staff member who corrects its variances."""
    bins = sorted({b for frame in checks for b in frame["Storage Bin"]})
    owners = pd.DataFrame(
        {
            "Storage Bin": bins,
            "Storage Type": "7020",
            "RESPONSIBLE PERSON": [STAFF[ord(b[2]) % len(STAFF)] for b in bins],
        }
    )
    # The e-mail block below the bins: name, then the address in the bin column.
    contacts = pd.DataFrame(
        {
            "Storage Bin": [f"{n.split()[0].lower()}.demo@example.com" for n in STAFF],
            "Storage Type": "",
            "RESPONSIBLE PERSON": STAFF,
        }
    )
    return pd.concat([owners, contacts], ignore_index=True)


def demo_stock_balance() -> pd.DataFrame:
    rows = []
    for position in stock_positions(CLOSING, 30):
        material = position["material"]
        rows.append(
            {
                "Plant": position["plant"],
                "Material": material.code,
                "Material Description": material.name,
                "Quantity": position["qty"],
                "Value": round(position["qty"] * material.cost, 2),
            }
        )
    return pd.DataFrame(rows)


# --- All files ---------------------------------------------------------------------------------

Sheets = dict[str, pd.DataFrame]


def all_files() -> dict[str, Sheets]:
    """File name -> sheets. Single-sheet files are written as CSV, the others as Excel."""
    orders, deliveries = va05_and_deliveries()
    opening = zstockreport(OPENING, 41)
    closing = zstockreport_after(opening, CLOSING, 42)
    movements = pd.concat(
        [mb51(), programme_issues(orders, deliveries), batch_movements(opening, closing)],
        ignore_index=True,
    )
    purchase_orders, receipts = purchase_orders_and_receipts()
    this_week, last_week = spot_check(131, date(2026, 9, 17)), spot_check(132, date(2026, 9, 10))
    return {
        "DEMO_GL_stock_lines_Jun2026.csv": {"GL": gl_stock_lines()},
        "DEMO_MB51_FY2025-26.csv": {"MB51": movements},
        "DEMO_OX10_plants_and_customers.csv": {"OX10": ox10_plants()},
        "DEMO_Previous_quarter_report_Mar2026.csv": {"CPDS Report": rbc_previous_report()},
        "DEMO_Item_categories.csv": {"ITEM Category": item_categories()},
        "DEMO_Material_master_MARA.csv": {"MARA": material_master()},
        "DEMO_Closing_vs_counted_Jun2026.csv": {"Closing vs Counted": closing_vs_counted()},
        "DEMO_Count_variance_lines_Jun2026.csv": {"Variance lines": gl_variance_lines()},
        "DEMO_Final_closing_by_WBS_Jun2026.csv": {"Final closing": final_closing_by_wbs()},
        "DEMO_ZSTOCKREPORT_31Mar2026.csv": {"ZSTOCK": opening},
        "DEMO_ZSTOCKREPORT_30Jun2026.csv": {"ZSTOCK": closing},
        "DEMO_Weekly_stock_monitoring_Jun2026.xlsx": weekly_stock_monitoring(),
        "DEMO_Donations_Apr-Jun2026.csv": {"Donations": donations(opening, closing)},
        "DEMO_VA05_sales_orders_Q4.csv": {"VA05": orders},
        "DEMO_Outbound_deliveries_Q4.csv": {"OBD": deliveries},
        "DEMO_ME2M_purchase_orders_H1.csv": {"ME2M": purchase_orders},
        "DEMO_Inbound_deliveries_H1.csv": {"IBD": receipts},
        "DEMO_MB5T_stock_in_transit_Jun2026.csv": {"MB5T": mb5t(movements)},
        "DEMO_EWM_warehouse_tasks_Q4.csv": {"Tasks": warehouse_tasks(deliveries)},
        "DEMO_Picking_register_Jun2026.xlsx": picking_register(),
        "DEMO_Spot_check_17Sep2026.csv": {"DETAIL": this_week},
        "DEMO_Spot_check_10Sep2026.csv": {"DETAIL": last_week},
        "DEMO_Storage_bins_responsible.csv": {"Bins": bin_owners(this_week, last_week)},
        "DEMO_Stock_balance.csv": {"Stock": demo_stock_balance()},
    }
