# Kế hoạch triển khai HomeMatch AI Agent

**Cập nhật:** 09/10/2026 (bảng "Còn lại sau E6" khớp với code 08/10). Thứ tự công việc tới mục tiêu trong [đề cương](ke-hoach-kltn-homematch.md). Ngày 05/10, người dùng duyệt docs và xác nhận D-01/D-02. Cùng ngày, các giai đoạn GĐ1–GĐ3, phần code của GĐ4 và đợt mở rộng 5 phân hệ (E1–E6) đã xong.

Mỗi task chỉ được tính là xong khi có code, test, cập nhật docs liên quan và bằng chứng được ghi vào [trạng thái](trang-thai-trien-khai.md).

## GĐ1 — Căn chỉnh đề tài và sửa lỗi (xong)

| Task | Kết quả | Trạng thái |
|---|---|---|
| T1.1 | Viết lại docs theo đề tài, lưu trữ bản "toàn vòng đời thuê" | Xong, đã duyệt 05/10 |
| T1.2 | Nhận diện khu vực: từ điển `locations.py` cho TP.HCM và Hà Nội; lọc cứng so khớp alias | Xong 05/10 |
| T1.3 | Chặn mã xác minh cũ kích hoạt lại tài khoản bị vô hiệu hóa; dùng token một lần nguyên tử | Xong 05/10 |
| T1.4 | Xác nhận D-01 (thuê thay vì mua) và D-02 (vay ngắn hạn cho tiền vào ở) | Xong, người dùng xác nhận 05/10 |

## GĐ2 — Kho v2 và engine tài chính (CB, xong 05/10)

