# Kịch bản demo HomeMatch — hiện có và toàn vòng đời thuê

**Cập nhật 04/10/2026.** Demo A kiểm tra subset đang có của API 0.3.0; Demo B là kịch bản nghiệm thu sản phẩm mục tiêu API v1/HM-01…HM-10. Demo B chưa chạy vì nhiều module chưa triển khai. Viết kịch bản không biến các màn mục tiêu thành tính năng đang có.

Đọc cùng [UI_SPEC](UI_SPEC.md), [TEST_CHECKLIST](TEST_CHECKLIST.md), [quy trình sản phẩm](../docs/quy-trinh-nghiep-vu.md) và [nghiệm thu](../docs/tieu-chi-nghiem-thu.md). Chỉ ghi đạt sau thao tác với API thật và lưu evidence. Browser/API offline và live AI phải có nhãn đúng; ảnh/video không chứa credentials hoặc dữ liệu cá nhân thật.

## 1. Chuẩn bị chung

- [ ] Ghi source/API/schema/data/config version, ngày, môi trường, browser/device/viewport, một API worker hiện tại và mode model/matching/embedding.
- [ ] Dùng DB/dataset tổng hợp cô lập, thời gian/slot/period rõ trong manifest; không gửi thông báo tới người thật hoặc đăng dữ liệu lên dịch vụ ngoài trong demo local.
- [ ] Có tài khoản theo seed/environment; không đưa mật khẩu vào docs/video. Demo A dùng renter-a/renter-b/manager-a/manager-b. Demo B cần thêm owner-a/owner-b/admin-scoped và scopes thật; các account này hiện là fixture mục tiêu cần tạo.
- [ ] Chuẩn bị dữ liệu có missing/zero/included/approximate location, tin hidden/unavailable, profile/run stale và các ca âm. Data tổng hợp chỉ ở fixture/test/demo được ghi nhãn, không runtime fallback.
- [ ] Evidence từng bước gồm expected/actual/status/entity IDs/version/receipt và screenshot phù hợp; mất response/conflict cần ghi cách phục hồi.

## 2. Demo A — subset hiện có trước thuê

**Phạm vi:** landing/login → chat/profile/confirm → HITL → results/compare → viewing → invalidation/auth. Không đại diện owner/admin, map/history/favorites hoặc vận hành sau thuê.

| Bước | Thao tác | Kết quả cần chứng minh |
|---|---|---|
| A01 | Renter-a nhập nhu cầu từ landing rồi login; renter-b và manager-b mở riêng để ca âm | Nhu cầu tiếp tục một lần đúng renter; sai actor không đọc phiên |
| A02 | Gửi “Tìm phòng TP.HCM Quận 7, một người, có cửa sổ, tầm 3,5 triệu” | Form/draft có inference; budget hint chưa thành ngân sách confirmed |
| A03 | Chủ động nhập tổng tháng 3.500.000 ₫, tiền ban đầu 6.500.000 ₫; một người/một xe/140 kWh/3 m³/chuyển 300.000/sắm 200.000 và xác nhận | Backend nhận profile/scenario/version đúng; không tự suy các số tiền |
| A04 | Chờ tạo run/manager review | Pending không có cards/detail/compare/viewing; ghi run/profile version |
| A05 | Manager-a mở queue, kiểm tra phí/source/unknown, chọn subset/reason rồi approve; manager-b thử truy cập | Assigned manager duyệt đúng run; ca âm bị backend chặn; mất response không giả published |
| A06 | Renter-a đọc lại published, mở chi tiết/chi phí | Chỉ subset approved/current, tối đa 5; rent/monthly/initial/unknown/0 phân biệt |
| A07 | Chọn 2 rồi 3 phòng để compare, thử phòng thứ tư | Compare cùng run/scenario, fourth bị chặn; không local rank/tính tiền |
| A08 | Đề xuất thời điểm tương lai theo timezone thiết bị; manager-a confirm một lịch và decline lịch khác | Server UTC; requested khác confirmed/declined; UI đọc lại đúng status |
| A09 | Sửa nhu cầu qua chat/form, giữ finance/scenario và confirm lại | Run mới pending, approval cũ không truyền sang; reply cũ không thay results |
| A10 | Manager đổi catalog availability/publication theo revision; renter thử compare/viewing cũ | Run ảnh hưởng invalidated, stale actions bị chặn; CAS conflict đọc lại |
| A11 | Mất response mạng tại review/viewing và thử recovery; đổi account/logout | Key/payload không đổi khi retry hỗ trợ; message/confirm/patch không tự resend; dữ liệu account cũ gỡ |

