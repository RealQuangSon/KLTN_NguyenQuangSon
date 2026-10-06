# Kế hoạch triển khai sản phẩm HomeMatch hoàn thiện

**Cập nhật:** 04/10/2026. Phạm vi theo [đặc tả v1](dac-ta-san-pham.md) và [30 yêu cầu](yeu-cau-san-pham.md). Giới hạn MVP/6 tuần, T01–T15 và các gate G1–G6 trước đây không còn quyết định phạm vi bản hoàn thiện. Tài liệu này đưa thứ tự phụ thuộc, không tự áp một thời hạn mới.

## 1. Hướng triển khai

Tái sử dụng React/FastAPI/finance/graphs/auth/SQLite-PG từ 0.3.0; mở rộng domain, quyền và trải nghiệm từng module. Mỗi lát phải có API+DB+UI+quyền+trạng thái+audit+ca kiểm, không giao một portal toàn nút chưa hoạt động.

Các gate P0–P4 theo [bộ nghiệm thu](tieu-chi-nghiem-thu.md); P5 riêng cho khóa luận. HM-10 làm từ đầu. HM-01/02 là nền, HM-03/04/05/06 phục vụ lựa chọn và lịch, HM-07 mở quan hệ thuê, HM-08/09 phục vụ vận hành. Notification của HM-06 dùng lại cho 07–09.

## 2. Backlog cấp sản phẩm

| Task | Kết quả phải xây | Yêu cầu/đầu vào | Điều kiện bàn giao |
|---|---|---|---|
| W-01 | Khóa glossary, roles/capabilities, organization, scope, trạng thái, DTO/errors/retry và nguồn dữ liệu | Tất cả HM; docs/research/code 0.3.0 | P0 review, target OpenAPI và matrix không mâu thuẫn |
| W-02 | Migration organization/membership/ownership/audit và tách public/private projection | HM-01/10, W-01 | Không cross-unit/user; dữ liệu demo cũ migrate được |
| W-03 | Registration/verification/reset/profile/consent/session revoke | HM-01, W-02; email provider ở integration | API+UI và các ca token/reset/isolation đạt |
| W-04 | Owner portal building/room/fee/media, source register | HM-02, W-02 | CRUD/CAS/media access/validation; ảnh có quyền |
| W-05 | Moderation/public snapshots/availability/reservation schema | HM-02/10, W-04 | Publish stale bị chặn; room history nguyên; P1 |
| W-06 | Public catalog/detail/filter/map/report | HM-03, W-05; map/geocoding source | Projection đúng quyền, unknown/distance/fallback; browser mobile |
| W-07 | Chat intent/draft/confirm/cost/ranking/provider và review hiện tại thành flow v1 | HM-04, W-01/02/05 | Finance oracle, fallback rõ, pending hidden, live integration theo cấu hình release |
| W-08 | Favorites/saved search/account history/compare hai mode | HM-05, W-03/06/07 | Persistence tài khoản, stale/consent đúng; không mixed compare |
| W-09 | Lịch slot/cancel/reschedule/completed/no_show và support vòng đời | HM-06, W-06/07 | Assignment/slot/revision/key đúng, viewing không giữ phòng |
| W-10 | Outbox/in-app/email/failed delivery queue | HM-06/10, W-02/03 | Crash/retry/dedup; business state độc lập delivery; P2 |
| W-11 | Contracts/terms/documents/version/acceptance/activation | HM-07, W-04/09 | Acceptance stale bị chặn; private docs và audit |
| W-12 | Tenancy/reservation/bàn giao vào-ra/sổ cọc/gia hạn/chấm dứt | HM-07, W-11 | Chặn overlap trong transaction; ledger cọc/correction/expiry |
| W-13 | Meter/rate/reading verification và correction/replacement | HM-08, W-12 | Measured khác estimate, rate theo kỳ, evidence private |
| W-14 | Invoice issue/adjust/advance rent/receivable/evidence/receipt/allocation/refund/dispute | HM-08, W-12/13 | Oracle billing/replay/balance đúng, issued bất biến |
| W-15 | Maintenance triage/assignment/schedule/cost approval/resolve/reopen/billing link | HM-09, W-12/14 | Tenant scope, chỉ một charge event, lịch sử/bằng chứng |
| W-16 | Admin/manager dashboard/queues/audit/privacy retention/export/delete | HM-10, W-02 và từng module | Số liệu thật có scope; consent/file/log/retention negative cases; P3 với W-11..15 |
| W-17 | Browser E2E/load/deploy/migration/rollback/backup-restore/alert/runbook/training | Tất cả HM/NFR, W-03..16 | Tất cả AC, NFR, ba E2E và điều kiện vận hành P4 |
| W-18 | Freeze/independent labels/paired metrics/user study có protocol/report/slide/video | P5, phương pháp/config/data đã khóa | Không tune test; raw evidence và giới hạn, không hứa P phải thắng |

## 3. Phụ thuộc và việc có thể song song

Sau W-01, FE có thể làm router/workspace và mock theo contract; backend làm W-02/03, data chuẩn hóa catalog/oracles, infra dựng staging/storage/email/observability. W-04/05 và W-07 có thể triển khai đồng thời trên schemas đã khóa. W-11/12 cần quyền/phòng/terms nhưng không chờ benchmark nghiên cứu; W-13/14 và W-15 dùng chung tenancy snapshots.

Research dev tiếp tục cùng sản phẩm. Test set nghiên cứu chỉ dùng sau freeze. Điểm nDCG chưa có không chặn viết billing hoặc làm browser QA. Thiếu provider ngoài không được che bằng màn success giả; ghi dependency và dùng sandbox/fake có nhãn cho development đến khi integration thực sẵn sàng.

## 4. Điều kiện ở từng lần giao

- Cập nhật requirement/AC/API/schema/UI spec khi hành vi thay đổi.
- Chạy kiểm phù hợp: quyền/finance/state/replay/concurrency ở backend; tương tác/stale/error ở UI; browser API thật tại integration; restore/load tại release.
- Lưu evidence theo release/data/config và cập nhật [trạng thái thực tế](trang-thai-trien-khai.md), không đánh dấu từ plan.
- Dùng data synthetic cho dev/test, catalog có quyền cho vận hành; media/chats/checkpoints/secrets không vào gói public.
- Cần đầu vào về inventory/provider/chính sách/nhân sự ở gate tương ứng; không suy ra đã có quyền tích hợp từ nghiên cứu HubHome.

## 5. Điểm bắt đầu từ mã hiện tại

Ưu tiên W-01 và W-02: migration bốn vai trò/đơn vị và public/private projection là nền của owner, catalog, lease và billing. Giữ flow confirm→review→publish đã có làm regression. Đồng thời FE chuẩn bị navigation và screen inventory; data tạo fixtures/oracle sau thuê; infra chuẩn bị storage/outbox/backup staging. Không cần viết lại finance hoặc bỏ kiểm duyệt để có public search.
