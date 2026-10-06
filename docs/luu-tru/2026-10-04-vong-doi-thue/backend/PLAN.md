# Kế hoạch Backend cho sản phẩm HomeMatch

Phiên bản 04/10/2026. Backend phải cung cấp toàn bộ **HM-01..HM-10**; luồng tìm phòng/AI đang có là nền tảng để phát triển. Đây là plan đích, không phải báo cáo hoàn thành. [Plan chi tiết](DETAILED_PLAN.md), [kiến trúc](../docs/kien-truc-homematch.md), [yêu cầu](../docs/yeu-cau-san-pham.md), [AC sản phẩm](../docs/tieu-chi-nghiem-thu.md) và [API v1 thiết kế](../docs/api-san-pham-v1.md) dùng chung IDs HM.

## 1. Nền tảng hiện tại

API [0.3.0](../docs/api-contract.md) có seed auth/token, renter/manager, draft/confirm/CAS, catalog import/read/status revision, deterministic cost/B1/P adapter, HITL, compare, viewing requested/confirmed/declined, ticket hỗ trợ nội bộ, SQL ledger/checkpoint SQLite/PG, health/readiness và metric process. Migration schema v2. [Báo cáo backend](../docs/kiem-chung-backend.md) ghi các kiểm chứng thực tế; không dùng fixture để kết luận live AI hoặc production.

Cập nhật 04/10/2026 (API `0.4.0`, schema v3): W-01 đã có mã — bốn vai trò renter/owner/manager/admin, ma trận quyền duy nhất ở `app/capabilities.py`, domain organization/membership/ownership và audit log; W-02 đã có mã — migration v3 và projection công khai allowlist ở `app/projection.py`; W-03 đã có mã — register/verify/reset, profile/consent, session revoke với stub email ghi log. HM-01 còn thiếu: rate limit auth, thu hồi token khi disable account, media/job/export permission. HM-02 trở đi chưa có mã.

Chưa có owner portal CRUD/moderation, public discovery, favorites/history đồng bộ, worker/outbox, tenancy/contracts, meters/invoices/reconciliation, maintenance hoặc privacy lifecycle. API snapshot/OpenAPI đã nâng lên 0.4.0 kèm endpoint mới; API đích chỉ là thiết kế cho đến có mã và checks.

## 2. Ranh giới

Backend sở hữu quyền, validation, transaction/state/CAS/idempotency, engine tài chính/ranking và DTO. Agent sở hữu extraction/routing/prompt/graph; không viết SQL, cấp quyền, tính tiền hay tự công bố. Data cung cấp fixtures/evidence/oracles độc lập, Eval giữ protocol/labels/metrics, Infra giữ môi trường/release/restore.

PostgreSQL là đích production, SQLite cho offline. Giữ một API worker đến audit concurrency/checkpointer; worker notification/IO là thành phần đích cần làm. Listing moderation và recommendation approval là hai quyết định khác nhau.

## 3. Đầu việc theo module

| ID | Công việc Backend bắt buộc | Phụ thuộc/gate | Hoàn thành khi |
|---|---|---|---|
| HM-01 | Account lifecycle; role renter/owner/manager/admin; organization/membership/assignment; session revoke, permission matrix | P0 → P1; HM-10 từ đầu | Positive/negative API và media/job/export quyền đạt; truy chéo đơn vị bị chặn |
| HM-02 | Property/room/listing CRUD, fee/evidence/version, media private, submission/moderation, availability | HM-01/10 → P1 | Owner quản lý đúng phạm vi; public chỉ projection published; sửa revision/invalidation có audit |
| HM-03 | Public filters/sort/pagination/detail/map contract; location uncertainty, nguồn/cost | HM-02 → P2 | Query/detail không nháp; filter có unknown policy; public mode không có approval AI |
| HM-04 | Hoàn thiện profile/finance/matching/HITL, quotas/provider errors, snapshot/validity/recovery | HM-01/02/03 → P2 | Pending không lộ; total/unknown đúng; manager assignment/CAS/replay/restart đạt |
| HM-05 | Favorites/history/preferences retention, public/AI compare theo mode | HM-03/04 → P2 | Đồng bộ account; xóa đúng phạm vi; compare 2–3 cùng scenario, stale rõ |
| HM-06 | Viewing lifecycle, handoff acceptance/assignment, notifications/outbox/worker contracts | HM-01..05 → P2; thuê events P3 | Requested không giữ phòng; cancel/reschedule/completed/no_show có event; retry không trùng |
| HM-07 | Agreements/reservation expiry, contract versions/acceptances, tenancy/occupants, move-in/out | HM-02/06 → P3 | Hai bên acceptance cùng terms; allocation contract chống kỳ chồng, tenancy active sau move-in; không thuê chồng; closing có đối chiếu |
| HM-08 | Meters/readings/tariffs, invoice engine/snapshot, manual payments/evidence/receipt/allocation/reconcile | HM-07 → P3 | Estimate khác bill; exact VND; partial/duplicate/dispute/adjustment có audit |
| HM-09 | Maintenance ticket/media/triage/appointment/progress/confirm/reopen theo tenancy | HM-07/06 → P3 | Tenant đúng quyền; lifecycle/ảnh/notification có evidence; chi phí không tự thành invoice |
| HM-10 | Admin/moderation, audit/privacy/retention/export/delete, rate limits, durable metrics/ops | Cắt ngang P0..P4 | Audit đủ actor/version/reason; không PII raw; restore/rollback/runbook đạt |

Không hoàn thành HM-07..09 bằng màn hình trống hoặc mocks. Cổng thanh toán thật, e-sign pháp lý, nền tảng video, voice/image AI và toàn quốc tùy chọn; manual billing/reconcile và contract records/consent bắt buộc.

## 4. Thứ tự và gates

P0 khóa domain/state/role/DTO, API 0.3.0 và v1 riêng, migration/version/privacy rules. P1 accounts/catalog/media/admin nền. P2 public discovery + AI + saved/history/compare + viewing/handoff/notifications. P3 contract/move-in → meters/invoices/reconcile và maintenance → move-out. P4 đủ 10 module, bốn-role E2E, negative permissions, deployment/restore/rollback và vận hành có bằng chứng. P5 là nghiên cứu riêng theo Eval; kết quả cải thiện ranking không được hứa trước.

Tách transaction theo aggregate; outbox cùng commit, worker at-least-once có dedup/lease/retry. Mọi financial/publication/state mutation đi qua service xác định; model output không ghi DB trực tiếp.

## 5. Definition of done và bàn giao

Mỗi module xong khi có schema/migration/DTO có version, đường đúng và ca âm/biên có checks phù hợp, permission/media/job isolation, CAS/replay/concurrency ở cấu hình cho phép, UI integration thực, audit/privacy và hướng dẫn vận hành. Số tests lịch sử không thay evidence theo module.

Bàn giao OpenAPI phiên bản đã thực thi, migration/rollback notes, fixtures, ma trận quyền, state/error dictionary, E2E và crash/restart reports. ID BE-01..12/AG-01..09, AC01..16 và checklist 62 cũ là lịch sử của prototype; nguồn phạm vi hiện tại là HM và gates P0..P4.

