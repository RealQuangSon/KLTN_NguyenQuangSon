# Danh mục yêu cầu HomeMatch v1

**Cập nhật:** 04/10/2026. Toàn bộ 30 yêu cầu dưới đây là bắt buộc cho sản phẩm v1. Các chức năng chi tiết đi cùng yêu cầu phải được triển khai, không chỉ tạo màn hình hoặc endpoint rỗng.

Nguồn `HH-*` tham chiếu [nghiên cứu HubHome](nghien-cuu-hubhome.md); nhãn **HM** là lựa chọn hoặc quy tắc riêng của HomeMatch. Một nguồn website chỉ giải thích vì sao có nhu cầu, không chứng minh khả năng thực tế của website hoặc của mã hiện tại. AC nằm ở [bộ nghiệm thu](tieu-chi-nghiem-thu.md).

## Yêu cầu chức năng và truy vết

| ID | Hành vi và quy tắc bắt buộc | Nguồn | AC |
|---|---|---|---|
| HM-01-R01 | Đăng ký/xác minh, đăng nhập/đăng xuất, khôi phục mật khẩu; token/reset có hạn, dùng một lần, thu hồi; lỗi không tiết lộ tài khoản tồn tại | HH-05; HM security | AC-HM-01-01 |
| HM-01-R02 | Hồ sơ cá nhân, tùy chọn lưu hội thoại/ghi nhớ, quản lý phiên; đổi mật khẩu thu hồi phiên theo policy; xóa dữ liệu cá nhân theo quy trình có trạng thái | HH-05/12; HM | AC-HM-01-02 |
| HM-01-R03 | Membership và quyền renter/owner/manager/admin theo đơn vị và bản ghi; không tin role/owner/organization từ client | HH-07/12; HM isolation | AC-HM-01-03 |
| HM-02-R01 | Chủ nhà tạo/sửa tòa nhà/phòng thực có ID ổn định, tin/listing revisions riêng, giá/phí, tiện ích, capacity, địa chỉ có độ chính xác, ảnh có quyền và nguồn/thời điểm xác minh; kiểm schema/null/zero và trùng phòng | HH-07; HM data model | AC-HM-02-01 |
| HM-02-R02 | Tin có draft/submitted/changes_requested/published/suspended/archived; quản lý kiểm duyệt cùng revision; thay giá/phí/địa chỉ cần duyệt phiên bản mới trước công bố | HH-07/12; HM | AC-HM-02-02 |
| HM-02-R03 | Availability unknown/available/reserved/occupied/unavailable riêng moderation; reservation có khoảng kỳ/thời hạn, contract active giữ kỳ planned, không giữ bởi lịch xem; kiểm overlap theo phòng thực, hết hạn contract không tự giải phóng tenancy đang ở | HH-07; HM | AC-HM-02-03 |
| HM-03-R01 | Khách tìm tin published bằng thành phố/khu vực/loại/ngân sách/số người/tiện ích và sort/pagination; tách trần thuê với tổng phí, không coi phí thiếu là 0 | HH-01/02/03; HM | AC-HM-03-01 |
| HM-03-R02 | List/detail/map đồng bộ cùng filters/revision; public coordinates gần đúng; distance ghi cách đo/sai số; có phương án danh sách khi map lỗi | HH-04/12; HM | AC-HM-03-02 |
| HM-03-R03 | Chi tiết hiện media, nguồn/xác minh, phí/scenario/phần thiếu, availability và report tin; ẩn địa chỉ/liên hệ chính xác nếu không có quyền | HH-03/04/12; HM | AC-HM-03-03 |
| HM-04-R01 | Hội thoại nhận diện tìm phòng/hỏi rõ/tính phí/hỗ trợ; trích xuất thành draft có provenance, người thuê xác nhận ngân sách/scenario trước matching | HH-02/03/06; HM confirmation | AC-HM-04-01 |
| HM-04-R02 | Hard filter deterministic trước B1/P cùng eligible set; cost null không vượt qua constraint cần biết; reason/score có evidence; provider lỗi có fallback nhãn rõ | HH-02/03; HM ranking | AC-HM-04-02 |
| HM-04-R03 | Nháp AI chỉ manager được phân công xem; approve subset/order cùng version; renter chỉ nhận published/current; sửa hồ sơ/kho làm stale, không kế thừa approval | HH-06/12; HM HITL riêng | AC-HM-04-03 |
| HM-05-R01 | Favorites và saved search theo tài khoản, tiếp tục được trên thiết bị khác; tin stale/archived được đánh dấu, không giữ bản copy như còn thuê được | HH-05; HM | AC-HM-05-01 |
| HM-05-R02 | Lịch sử phiên tư vấn/kết quả và tiếp tục phiên theo consent/retention; không khôi phục kết quả chưa được duyệt hoặc của người khác | HH-05/12; HM | AC-HM-05-02 |
| HM-05-R03 | So sánh 2–3 ID khác nhau cùng scenario; mode public_catalog dùng tin published, mode ai_recommendation dùng cùng published run; không trộn mode hoặc tin stale | HH-03/04; HM | AC-HM-05-03 |
| HM-06-R01 | Renter gửi lịch tương lai có timezone, nguồn tin và revision; manager assigned confirm/decline/cancel/reschedule, giữ lịch sử và kiểm slot; requested không là confirmed | HH-06; HM | AC-HM-06-01 |
| HM-06-R02 | Sau lịch có completed/no_show và kết quả, link tư vấn/nguồn phòng; ticket người thật có phân công, open/in_progress/resolved/closed và reopen | HH-06; HM | AC-HM-06-02 |
| HM-06-R03 | In-app + email giao dịch cho lịch, duyệt, hợp đồng, hóa đơn, sửa chữa; outbox commit cùng nghiệp vụ, retry/dedup, trạng thái gửi độc lập trạng thái nghiệp vụ | HH-06; HM | AC-HM-06-03 |
| HM-07-R01 | Soạn hợp đồng/tài liệu với renter, đơn vị, phòng, kỳ hạn, rent/fees/deposit, version và lịch hiệu lực; hai bên chấp thuận đúng bản, sửa điều khoản hủy chấp thuận cũ | HH-08; HM | AC-HM-07-01 |
| HM-07-R02 | Activate hợp đồng có quyền/chấp thuận; reservation riêng có expiry; tenancy active qua biên bản vào ở/công tơ/tài sản/cọc; transaction chặn thuê trùng kỳ | HH-08; HM | AC-HM-07-02 |
| HM-07-R03 | Gia hạn/chấm dứt/trả phòng có điều khoản, thông báo, bàn giao, hóa đơn cuối và sổ cọc; deduction proposed/accepted/disputed có bằng chứng và bên chấp thuận/căn cứ điều khoản; disputed hold chưa thành khấu trừ đã quyết toán; closed không tự xóa hồ sơ | HH-08/09; HM | AC-HM-07-03 |
| HM-08-R01 | Chỉ số tích lũy đầu/cuối theo công tơ/phòng/kỳ `[start,end)` có ảnh/xác minh; consumption là hiệu chỉ số hoặc tổng đoạn replacement có nguồn; rate tại đầu kỳ, đổi giữa kỳ chỉ chia đoạn với amendment được chấp thuận và boundary reading | HH-10; HM | AC-HM-08-01 |
| HM-08-R02 | Invoice lifecycle draft/issued/void, payment_status unpaid/partially_paid/paid và overdue suy từ balance/hạn; line/rate/quantity/rounding/snapshot rõ, rent advance phân bổ kỳ; issued không sửa âm thầm, điều chỉnh bằng bản ghi đối ứng | HH-09/10; HM ledger | AC-HM-08-02 |
| HM-08-R03 | Người thuê gửi chứng từ; người có quyền xác minh receipt/allocate; partial/overpayment/refund/dispute có ledger và lý do; uploaded chưa là paid; replay không cộng tiền hai lần | HH-09; HM | AC-HM-08-03 |
| HM-09-R01 | Người thuê có tenancy gửi maintenance ticket mô tả, ảnh, mức ưu tiên; đánh dấu khẩn và hướng dẫn liên hệ; chỉ các bên được giao đọc nội dung | HH-11; HM | AC-HM-09-01 |
| HM-09-R02 | Người phụ trách triage/phân công/đề xuất lịch và chi phí; trạng thái submitted/triaged/scheduled/in_progress/resolved/closed/cancelled; cost event ghi payer, bên chịu tiền chấp thuận hoặc căn cứ terms được xác minh; dispute chưa tự charge | HH-11; HM | AC-HM-09-02 |
| HM-09-R03 | Hoàn tất có ghi nhận công việc/bằng chứng/chi phí; renter xác nhận hoặc reopen có lý do; khoản thu đưa sang billing bằng tham chiếu, không charge trùng | HH-11/09; HM | AC-HM-09-03 |
| HM-10-R01 | Admin/manager queues theo quyền, phân công/chuyển giao có audit; dashboard nguồn phòng/lịch/thuê/công nợ/ticket từ bản ghi thực; không lộ PII trong thống kê | HH-07; HM | AC-HM-10-01 |
| HM-10-R02 | Audit thay đổi quyền/giá/tin/review/lease/invoice/receipt; yêu cầu export/delete/restrict có trạng thái và retention theo policy; file private có access check/link có hạn | HH-12; HM | AC-HM-10-02 |
| HM-10-R03 | Readiness, monitoring/alert, migration/rollback, backup/restore, queue recovery, runbook và release evidence; secret/PII/checkpoint/raw chat không vào gói public | HM vận hành | AC-HM-10-03 |

