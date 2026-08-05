#!/bin/sh
set -eu

: "${BACKUP_DATABASE_URL:?Set BACKUP_DATABASE_URL to the authoritative PostgreSQL database}"
: "${RESTORE_DATABASE_URL:?Set RESTORE_DATABASE_URL to a disposable restore database}"
: "${BACKUP_FILE:?Set BACKUP_FILE to an explicit output path}"

if [ "$BACKUP_DATABASE_URL" = "$RESTORE_DATABASE_URL" ]; then
  echo "Source and restore databases must differ" >&2
  exit 2
fi

pg_dump --dbname "$BACKUP_DATABASE_URL" --format=custom --no-owner --file "$BACKUP_FILE"
pg_restore --dbname "$RESTORE_DATABASE_URL" --clean --if-exists --no-owner "$BACKUP_FILE"
psql "$RESTORE_DATABASE_URL" --set ON_ERROR_STOP=1 --tuples-only --command \
  "SELECT version_num FROM alembic_version; SELECT extname FROM pg_extension WHERE extname = 'vector';"
