# CLAUDE.md

Guidance for anyone (human or Claude Code) working in this repository.
Read `docs/PLAN.md` first: it says which phase is in progress, what is done
and what is next.

## What this project is

A web application owned by Ferdinand Bizimana (supply chain, Rwanda Medical
Supply, SAP S/4HANA MM / EWM / SD / FI). It has two parts:

- **Public**: personal portfolio (home, about, experience, skills, projects
  and case studies, CV download, contact form) and a page listing the
  dashboards Ferdinand has chosen to publish. Each published dashboard has
  its own shareable link and is read-only.
- **Private** (one admin user, password login page): upload SAP
  exports (Excel / CSV), choose an analysis, validate columns, run it in the
  background, review an interactive dashboard and self-checks, download
  Excel / Word / PowerPoint reports built on uploaded organisation templates,
  compare periods, publish or unpublish dashboards, edit portfolio content.
- **Automation**: the same analyses on spreadsheets saved in a shared folder,
  on a schedule. There is no direct SAP connection: all data comes from
  spreadsheets exported from SAP.

The original one-off scripts ("legacy scripts") are the reference for
business rules. They are **kept outside this repository** and must never be
committed (`legacy/` is git-ignored). `docs/legacy-analysis.md` summarises
them without real figures; when more detail is needed, ask Ferdinand.

## Layout (target; built up phase by phase)

```
backend/                 FastAPI application (Python 3.12, uv)
  app/
    main.py              app factory, routers
    core/                settings (env vars), security, logging, audit log
    db/                  SQLAlchemy models, session, Alembic migrations
    api/                 routers: public/, admin/, auth/
    content/             portfolio content schemas and service
    storage/             file storage interface + local filesystem adapter
    jobs/                RQ worker tasks (run analysis, render reports)
    datasources/         where input data comes from: upload, shared folder
    analyses/            one self-contained package per analysis
      base.py            Analysis contract, InputSpec, Check, Result
      registry.py        discovers analyses
      stock_count_reconciliation/
      closing_stock_wbs/
      rbc_accountability/
      stock_sufficiency_amc/
    reporting/           Excel / Word / PowerPoint writers, language guard
  tests/
    fixtures/            small FAKE sample files only
frontend/                Next.js (App Router, TypeScript, Tailwind)
  src/app/(public)/      portfolio and public dashboards (cached, tag "portfolio")
  src/app/admin/         private area (sign-in required)
  e2e/                   Playwright browser tests (desktop and mobile)
docs/                    PLAN.md, legacy-analysis.md, operations.md (how to run it)
docker-compose.yml       whole stack, one command
.env.example             every setting, no real values
```

## Running and testing

Everything runs with Docker Compose:

```bash
cp .env.example .env          # then fill in values
docker compose up --build     # http://localhost:8080 (Caddy: /api -> backend, rest -> frontend)
docker compose exec backend python -m app.cli create-admin --email you@example.com
```

Tests and linters (also run in GitHub Actions on every push / PR):

```bash
# backend (tests need PostgreSQL; see backend/tests/conftest.py)
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app tests
TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:55432/test uv run pytest
# frontend
cd frontend && pnpm lint && pnpm typecheck && pnpm test
# browser tests (stack running, admin account created)
cd frontend && E2E_EMAIL=... E2E_PASSWORD=... pnpm e2e
```

pytest treats warnings as errors. GitHub Actions runs all of the above,
including the browser tests on desktop and mobile layouts.

## Rules for analyses (non-negotiable)

1. **Deterministic.** Same input files → same results, byte for byte in the
   result data. No randomness, no current date / time inside calculations
   (the reporting date is an input parameter), stable sorting with explicit
   tie-breakers. Each analysis has a version string, stored with every run
   together with the SHA-256 of each input file.
2. **Self-contained.** One package per analysis under `backend/app/analyses/`.
   An analysis never imports another analysis. Shared helpers go in
   `analyses/common/` only when two analyses really need them. Adding an
   analysis must not require editing other analyses.
3. **Pure core.** The calculation takes pandas DataFrames (keyed by logical
   input name, e.g. `gl_stock_lines`) and parameters, and returns a result
   object. It never reads files, the database or the network. Data sources
   and file parsing sit outside, so uploads can later be replaced by SAP.
4. **Declared inputs.** Each analysis declares its input datasets and the
   exact columns it needs. Validation errors name the file, the sheet and the
   column.
