# Nightly encrypted backups of the database and the stored files with restic.
# PostgreSQL tools (pg_dump, pg_restore) and time zones come with this image.
FROM postgres:16-alpine
COPY --from=restic/restic:0.18.1 /usr/bin/restic /usr/bin/restic
COPY backup.sh restore.sh loop.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/restore.sh /usr/local/bin/loop.sh
CMD ["loop.sh"]
