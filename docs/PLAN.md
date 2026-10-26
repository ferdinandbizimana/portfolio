# Build plan

Status: **Phase 7 (more analyses) in review**: order fill rate, expiry
risk, stock in transit, purchase order follow-up and warehouse activity, built
with your rules of 2026-10-23 on the headers of the exports you sent (they had
headers only, so they are tested on invented data; please check one real run of
each, Q13). Phases 0–6, 8 and the Phase 9 tooling are merged. Next: going live
(G2: a server and a domain), then fillable copies of the templates you shared.
Ferdinand asked (2026-10-21) to continue through all phases without stopping;
each phase gets its own pull request, merged once CI is green. Still needs
something from you: Q1, Q7–Q19 below and G2.

---

## 1. Technology choices

| Area | Choice | Why |
|---|---|---|
| Backend | FastAPI, Python 3.12, Pydantic v2, managed with `uv` | Required. `uv` gives fast, reproducible installs from a lock file. |
| Analysis engine | pandas + `python-calamine` (Excel reading) + pyarrow | Same tools as the legacy scripts, so rules port directly and results can be compared. Calamine reads large `.xlsx` files much faster than openpyxl. Uploaded files are converted once to Parquet so re-runs are fast. |
| Database | PostgreSQL 16, SQLAlchemy 2, Alembic | Well known, reliable, one service. Holds users, runs, results metadata, portfolio content, published snapshots, audit log. JSONB for dashboard data. |
| File storage | Local filesystem volume behind a small `Storage` interface | Simplest to run and back up on one server. Uploads of 200 MB+ are streamed to disk in chunks. An S3-compatible adapter can be added later without touching analyses. |
| Background jobs | Redis + RQ (worker container) | Simple Python job queue, easy to understand and debug. Progress is reported through job metadata and shown in the UI. Scheduled jobs (nightly SAP refresh, Phase 8) are added with a small scheduler that enqueues RQ jobs. |
| Excel reports | openpyxl | Live formulas, charts and formatting, as in the legacy workbooks. |
| Word reports | docxtpl (Jinja placeholders in `.docx`) on top of python-docx | You upload an RMS template with placeholders; cover, styles, header, footer and logo stay as designed. Replaces the legacy raw-XML approach and the Node `docx` scripts, so all report code is Python. |
| PowerPoint reports | python-pptx, using the layouts of an uploaded `.pptx` template | Same reason; replaces Node `pptxgenjs`. |
| Frontend | Next.js (App Router), TypeScript strict, Tailwind CSS, shadcn/ui components | Required framework. Tailwind + shadcn give a clean, accessible, mobile-friendly UI without a heavy design system. Portfolio pages are statically rendered and revalidated on edit, so they are fast. |
| Charts and tables | Apache ECharts (`echarts-for-react`) and TanStack Table | ECharts handles bar, stacked, pie, line and large data sets well and renders the same in light and dark mode. TanStack Table gives sorting, filtering, search and pagination for line-level tables. |
| Authentication | A login page with e-mail and password only (no two-factor, by your decision). Behind the scenes: Argon2 password hash, server-side session in an HttpOnly, Secure, SameSite=Lax cookie plus an Origin check on every state-changing request (CSRF protection), login rate limiting | One user only, so no external identity provider is needed. The admin account is created from the command line, never through a public sign-up. |
| Contact form | Sent by SMTP directly to your e-mail address, with a honeypot field and rate limiting against spam | Your address and the SMTP password live in `.env`, never in the public code. |
| Tests and linting | pytest (against real PostgreSQL), ruff, mypy; ESLint, Prettier, Vitest; Playwright browser tests on desktop and mobile | Standard tools. All run in GitHub Actions on every push and pull request. |
| Local run | Docker Compose: `proxy` (Caddy), `frontend`, `backend`, `worker`, `postgres`, `redis` | `docker compose up` starts everything; the browser uses one origin, http://localhost:8080. |
| Deployment (Phase 9) | One Linux VPS running the same Docker Compose stack, Caddy as reverse proxy with automatic HTTPS | Cheapest and simplest setup one person can maintain. Same files in development and production. |
| Backups (Phase 9) | Nightly `pg_dump` + file volume, encrypted and sent off-site with restic | Proven, scriptable, and restore is tested with a written guide. |

## 2. Architecture

```
Browser ── Next.js (public pages, admin UI) ── FastAPI ── PostgreSQL
                                                 │  └──── Storage (uploads, Parquet, reports, templates)
                                                 └─ Redis ── RQ worker (parse, validate, analyse, render reports)
```

### Analysis contract

Each analysis is a package under `backend/app/analyses/<name>/` with:

- `spec.py` — name, version, description, the **input datasets** it needs
  (logical names such as `mb5b_reconciliation`, `gl_stock_lines`,
  `scrapping_list`, `ox10_plants`), and for each the required columns, types
  and how to recognise the file (sheet name, header row, key columns).
- `compute.py` — a pure function: `DataFrames + parameters → Result`. No file,
  database or network access.
- `checks.py` — self-checks: name, expected, actual, tolerance, passed.
- `dashboard.py` — builds the dashboard data (KPIs, tables, chart series,
  filter options) from the result, at line level and at summary levels.
- `reports/` — Excel, Word and PowerPoint writers using the shared reporting
  helpers and the uploaded templates.
- `tests/` — tests with fake fixtures and hand-checked expected values.

### Where data comes from

A `DataSource` produces the input datasets for a run:

