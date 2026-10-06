#!/usr/bin/env bash
set -euo pipefail

# Isolated, localhost-only development cluster; never touches a system service.
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PG_BIN=${HOMEMATCH_PG_BIN:-$(pg_config --bindir)}
PG_DATA="$ROOT/.local/pgdata"
PG_SOCKET="$ROOT/.local/pgsocket"
PG_PORT=${HOMEMATCH_PG_PORT:-55432}
ACTION=${1:-status}

if ! [[ "$PG_PORT" =~ ^[0-9]+$ ]] || (( PG_PORT < 1024 || PG_PORT > 65535 )); then
  echo "HOMEMATCH_PG_PORT must be a port between 1024 and 65535." >&2
  exit 2
fi

case "$ACTION" in
  start)
    mkdir -p "$PG_SOCKET"
    if [[ ! -f "$PG_DATA/PG_VERSION" ]]; then
      "$PG_BIN/initdb" -D "$PG_DATA" --username homematch --auth-local=trust \
        --auth-host=trust --encoding=UTF8 --no-locale
    fi
    if ! "$PG_BIN/pg_ctl" -D "$PG_DATA" status >/dev/null 2>&1; then
      "$PG_BIN/pg_ctl" -D "$PG_DATA" -l "$ROOT/.local/postgres.log" \
        -o "-h 127.0.0.1 -p $PG_PORT -k $PG_SOCKET" start
    fi
    for DB in homematch_dev homematch_test; do
      EXISTS=$("$PG_BIN/psql" -h 127.0.0.1 -p "$PG_PORT" -U homematch \
        -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DB'")
      if [[ "$EXISTS" != 1 ]]; then
        "$PG_BIN/createdb" -h 127.0.0.1 -p "$PG_PORT" -U homematch "$DB"
      fi
      "$PG_BIN/psql" -h 127.0.0.1 -p "$PG_PORT" -U homematch -d "$DB" \
        -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS vector;'
    done
    echo "Local DB ready on 127.0.0.1:$PG_PORT: homematch_dev, homematch_test."
    ;;
  stop)
    "$PG_BIN/pg_ctl" -D "$PG_DATA" stop -m fast
    ;;
  status)
    "$PG_BIN/pg_ctl" -D "$PG_DATA" status
    ;;
  *) echo "Usage: bash infra/local-pg.sh {start|status|stop}" >&2; exit 2 ;;
esac
