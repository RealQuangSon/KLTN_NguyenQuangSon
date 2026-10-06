# Coding plan — Dữ liệu và đánh giá (DA)

Đọc [README.md](README.md) trước. DA chỉ sửa trong `data/` và `eval/`.

**Tài liệu và code mẫu cần đọc:**
- `data/README.md`, `data/PLAN.md`: dataset v2 gồm 220 căn và 45 hồ sơ gold (dev 15, test 30), 22 ca oracle chi phí và vay.
- `data/generate.py`: sinh tất định, giữ nguyên 80 phòng v1. Hằng `V2_CASES`, `LOAN`, hàm `landlord_for`.
- `data/manifests/development_manifest.json`: hash từng file. `python -m eval validate` kiểm hash.
- `eval/pipeline.py` (`oracle_report`, `extraction_report`), `eval/suites.py`, `eval/__main__.py` (danh sách lệnh), `eval/tests/`.
- `eval/PLAN.md`, `eval/README.md`, `eval/REPRODUCE.md`: protocol đánh giá.

**Luật riêng của mảng:**
- **Không sửa tay** file trong `data/catalog`, `data/profiles`, `data/oracles`, `data/manifests`. Mọi thay đổi đi qua `data/generate.py`, rồi chạy `python -m data.generate`. Lệnh này phải giữ 80 phòng v1 giống hệt; kiểm bằng `eval validate` và test hiện có.
- **Split `test` không được dùng để tinh chỉnh luật.** Chỉ thêm ca mới vào `dev`, hoặc vào split mới có ghi rõ mục đích.
- **Giá trị oracle phải tính độc lập** với code trong `backend/`: tính tay hoặc bằng công thức viết lại trong test. Không gọi `costs.py` hay `pms.py` để sinh đáp án.
- Không dùng `crawl_chotot.py`. Không đưa dữ liệu thật của người nào vào repo.

| ID | Task | Ưu tiên | Phụ thuộc |
|---|---|---|---|
| DA-01 | Bộ gold cho ý định chat và suite `eval intents` | P1 | — |
| DA-02 | Oracle parse câu hỏi vay (`loan_parse_cases.json`) | P1 | — (AG-02 dùng) |
| DA-03 | Oracle hóa đơn PMS tính tay | P1 | — |
| DA-04 | Kiểm công bằng khi có ưu đãi | P2 | BE-07 |
| DA-05 | Chuẩn bị đánh giá nghiên cứu GĐ5 (người dùng thu thập) | P2 | — |

---

## DA-01 — Bộ gold cho ý định chat

**Vấn đề:**
- Gold hiện có gần như chỉ có intent `find_room` và `calculate_cost` (xem các `"intent":` trong `data/generate.py` ~dòng 296–357).
- Các nhánh `handbook`, `human_support` và `simulate_finance` (sắp có, AG-02) chưa có ca đánh giá.

**Các bước:**
1. Trong `data/generate.py`, thêm hằng `INTENT_CASES`. Mỗi ca có dạng `{"case_id": "I001", "split": "dev"|"test", "text": "...", "intent": "..."}`. Tối thiểu:

   | Intent | Số ca |
   |---|---|
   | `handbook` | 8 |
   | `human_support` | 6 |
   | `calculate_cost` | 6 |
   | `simulate_finance` | 8 |
   | `find_room` | 6 |
   | `unknown` | 4 |

   Chia khoảng 40% `dev`, 60% `test`.
   - Câu đa dạng: có dấu và không dấu, viết tắt ("ko", "dc"), lẫn hai ý.
   - Có ca khó dễ nhầm: "tính tiền vay" là `simulate_finance`, khác "tính tiền vào ở" là `calculate_cost`; "quy định gửi xe" là `handbook`.
