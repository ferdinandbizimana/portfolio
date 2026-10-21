#!/usr/bin/env bash
# Update the live site to the latest version (run on the server).
# Takes a backup first when backups are set up, then rebuilds and restarts.
# Database migrations run automatically when the backend starts.
set -euo pipefail
cd "$(dirname "$0")/.."

if docker compose config --services | grep -qx backup; then
  echo "== Backup before updating"
  docker compose run --rm backup backup.sh
fi

echo "== Getting the latest version"
git pull --ff-only

echo "== Building and restarting"
docker compose build --pull
docker compose up -d --wait --remove-orphans

echo "== Checking"
docker compose exec -T backend python -c \
  "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"
docker image prune -f >/dev/null
echo "Updated to $(git rev-parse --short HEAD)."
