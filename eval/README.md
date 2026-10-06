# Đánh giá HomeMatch

**Cập nhật 05/10/2026:** [PLAN](PLAN.md) ánh xạ các lệnh dưới đây vào RQ1–RQ5 của đề tài và liệt kê phần còn thiếu (gold v2, oracle vay, nhãn người chấm, khảo sát người dùng).

Mặc định offline. Các output ở `eval/runs/development` là bằng chứng kiểm tra thành phần và gói gán nhãn thử; không phải kết quả GPT/P thật hoặc đo hài lòng.

## Chạy kiểm tra phát triển

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

Oracle so sánh exact VND/null với 22 ca được tính độc lập: 15 ca chi phí và 7 ca khả năng chi trả/vay (khoản thiếu, trả góp, tổng lãi, tỷ lệ, băng). Extraction báo field F1 và intent riêng; tiền local hint/form không vào model F1. Ranking chạy B1 và yêu cầu P trên cùng toàn bộ tập eligible; thiếu vector thật thì P ghi `unavailable`. Không tự thay B1 bằng nhãn P. Metric khi chưa có nhãn trả `pending_human_judgments`, không cho điểm tự tạo.

`invariants` kiểm lại điều kiện cứng trên mọi phòng eligible (published/available/capacity/budget/must-amenity/khoảng cách), dedup canonical và phản thực tế: đổi metadata thương mại (hoa hồng ở title/source) không được đổi thứ tự/điểm; đối chứng `available=false` phải loại phòng khỏi eligible. `grounding` bóc từng claim trong reasons/tradeoffs đối chiếu bằng chứng phòng ở đúng revision và cost tính lại; claim không parse được tính `unparsed`. `measure` gộp p50/p95 machine latency và logical model calls từ các artifact chạy thật (review waiting không tính vào). `report` dựng `report.md` + `evidence_index.csv`; thiếu artifact nào sẽ báo rõ lệnh cần chạy trước. Đây là suite chức năng máy kiểm được, không thay nhãn người chấm.

## Nhãn độc lập và freeze

CLI hiện còn guard lịch sử G4: `python -m eval freeze --ack-g4`; runner test từ chối dataset chưa freeze. Phạm vi mới dùng P5 nghiên cứu và P4 release riêng; phải version protocol/inputs và chốt readiness nghiên cứu trước thao tác freeze, không tự xem cờ ack là đã hoàn thiện sản phẩm. Thứ tự: khóa dataset/code/config → chạy B1/P → union top5 canonical → người chấm gói blind → khóa hash nhãn → metrics. Chưa có freeze research được xác nhận; không chạy freeze chỉ để bỏ qua guard.

Mở `eval/runs/development/annotation.html` để thử thao tác chấm. File chỉ chạy local, không gửi dữ liệu ra ngoài. Judge dùng ID giả danh; ghi relevance 0–3, lý do và bằng chứng cho từng cặp hồ sơ/phòng. Export JSON rồi chạy:

```bash
.venv/bin/python -m eval metrics --judgments /path/judgments.json --human-declared --allow-development
```

`--allow-development` tạo kết quả khám phá, không phải test nghiên cứu. Không dùng nhãn máy/LLM hoặc điểm rank làm gold. Mẫu CSV nằm cạnh HTML; nhãn thiếu không biến thành 0. Pool-based nDCG@5 dùng union đã chấm; Precision@5 chia 5, precision trên số phòng trả về báo riêng. Không đo full Recall. So sánh paired dùng cùng profile IDs fully judged/metric-defined cho hai phương pháp và công bố các ca bị loại; bootstrap theo hồ sơ gốc.

## Mode live tùy chọn

Extraction dùng `--live --allow-live --api-budget-vnd <số dương>`. P dùng `ranking --live-semantic --allow-live --api-budget-vnd <số dương>`, PostgreSQL catalog phải khớp JSON và vector đã index bằng CLI backend. Key chỉ ở server. Chưa chạy live trong lần bàn giao này.

Budget ở CLI là khai báo của operator, **chưa là giới hạn chi tiêu được cưỡng chế**. Cần kiểm soát ngân sách tại tài khoản provider trước khi chạy; báo cost `unavailable` khi thiếu giá/usage được kiểm chứng. Không lấy fake SDK hoặc latency rule làm chất lượng hay chi phí GPT.

Xem [REPRODUCE.md](REPRODUCE.md) cho thứ tự tái lập development/test và điều kiện live.
