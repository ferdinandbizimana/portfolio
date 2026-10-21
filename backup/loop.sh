#!/bin/sh
# Runs backup.sh every day at BACKUP_TIME (HH:MM, in TZ).
set -eu
: "${BACKUP_TIME:=02:30}"
: "${RESTIC_PASSWORD:?set RESTIC_PASSWORD in .env}"
echo "Backups every day at ${BACKUP_TIME} (${TZ:-UTC}) to ${RESTIC_REPOSITORY:?set RESTIC_REPOSITORY}"
target=$(echo "$BACKUP_TIME" | tr -d :)
last_day=""
while true; do
  today=$(date +%F)
  if [ "$(date +%H%M)" -ge "$target" ] && [ "$today" != "$last_day" ]; then
    backup.sh || echo "Backup failed; see the messages above."
    last_day=$today
  fi
  sleep 30
done