2. Ghi ra `data/profiles/intent_cases.json` và thêm file này vào manifest (cách generator ghi hash các file khác).
3. Trong `eval/`, thêm suite `intents`:
   - lệnh `python -m eval intents --split dev`;
   - với mỗi ca, chạy `fixed_intent(text) or DemoInterpreter().extract(text).intent`, đúng cách chat graph quyết định (đọc `_build_chat_graph` node `route` để làm khớp);
   - báo accuracy theo từng intent, confusion matrix, danh sách ca sai;
   - ghi ra `eval/runs/development/intents.json`.
4. Thêm bước `intents --split dev` vào `infra/check-local.sh`. Đây là ngoại lệ được phép sửa một dòng trong `infra/`; ghi trong báo cáo. **Không** đặt ngưỡng pass/fail cho accuracy, vì đây là số đo, không phải cổng.
5. Cho tới khi AG-02 xong, các ca `simulate_finance` sẽ bị đoán sai. Đó là kết quả đúng, phải ghi lại; không sửa nhãn cho khớp.

**Test** (`eval/tests/`):
- generator sinh `intent_cases.json` tất định (chạy 2 lần, hash giống nhau);
- mọi `intent` thuộc `Literal` của `schemas.MessageResult.intent` (import từ backend để kiểm);
- suite chạy được trên dev.

**Docs:** `data/README.md`, `data/PLAN.md`, `eval/README.md` (lệnh mới); AC-01 trong `docs/tieu-chi-nghiem-thu.md` thêm nguồn kiểm `eval intents`.

---

## DA-02 — Oracle parse câu hỏi vay

**Mục tiêu:** cung cấp đáp án độc lập cho `interpreter.parse_loan_terms` (AG-02).

**Các bước:**
1. Thêm hằng `LOAN_PARSE_CASES` vào `data/generate.py`, ghi ra `data/oracles/loan_parse_cases.json` và thêm vào manifest. Mỗi ca có dạng `{"case_id":"LP01","text":"...","expected":{"term_months":..., "annual_rate":..., "principal_vnd":...}}`.
2. Tối thiểu 15 ca, gồm 3 ca ở README §7.4 và:
   - "vay 1,5 triệu";
   - "lãi 0%";
   - "12 tháng" mà không có chữ "vay" (vẫn parse được kỳ hạn; việc có phải `simulate_finance` không là chuyện của DA-01);
   - số ngoài khoảng: "100 tháng", "60%" → `null`;
   - hai con số tháng: lấy số đầu tiên, và ghi quy tắc này trong mô tả file;
   - không dấu: "lai suat 9.5%";
   - đơn vị "tr" ("20tr").
3. Mô tả quy tắc (khoảng hợp lệ, cách xử lý dấu phẩy thập phân) ở đầu file JSON, trường `"rules"`. Quy tắc phải khớp README §7.4 và AG-02 bước 3; khác thì hỏi lại trước.

**Test:** `eval/tests/test_loan_parse_oracle.py` kiểm schema của file: mọi ca có đủ 3 khóa, giá trị đúng kiểu hoặc `null`. Test của AG-02 sẽ chạy hàm thật trên file này.

---

## DA-03 — Oracle hóa đơn PMS tính tay

**Mục tiêu:** NFR-04 (đúng tiền) hiện mới có 1 ví dụ hóa đơn trong `test_pms.py`. Cần một bộ oracle độc lập như oracle chi phí.

**Các bước:**
1. Đọc cách `pms.py` lập hóa đơn để biết **đầu vào** (bảng phí chụp lại trong hợp đồng, chỉ số đầu/cuối kỳ, số người, số xe). Viết **đáp án tính tay**, không chạy `pms.py` để lấy số.
2. Thêm `INVOICE_CASES` vào generator, ghi ra `data/oracles/invoice_cases.json`. Tối thiểu 10 ca:
   - ví dụ có sẵn: 3.360.000 VND;
   - điện theo kWh có số lẻ cần làm tròn;
   - nước theo m³;
   - nước theo người;
   - phí đã gồm trong tiền thuê (không cộng);
   - chỉ số cuối < đầu (lỗi `reading_decreased`);
   - thiếu đơn giá (lỗi `invoice_incomplete`);
   - 0 kWh;
   - nhiều xe;
   - tiền thuê lớn (căn hộ 2 phòng ngủ).

   Mỗi ca có `expected_total_vnd` **hoặc** `expected_error`, và `lines` từng dòng.
