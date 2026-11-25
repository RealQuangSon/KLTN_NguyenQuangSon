# Đánh giá HomeMatch

Công cụ đánh giá trợ lý: độ chính xác trích xuất, chất lượng xếp hạng, engine chi phí, điều kiện cứng, căn cứ của lời giải thích.

Mặc định offline. Các output ở `eval/runs/development` là bằng chứng kiểm tra thành phần và gói gán nhãn thử; không phải kết quả GPT/P thật hoặc đo hài lòng.

## Chạy kiểm tra phát triển

```bash
.venv/bin/python -m eval validate
.venv/bin/python -m eval oracle
.venv/bin/python -m eval extraction --split dev
.venv/bin/python -m eval ranking --split dev
.venv/bin/python -m eval metrics
.venv/bin/python -m eval invariants --split dev
.venv/bin/python -m eval intents --split dev
.venv/bin/python -m eval invoices
.venv/bin/python -m eval grounding
.venv/bin/python -m eval measure
.venv/bin/python -m eval report
```

Oracle so sánh exact VND/null với 22 ca được tính độc lập: 15 ca chi phí và 7 ca khả năng chi trả/vay (khoản thiếu, trả góp, tổng lãi, tỷ lệ, băng). Extraction báo field F1 và intent riêng; tiền local hint/form không vào model F1. Ranking chạy B1 và yêu cầu P trên cùng toàn bộ tập eligible; thiếu vector thật thì P ghi `unavailable`. Không tự thay B1 bằng nhãn P. Metric khi chưa có nhãn trả `pending_human_judgments`, không cho điểm tự tạo.

`invariants` kiểm lại điều kiện cứng trên mọi phòng eligible (published/available/capacity/budget/must-amenity/khoảng cách), dedup canonical và phản thực tế: đổi metadata thương mại (hoa hồng ở title/source) không được đổi thứ tự/điểm; ưu đãi chủ nhà ghi qua API BE-07 (`HomeMatchService.set_promotion` lên bảng `hm_promotions` trên DB tạm) không được đổi thứ hạng — `promotion_rank_changes` phải bằng 0, khác 0 thì suite fail; đối chứng `available=false` phải loại phòng khỏi eligible. `intents` đo bộ định tuyến ý định trên 38 ca gold (`data/profiles/intent_cases.json`) đúng cách node `route` quyết định; **chỉ đo, không đặt ngưỡng đậu/rớt**, ca sai được liệt kê (kèm confusion matrix); `simulate_finance` dự kiến sai cho tới khi AG-02 có mặt. `invoices` so 12 ca hóa đơn tính tay (`data/oracles/invoice_cases.json`) từng dòng và tổng trên DB tạm; lệch ca nào exit khác 0, oracle không sửa theo code. `grounding` bóc từng claim trong reasons/tradeoffs đối chiếu bằng chứng phòng ở đúng revision và cost tính lại; claim không parse được tính `unparsed`. `measure` gộp p50/p95 machine latency và logical model calls từ các artifact chạy thật (review waiting không tính vào). `report` dựng `report.md` + `evidence_index.csv`; thiếu artifact nào sẽ báo rõ lệnh cần chạy trước. Đây là suite chức năng máy kiểm được, không thay nhãn người chấm.

## Nhãn độc lập và freeze

CLI hiện còn guard lịch sử G4: `python -m eval freeze --ack-g4`; runner test từ chối dataset chưa freeze. Phạm vi mới dùng P5 nghiên cứu và P4 release riêng; phải version protocol/inputs và chốt readiness nghiên cứu trước thao tác freeze, không tự xem cờ ack là đã hoàn thiện sản phẩm. Quy trình từng bước (ghi model, ngày, commit; split test chỉ chạy một lần) ở [FREEZE.md](FREEZE.md). Thứ tự: khóa dataset/code/config → chạy B1/P → union top5 canonical → người chấm gói blind → khóa hash nhãn → metrics. Chưa có freeze research được xác nhận; không chạy freeze chỉ để bỏ qua guard.

Công cụ gán nhãn và tổng hợp (DA-05, 08/10/2026) — chỉ là công cụ, **agent không tự tạo nhãn**:

```bash
.venv/bin/python -m eval label-sheet --split test --method B1   # và --method P
.venv/bin/python -m eval label-report                            # sau khi người chấm điền
.venv/bin/python -m eval survey-report --csv <file>.csv          # theo eval/survey/khao-sat.md
```

`label-sheet` xuất CSV `eval/labels/sheet-<alias>.csv` (thư mục git-ignore): thứ tự xáo trộn, **ẩn tên phương pháp** (chỉ nằm trong `sheet-<alias>.key.csv` để người vận hành giữ), cột `label` để trống cho người chấm điền 0–3 kèm `annotator`/`note`; mô tả nhu cầu đã che các trường tiền. `label-report` tính nDCG@5, P@5 theo phương pháp từ các sheet đã điền và Cohen's kappa khi có từ 2 người chấm cùng cặp. Phiếu khảo sát (SUS rút gọn + tin cậy lời giải thích + hài lòng gợi ý + riêng tư tài chính) ở `eval/survey/khao-sat.md`.

Mở `eval/runs/development/annotation.html` để thử thao tác chấm. File chỉ chạy local, không gửi dữ liệu ra ngoài. Judge dùng ID giả danh; ghi relevance 0–3, lý do và bằng chứng cho từng cặp hồ sơ/phòng. Export JSON rồi chạy:

```bash
.venv/bin/python -m eval metrics --judgments /path/judgments.json --human-declared --allow-development
```

`--allow-development` tạo kết quả khám phá, không phải test nghiên cứu. Không dùng nhãn máy/LLM hoặc điểm rank làm gold. Mẫu CSV nằm cạnh HTML; nhãn thiếu không biến thành 0. Pool-based nDCG@5 dùng union đã chấm; Precision@5 chia 5, precision trên số phòng trả về báo riêng. Không đo full Recall. So sánh paired dùng cùng profile IDs fully judged/metric-defined cho hai phương pháp và công bố các ca bị loại; bootstrap theo hồ sơ gốc.

## Mode live tùy chọn

Extraction dùng `--live --allow-live --api-budget-vnd <số dương>`. P dùng `ranking --live-semantic --allow-live --api-budget-vnd <số dương>`, PostgreSQL catalog phải khớp JSON và vector đã index bằng CLI backend. Key chỉ ở server. Chưa chạy live trong lần bàn giao này.

Budget ở CLI là khai báo của operator, **chưa là giới hạn chi tiêu được cưỡng chế**. Cần kiểm soát ngân sách tại tài khoản provider trước khi chạy; báo cost `unavailable` khi thiếu giá/usage được kiểm chứng. Không lấy fake SDK hoặc latency rule làm chất lượng hay chi phí GPT.

Xem [REPRODUCE.md](REPRODUCE.md) cho thứ tự tái lập development/test và điều kiện live.
