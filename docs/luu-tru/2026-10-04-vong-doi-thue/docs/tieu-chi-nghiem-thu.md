# Tiêu chí nghiệm thu sản phẩm HomeMatch v1

**Ngày:** 04/10/2026. Đây là điều kiện hoàn thành cần kiểm chứng, không phải checklist đã đạt. Phạm vi bắt buộc theo [30 yêu cầu](yeu-cau-san-pham.md), [quy trình](quy-trinh-nghiep-vu.md) và [UI spec](../frontend/UI_SPEC.md).

## 1. Quy tắc kết luận

Chỉ gọi sản phẩm v1 hoàn thiện khi cả HM-01–HM-10, NFR và cổng P4 có bằng chứng đạt trên cùng release candidate. Không dùng số lượng test, màn hình hoặc task đã đóng để thay kết quả E2E. Một lỗi quyền, lộ dữ liệu, sai tiền, thuê trùng hoặc công bố nháp là lỗi chặn phát hành.

Bằng chứng mỗi ca gồm: release/config/schema version, dữ liệu và actor fixture, thao tác, expected/actual, thời điểm, ảnh hoặc API/DB assertions phù hợp và người kiểm. Trạng thái cho phép: `not_run`, `passed`, `failed`, `blocked`; blocked phải có thiếu đầu vào cụ thể và người phụ trách. Chưa có ca nào được đánh dấu passed trong tài liệu này.

## 2. Ca nghiệm thu theo yêu cầu

