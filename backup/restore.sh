#!/bin/sh
# Restore the database and the stored files from a backup.
#   restore.sh            the latest backup
#   restore.sh 1a2b3c4d   a given snapshot (see: restic snapshots)
# Stop the backend, worker and scheduler first (see docs/operations.md).
set -eu
SNAPSHOT=${1:-latest}
TARGET=/tmp/restore
rm -rf "$TARGET"
mkdir -p "$TARGET"

echo "Reading snapshot ${SNAPSHOT} from $RESTIC_REPOSITORY"
restic restore "$SNAPSHOT" --tag portfolio --target "$TARGET"

echo "Restoring the database"
pg_restore --clean --if-exists --no-owner --dbname="$PGDATABASE" "$TARGET/tmp/backup/database.dump"

echo "Restoring the stored files"
mkdir -p /data/storage
# Replace the current files by the backed-up ones (the backup status is kept).
find /data/storage -mindepth 1 -maxdepth 1 ! -name system -exec rm -rf {} +
cp -a "$TARGET/data/storage/." /data/storage/

rm -rf "$TARGET"
echo "Restore finished. Start the services again: docker compose up -d"
