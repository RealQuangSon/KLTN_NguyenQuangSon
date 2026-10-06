# Tái lập đánh giá HomeMatch

Mọi artifact đều truy được về hash trong manifest; chạy lại cùng dữ liệu/code cho cùng kết quả
deterministic (rule/B1, không provider). LLM thật có thể khác qua lần chạy — công bố số lần lặp
và settings, không hứa bit-for-bit.

## Môi trường

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pytest            # gồm eval/tests
```

Mặc định offline: rule extraction, B1 ranking, JSON catalog, 0 model call.
Dataset gốc tại `data/` đã có manifest; tái sinh deterministic bằng:

```bash
.venv/bin/python -m data.generate --output .local/regenerated-data
.venv/bin/python -m eval validate --data-dir .local/regenerated-data
```

## Chu trình development (exploratory, hiện tại)

```bash
.venv/bin/python -m eval validate
.venv/bin/python -m eval oracle
.venv/bin/python -m eval extraction --split dev
.venv/bin/python -m eval ranking --split dev
.venv/bin/python -m eval metrics
.venv/bin/python -m eval invariants --split dev
.venv/bin/python -m eval grounding
.venv/bin/python -m eval measure
.venv/bin/python -m eval report
```

Output vào `eval/runs/development/`: `rankings.jsonl`, `run_manifest.json`, `blind_packets.json`,
`annotation.html`, `extraction.json`, `oracle.json`, `invariants.json`, `grounding.json`,
`measurements.json`, `evaluation_summary.json`, `report.md`, `evidence_index.csv`.

Kiểm tra lại: hash `rankings.jsonl` khớp `run_manifest.json`; `report.md` liệt kê mọi bảng kèm
giới hạn. Đổi bất kỳ file dữ liệu nào → `validate`/runner báo hash mismatch.

## Chu trình nghiên cứu trên test (chưa mở)

Thứ tự bắt buộc, không hoán đổi:

1. Xác nhận G4 (MVP/freeze readiness) rồi `python -m eval freeze --ack-g4` — khóa
   dataset/code/config/protocol vào `data/manifests/input_manifest.json`.
2. `python -m eval ranking --split test` — runner từ chối test khi chưa freeze.
3. Chấm blind qua `eval/runs/test/annotation.html` (hoặc CSV template); export `judgments.json`.
4. `python -m eval metrics --run-dir eval/runs/test --judgments <file> --human-declared` —
   khóa label manifest trước khi tính paired metrics.
5. `python -m eval invariants --split test`, `grounding`, `measure`, `report` trên run test.

Không tune theo test; sau khi thấy kết quả test, mọi điều chỉnh là run/protocol mới.

## Live GPT/P (tùy chọn, cần quyền + ngân sách)

- Extraction: `python -m eval extraction --split test --live --allow-live --api-budget-vnd <dương>`.
- P: PostgreSQL catalog khớp hash + vector đã index (`python -m backend.manage index --allow-live`),
  rồi `python -m eval ranking --split test --live-semantic --allow-live --api-budget-vnd <dương>`.
- Budget CLI là khai báo của operator, không phải giới hạn chi tiêu được cưỡng chế.
- Không trộn kết quả fixtures/demo với phép đo model thật trong cùng báo cáo.
