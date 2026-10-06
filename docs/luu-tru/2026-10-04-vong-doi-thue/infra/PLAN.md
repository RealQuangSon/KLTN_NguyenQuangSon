# Kế hoạch hạ tầng và vận hành HomeMatch

Phiên bản 04/10/2026. Hạ tầng phải vận hành sản phẩm đủ **HM-01..10**, không dừng ở một demo AI. Đọc [plan chi tiết](DETAILED_PLAN.md), [kiến trúc](../docs/kien-truc-homematch.md), [AC sản phẩm](../docs/tieu-chi-nghiem-thu.md), [env hiện tại](env-inventory.md) và [runbook hiện tại](RUNBOOK.md).

## 1. Hiện trạng trung thực

Đã có local checks, smoke API, local PostgreSQL scripts, migration/seed/index commands, health/readiness/metrics và backup/restore scripts. Docker/compose/Railway files là cấu hình/draft cần kiểm chứng theo [báo cáo backend](../docs/kiem-chung-backend.md) và [backup/restore](backup-restore.md), không tự là deployment thành công. Không có bằng chứng full cloud/restore/public production hoặc worker notification.

Hiện một API worker, SQLite offline hoặc PG; production đích là PostgreSQL/pgvector, private media và worker outbox/IO. Thêm worker nền không cho phép tăng API workers trước audit DB/checkpoint/concurrency. Env mới chỉ cập nhật inventory khi mã thực sự đọc; không hư cấu các biến là đã có.

## 2. Hạng mục và phụ thuộc

| Hạng mục | HM liên quan | Gate/phụ thuộc | Evidence hoàn thành |
|---|---|---|---|
| Runtime/build/lock và CI | Toàn bộ | P0; code/dependencies | Build/tests từ checkout mới; CI run thật, không secret/live calls mặc định |
| PG/migrations/seed/schema/checkpoints | HM-01/02/04/07/08/09 | P1; Backend migrations | DB trống/upgrade/restart đạt; production config đúng, SQLite chỉ offline |
| Identity/security isolation | HM-01/10 | P1 → P4 | TLS/origins/private access, session/rate limits và four-role/org negative smoke |
| Private media/documents | HM-02/07/08/09/10 | P1/P3; media adapter | Permission URLs/uploads/retention; backups và restored links đọc đúng scope |
| Queue/outbox/worker | HM-06/07/08/09/10 | P2 core; thuê events P3; transaction/event contract | Claim/lease/dedup/retry/dead-letter, queue lag/cảnh báo; crash không lặp nghiệp vụ |
| Observability/capacity | HM-04/06/08/10 | P2/P3 → P4 | Durable metrics/alerts, bounded AI budget, measured load/SLO và topology thực |
| Backup/restore/rollback | HM-01..10 | P4; ledger/media/worker | Restore cô lập giữ state/quyền/revision/công nợ/checkpoint; diễn tập rollback |
| Production deployment/runbook | Toàn bộ | P4 sau HM-01..10 | Public config/release smoke thực, operator guide, incidents và actual limitation |

## 3. Gates

P0 khóa topology/ownership/data classes/env/secrets/target workload và rollback policy. P1 production storage/account/catalog/media nền. P2 discovery/AI/viewing smoke, worker/notification core và provider mode/quota. P3 notification sau thuê và full rental-operation state. P4 build/deploy/permission/load/restore/rollback/runbook đủ evidence cho cả HM-01..10. P5 research bàn giao cấu hình/mode/cache/usage thực riêng, không suy production capacity từ benchmark nhỏ.

Các mục tiêu latency/load/RPO/RTO đã đề xuất trong [NFR](../docs/yeu-cau-san-pham.md); chốt cấu hình/workload/cadence/ngân sách trước acceptance, đo thực và không điền số đã đạt khi chưa đo. Core discovery/account/billing không phụ thuộc provider AI luôn sẵn sàng.

## 4. Bàn giao và giới hạn

Bàn giao release topology, lock versions, config inventory có secret references, deploy/rollback/runbook, actual CI/smoke/load/restore reports và alert ownership. Không gửi token/DB URLs/dumps/raw checkpoints hoặc dữ liệu thuê thật vào artifacts công khai.

Provider/hosting account và budget là đầu vào khi triển khai dịch vụ thật; plan này không tự tạo cloud resources. Chưa deploy thì trạng thái local-only giữ rõ; chưa restore thì không đánh dấu disaster recovery đạt. Gateway/e-sign/video optional, còn private storage/notification delivery/manual financial operations là core.

ID INF-01..08 và checklist MVP là lịch sử. Tiến độ/release đích theo HM modules và P0..P4; tài liệu evidence/runbook cũ không bị sửa thành đã vận hành sản phẩm hoàn thiện.

