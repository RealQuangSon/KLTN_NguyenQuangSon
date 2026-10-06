# Kế hoạch đánh giá

**Cập nhật:** 05/10/2026. Trả lời RQ1–RQ5 trong [đề cương](../docs/ke-hoach-kltn-homematch.md#6-câu-hỏi-nghiên-cứu) và chứng minh NFR trong [danh mục yêu cầu](../docs/yeu-cau-san-pham.md#2-yêu-cầu-phi-chức-năng). Lệnh chạy ở [README.md](README.md); thứ tự tái lập ở [REPRODUCE.md](REPRODUCE.md).

> **Việc tiếp theo (06/10/2026):** làm theo [coding plan](../docs/coding-plan/data.md); đọc [phần chung](../docs/coding-plan/README.md) trước.

## 1. Hiện có

CLI `python -m eval` với các lệnh:

- `validate`, `oracle`, `extraction`, `ranking`, `metrics`;
- `invariants`, `grounding`, `measure`, `report`, `freeze`.

Gói gán nhãn mù ở `eval/runs/development/annotation.html`. Ngày 05/10, các lệnh chạy offline đều pass (xem [trạng thái](../docs/trang-thai-trien-khai.md)).

**Chưa có:**

- nhãn người chấm;
- kết quả GPT-4o hoặc P live;
- khảo sát người dùng.

## 2. Ma trận đánh giá

| RQ / NFR | Lệnh hoặc phương pháp | Chỉ số | Cần thêm |
|---|---|---|---|
| RQ1 trích xuất | `eval extraction` (luật offline và `--live` GPT-4o) | Độ chính xác ý định; P/R/F1 từng trường; tỷ lệ fallback | Gold v2 đã có (45 hồ sơ). Gold và luật offline cùng tác giả, nên cần thêm câu nói từ người thật, hoặc ít nhất một người khác soạn câu. |
| RQ2 xếp hạng | `eval ranking` (B1, P) + nhãn mù 0–3 | nDCG@5, P@5 theo cặp; bootstrap theo hồ sơ gốc; độ phủ nhãn | Vector thật, 2 người chấm, hệ số đồng thuận |
| RQ3 đúng và công bằng | `oracle`, `invariants`, `grounding` | Số vi phạm điều kiện cứng = 0; oracle khớp 100%; phản thực tế hoa hồng/thời gian tồn: 0 thay đổi; tỷ lệ khẳng định có bằng chứng (gồm khoản vay, băng) | Người khác kiểm tra chéo 22 ca oracle |
| RQ4 hài lòng | Khảo sát 5–10 người, kịch bản demo đầu-cuối, có đồng ý | Tỷ lệ hoàn thành; thời gian; 3–5 câu kiểm tra hiểu chi phí (tổng tháng/tiền vào ở/trả góp/"chưa rõ"); thang hài lòng 1–5 hoặc SUS | Phiếu khảo sát, chạy thử với 1 người trước |
| RQ5 chi phí, độ trễ | `eval measure` | p50/p95 thời gian máy; số lượt gọi, token, VND mỗi phiên; tỷ lệ trúng cache embedding | Bảng giá provider có ngày |
| Memory (FR-22) | So sánh có và không có memory trên cùng kịch bản phiên thứ hai | Số câu hỏi và thời gian tới khi xác nhận | Kịch bản 2 phiên |

## 3. Quy trình nghiên cứu

1. Tinh chỉnh (prompt, α, trọng số) **chỉ trên tập dev**.
2. Freeze: dữ liệu, cấu hình, prompt, code hash (`eval freeze`).
3. Chạy B1 và P trên tập test. Gộp top 5 của cả hai thành pool, xáo trộn, ẩn phương pháp.
4. Người chấm gán nhãn 0–3 kèm lý do. Khóa hash nhãn.
5. Tính metrics theo cặp trên các hồ sơ đủ nhãn. Báo cáo cả các ca bị loại.
6. Kết quả âm (P không hơn B1) vẫn là kết quả hợp lệ.

## 4. Quy tắc báo cáo

- Thiếu nhãn → `pending_human_judgments`, không tự chấm bằng LLM hay bằng điểm xếp hạng.
- Fallback B1 không được tính là P. Dùng provider giả không được báo là chất lượng GPT-4o.
- Mọi số liệu kèm ngày, cấu hình, hash dữ liệu và giới hạn (dữ liệu tổng hợp, mẫu nhỏ).
