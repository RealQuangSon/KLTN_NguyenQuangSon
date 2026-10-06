# Hạ tầng — kế hoạch chi tiết sản phẩm HomeMatch

Phiên bản 04/10/2026. [PLAN](PLAN.md), [kiến trúc](../docs/kien-truc-homematch.md), [Backend plan](../backend/DETAILED_PLAN.md) và [AC sản phẩm](../docs/tieu-chi-nghiem-thu.md) là nguồn phạm vi. Các INF-Rn dưới đây là hạng mục readiness cho HM-01..10, không trạng thái đã làm.

## INF-R1 — Runtime, build và kiểm tra tự động

**Gate:** P0/P1; áp dụng tất cả HM.

- Inventory runtime/lock/library/system dependency và lệnh build/start/test đã thực thi.
- CI hoặc pipeline tương đương chạy offline regression, FE tests/build, schema/API contract checks, dataset hash checks; PG fixtures khi môi trường hỗ trợ.
- Tách provider live/deploy cần môi trường riêng, không chạy bằng key cá nhân trong default tests.
- Lưu evidence với code/config version; screenshot/browser checks cần module UI thật.

**AC:** Checkout mới cài/build/tests theo lệnh đã ghi; failure dừng release; không commit secret/DB/raw chat/checkpoint. CI file chưa chạy không ghi CI passed.

## INF-R2 — PostgreSQL, migration và checkpoint

**Gate:** P1 rồi P3; HM-01/02/04/07/08/09.

- Production PostgreSQL/pgvector; SQLite offline path tách rõ.
- Migration trống/upgrade có backup/roll-forward/rollback plan; chỉ schema hợp lệ nhận traffic.
- Quyền DB theo app/job/operator; pool/timeouts theo cấu hình thực; durable ledger/checkpoints, vector index/hash version.
- Script seed/import không overwrite production/cross-org; startup không nạp demo vào kho đang có.
- Audit current RLock/service/checkpointer trước multi-process; API vẫn workers=1. Notification worker không chia connection singleton của API.

**AC:** Migrate/upgrade/restart thực giữ session/run/event/contract/invoice/payment; readiness lỗi khi schema/checkpoint/storage sai. PG connection failure không fallback âm thầm SQLite. Multi-worker chỉ được mở khi DB/checkpointer race/crash tests riêng đạt.

## INF-R3 — Bảo mật và cấu hình

**Gate:** P1/P4; HM-01/10 và media các module.

- TLS/explicit origins/private network/secret references; public không dùng demo token/seed credential mặc định.
- Login/API/upload limits, account recovery token/session revoke và tenant organization isolation smoke.
- URL/log/trace/body handling không lộ credentials/chat/tài chính; frontend bundle không server key.
- Quyền background job/export/notification/media kiểm như API. Admin sensitive access có reason/audit.
- Rotation/secrets/incident runbook, retention/export/delete jobs và audit quyền vận hành.

**AC:** Renter/owner/manager/admin đúng scope được phép; truy chéo org/record/media bị chặn; revoked token thất bại. Log/bundle scan không raw secret/PII. Config chưa được code đọc phải gắn design-only, không thêm vào env hiện tại như đã có.

## INF-R4 — Media, chứng từ và tài liệu

**Gate:** P1/P3/P4; HM-02/07/08/09/10.

- Chọn private object storage adapter, path ownership/metadata/hash/access class.
- Validate file size/type/name/content handling; document/image preview lỗi có fallback.
- Signed/access URLs TTL và server checks, không dựa vào tên file ngẫu nhiên như permission.
- Upload lifecycle orphan cleanup, retention và backup DB metadata + objects cùng phiên bản.
- Kiểm public room photos khác private contract/payment/meter/maintenance evidence.

**AC:** Private URL không đọc bằng account/org khác; expired URLs bị từ chối; delete/restore giữ đúng links/quyền. Public ảnh tin không làm public toàn storage bucket.

## INF-R5 — Outbox và worker notification/IO

**Gate:** P2 core; P3 thuê events; HM-06/07/08/09/10.