| AC | Kịch bản cần chạy | Kết quả bắt buộc |
|---|---|---|
| AC-HM-01-01 | Đăng ký/xác minh; đăng nhập sai; logout; reset token hết hạn/dùng lại; đổi mật khẩu | Tài khoản chỉ active khi đúng policy; lỗi không tiết lộ tồn tại; token reset một lần; phiên bị thu hồi không truy cập được |
| AC-HM-01-02 | Sửa hồ sơ; từ chối ghi nhớ; đăng nhập thiết bị khác; export/delete request có ledger còn hiệu lực | Lựa chọn lưu có hiệu lực server; không khôi phục dữ liệu không consent; export chỉ của mình; delete có trạng thái/retention và giải thích khoản phải giữ |
| AC-HM-01-03 | Renter B, owner đơn vị B và manager không assigned đoán ID của A; client sửa role/organization | API/file/export đều chặn; không lộ metadata private; thay role từ client không có tác dụng; audit phân công đúng |
| AC-HM-02-01 | Tạo/sửa room với phí null/0/included, ảnh sai loại/quá giới hạn, thiếu nguồn hoặc tọa độ chưa rõ | Validation cụ thể; null khác 0; media private trước publish; metadata nguồn và độ chính xác được giữ; room nằm đúng đơn vị |
| AC-HM-02-02 | Gửi duyệt revision r1, sửa r2 khi manager đang xem r1; publish rồi đổi giá; suspension | Review r1 stale bị chặn; không public r2 chưa duyệt; bản cũ không còn đúng được ẩn; suspension thu hồi projection và invalidates run |
| AC-HM-02-03 | Requested viewing; hai reservation cùng kỳ; reservation expiry/conversion; hai listing cùng phòng thực activate đồng thời; expired contract còn người ở | Viewing không giữ phòng; một allocation cùng kỳ; conversion atomic; chỉ một activation hợp lệ theo physical room; expired không tự available; history giữ nguyên |
| AC-HM-03-01 | Cùng bộ lọc qua UI/API; ngân sách rent vs total; unknown fee; pagination/sort tie | Kết quả đúng published/availability và constraint; total thiếu không được coi đạt trần; page/sort ổn định, không trả tin nháp |
| AC-HM-03-02 | Đổi filters ở list/map; mở detail; location approximate; map service lỗi | Cùng tập ID/revision; nhãn sai số/cách đo rõ; không lộ exact private; fallback list dùng được, không mất filters |
| AC-HM-03-03 | Mở detail public/authorized; đổi scenario; report tin stale | Public/private đúng quyền; breakdown và unknown đổi đúng scenario; report tạo ticket cho đúng room revision, không gửi form ra ngoài trái phép |
| AC-HM-04-01 | Tin nhắn tìm phòng thiếu city/budget; yêu cầu chỉ tính phí; yêu cầu người thật; sửa draft rồi confirm | Route intent đúng; không matching cho cost-only; inferred chưa thành confirmed; thiếu trường được hỏi; confirm tạo đúng version/run |
| AC-HM-04-02 | Cùng profile/catalog qua B1/P; unknown amenity/fee; provider timeout; yêu cầu không có match | Eligible set đúng; oracle phí chính xác; reasons truy evidence; fallback ghi B1; lỗi provider không bị báo no_match |
| AC-HM-04-03 | Renter đọc pending; sai manager review; double review/key; crash sau decision; catalog/profile đổi trước finalize | Pending không có candidates; sai quyền/stale bị chặn; replay không double publish; reviewed chưa visible; finalize/reads kiểm version |
| AC-HM-05-01 | Favorite/save search trên thiết bị A rồi mở B; tin unavailable/archived; user khác đọc | Đúng tài khoản; persistence server; trạng thái mới rõ; không hiển thị bản lưu như phòng còn thuê được; không cross-user |
| AC-HM-05-02 | Tiếp tục phiên theo consent; mở run lịch sử đã invalidated; logout/login tài khoản khác | Lịch sử đúng quyền; không làm live run cũ; không phục hồi chat của actor trước; retention/consent có tác dụng |
| AC-HM-05-03 | Compare 2/3 ID; lặp ID/4 ID/mixed mode; cùng scenario; quote đổi giữa thao tác | Hợp lệ trả phí/diện tích/location/tradeoff/unknown cùng basis; invalid/stale bị chặn; không lộ pending AI |
| AC-HM-06-01 | Gửi lịch tương lai/timezone; confirm slot; hai confirm trùng; reschedule/cancel; room unavailable | requested khác confirmed; conflict có thông điệp; đổi lịch cần xác nhận mới; audit/notification đúng, không tạo reservation |
| AC-HM-06-02 | Completed/no_show; ticket hỗ trợ assigned/resolved/reopen; owner xem phiên không liên quan | Luồng trạng thái đúng; kết quả có actor/time; ticket quay lại người phụ trách; owner chỉ thấy projection lịch được phép |
| AC-HM-06-03 | Crash sau commit trước gửi; gửi thất bại rồi retry; replay event; địa chỉ email không còn hợp lệ | Nghiệp vụ đã commit vẫn đúng; notification dedup; failed hiển thị queue; recipient/link đúng quyền, không gửi tài liệu private trong mail |
| AC-HM-07-01 | Renter accept v1, owner sửa v2; owner/renter accept khác version; tải file không liên quan | Hợp đồng chưa active; chấp thuận bản cũ hết hiệu lực; chỉ activation cùng bản đủ hai bên; file private bị chặn |
| AC-HM-07-02 | Activate/move-in replay; thiếu acceptance; kỳ thuê giao nhau; planned chưa bàn giao | Thiếu điều kiện bị chặn; đúng một hợp đồng/tenancy; rent/cọc/đầu công tơ snapshot đúng; planned không tự occupied trước policy |
| AC-HM-07-03 | Gia hạn/kết thúc; owner đề xuất khấu trừ thiếu acceptance; hoàn cọc; disputed hold; public lại tin | Không khấu trừ đơn phương chỉ từ proposal/dispute; nhận cọc=hoàn+khấu trừ hợp lệ+còn giữ; evidence/reversal đủ; closed/công nợ rõ; không tự public tin suspended |
| AC-HM-08-01 | Chỉ số cuối thấp hơn đầu; meter replacement thiếu/đủ old-last/new-first; estimated reading; rate đổi giữa kỳ có/không amendment+boundary | Reject sai; missing segment unknown; replacement sum delta đúng; default rate đầu kỳ, đổi áp kỳ sau; chia đoạn chỉ có acceptance+số đo; issued giữ nguyên |
| AC-HM-08-02 | Invoice có điện/nước/per-person/included/null, thuê trả trước, rounding; issued sửa/void/adjust | Oracle đúng VND; không cộng trước thuê hai lần; missing chặn issued theo policy; sửa issued dùng adjustment, không overwrite |
| AC-HM-08-03 | Evidence uploaded; receipt verified một phần trước/sau due_at/trùng key; overpayment/refund/rejected/disputed | Uploaded chưa paid; issued+partially_paid+overdue đồng thời đúng; balance/allocations không trùng; verified receipts=allocated+unallocated+refunded hợp lệ; dispute không xóa nợ |
| AC-HM-09-01 | Renter tạo ticket/ảnh cho tenancy của mình, đoán tenancy khác; chọn urgent | Đúng quyền; ảnh private; urgent hiển thị kênh người phụ trách và giờ phục vụ, không hứa phản hồi chưa được vận hành |
| AC-HM-09-02 | Triage/assign/schedule; owner duyệt kỹ thuật rồi charge renter thiếu payer acceptance/verified terms; disputed cost; sai manager | Transition/capability đúng; không charge từ technical approval/dispute; payer/terms/acceptance version có audit và notification |
| AC-HM-09-03 | Resolved thiếu evidence; renter close/reopen; replay charge-to-invoice | Yêu cầu evidence; reopen có lý do về triaged; cùng cost event chỉ một dòng charge; lịch sử sửa chữa không mất |
| AC-HM-10-01 | Chuyển assignment; dashboard qua đơn vị A/B; khóa tài khoản còn token | Người cũ mất quyền theo policy; số liệu scope đúng, không lộ PII; tài khoản bị khóa không dùng token cũ; audit đủ |
| AC-HM-10-02 | Audit các mutation; export/delete/restrict; file URL hết hạn; log/embedding sample | Audit có actor/ref/version không raw chat; export không cross-user; retention chạy theo policy; link hết hạn bị chặn; không secret/PII ngoài phạm vi |
| AC-HM-10-03 | Deploy/migration/rollback; ledger+media backup/restore; restart API/worker; queue dead-letter | Smoke/browser chạy trên release; restore balance/quyền/checkpoint/media đúng; retry không nhân bản; runbook có người xử lý và bằng chứng RPO/RTO |

