# Legacy scripts: what they do

This is a reading of the scripts in `legacy/` (FY2025/26 analyses). They are the
reference for business rules, file formats and expected outputs. They are not
production code: paths are hard-coded, steps pass data through pickle files, and
several preparation scripts are missing (see "Gaps" in each section and the
summary at the end).

Notation used below:

- **ID** = plant code followed by material number, e.g. plant `7000` + material
  `1000000546` → `70001000000546`.
- **RWF** = Rwandan franc. All values in the reports are RWF.
- **OX10** = SAP plant list export; only the first two columns are used
  (plant code, plant name).

---

## 1. `w2`, `w3` — Year-end stock count reconciliation (count vs MB5B)

`w2` is the first version; `w3` is the final version. `w2/prep.py` and
`w3/prep0.py` are identical. Use `w3` as the reference.

### Inputs

| File | Used for | Columns used (as named in the scripts) |
|---|---|---|
| Reconciliation workbook, sheet "Closing vs Counted branches" (MB5B with reconciliation of stock and Finance) | One line per ID | after renaming: `ID`, `ValA` (plant / valuation area), `Material`, `Description`, `ClosQty`, `ClosVal`, `UC` (unit cost), `CntQty`, `CntVal`, `Diff`, `Reason` |
| OX10 | Plant names | column 1 = plant code, column 2 = plant name |

Gap: the step that reads the workbook and renames its columns to the short
names above (it produced `d.pkl`) is not in the folder. **The real SAP / Excel
column headers of this sheet are unknown.**

### Rules (`w3/prep.py`, `w3/content.py`)

1. Join plant names from OX10 on plant code.
2. Clean the free-text `Reason` (remove line breaks, trim), then classify it
   with ordered keyword rules (upper case, first match wins) into **causes**:

   | Order | Keywords (any) | Cause |
   |---|---|---|
   | 1 | exactly `NO VARIANCE` | NO VARIANCE (excluded from cause analysis) |
   | 2 | `NON MEDICAL` | Non-medical stock (outside count scope) |
   | 3 | `MOVING AVERAGE` | Moving average price difference |
   | 4 | `GL LEVEL`, `DIFF ANALYSER`, `NOT POSTED IN ERP` | Counted but not posted (EWM difference analyzer / MM) |
   | 5 | `RECOUNT`, `COUNTED TWICE`, `COUNTED,ADJ` | Recount / duplicate count |
   | 6 | `QC PLANT`, `QUALITY INSPECTION` | Not counted – quality inspection (QI) |
   | 7 | `BLOCKED` and `NOT` | Not counted – blocked stock |
   | 8 | `TRANSIT`, `RANSIT` | Not counted – stock in transit |
   | 9 | `NOT COUNTED`, `NOTE COUNTED`, `NOT CONTED` | Not counted – missed bins / locations |
   | 10 | `SCRAP`, `SRAPP` | Scrapping posted after count |
   | 11 | `CREDIT NOTE`, `RETURN TO VENDOR` | Credit notes / vendor returns after count |
   | 12 | `SALES`, `SOLD`, `DISTRIBUT`, `DUSTRIBUT`, `STO POSTED` | Sales / distribution posted after count |
   | 13 | `RECEIPT`, `POSTED IN JULY` | Goods receipts posted after count |
   | 14 | `ADJUST`, `VARIANCE`, `VARAINCE`, `BACKADATED`, `POSTING CHANGE` | Adjustments / posting changes after count |
   | 15 | `TRANSACTIONS POSTED AFTER` | Other transactions posted after count |
   | — | none | Other |

   The misspellings are intentional: they match how reasons are typed in the file.
   `POSTED IN JULY` is specific to a June year-end.

3. Group causes into six **SAP root-cause themes**: period-end cut-off breach
   (all "posted after count" causes); non-countable stock status (QI, blocked,
   transit); count execution and warehouse layout (missed bins, recount);
   EWM–MM integration / posting failure; count scope (non-medical); valuation
   and master data (moving average price).