- Business record/audit/outbox cùng commit. Worker claim/lease, event IDs/dedup, bounded retry/backoff và dead-letter.
- In-app notification/read state là core; email theo cấu hình/consent channel, không cần SMS để release.
- Nội dung giảm PII, link có quyền, recipient resolve server; role/assignment đổi phải recheck.
- Queue lag/attempt/failure metrics; operator retry có audit và nguyên tắc không đổi quyết định.
- Recovery graph là policy riêng, không tự resume approval/generation bằng worker gửi email.

**AC:** Crash sau commit, lúc delivery và retry không mất business record/không nhân đôi tác vụ tiền/lịch/hợp đồng. Queue failures có alert/dead-letter/retry; notification sent không giả recipient đã nhận xử lý. Worker không tự cho API multiworker.

## INF-R6 — Observability, chi phí và capacity

**Gate:** P2/P3/P4; HM-04/06/08/10.

- Bền vững metric request/errors/latency, provider usage/timeout/quota, queue lag/retry, billing/reconciliation failures, backup age.
- Dùng workload/SLO đề xuất trong NFR; chốt cấu hình trước test, đo capacity thật với topology/DB/media/cache/concurrency; không suy từ một process vài samples.
- Tách machine latency/review waiting; cold/warm cache, indexing/query costs, retry/error đều đếm.
- Provider budget cần enforcement/circuit breaker; usage unavailable không giả 0.
- Alert owner, dashboard và incident runbook; health/readiness không tiết lộ secret.

**AC:** Mỗi SLO có config/sample/actual measurements; failed attempts có denominator. Metrics process 0.3.0 reset khi restart không bị gọi durable monitoring. Core account/catalog/billing còn hoạt động khi AI provider lỗi.

## INF-R7 — Backup, restore và rollback

**Gate:** P4; toàn bộ HM.

- Dùng RPO/RTO đề xuất trong NFR, chốt cadence/retention từ workload/budget; backup private DB/ledger/checkpoints/media/manifest.
- Restore sang DB/storage cô lập, không drop/overwrite live; verify checksums/schema/references.
- Kiểm auth/roles/assignments, pending/reviewed/invalidated, public/AI projections, contract acceptance/tenancy, reading/invoice/payment/reconcile và maintenance/media.
- Retry/recovery sau restore không gửi thông báo/ghi tiền/công bố hai lần.
- Diễn tập rollback ứng dụng/migration với compatibility plan; destructive schema changes có phương án phục hồi.

**AC:** Restore thực khớp counts/hashes/số dư/trạng thái/quyền và báo thời gian đạt mục tiêu đã chốt. Backup file/cú pháp script riêng không đủ. Hai SQLite files phải cùng phiên đóng connection nếu kiểm offline; production evidence phải dùng PG/media đích.

## INF-R8 — Release và vận hành

**Gate:** P4; đủ HM-01..10.

- Deploy staging, migrations và smoke bốn role/ít nhất hai org; browser flow toàn vòng đời thuê.
- Kiểm source public/AI, stale/CAS, viewing không giữ phòng, contract acceptance rồi move-in, manual payment/reconcile, maintenance và move-out.
- Chốt vận hành/admin support, notification failure, billing dispute, restore, provider outage, account/privacy requests.
- Release manifest mới chỉ tạo từ checks thật; evidence cũ giữ lịch sử, không đổi thành release success.
- Cloud/hosting/provider cần account/budget thật khi triển khai; trước đó làm mọi kiểm chứng local/staging trong phạm vi cho phép.

**AC:** Release checklist có module/owner/evidence/limitation, không mandatory HM còn placeholder. Deployment/rollback/restore reports đúng môi trường; chưa deploy giữ local-only. Gateway/e-sign/video/voice/image AI/toàn quốc được ghi optional, không ngăn core release.

## Bàn giao P5 nghiên cứu

Cung cấp runtime/topology/model/cache/calls/usage/pricing-date khi có cho Eval; không sửa frozen dataset/protocol hay independent labels. Research p95/nDCG khác acceptance vận hành. ID INF cũ là lịch sử; P0..P4 và HM là nguồn scope hiện tại.

