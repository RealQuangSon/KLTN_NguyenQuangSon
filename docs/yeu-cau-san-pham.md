# Danh mục yêu cầu HomeMatch AI Agent

**Cập nhật:** 31/10/2026 (LF: trường tin đăng mở rộng — cập nhật FR-24, 26, 27); trước đó 08/10/2026 (thêm FR-49, cập nhật FR-08, 33, 38, 40, 43, NFR-04, 05); mở rộng 5 phân hệ ngày 05/10. Yêu cầu được suy ra từ [đề cương](ke-hoach-kltn-homematch.md).

- **Mức:**
  - **CB**: yêu cầu cơ bản của đề tài;
  - **NC**: phần nâng cao của đề tài;
  - **NT**: phân hệ nền tảng người dùng yêu cầu ngày 05/10.
- **Hiện trạng:** đối chiếu code ngày 09/10/2026.
  - **Đã có**: có code và test tự động.
  - **Một phần**: có nền nhưng thiếu hành vi nêu trong yêu cầu.
- Cột AC trỏ tới [tiêu chí nghiệm thu](tieu-chi-nghiem-thu.md).

## 1. Trợ lý AI (đề tài)

| ID | Yêu cầu | Mức | Hiện trạng | AC |
|---|---|---|---|---|
| FR-01 | Hội thoại tiếng Việt, phân loại ý định (tìm, chi phí, gặp người thật, cẩm nang). Ý định rõ ràng đi nhánh luật, không gọi LLM. | CB | Đã có | AC-01 |
| FR-02 | Trích xuất thành phố, khu vực (kèm tên gọi khác), loại, số phòng ngủ, số người, sở thích, điểm đến, mô tả mềm. Mỗi trường có trạng thái và nguồn. | CB | Đã có | AC-01 |
| FR-03 | Harness hỏi tối đa 1 câu mỗi lượt, tối đa 2 câu trước kết quả đầu tiên; chip lấy từ kho, khách sửa/xóa từng trường | CB | HN-02 đã kiểm offline (06/11), chờ bằng chứng HUST/Jev live; xem review/HN-02.md | AC-01 |
| FR-04 | Khách xác nhận hồ sơ trên form; mỗi lần tạo phiên bản bất biến; tiền nêu trong chat không tự thành ngân sách | CB | Đã có | AC-02 |
| FR-05 | Tổng tháng, tiền vào ở; khoản chưa biết giữ `null` | CB | Đã có | AC-03 |
| FR-06 | Khả năng chi trả: trần tổng tháng, tiền mặt, tỷ lệ trên thu nhập, băng đánh giá | CB | Đã có | AC-03 |
| FR-07 | Ước tính vay ngắn hạn (annuity) cho phần tiền vào ở còn thiếu | CB | Đã có | AC-04 |
| FR-08 | Mô phỏng tối đa 3 kịch bản tài chính | NC | Đã có (giao diện và chat, 08/10) | AC-04 |
| FR-09 | Lọc cứng trước xếp hạng; thiếu bằng chứng thì đưa vào "cần xác minh" | CB | Đã có | AC-05 |
| FR-10 | B1: điểm chi phí, sở thích, vị trí; tất định | CB | Đã có | AC-05 |
| FR-11 | P: B1 kết hợp semantic (pgvector) trên tập đủ điều kiện; quay về B1 khi thiếu vector, ghi rõ nhãn | CB | Một phần (chưa chạy với vector thật) | AC-06 |
| FR-12 | Lý do, đánh đổi, cờ xác minh có bằng chứng | CB | Đã có | AC-07 |
| FR-13 | Không thiên vị căn tồn (ranking không đọc hoa hồng/thời gian đăng); phần duyệt có lý do thay đổi đã bị bỏ theo D-10 | CB | Đã có (phần ghi lý do duyệt bỏ 05/11) | AC-08 |
| FR-14 | Phân biệt `no_match` và `needs_verification`; gợi ý nới lỏng mềm | CB | Đã có | AC-05 |
| FR-15 | **Mỗi chủ nhà chỉ thấy phòng của mình** trong lead/CRM; kết quả tới khách ngay sau xếp hạng (D-10 bỏ bước duyệt 05/11) | CB | Đã có (đã đổi thiết kế 05/11) | AC-09 |
| FR-16 | (Đã bỏ theo D-10, 05/11/2026) Chủ nhà duyệt từng phần phòng — thay bằng lead `recommended` top 5 và thông báo `rooms_ready` cho khách | CB | Bỏ | AC-09 |
| FR-17 | Hồ sơ hoặc kho đổi thì kết quả cũ hết hiệu lực | CB | Đã có | AC-09 |
| FR-18 | Khách xem top căn kèm giải thích, chi phí, băng tài chính, khoản vay | CB | Đã có | AC-10 |
| FR-19 | So sánh trực quan 2–3 căn: bảng, nhãn "Tốt nhất", biểu đồ chi phí | NC | Đã có | AC-10 |
| FR-20 | Gửi yêu cầu xem căn; chủ nhà của căn xác nhận | CB | Đã có | AC-10 |
| FR-21 | Multi-agent: supervisor và các agent nhu cầu, tài chính, xếp hạng, cẩm nang, hỗ trợ; danh sách tool riêng | NC | Đã có; HN-03 (06/11): registry sinh schema/quyền/view, hợp đồng tool và khóa retry bền (kiểm offline; chưa PG/live) | AC-11 |
| FR-22 | Memory sở thích xuyên phiên khi khách đồng ý | NC | Đã có | AC-12 |
| FR-23 | Đánh giá độ chính xác và độ hài lòng | NC | Một phần (CLI eval có; chưa có nhãn người chấm và khảo sát) | [eval](../eval/PLAN.md) |
| FR-24 | Kho phòng, studio, căn hộ tại TP.HCM và Hà Nội | CB | Đã có (31/10: tin đăng có thêm nội dung tin đã che SĐT/email, ngày đăng, loại người đăng, phường cũ/mới, tên đường, ngày trống, kỳ thanh toán, thời hạn tối thiểu và 19 khóa tiện ích; trường mới đều `null` khi tin không ghi; áp cho catalog demo Chợ Tốt crawler 2.2. FC-01 31/10: mô tả, nội quy và features_text do chủ nhà nhập cũng được server che SĐT/email lúc tạo/sửa tin, trang tin công khai không hiện số liên hệ nào) | AC-13 |
| FR-25 | Đăng nhập theo vai trò khách, chủ nhà, quản trị; kiểm quyền theo bản ghi | CB | Đã có | AC-14 |

