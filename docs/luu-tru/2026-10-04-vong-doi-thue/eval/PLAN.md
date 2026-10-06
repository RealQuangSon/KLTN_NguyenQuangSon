# Kế hoạch kiểm chứng và đánh giá sản phẩm HomeMatch

Phiên bản 04/10/2026. Eval phục vụ **hai mục đích có evidence riêng**: nghiệm thu sản phẩm đủ HM-01..10 ở P0..P4 và nghiên cứu AI/matching ở P5. Không dùng điểm nDCG thay nghiệm thu hợp đồng/công nợ/sửa chữa, không dùng unit test thay model quality.

Đọc [plan chi tiết](DETAILED_PLAN.md), [AC sản phẩm](../docs/tieu-chi-nghiem-thu.md), [yêu cầu/NFR](../docs/yeu-cau-san-pham.md), [Data plan](../data/PLAN.md), [README hiện tại](README.md) và [tái lập](REPRODUCE.md).

## 1. Hiện trạng

Đã có CLI validate/oracle/extraction/ranking/metrics/invariants/grounding/measure/report/freeze, protocol ở eval/config/protocol.json, tests và development outputs/gói blind. Oracle/functional checks khác research results. Chưa có relevance labels người độc lập, frozen research run, GPT/P live quality hoặc user study; fake SDK/vector fixtures không phải chất lượng model thật.

Các runners hiện tập trung phòng/profile/cost/ranking, chưa phủ account organization lifecycle, public catalog/history, contract/tenancy, meters/invoices/manual payments/reconcile, maintenance và production recovery. Dataset/manifests/protocol/evidence hiện tại giữ nguyên; plan này không tự đóng gate hoặc tạo metric mới.

## 2. Nghiệm thu theo module

| ID | Suites/evidence bắt buộc | Gate |
|---|---|---|
| HM-01 | Bốn role/account/session/recovery/revoke, ít nhất hai org; API/media/export/job isolation | P1/P4 |
| HM-02 | CRUD/fee/null-zero/media/moderation/canonical/revisions/invalidation | P1/P4 |
| HM-03 | Public filter/list/detail/map/sort/pagination/source/uncertainty và fallback map | P2 |
| HM-04 | Intent/ambiguity/edit/confirm, finance oracle, hard constraints, HITL/quyền/stale/replay/restart/grounding/provider modes | P2/P4; quality P5 |
| HM-05 | Favorites/saved-search/history/device sync/consent/delete, public/AI compare/scenario/stale | P2 |
| HM-06 | Viewing/request/confirm/reschedule/cancel/completed/no_show; handoff/read notification/outbox retries | P2; thuê events P3 |
| HM-07 | Terms version/acceptance/reservation expiry/overlap/activation/move-in/out/deposit settlement | P3 |
| HM-08 | Reading/tariff/billing oracle, invoice issued snapshot, receipt/allocation/partial/duplicate/dispute/refund | P3 |
| HM-09 | Tenant/role/media permissions, triage/schedule/cost approval/resolved/close/reopen/dedup charge | P3 |
| HM-10 | Admin scoped dashboard/audit/privacy/retention/rate limits/monitoring/restore/rollback | Cắt ngang → P4 |

Mỗi suite có actual outcome, config/fixture version và failure counts. P4 cần browser bốn roles, API negative checks, full rental E2E, load theo NFR đề xuất và recovery. Mocks/màn hình trống/script chưa chạy không đủ. Giữ một API worker; tests concurrency trong process không suy multiworker.

## 3. Nghiên cứu P5

B1 và P dùng cùng confirmed gold profile/scenario/catalog/cost/hard-filter/eligible set. P cần semantic vectors thật; unavailable/fallback B1 không biến thành P successful. Tune chỉ dev; freeze code/config/prompt/catalog/gold/split → method outputs → blind human judgments → label hash → metrics.

Giữ metric conventions của protocol được khóa: relevance 0–3, relevant≥2, Precision@5 mẫu số 5; actual-return precision riêng; pool-based nDCG@5, IDCG=0/thiếu judgment undefined; không full-catalog recall. Paired effect/CI trên cùng profile IDs fully judged/metric-defined; bootstrap profile gốc, paraphrase không thành samples độc lập; coverage/exclusions/errors/no-match báo đủ.

Extraction field F1 chỉ trường schema/provider thực nhận; local money hint/form budget không model F1. Intent/ambiguity/unsupported inferences đo riêng. Grounding từ evidence/cost/version, không LLM tự chứng nhận. Machine latency tách waiting quản lý; indexing/update/query costs tách nhau; usage unavailable khác 0, retry/errors đếm.

Dataset hiện 80 rooms/30 profiles synthetic hỗ trợ kết luận trong phạm vi nhỏ. P tốt hơn B1 là giả thuyết cần đo, không điều kiện buộc kết quả phải dương. User study độc lập/tự nguyện có thể bổ sung; không có thì không claim hài lòng/usability thị trường.

## 4. Gates và release evidence

P0 khóa test matrix/AC/NFR/protocol riêng; P1 accounts/catalog; P2 discovery/AI/saved/viewing; P3 lease/billing/maintenance; P4 release với đủ AC/NFR/restore/browser evidence; P5 research freeze/labels/paired metrics. NFR trong yêu cầu là mục tiêu đề xuất, phải đo cấu hình thực, không kết quả đã đạt.

CLI freeze hiện vẫn có G4 acknowledgment theo protocol cũ. Không tự sửa manifest/guard để coi P4 đã đạt; khi nghiên cứu mới, version protocol/inputs và quyết định freeze rõ. Release manifest mới chỉ lấy checks thật, không đổi evidence lịch sử.

Bàn giao test matrix/module-to-AC/evidence, per-case failures, financial oracles, E2E/browser/load/restore reports và limitations. Research bàn giao manifests/raw outputs/judgments/metrics/CI/error analysis. EV-01..08/checklist MVP/AC01..16 cũ là lịch sử.

