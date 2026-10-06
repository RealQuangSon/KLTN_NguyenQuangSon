# Eval — kế hoạch chi tiết nghiệm thu và nghiên cứu

Phiên bản 04/10/2026. [PLAN](PLAN.md), [AC sản phẩm](../docs/tieu-chi-nghiem-thu.md), [yêu cầu/NFR](../docs/yeu-cau-san-pham.md) và [Data detailed plan](../data/DETAILED_PLAN.md) là nguồn phạm vi. HM-xx.EV-ACn là AC kiểm chứng bổ sung; output đích chưa chạy không được gọi evidence.

## P0 — Test matrix và protocol

- Map HM requirements → product AC → suites/API/browser → fixture/config version → artifact.
- Khóa bốn role/ít nhất hai org/resource ownership, state transitions/version/CAS/idempotency và source modes.
- Chốt NFR workload/topology/data volumes/cache/errors theo mục tiêu đề xuất; ghi config trước test.
- Tách functionality/financial safety/provider quality/research/usability/operation evidence.
- Loader reject hash/schema/split/version mismatch; synthetic/fixture/live modes không trộn.

**AC chung:** Mỗi tuyên bố có method/actual outcome/evidence; thiếu input hoặc ca chưa chạy báo pending/unverified, không passed. Test phù hợp hành vi/rủi ro, không mirror code hoặc viết lại implementation làm expected.

## HM-01/10 — Identity và governance

**Phụ thuộc:** accounts/permission/privacy/admin modules.

- Test register/verify/reset one-use/expiry, login/logout/session revoke/password/disable.
- Matrix renter/owner/manager/admin × organization × record × API/media/export/jobs; forged role/owner/org, guessed ID và reassignment.
- Admin dashboard scope/audit reasons, sensitive access; retention/export/delete/restrict theo policy.
- Sample logs/bundles/vector/checkpoint exports không secret/raw chat/PII ngoài scope.

**AC:** HM-01.EV-AC1 — mọi allow/deny có actual API/browser/media outcomes; revoke/role change không để quyền cũ. HM-10.EV-AC1 — audit/privacy/export đúng phạm vi và giữ transaction obligations có lý do.

## HM-02 — Inventory và moderation

**Phụ thuộc:** CRUD/media/catalog version.

- Owner create/edit property/room/fees/media, unknown/included/zero và validation.
- Submitted/changes_requested/published/suspended/archived, revision stale/CAS và re-approval.
- Private media/url expiry/cross-org, physical_room_id stable khác listing_id/published_revision; unique org/building/room_code, room.id migration mapping, aliases/dedup/import batch conflict.
- Update rent/fee/availability trong lúc review/read phải invalidates/refresh theo policy.

**AC:** HM-02.EV-AC1 — chỉ published projection public; moderation decision đúng revision; edit không silent replace. HM-02.EV-AC2 — source/unknown/media rights và duplicate outcomes đạt, evidence có fixture IDs.

## HM-03 — Public discovery

**Phụ thuộc:** query/map/detail API và FE.

- Filters type/city/area/people/rent/total/amenities, sort/pagination và canonical no duplicates.
- List/map/detail dùng cùng filter/revisions; approximate/area_only/uncertainty và boundary.
- Missing cost không 0/pass budget; public exact private address/contact ẩn.
- Map outage có list fallback, empty/no-match/error rõ; report tin tạo đúng internal ticket.

**AC:** HM-03.EV-AC1 — expected eligible IDs độc lập khớp; public không pending AI/unpublished listing. HM-03.EV-AC2 — browser map/list giữ filters/source/sai số và lỗi không mất tác vụ.

## HM-04 — AI hiểu nhu cầu, cost và HITL

**Phụ thuộc:** Agent/finance/ranking/ledger/checkpoints.

- Cost-only/human-support/find/unknown routing, no auto city/school/budget; edit/remove/confirm/CAS/provenance.
- Independent oracle exact VND/null/known/missing/rounding/deposit/advance, rent thấp total vượt.
- Hard filter/unknown amenities/capacity/availability/location errors; B1/P eligible equality/dedup.
- Pending/reviewed/generation_failed/invalidated renters không items qua results/compare/viewing/tool/stream; manager wrong assignment.
- Review key replay/changed payload, profile/catalog stale before/after review/publish/read.
- Crash after event commit before resume, checkpoint missing, restart pending/generation retry; no old approval inheritance.
- Explanation claims evidence/cost/revision; counterfactual commission/stock không đổi rank.
- Provider timeout/refusal/incomplete/quota/injection có form/errors/modes; fake clients không live quality.