## 2. Cổng người thuê

| ID | Yêu cầu | Mức | Hiện trạng | AC |
|---|---|---|---|---|
| FR-26 | Tìm theo bộ lọc (thành phố, khu vực, loại, khoảng giá, tổng tháng, diện tích, phòng ngủ, số người, tiện nghi, sắp xếp, phân trang) trên tin đã công khai | NT | Đã có (`GET /listings`; 31/10: thêm sắp xếp "Mới đăng" chỉ do người dùng chọn ở tìm theo bộ lọc, xếp hạng AI không dùng ngày đăng/loại người đăng — kiểm bằng `eval invariants`) | AC-15 |
| FR-27 | Khung xem nhanh bên cạnh; chuyển giữa danh sách và bản đồ; vị trí gần đúng có vòng sai số | NT | Đã có (Leaflet + OSM; 31/10: xem nhanh và trang tin công khai có địa chỉ chi tiết phường cũ/mới, "Đăng N ngày trước", nhãn môi giới/chính chủ chỉ khi tin ghi rõ, khối "Điều khoản thuê" với mục chưa rõ hiện "Chưa rõ", nội dung tin thu gọn, chip tiện ích true/false/null) | AC-15 |
| FR-28 | AI phân tích ưu/nhược điểm của các căn được chọn và đề xuất căn tối ưu theo ngân sách | NT | Đã có (tư vấn tất định từ engine chi phí) | AC-16 |
| FR-29 | Live chat 1-1 với chủ nhà; chuyển ngữ cảnh từ AI: nhu cầu, phòng, băng tài chính, chat gần nhất đã che PII | NT | Đã có (cập nhật định kỳ 5 giây, chưa realtime) | AC-17 |
| FR-30 | Lịch xem trực tiếp hoặc trực tuyến (link phòng họp); đặt từ danh sách AI hoặc từ tin đăng | NT | Đã có (Jitsi) | AC-18 |
| FR-31 | Cẩm nang: hỏi đáp quyền lợi, quy định chung, điều khoản; nội quy và cách tính phí của từng chủ nhà; hỏi được trong chat | NT | Đã có (truy xuất, không sinh nội dung) | AC-19 |

