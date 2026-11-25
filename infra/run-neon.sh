#!/usr/bin/env bash
# Run the API on localhost against the Neon (online PostgreSQL) app database.
# Settings come from .env (LLM, auth, CORS...); .local/neon.env then supplies
# HOMEMATCH_DATABASE_URL (app DB) and HOMEMATCH_CRAWL_DATABASE_URL (Chợ Tốt snapshots).
# Neither file is committed. Usage: bash infra/run-neon.sh [port]   (default 8000)
set -euo pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
SNAPSHOT=${HOMEMATCH_CHOTOT_SNAPSHOT:-chotot-2026-11-07-5k-r2}
PORT=${1:-8000}

[ -f .env ] || { echo "Thiếu .env (copy từ .env.example)." >&2; exit 1; }
[ -f .local/neon.env ] || { echo "Thiếu .local/neon.env; lấy URL bằng: neon connection-string --project-id <project-id> --database-name homematch" >&2; exit 1; }
set -a
# shellcheck disable=SC1091
source .env
# shellcheck disable=SC1091
source .local/neon.env
set +a
[ -n "${HOMEMATCH_DATABASE_URL:-}" ] || { echo "HOMEMATCH_DATABASE_URL trống trong .local/neon.env." >&2; exit 1; }

# The catalog only seeds an empty database, but keep the snapshot on disk so a fresh
# Neon database can be rebuilt; restore it from Neon (hash-checked) when missing.
CATALOG=".local/chotot/$SNAPSHOT/catalog.json"
if [ ! -f "$CATALOG" ]; then
  .venv/bin/python -m data.crawl_chotot --pull --snapshot-id "$SNAPSHOT"
fi
export HOMEMATCH_CATALOG_PATH="$CATALOG"

if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Cổng $PORT đang có server khác; tắt nó trước hoặc chạy: bash infra/run-neon.sh <cổng khác>." >&2
  exit 1
fi
.venv/bin/python -m backend.manage setup
exec .venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port "$PORT" --workers 1 \
  --no-access-log --log-config backend/logging.json
