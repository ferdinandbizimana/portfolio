#!/usr/bin/env bash
# Run the CI checks on exactly what is committed (a clean export of HEAD), so
# files that exist only locally, or are hidden by .gitignore, cannot hide a
# failure. Needs TEST_DATABASE_URL for the backend tests (see backend/tests/conftest.py).
#
#   TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:55432/test scripts/check-commit.sh
set -euo pipefail

repo="$(git rev-parse --show-toplevel)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git -C "$repo" archive HEAD | tar -x -C "$work"

echo "== data guard"
(cd "$work" && git -C "$repo" ls-files | python3 scripts/check_no_data_files.py $(cat))

echo "== backend"
(
  cd "$work/backend"
  uv sync --frozen -q
  uv run ruff check .
  uv run ruff format --check .
  uv run mypy app tests
  uv run pytest -q
)

echo "== frontend"
(
  cd "$work/frontend"
  pnpm install --frozen-lockfile --silent
  pnpm lint
  pnpm typecheck
  pnpm test
)

echo "All checks passed on $(git -C "$repo" rev-parse --short HEAD)."
