# Kế hoạch theo từng phần HomeMatch v1

**Ngày:** 04/10/2026. Các nhóm cùng phục vụ HM-01–HM-10 trong [đặc tả](dac-ta-san-pham.md). Module sau thuê là bắt buộc, không còn nằm ngoài MVP. Đầu việc cấp sản phẩm W-01–W-18 nằm tại [kế hoạch triển khai](ke-hoach-trien-khai.md).

## Phân công và nguồn tài liệu

| Phần | Phạm vi sở hữu | Plan / chi tiết | Bàn giao |
|---|---|---|---|
| Frontend | Navigation/roles, public/AI workspace, owner, tenancy/billing/maintenance/admin, responsive/accessibility | [FE](../frontend/PLAN.md), [chi tiết](../frontend/DETAILED_PLAN.md), [UI spec](../frontend/UI_SPEC.md) | Screens/flows theo DTO; browser evidence |
| Backend | Auth/membership, catalog/media/moderation, viewing, contract/tenancy/ledger, billing/maintenance/admin, migrations | [BE](../backend/PLAN.md), [chi tiết](../backend/DETAILED_PLAN.md) | OpenAPI/schema/permission/state/transaction/replay tests |
| Agent | Intent/extraction/confirmation/rank/review/grounding, read-only rental summaries và handoff có quyền | [AG](../backend/AGENT_PLAN.md), [chi tiết](../backend/AGENT_DETAILED_PLAN.md) | Graph/tool contract, provider/fallback/recovery evidence |
| Data | Catalog có nguồn, quyền media, profiles/split, cost và billing oracle, fixtures toàn vòng đời | [Data](../data/PLAN.md), [chi tiết](../data/DETAILED_PLAN.md) | Version/schema/hash/source register, fixtures độc lập |
| Eval/QA | Matching/extraction research, invariants, integration negative/race/fault/browser/load/retention | [Eval](../eval/PLAN.md), [chi tiết](../eval/DETAILED_PLAN.md), [AC](tieu-chi-nghiem-thu.md) | Protocol/runs/judgments/QA evidence, báo kết quả thực |
| Infra | PostgreSQL/private storage, one API worker, outbox/email, staging/release, alert/restore/rollback | [Infra](../infra/PLAN.md), [chi tiết](../infra/DETAILED_PLAN.md) | Môi trường vận hành/runbook và diễn tập |
| Docs | Product/requirements/process/AC/glossary/research/architecture/guide/thesis/handover | [Docs](PLAN.md), [chi tiết](DETAILED_PLAN.md) | Bộ tài liệu thống nhất trạng thái/nguồn/release |

## Hợp đồng phối hợp

W-01 khóa terminology, resource refs, states, error envelope và retry cho từng endpoint. Người phụ trách domain giao DTO/schema trước FE integration; FE mock không là proof backend. Database/schema/migration do BE sở hữu; agent chạy trong backend và dùng service kiểm quyền, không tự truy DB bỏ qua policy.

Một thay đổi public/private projection phải rà HM-03/04/05/06 cùng lúc. Chuyển role/assignment rà cả files/notifications/export. Terms/rates/meter/receipts thay đổi phải có billing oracle độc lập và version rule; UI không tự tính số dư.

Bàn giao mỗi module gồm behavior/API/DB/permissions/UI/AC/evidence. Không ghi "xong frontend" khi toàn bộ API sau thuê còn fake; không ghi "xong backend" chỉ vì có migrations nhưng flow người dùng chưa chạy.

## Thứ tự gate

P0 contract → P1 accounts/catalog → P2 discovery/AI/saved/viewing/notification → P3 lease/billing/maintenance → P4 release. HM-10 đi xuyên suốt; P5 research là nhánh riêng trên cấu hình đã freeze. Các phần FE mocks/data/oracles/docs/infra có thể làm đồng thời khi không đụng hợp đồng đã khóa.

Khi thiếu đầu vào bên ngoài, ghi người sở hữu và gate bị ảnh hưởng ở trạng thái thực tế. Gateway, e-sign pháp lý và video-call riêng không chặn v1; manual payment ledger, contract acceptance và viewing vẫn phải hoạt động.