**AC:** HM-04.EV-AC1 — oracle và hard constraints không unsafe pass; state outcomes/evidence từng case rõ. HM-04.EV-AC2 — no draft leak/unauthorized/stale publish/double event, kể cả restart/replay. HM-04.EV-AC3 — provider release mode được kiểm thật nếu quảng bá AI; failures/fallback không báo no_match hoặc P successful giả.

## HM-05 — Saved/history/compare

**Phụ thuộc:** account storage/privacy/public-AI compare.

- Favorite/save search replay và cross-device sync, stale/archived listing status.
- History consent/retention/clear/continue, opt-out khác minimum operational checkpoint/ledger purpose/TTL đã thông báo, logout account switch, invalidated historical run không live.
- Compare 2–3 distinct IDs cùng source mode/scenario; mixed mode/4 IDs/duplicate/stale bị chặn.
- Quote/catalog đổi giữa thao tác, pending AI guessed ID không bypass.

**AC:** HM-05.EV-AC1 — server persistence đúng actor, privacy/clear có effect đúng scope. HM-05.EV-AC2 — cost basis/revisions/source rõ, invalid input/stale không leak.

## HM-06 — Viewing, handoff và notification

**Phụ thuộc:** lifecycle/outbox/worker; core đóng P2, lease notifications P3.

- Future timestamp/timezone/slots, source public listing revision hoặc AI current run; room unavailable.
- Owner suggest slot/manager confirm; requested không reserve, reschedule cần confirm mới.
- Cancel/completed/no_show/declined events, duplicate requests/respond và wrong actor.
- Handoff assignment/ack/open/in_progress/resolved/closed/reopen, không nhận thì không nói connected.
- Fault channel/recipient change, crash after commit/during delivery, event replay/dedup/dead-letter; notifications không đổi nghiệp vụ.

**AC:** HM-06.EV-AC1 — exact state/actor/time/version và slot conflicts; no phantom reservation. HM-06.EV-AC2 — retries không double-record/double-notify, channel failure visible và recipient links đúng quyền.

## HM-07 — Contract, tenancy và settlement

**Phụ thuộc:** agreements/reservation/contract/tenancy/handover.

- Renter accept v1, owner sửa v2, missing/unauthorized/cross-version acceptance.
- Contract activation đúng terms + renter/owner hoặc authorized manager, document private/hash.
- Reservation agreement/interval/expiry/convert/cancel/concurrent hold theo physical_room_id, conversion closes reserve→lease atomic; viewing không reserve.
- Contract activation room/period allocation chống active contract overlap, concurrent activation/replay; planned allocation chặn overlap nhưng không active/occupied trước move-in; expired contract không release occupied trước recorded move-out; initial readings/assets/deposit snapshot.
- Renew/terminate/move-out/final invoice/deposit deduction proposed/accepted/disputed/refund/open obligations; dispute hold không tự khấu trừ/financial settlement settled.
- App consent/doc records không giả e-sign pháp lý.

**AC:** HM-07.EV-AC1 — stale acceptance/missing rights/overlap bị chặn, move-in gating/replay đạt. HM-07.EV-AC2 — settlement deposit ledger balance/evidence và final obligations rõ, closed không xóa history.

## HM-08 — Readings, invoices và reconciliation

**Phụ thuộc:** billing engine/independent oracle/ledger.

- Cumulative readings khác usage delta; decreasing/meter replacement/correction/photo/version, overlap/missing/estimated vs measured; replacement usage old_last−old_start+new_end−new_first, unknown segment chặn actual issue.
- Kỳ [start,end), default tariff hiệu lực đầu kỳ; midperiod change áp kỳ sau trừ accepted amendment+measured boundary split segments; không tự prorate đoán; unit/included/null/rounding/rent advance allocation.
- Invoice lifecycle draft/issued/void; payment_status unpaid/partially_paid/paid; overdue computed balance > 0 và now > due_at, test partial+overdue đồng thời; issued snapshot immutable, adjustments linked.
- Payment evidence uploaded chưa paid; receiver verify/receipt/allocation/partial/overpayment/rejected/dispute/refund.
- Same key replay/changed payload, duplicate evidence và concurrent allocations; remaining balance exact VND.
- Crash at issue/receipt/reconcile/adjust commit, retry không double-count.

