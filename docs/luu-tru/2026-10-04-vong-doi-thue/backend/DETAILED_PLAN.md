# Backend — kế hoạch chi tiết theo HM modules

Phiên bản 04/10/2026. Đọc [PLAN](PLAN.md), [API 0.3.0](../docs/api-contract.md), [API v1 đề xuất](../docs/api-san-pham-v1.md), [kiến trúc](../docs/kien-truc-homematch.md) và [AC sản phẩm](../docs/tieu-chi-nghiem-thu.md). Đây là công việc đích; checklist không ghi là xong khi chưa có evidence. Các mã HM-xx.BE-ACn dưới đây là tiêu chí kỹ thuật bổ sung, không thay bộ AC sản phẩm.

## Nền chung ở P0

- Khóa domain, role/membership/assignment, state transitions và public/AI source mode.
- Thiết kế schema/migration/constraints/DTO hiện tại và đích riêng; không sửa OpenAPI 0.3.0 để mô tả route chưa viết.
- Khóa rules null/zero, revision/CAS, key scope/replay, errors và retention từng loại hồ sơ.
- Chọn transaction boundaries và ownership cho media/audit/outbox; lập fixture ít nhất hai organizations và bốn roles.
- Tiếp tục một API worker. Audit multi-process/checkpointer là task riêng trước mọi tăng replica.

## HM-01 — Tài khoản, vai trò và cách ly

**Phụ thuộc:** P0 và HM-10 nền. **Hiện có:** seed auth, token expiry/revoke, renter/manager và session ownership/assignment.

**Trạng thái 04/10/2026 (W-01/W-03):** đã có bốn vai trò và ma trận quyền duy nhất (`app/capabilities.py`), organization/membership/audit (`app/organizations.py`, migration v3), register/verify/reset/profile/consent/session revoke (`app/auth.py`) với stub email ghi log; ca âm quyền organization và lifecycle có checks. **Chưa có:** rate limit auth, thu hồi token khi account disable, permission cho media/jobs/export, recovery giao cấp membership.

**Các bước còn lại:** account register/verify/recover/password/session lifecycle; memberships/role grants/assignment có audit; permission service áp dụng API/media/jobs/export; auth rate limits và thu hồi khi role/account đổi. Không nhận role/org quyền từ client.

**Nghiệm thu:** HM-01.BE-AC1 — renter/owner/manager/admin hoàn thành tác vụ đúng phạm vi; user khác/org khác bị chặn kể cả đoán IDs và media URLs. HM-01.BE-AC2 — logout/revoke/account disable hết hiệu lực token; login/recovery sai không lộ credential hoặc account details. HM-01.BE-AC3 — background job không đọc dữ liệu ngoài scope/recipient đã xác minh.

**Bàn giao:** permission matrix, migrations, session policies và API negative report → FE/Infra.

## HM-02 — Inventory, media và moderation

**Phụ thuộc:** HM-01/10. **Hiện có:** canonical room JSON/import/revision/read/status toggle; schema v3 đã có `hm_room_ownership` và projection allowlist (`app/projection.py`) làm nền public (trạng thái W-02, 04/10/2026). CRUD property/room/listing, media, moderation states và public API chưa có mã.

**Các bước:** property/room/listing/fee/evidence CRUD; physical_room_id stable khác listing_id/published_revision, unique(organization,building,room_code), mapping migration room.id hiện tại; tách publication và occupancy; upload/media access/size/type checks; owner submit, admin/authorized moderator review, revision mới; public projection và catalog invalidation; canonical merge có audit.

**Nghiệm thu:** HM-02.BE-AC1 — owner sửa tài sản mình; submitted/changes_requested/draft/suspended không truy public. HM-02.BE-AC2 — sửa giá/phí/availability tạo revision và invalidates run liên quan; cùng revision khác data conflict. HM-02.BE-AC3 — media/chứng từ riêng không truy qua URL chéo org; phí missing không thành 0.

**Bàn giao:** import/migration/quality rules, moderation states, public DTO, media permissions → FE/Data.

## HM-03 — Public search, detail và map

**Phụ thuộc:** HM-02. **Hiện có:** matching filter/location; chưa public discovery API.

**Các bước:** filters/sort/pagination ổn định, detail và map projection; query validation, canonical dedup, availability/unknown policy; nguồn/timestamp/sai số; một schema tiêu chí giữa form/chat khi áp dụng. Không chuyển map thành thời gian đi lại.

**Nghiệm thu:** HM-03.BE-AC1 — query chỉ trả published listing hiện hành và tôn trọng hard filters; pagination không trùng canonical rooms. HM-03.BE-AC2 — detail không lộ contact/private docs/AI draft; map gần đúng có label. HM-03.BE-AC3 — public mode không tạo approval AI hay vượt permission.