## 3. Động cơ tự động hóa

| ID | Yêu cầu | Mức | Hiện trạng | AC |
|---|---|---|---|---|
| FR-32 | Nhắc lịch xem (trong 24 giờ), nhắc thanh toán (sắp đến hạn và quá hạn), nhắc gia hạn hợp đồng (30 ngày) | NT | Đã có (job nền + `manage jobs`) | AC-20 |
| FR-33 | Chăm sóc khách đã xem tin mà chưa đặt lịch: gửi gợi ý căn tương đương, kèm ưu đãi còn hạn do chủ nhà tự đặt | NT | Đã có (ưu đãi 08/10; không ảnh hưởng xếp hạng) | AC-20 |
| FR-34 | Đồng bộ biến động: trạng thái phòng (trống/đã cọc/đã thuê/ẩn), giá, bảng phí → thông báo cho khách đã quan tâm | NT | Đã có (trong ứng dụng; email là stub) | AC-20 |
| FR-35 | Tự tạo hợp đồng, hóa đơn, biên lai giữa chủ nhà và khách | NT | Đã có (HTML in được; không phải chữ ký số) | AC-21 |

## 4. Admin Console

| ID | Yêu cầu | Mức | Hiện trạng | AC |
|---|---|---|---|---|
| FR-36 | Lưu và theo dõi lịch sử chat AI–người dùng; che PII; giữ 90 ngày; mỗi lần mở được audit | NT | Đã có | AC-22 |
| FR-37 | Quản lý chuyển giao AI → chủ nhà: tỷ lệ phản hồi, thời gian phản hồi đầu tiên | NT | Đã có | AC-22 |
| FR-38 | Người dùng, kiểm duyệt tin (ẩn/hiện), vận hành (job, số liệu, khởi tạo lại bản lỗi), vòng đời ticket hỗ trợ (duyệt/tiếp nhận/giải quyết có ghi chú, thông báo khách) | NT | Đã có (ticket chỉ admin thao tác, 08/10) | AC-22 |
| FR-49 | Chủ nhà tự đăng ký (xác minh email); admin duyệt trước khi chủ nhà được công khai tin; owner seed luôn đã duyệt | NT | Đã có (08/10) | AC-22 |

## 5. Cổng chủ nhà (PMS & CRM)

| ID | Yêu cầu | Mức | Hiện trạng | AC |
|---|---|---|---|---|
| FR-39 | Dashboard: lấp đầy, trống/cọc/thuê, thực thu tháng, công nợ, quá hạn, lịch 7 ngày, sự cố, hợp đồng sắp hết | NT | Đã có | AC-23 |
| FR-40 | Quản lý phòng và tin: tạo, sửa (CAS), công khai/ẩn, trạng thái trống/đã cọc/đã thuê, nội quy, ảnh tin | NT | Đã có (ảnh 08/10: kiểm magic bytes, 5 MB, 10 ảnh/tin) | AC-23 |
| FR-41 | Hợp đồng và khách thuê: soạn, gửi, khách chấp thuận đúng phiên bản, kích hoạt, gia hạn, thanh lý; chống trùng kỳ | NT | Đã có | AC-21 |
| FR-42 | Tài chính: chốt chỉ số điện nước, lập hóa đơn (không sửa sau phát hành), ghi thu, khách báo chuyển và chủ xác nhận, biên lai, đối soát theo kỳ | NT | Đã có (không cổng thanh toán) | AC-24 |
| FR-43 | Bảo trì: khách đang thuê báo hỏng, chủ phân công, cập nhật tiến độ và chi phí, khách xác nhận hoặc mở lại, đính ảnh sự cố | NT | Đã có (ảnh 08/10: tối đa 5 ảnh, chỉ hai bên xem được) | AC-25 |
| FR-44 | CRM: khách tiềm năng theo giai đoạn và mức quan tâm, hộp thư hợp nhất, phòng xem trực tuyến, lịch hẹn | NT | Đã có | AC-23 |
| FR-45 | Báo cáo: lượt xem, yêu cầu xem, tỷ lệ chuyển đổi, doanh thu từng phòng | NT | Đã có | AC-23 |

