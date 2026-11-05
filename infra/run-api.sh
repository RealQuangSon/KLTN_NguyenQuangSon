#!/usr/bin/env bash
# Khởi động API local với .env nạp đầy đủ (LLM openai + Neon PostgreSQL).
# Dùng: bash infra/run-api.sh  — .env không tự nạp, script này nạp hộ.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  echo "Thiếu .env ở gốc repo; sao chép .env.example và điền key trước." >&2
  exit 1
fi
set -a
source .env
set +a
exec .venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --log-config backend/logging.json
