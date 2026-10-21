#!/bin/sh
# One backup: database dump + stored files -> encrypted restic repository.
# Needs: RESTIC_REPOSITORY, RESTIC_PASSWORD (and the storage provider's keys),
# PGHOST, PGUSER, PGPASSWORD, PGDATABASE.
set -eu
STATUS_DIR=/data/storage/system
WORK=/tmp/backup
mkdir -p "$WORK" "$STATUS_DIR"

status() {  # result message
  printf '{"result": "%s", "finished_at": "%s", "message": "%s"}\n' \
    "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$2" > "$STATUS_DIR/last-backup.json"
}
trap 'status failed "The backup stopped with an error. See: docker compose logs backup"' EXIT

if ! restic cat config >/dev/null 2>&1; then
  echo "Creating the backup repository"
  restic init
fi

echo "Dumping the database"
pg_dump --format=custom --no-owner --file="$WORK/database.dump"

echo "Saving to $RESTIC_REPOSITORY"
restic backup --tag portfolio --host portfolio "$WORK/database.dump" /data/storage \
  --exclude /data/storage/uploads --exclude "$STATUS_DIR"

echo "Removing old backups (keep 7 daily, 4 weekly, 12 monthly)"
restic forget --tag portfolio --keep-daily 7 --keep-weekly 4 --keep-monthly 12 --prune

# Check a sample of the stored data each time.
restic check --read-data-subset=5%

rm -f "$WORK/database.dump"
trap - EXIT
snapshot=$(restic snapshots --tag portfolio --latest 1 --json | sed -n 's/.*"short_id":"\([0-9a-f]*\)".*/\1/p' | tail -1)
status ok "Snapshot ${snapshot}"
if [ -n "${BACKUP_PING_URL:-}" ]; then
  wget -q -O /dev/null "$BACKUP_PING_URL" || echo "Could not reach BACKUP_PING_URL"
fi
echo "Backup finished: snapshot ${snapshot}"