3. Thêm suite `python -m eval invoices` vào `eval/`:
   - với mỗi ca, dựng hợp đồng và chỉ số qua API **trong TestClient** hoặc qua `HomeMatchService` trên DB tạm;
   - lập hóa đơn rồi so từng dòng và tổng;
   - ghi ra `eval/runs/development/invoices.json`.

   Suite này đọc `backend` nhưng không sửa.
4. Thêm `invoices` vào `infra/check-local.sh` (ghi trong báo cáo). Lệch bất kỳ ca nào → exit khác 0, giống `oracle`.

**Nếu oracle lệch với code:** **không sửa oracle cho khớp.** Ghi ca lệch vào báo cáo, kèm phép tính tay, để BE xem lại `pms.py`.

**Docs:** NFR-04 trong `yeu-cau-san-pham.md`; AC-24; `data/README.md`.

---

## DA-04 — Kiểm công bằng khi có ưu đãi

**Làm sau BE-07.**

1. Trong `eval invariants` (`eval/suites.py`), các phản thực tế hiện thêm "hoa hồng" và "Tồn kho 120 ngày". Thêm phản thực tế thứ ba: đặt ưu đãi cho căn (ghi bảng `hm_promotions` trên DB tạm, qua API của BE-07) và kiểm thứ hạng không đổi.
2. Báo cáo thêm `promotion_rank_changes: 0`. Khác 0 thì suite fail.

---

## DA-05 — Chuẩn bị đánh giá nghiên cứu (GĐ5)

**Agent không được tự tạo nhãn hay câu trả lời khảo sát.** Chỉ chuẩn bị công cụ.

1. **Freeze:** viết `eval/FREEZE.md` hướng dẫn chốt dataset:
   - `frozen=true` trong manifest qua generator hoặc lệnh;
   - ghi model, ngày, commit;
   - test split chỉ chạy một lần.

   Kiểm xem `eval` đã có lệnh freeze chưa (`eval/__main__.py`), nếu có thì dùng lại.
2. **Form gán nhãn mức liên quan:** lệnh `python -m eval label-sheet --split test --method B1|P` xuất CSV `eval/labels/sheet-<method>.csv`. Mỗi dòng là một cặp hồ sơ–căn trong top 5:
   - cột: `profile_id`, `room_id`, mô tả nhu cầu (đã che tiền), thông tin căn, `label` (bỏ trống, thang 0–3), `annotator`, `note`;
   - **trộn thứ tự và ẩn tên phương pháp** để người chấm không biết căn đến từ B1 hay P; bảng ánh xạ ghi ra file riêng `*.key.csv`;
   - thêm `eval/labels/` vào `.gitignore` nếu chưa có, vì nhãn thật do người dùng quyết định có đưa vào repo hay không.
3. **Tổng hợp nhãn:** lệnh `python -m eval label-report` đọc các file đã điền, tính:
   - nDCG@5 và Precision@5 theo phương pháp;
   - độ đồng thuận giữa người chấm (Cohen's kappa) nếu có từ 2 người chấm.

   Test bằng file nhãn **giả lập trong `tmp_path`**; không đưa nhãn giả vào `eval/labels/`.
4. **Khảo sát:** `eval/survey/khao-sat.md` gồm thang SUS rút gọn và các câu về độ tin cậy lời giải thích, mức hài lòng với gợi ý, cảm nhận về quyền riêng tư tài chính. Thêm `python -m eval survey-report` đọc CSV kết quả và tính trung bình, độ lệch chuẩn. Test bằng dữ liệu giả trong `tmp_path`.
5. Cập nhật `eval/PLAN.md` và `docs/ke-hoach-trien-khai.md` (GĐ5): ghi công cụ đã sẵn sàng; dữ liệu do người dùng thu thập.
