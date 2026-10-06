# Kế hoạch dữ liệu sản phẩm HomeMatch

Phiên bản 04/10/2026. Data phải phục vụ toàn vòng đời thuê **HM-01..10**: dữ liệu vận hành, fixtures kiểm chứng và nghiên cứu AI có nguồn/phiên bản riêng. Đọc [plan chi tiết](DETAILED_PLAN.md), [schema đích](../docs/kien-truc-homematch.md), [yêu cầu](../docs/yeu-cau-san-pham.md), [AC](../docs/tieu-chi-nghiem-thu.md) và [Data hiện tại](README.md).

## 1. Hiện trạng và ranh giới

Đã có 80 canonical rooms synthetic TP.HCM, pilot25, 30 gold profiles (dev10/test20), alias fixtures, source register, 15 cost oracles độc lập và development manifest frozen=false. Chưa có human relevance labels độc lập hoặc bộ fixtures contracts/meters/payments/maintenance/organization isolation. Seed demo cũ không thay bộ data sản phẩm.

**Trạng thái 05/10/2026:** fixture packs v1 cho HM-01/02/07/08 (+HM-09) đã soạn tại `data/fixtures/v1/` (29 file, ~250 record, toàn bộ synthetic) kèm oracle billing độc lập và validator `data/validate_fixtures.py` (2550 assertions, gồm tính lại VND bằng Decimal/ROUND_HALF_UP riêng, không import backend). Hạn chế trung thực: oracle chưa có người kiểm tra chéo (`human_cross_check_status: pending` theo mô hình cost_cases); fixtures chưa được backend nạp/schema đối chiếu; chưa có case cho HM-03..06, HM-10; quy mô nhỏ, không phải kho thị trường. Hash các input frozen (`catalog/`, `profiles/`, `oracles/cost_cases.json`, manifests, `generate.py`) không đổi sau lần soạn này.

Dữ liệu không xuất từ HubHome và không đại diện thị trường. [Research HubHome](../docs/nghien-cuu-hubhome.md) là bằng chứng chức năng/UX, không quyền sao chép catalog/ảnh/chats hoặc yêu cầu crawl. Viết plan này không thay hash/manifests/dataset hiện tại.

Data sở hữu dictionary/source/canonical quality, fixtures/gold/oracles và blind human labels. Backend sở hữu schema/migration/import/engine; Eval sở hữu runner/metric/freeze/run reports. Không lấy output backend/ranking/LLM làm oracle hay relevance gold.

## 2. Đầu việc theo module

| ID | Dataset/rules cần bổ sung | Gate/phụ thuộc | Evidence |
|---|---|---|---|
| HM-01 | Ít nhất hai organizations, bốn roles, membership/assignment lifecycle, account recovery/revoke fixtures | P0/P1; permission model | Ca đúng/sai quyền API/media/job/export; không credential thật |
| HM-02 | Property/room/listing/fee/media/evidence/moderation/revision/canonical dictionary | P0/P1; Backend schema | Published/draft/changes_requested/suspended/stale, source/hash và unknown quality report |
| HM-03 | Filters/sort/map/detail cases, approximate/area_only/boundary/pagination | P2; public DTO | Public projection, hard-filter expected IDs, không địa chỉ thật bị suy từ fixture |
| HM-04 | Utterances/gold profiles/intent/ambiguity, cost oracle, B1/P blind pool/labels | P2; P5 research riêng | Null/zero/cost/hard/HITL fixtures; labels độc lập và frozen chain |
| HM-05 | Favorites/history/preferences/public-AI compare/sync/delete fixtures | P2; HM-01/03/04 | Source mode/scenario/version rõ, cross-account/retention cases |
| HM-06 | Viewing timezone/status/reschedule/no_show, handoff assignment, outbox/delivery events | P2 core; thuê events P3 | Requested không giữ phòng, retries/recipient quyền và crash cases |
| HM-07 | Agreement/reservation/terms/version/acceptance/tenancy/move-in-out fixture pack | P3; contract rules | Hai bên đúng version, expiry/overlap/handover/cọc và unresolved settlement |
| HM-08 | Reading/tariff/invoice/payment/receipt/allocation/reconcile oracle pack | P3; billing rules | Exact VND, reset/overlap/partial/duplicate/dispute/adjustment |
| HM-09 | Ticket/media/triage/schedule/progress/complete/reopen fixtures | P3; tenancy | Lifecycle/quyền/ảnh/chi phí xác nhận, không auto billing |
| HM-10 | Audit/retention/export/delete/redaction/restore fixtures và source permissions | Cắt ngang P0..P4 | Retained record policy, no PII, version/hash và restored reference checks |

## 3. Hợp đồng dữ liệu

Tiền nguyên VND, đơn giá Decimal dạng string; null chưa biết khác zero có nguồn. Tách estimate usage scenario khỏi actual meter readings/invoices. Canonical room khác listing; listing published khác availability/occupancy/reservation; mỗi thay đổi có revision/evidence/effective time.

Contract terms và invoice issued lines là snapshot; sửa cần version/adjustment và audit, không overwrite. Renter declared transfer khác receiver receipt/reconciled allocation. Timestamps lưu timezone-aware, UI theo múi giờ sản phẩm; ID/organization/resource và actor đều rõ.

Public ảnh/phòng khác private contract/payment/meter/maintenance media. Dữ liệu giả dùng synthetic=true, fixture coordinates và faux files; không tài chính, giấy tờ, credential hoặc hội thoại người thật trong repo/vector/reports.

## 4. Gates, nghiên cứu và bàn giao

P0 dictionary/quyền/đơn vị/state/source policies. P1 seed accounts/catalog/moderation/media. P2 public/AI/history/compare/viewing/notification cases. P3 bộ dữ liệu xuyên vòng đời thuê và độc lập financial oracles. P4 integrity/privacy/restore evidence cùng release. P5 riêng giữ freeze trước test, blind relevance labels và model/prompt/config hashes.

Dataset research hiện tại 80 rooms/30 profiles là quy mô thử nhỏ, không mục tiêu quy mô production. Mọi mở rộng version mới; không đổi test khó hoặc thêm label sau khi nhìn metric để cải thiện số. P@5 chia 5; pool-based nDCG từ union B1/P không là recall toàn kho. Paraphrase giữ cùng profile group/split.

Bàn giao dictionary, source/rights register, synthetic ratio, quality report, fixture expected outcomes, independent oracle formulas, manifests/hashes/split/labels status và privacy notes. IDs DATA-01..07/checklist MVP cũ là lịch sử, scope mới là HM-01..10.

