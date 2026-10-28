# Build plan

Status: **Phase 13 (spot check accuracy, expiry projection, donations) in
progress**. Phases 0–12 and the RBC receipts and goods issues are merged.
Phase 13 adds spot check accuracy, the months-of-stock projection in Expiry
risk and the donations list in Expiry monitoring. Next: going live (G2: a
server and a domain) and fillable copies of the templates you shared. Still needs something from you: Q1, Q7–Q24, L2 and G2.

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
- [ ] The actual server. Domain chosen: **ferdinandbizimana.rw** (27 October 2026). **Waiting for you** (G2): rent the server (recommendation in `docs/deploy.md`, "Choosing the server": 8 GB, 80–100 GB, preferably in Kigali), then follow `docs/deploy.md` (about an hour). I can guide you step by step.

### Phase 10 — Spot-check variance follow-up
- [x] Bin list upload (storage bin → responsible person, e-mails below the bins);
      names matched whatever the word order or small spelling differences;
      bins of warehouse units (RECEIVING, PICKING) left out
- [x] Variances from the spot check sheet, the picking register ("REPORTING ON
      MISSING") and the PI document counting template, assigned by bin
- [x] E-mail on assignment and a list of open variances each working morning;
      every e-mail copied (BCC) to VARIANCE_BCC
- [x] Secure link (no account): the person records the reason, the responsible
      unit (Receiving, Picking, Putaway / bin moves, System EWM–ERP), the action
      taken and their name; green when corrected, red after 2 days
- [x] Admin page: by person, filters, reassign, close or reopen, copy link,
      Excel export
- [x] Picker accuracy (Q27): lines and discrepancies per picker and per day from
      the picking register's daily sheets, by customer and order type from the
      sheets with one row per outbound delivery; target 100% (Q28; a parameter).
      Local check on your register: every day read correctly from the sheet names
- [ ] Your check on real data: upload the bin list and one week's spot check

### Phase 11 — Interactive HTML dashboards, order fill rate in your format
- [x] Interactive HTML dashboard engine: one self-contained file per run (data
      inside, works offline), filters that apply to every section, KPIs,
      charts and sortable, searchable tables; opened from the run page and
      downloaded with the other reports; checked by the language guard
- [x] Order fill rate laid out like "RMS Order Fill Rate Dashboard FY2025/26":
      loss per WBS (RM: ZRMS + ZSPO in RWF; donor ZDON in units), monthly
      trend, fiscal quarters, plant / shipping point, items most requested
      and not delivered, most-missing items over time, Delivered-In-Full per
      order and customer; plus regional analysis (region, district, border
      districts, facility type); filters: quarter, month, plant, WBS, order
      type, customer, item, region, district, border
- [x] Excel workbook of every detail line
- [x] Same dashboard style for the other analyses (variance investigation,
      RBC, stock sufficiency, expiry, warehouse, PO, transit, picker)
- [x] RBC dashboard laid out like your "RBC Program Stock" dashboard: filters
      for programme, plant, product and value band (the larger of opening and
      closing), KPIs (opening, closing, difference with Increase / Reduction
      %, products in stock at closing), opening against closing by programme
      and by plant (top 15), the closing stock list with a summary by
      programme and CSV download, and every plant-product line with its
      difference and closing quantity. Still only opening, closing and the
      difference. Not taken over: the two-quarter switch (one run covers one
      period; compare runs instead) and the AMC section (that is the stock
      sufficiency analysis, which has its own dashboard)

### Phase 12 — Expiry monitoring (monthly ZSTOCKREPORT)
- [x] Snapshot of each monthly ZSTOCKREPORT kept; any period (month, quarter,
      half year, financial year July–June) compares its opening and closing
      month, cumulatively
- [x] Expired batches per plant (expiry date on or before the report date);
      flag expired batches not blocked or not in the quarantine plant; days
      from expiry to scrapping (MB51 551 / 555)
- [x] Batches due to expire in the period: cleared, expired or still in stock;
      projection (opening) against actual expiries (closing): the difference is
      the value saved; reports saved per period
- [x] Donations made to save expiries (list of donated products from Sales;
      see Phase 13)
- [x] Distributed with less than 3 months of shelf life left (all distribution
      movement types; for 641, whether the receiving plant issued or expired it)
- [x] Batches whose expiry date changed between two snapshots
- [x] Board reports per plant: executive expiry dashboard, stock expiry and
      intervention dashboard, expiry justifications (commercial RMS-OWN /
      programme RMS-PRG); monthly, quarterly and yearly
- [x] Justifications: each month the expired items are listed; the responsible
      person picks a root cause from a list (Other = own reason) and writes it
- [x] E-mail on the last day of each month: expired, 0–3 and 3–6 months, value
      per plant; Excel attached and a secure link; to the sales pharmacist, CC
      managers and you, BCC the manager address
### Phase 13 — Spot check accuracy, expiry projection, donations
- [x] Spot check accuracy from the weekly spot check sheet (EWM bin stock with
      the quantity found, variance and comment; both layouts you sent):
      quantity and line accuracy, raw and "true" (variances explained by the
      comment left out), variance value, data-integrity flags (wrong batch,
      expiry or description), by WBS, storage type and responsible person (bin
      list), comparison with the previous spot check; Excel, Word, PowerPoint
      and interactive dashboard
- [x] Expiry projection in Expiry risk: per material and WBS on unrestricted
      stock, remaining shelf life (average months to expiry of the unexpired
      batches), months of stock from the AMC, at-risk quantity = quantity −
      AMC × remaining shelf life; Overstock / Risk of stockout. ZSTOCKREPORT
      has no goods receipt date, so it covers all stock, not only the week's
      receipts
- [x] Donations to save expiries in Expiry monitoring: Sales' list (the
      ZSTOCKREPORT lines of the donated products with Total Value, Status,
      Customer, Reason for Donation); donated value, value saved by donation,
      by reason and by customer

