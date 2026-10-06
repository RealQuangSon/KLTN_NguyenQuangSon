# Kế hoạch frontend HomeMatch — sản phẩm toàn vòng đời thuê

**Cập nhật 04/10/2026.** Đích hoàn thành là sản phẩm có bốn vai trò renter/owner/manager/admin và đủ HM-01…HM-10. Luồng tìm phòng hiện có là nền tảng phát triển; các màn sau thuê là phần bắt buộc của sản phẩm. Không dùng điều kiện hoàn tất bản tìm phòng để đánh dấu sản phẩm hoàn chỉnh.

Đọc cùng [UI_SPEC](UI_SPEC.md), [kế hoạch chi tiết](DETAILED_PLAN.md), [thiết kế](../DESIGN.md), [đặc tả sản phẩm](../docs/dac-ta-san-pham.md), [yêu cầu](../docs/yeu-cau-san-pham.md), [nghiệm thu](../docs/tieu-chi-nghiem-thu.md) và [API v1 mục tiêu](../docs/api-san-pham-v1.md). FE-01…FE-10 giữ mã truy vết cũ nhưng mở rộng phạm vi; FE-11…FE-18 bổ sung công việc sản phẩm đầy đủ. Không ấn định số giờ/tuần khi chưa có năng lực và dependencies được kiểm chứng.

## 1. Hiện trạng và đích phát hành

Source React/TypeScript hiện có landing/login, renter search/viewings, manager review/catalog/viewings, API client và các kiểm soát pending/null/0/stale/CAS/key. API backend hiện tại 0.3.0, role chỉ renter/manager, navigation là state tab. Chưa có route/deep link, owner/admin, public discovery/map/media, favorites/saved searches/account history/notifications hoặc hợp đồng/công tơ/hóa đơn/sửa chữa. Theme cam đỏ/nền ngà và landing hai cột chưa theo token/layout mục tiêu.

Bằng chứng ngày 02/10 trong [TEST_CHECKLIST](TEST_CHECKLIST.md) là baseline của source cũ; fixtures và [preview độc lập](design/hubhome-preview.html) không chứng minh target đã được triển khai. Mọi task dưới đây là việc cần thực hiện/kiểm chứng, không tự nhận hoàn tất từ việc viết lại docs.

## 2. Phạm vi và dependencies

| ID | Đầu ra mục tiêu | Module | Phụ thuộc chính | Gate |
|---|---|---|---|---|
| FE-01 | Contract/state/role/screen coverage, register tham chiếu và fixtures | Tất cả | Product spec, API current/target, nguồn nghiên cứu | P0 |
| FE-02 | Token, landing, router/deep link và shell bốn vai trò | HM-01/03/10 | FE-01, auth/role/scope | P1 |
| FE-03 | Assistant chat–preview, draft/filter/form/confirm và progress | HM-04 | FE-02, session/profile/run APIs | P2 |
| FE-04 | Listing moderation và recommendation HITL tách biệt | HM-02/04 | FE-02/06, moderation/review/assignment | P1/P2 |
| FE-05 | Public discovery/list/detail và gợi ý/chi phí theo projection | HM-03/04 | FE-02/06/11, search/results/cost APIs | P2 |
| FE-06 | Owner CRUD nhà/phòng/quote/availability và quản lý kho | HM-02 | FE-02/18, inventory/revision/permissions | P1 |
| FE-07 | Renter overview, nhu cầu, chuyển tìm/đang thuê và điều hướng lifecycle | HM-04/05/07 | FE-03/12/13/14, overview APIs | P2/P3 |
| FE-08 | State/errors/stale/retry/cache isolation trên mọi màn | Tất cả | Error/version/idempotency contract | Xuyên suốt |
| FE-09 | Visual QA, responsive, keyboard và accessibility | Tất cả | UI_SPEC, từng screen/flow đã tích hợp | Xuyên suốt/P4 |
| FE-10 | E2E bốn vai trò, demo toàn lifecycle và release evidence | Tất cả | Các module bắt buộc đạt; API/deployment readiness | P4 |
| FE-11 | Media upload/gallery/tour và map/list/location precision | HM-02/03/06 | Media/location/storage/provider contracts | P1/P2 |
| FE-12 | Favorites/saved searches/viewed/session history và compare public/AI | HM-05 | FE-03/05, account persistence/compare APIs | P2 |
| FE-13 | Viewing đầy đủ, handoff và notifications in-app | HM-06 | FE-05/12, slot/assignment/outbox APIs | P2, mở rộng P3 |
| FE-14 | Reservation/contract/consent/tenancy/move-in/out và gia hạn/kết thúc | HM-07 | FE-06/13, contract/tenancy/handover APIs | P3 |
| FE-15 | Meters/invoices/payment recording/reconciliation/dispute | HM-08 | FE-14, deterministic billing/ledger APIs | P3 |
| FE-16 | Maintenance tạo/xử lý/accept/reopen, media/timeline | HM-09 | FE-11/13/14, maintenance APIs | P3 |
| FE-17 | Admin/assignment/support/report/privacy/audit/ops | HM-01/10 | FE-01/02, RBAC/audit/privacy/ops APIs | P0→P4 |
| FE-18 | Registration/verification/recovery/profile/security sessions | HM-01 | Auth threat model, account/email/session APIs | P1 |