**Bàn giao:** filter dictionary, public DTO/fixtures và API/map tests → FE/Agent.

## HM-04 — AI, finance và HITL

**Phụ thuộc:** HM-01/02/03; phối hợp Agent. **Hiện có:** cost/B1/P adapter, two graphs, CAS/snapshot/review/checkpoint.

**Các bước:** giữ cost Decimal/rules/null, eligible set chung B1/P; field evidence/provenance; schema/model errors/quota, cache có version/quyền; review commit-before-resume, validity trước review/publish/read; controlled recovery và crash windows. Manager chỉ subset/reorder hợp lệ.

**Nghiệm thu:** HM-04.BE-AC1 — oracle exact VND/null/known/missing; rent thấp nhưng total vượt bị loại, unknown hard không pass. HM-04.BE-AC2 — pending/reviewed/stale không trả AI items qua results/detail/compare/stream. HM-04.BE-AC3 — wrong manager, stale profile/catalog, duplicate key hoặc restart không bypass HITL; replay khác payload conflict. HM-04.BE-AC4 — provider unavailable có fallback form/algorithm rõ; fixtures không ghi live quality.

**Bàn giao:** finance/matching interface, state/error dictionary, event/retry tests → Agent/FE/Eval.

## HM-05 — Lưu, lịch sử và so sánh

**Phụ thuộc:** HM-03/04 và privacy HM-10. **Hiện có:** compare AI 2–3 cùng published/current run.

**Các bước:** favorites/historical views/session history đồng bộ actor; tách history/preferences/checkpoint và retention, opt-out history khác minimum operational checkpoint/ledger có purpose/TTL đã thông báo; xóa/clear/export đúng scope; public compare snapshot listing revisions cùng scenario; AI compare current run; stale/hidden listing hiển thị trạng thái không lộ dữ liệu.

**Nghiệm thu:** HM-05.BE-AC1 — lưu/bỏ lưu replay không tạo trùng; đổi thiết bị/account đọc đúng và truy chéo bị chặn. HM-05.BE-AC2 — 2–3 phòng cùng scenario, source mode rõ; pending/stale AI không compare được. HM-05.BE-AC3 — xóa history không tự xóa hợp đồng/công nợ hoặc preferences nếu người dùng chưa chọn.

**Bàn giao:** history/privacy schema, compare DTO và sync/stale report → FE.

## HM-06 — Viewing, handoff và notifications

**Phụ thuộc:** HM-01..05. **Hiện có:** viewing requested/confirmed/declined, support requested nội bộ.

**Các bước:** refs discriminated public_catalog(listing_id,published_revision), server resolve physical_room_id hoặc ai_recommendation(run_id,profile_version,catalog_version,room_ids cùng published/current run), không mixed mode; timezone/slot/request/cancel/reschedule/completed/no_show; owner đề xuất slot, assigned manager confirm; handoff open/in_progress/resolved/closed và assignment/ack riêng; notification preferences/read state; outbox cùng transaction, worker lease/dedup/backoff/dead-letter và operator retry.

**Nghiệm thu:** HM-06.BE-AC1 — requested không reserve; đổi/hủy/lỗi stale có transition/version; người không được giao không respond. HM-06.BE-AC2 — crash sau commit hoặc retry delivery không tạo thêm viewing/ticket/notification; lỗi channel không mất business record. HM-06.BE-AC3 — “đã kết nối” chỉ sau người xử lý nhận, notification không lộ private payload.

**Bàn giao:** queue/worker interface, transitions và crash/delivery report → FE/Infra.

## HM-07 — Hợp đồng, tenancy và bàn giao

**Phụ thuộc:** HM-02/06/10. **Hiện chưa có domain/API.**

**Các bước:** agreements/terms/reservation expiry; reservation interval+expiry/lease allocation conflict theo physical_room_id trong transaction; convert reservation→lease atomic, active contract/planned allocation chặn overlap; contract expired không release occupied trước recorded move-out; contract draft/pending_acceptance/active/cancelled/termination_pending/ended/expired, terms version/document hash/acceptance; activation cần renter và owner/authorized manager, tạo allocation phòng/kỳ chống active contracts giao nhau; tenancy planned rồi active sau move-in, ending/closed; checklist hiện trạng/ảnh/chỉ số/cọc, move-out/closing/settlement; deduction cọc proposed/accepted/disputed, dispute hold không tự khấu trừ/financial settlement settled. Records/consent là bắt buộc; e-sign pháp lý optional.