- [ ] Chạy A01…A11 với backend thật; fixture tests không tự đánh dấu bước đạt.
- [ ] Ghi riêng browser compare 3/declined/loss/restart nếu đã làm; không dùng ghi chép 02/10 để xác nhận lượt mới.
- [ ] Báo rõ offline B1/rule demo hay GPT/embedding live; demo này không chứng minh chất lượng model hoặc full product readiness.

## 3. Demo B — sản phẩm toàn vòng đời thuê

**Persona:** renter-a tìm và thuê; owner-a quản lý nhà/phòng; manager-a được phân công moderation/HITL/lịch/vận hành; admin-scoped quản trị đúng quyền. Renter-b/owner-b/manager-b là ca âm. Mọi dữ liệu là tổng hợp. Nhóm module chưa có API/UI phải để “chưa triển khai”, không dựng kết quả giả trong runtime.

### B1. Tài khoản, nguồn cung và moderation · HM-01/02/10

- [ ] Renter/owner đăng ký, xác minh, login/profile/recovery theo target contract; role manager/admin chỉ được cấp qua quyền server. Đọc security sessions, revoke một phiên và thử deep link bị thu hồi.
- [ ] Admin-scoped phân công manager-a cho owner/property/runs phù hợp; audit ghi actor/time/entity/reason/outcome. Client không tự đổi role/scope.
- [ ] Owner-a tạo nhà/phòng, location có precision, quote/phí/amenities/availability, media có quyền sử dụng/alt và lưu nháp. Owner-b thử đọc/sửa tin hoặc media, phải bị chặn.
- [ ] Gửi listing moderation; manager-a yêu cầu sửa một lỗi, owner sửa revision và gửi lại; manager approve tin. Draft/save không tự public, listing moderation không approve gợi ý AI.
- [ ] Manager-b ngoài scope và renter thử đọc draft tin/AI, đều bị chặn. Upload/error/validation/CAS conflict có UI và receipt thật.

### B2. Public discovery và AI cá nhân hóa · HM-03/04

- [ ] Renter tìm bằng filter tại `/phong`, chuyển map/list, mở gallery/detail/source/fees; marker/card cùng listing ID/revision. Một tin approximate chỉ có vị trí gần đúng; lỗi map vẫn dùng list được.
- [ ] Gửi nhu cầu vào assistant, xem draft/hỏi rõ và xác nhận profile/scenario. UI có rail/chat–preview, mobile tab và drawer giữ trạng thái.
- [ ] Kiểm tra pending không lộ candidates; manager-a review costs/source/missing, approve subset đúng version. Renter chỉ nhận published/current; listing public vẫn là luồng riêng.
- [ ] Gửi yêu cầu chỉ tính chi phí theo fixture dưới đây, không yêu cầu tìm. Product phải trả phép tính/giả định đúng intent; không thay bằng kết luận kho không có phòng. Luồng này là nghiệm thu target, chưa là claim API hiện có hỗ trợ đầy đủ.

**Fixture chi phí minh họa cho Demo B:** tiền thuê 2.500.000 ₫/tháng; điện 140 kWh × 3.500 = 490.000; nước 3 m³ × 10.000 = 30.000; internet 100.000; xe 100.000; dịch vụ 30.000. Tổng tháng xác định là **3.250.000 ₫**. Cọc 2.500.000, trả trước một tháng 2.500.000, chuyển nhà 300.000 và sắm ban đầu 200.000; tiền ban đầu là **5.500.000 ₫**. Không có khoản missing/included trong fixture này; ca missing/zero/included kiểm tra riêng. Đây là giả định tổng hợp do dự án đặt, không là phòng/giá/câu trả lời HubHome.