## 4. Decisions

| Date | Decision |
|---|---|
| 2026-10-26 | Expiry (Ferdinand): a batch has expired when ZSTOCKREPORT shows its expiry date on or before the report date; every expired batch must be blocked and moved to the quarantine plant; MB51 scrapping (551 / 555) gives the days from expiry to scrapping. A period compares its opening and closing monthly ZSTOCKREPORT (month, quarter, six months, year; cumulative). Batches due to expire end as cleared, expired or still in stock. Savings = projected expiries (opening) − actual expiries (closing); reports are saved as snapshots. Donations: a list of donated products from Sales. Distribution with < 3 months shelf life: all distribution movement types; for 641 check whether the receiving plant issued or expired the batch. Commercial = RMS-OWN (sales revenue), programme = RMS-PRG (CP). Justifications: root cause from a drop-down, "Other" with own text. Monthly e-mail on the last day of the month to the sales pharmacist (all scope), CC the two managers and Ferdinand, BCC as for variances; Excel attached and a secure link; lists expired, 0–3 and 3–6 months with value per plant. Periods are financial (July–June). Addresses live in settings, never in git. |
| 2026-10-26 | Each period of expiry monitoring is one run over two ZSTOCKREPORTs (opening and closing month); runs and their reports stay stored, so every period's report can be opened again. A batch followed by material and batch: one moved to another plant and expired there counts as expired (value saved is counted where the batch is at closing). Root causes of the justification list are the ones named in Ferdinand's expiry justifications report, plus Other. |
| 2026-10-26 | The quarantine plant is 9900 (Ferdinand): the default of the run's "Quarantine plants" parameter, which takes codes (or starts of codes), comma-separated. |
| 2026-10-26 | Every analysis gives an Excel workbook and an HTML dashboard (Ferdinand). The engine adds a standard one built from the result tables when an analysis has no layout of its own. |
| 2026-10-26 | Dashboards follow Ferdinand's own HTML dashboards: one self-contained interactive page per run, downloadable, with filters applying to every section, plus an Excel workbook of all detail lines. |
| 2026-10-20 | Report generation is done in Python only (openpyxl, docxtpl, python-docx, python-pptx); the legacy Node scripts are not reused. |
| 2026-10-20 | Analyses are pure functions over named datasets; data sources are separate (upload now, folder and SAP later). |
| 2026-10-20 | Your instructions override legacy behaviour; for the RBC report receipts, issues and expired stock are never shown (replaced on 2026-10-26, below). |
| 2026-10-28 | Stock in transit (Ferdinand): the money of the outbound delivery must be visible, material-wise: the OBD value (641 goods issue in MB51, for the quantity still in transit) is a column of every line, a total, and a "By material" table, in the dashboard, the HTML dashboard and Excel. Version 1.4.0. |
| 2026-10-28 | Run again (Ferdinand): a finished run can be run again on the same files, sheets and parameters, with the current version of the analysis, without filling the form in again; the earlier run is kept (results stay reproducible). "Change and run again" opens the form filled in from the run. |
| 2026-10-28 | Stock in transit (Ferdinand, manual test): the line count must match the MB5T document (643 lines, not 628): every MB5T line is now a line, lines of the same STO and material are no longer merged (the MB51 comparison stays per STO and material, shown on its first line). MB5T can give no value: the value is then that of the goods issue (641) of the outbound delivery in MB51, open quantity × the 641's value per unit, shared over the STO's MB5T lines by quantity ("Value from" column). Version 1.3.0. |
| 2026-10-28 | Feedback on the guide (Ferdinand): (1) report pages show a "Downloads" list with a Download button per file; (2) new variances are no longer e-mailed one import at a time: each person gets one e-mail with all their new variances when the day closes (`VARIANCE_DAY_CLOSE_TIME`, default 17:00) or when the admin clicks "Send e-mails now"; (3) a correction records the root cause (the cause list of the spot check findings file), the reason, the optional quantity corrected and the responsible unit, and marks the variance corrected; (4) each imported variance file has an accuracy progress line (line and quantity accuracy when imported, and now, counting only the variances still open; same formulas as the spot check accuracy analysis), on the page and in the Excel export; (5) the expiry follow-up also lists every material expiring within 6 months, where the pharmacist records the measure taken to avoid the expiry. The measures list (redistribute, transfer to another branch, inform customers, donation agreed with Sales, return or exchange with the supplier, issue first, other) is a proposal built from the actions in the monthly e-mail (Q32). |
| 2026-10-28 | Test data (Ferdinand: "insert dummy data where you don't have data"): `python -m app.cli seed-demo` fills a test installation with a sample portfolio (only the name, field and SAP modules are real; the rest is marked "(sample)") and 24 fake `DEMO_` files covering every analysis, then runs each analysis and prepares the variance and expiry follow-ups. Materials, plants, customers, staff and figures are invented from a fixed seed; nothing comes from RMS data. Refused in production. The first admin account can also come from `ADMIN_EMAIL` / `ADMIN_PASSWORD` in `.env` (seed-admin at start). |
| 2026-10-27 | Look and names (Ferdinand): the website uses the shades of Ferdinand's own dashboards (navy ink #15234A, blue accent #0079BF, light blue-grey panels, green / amber / red for status; dark mode to match), with no RMS logo or gold. RMS and RBC names appear only in the exported files (Excel, HTML dashboards, Word, PowerPoint); the website's menus, analysis names, form labels and page headings use neutral names (e.g. "Programme stock accountability" for the RBC report). Domain: ferdinandbizimana.rw. |
| 2026-10-26 | Spot check accuracy (Ferdinand; from the spot check progress report): quantity accuracy = 1 − \|sum of variances\| / sum of system quantities ("Qty AUoM", else the available quantity); line accuracy = 1 − lines with a variance / lines checked. True accuracy leaves out variance lines whose comment explains them: picked, served, delivered, bin to bin, moved, corrected (a parameter). Data-integrity flags: comments mentioning batch, lot, expiry ("EXPIR", "EX:") or description ("DESC"), a parameter. Variance value = "variance on cost", else variance × "Uunit cost". Rows without a product code are left out. Headers read: ONHAND QTY / SOH (counted), VARIANCE, COMMENT / Comments. |
| 2026-10-26 | Expiry projection (Ferdinand, from "Projection of Expiration for items received"): remaining shelf life (months) from the expiry date at the report date; MOS = quantity / AMC; at-risk quantity = quantity − AMC × remaining shelf life; Overstock when MOS − remaining shelf life > 0, Risk of stockout when < 0; built from ZSTOCKREPORT and the AMC. Donations list (Ferdinand): the ZSTOCKREPORT lines of the donated products plus total value, status (donated), customer if any and reason for donation. Built as: a line counts as donated when its status is empty or says "donated" (other statuses are listed only); a donated batch that was due to expire in the period counts as saved by donation (by material when the line has no batch). Headers expected: Total Value, Status, Customer, Reason for Donation (send a sample to confirm, Q30). |
| 2026-10-26 | RBC report (Ferdinand): receipts and goods issues from MB51 in every RBC output (Excel, Word, PowerPoint, HTML), split by movement type; scrapping shown as its own column "Scrapped (expired)". Defaults (parameters, change them on the run form if needed): receipts 101, 102; goods issues 601, 602, 641, 642, Y01, Z01, X01; scrapping 551, 555. Only MB51 lines on the WBS posted in the period (after the opening date, up to the closing date) count; amounts keep the MB51 sign (issues negative). "Other movements and adjustments" = closing − opening − receipts − goods issues − scrapped, so every line rolls forward. The CPDS Report data sheet gets the legacy columns Total Receipt Qties / Values and Total Issue Quantities / Values again. |
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
| 2026-10-26 | Spot-check follow-up agreed with Ferdinand: staff close a variance through a secure link in the e-mail (no account); one e-mail when variances are assigned, then a list each working morning (07:30, Monday–Friday); red when open for more than 2 days; responsible units Receiving, Picking, Putaway / bin moves, System (EWM–ERP); every e-mail in BCC to Ferdinand (address in `.env`, `VARIANCE_BCC`). Bins of units (RECEIVING, PICKING) are left out. The link token is kept (like a publication's secret link) because the morning list repeats each link; the database is never public. |
| 2026-10-26 | Same line imported twice = one variance: the picking register grows, so its lines are recognised again; a spot check file is one check (the same line in a new file is a new variance); PI lines by document and item. A date typed by hand that cannot be read is left empty with a warning instead of refusing the file. |
| 2026-10-26 | Dates with slashes: the order is decided per column (a day above 12 shows it); EWM exports of RMS are month first (6/30/2026); when every date fits both, month first. Dots are always day first. |
| 2026-10-26 | The data files list counted runs once per file (2 s with 500 files, slower than the page's 2-second refresh, so the page stopped updating): it now counts once per request. |
| 2026-10-26 | Picker accuracy: accuracy = 1 − discrepancies / lines picked; the day of a daily sheet is read from its name ("25nov", "26 NOV", "28TH nov", "27112025", "2122025" = 2 December 2025, the reading nearest the other days); names without a year take the year of the other sheets and of the delivery rows; the same picker in different capitals is one picker. G2: Ferdinand is buying the server and the domain. |
| 2026-10-26 | The variance Excel export is a working list (downloaded and edited to get the right data), not a report: it lists what was uploaded and typed by staff, and is not passed through the language guard (Q26, Ferdinand). Reports still are. |
| 2026-10-26 | Picker accuracy target is 100% (Q28, Ferdinand): a picker with any discrepancy is below target. It stays a parameter of the run. |
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
- Q28: answered 2026-10-26: the target is 100% (default of the parameter).
- Q29: answered 2026-10-26: the quarantine plant is 9900.
- Q30. Donations: built from your description (ZSTOCKREPORT columns plus
  Total Value, Status, Customer, Reason for Donation). Please send one list
  from Sales (headers are enough) to confirm the exact header names.
- Q31. RBC dashboard: received as an artifact on 2026-10-26 and applied. The spot
  check dashboard you linked is inside a Claude chat, which the app cannot open:
  please attach its HTML or share it as an artifact.
- Q32. Expiry measures: is the proposed list right (redistribute to facilities
  that use it; transfer to another branch; inform customers and promote the
  product; donation agreed with Sales; return or exchange with the supplier;
  issue first; other, described)? Add or rename any.
- Q33. Word and PowerPoint reports should follow the RMS Approved Brand Guide.
  Please send the guide (colours, fonts, logo rules), or simpler: an RMS Word
  template and an RMS PowerPoint template, which can be uploaded at once in
  Admin → Templates and are then used for every report.
- Q26: answered 2026-10-26: keep it; the variance Excel export is not passed through the language guard.
- Q27: answered (yes): built as the Picker accuracy analysis.
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
- R2: answered 2026-10-26: the roll-forward is shown in the report (receipts,
  goods issues, scrapped, other movements and adjustments).
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
| 2026-10-26 | Spot check accuracy analysis built from your two spot check files and progress report. Verified: hand-checked tests, browser test (desktop + mobile), your 17 September sheet locally (outside git): 685 lines, 36 with a variance, every check passes, quantities as in your progress report except one row without a product code (left out). | Expiry projection; donations list. |
| 2026-10-26 | RBC report shows receipts, goods issues (MB51 by movement type) and scrapped (expired) stock in every output, with other movements and adjustments so each line rolls forward. Verified: hand-checked fake MB51 lines (reversals, other WBS, other types, posting after the period), round trip of the data sheet. | Spot check files received: build the spot check analysis from them. |
| 2026-10-26 | RBC dashboard follows your "RBC Program Stock" layout (value band filter, products in stock, opening vs closing by plant, closing stock list, products by plant). Verified: RBC tests incl. a new layout test, ruff, mypy, rendering in Chromium on desktop and mobile with no errors. | Spot check dashboard (Q31), donations list (Q30), going live (G2). |
| 2026-10-26 | Phase 7 answers merged (PR 15). Phase 10 built: variance follow-up (bin list, three sources, secure link, e-mails, morning list, admin page, export). Verified: 247 backend tests, 30 frontend unit tests, browser test of the whole flow (bin list → variance → e-mail with BCC via Mailpit → link → corrected) on desktop and mobile; your real bin list gives exactly the six people with their e-mails; your PI document gives 624 variances, the picking register 321. | Going live (G2). |
| 2026-10-24 | Phase 5 part 3 merged. Phase 7: order fill rate, expiry risk, stock in transit, purchase order follow-up, warehouse activity; weekly report reading shared in `analyses/common/weekly.py`; SAP day-first dates. Verified: 228 backend tests, 27 frontend unit tests, 56 browser tests (desktop + mobile) incl. a run of each new analysis; every export you sent is recognised as the right dataset. | Going live (G2); Q13–Q19. |
| 2026-10-23 | Phase 5 part 3: stock count reconciliation, stock sufficiency against AMC, MB51 movement-type filter, counted stock vs final closing, all-sheet inputs, better header detection. Verified: 191 backend tests, 27 frontend unit tests, 48 browser tests (desktop + mobile) incl. reconciliation and AMC runs; your June figures reproduced (AMC Summary, No-AMC list, reconciliation causes). | Phase 7 (your rules); Q1, Q7–Q12. |
| 2026-10-23 | Phase 5 part 2: physical inventory variance investigation (dashboard, Excel, Word, PowerPoint), RBC opening on RMS-PRG-FND-CP only, typed absent columns, most specific dataset first. Verified: 152 backend tests, 44 browser tests (desktop + mobile) incl. a variance run; your real files reproduce the narrative report's tables 1, 2, 5, 6 and the retained-earnings finding exactly. | AMC next; Q1, Q4–Q10. |
| 2026-10-28 | Feedback round on the guide: Download buttons on run pages; variance e-mails grouped per person at the day close or on "Send e-mails now"; root cause and quantity corrected on every correction; accuracy progress per imported file (page and Excel); expiry measures for items expiring within 6 months (pharmacist's page, Excel). Verified: backend tests (new: day close, send now, root cause, progress, measures), frontend checks, browser tests updated. | Q32 (measures list), Q33 (brand guide or RMS templates), going live (G2). |
| 2026-10-28 | Stock in transit fixes from your manual test: every MB5T line counted; value from the MB51 goods issue of the outbound delivery when MB5T has none. Verified: new hand-checked test (split STO lines, values from MB51, long-transit value). | Rerun stock in transit on your files to confirm 643 lines and the value; Q32, Q33, G2. |
| 2026-10-28 | Run again and "Change and run again" on every finished run. Verified: backend test (same inputs and parameters, new version, same result), browser test of both buttons. | Run stock in transit again on your files (643 lines, values from MB51); Q32, Q33, G2. |

Known gaps after Phase 1:
- The cloud session could not pull from Docker Hub (rate limit) or GitHub's container registry, so the local stack test used mirror images and a local copy of the uv binary. The Dockerfiles themselves are unchanged; the `stack` job in GitHub Actions is the authoritative test.
