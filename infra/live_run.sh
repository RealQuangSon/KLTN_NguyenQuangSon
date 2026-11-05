#!/usr/bin/env bash
set -euo pipefail

# AG-04 live run of GPT-4o extraction and pgvector hybrid ranking.
# Agents and CI must NEVER run this script: every step after the checks spends
# real API budget. The user runs it themselves with their own key.
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

RUN_DATE=$(date +%Y-%m-%d)
RUN_DIR="eval/runs/live-$RUN_DATE"

fail() {
  echo "live_run: $1" >&2
  exit 1
}

# --- Checks first: stop before anything that could cost money. ---
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  fail "OPENAI_API_KEY chưa đặt (giá trị không bao giờ được in). Xuất key rồi chạy lại, ví dụ: export OPENAI_API_KEY=...; bash infra/live_run.sh"
fi
if [[ -z "${HOMEMATCH_LIVE_BUDGET_VND:-}" ]]; then
  fail "HOMEMATCH_LIVE_BUDGET_VND bắt buộc: số VND tối đa bạn chấp nhận chi cho lần chạy này. Ví dụ: export HOMEMATCH_LIVE_BUDGET_VND=200000"
fi
if ! [[ "$HOMEMATCH_LIVE_BUDGET_VND" =~ ^[0-9]+$ ]] || (( HOMEMATCH_LIVE_BUDGET_VND <= 0 )); then
  fail "HOMEMATCH_LIVE_BUDGET_VND phải là số nguyên > 0."
fi

DEV_PROFILES=$(grep -c . data/profiles/dev/profiles.jsonl)
DEV_UTTERANCES=$(.venv/bin/python - << 'PY'
import json
rows = [json.loads(line) for line in open("data/profiles/dev/profiles.jsonl") if line.strip()]
print(sum(len(row.get("utterances", [])) for row in rows))
PY
)
ROOMS=$(.venv/bin/python -c "import json; print(len(json.load(open('data/catalog/rooms.json'))['rooms']))")

echo "=== Kế hoạch chạy live (AG-04) ==="
echo "Ngày chạy: $RUN_DATE; mọi kết quả ghi vào $RUN_DIR/, không đè eval/runs/development/."
echo "Hồ sơ gold dev: $DEV_PROFILES; số câu gold dev: $DEV_UTTERANCES."
echo "Căn cần embedding: $ROOMS (chỉ embed lại căn có hash văn bản semantic đổi)."
echo "Lượt gọi ước tính: ~$DEV_UTTERANCES lượt GPT-4o (extraction, 1 lượt/câu) + tối đa $ROOMS lượt embedding;"
echo "  ranking và measure chạy trên vector đã dựng, không gọi thêm model."
echo "Ngân sách kê khai: $HOMEMATCH_LIVE_BUDGET_VND VND (chỉ kê khai, KHÔNG phải trần cứng — xem infra/live-run.md)."
read -r -p "Gõ 'yes' để chạy thật với API key của bạn: " CONFIRM
[[ "$CONFIRM" == "yes" ]] || fail "Không xác nhận — dừng mà không tốn chi phí."

if [[ -d "$RUN_DIR" && -n "$(ls -A "$RUN_DIR" 2>/dev/null)" ]]; then
  fail "Thư mục $RUN_DIR đã có kết quả; di chuyển hoặc đổi tên nó trước khi chạy lại để không ghi đè."
fi

# --- Isolated local PostgreSQL with pgvector (never a system service). ---
bash infra/local-pg.sh start
export HOMEMATCH_DATABASE_URL="postgresql://homematch@127.0.0.1:55432/homematch_dev"
export HOMEMATCH_EMBEDDING_MODE=openai
export HOMEMATCH_MATCHING_METHOD=P

# 1-2. Schema and stored catalog on PostgreSQL.
.venv/bin/python -m backend.manage setup
# 3. Embed rooms; the text-hash check keeps repeat runs cheap.
.venv/bin/python -m backend.manage index --allow-live
mkdir -p "$RUN_DIR"
# 4. Live GPT-4o extraction over the frozen dev gold (Responses API, store=False).
.venv/bin/python -m eval extraction --split dev --live --allow-live \
  --api-budget-vnd "$HOMEMATCH_LIVE_BUDGET_VND" --output "$RUN_DIR/extraction.json"
# 5. Hybrid P on real pgvector vectors; B1 is computed alongside as the baseline.
.venv/bin/python -m eval ranking --split dev --live-semantic --allow-live \
  --api-budget-vnd "$HOMEMATCH_LIVE_BUDGET_VND" --run-dir "$RUN_DIR"
# Deterministic offline oracle artifact `measure` needs in the same run dir.
.venv/bin/python -m eval oracle --output "$RUN_DIR/oracle.json"
# 6. Latency and model-call measurements over this run dir.
.venv/bin/python -m eval measure --run-dir "$RUN_DIR" --output "$RUN_DIR/measurements.json"

echo "Hoàn tất. Kết quả nằm trong $RUN_DIR/; cách đọc xem infra/live-run.md."