1. `UploadSource` (Phase 4): files you upload; the app detects which dataset
   each file is by its sheet names and column headers, and asks you to
   confirm.
2. `FolderSource` (Phase 8): picks up new SAP exports from a shared folder.
3. ~~`SapSource`~~: dropped (2026-10-21). Data always comes from spreadsheets
   exported from SAP, uploaded or saved in the shared folder.

Analyses only see datasets, never the source, so changing the source does not
change the analysis.

### Runs, results and publishing

- A **run** stores: analysis + version, parameters (e.g. period end date),
  input file hashes, status and progress, check results, result tables
  (Parquet), dashboard data (JSON) and generated reports.
- **Compare periods**: pick two runs of the same analysis (e.g. end of March
  and end of June) and see the differences by program, plant and product.
- **Publishing** creates a frozen **snapshot** of the dashboard at a detail
  level you choose (e.g. program or plant only, product detail removed). A
  preview shows exactly what will be visible. Visibility: private (default),
  secret link (unguessable token), or public (listed on the dashboards page).
  Unpublishing removes access immediately. Public pages read snapshots only.

## 3. Phases and checklists

Each phase: its own branch, small commits, a pull request with summary, how to
test and open questions. You review and merge before the next phase starts.

### Phase 0 — Exploration and plan (this pull request)
- [x] Read `legacy/` and write `docs/legacy-analysis.md`
- [x] Write `CLAUDE.md`
- [x] Write this plan
- [x] Add `.gitignore` rules that block data files
- [x] Approval of the plan (2026-10-20)
- [ ] Answers to the questions in section 5

### Phase 1 — Foundation
- [x] Monorepo layout: `backend/`, `frontend/`, `docs/`, `scripts/`
- [x] Legacy scripts kept out of git (your decision, G1); `legacy/` is git-ignored and blocked by the data guard
- [x] Backend skeleton: settings from environment, `/api/health` (checks DB and Redis, 503 naming the failing one), JSON logging
- [x] Alembic set up with a first empty migration (run automatically when the backend container starts)
- [x] Frontend skeleton: Next.js + TypeScript (strict) + Tailwind, placeholder home page showing the API status
- [x] Worker container with a trivial `ping` job and a smoke test (`python -m app.jobs.smoke`)
- [x] `docker-compose.yml` (frontend, backend, worker, postgres, redis) — `docker compose up --build`
- [x] `.env.example` listing every setting
- [x] GitHub Actions: data guard, backend lint/type/test, frontend lint/type/test/build, full stack start + health check + worker smoke test
- [x] Pre-commit hook and CI job that reject data files (xlsx, csv, …) outside `backend/tests/fixtures/`
- [x] README: what the project is, how to run, how to test

### Phase 2 — Login and admin area
- [x] User table; `create-admin` and `set-password` command line tools
- [x] Login page (e-mail + password, Argon2 hash); no two-factor
- [x] Sessions in secure cookies (idle 12 h, absolute 7 days), Origin-check CSRF protection, logout
- [x] Login rate limiting: 5 failures per 15 minutes per e-mail and per address
- [x] Audit log table and admin page (sign-ins, failures, blocks, sign-outs, password changes)
- [x] uvicorn logs in JSON like the application logs
- [x] Admin layout (mobile and desktop): overview, activity log, settings (change password)
- [x] Caddy as the single entry point in Docker Compose (same set-up as production)
- [x] Tests for every auth path: wrong password, unknown e-mail, idle and absolute expiry, rate limit, password change signs out other devices, cross-site request refused; migrations match models; browser tests on desktop and mobile

### Phase 3 — Portfolio
- [x] Content model: profile, experience, skill groups, projects / case studies, stored files (migration 0003)
- [x] Public pages: home, about, experience, skills, projects, case study pages, CV download, contact form
- [x] Admin editors for all content (Markdown with preview), photo, CV and cover image upload (type checked from file content, 10 MB limit)
- [x] Cached rendering refreshed on save (`updateTag`); SEO metadata, Open Graph image, sitemap, robots.txt
- [x] Mobile-first layout; Lighthouse (mobile): performance 95–100, accessibility 100, best practices 96, SEO 100
- [x] Contact form: validation, honeypot, 5 per hour per address, sent by SMTP to your e-mail; test button in Settings; Mailpit for local and CI testing
- [x] `docs/operations.md`: first start, password reset, Gmail set-up, editing content

### Phase 4 — Upload and analysis engine
- [x] Chunked (8 MB), resumable upload with progress and retries; SHA-256 per file; up to 1 GB (setting)
- [x] Parse Excel (.xlsx/.xls via calamine) and CSV (any separator, UTF-8 or Windows encoding) to Parquet in the worker, streaming; header row found below title lines; values kept as exact text
- [x] Dataset recognition by headers (case and punctuation ignored, aliases) and sheet name; the run form pre-selects the recognised sheet and lets you change it
- [x] Validation with clear messages naming file, sheet, row and column (missing columns, bad numbers/dates; SAP "1,234" and "1234-" understood)
- [x] Analysis contract (`app/analyses/base.py`) and registry: drop a package in `app/analyses/` and it appears
- [x] Background runs with progress, cancel, clear failure messages; run history page
- [x] Results stored: tables (Parquet), checks, KPIs, dashboard, reports, result fingerprint (same inputs → same fingerprint, tested across Excel and CSV)
- [x] Dashboard renderer: KPI tiles, filters and search, ECharts charts, sortable paginated tables, checks
- [x] Reports: Excel (streaming, live totals, checks sheet), Word and PowerPoint on uploaded templates or a built-in layout; template upload, activate, delete
- [x] Language guard: a run fails if any report or dashboard text contains "AI" (whole word) or "to be confirmed"
- [x] Compare two runs of the same analysis (difference, Increase / Reduction %)
- [x] Demo analysis on clearly fake data proves the flow end to end
- [x] Large file test: 210 MB CSV, 4.9 million rows: upload 2 s, parse 28 s, full run with reports 4 min 47 s, worker peak memory 1.8 GB