## Yêu cầu chất lượng của bản phát hành

| ID | Tiêu chí đề xuất để nghiệm thu | Cách chứng minh |
|---|---|---|
| NFR-01 Quyền | 0 truy cập trái quyền trong ma trận actor×đơn vị×bản ghi; kiểm cả API/file/export, không chỉ UI | Negative integration tests và browser các vai trò |
| NFR-02 Số học | 100% bộ oracle finance/billing/receipt được duyệt độc lập đúng VND; replay và rounding không đổi ledger | Expected results độc lập, audit và DB assertions |
| NFR-03 UX | Các tác vụ cốt lõi chạy ở 360/768/1440 px, dùng bàn phím; nhãn/đọc lỗi/focus/contrast theo checklist WCAG 2.2 AA áp dụng | Browser QA + kiểm accessibility, ghi ngoại lệ |
| NFR-04 Tốc độ | Trên staging tương đương cấu hình release: API đọc p95≤1s, mutation thường p95≤2s với 20 phiên đồng thời, 1.000 tin và 10.000 invoice; AI phản hồi processing≤2s, tự timeout≤30s | Load scenario/version/hardware/cold-warm/error rate công bố; mục tiêu chưa phải kết quả |
| NFR-05 Độ bền | Review/lease/invoice/receipt không commit trùng sau crash/retry; notification đến sau restart hoặc lộ rõ failed | Fault injection tại các mốc commit/resume/delivery |
| NFR-06 Khôi phục | Mục tiêu ban đầu RPO≤24h, RTO≤4h cho ledger+media; restore staging chứng minh totals/quyền/checkpoints nhất quán | Runbook và diễn tập có thời điểm; chưa claim SLA đã đạt |
| NFR-07 Riêng tư | Log/embedding/export không chứa secret/raw chat/PII ngoài phạm vi; retention/consent và quyền truy cập được triển khai | Sample log review, retention job, export/delete scenario |
| NFR-08 Trung thực dữ liệu | Synthetic, unknown, approximate, estimated, pending và fallback hiển thị đúng ở API/UI/report | Fixtures và browser assertions theo từng trạng thái |

Các ngưỡng NFR là đề xuất thiết kế v1 để đo trước release. Nếu đổi tải, thời hạn, cấu hình hoặc scope phải cập nhật trước nghiệm thu và giữ kết quả theo cấu hình thực. Kiểm pháp lý/chính sách dùng dữ liệu thực là đầu vào phát hành, không được suy từ disclaimer của website tham khảo.