**AC:** HM-08.EV-AC1 — independent oracle 100% exact VND theo NFR mục tiêu; missing rules chặn issued theo policy. HM-08.EV-AC2 — transfer declaration không received/paid; allocations/refunds/balance khớp audit, retries/correction giữ lịch sử.

## HM-09 — Maintenance

**Phụ thuộc:** tenancy/ticket/media/cost/notification.

- Tenant create/urgency/triage/assignment/appointment/progress/resolved/close/reopen/cancel; wrong tenancy/org.
- Private photos, evidence thiếu, tenant confirmation, reopen reason.
- Cost có payer và đúng bên chịu tiền chấp thuận hoặc terms snapshot xác minh; owner technical approval không đủ thu renter, disputed charge chưa xác định debt; dedup charge event→invoice.
- Role/assignment change, retry/schedule conflicts/channel faults.

**AC:** HM-09.EV-AC1 — lifecycle/actor/evidence/permissions đúng, emergency instructions không hứa staffing chưa có. HM-09.EV-AC2 — unapproved cost không invoice, replay approved charge không double-bill.

## P4 — Browser, load, deploy và recovery

Chạy ba hành trình trong AC sản phẩm bằng browser thật bốn roles/ít nhất hai org: source→discovery→viewing; acceptance→move-in→invoice→receipt; maintenance→move-out→settlement. Kiểm desktop/mobile/keyboard/loading/empty/error/stale. Mock/in-process là evidence thành phần.

Load theo NFR và topology config; p50/p95/counts/errors/cold-warm/tài nguyên/version. Giữ một API worker; multi-process scale chỉ sau audit riêng. Backup/restore DB/ledger/checkpoints/media cô lập, verify permissions/revisions/pending state/số dư/references, retry side effects. Deployment/migration/rollback/runbook bằng evidence thật.

**AC P4:** Không HM mandatory là placeholder; AC/NFR có reports/actual limitations và no blocking defects. Script syntax/unit tests không proof restore/browser/cloud.

## P5 — Research B1/P và extraction

- Giữ eval/config/protocol.json hiện tại như development protocol; CLI guard G4 acknowledgment không tự chuyển thành P4.
- Khóa version code/config/prompt/catalog/gold/split trước outputs; vectors P thật cùng eligible set, fallback unavailable riêng.
- Blind human labels union top5 B1/P canonical; label hash trước metrics, không machine/LLM/self-rank gold.
- Precision@5 chia 5, actual precision riêng; pool nDCG IDCG=0/thiếu label undefined, không full recall.
- Paired same fully judged/metric-defined IDs, report coverage/exclusions/errors; bootstrap original profile, effect tuyệt đối/tương đối khi B1>0 và CI; kết quả âm giữ nguyên.
- Field F1 chỉ schema/provider input thực, intent/ambiguity/inferred unsupported riêng; finance form/local tiền không model F1.
- Machine vs manager wait, indexing/update/query cost và actual calls/token/retry/usage; unavailable khác 0, pricing source/date khi có.
- User study nếu tuyển được/consent/tasks/order/actual n; không có thì không claim hài lòng, synthetic/mẫu nhỏ không market proof.

**AC research:** Reports truy raw outputs/manifests/labels/denominators/mode; hash/group leak fail; fake SDK không quality; config đổi sau test gọi version/run mới hoặc post-test analysis. P tốt hơn B1 không bắt buộc để báo nghiên cứu trung thực.

## Bàn giao

Matrix HM→AC→evidence, per-case reports/fixtures hashes, regression/browser/load/recovery/releases actual outcomes; research manifests/independent labels/paired metrics/error analysis và reproduction. Không sửa evidence/manifests lịch sử hoặc dataset frozen để đóng gate trong lần viết docs. EV task IDs/62-task checklist cũ là lịch sử.
