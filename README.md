# Ferdinand Bizimana — portfolio and SAP supply chain analytics

A web application with two parts:

- **Public**: personal portfolio and a page of published, read-only dashboards.
- **Private** (one admin, password login): upload SAP S/4HANA
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
# once, to create your admin account (asks for the password):
docker compose exec backend python -m app.cli create-admin --email you@example.com
```

- Site: http://localhost:8080 (Caddy sends `/api/*` to FastAPI, everything else to Next.js)
- Admin area: http://localhost:8080/admin
- API health check: http://localhost:8080/api/health
- API docs (development only): http://localhost:8000/api/docs

Forgot the password? `docker compose exec backend python -m app.cli set-password --email you@example.com`.
Contact form e-mail, editing content and day-to-day tasks: [`docs/operations.md`](docs/operations.md).

## Develop and test without Docker

Backend (needs [uv](https://docs.astral.sh/uv/)):

```bash
cd backend
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy app tests
# tests need PostgreSQL:
docker run -d --name testpg -p 55432:5432 -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=test postgres:16-alpine
TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:55432/test uv run pytest
```

Frontend (needs Node 22 and pnpm via `corepack enable`):

```bash
cd frontend
pnpm install
pnpm lint && pnpm typecheck && pnpm test
pnpm dev                      # http://localhost:3000, /api forwarded to localhost:8000
# browser tests against a running stack (docker compose up, with COMPOSE_PROFILES=dev-mail
# and SMTP_HOST=mailpit for the contact form test) and an admin account:
E2E_EMAIL=you@example.com E2E_PASSWORD=... pnpm e2e
```

## Data protection

No real data is ever committed. `.gitignore` and `scripts/check_no_data_files.py`
(run in CI and as a pre-commit hook) block Excel, CSV, Parquet, pickle, Word,
PowerPoint, PDF and zip files outside `backend/tests/fixtures/`, which holds
fake samples only. Secrets go in `.env`, which is never committed.
