# AI Agent — công việc chi tiết cho sản phẩm hoàn thiện

Phiên bản 04/10/2026. [PLAN](AGENT_PLAN.md) và [thiết kế](../docs/thiet-ke-agent.md) là nguồn phạm vi; [Backend](DETAILED_PLAN.md) giữ transaction/quyền/finance. Các HM-xx.AG-ACn là AC kỹ thuật bổ sung. Chưa đánh dấu xong chỉ vì có code hoặc fixture.

## HM-01/10 — Quyền, context và provider

**Phụ thuộc:** P0 permission/DTO/privacy; hiện có redaction phổ biến và giới hạn adapter.

- Khóa allowlist tools theo intent/actor/resource; kiểm lại tại service, không nhận role/org/approval từ model.
- Context chỉ draft chuẩn hóa/lượt mới và read DTO tối thiểu đã có quyền. Contract/payment media không đưa provider mặc định.
- Quota/token/step budgets cưỡng chế, timeout/retry hữu hạn, usage unavailable khác 0, model/prompt/schema version.
- Test prompt injection trong chat/tin/tool/upload, role forgery, PII và refusal/incomplete/error. Tool output luôn là dữ liệu.
- Log/trace giảm dữ liệu; history/preferences/checkpoint retention có owner/scope.

**AC:** HM-10.AG-AC1 — injection không đổi tool/quyền/HITL; wrong resource bị chặn ngoài model. HM-10.AG-AC2 — spy/fake kiểm limits/error, live logs kiểm usage khi có; không raw chat/tài chính/credential. HM-10.AG-AC3 — provider unavailable có form/error thật, không auto-switch model/bịa.

**Trạng thái 05/10/2026:** AG-AC1 có mã + test offline (ma trận `agent_capability`, chặn resume payload đặc quyền, quarantine injection, wrong owner/role/forged-role bị chặn). AG-AC3 có fallback guided-form kèm mã lỗi (`ai_unavailable`/`context_limit`), `budget_exceeded` 429, không retry storm (test 1 lần gọi provider). AG-AC2 mới có phần offline (redact PII vào trace/diagnostics/checkpoint, budget spy); chưa có live logs/usage thật. Provenance hiện ở `agent_trace` service-level; lộ HTTP chờ schemas. Handoff chat vẫn là "requested" (ticket idempotent per session, chưa có lifecycle accepted); viewing từ chat chỉ chuẩn bị + kiểm approved/current, không tạo lịch.

## HM-02/03 — Catalog và từ điển

**Phụ thuộc:** listing moderation/public projection/evidence.

- Khóa mapping tiếng Việt/có-không dấu/từ đồng nghĩa vào room types/amenity/location.
- Public navigation dùng listing published revision và source public_catalog; AI context không dùng pending item để mở public đường vòng.
- Unknown tiện ích/fee/vị trí giữ unknown; bằng chứng theo revision, không suy address hoặc phút di chuyển.
- Filters/chat dùng schema thống nhất nhưng thay hard condition cần renter confirm.

**AC:** HM-03.AG-AC1 — fixture nói mơ hồ không tự thêm city/school/amenity true. HM-03.AG-AC2 — public response không có AI approval; AI pending không lộ qua tool/detail/stream. HM-03.AG-AC3 — nguồn hoặc version thiếu được ghi thiếu, không bịa.

## HM-04 — Hiểu nhu cầu và confirm

**Phụ thuộc:** draft/profile schema/CAS, dev gold fixtures; hiện có draft status/evidence/rules.

- Extraction strict schema, nullable unknown; inferred khác confirmed; money hint không thành budget confirmed.
- Hỏi tối đa hai mục quan trọng/lượt: city/type, rent/total, people/vehicles, destination/campus/radius, hard/soft, upfront/usage.
- Sửa/xóa/rephrase preferences và fields, không merge vô hạn; câu mới cập nhật draft, không silent mutate confirmed profile.
- Form xác nhận assumptions/units/hard/soft; CAS conflict đọc lại, không auto-resend message/confirm.
- Cost/support rõ route trực tiếp. Parse/refusal/error chuyển form, không giả model extraction thành success.

**AC:** HM-04.AG-AC1 — “3 triệu gần trường thoáng” hỏi rõ hoặc form, không tự TP.HCM/trường/budget. HM-04.AG-AC2 — thay/xóa giữ revision/provenance; tab cũ conflict, confirmation chỉ actor UI. HM-04.AG-AC3 — cost/support rõ không gọi LLM; lỗi model giữ draft an toàn và state rõ.

## HM-04 — Finance, matching, explanation và HITL

**Phụ thuộc:** Backend cost/eligible/ranking/event/checkpoint; hiện có hai graph.

- Tools nhận confirmed snapshot, không query SQL tự do. Finance Decimal/null/source/assumptions giữ nguyên từ tool.
- B1/P cùng eligible set; semantic text loại money/contact, query embedding chỉ sau confirm; fallback algorithm rõ.
- Template explanation từ evidence/cost lines; unknown không thành true, commission/stock không tín hiệu.
- Persist draft trước interrupt; review chỉ service commit event/assignment/version. Resume bằng event ID, không boolean chat.
- Stale before review/publish/read, restart pending, crash commit-before-resume, generating retry run mới cần approval mới.
- Worker recovery chỉ sau backend policy/lease/checkpointer tests; không tăng API worker tự động.

