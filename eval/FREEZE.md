# Quy trình chốt dữ liệu nghiên cứu (freeze) — DA-05

**Mục đích:** khóa dữ liệu, code và cấu hình trước khi chạy tập `test` cho nghiên cứu GĐ5.
Lệnh freeze **đã có sẵn** trong CLI và được dùng lại, không viết lệnh mới.

## Nguyên tắc

- Tinh chỉnh (prompt, α, trọng số, luật) **chỉ làm trên split `dev`**. Chạm vào `test` để tinh chỉnh là mất giá trị nghiên cứu.
- Split `test` chỉ chạy **một lần** sau freeze; chạy lại phải tạo dataset/protocol version mới.
- Không tự coi cờ ack là "sản phẩm đã hoàn thành": freeze chỉ khóa đầu vào nghiên cứu (P5), không phải bằng chứng G4 release.

## Các bước

1. **Chốt cấu hình nghiên cứu** trong `eval/config/protocol.json` trước khi freeze:
   - `extraction_model` (model GPT dùng cho extraction live);
   - `methods.P` (alpha, `embedding_model`, `dimensions`) khớp với vector đã index;
   - thêm/ghi ngày và commit Git của repo vào trường `freeze_context` (ví dụ
     `{"date": "2026-10-08", "git_commit": "<hash>", "operator": "<tên>"}`) để
     phản ánh model, ngày, commit theo yêu cầu. `eval freeze` lưu `protocol_hash`
     nên mọi sửa sau freeze sẽ bị phát hiện.
2. **Chạy freeze** (ghi `data/manifests/input_manifest.json` với `frozen=true`,
   kèm hash toàn bộ artifact, code hash và protocol):

   ```bash
   .venv/bin/python -m eval freeze --ack-g4
   ```

   Freeze từ chối chạy lần thứ hai trên cùng dataset ("Input already frozen").
3. **Chạy một lần duy nhất trên tập test:**

   ```bash
   .venv/bin/python -m eval ranking --split test
   ```

4. **Gán nhãn mù:** tạo sheet với `python -m eval label-sheet --split test --method B1`
   và `--method P` (thứ tự xáo trộn, tên phương pháp chỉ nằm trong `*.key.csv`);
   người chấm điền `label` 0–3, `annotator`, `note` theo thang trong protocol.
   Thư mục `eval/labels/` đã git-ignore; việc đưa nhãn vào repo là quyết định của người dùng.
5. **Tổng hợp:** `python -m eval label-report` (nDCG@5, P@5 theo phương pháp,
   Cohen's kappa khi có từ 2 người chấm), rồi `python -m eval metrics --judgments … --human-declared`.

## Những gì freeze lưu lại

- `frozen=true`, `stage="frozen_test_input"`, hash từng file dữ liệu (`artifacts`);
- `code_hashes` của `backend/app`, `eval`, requirements — runner test từ chối chạy nếu code đổi;
- `protocol` + `protocol_hash`; `labels_status` khởi điểm `pending_human_judgments`.

## Sau freeze

- Muốn đổi dữ liệu/code/protocol → tạo version mới (thư mục output hoặc protocol mới), không ghi đè.
- Nhãn khóa bằng `evaluation_manifest.json` khi đủ nhãn; khác biệt sẽ bị từ chối.
