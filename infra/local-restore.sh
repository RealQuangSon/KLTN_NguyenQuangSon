#!/usr/bin/env bash
set -euo pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PG_BIN=${HOMEMATCH_PG_BIN:-$(pg_config --bindir)}
BACKUP=${1:?Usage: bash infra/local-restore.sh /absolute/path/backup.dump}
[[ -f "$BACKUP" ]] || { echo "Backup does not exist." >&2; exit 2; }
[[ -f "$BACKUP.sha256" ]] || { echo "Missing backup checksum." >&2; exit 2; }
shasum -a 256 -c "$BACKUP.sha256"
export PGHOST=127.0.0.1 PGPORT=${HOMEMATCH_PG_PORT:-55432} PGUSER=homematch
TARGET="homematch_restore_$(date -u +%Y%m%dT%H%M%SZ | tr '[:upper:]' '[:lower:]')"
# A new database only: no drop, clean or overwrite of dev/test state.
"$PG_BIN/createdb" "$TARGET"
"$PG_BIN/pg_restore" --dbname="$TARGET" --no-owner --no-privileges --exit-on-error "$BACKUP"
echo "Restored to new local database: $TARGET"
echo "Verify ledger and checkpoint counts, then run the application against this database."