Chi tiết kết quả và kiểm thử ở [trạng thái](trang-thai-trien-khai.md#3-thay-đổi-code-theo-đợt-05102026). Khác thiết kế ban đầu: `Room.room_type` được mở rộng thêm `apartment` thay vì thêm trường `property_type`; dữ liệu căn lưu JSON nên không cần migration v4. Kho có 220 căn thay vì khoảng 200, để mỗi hồ sơ dev có đủ căn đánh giá. Form dùng danh sách khu vực tĩnh, có test giữ đồng bộ với backend, thay vì gọi `GET /locations`.

| Task | Kết quả | Yêu cầu | Phụ thuộc |
|---|---|---|---|
| T2.1 | Model `Room` thêm `property_type` (`room`/`studio`/`apartment`), `bedrooms`, `features_text`; migration schema v4; extraction nhận `apartment` | FR-24 | T1.4 |
| T2.2 | Generator v2: TP.HCM + Hà Nội, phòng/studio/căn hộ trong **cùng kho chính**; seed mới; manifest mới; hồ sơ gold dev/test cho cả hai thành phố | FR-24 | T2.1 |
| T2.3 | Engine khả năng chi trả: thu nhập, tỷ lệ, băng, `cost_split` | FR-06 | — |
| T2.4 | Engine vay annuity; điều kiện cứng `loan_principal`/`loan_burden`; oracle `LOAN-*` tính độc lập | FR-07 | T2.3 |
| T2.5 | Ẩn thu nhập khỏi DTO của chủ nhà (trước 05/10 là sale); kiểm thử NFR-01 | NFR-01 | T2.3 |
| T2.6 | Người duyệt (nay là chủ nhà) phải ghi `override_reasons`; lưu thứ tự của agent | FR-13 | — |
| T2.7 | UI: form tài chính (thu nhập, tiền mặt, vay), hiển thị băng và khoản vay, chọn khu vực theo `GET /locations` | FR-06, 07, 24 | T2.3, T2.4 |

Hết GĐ2, các AC của cổng **G1 Cơ bản** ([nghiệm thu](tieu-chi-nghiem-thu.md#cổng-hoàn-thành)) đã có test pass. Còn chạy demo đầu-cuối trên trình duyệt để chốt G1.

## GĐ3 — Multi-agent và memory (NC, xong 05/10)

Khác thiết kế: các agent là node chung một graph, tool đi qua `ToolBox` có danh sách cho phép, thay vì subgraph riêng. Recommendation graph giữ tên node để không làm hỏng checkpoint đang chờ duyệt. Cache embedding truy vấn dùng bảng ledger nên chạy được cả trên SQLite (test) lẫn PostgreSQL.

| Task | Kết quả | Yêu cầu |
|---|---|---|
| T3.1 ✓ | Tách chat graph thành supervisor và 3 subgraph (nhu cầu, tài chính, xếp hạng); danh sách tool được phép; giới hạn số bước | FR-21 |
| T3.2 ✓ | Recommendation graph thành phần của agent xếp hạng; giữ bất biến interrupt và ledger | FR-21 |
| T3.3 ✓ | `hm_preference_memory`, `GET/DELETE /me/memory`, điền sẵn `inferred` theo đồng ý | FR-22 |
| T3.4 ✓ | Cache embedding truy vấn bền (`hm_query_embeddings`); metrics `semantic_usage`. Chi phí VND còn chờ bảng giá ([API đích](api-san-pham-v1.md)). | NFR-05 |

## GĐ4 — Trải nghiệm và triển khai (NC; T4.1–T4.2 xong 05/10, T4.3 ngoài phạm vi, T4.4 cần API key)

| Task | Kết quả | Yêu cầu |
|---|---|---|
| T4.1 ✓ | So sánh trực quan: đánh dấu chênh lệch, biểu đồ chi phí tháng và tiền vào ở | FR-19 |
| T4.2 ✓ | UI mô phỏng 3 kịch bản (`SimulationPanel`) | FR-08 |
| T4.3 (ngoài phạm vi, D-09 28/10) | ~~Deploy Railway~~. Thay bằng chạy localhost: một worker uvicorn, SQLite hoặc PostgreSQL local; smoke HTTP trên server thật | NFR-09 |
| T4.4 (chờ `OPENAI_API_KEY` và ngân sách) | Trên máy local (`infra/live_run.sh`): index vector thật vào PostgreSQL + pgvector local, chạy GPT-4o có ngân sách; đo độ trễ và chi phí | NFR-05, 06 |

## Mở rộng 5 phân hệ (E1–E6, xong 05/10)

Người dùng yêu cầu ngày 05/10: chủ nhà thay sale, và nền tảng có 5 phân hệ (cổng người thuê, tự động hóa, Admin Console, cổng chủ nhà PMS & CRM, trợ lý AI cho chủ nhà). Quyết định D-05 → D-08 ở [đề cương](ke-hoach-kltn-homematch.md#7-quyết-định-điều-chỉnh-so-với-đề-bài).

| Đợt | Kết quả | Yêu cầu |
|---|---|---|
| E1 ✓ | Chủ nhà sở hữu phòng; mỗi chủ duyệt phòng của mình; CRUD tin; trống/đã cọc/đã thuê; lịch xem gửi đúng chủ, xem trực tuyến | FR-13, 15–17, 20, 30, 40 |
| E2 ✓ | Tìm theo bộ lọc, xem nhanh, bản đồ; đặt lịch từ tin; tư vấn so sánh; cẩm nang | FR-26–28, 30, 31 |
| E3 ✓ | Live chat và chuyển giao ngữ cảnh; hộp thư hợp nhất; lưu chat AI che PII; Admin Console | FR-29, 36–38, 44 |
| E4 ✓ | Thông báo chống trùng; job nền; đồng bộ trạng thái và giá; chăm sóc khách | FR-32–34 |
| E5 ✓ | Hợp đồng, công tơ, hóa đơn, thu tiền, đối soát, biên lai, bảo trì, khách tiềm năng, dashboard, báo cáo | FR-35, 39, 41–45 |
| E6 ✓ | Bài đăng theo kênh, chia sẻ, trang tin công khai, cố vấn bằng văn bản và giọng nói | FR-46–48 |

**Còn lại sau E6** (đối chiếu code 09/10/2026; task theo [coding plan](coding-plan/README.md)):

| Việc | Trạng thái |
|---|---|
| Ảnh tin và ảnh sự cố | ✓ 08/10 (BE-06, FE-05): file local theo hash, lưu tại `.local/media` |
| Ưu đãi trong luồng chăm sóc khách | ✓ 08/10 (BE-07, FE-06, DA-04) |
| Ý định chat `simulate_finance` và số liệu chi phí VND | ✓ 08/10 (AG-02, FE-07; BE-05, FE-04) |
| Chủ nhà tự đăng ký + admin duyệt; vòng đời ticket hỗ trợ | ✓ 08/10 (BE-03, FE-02; BE-04, FE-03) |
| Test PostgreSQL | ✓ 08/10 (BE-01): 417 passed trên PostgreSQL 17.11, schema v13 |
| Viết lại bài đăng bằng LLM (tùy chọn) | Chưa làm (AG-05) |
| Demo trên trình duyệt | Kịch bản có ([kich-ban-demo.md](kich-ban-demo.md)); chưa quay, chưa kiểm viewport. Chốt G1, G2, G-NT |

## GĐ5 — Đánh giá và báo cáo

| Task | Kết quả |
|---|---|
| T5.1 | Khóa dữ liệu, cấu hình, prompt (freeze) — quy trình từng bước ở [eval/FREEZE.md](../eval/FREEZE.md) (08/10/2026) |
| T5.2 | Chạy trích xuất (luật và GPT-4o) và xếp hạng (B1 và P) trên tập test |
| T5.3 | Người chấm mù gán nhãn relevance; tính nDCG@5, P@5 theo cặp — công cụ sẵn sàng 08/10/2026: `eval label-sheet` (sheet blind xáo trộn, ẩn tên phương pháp) và `eval label-report` (nDCG@5, P@5, Cohen's kappa); nhãn do người dùng thu thập |
| T5.4 | Khảo sát 5–10 người dùng theo kịch bản demo đầu-cuối — phiếu sẵn sàng 08/10/2026: [eval/survey/khao-sat.md](../eval/survey/khao-sat.md) + `eval survey-report`; câu trả lời do người dùng thu thập |
| T5.5 | Báo cáo RQ1–RQ5, slide, video demo |

Chi tiết phương pháp ở [eval/PLAN.md](../eval/PLAN.md).

## Phân công theo thư mục

| Phần | Kế hoạch |
|---|---|
| Backend và agent | [backend/PLAN.md](../backend/PLAN.md), [backend/AGENT_PLAN.md](../backend/AGENT_PLAN.md) |
| Frontend | [frontend/PLAN.md](../frontend/PLAN.md), [frontend/UI_SPEC.md](../frontend/UI_SPEC.md) |
| Dữ liệu | [data/PLAN.md](../data/PLAN.md) |
| Đánh giá | [eval/PLAN.md](../eval/PLAN.md) |
| Hạ tầng | [infra/PLAN.md](../infra/PLAN.md) |