### Phase 5 — First analyses (from legacy)
For each: input specs from real headers (you provide), fake fixtures, rules,
checks, dashboard, reports, tests, and a **local parity script** that runs the
new code and the legacy logic on your real files (kept outside git) and
compares totals line by line.
- [x] SAP export definitions: every export you sent (2026-10-23) is
      recognised on upload by its exact headers (`docs/sap-exports.md`)
- [x] Final closing stock by WBS (w5): G/L line items − expired stock scrapped
      on its own WBS; WBS split, main WBS, flags, checks, dashboard, reports.
      With the "Closing vs Counted branches" sheet as an optional input it
      also compares counted stock with the final closing (w5 rules 8–9).
- [x] RBC accountability report (w6): opening, closing, difference only;
      laid out like your June 2026 report (version 6); its "CPDS Report" sheet
      is next quarter's opening. Local check on your files: opening by
      programme equals your June report to the franc.
- [x] Physical inventory variance investigation (the 30 June 2026 Variance
      Investigation Report and its Detailed Variance Report): justification by
      status, plant, root cause and required action; inventory accuracy by
      stock category, programme and plant (Variance Management SOP); retained
      earnings; dashboard and reports. Local check on your files: every figure
      of the narrative report's tables 1, 2, 5 and 6 and the retained-earnings
      finding is reproduced to the franc.
- [x] Stock sufficiency against AMC (w6): every programme sheet of the weekly
      report, months of stock at RMS and nationally, status, value above the
      maximum level, programme stock without AMC. Local check on your files:
      every product count, status count, value, monthly consumption value and
      value above max of your June report's AMC Summary is reproduced exactly,
      and the "No AMC – Monitor" list has the same 884 materials.
- [x] Stock count reconciliation (w3, Q4): closing vs counted stock, causes
      and themes from the reasons, sites, integrity flags, offsetting
      materials, recount effect. Local check on your June 2026 workbook: same
      variance lines, causes and flags as the legacy output, all checks pass.
- [ ] Parity confirmed by you on real files (closing stock needs the G/L export, Q1)

### Phase 6 — Publishing
- [x] Visibility: private, secret link, public; unpublish
- [x] Detail level choice and a preview of exactly what will be visible. Each analysis marks its tables as summary or detail; "Summary only" keeps the summary tables (for example by program or plant) and leaves out line-level detail. The real analyses in Phase 5 decide which tables are summary.
- [x] Frozen snapshots; public endpoints read snapshots only
- [x] Public dashboards page and per-dashboard pages with filters, search, charts, tables
- [x] Tests proving public endpoints cannot reach uploads, runs or unpublished snapshots

### Phase 7 — More analyses
Rules from you (2026-10-23, Q6); headers from the exports you sent:
- [x] Order fill rate: VA05 sales orders, outbound deliveries, OX10
- [x] Expiry risk: ZSTOCKREPORT expiry dates with the AMC
- [x] Stock in transit: MB5T, and in MB51 the STO goods issue (movement type
      641) matched to the goods receipt (101) by purchase order and outbound
      delivery reference: time in transit
- [x] Purchase order follow-up: ME2N and inbound deliveries; delivery period
      (PO creation date to goods receipt) and delivered in full (ordered vs
      delivered quantity and value)
- [x] Warehouse activity: EWM "All Movement for Products"; dock to stock
      (goods receipt to putaway) and picking (stock removal) to goods issue

### Phase 8 — SAP connection
- [x] Shared folder pickup: new exports in the shared folder are taken once they stop changing, copied into storage (the folder is only read) and read like uploads; a file is taken again only when its content changes
- [x] Schedules: at a set time on chosen days, or as soon as new files arrive; newest file matching a name pattern per input; date parameters as rules ("last day of the previous month"); skip when nothing changed; Run now
- [x] E-mail when a scheduled run finishes (status, self-checks, link)
- Direct S/4HANA connection: **dropped** by decision of 2026-10-21 (no SAP APIs; spreadsheet exports only).

### Phase 9 — Going live
- [x] Caddy with automatic HTTPS for your domain, security headers (HSTS, Content Security Policy, no framing), checked by browser tests
- [x] Production Docker Compose (`docker-compose.prod.yml`): only ports 80/443 open, restart on failure, log rotation, secure cookies; secrets only in `.env` on the server
- [x] Nightly encrypted off-site backups (restic: database + stored files, 7 daily / 4 weekly / 12 monthly, sample check each night); restore tested automatically in CI (`scripts/test-backup-restore.sh`)
- [x] Monitoring: Admin → Overview shows worker, scheduler, last backup and disk space; `/api/health` for an outside uptime check; optional backup ping (healthchecks.io); error log commands
- [x] `docs/deploy.md` (server, domain, first start, backups, monitoring) and `docs/operations.md` (update, back up, restore, change passwords and keys); `scripts/update.sh`
- [ ] After going live: clean, fillable copies of the templates you shared
      (spot check, OX10, PI document, VA05 and the other export templates),
      with headers, formats and instructions, for you to fill in.