**Nghiệm thu:** HM-07.BE-AC1 — sửa terms làm acceptance cũ mất hiệu lực; không activate thiếu một bên/ủy quyền. HM-07.BE-AC2 — viewing/request không giữ phòng, reservation có agreement/expiry và concurrent transaction không giữ trùng. HM-07.BE-AC3 — tenancy active/availability occupied chỉ sau move-in; move-out có handover và unresolved money/maintenance rõ, không tự mất ledger.

**Bàn giao:** contract/tenancy state model, document access/consent và overlap tests → FE/Data/Infra.

## HM-08 — Công tơ, hóa đơn và đối chiếu

**Phụ thuộc:** HM-07 và finance HM-04. **Hiện chỉ engine estimate.**

**Các bước:** meters/readings/evidence/close kỳ, reset/change meter; cumulative readings và consumption delta; kỳ [start,end), tariff default hiệu lực đầu kỳ, midperiod áp kỳ sau trừ accepted amendment+measured boundary để split segments; replacement usage old_last−old_start+new_end−new_first, unknown segment chặn actual issue; deterministic invoice lines/version/issue/void/adjustment; lifecycle status draft/issued/void tách payment_status unpaid/partially_paid/paid và overdue tính balance > 0, now > due_at; manual payment declaration/evidence, received receipt, allocations/partial/overpayment/dispute/reconciliation; duplicate evidence detection hỗ trợ người kiểm tra, không coi heuristic là proof gian lận.

**Nghiệm thu:** HM-08.BE-AC1 — readings giảm/kỳ overlap/thiếu tariff bị chặn hoặc cần xử lý rõ; estimate không thành invoice. HM-08.BE-AC2 — invoice khớp oracle exact VND; issued snapshot không đổi theo tariff sau đó; correction giữ bản gốc. HM-08.BE-AC3 — renter “đã chuyển” không tự thành paid; received/reconcile đúng actor, partial/duplicate/retry không double-count; thừa/thiếu/dispute có lịch sử.

**Bàn giao:** financial rules/oracles interface, reconciliation/audit reports → FE/Data/Eval.

## HM-09 — Sửa chữa

**Phụ thuộc:** HM-07/06 và media HM-02. **Hiện chưa có domain/API.**

**Các bước:** ticket theo tenancy/resource, ảnh/mô tả, urgency/triage, assignment/schedule/progress, completion evidence/tenant confirm/reopen/cancel; chi phí có payer và đúng bên chịu tiền chấp thuận hoặc căn cứ terms snapshot đã xác minh; owner approve kỹ thuật không đủ charge renter, disputed charge chưa là khoản phải thu xác định; không invoice tự động từ chat.

**Nghiệm thu:** HM-09.BE-AC1 — chỉ bên tenancy/manager/owner đúng scope đọc/tạo/chuyển ticket; ảnh private. HM-09.BE-AC2 — trạng thái/lịch đổi có audit/notification, replay không trùng; closed ticket có evidence và reopen có lý do. HM-09.BE-AC3 — booking thợ/chi phí chưa được chấp thuận không được diễn đạt đã xác nhận.

**Bàn giao:** ticket/appointment rules, permission/lifecycle report → FE.

## HM-10 — Admin, privacy và vận hành

**Phụ thuộc:** cắt ngang từ P0. **Hiện có:** readiness/process metrics, review ledger, backup/restore scripts chưa tự là bằng chứng restore.

**Các bước:** console phân quyền/moderation/ops; audit actor/resource/version/reason và access sensitive; retention/export/delete có policy cho transactional records; rate limits/uploads/secrets/log review; durable metrics/alerts; migration/restart/restore/rollback runbook.

**Nghiệm thu:** HM-10.BE-AC1 — mỗi mutation nhạy cảm và truy cập admin có audit, không raw PII/chat/credential trong log. HM-10.BE-AC2 — export/delete đúng actor/scope, retained records có lý do/thời hạn, checkpoints/media không bị bỏ sót. HM-10.BE-AC3 — restored DB/media giữ quyền/version, pending không publish, financial ledger khớp; readiness không ok khi schema/checkpoint lỗi.

## P4 — Hoàn thành tích hợp

Bốn role chạy xuyên suốt published listing → public/AI discovery → save/compare → viewing → acceptance → move-in → meter/invoice/payment/reconcile → maintenance → move-out. Chạy cả ca quyền âm, stale/tab cũ, replay, network failure và restart ở các commit windows. Test nhiều request trong một process không chứng minh nhiều API worker.

Gói bàn giao: contract thực thi có version, migrations/rollback, fixture IDs/hashes, actual checks/limitations, restore evidence và runbook. P5 research riêng giữ freeze/independent labels; không tự đổi dataset/manifests trong việc viết plan này. Legacy BE task IDs là lịch sử, không nguồn scope mới.