### B3. Lưu, lịch sử, compare, viewing và handoff · HM-05/06

- [ ] Lưu/bỏ lưu tin và saved search name/filter/scenario, sửa/xóa/chạy lại không sao approval cũ; ghi đã xem/cân nhắc/loại, mở phiên lịch sử trên phiên đăng nhập thứ hai cùng account; account khác không thấy lists/history.
- [ ] Compare 2–3 tin public cùng source/scenario; compare AI riêng với approved/current run. Không trộn nguồn hoặc so AI pending/stale. Thay giá/ẩn tin hiện nhãn thay đổi và chặn CTA trái rule.
- [ ] Renter đề xuất lịch tại chỗ/trực tuyến, owner-a đề xuất slot, manager-a được giao confirm; thử decline/cancel/reschedule và slot conflict. Requested không giữ phòng.
- [ ] Xem tour/media/link tại lịch trực tuyến; không cần tự dựng video call platform. Mark completed/no-show theo API thật.
- [ ] Handoff có receipt/đầu mối/trạng thái; in-app notification read/unread, email giao dịch tới hộp thư sandbox và deep link đúng quyền; mail không có tài liệu/chat/chứng từ private. Retry event không tạo notification trùng; không nói người thật đã nhận khi chưa có receipt.

### B4. Hợp đồng và vào ở · HM-07

- [ ] Tạo giữ phòng theo thỏa thuận có expiry và thử expired/release giải phóng theo policy; viewing không tạo reservation và manager/owner khác không sửa được.
- [ ] Owner/authorized manager soạn hợp đồng với phòng/participants/terms/price/fees/deposit/kỳ/thời hạn/tài liệu; renter xem và yêu cầu sửa.
- [ ] Hai bên consent đúng version; thử sửa sau một consent để chứng minh version cũ không còn đủ activate. Chỉ contract hợp lệ mới active; không gọi thao tác này là legal e-sign nếu tích hợp đó chưa có.
- [ ] Move-in checklist gồm tài sản/tình trạng/ảnh/keys/initial meters và confirmation; contract active/planned giữ allocation period nhưng chưa active tenancy/occupied. Thử hai activation và reservation giao nhau trên cùng physical_room_id, kể cả qua hai listing khác nhau: backend chỉ cho allocation hợp lệ.
- [ ] Hoàn tất move-in, tenancy active hiện trong renter overview và owner/manager đúng scope. Renter-b/owner-b không truy cập contract/document/tenant details.
- [ ] Ghi nhận khoản owner thực nhận cho rent trả trước + deposit **5.000.000 ₫** theo fixture; moving/setup **500.000 ₫** là khoản chuẩn bị của renter, không giả thành tiền owner nhận. Tiền cọc giữ riêng theo ledger.

### B5. Công tơ, hóa đơn và đối chiếu · HM-08

- [ ] Chọn một kỳ sau kỳ đã trả trước trong fixture manifest để tránh thu thuê hai lần. Chốt điện đầu 1.000/cuối 1.140 kWh, nước đầu 100/cuối 103 m³ với ảnh, đơn giá và thời điểm theo kỳ.
- [ ] Owner/authorized manager lập/chốt invoice từ server; các lines theo fixture B2 cho total **3.250.000 ₫**, lifecycle `issued`, payment_status `unpaid`, balance 3.250.000 ₫. Không dùng estimate trước thuê như invoice thực tế hoặc tính lại bằng client.
- [ ] Renter báo chuyển **2.000.000 ₫**; receipt trước xác minh là `submitted`, sau `verified/allocate` invoice payment_status `partially_paid`, lifecycle vẫn `issued`, balance **1.250.000 ₫**.
- [ ] Renter báo chuyển tiếp **1.250.000 ₫**, owner confirm/allocate/reconcile; chỉ sau đó invoice `payment_status=paid` và số dư đúng; lifecycle vẫn `issued`. Thử quá hạn còn dư nợ để thấy overdue true độc lập unpaid/partially_paid. Replay key/event không nhận tiền hai lần.
- [ ] Chạy ca khác với missing/zero/included, số cuối giảm/reset công tơ, trả thừa/nhiều lần/dispute/correction. Hóa đơn đã chốt không sửa trực tiếp; correction/reversal giữ lịch sử/reason/audit.
- [ ] Notifications invoice/due/receipt/dispute có deep link và scope. Manual recording/reconciliation hoạt động dù gateway chưa bật.

