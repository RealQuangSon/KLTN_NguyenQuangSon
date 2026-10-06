# Từ điển và quyết định sản phẩm HomeMatch

**Cập nhật:** 04/10/2026. Phạm vi hiện hành là sản phẩm v1 hoàn thiện theo [đặc tả](docs/dac-ta-san-pham.md), thay thế giới hạn MVP. [Chỉ mục docs](docs/README.md) là điểm bắt đầu.

## Thuật ngữ

| Thuật ngữ | Nghĩa sử dụng trong repository |
|---|---|
| HomeMatch | Nền tảng tìm và quản lý thuê phòng/studio, có trợ lý AI và bàn giao người thật |
| HubHome | Website nghiên cứu trải nghiệm/nghiệp vụ; không mặc định là nguồn inventory, API hoặc backend của HomeMatch |
| Người thuê / renter | Người có nhu cầu hoặc là bên thuê của hợp đồng; chỉ đọc dữ liệu của mình và projection được phép |
| Chủ nhà / owner | Người có quyền quản lý nguồn phòng trong một đơn vị; không tự đọc raw chat/ngân sách người thuê |
| Quản lý / manager | Người được phân công tư vấn/kiểm duyệt/vận hành; quyền gắn tài nguyên và đơn vị |
| Quản trị viên / admin | Vai trò quản trị có capability/audit; không phải cờ bỏ qua mọi access check |
| Đơn vị / organization | Phạm vi sở hữu và cách ly dữ liệu của nhóm chủ nhà/quản lý; khác nghĩa người thuê |
| Phòng thực / physical room | ID ổn định, unique organization/building/room_code; chống thuê trùng áp lên ID này dù có nhiều tin/nguồn |
| Tin phòng / room listing | Listing ID/source riêng, draft/published revisions và bằng chứng; tham chiếu physical room; moderation khác availability |
| Published listing | Phiên bản tin được kiểm duyệt để công khai; không phải approval của gợi ý AI |
| Public catalog | Catalog/list/detail/map từ tin published, với projection công khai |
| AI recommendation | Danh sách tạo từ hồ sơ xác nhận; pending hidden, chỉ công bố sau manager review đúng version |
| Draft profile | Nhu cầu chưa xác nhận, có trạng thái unknown/inferred/confirmed và provenance |
| Confirmed profile | Snapshot nhu cầu/scenario/ngân sách do người thuê xác nhận, có version |
| Hard constraint | Điều kiện bắt buộc, kiểm bằng code và bằng chứng; không được model tự nới |
| Soft preference | Ưu tiên dùng rank/explanation, không biến thành điều kiện bắt buộc |
| Quote | Giá thuê và phí có nguồn/đơn vị/điều kiện áp dụng, gắn phiên bản tin/điều khoản |
| Scenario | Số người/xe, mức điện/nước và các khoản chuyển nhà/sắm sửa dùng tính ước tính |
| Tổng tháng | Rent và các khoản định kỳ theo scenario; nếu thiếu khoản bắt buộc, full total là null |
| Tiền vào ở | Cọc + thuê trả trước + phí một lần + chuyển nhà + sắm sửa; không cộng lại tháng đầu |
| Known subtotal | Tổng các khoản đã biết; không phải tổng đầy đủ nếu vẫn thiếu dữ liệu |
| Unknown / null | Chưa có bằng chứng/giá trị; khác 0 và khác false |
| B1 | Baseline lọc/rank cấu trúc xác định, cấu hình có version |
| P | Blend B1 và semantic fit trên cùng eligible set; fallback B1 không được báo là kết quả P |
| Run | Một lần sinh gợi ý từ snapshot; profile có thể có nhiều run khi retry, chỉ một active run |
| HITL | Manager kiểm và duyệt gợi ý AI trước renter thấy; lịch xem xác nhận là bước riêng |
| Reviewed | Quyết định đã lưu nhưng chưa finalize/published; không cho renter thấy candidates |
| Stale / invalidated | Snapshot không còn khớp hồ sơ/kho/run hiện tại; không dùng approval cũ |
| Viewing requested | Lịch người thuê mong muốn; chưa confirmed, chưa reservation hoặc giao dịch |
| Reservation | Giữ phòng có thỏa thuận, thời hạn và transaction; không phát sinh tự động từ viewing |
| Contract | Điều khoản/tài liệu và chấp thuận cùng version của các bên; record không tự chứng minh e-sign pháp lý |
| Tenancy | Quan hệ thuê và việc bàn giao/thực tế vào ở; contract active khác tenancy active |
| Meter reading | Chỉ số công tơ có kỳ/đơn vị/bằng chứng, phân biệt measured/estimated/correction |
| Invoice | Khoản phải thu kỳ/terms snapshot; status draft/issued/void, payment_status unpaid/partially_paid/paid, overdue theo balance/hạn; khác estimate |
| Payment evidence | Chứng từ người thuê gửi; uploaded chưa xác nhận đã trả |
| Receipt / allocation | Khoản tiền đã được xác minh và phân bổ vào invoice; nguồn tính đã thu/còn nợ |
| Deposit ledger | Sổ nhận/khấu trừ/hoàn cọc có evidence; cọc không mặc định thành doanh thu thuê |
| Maintenance ticket | Báo lỗi/sửa chữa của tenancy, có phân công/chi phí/tiến độ/xác nhận |
| Outbox | Sự kiện gửi thông báo commit cùng nghiệp vụ, worker delivery/retry độc lập |
| Synthetic | Dữ liệu tổng hợp để demo/test; không phải nguồn phòng thực đã kiểm tra |

## Các quyết định đang áp dụng

- Phạm vi v1 có HM-01–HM-10, gồm cả tài khoản đầy đủ, portal owner, public discovery/map/media, lưu/lịch sử, hợp đồng, công tơ/hóa đơn/đối soát và sửa chữa.
- Bốn vai trò đích renter/owner/manager/admin; hiện mã 0.3.0 mới renter/manager và kho demo chung.
- Giữ deterministic money/filters/permissions/publication, version/CAS/idempotency và không công bố nháp AI.
- Target PostgreSQL, private media và outbox worker; SQLite giữ cho demo offline. Hiện một API worker; mở rộng cần kiểm concurrency/checkpoint.
- Manual evidence/receipt/reconciliation và document/acceptance hợp đồng bắt buộc. Gateway, legal e-sign, video-call riêng, AI ảnh/giọng và toàn quốc là mở rộng.
- API đang chạy 0.3.0 khác [API v1 thiết kế](docs/api-san-pham-v1.md). Không dùng docs để tự đổi nhãn source thành sản phẩm đã hoàn thiện.
- Bằng chứng nghiên cứu/test có ngày/phạm vi; không đổi mock thành live, synthetic thành inventory thật, mục tiêu thành kết quả.
- Bộ AC-HM và P0–P4 quyết định nghiệm thu sản phẩm. P5 quyết định bàn giao nghiên cứu; các ID MVP cũ chỉ còn giá trị lịch sử.