4. Map plants to **sites**: 7000 → Kigali Hub (EWM–MM); 1000 → Kigali HQ
   (EWM–MM); 9900 → Quarantine Store (QI); 1002 → Zipline; all others →
   District branches (MM).
5. Calculations per line:
   - Variance value = counted value − closing value (`Diff`).
   - Variance qty = counted qty − closing qty.
   - Direction: > +0.5 "Count above books", < −0.5 "Count below books", otherwise "No value difference".
   - Gross variance = sum of absolute differences; net = signed sum.
   - Value integrity: counted value should equal counted qty × unit cost
     (if unit cost is missing, use counted value). Gap > RWF 1 → flag "CHECK".
   - Recount lines: the net difference is also shown with recount variance reversed.
   - "Mislabelled NO VARIANCE": reason is NO VARIANCE but |difference| > RWF 1.
   - Quantity/value mismatch: variance qty = 0 but |difference| > RWF 1.
   - Offsetting materials: same material in more than one plant whose net
     difference is under 5% of its gross (e.g. a transfer in transit).
6. `w2` also split variance into a quantity effect (variance qty × unit cost)
   and a price effect (difference − quantity effect); `w3` dropped this.

### Self-checks in the workbook

- Total difference = counted value − closing value.
- Unexplained = total difference − net variance explained by reasons (should be 0).
- `w2`: explained + mislabelled − total difference (should be 0).
- Every summary table total is a live formula over the line sheet.

### Outputs

- **Detailed workbook** (`build_xlsx.py`): Read Me; Summary (headline figures,
  tables by theme / cause / site / plant, three charts); Variance Lines (all
  formulas live); Theme x Plant matrix; Data Integrity; Root Causes; Action
  Plan (status dropdown); Period-End Calendar (D-10 to D+5); Analysis Prompt.
- **Word report** (`report.js`, Node `docx`): memo to the Finance Manager with
  purpose, summary, scope and method, results tables, findings and root causes
  per theme, EWM–MM integration assessment, recommendations, calendar,
  actions to close the year, and a sign-off table (Finance Senior Inventory
  Officer, Finance Manager).
- **Slide deck** (`deck.js`, Node `pptxgenjs`): about ten slides — opening,
  findings by theme and site, cut-off breach by transaction type, root
  causes, next inventory, close.
- **HTML dashboard** (`dash_template.html`, data injected at `__DATA__`):
  filters for site, plant, theme, cause and direction; KPI tiles; charts by
  theme, cause, site (above / below books) and plant (stacked by theme); top
  ten lines; root-cause cards; recommendations.

Gaps: `report_data.json` and `deck_data.json` (pre-aggregated tables for the
Word report and the deck) are produced by a script that is not in the folder.
They can be rebuilt from the rules above.

The narrative text (root causes, the eight recommendations R1–R8, the
calendar) is hand-written for FY2026 and stored in `content.py`. Some sentences
quote figures typed by hand rather than calculated.

---

## 2. `w4` — Reconciliation report and deck on RMS templates

Same content as `w3`, laid out on the organisation's templates.

- `build_doc.py`: opens an **unzipped RMS Word template** (folder `dx`), keeps
  the first 14 cover paragraphs (replacing the title and committee name),
  keeps the template's table-of-contents and list-of-tables headings, then
  writes a new body as raw WordprocessingML: numbered headings with
  bookmarks, captions with `SEQ Table` fields, KPI tiles, tables, PNG charts
  (`fig_theme.png`, `fig_site.png`, `fig_cutoff.png`) and the approval table.
  It removes the template's old images except the logo and re-zips.
- `pages.py`: converts the document to PDF, finds which page each heading and
  table caption landed on, and writes `pages.json` so a second pass of
  `build_doc.py` can fill page numbers in the table of contents.
- `deck2.js`: RMS-branded deck using `logo.png` and `title_photo.jpeg`.

Gaps: the template folders, images and chart PNGs are not in the zip; the
script that drew the PNG charts is not in the folder.