Shared token/component/API client tái dùng được; agent logic, tiền, quyền và publication vẫn ở backend. Mock/fixture chỉ nằm trong test/preview, không làm runtime fallback của tính năng sản phẩm.

## 3. Các gate thực hiện

| Gate | Phạm vi và điều kiện ra | Không được suy ra |
|---|---|---|
| P0 — contract | Chốt role/scope, HM modules, entities/state transitions, current vs v1, DTO/errors/keys, screen coverage và dữ liệu được phép | Docs đã đầy đủ không có nghĩa source hoặc security đã đạt |
| P1 — accounts/catalog | Tài khoản bốn role; owner inventory/media; moderation; admin assignment/audit; stale/ownership; UI có route thật | Tin approved không có nghĩa AI recommendation approved |
| P2 — discovery/AI | Public search/map/detail/save/history/compare; AI draft/confirm/HITL; lịch/handoff/notification nền tảng; browser các role | Luồng trước thuê đạt chưa là sản phẩm toàn vòng đời hoàn tất |
| P3 — rental operations | Contract/consent + move-in/out; công tơ/hóa đơn/ghi nhận/đối chiếu; sửa chữa; notifications liên quan; negative/correction flows | UI biểu mẫu trống hoặc demo happy path không chứng minh ledger/quyền/recovery |
| P4 — release | HM-01…HM-10 bắt buộc đều đạt API/browser/security/mobile/keyboard; migration/backup/restore/ops/support evidence; docs đúng source | Local fixtures không thay kiểm chứng môi trường phát hành |
| P5 — research | Bộ input/labels đóng băng, phương pháp và báo cáo chất lượng matching riêng | Benchmark không thay nghiệm thu sản phẩm, và sản phẩm đạt không chứng minh AI tốt |

HM-10 được làm từ P0; outbox/notifications in-app + email giao dịch HM-06 cung cấp sự kiện cho HM-07…09. SMS/push là kênh tùy chọn. Các gate là dependencies, không là lịch cam kết. P4 chỉ đạt khi tất cả module bắt buộc hoàn thành; không dùng release checklist cũ của bản tìm phòng.

## 4. Trình tự và điểm khóa hợp đồng

1. FE-01 + FE-17 nền tảng: làm rõ roles/scopes, listing vs AI projection, trạng thái hợp đồng/thuê/tiền và policy dữ liệu.
2. FE-02/18 và FE-06/11: shell/auth, owner inventory/media, moderation/assignment. Kiểm chứng ownership ngay khi có entity.
3. FE-03/04/05/12/13: public discovery và AI song song, favorite/history, compare, lịch và notification; FE-07 làm overview từ dữ liệu thật.
4. FE-14 → FE-15/16: contract/tenancy là điều kiện để hóa đơn/công tơ/sửa chữa có đúng ngữ cảnh. FE-13/17 mở rộng sự kiện và quyền tương ứng.
5. FE-08/09 theo từng increment, FE-10 tổng hợp P4 sau API/browser/ops evidence.