- [ ] The actual server and domain. **Waiting for you** (G2): choose a provider and a domain, then follow `docs/deploy.md` (about an hour). I can guide you step by step.

## 4. Decisions

| Date | Decision |
|---|---|
| 2026-10-20 | Report generation is done in Python only (openpyxl, docxtpl, python-docx, python-pptx); the legacy Node scripts are not reused. |
| 2026-10-20 | Analyses are pure functions over named datasets; data sources are separate (upload now, folder and SAP later). |
| 2026-10-20 | Your instructions override legacy behaviour; for the RBC report receipts, issues and expired stock are never shown. |
| 2026-10-20 | G1 answered: the legacy scripts are never put on GitHub. They stay with you; `legacy/` is git-ignored and blocked by the data guard. `docs/legacy-analysis.md` holds the rules without real figures. |
| 2026-10-20 | G4 answered: a simple login page (e-mail + password). No two-factor, no recovery codes. Passwords are still stored hashed, sessions use secure cookies, and repeated failed logins are slowed down. |
| 2026-10-20 | G3 answered: contact form messages are sent by SMTP directly to your e-mail. Recipient address and SMTP account go in `.env` (`CONTACT_TO_EMAIL`, `SMTP_*`), never in the code. |
| 2026-10-20 | F1/F2 answered: you will provide the export headers and preparation scripts when Phase 5 starts. |
| 2026-10-21 | Uploaded cells are stored as exact text; each dataset definition declares column types, and conversion happens per analysis with row-level messages. Thousands separators "," are removed and a trailing minus ("1234-", SAP style) is read as negative. If your exports use "." for thousands and "," for decimals, tell me. |
| 2026-10-21 | Dashboards keep at most 20,000 lines per table (the full table stays with the run and in the Excel workbook). Excel sheets stop at Excel's 1,048,576-row limit with a visible note. |
| 2026-10-21 | Server sizing: the worker needed 1.8 GB for a 4.9-million-row file; plan at least 4 GB of memory for the server (8 GB comfortable). |
| 2026-10-21 | Publishing: a publication is a frozen copy of one run's dashboard. It starts private; a secret link is `/d/<token>` (not listed, not indexed by search engines, can be replaced by a new one); public dashboards are listed at `/dashboards`. Self-checks are hidden from visitors unless you tick "Show the self-checks". Unpublishing deletes the copy. Deleting the run does not change a publication. |
| 2026-10-21 | Shared folder: the app reads the folder given by `INBOX_HOST_DIR` (read-only mount) every minute. A file is taken once unchanged for 60 s; Office lock files (`~$…`) and hidden files are ignored. Schedule times use `TIMEZONE` (default Africa/Kigali). A scheduled run stores the actual date (for example 2026-06-30), not the rule, so it can be repeated exactly. |
| 2026-10-21 | Backups use restic (encrypted, deduplicated) to any S3-compatible bucket; the backup password must be kept outside the server. The command-line password reset now also signs out every session. |
| 2026-10-21 | Content Security Policy allows only the site itself; inline scripts and styles are allowed because Next.js and the charts need them. |
| 2026-10-21 | P1 answered: no SAP APIs and no direct S/4HANA connection. All data comes from spreadsheets exported from SAP and uploaded (or saved in the shared folder). Phase 8 is complete as built. |
| 2026-10-23 | From your files: exact headers of 13 SAP exports recorded in `docs/sap-exports.md`; analyses use only these names. |
| 2026-10-23 | From your June 2026 RBC report (version 6): line labels are Increase / Reduction / No change (R3); "new" when opening is 0 (R7, shown as "New product: Yes"); programme list and category names as in the report (R5); AMC belongs to the RBC workbook (R6, comes with Q3); closing = reconciled closing stock (R4). |
| 2026-10-23 | RBC opening = every line of the previous report's "CPDS Report" sheet, whatever its WBS, because your June report counts the March lines on RMS-OWN-ESE-RM (as Cross Cutting) in the opening. To confirm (Q2). |
| 2026-10-23 | A workbook upload no longer fails because one sheet has no table (notes, summaries): such sheets are skipped. |
| 2026-10-23 | Q2 answered: the RBC report counts RMS-PRG-FND-CP only; RMS-OWN-ESE-RM lines are not RBC stock and are left out of the opening. (They may still give the programme name of an item that is new on RMS-PRG-FND-CP: Q7.) |
| 2026-10-23 | Q3 answered: weekly-report product codes are linked to SAP materials through ZSTOCKREPORT column `NPC CODE`; when no code matches, through the description. |
| 2026-10-23 | Variance investigation rules (narrative report, Variance Management SOP): stock variance = minus the amount on the difference account; positive and negative never offset; status Justified (any capitals) or Not Justified; inventory variance = Σ|Not Justified variance| ÷ final closing stock, accuracy = 100% − variance, tolerance 0.5% (a parameter). Retained earnings = lines with an "AMOUNT MOVED TO RETAINED EARNINGS" value (zero included), variance = minus that amount. Plant names as in the file (7000 = RMS-Kigali, as in OX10). |
| 2026-10-23 | When several datasets fit a sheet, the most specific one (most required columns) is proposed first; absent optional columns keep their type. |
| 2026-10-23 | Q4 answered: stock count reconciliation uses "Closing vs Counted branches" (closing posted in Finance vs counted). Cause list, themes, sites and thresholds as in the legacy `w3` script (S1–S3 kept as they were). |
| 2026-10-23 | Q5 answered: MB51 holds every goods movement. Only scrapping movement types count as expired stock scrapped: 551 and 555 by default (the types in your June reconciliation's "Scrapped at Fin" sheet), a parameter of the closing and RBC analyses. |
| 2026-10-23 | Stock sufficiency (AMC): every sheet of the weekly report recognised as a programme sheet is read; the header row is the one with the most labels among the first 30 rows; a sheet stops at its next block ("STOCK STATUS …"). Status on national months of stock; min / max 6 / 12, MCCH 9 / 14; stock-out risk below 3. Value on the WBS from the final closing stock when given (as in your RBC report), otherwise ZSTOCKREPORT quantity × unit cost. A material reached from two products is valued once, under the first (A4). Materials without AMC are listed when their quantity is above zero and their value is at least RWF 0.5 (as your June list). |
| 2026-10-23 | Q6 answered: Phase 7 analyses and rules (see Phase 7). |
| 2026-10-23 | After going live, you receive fillable, well-formatted copies of the templates you shared. |
| 2026-10-24 | Dates in uploads: ISO dates (Excel) and SAP day-first dates (30.06.2026, 30/06/2026) are read as dates. |
| 2026-10-24 | Order fill rate (definitions to confirm, Q14): order line = VA05 item dated in the period, quantity above zero; delivered = "Actual delivery qty" (else "Delivery Quantity") of goods-issued outbound delivery items with that sales document and item (or material); in full when delivered ≥ ordered; line, order, quantity and value fill rate (quantities capped at the ordered quantity); plant = delivering plant, named from OX10; days from order date to the last goods issue. |
| 2026-10-24 | Expiry risk (Q15): ZSTOCKREPORT unrestricted + QI + blocked per batch at the unit cost; bands expired / ≤3 / 3–6 / 6–12 / >12 months / no date; the batches of a product are used in order of expiry at the weekly-report AMC (national), what is left at expiry is at risk; expired stock is at risk in full; products without AMC are shown by band only. |
| 2026-10-24 | Stock in transit: MB51 641 issues and 101 receipts per STO and material (642 and 102 reversals taken off); receipts matched to the issue with the same outbound delivery reference first, then the oldest open issue; transit time = receipt − issue posting date; MB5T lines aged from the oldest open issue; long transit over 30 days (a parameter). |
| 2026-10-24 | Purchase order follow-up: ME2N items created in the period, not deleted; receipts = inbound delivery items with a goods movement date, matched by PO and item (or material); in full when received ≥ ordered; received value = net order value × received / ordered; delivery period = last goods receipt − PO document date; open POs aged to the report date. |
| 2026-10-24 | Warehouse activity: task type from the warehouse process category (putaway, stock removal); cancelled tasks (status A) left out; dock to stock = putaway confirmation date − goods receipt date (target 1 day, a parameter); picking time = task creation to confirmation; picking to goods issue = last stock removal of a delivery to its goods issue in the outbound delivery list (EWM document = delivery number). |
| 2026-10-24 | The outbound delivery list must have "Goods Issue Date" and the inbound list "Goods receipt date", so the two lists (same SAP layout) are never mistaken for each other. |
| 2026-10-25 | PO follow-up uses the ME2M report (same columns as ME2N) for the creation date (Document Date), approval date (Final Approval Date) and required delivery date (Delivery Date): days to approval, approval to receipt, on time (last receipt on or before the required date), on time in full, open lines past the required date. Your ME2M file loads without errors (headers recorded in `docs/sap-exports.md`; no data kept). |
| 2026-10-26 | Answers to Q14–Q18 and the AMC link (to be built in the next pull request): AMC and ZSTOCKREPORT quantities are always in the base unit of measure (pack sizes x30 / x60 are descriptions only). MB51 "Reference" holds the outbound delivery on 641, 101 and their reversals 642, 102 and 122; the STO creation date comes from ME2M, so stock in transit also measures STO creation → goods issue (641) → goods receipt (101). PO follow-up keeps STOs and flags them (document type ZSTO, numbers starting 71). Warehouse activity: dock-to-stock target 2 days; inbound deliveries (numbers starting 18) traced from goods receipt to putaway, with a check that MB51 has the 101 for the same inbound delivery; picking traced to post goods issue, with a check that MB51 has the 641 (STO) or 601 / Y01 / Z01 (customer deliveries) for the same outbound delivery; missing postings are flagged as EWM–ERP synchronisation issues. Order fill rate: goods-issued deliveries count; ordered vs confirmed quantity per line; net price = unit cost, net value = line value; ZRMS and ZSPO are normal sales, ZDON programme commodities at 100% discount, valued from MB51 601 / Y01 / Z01 / X01 by sales document; OX10 gives customer names (facility type in Name 1: HP, CS / HC, DH, RH, PH …), district (City) and region (Description), matched to the outbound delivery names; the fill rate is also analysed by facility type, region and border districts. Weekly product codes → SAP materials through the material master (MARA): "Old material number" = NPC code, "Material" = SAP code. |
| 2026-10-26 | Built from those answers: MARA link first in stock sufficiency and expiry risk; ME2M STO creation dates and 122 reversals in stock in transit; STO flag in PO follow-up; 2-day target and MB51 synchronisation checks in warehouse activity; confirmed quantity, ZDON distribution value from MB51 (by "Sales order" / "Sales order item"), facility type, district, region and border districts in the order fill rate. Facility types read from the abbreviation in the OX10 name (HP, CS, HC, DH, RH, PH; anything else "Other"). Border districts are a parameter (default list in Q23). |
| 2026-10-21 | Word templates: the report goes where the template has a paragraph `{{p body }}`; `{{ title }}`, `{{ subtitle }}`, `{{ report_date }}` may be used anywhere. PowerPoint uses the layouts "Title Slide", "Title and Content", "Title Only". |
| 2026-10-20 | Phase 0 and Phase 1 go in one pull request on the session branch, because Phase 0 had not been merged when you asked to continue. Later phases get one pull request each. |
| 2026-10-20 | Tool versions pinned: Python 3.12, uv 0.11.32, Node 22, pnpm 10.28. Backend dependencies locked in `backend/uv.lock`, frontend in `frontend/pnpm-lock.yaml`. |

## 5. Open questions

Answers will be recorded in section 4 (Decisions).

**General (needed before Phase 1–3)**
- G1, G3, G4: answered (see Decisions).
- G2. Hosting: do you have a domain and a preferred server provider or budget? (Phase 9)
- G5. Report narrative: the app writes fixed, rule-based sentences from the
  numbers, and you can add or edit commentary sections in the admin area
  before generating Word / PowerPoint. Acceptable?

**Files (needed before Phase 5 — you will provide them then)**
- F1. Header rows (values removed) of: reconciliation workbook, sheet "Closing
  vs Counted branches"; GL export sheets "Stock 1", "Stock2", "Details for
  scrapping", "Materials differences"; OX10; previous RBC report sheets "CPDS
  Report", "Data", "ITEM Category", "Stock witH wbs"; weekly stock monitoring
  workbook (one sheet per program); material master export.
- F2. The missing preparation scripts, if you still have them (they built
  `d.pkl`, `rec.pkl`, `det.pkl`, `scrap.pkl`, `gl.pkl`, `A4.pkl`, `amc_mm.pkl`,
  `noamc.pkl`).
- F3. RMS Word and PowerPoint templates. Shall I add the placeholders to a
  copy, or will you?

**Phase 5, part 2 (2026-10-23)**
- Q1. (The variance file you sent is the G/L export of the inventory difference
  accounts 42300600–42303000, used for the variance investigation.) The G/L
  line item export used for closing stock ("Stock 1" / "Stock2"):
  same columns as your variance investigation sheet (`Document Number` …
  `Material Description`), only stock accounts 11000100–11001300, all lines up
  to the period end? Could you upload one (any period) so I can check parity?
- Q2: answered (see Decisions).
- Q3: answered (see Decisions).
- Q4, Q5, Q6: answered (see Decisions). Your Q5 message was cut off after
  "…to Distribution so the"; if it said more, please send the rest.

- Q7. RBC: an item new on RMS-PRG-FND-CP takes its programme from the
  previous report's lines on other WBS (as your June report did, "March MB5B
  data – other WBS"). Keep that, or skip RMS-OWN-ESE-RM lines for naming too
  (the item then goes to CPDS for review)?
- Q8. Variance investigation: root cause and required action per line are in
  the "Detailed Variance Report.xlsx" embedded in the Word report, not in the
  G/L file. Could you upload that workbook (or add columns "Root cause" and
  "Required action" to the G/L sheet)? The app then fills tables 3 and 4.
- Q9. Inventory accuracy of RMS-own stock by material group (Medicines,
  Medical consumables, Medical devices & equipment, Laboratory reagents &
  supplies): which file gives each material's group?
- Q10. Table 6 of the narrative report leaves out GICUMBI, KAMONYI and
  RULINDO, which have Not Justified lines but almost no closing stock (their
  percentage is meaningless). The app lists them; should it leave out plants
  whose closing stock is below their Not Justified variance?

- Q11. MB51 reversals of scrapping (movement types 552 and 556): should they
  count too (they cancel a scrapping)? They are left out for now; add them in
  the run's "scrapping movement types" field to include them.
- Q12. AMC projections: your June report also shows pipeline quantities,
  "falls below 3 MOS" and "projected stock-out" months. Which file gives the
  pipeline (expected deliveries by month)? The ZSTOCKREPORT you sent has
  headers only, so the NPC CODE link was checked with the links in your June
  report; please check one run with a full ZSTOCKREPORT.

- Q13. Phase 7: the VA05, OBD, ME2N, inbound delivery, MB5T, MB51,
  ZSTOCKREPORT and EWM files you sent have headers only. Please run each new
  analysis once on a real export and tell me if a figure looks wrong.
- Q14. Order fill rate: count only goods-issued deliveries (default), or every
  delivery created? Should rejected order lines (VA05 reason for rejection)
  be left out? Which customers count (all sold-to parties, or only health
  facilities)? What is the role of OX10 in your fill rate (plant names, as
  built, or something else)?
- Q15. Expiry risk: the AMC of the weekly report is national and in weekly
  report units; ZSTOCKREPORT quantities are in SAP base units. Are the units
  the same? Should the AMC used for RMS stock be the national AMC (as built)?
  Expiry bands (3 / 6 / 12 months): right?
- Q16. Stock in transit: is "Reference" in MB51 the outbound delivery number on
  both the 641 and the 101 lines? Age bands (7 / 30 / 60 / 90 days) and the
  30-day "long transit" limit: right?
- Q17. PO follow-up: leave out STOs (document type UB) from ME2N? Count the
  delivery period to the last receipt (as built) or to the first?
- Q18. Warehouse activity: dock-to-stock target (1 day)? Is the EWM task
  "Document" the same number as the outbound delivery in the OBD list? If not,
  which column links them?
- Q20. ME2M has an approval date ("Final Approval Date") but no approval
  time. Is the time in another export, or is the date enough? Many lines in
  your file have no approval date: should those count as "not approved" (as
  built) or be left out?
- Q21. Your ME2M contains document types ZSTO and UB (stock transport
  orders). Leave them out of the PO follow-up (they are followed in stock in
  transit)? Same question as Q17.
- Q22. VA05 confirmed quantity and net price: the VA05 export you sent has no
  such columns. The app reads "Confirmed Quantity" and "Net Price"; please
  send the exact headers of an export that has them (or confirm these).
- Q23. Border districts (default, please correct): Rubavu, Rutsiro, Karongi,
  Nyamasheke, Rusizi, Nyamagabe, Nyaruguru, Huye, Gisagara, Bugesera, Kirehe,
  Kayonza, Nyagatare, Gicumbi, Burera, Musanze. And the full list of facility
  abbreviations in OX10 names ("and many others").
- Q24. MB51 has both "Sales order" and "Sales Order" (and the same for the
  item). Which one holds the sales document of a 601 / Y01 / Z01 / X01 line?
- Q25. Spot-check variance follow-up (new): see the proposal in the session
  of 2026-10-26: zones and their responsible staff (and e-mails), how a zone
  is recognised (storage type, bin prefix?), the list of reasons and of
  responsible units (Receiving, Picking, …), and the layout of the "items
  missed by picking" list.
- Q19. Which Phase 7 dashboards should be published, and at which detail level?

**Stock count reconciliation**
- S1. Use the `w3` cause list (14 causes, 6 themes, 5 sites)? Should the keyword
  rules and the plant-to-site map be editable in the admin area (versioned)
  or fixed in code?
- S2. Keep the thresholds: integrity gap > RWF 1, direction ±0.5?
- S3. The keyword "POSTED IN JULY" assumes a June year-end. For other count
  dates, should it become "posted in the month after the count"?

**Closing stock by WBS**
- W1. Always split into `RMS-OWN-ESE-RM`, `RMS-PRG-FND-CP` and "No WBS / other",
  or one column per WBS found?
- W2. GL stock accounts 11000100–11001300 and reconciling account 11890000:
  fixed, or settings?
- W3. Read the reconciling postings from "Materials differences"
  automatically instead of typing them in?

**RBC accountability**
- R1. Opening = closing of the previous RBC report you upload. Once the app has
  its own previous quarter run, should opening come from that run, with the
  uploaded report as a fallback?
- R2. The legacy roll-forward check (opening + receipts + issues + scrapping =
  closing, and the "adjustment" between reported opening and GL) cannot
  appear in the report. Keep it as a private check in the run view only, or
  drop it entirely?
- R3. When the difference rounds to zero, legacy says "No change". Allowed, or
  only "Increase" / "Reduction"?
- R4. Closing = final closing after expired stock is deducted (the `w5` result)
  on `RMS-PRG-FND-CP`. Confirm.
- R5. Program list (CPDS, MALARIA AND NTD, ARV and Opportunistic Infection,
  MCCH, EI, VMMC, Cross Cutting, Hepatitis, TB, NCDS) and the name
  normalisation: fixed, or editable? New items go to CPDS marked for review —
  keep that wording?
- R6. Is stock sufficiency against AMC a section of the RBC report (as in the
  legacy narrative) or a separate analysis with its own reports? It shows
  shipment / pipeline quantities — allowed in the RBC report?
- R7. Difference % when opening is 0: legacy shows "new". Keep?

**Stock sufficiency (AMC)**
- A1. Is the weekly monitoring workbook layout stable? Legacy reads fixed row
  and column positions per sheet; I would rather find columns by header text.
- A2. Min / max months of stock (6 / 12; MCCH 9 / 14) and the 3-month stock-out
  threshold: fixed, or editable?
- A3. Product code → SAP material via material master "Old material number",
  plus manual corrections: keep the corrections as an editable table in the
  admin area?
- A4. A material that appears under two programs has its value counted once
  (under ARV and OI). Is that a general rule?

**Writing**
- P1: answered (see Decisions): no SAP connection.
- L1. "AI" check: whole word, upper case only (so "AID" or "maintain" pass)?
  "to be confirmed": any case. Also forbid "TBC"? (Implemented as described; "TBC" is not blocked yet.)
- L2. **Now blocking real reports** (found on your ME2M file, 2026-10-25): a
  material description contains "AI" as part of a model name, so every report
  listing that product fails. The guard also scans data printed in reports (product names, reasons). A
  material description containing the word "AI" would make a run fail. Should
  the guard check only the wording the application writes, or everything?

## 6. Session log

| Date | Done | Next |
|---|---|---|
| 2026-10-20 | Read legacy scripts (from the uploaded zip; the repository was empty). Wrote `docs/legacy-analysis.md`, `CLAUDE.md`, this plan, `.gitignore`. | Your review and answers; then Phase 1. |
| 2026-10-20 | Phase 1 built and verified locally: backend checks (ruff, mypy, 4 tests), frontend checks (ESLint, Prettier, tsc, 6 tests, production build), `docker compose up` with all five services healthy, `/api/health` 200 (503 when Redis is stopped), migration applied, worker smoke test passed. | Merge the Phase 0–1 pull request; start Phase 2 (login page, admin layout, audit log). |
| 2026-10-21 | Phase 4 built: chunked uploads, parsing, dataset recognition and validation, analysis contract and registry, background runs, dashboards, Excel/Word/PowerPoint reports with templates, language guard, run comparison, demo analysis. Verified: 86 backend tests, 23 frontend unit tests, 24 browser tests (desktop + mobile) incl. upload → run → reports → compare; 210 MB / 4.9 M-row file processed. Fixed on the way: memory (5 GB → 1.8 GB), Excel row limit, missing docxcompose. | Phase 5 needs your SAP headers; meanwhile Phase 6 (publishing). |
| 2026-10-21 | Phase 4 merged. Phase 6 built: publications (frozen snapshot, summary or full detail, optional checks), private / secret link / public, new secret link, unpublish, preview before creating, public Dashboards page and menu entry, sitemap, `/d/` excluded from search engines. Verified: 97 backend tests, 25 frontend unit tests, 28 browser tests (desktop + mobile) incl. publish → secret → public → unpublish. | Phase 5 still needs your SAP headers; next Phase 8 shared-folder pickup and Phase 9 going-live tooling. |
| 2026-10-21 | Phase 6 merged. Phase 8 (folder part) built: shared folder pickup, scheduler service, schedules (set time or new files, name patterns, date rules, skip when unchanged, Run now), e-mail notification, Schedules admin pages. Verified: 119 backend tests, 27 frontend unit tests, browser tests incl. folder → schedule → run; live check of the scheduler container starting a run by itself. | Direct SAP connection waits for SAP access (P1); Phase 5 waits for headers; next Phase 9 going-live tooling. |
| 2026-10-21 | Phase 8 merged. Phase 9 built: production Compose, HSTS + CSP, restic backup service with nightly schedule and retention, restore script, automated backup → wipe → restore test, admin system status, deploy and operations guides, update script. Verified: 123 backend tests, 27 frontend unit tests, browser tests incl. CSP on chart pages; backup/restore on the local stack (row counts and file checksums identical). | Waiting for you: G2 (server, domain), F1/F2 (Phase 5), Phase 7 rules, P1 (SAP access). |
| 2026-10-21 | Phase 9 merged. Decision: no SAP APIs; data only from uploaded SAP spreadsheet exports. | Waiting for you: SAP export headers and preparation scripts (F1/F2, Phase 5), rules and samples (Phase 7), server and domain (G2). |
| 2026-10-21 | Phase 3 built: portfolio content API, public pages, admin editors, file uploads, SMTP contact form, SEO. Verified: 52 backend tests, 17 frontend unit tests, 18 browser tests (desktop + mobile) incl. a real SMTP delivery to Mailpit; 20 page views made 0 backend calls (cache) and pages answer in ~10 ms. | Phase 4: upload and analysis engine. |
| 2026-10-21 | Phase 2 built: login (Argon2, sessions, rate limit, Origin check), audit log, admin area (overview, activity log, settings), CLI for admin account, JSON uvicorn logs, Caddy entry point. Verified: 26 backend tests on PostgreSQL, 13 frontend unit tests, 8 browser tests (desktop + mobile) against the full Docker stack. | Phase 3: portfolio. |
| 2026-10-23 | Phase 5 part 1: SAP export definitions (13 exports), closing stock by WBS, RBC accountability report; workbook sheets without a table are skipped. Verified: 139 backend tests (hand-checked closing and RBC figures, report wording, next-quarter round trip), 27 frontend unit tests, 42 browser tests incl. an RBC run; your real files load without errors; RBC opening by programme equals your June report. | Q1–Q6. |
| 2026-10-24 | Phase 5 part 3 merged. Phase 7: order fill rate, expiry risk, stock in transit, purchase order follow-up, warehouse activity; weekly report reading shared in `analyses/common/weekly.py`; SAP day-first dates. Verified: 228 backend tests, 27 frontend unit tests, 56 browser tests (desktop + mobile) incl. a run of each new analysis; every export you sent is recognised as the right dataset. | Going live (G2); Q13–Q19. |
| 2026-10-23 | Phase 5 part 3: stock count reconciliation, stock sufficiency against AMC, MB51 movement-type filter, counted stock vs final closing, all-sheet inputs, better header detection. Verified: 191 backend tests, 27 frontend unit tests, 48 browser tests (desktop + mobile) incl. reconciliation and AMC runs; your June figures reproduced (AMC Summary, No-AMC list, reconciliation causes). | Phase 7 (your rules); Q1, Q7–Q12. |
| 2026-10-23 | Phase 5 part 2: physical inventory variance investigation (dashboard, Excel, Word, PowerPoint), RBC opening on RMS-PRG-FND-CP only, typed absent columns, most specific dataset first. Verified: 152 backend tests, 44 browser tests (desktop + mobile) incl. a variance run; your real files reproduce the narrative report's tables 1, 2, 5, 6 and the retained-earnings finding exactly. | AMC next; Q1, Q4–Q10. |

Known gaps after Phase 1:
- The cloud session could not pull from Docker Hub (rate limit) or GitHub's container registry, so the local stack test used mirror images and a local copy of the uv binary. The Dockerfiles themselves are unchanged; the `stack` job in GitHub Actions is the authoritative test.
