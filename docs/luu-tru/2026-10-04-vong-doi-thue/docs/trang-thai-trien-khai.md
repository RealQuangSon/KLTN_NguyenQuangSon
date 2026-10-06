# Trạng thái sản phẩm HomeMatch

**Cập nhật tài liệu:** 04/10/2026. **Định hướng hiện hành:** sản phẩm v1 hoàn thiện theo [đặc tả](dac-ta-san-pham.md). **Mã hiện có:** nền tảng local 0.3.0. Lần viết lại docs không thay đổi mã ứng dụng, chạy lại test chức năng hoặc tạo deployment.

## Nền tảng và khoảng cách tới v1

| Module | Mã/nền tảng hiện có | Phần chưa hoàn thiện theo v1 |
|---|---|---|
| HM-01 | Renter/manager seed, scrypt password, random token expiry/revoke, ownership/assignment | Signup/verify/reset/profile/consent, owner/admin/membership/cách ly đơn vị |
| HM-02 | 80 rooms synthetic, import merge, catalog read/status toggle/revisions | Owner CRUD/building/media/source quyền thật, moderation snapshots và availability/reservation đầy đủ |
| HM-03 | Candidate details từ run được duyệt và filters khi matching | Public search/detail/map, real media/location projection/report tin |
| HM-04 | Chat/recommendation graphs, draft/confirm, cost/B1, P/live adapters, review ledger/retry/version/CAS | Live provider/quality theo cấu hình release, đầy đủ integration v1 và projection roles mới |
| HM-05 | Compare 2–3 từ published run; session ID trong browser | Account favorites/saved searches/history/consent, public compare mode |
| HM-06 | Requested→confirmed/declined; support ticket nội bộ | Slots/cancel/reschedule/result, support lifecycle/UI, outbox/in-app/email/recovery |
| HM-07 | Chưa có contract/tenancy domain | Terms/acceptances/documents/activation/reservation/move-in/out/deposit ledger |
| HM-08 | Pure cost estimate | Meter/rate periods/invoices/receipt allocation/adjustments/refund/dispute/receivables |
| HM-09 | Chưa có maintenance domain | Report/triage/assign/schedule/cost approval/resolve/reopen/billing link |
| HM-10 | Readiness, process metrics, log giảm dữ liệu, local scripts | Admin portal/queues/organization audit/privacy retention, release ops/load/restore thực |

## Bằng chứng lịch sử

[Báo cáo backend 0.3.0](kiem-chung-backend.md) ngày 01/10 ghi 121 Python tests (104 backend + 17 eval), 15 UI tests, TypeScript/build và HTTP thật trên SQLite/PostgreSQL. [Báo cáo MVP](kiem-chung-mvp.md) và [scaffold](kiem-chung-scaffold.md) giữ các phạm vi trước đó. Các cập nhật landing/UI sau này có fixture tests riêng; không cộng số khác ngày/config thành một suite mới đã chạy trong lần này.

Fake providers/vector fixtures không chứng minh GPT/embedding thật. Test backend hoặc fixture UI không tự chứng minh browser integration, restore, Docker hay cloud. [README frontend](../frontend/README.md) giữ bằng chứng browser/UI của đợt 02/10 trong phạm vi đã ghi. Live GPT/P quality, relevance labels độc lập và user satisfaction chưa có kết quả nghiên cứu hợp lệ.

[Release manifest](release-manifest.json) là snapshot tạo 01/10/2026, không đại diện cho docs/source sau lần viết lại 04/10. Không cập nhật hashes cũ để giả một release đã nghiệm thu; khi phát hành cần tạo manifest mới cùng kết quả mới.

## Trạng thái các gate

| Gate | Trạng thái | Lý do |
|---|---|---|
| P0 contract v1 | Có bộ đặc tả; chờ khóa implementation schema/DTO | Product/process/AC/API target/plans đã viết; OpenAPI v1 thực thi và migration chưa có |
| P1 accounts/catalog | Chưa đạt | Owner/admin/isolation/signup/reset/moderation/media chưa có |
| P2 discovery/AI | Chưa đạt | Có core AI HITL local; thiếu public/map/history/favorites/full viewing/notification và live evidence release |
| P3 rental operations | Chưa đạt | Contracts/tenancy/billing/meters/maintenance chưa có |
| P4 release hoàn thiện | Chưa đạt | Không có đủ toàn bộ AC/NFR/E2E và điều kiện vận hành |
| P5 research | Chưa đạt | Thiếu freeze nghiên cứu/live runs theo phương pháp, independent relevance labels và kết luận thực |

## Việc tiếp theo

W-01/W-02 trong [backlog](ke-hoach-trien-khai.md): khóa contract v1, migration organization/roles và permission/projection. Sau đó làm accounts/catalog và mở public discovery, giữ regression cost/HITL hiện tại. Docs có thể dùng để triển khai; trạng thái sản phẩm chỉ đổi khi có code và evidence tương ứng.

Nguồn inventory/media, email/map/storage provider, người vận hành, policy hợp đồng/riêng tư và đầu vào nghiên cứu nằm tại [assumptions](dac-ta-san-pham.md). Thiếu một đầu vào không được đánh dấu chức năng đã chạy; ghi blocker ở gate cần nó và tiếp tục việc độc lập.