Lesson for the application: template support means "keep the template's
cover, styles, header, footer and logo; replace the body". This is easier with
placeholders in the template (e.g. `{{ title }}`, `{{ body }}`) than with
paragraph positions.

---

## 3. `w5` — Final closing stock by WBS element

### Inputs (from `w5/prompt.txt` and `build.py`)

| File / sheet | Used for | Columns used |
|---|---|---|
| Reconciliation workbook, "Closing vs Counted branches" | Closing qty / value, unit cost, counted qty / value, reason per ID | same as section 1, plus `Plant`, `Mat` as text |
| GL stock export, sheets "Stock 1" and "Stock2" | GL line items of stock accounts | `Plant`, `Material`, `WBS Element`, `Year/Month`, quantity, amount in local currency |
| GL export, sheet "Details for scrapping" | Expired stock scrapped and posted at Finance level | `Plant`, storage location, `Material`, `Material Description`, `Batch`, movement type and text, `Qty`, `Amt`, posting date, material document, `WBS` |
| GL export, sheet "Materials differences" | GL reconciling postings (account 11890000) | not read: the two documents are typed into the script |
| OX10 | Plant names | |

Gaps: the scripts that built `rec.pkl`, `det.pkl`, `scrap.pkl` and `gl.pkl`
are missing. In particular, the columns `qty`, `val`, `aq`, `av`, `fq`, `fv`
of `det.pkl` (closing, scrapped and final qty / value per ID and WBS) were
computed there. Several scrapping columns are read by position (`_2`, `_4`,
`_5`, `_9`, `_10`, `_25`), so their real headers are unknown.

### Rules

1. ID = plant + material.
2. Sum the GL lines by plant, material and WBS. Exclude subtotal rows with no
   material. Blank WBS is reported as "No WBS in GL".
3. GL totals per ID must agree with the reconciliation closing qty and value;
   report every ID that does not agree. The Read Me states they agree exactly
   for GL stock accounts 11000100–11001300.
4. Sum the scrapping list by plant, material and WBS. Scrapped quantities and
   values are negative. Deduct them from the closing stock **on the WBS shown
   on each scrapping line**; never move them to another WBS.
5. Final closing = closing + scrapped (scrapped is negative).
6. Main WBS = the WBS with the largest absolute final value (fallback: value,
   final qty, qty). "All WBS with balance" lists every WBS with a non-zero value.
7. Value split into three named columns: `RMS-OWN-ESE-RM`,
   `RMS-PRG-FND-CP`, No WBS; any other WBS is added to the No WBS column in
   the main sheet and shown as "Other WBS (net)" in the summary.
8. Counted stock excluding expired: if the ID has scrapping and counted qty ≥
   scrapped qty, also remove the scrapped qty and value from the counted stock.
9. Difference after scrapping = counted value excluding expired − final closing value.
10. Scrapped IDs not in the closing stock are added as lines with zero closing
    and the reason "Not in closing stock … scrapped at Finance level only".
11. Flags (first match): "Check: negative after scrapping" (final qty < 0 or
    final value < −0.5); "Check: scrapped WBS differs from stock WBS" (any WBS
    value < −0.5); "Expired stock removed".

### Self-checks

- Bridge: closing − scrapping = final; final list total − bridge total = 0.
- Per line: final value − sum of WBS split = 0 ("WBS Check").
- Totals by WBS − final total = 0.
- Scrapping in GL (document) − scrapping list total (rounding only).
- Counts: IDs in list, IDs with expired stock removed, IDs with more than one
  WBS, IDs negative after scrapping, IDs whose scrapping WBS differs, scrapped
  lines with no closing balance.

### Outputs

Workbook with Read Me, Summary (bridge, GL reconciling postings, totals by
WBS and by plant, counts, chart), Final Closing Stock (one line per ID, live
formulas), Closing by ID & WBS, Expired Scrapped (with "In closing stock?"
match), Analysis Prompt.

---

## 4. `w6` — RBC accountability report (WBS `RMS-PRG-FND-CP`) and AMC

### Inputs