**AC:** HM-04.AG-AC4 — renter pending không có card/items/diagnostics ở mọi projection/tool/stream. HM-04.AG-AC5 — wrong manager/stale/replay/restart không công bố; event đã ghi resume idempotent. HM-04.AG-AC6 — exact money do tool; claim có nguồn/version và P fallback không ghi P quality.

## HM-05 — Lịch sử, sở thích và so sánh

**Phụ thuộc:** account/history/privacy/public/AI compare.

- Phân biệt chat history, saved rooms, confirmed preferences và checkpoint; consent memory/xóa được; opt-out history khác operational checkpoint/ledger purpose/TTL thông báo.
- Không gửi transcript toàn bộ hoặc ngầm nhớ budget/contact xuyên phiên.
- Public compare dùng revisions + chung scenario; AI compare cùng published/current run, 2–3 rooms.
- Stale/hidden room hướng dẫn refresh/review; không giữ nhãn valid sau thay dữ liệu.

**AC:** HM-05.AG-AC1 — clear history không silent mất contract/invoice; context không kéo phiên user khác. HM-05.AG-AC2 — compare pending/stale bị chặn, source/assumptions rõ.

## HM-06 — Lịch và người thật

**Phụ thuộc:** viewing/handoff/outbox services.

- Agent chuẩn bị request/timezone/source; UI actor gửi; requested không giữ room.
- Owner đề xuất slot; assigned manager confirm/decline; cancel/reschedule/completed/no_show đọc đúng event.
- Handoff open → in_progress → resolved → closed, assignment/ack riêng; người chưa tiếp nhận không nói đã kết nối.
- Notification do server từ event/recipient quyền; model không gửi email/chat ra bên ngoài.

**AC:** HM-06.AG-AC1 — câu “đặt lịch” chưa thành confirmed/reserved; tool read phản ánh actual state. HM-06.AG-AC2 — channel failure/retry không đổi business state hoặc báo đã nhận khi chưa có acknowledgment.

## HM-07 — Hợp đồng và thuê

**Phụ thuộc:** contract/acceptance/tenancy/handover services; tools đích chưa có.

- Read/navigation có quyền theo chosen tenancy; tóm tắt terms từ version/document, không thêm cam kết.
- Dẫn renter/owner/authorized manager đến form acceptance; sửa terms yêu cầu acceptance mới.
- Active tenancy sau move-in, planned/ending/closed rõ; contract expired không tự release occupied trước move-out; reservation là agreement riêng có expiry.
- Không quảng bá app consent thành e-sign pháp lý.

**AC:** HM-07.AG-AC1 — chat không activate contract/tenancy hay reserve; form/service actor/version quyết định. HM-07.AG-AC2 — tóm tắt khớp terms hiện hành, thiếu terms không tự bổ sung; user khác không đọc.

## HM-08 — Invoice và payment

**Phụ thuộc:** deterministic billing/payment/reconcile DTOs.

- Phân biệt estimate, issued invoice, declaration transferred, receipt received và reconciled balance. Invoice lifecycle draft/issued/void, payment_status unpaid/partially_paid/paid và computed overdue độc lập.
- Không tính số từ model; đọc totals/breakdown/corrections từ engine/ledger. Cumulative reading khác usage delta; kỳ/rate/segments/replacement do finance rule xác định, unknown segment không actual issue.
- Hướng dẫn payment evidence/partial/dispute forms; actor xác nhận ghi nhận tiền; không gọi gateway mandatory.

**AC:** HM-08.AG-AC1 — “tôi đã chuyển” không tự đổi paid; bill totals đúng tool và revision. HM-08.AG-AC2 — reading thiếu/adjustment/remaining amount được nói đúng trạng thái, không che dispute.

## HM-09 — Maintenance

**Phụ thuộc:** tenancy/ticket/media/appointment services.

- Hướng dẫn hoặc prepare form ticket/ảnh, chọn tenancy đúng quyền; actor gửi.
- Đọc triage/schedule/progress/completion evidence/reopen; không tự hứa thợ/chi phí nếu chưa confirm.
- Cost billing từ maintenance cần payer, đúng bên chịu tiền chấp thuận hoặc căn cứ terms snapshot xác minh; owner technical approval chưa đủ thu renter, disputed charge chưa là phải thu xác định.

**AC:** HM-09.AG-AC1 — private photos/ticket không truy chéo; scheduled khác đề xuất. HM-09.AG-AC2 — completion/reopen đúng actor/evidence, chat không tự tạo invoice.

## Gates và gói bàn giao

P2 đóng regression schema/draft/routing/finance/HITL/viewing/handoff; P3 đủ navigation/read và service confirmations trên vòng đời thuê; P4 browser/error/quota/privacy/injection/runbook; P5 riêng frozen provider/research.

Bàn giao prompts/config/schema hashes, tool contracts, dev error analysis, regression/live mode evidence, usage và limitation. Fake SDK/graph fixtures chỉ chứng minh hành vi kỹ thuật. Live quality phải chạy provider thật, protocol/split khóa và độc lập labels; ngưỡng research đã có trong protocol không tự thành release kết quả. ID AG cũ giữ lịch sử.

