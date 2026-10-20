# Ferdinand Bizimana — portfolio and SAP supply chain analytics

A web application with two parts:

- **Public**: personal portfolio and a page of published, read-only dashboards.
- **Private** (one admin, password + two-factor login): upload SAP S/4HANA
  exports, run fixed, tested analyses (stock reconciliation, closing stock by
  WBS, RBC accountability, stock sufficiency against AMC, and more), review
  dashboards and self-checks, and download Excel / Word / PowerPoint reports.

Status and roadmap: [`docs/PLAN.md`](docs/PLAN.md). Conventions for
contributors: [`CLAUDE.md`](CLAUDE.md).

## Stack

FastAPI (Python 3.12) · PostgreSQL · Redis + RQ worker · Next.js (TypeScript,
Tailwind) · Docker Compose.

## Run locally

Requires Docker with Compose v2.

```bash
cp .env.example .env     # set POSTGRES_PASSWORD
docker compose up --build
```

- Frontend: http://localhost:3000
- API health check: http://localhost:8000/api/health
- API docs (development only): http://localhost:8000/api/docs

## Develop and test without Docker

Backend (needs [uv](https://docs.astral.sh/uv/)):

```bash
cd backend
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest
```

Frontend (needs Node 22 and pnpm via `corepack enable`):

```bash
cd frontend
pnpm install
pnpm lint && pnpm typecheck && pnpm test
pnpm dev
```

## Data protection

No real data is ever committed. `.gitignore` and `scripts/check_no_data_files.py`
(run in CI and as a pre-commit hook) block Excel, CSV, Parquet, pickle, Word,
PowerPoint, PDF and zip files outside `backend/tests/fixtures/`, which holds
fake samples only. Secrets go in `.env`, which is never committed.