## 3. Ba hành trình E2E bắt buộc

1. **Từ nguồn phòng tới lịch xem:** owner tạo room/media/fee → manager duyệt → guest lọc/map → renter xác nhận hồ sơ → AI tạo nháp hidden → manager duyệt → renter favorite/compare → requested viewing → manager confirm → completed. Kiểm thêm stale/reject/no_match/provider down.
2. **Từ xem phòng tới kỳ thu đầu tiên:** chốt điều khoản → hai bên accept cùng version → activation → move-in/cọc/chỉ số đầu → chỉ số cuối → issued invoice → evidence → verified receipt/partial allocation → paid. Kiểm thêm acceptance stale, thuê trùng, missing reading và replay receipt.
3. **Từ vận hành tới trả phòng:** maintenance triage → cost approval → resolved/reopen/close → invoice cost event → termination/move-out → final invoice/deposit/refund/dispute → closed → room được kiểm tra lại trước công bố. Kiểm access của các bên không liên quan và notification sau restart.

Chạy trên browser thật ở bốn vai trò bằng tài khoản/đơn vị riêng; kiểm desktop/mobile/keyboard. Mock UI và in-process smoke là kiểm lớp thành phần, không thay E2E. Dữ liệu nghiệm thu synthetic được ghi nhãn; nghiệm thu public operation thêm inventory được phép dùng và người vận hành thực.

## 4. Cổng hoàn thành

| Cổng | Điều kiện đóng | Bằng chứng cần lưu |
|---|---|---|
| P0 Contract | Scope HM, glossary, quyền, state machines, DTO/errors/version/idempotency, nguồn dữ liệu thống nhất | Docs review, API v1 schema/mock và quyết định còn mở có owner |
| P1 Accounts/catalog | HM-01/02 và nền HM-10 chạy API+UI, private media, moderation/CAS/isolation | Integration/negative tests và browser tạo/duyệt tin |
| P2 Discovery/AI | HM-03/04/05/06, public khác AI, profile/cost/review/history/notification hoạt động | E2E 1; oracle; live provider theo cấu hình release nếu quảng bá chức năng AI; fallback/fault cases |
| P3 Rental operations | HM-07/08/09, sổ cọc/rate/meter/invoice/receipt/reopen với transaction và audit | E2E 2–3, billing oracle và race/replay tests |
| P4 Release hoàn thiện | Tất cả AC/NFR bắt buộc đạt; không còn lỗi chặn; deploy/restore/load/privacy/moderation/support có chủ trách nhiệm | Release manifest mới, báo cáo QA, runbook, diễn tập, bộ hướng dẫn và bộ dữ liệu hợp lệ |
| P5 Research | Freeze input trước test, nhãn người thật khóa, paired metrics/error analysis và giới hạn công bố | Raw runs/config/hashes/judgments/report; tách với nghiệm thu sản phẩm |

P5 là cổng bàn giao nghiên cứu KLTN, không phải điều kiện máy móc rằng P phải thắng B1. Kết quả không cải thiện vẫn phải báo trung thực. Hoàn tất P5 không thay P4; hoàn tất P4 không tự chứng minh điểm chất lượng/hài lòng.

## 5. Definition of done cho một yêu cầu

- Hành vi/quyền/trạng thái/API và UI được triển khai đủ, có xử lý lỗi/loading/empty/stale và tiếp tục công việc.
- Test tập trung vào hành vi và các rủi ro tương ứng đã chạy, kết quả truy được release/data/config; UI thay đổi có browser QA.
- Có audit/notification/retention đúng phạm vi; migration dữ liệu và retry không mất hoặc nhân bản nghĩa vụ.
- Hướng dẫn sử dụng/vận hành và contract đã cập nhật; không để module sau thuê là màn minh họa.
- Không còn lỗi chặn liên quan yêu cầu; ngoại lệ được ghi cụ thể, không đổi status passed để bỏ qua thiếu đầu vào.