| File / sheet | Used for | Columns used |
|---|---|---|
| Previous RBC report (`rbc.xlsx`), sheet "CPDS Report" | Opening stock (= last quarter's reported closing) and last quarter's figures | `Valuation Area`, `Material`, `Material Description`, `Base Unit of Measure`, `Category`, `Opening Stock`, `Opening Value`, `Closing Stock`, `Closing Value`, plus `Total Receipt Qties/Values`, `Total Issue Quantities/Values` (dropped from the new report) |
| Previous RBC report, sheet "Data" (header on row 2) | Category per material on any WBS | `Valuation Area`, `Material`, `WBS`, `Category`, `Closing Value`, `Closing Stock`, `Material Description`, `Base Unit of Measure` |
| Previous RBC report, sheet "ITEM Category" | Fallback category list | `SAP MATERIAL`, `Category`, `Product description` |
| Previous RBC report, sheet "Stock witH wbs" (header on row 2) | Descriptions | `Material`, `Material Description` |
| `w5` outputs (`det.pkl`, `gl.pkl`, `rec.pkl`, `scrap.pkl`) | Closing stock on the WBS after scrapping | see section 3 |
| OX10 | Plant names | |
| Weekly stock monitoring workbook (`wk.xlsx`) | AMC, stock on hand (HQ, branches, SDPs), months-of-stock projections, shipments | read by **fixed row and column positions per sheet** (see below) |
| Material master export (`mm.xlsx`) | Map weekly product codes to SAP materials | `Material`, `Old material number` |

### Roll-forward (`roll.py`, `roll2.py`)

- GL lines on WBS `RMS-PRG-FND-CP`. `Year/Month` is the fiscal period: the
  script treats `2025/10`, `2025/11`, `2025/12` as April, May, June 2026, so
  the fiscal year starts in July and `2025` means FY2025/26.
- Opening per plant and material = closing reported to RBC last quarter.
- GL balance at the end of the previous quarter is also computed; the gap
  with the reported opening is an "adjustment".
- Quarter movements split into receipts (amount > 0, or amount = 0 and qty > 0)
  and issues (the rest), also by month.
- Closing = final closing after scrapping from `w5`.
- Check: opening + adjustment + receipts + issues + scrapping − closing = 0.
- Material numbers: leading zeros removed; plant trimmed.

Under your current rule, receipts, issues, scrapping and the adjustment are
**not shown** in the RBC report. The roll-forward may still run in the
background as a check; see question R1.

### Category assignment (first match wins)

1. Same plant and material in last quarter's CPDS report.
2. Same material in last quarter's CPDS report, any plant.
3. Same material in last quarter's "Data" sheet, any WBS (most frequent category).
4. "ITEM Category" list.
5. Otherwise **CPDS**, marked "New item – assigned CPDS (review)".

Category names are normalised: `ARV AND OPPORTUNITIC INFECTION` and `ARV&OI`
→ ARV and Opportunistic Infection; `MALARIA` → MALARIA AND NTD; `Program Lab` →
CPDS; `ESE`, `Oncology`, `SPECIALIZED` → Cross Cutting.

Report order of programs: CPDS, MALARIA AND NTD, ARV and Opportunistic
Infection, MCCH, EI, VMMC, Cross Cutting, Hepatitis, TB, NCDS.

### RBC calculations (`build_rbc.py`, `add_close.py`)

- Difference = closing − opening (qty and value), per line, program, plant, product.
- Label: rounded difference > 0 → "Increase", < 0 → "Reduction", 0 → "No change".
- Difference % = difference ÷ opening (0 if opening is 0; "new" for products in Top Products).
- Share of stock = program value ÷ total, for last quarter and this quarter.
- Lines in stock = count of lines with closing value > 0.
- Lines with all values zero are dropped.

### RBC self-checks

- Detailed closing list total − SUMMARY total = 0.
- Closing by material grand total − SUMMARY total = 0.
- Every summary is a live SUMIF over the data sheet.

### RBC outputs

- **Workbook**: Read Me; SUMMARY Report (by program + overall position + chart);
  March vs June (by program, share, two charts); By Plant; Top Products (top 25
  by closing, top 15 increases and reductions); Metrics; Data (line detail);
  previous CPDS report copy with receipt and issue columns removed; Category
  Mapping; Analysis Prompt; plus "Closing Stock" (detail list with AMC status)
  and "Closing by Material" (program subtotals).
- **Word narrative** (`build_nar.py`): opens an unzipped previous-quarter
  narrative (folder `nx`), keeps the header and title block (period changed),
  writes a new body with tables and charts, including section 5 "Stock
  sufficiency against AMC".
- **HTML dashboard** (`rbc_dash.html`): quarter switch, product search (name or
  SAP code), plant, program and minimum-value filters; AMC section with a
  program filter.

Note: `build_nar.py` still defines helper text about receipts and issues
("Receipts above issues", "Deliveries exceeded distributions…") and loads
receipt / issue totals. These must not appear in the new reports.

### Stock sufficiency against AMC (`amc.py`, `amc2.py`, `add_amc.py`)

- Weekly report sheets read: `ARV&OIs_NoChange`, `Hepatitis`, `VMMC`, `LAB `
  (trailing space), `MALARIA`, `TB`, `MCCH`. For each sheet the script stores the
  header row and the column positions of product code, alternative code,
  description, pack, HQ stock, branches stock, SDP stock, total, AMC, the first
  of seven monthly MOS projections, the first shipment column and the number of
  shipment columns, plus max and min MOS.
- Reading stops at the next "STOCK STATUS" / "Product code" block; rows
  starting with "Total" or "Product" are skipped.
- Mapping to SAP material: material master "Old material number" = weekly
  product code, plus hand corrections for three products in `amc2.py`.
  A material that appears twice has its value counted once (under ARV and OI).
- RMS stock = HQ + branches. National stock = RMS + SDPs.
- MOS at RMS = RMS ÷ AMC; MOS national = national ÷ AMC (only when AMC > 0).
- Status on national MOS: no AMC → "No AMC reported"; > max → "Overstock";
  ≥ min → "Stocked to plan"; ≥ 3 → "Understock"; else "Stock-out risk (<3 MOS)".
  Thresholds: min 6 / max 12 for all programs, min 9 / max 14 for MCCH.
- From the seven monthly projections (Jul-26 … Jan-27): first month below 3
  MOS and first month at or below 0 (projected stock-out).
- Monthly consumption value = closing value ÷ MOS at RMS. Value-weighted MOS
  per program = closing value ÷ monthly consumption value.
- Value above max = closing value × min(1, (MOS national − max) ÷ MOS at RMS)
  when MOS national > max.
- Products in stock on the WBS but not in the weekly report: "No AMC data –
  monitor" list.
- Outputs: AMC Summary (count by status per program, % below min, value
  measures, two charts), AMC Analysis (one line per product, conditional
  colours), AMC Risk List (< 3 MOS or projected stock-out), No AMC – Monitor.

Gaps: the scripts that produced `A4.pkl`, `amc_mm.pkl` and `noamc.pkl` are
missing. `A4.pkl` is used everywhere in place of `A3.pkl` from `roll2.py`; the
difference between them is unknown.

---

## 5. Things I could not determine

1. Real column headers of every SAP export. The scripts mostly use short
   names created by missing preparation steps (`d.pkl`, `rec.pkl`, `det.pkl`,
   `scrap.pkl`, `gl.pkl`, `A4.pkl`, `amc_mm.pkl`, `noamc.pkl`,
   `report_data.json`, `deck_data.json`, chart PNGs).
2. Which GL export columns hold quantity and amount (`Qty`, `Amt` are renamed).
3. What `A4.pkl` changed compared with `A3.pkl` in the RBC flow.
4. Whether the layout of the weekly stock monitoring workbook (header rows,
   column positions) is stable from month to month.
5. How the GL reconciling postings (account 11890000) should be read from the
   "Materials differences" sheet instead of being typed in.
6. The RMS Word and PowerPoint templates themselves.
