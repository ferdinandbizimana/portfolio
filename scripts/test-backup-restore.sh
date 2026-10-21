#!/usr/bin/env bash
# Proves that a backup can be restored, on the running Compose stack:
# back up, wipe the database and the stored files, restore, compare.
# Used in CI; safe to run locally on test data only (it wipes the data!).
set -euo pipefail
cd "$(dirname "$0")/.."

export COMPOSE_PROFILES="${COMPOSE_PROFILES:+$COMPOSE_PROFILES,}backup"
export RESTIC_REPOSITORY=/backups
export RESTIC_PASSWORD="test-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
export BACKUP_LOCAL_DIR=./local-data/backup-test
rm -rf "$BACKUP_LOCAL_DIR"
mkdir -p "$BACKUP_LOCAL_DIR"

sql() {
  docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "$1"' sh "$1"
}
counts() {
  sql "select string_agg(t || '=' || n, ' ' order by t) from (
         select 'users' t, count(*) n from users union all
         select 'data_files', count(*) from data_files union all
         select 'analysis_runs', count(*) from analysis_runs union all
         select 'publications', count(*) from publications union all
         select 'audit_events', count(*) from audit_events) x"
}
files() {
  docker compose exec -T backend sh -c \
    'cd /data/storage && find . -type f ! -path "./system/*" ! -path "./uploads/*" | sort | xargs -r sha256sum | sha256sum'
}

before_counts=$(counts)
before_files=$(files)
echo "Before: $before_counts"

echo "== Backup"
docker compose build -q backup
docker compose run --rm backup backup.sh

echo "== Simulated loss of the database and the files"
docker compose stop backend worker scheduler
sql "drop schema public cascade; create schema public"
docker compose run --rm --entrypoint sh backup -c \
  'find /data/storage -mindepth 1 -maxdepth 1 ! -name system -exec rm -rf {} +'

echo "== Restore"
docker compose run --rm backup restore.sh
docker compose up -d --wait backend worker scheduler

after_counts=$(counts)
after_files=$(files)
echo "After:  $after_counts"
[ "$before_counts" = "$after_counts" ] || { echo "Row counts differ after restore"; exit 1; }
[ "$before_files" = "$after_files" ] || { echo "Stored files differ after restore"; exit 1; }
curl --fail --silent --show-error http://localhost:8080/api/health >/dev/null
echo "Backup and restore: OK"
