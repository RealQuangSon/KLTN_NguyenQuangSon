#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PG_BIN=${HOMEMATCH_PG_BIN:-$(pg_config --bindir)}
export PGHOST=127.0.0.1 PGPORT=${HOMEMATCH_PG_PORT:-55432} PGUSER=homematch
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$ROOT/.local/backups"
BACKUP="$ROOT/.local/backups/homematch_dev_$STAMP.dump"
"$PG_BIN/pg_dump" --dbname=homematch_dev --format=custom --file="$BACKUP"
shasum -a 256 "$BACKUP" > "$BACKUP.sha256"
echo "$BACKUP"
