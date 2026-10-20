# Build plan

Status: **Phase 0 (exploration and plan) — waiting for approval.**
No application code is written until this plan is approved.

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
| Authentication | Built into the backend: Argon2 password hash, TOTP two-factor (authenticator app) with one-time recovery codes, server-side sessions in an HttpOnly, Secure, SameSite=Strict cookie, CSRF token, login rate limiting | One user only, so no external identity provider is needed. Everything stays in the application you own. The admin account is created from the command line, never through a public sign-up. |
| Contact form | Stored in the database and e-mailed via SMTP (any provider) with a honeypot field and rate limiting | No third-party form service; messages are visible in the admin area even if e-mail fails. |
| Tests and linting | pytest, ruff, mypy; ESLint, Prettier, Vitest; Playwright for a few end-to-end checks later | Standard tools. All run in GitHub Actions on every push and pull request. |
| Local run | Docker Compose: `frontend`, `backend`, `worker`, `postgres`, `redis` | `docker compose up` starts everything. |
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
3. `SapSource` (Phase 8): read-only OData / CDS queries on S/4HANA.

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
- [ ] Your approval of the plan and answers to the questions in section 5

### Phase 1 — Foundation
- [ ] Monorepo layout: `backend/`, `frontend/`, `docs/`; `legacy/` added unchanged
- [ ] Backend skeleton: settings from environment, `/api/health` (checks DB and Redis), structured logging
- [ ] Alembic set up with a first empty migration
- [ ] Frontend skeleton: Next.js + TypeScript + Tailwind, a placeholder home page, calls the health check
- [ ] Worker container with a trivial test job
- [ ] `docker-compose.yml` (frontend, backend, worker, postgres, redis) — `docker compose up` works
- [ ] `.env.example` listing every setting
- [ ] GitHub Actions: backend lint/type/test, frontend lint/type/test, Docker build
- [ ] Pre-commit check that rejects data files (xlsx, csv, …) outside `backend/tests/fixtures/`
- [ ] README: what the project is, how to run, how to test

### Phase 2 — Login and admin area
- [ ] User table; `create-admin` command line tool
- [ ] Login with password (Argon2) and TOTP; enrolment with QR code; recovery codes
- [ ] Sessions in secure cookies, CSRF protection, logout, session expiry
- [ ] Login rate limiting and lockout after repeated failures
- [ ] Audit log table and admin page (login, failures, 2FA changes, later uploads, runs, publishing)
- [ ] Admin layout: navigation, dashboard home, settings
- [ ] Tests for every auth path, including wrong code and expired session

### Phase 3 — Portfolio
- [ ] Content model: profile, about, experience, skills, projects / case studies, CV file, contact messages
- [ ] Public pages: home, about, experience, skills, projects, case study pages, CV download, contact form
- [ ] Admin editors for all content (Markdown for long text), image and CV upload
- [ ] Static rendering with revalidation on save; SEO metadata, Open Graph image, sitemap
- [ ] Mobile-first layout, accessibility checks, Lighthouse performance ≥ 90
- [ ] Contact form: validation, honeypot, rate limit, stored + e-mailed

### Phase 4 — Upload and analysis engine
- [ ] Chunked, resumable upload for large files (200 MB+), progress bar, SHA-256 hash
- [ ] Parse Excel / CSV to Parquet in the worker; keep the original file private
- [ ] Dataset detection by sheet name and headers, with confirmation screen
- [ ] Column validation with clear messages: file, sheet, column, what is wrong
- [ ] Analysis registry and the contract in section 2
- [ ] Run in background with progress; cancel; error messages
- [ ] Store results, checks, dashboard data; run history page
- [ ] Generic dashboard renderer (KPI tiles, charts, filterable tables)
- [ ] Report generation framework: Excel, Word (docxtpl), PowerPoint; template upload and versioning
- [ ] Language guard: reports fail if they contain "AI" or "to be confirmed"
- [ ] Compare two runs of the same analysis
- [ ] One small demo analysis on fake data to prove the whole flow end to end

### Phase 5 — First analyses (from legacy)
For each: input specs from real headers (you provide), fake fixtures, rules,
checks, dashboard, reports, tests, and a **local parity script** that runs the
new code and the legacy logic on your real files (kept outside git) and
compares totals line by line.
- [ ] Stock count reconciliation (w2 / w3 / w4)
- [ ] Final closing stock by WBS (w5)
- [ ] RBC accountability report (w6) — opening, closing, difference only
- [ ] Stock sufficiency against AMC (w6)
- [ ] Parity confirmed by you on real files for all four

### Phase 6 — Publishing
- [ ] Visibility: private, secret link, public; unpublish
- [ ] Detail level choice (program / plant / product) and a preview of exactly what will be visible
- [ ] Frozen snapshots; public endpoints read snapshots only
- [ ] Public dashboards page and per-dashboard pages with filters, search, charts, tables
- [ ] Tests proving public endpoints cannot reach uploads, runs or unpublished snapshots

### Phase 7 — More analyses
Rules and fake-safe samples from you for each:
- [ ] Order fill rate
- [ ] Physical inventory
- [ ] Procurement and tender analytics
- [ ] Inventory performance

### Phase 8 — SAP connection
- [ ] `FolderSource`: watch a shared folder, pick up new exports, run scheduled analyses
- [ ] Scheduler (nightly by default), run notifications
- [ ] `SapSource`: read-only OData / CDS connection to S/4HANA with a technical user
- [ ] Same results from SAP as from the equivalent uploaded files (tested)

### Phase 9 — Going live
- [ ] VPS setup, domain, Caddy with HTTPS, security headers
- [ ] Production Docker Compose, secrets on the server only
- [ ] Nightly encrypted off-site backups; restore tested
- [ ] Monitoring: uptime check, error log
- [ ] `docs/operations.md`: how to update, back up, restore, rotate secrets

## 4. Decisions

| Date | Decision |
|---|---|
| 2026-10-20 | Report generation is done in Python only (openpyxl, docxtpl, python-docx, python-pptx); the legacy Node scripts are not reused. |
| 2026-10-20 | Analyses are pure functions over named datasets; data sources are separate (upload now, folder and SAP later). |
| 2026-10-20 | Your instructions override legacy behaviour; for the RBC report receipts, issues and expired stock are never shown. |

## 5. Open questions

Answers will be recorded in section 4 (Decisions).

**General (needed before Phase 1–3)**
- G1. Is the GitHub repository public or private? The legacy scripts contain a
  few real figures (quarter totals, GL document numbers and amounts, product
  names in narrative text). Commit `legacy/` as it is, or only while the
  repository stays private?
- G2. Hosting: do you have a domain and a preferred server provider or budget? (Phase 9)
- G3. Contact form: which address receives messages, and which SMTP account can send them?
- G4. Two-factor with an authenticator app (Microsoft / Google Authenticator) — acceptable?
- G5. Report narrative: the app writes fixed, rule-based sentences from the
  numbers, and you can add or edit commentary sections in the admin area
  before generating Word / PowerPoint. Acceptable?

**Files (needed before Phase 5)**
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
- L1. "AI" check: whole word, upper case only (so "AID" or "maintain" pass)?
  "to be confirmed": any case. Also forbid "TBC"?

## 6. Session log

| Date | Done | Next |
|---|---|---|
| 2026-10-20 | Read legacy scripts (from the uploaded zip; the repository was empty). Wrote `docs/legacy-analysis.md`, `CLAUDE.md`, this plan, `.gitignore`. | Your review and answers; then Phase 1. |