5. **Self-checks.** Every result includes checks (e.g. detail total = summary
   total; opening + difference = closing) with expected value, actual value,
   tolerance and passed / failed. Checks are shown in the dashboard and in
   every report.
6. **Business rules come from the legacy scripts and from Ferdinand.** Where they
   differ, Ferdinand's instructions win. **Never invent a rule or an SAP
   column name.** If something is unclear, ask and record the answer in
   `docs/PLAN.md` (Decisions).
7. **RBC accountability report**: opening stock, receipts and goods issues
   (MB51, by movement type), expired stock scrapped, other movements and
   adjustments, closing stock and the difference, labelled "Increase" or
   "Reduction", with percentages (Ferdinand, 26 October 2026; this replaces
   the earlier "opening, closing and difference only" rule).
8. **Writing**: plain, professional English. Reports must never contain the
   words "AI" or "to be confirmed". A language guard test scans every
   generated report and fails the run if they appear.
9. **Tests**: each analysis has unit tests on fake fixtures with hand-checked
   expected values. Parity with the legacy outputs on real files is checked
   locally only (see "Data protection").

## Adding an analysis

1. Define its input datasets in `backend/app/datasets/definitions.py`, with the
   exact SAP column headers (from Ferdinand) and a type per column.
2. Create `backend/app/analyses/<name>/__init__.py` with a subclass of
   `Analysis` (`base.py`): key, title, version, description, inputs,
   `Parameters` (Pydantic), `compute()` (pure) and `reports()`; end with
   `ANALYSIS = MyAnalysis()`. The registry finds it; nothing else changes.
3. `compute()` returns tables, KPIs, `Check`s and a `Dashboard`
   (`dashboard.py`). Use `rows_of()` for table rows; mark line-level tables
   `level="detail"` so publishing can leave them out.
4. Reports: build a `ReportDocument` and call `build_workbook`, `build_docx`,
   `build_pptx` (`app/reporting/`). The engine runs the language guard.
5. Tests: fake inputs built in code (`tests/samples.py` style), hand-checked
   expected values, a determinism test (same inputs → same `result_hash`).
6. Bump `version` whenever the calculation changes.

Before every push run `scripts/check-commit.sh` (CI checks on a clean export
of the commit).

## Data protection (non-negotiable)

- **No real RMS data in git.** `.gitignore` blocks Excel, CSV, Parquet,
  pickle, Word, PowerPoint, PDF and zip files everywhere except
  `backend/tests/fixtures/`. Fixtures are fake: invented materials, plants,
  quantities and values, with the same column headers as the real exports.
- Do not paste real figures, material numbers, document numbers or product
  lists into code, tests, docs or commit messages.
- Everything is private by default. Publishing creates a **frozen snapshot**
  of the dashboard data at a chosen detail level (e.g. program or plant only).
  Public endpoints read snapshots only, never uploads or run results.
- Secrets live in environment variables. `.env` is git-ignored; keep
  `.env.example` complete and value-free.

## Conventions

- Python: ruff (lint + format), mypy (strict on `app/analyses` and
  `app/reporting`), pytest. Type hints everywhere. Pydantic v2 for API
  schemas and settings.
- TypeScript: strict mode, ESLint, Prettier. Server components by default;
  client components only for interactivity (filters, charts).
- Database changes only through Alembic migrations.
- Money is RWF. Keep full precision in data; round only for display.
- Names in code are English and descriptive; SAP terms (MB5B, WBS, AMC, MOS,
  OX10) are fine.
- Commits: small, imperative subject line ("Add RBC opening/closing
  calculation"). One branch and one pull request per phase.
- Important admin actions (login, failed login, password change, upload, run,
  publish, unpublish, delete) are written to the audit log with
  `app.core.audit.record()`.
- Every admin API route depends on `CurrentUserDep` (401 without a session).
- Public pages fetch through `lib/public-api.ts` (cached); after an admin
  edit, the client calls the `refreshPublicPages` server action.
- Code that runs on the server must not import helpers from a `"use client"`
  file; shared values go in plain modules.
- The browser only talks to one origin (Caddy on :8080, or Next.js rewrites
  in `pnpm dev`); state-changing requests from other origins are refused.

## Working in a cloud session

1. Read `docs/PLAN.md` and continue from "Next".
2. Work on the phase branch, never on `main`.
3. Before opening a pull request: run all tests and linters, start the stack
   with Docker Compose and hit the health check, and list honestly anything
   that does not work yet.
4. At the end of the session, update `docs/PLAN.md` (Done, Next, Decisions,
   Open questions).