## 6. Trợ lý AI cho chủ nhà

| ID | Yêu cầu | Mức | Hiện trạng | AC |
|---|---|---|---|---|
| FR-46 | Viết bài đăng theo văn phong Facebook, Zalo, diễn đàn từ thông số phòng | NT | Đã có (mẫu theo kênh, chỉ dùng dữ liệu tin; chưa dùng LLM viết lại) | AC-26 |
| FR-47 | Chọn điểm mạnh và chia sẻ nhanh đa kênh | NT | Một phần (link chia sẻ Facebook, trang tin công khai, sao chép nội dung; không tự đăng) | AC-26 |
| FR-48 | Cố vấn bằng văn bản hoặc giọng nói: vì sao phòng trống lâu, đề xuất giá theo căn tương đương, doanh thu, công nợ, lấp đầy | NT | Đã có (định tuyến luật; giọng nói phụ thuộc trình duyệt) | AC-26 |

## 7. Yêu cầu phi chức năng

| ID | Yêu cầu | Cách chứng minh |
|---|---|---|
| NFR-01 Bảo mật tài chính | Không có tiền, thu nhập, liên hệ trong prompt, embedding, log. Chủ nhà chỉ thấy băng. Ngữ cảnh chuyển giao không có thu nhập. | Test DTO chủ nhà, test chuyển giao, `redact` |
| NFR-02 Minh bạch | Mọi khẳng định trong lý do có bằng chứng | `eval grounding` |
| NFR-03 Công bằng | Đổi hoa hồng hoặc thời gian tồn không đổi thứ hạng; chủ nhà không đẩy được phòng mình lên trước phòng người khác | `eval invariants`, `test_landlord.py` |
| NFR-04 Đúng tiền | Oracle chi phí và vay khớp chính xác; hóa đơn khớp số tính tay; không thu vượt số còn nợ | `eval oracle`, `eval invoices` (12 ca hóa đơn tính tay, 08/10), `test_pms.py` |
| NFR-05 Chi phí semantic | Không embed lại vector căn cùng hash; cache truy vấn bền; giới hạn lượt | Metrics `semantic_usage`; `provider_usage` tách token input/output/embedding theo model (08/10, AG-03); quy VND trên `/admin/metrics` có `cost` (08/10, BE-05 — giá thật do người dùng điền vào file bảng giá) |
| NFR-06 Độ trễ | Mục tiêu p95 phản hồi chat ≤ 5 giây khi dùng GPT-4o, ≤ 1 giây offline | `eval measure` (chưa đo live) |
| NFR-07 Độ bền | Quyết định duyệt, hợp đồng, thanh toán không ghi trùng khi gửi lại; job chạy lặp không thông báo trùng | Test durability, khóa chống trùng |
| NFR-08 Trung thực dữ liệu | Dữ liệu tổng hợp, chưa biết, gần đúng, chờ duyệt, stub hiển thị đúng nhãn | Test UI và API |
| NFR-09 Triển khai | Chạy trên localhost: một worker uvicorn, SQLite hoặc PostgreSQL local (pgvector khi chạy P). Deploy cloud ngoài phạm vi (D-09, 28/10) | Đã có: `check-local.sh`, smoke HTTP trên server uvicorn thật (05/10) |
| NFR-10 Lưu trữ chat | Che PII khi lưu; xóa sau 90 ngày (`HOMEMATCH_CHAT_RETENTION_DAYS`) | Test admin transcript |
| NFR-11 Quyền theo bản ghi | Chủ nhà chỉ thấy phòng, hợp đồng, hóa đơn, chat, sự cố của mình; khách chỉ thấy của mình | Test quyền ở từng module |