### B6. Sửa chữa, kết thúc thuê và quản trị · HM-09/07/10

- [ ] Renter tạo ticket có ảnh/priority/access time gắn tenancy active; owner/manager tiếp nhận/phân công/hẹn/xử lý/complete, renter accept hoặc reopen. Worker complete chưa tự renter accepted.
- [ ] Wrong account/tenancy không xem ticket/media; lost response không tạo duplicate; timeline/notifications và cost/responsibility theo server. Thử owner chỉ approve kỹ thuật mà chưa có payer/acceptance bên chịu tiền hoặc verified term snapshot: không được charge renter; charge hợp lệ liên kết billing một lần.
- [ ] Thử gia hạn hoặc thông báo kết thúc theo contract; move-out có tài sản/ảnh/keys/final readings/final invoice/settlement/deposit. Không tự coi thông báo kết thúc hoặc contract expired là đã trả phòng; occupied chỉ giải phóng theo move-out/policy.
- [ ] Fixture không thiệt hại/không dư nợ: hoàn deposit **2.500.000 ₫** qua record/receipt đúng quyền và reconcile số dư; ca deduction/dispute cần lý do và chứng từ riêng, deduction proposed/accepted/disputed; disputed hold chưa tự khấu trừ hoặc financial settlement settled. Closed tenancy giữ history/document và chặn action mới trái rule.
- [ ] Report/support có mã tiếp nhận và outcome; admin-scoped xử lý đúng scope; xem audit của moderation/review/consent/meter/invoice/receipt/ticket/termination.
- [ ] Renter kiểm tra privacy/export/delete/retention theo policy; dữ liệu được giữ có lý do/trạng thái, không hứa xóa mọi ledger tức thì. Export/document URLs không lộ cho actor khác.

## 4. Kịch bản phục hồi và kiểm tra UI

- [ ] Rời màn/đổi actor/scope giữa request chậm; response cũ không thay UI hoặc logout actor mới.
- [ ] Mất response review/viewing/consent/payment theo key semantics của API; đọc lại state trước hành động, không tự replay endpoint không hỗ trợ.
- [ ] Listing/profile/contract/meter/invoice sửa revision trong một phiên khác; current UI báo stale/conflict và không ghi đè silently.
- [ ] Notification delivery lỗi/retry; item/deep link không trùng, không leak nội dung sau đổi quyền.
- [ ] Restart/recovery trong pending và vận hành thuê; state/ledger/consent/history tồn tại và không bypass HITL/ownership. Phần backend/infra cần evidence riêng.
- [ ] Desktop 1440×900/1280×720, tablet 768px, mobile 360px/390×844/320px, zoom 200%; keyboard/mobile focus/form/table/map/media dùng được và không tràn trang.
- [ ] Empty/error/loading/success của từng portal không có stats/card/hóa đơn giả; console không lỗi trọng yếu; bundle/env/screenshots không secrets.

## 5. Điều kiện kết thúc demo và phát hành

Demo A đạt chỉ chứng minh subset được chạy. Demo B đạt happy path vẫn cần negative/recovery/ops evidence theo [TEST_CHECKLIST](TEST_CHECKLIST.md). P4 sản phẩm hoàn chỉnh chỉ đóng khi HM-01…HM-10 bắt buộc và UI-V tương ứng đều đạt trong môi trường phát hành, migration/backup/restore/support được kiểm chứng, docs đúng source và hạn chế được ghi thật.

Ghi kết quả từng bước: `A/B step | task/HM/UI-V | version/môi trường/provider | actor/scope | expected/actual | entity/version/receipt | pass-fail | artifact | limitation`. Không dùng video edit hoặc preview fixture để che bước chưa triển khai. Tách chất lượng matching/live AI/P5 nghiên cứu khỏi demo chức năng; optional gateway/legal e-sign/video platform/voice-image AI ghi trạng thái riêng.