Chốt DTO/action trước xây màn có mutation. Khi backend chưa có API, FE chuẩn bị component/fixture kiểm thử nhưng task integration vẫn mở. Thay đổi contract cần cập nhật screen/state/AC cùng lúc; không nối raw graph/checkpoint để bỏ qua API.

## 5. Các quyết định bắt buộc

- Public search/detail/compare/viewing dựa listing đã moderation, revision và `mode/source_mode=public_catalog`; AI results/compare/viewing dựa `published/current` và `mode/source_mode=ai_recommendation`. Không bắt mọi tin public qua cổng HITL cá nhân hóa.
- Current recommendation tối đa 5 và compare 2–3 theo API hiện có; v1 public search có pagination theo contract. Bộ lọc/sắp xếp không tự rank lại gợi ý approved.
- Requested viewing không giữ phòng; reservation riêng có expiry theo thỏa thuận; slot/confirmed/reschedule/cancel/completed/no-show do server quyết định. Owner đề xuất slot, manager assigned confirm/decline.
- Contract activate sau chấp thuận đúng version của renter và owner/manager được ủy quyền; tenancy active sau move-in checklist. Legal e-sign là tùy chọn, document/consent/audit là bắt buộc.
- Báo đã chuyển tiền và xác nhận đã nhận là hai thao tác; manual recording/reconciliation bắt buộc. Cổng thanh toán không phải điều kiện để có sổ đối chiếu đúng.
- Tour/media/link và lịch trực tuyến có thể hoàn thành trải nghiệm xem từ xa; không bắt xây nền tảng video call riêng. Voice/image AI không là điều kiện để nghiệp vụ core đạt.
- Không sao assets/data HubHome; layout tham chiếu có nguồn, phần bổ sung có nhãn thiết kế HomeMatch. Độ giống không thay quyền/tiền/trạng thái.

## 6. Truy vết và nghiệm thu

| Nhóm | Bằng chứng bắt buộc | Task |
|---|---|---|
| HM-01/10 | Cross-account/scope/role, auth recovery/revocation, admin audit/privacy/support | FE-02/08/17/18 |
| HM-02/03 | Owner draft→moderation→public; media/map/list/revision/availability/filter | FE-04/05/06/11 |
| HM-04 | Confirm→pending→HITL→published; hidden draft/null/0/invalidation | FE-03/04/05/08 |
| HM-05/06 | Account sync, public/AI compare; slot/status/timezone; handoff/notification receipt | FE-12/13 |
| HM-07 | Version consent, activation allocation period, move-in/out/gia hạn/kết thúc, deposit dispute hold | FE-14 |
| HM-08 | Meter/invoice lifecycle/payment_status/overdue oracle, partial/overpayment/dispute/correction, reconciliation | FE-15 |
| HM-09 | Assignment/timeline/media/accept/reopen và quyền tenancy | FE-16 |
| UI-V01…16 | Route/state, reference/token, responsive/keyboard/contrast, errors/recovery, full release | FE-01/08/09/10 |

Mỗi task xong phải có file/screen/component, endpoint contract, test phù hợp, API/browser evidence và hạn chế ghi thật. [DETAILED_PLAN](DETAILED_PLAN.md) có tiêu chí FE-xx.ACn; [TEST_CHECKLIST](TEST_CHECKLIST.md) và [DEMO_CHECKLIST](DEMO_CHECKLIST.md) ghi kết quả. Tài liệu hiện là kế hoạch đã mở rộng; không thay source, chạy lại kiểm thử hoặc tự đánh dấu triển khai hoàn tất.
