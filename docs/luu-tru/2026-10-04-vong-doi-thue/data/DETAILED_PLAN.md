# Data — kế hoạch chi tiết theo vòng đời thuê

Phiên bản 04/10/2026. Đọc [PLAN](PLAN.md), [README hiện tại](README.md), [Backend detailed plan](../backend/DETAILED_PLAN.md) và [AC sản phẩm](../docs/tieu-chi-nghiem-thu.md). HM-xx.DATA-ACn là AC kỹ thuật bổ sung; paths/bộ dữ liệu đích chưa có không được ghi là đã tạo.

## P0 — Dictionary và nguồn

- Khóa vocabulary room/property/listing, renter/organization, role/assignment, source mode public_catalog/ai_recommendation.
- Khóa unit/null/zero/evidence/version/timezone/financial snapshot và state dictionary từng HM.
- Source register ghi quyền/phạm vi sử dụng/tái phân phối/ngày/real-synthetic; khảo sát HubHome không quyền export/crawl.
- Phân public/private/sensitive/transactional data, retention/export/delete và media metadata.
- Giữ dataset development/manifests hiện tại. Tạo dataset version mới khi mở rộng, không overwrite frozen inputs.

**AC chung:** Mỗi field có unit/type/unknown/source/owner; source thiếu quyền không vào production/research share; expected outcomes không sao chép từ engine được test.

## HM-01/10 — Isolation và governance fixtures

**Phụ thuộc:** roles/membership/assignment/privacy design.

- Tạo ít nhất hai organizations, renters/owners/managers/admin, account sessions/role changes/disable/revoke.
- ID guesses, manager reassignment, owner ở hai tổ chức, renter liên quan nhiều đơn vị nhưng private profile chỉ owner chính.
- Media/export/job/notification/audit cross-scope cases; admin access reason.
- Retention/delete/backup-restore fixtures tách hồ sơ có thể xóa và ledger cần giữ có lý do.
- Dùng credential/PII giả; tài khoản seed không trở thành dữ liệu thật.

**AC:** HM-01.DATA-AC1 — mỗi permission path có allow/deny expected và actor/resource/org cụ thể. HM-10.DATA-AC1 — delete/export không bỏ checkpoint/media hoặc mất records cần đối chiếu; audit không raw secrets/chat.

## HM-02 — Catalog và evidence

**Phụ thuộc:** listing/media/moderation schema.

- physical_room_id ổn định, unique(organization,building,room_code), khác listing_id/published_revision; mapping room.id hiện tại trong migration phải rõ. Property chứa nhiều canonical rooms; nhiều listing aliases cùng room không tăng lựa chọn.
- Fee rules fixed/person/vehicle/kwh/m3/included/missing/zero; unsupported tariff ghi cần xác minh.
- Draft/submitted/changes_requested/published/suspended/archived, stale revision, unavailable/unknown/reserved/occupied.
- Evidence theo field/source/observed/effective/revision; mâu thuẫn ghi cách xử lý, không tự chọn giá thấp nhất.
- Public photo/private document fixtures có hash/owner/access class.

**AC:** HM-02.DATA-AC1 — catalog validates/dedup canonical, unknown giữ null; version conflict và private media có ca âm. HM-02.DATA-AC2 — quality report đếm nguồn/aliases/moderation/missing/stale/location accuracy, không coi 80 synthetic là kho thị trường.

## HM-03 — Public discovery

**Phụ thuộc:** catalog public projection và query contract.

- Hard/soft filters, sort ties/pagination, type/area/capacity/amenity/availability.
- Map exact/approximate/area_only và boundary với uncertainty; tọa độ fixture không address thật.
- Public detail costs/source/timestamp/unknown; nháp moderation và AI drafts không trong expected public.
- Expected IDs/filter decisions ghi độc lập; không lấy actual match output làm expected.

**AC:** HM-03.DATA-AC1 — public mode chỉ published listing, pagination canonical không trùng; accuracy/unknown expected rõ. HM-03.DATA-AC2 — fixture gần trường không được label phút đi lại.

## HM-04 — Agent, finance và relevance

**Phụ thuộc:** extraction/profile schemas, finance/ranking interfaces, Eval protocol.

- Giữ 30 hồ sơ gốc/10 dev/20 test hiện tại và paraphrase cùng group; dataset mới phải có version.
- Gold utterance intent/fields/ambiguity/edit/remove; ngân sách local/form không tự vào model field F1.
- Mơ hồ city/school/rent-total/usage/hard-soft, no-match/needs-verification/provider failure.
- Cost oracle independent constants/formulas cho included/null/0/person/vehicle/kwh/m3/deposit/advance/rounding/boundary.
- Blind union top5 B1/P canonical sau freeze; ẩn method/score/rank, xáo có seed; labels người 0–3/evidence/reason.
- Người kiểm tra chéo gold/oracle, adjudication nếu có; thiếu judge giữ pending, không LLM tự chấm.

**AC:** HM-04.DATA-AC1 — oracle exact VND/known/null/missing và đầu vào/công thức tự kiểm được. HM-04.DATA-AC2 — profile grouping/split không leak; labels đầy đủ top cả methods, method mapping riêng. HM-04.DATA-AC3 — P unavailable không tạo pool giả từ B1; labels thiếu không thành 0.

## HM-05 — Favorites/history/compare

**Phụ thuộc:** account/history/privacy/public-AI schema.

- Lưu/bỏ lưu/replay, viewed/history sync qua device, hidden/stale listing, account khác.
- Clear/opt-out history khác preferences và minimum operational checkpoint/ledger có purpose/TTL đã thông báo; consent/memory expiry.
- 2–3 phòng chung scenario, public listing revisions và AI same current/published run; mode lẫn hoặc pending/stale cần expected fail.

**AC:** HM-05.DATA-AC1 — fixtures mô tả source/scenario/versions, conflict và delete scope; không raw user history.

## HM-06 — Viewing, handoff và delivery

**Phụ thuộc:** lifecycle/event/outbox contract.

- Timestamp timezone-aware, quá khứ/DST nếu hỗ trợ, slot conflict; owner đề xuất/manager confirm; requested không reservation.
- Cancel/reschedule/completed/no_show/declined, requester/assignee wrong actor.
- Handoff open/in_progress/resolved/closed, assignment/ack riêng, recipient reassignment.
- Outbox commit/crash/retry/dedup/dead-letter/read notification với expected business state độc lập channel success.

**AC:** HM-06.DATA-AC1 — expected không đồng nhất sent với accepted hoặc requested với confirmed; replay keys/payloads và rights đủ ca.

## HM-07 — Agreement, contract và tenancy

**Phụ thuộc:** terms/reservation/acceptance/handover rules.

- Contract draft/pending_acceptance/active/cancelled/termination_pending/ended/expired và acceptance riêng, document hash/terms revision; renter+owner/authorized manager acceptance, một bên missing hoặc acceptance cũ.
- Reservation chỉ agreement riêng có interval+expiry; concurrent hold/overlap theo physical_room_id; convert đóng reserve và lease allocation atomic.
- Planned tenancy allocation chặn kỳ chồng → move-in handover → active/occupied → ending → closed; occupant/room dates, ảnh hiện trạng/chỉ số/cọc.
- Contract activation allocation physical_room_id/kỳ chặn active contracts/planned allocation overlap; expired không tự release occupied trước recorded move-out; occupancy occupied sau move-in. Move-out/closing/closed có final reading/settlement, deduction cọc proposed/accepted/disputed và dispute hold không tự khấu trừ/financial settlement settled; outstanding invoice/damage/maintenance không tự biến mất.
- Document fixture minh họa, không copy legal template có tuyên bố hiệu lực.

**AC:** HM-07.DATA-AC1 — sửa terms đòi accept lại, contract active sau acceptance/activation, tenancy active chỉ sau move-in; overlap/expiry/unresolved settlement expected rõ. HM-07.DATA-AC2 — contracts private và app consent không label pháp lý e-sign.

## HM-08 — Meter, invoices và payment oracles

**Phụ thuộc:** billing/tariff/prorate/receipt/allocations rules đã khóa.

- Bộ financial oracle mới độc lập: cumulative readings khác usage delta; kỳ [start,end), default rate hiệu lực đầu kỳ; midperiod change áp kỳ sau trừ accepted amendment+measured boundary split segments; replacement usage old_last−old_start+new_end−new_first, unknown segment chặn actual issue. Bao gồm readings/tariffs/invoice kỳ, fixed/person/vehicle/consumption/prorate, rounding/due dates.
- Reading cuối thấp hơn đầu/reset/thay meter, kỳ overlap/missing/evidence dispute; estimate tách actual.
- Invoice lifecycle draft/issued/void; payment_status unpaid/partially_paid/paid; overdue computed balance > 0 và now > due_at, test partial+overdue đồng thời. Issued snapshot, đổi tariff về sau, void/adjustment có linked original.
- Transfer declared/evidence/received/reconciled, partial/multiple/overpayment/duplicate/rejected/disputed/refund và remaining balance.
- Oracle không tự gọi backend costs/invoice engine; người kiểm tra formula/expected constants.

**AC:** HM-08.DATA-AC1 — invoice/reconcile exact VND; duplicate không double-count, sum allocations/số dư truy được formula. HM-08.DATA-AC2 — renter transferred không paid, version correction không overwrite history.

## HM-09 — Maintenance lifecycle

**Phụ thuộc:** tenancy/media/schedule/cost rules.

- Ticket thuộc active/closing tenancy, urgency/triage/assignment, proposed/confirmed appointment, progress/completion evidence/confirmation/reopen/cancel.
- Cross-tenancy/org và private photos, inaccessible/deleted media.
- Quote repair fee khác approved fee/invoice allocation; có payer và đúng bên chịu tiền chấp thuận hoặc căn cứ terms snapshot đã xác minh, owner approve kỹ thuật chưa đủ charge renter; disputed charge chưa phải thu xác định. Không tự billing từ chat.

**AC:** HM-09.DATA-AC1 — expected quyền/transitions/notifications/completion/reopen rõ; cost chưa confirmed không thành debt.

## P4/P5 — Packaging và freeze

Bộ release fixtures version riêng cho HM-01..10 với dictionary/source/rights, synthetic flags, IDs/hash, expected outcomes/oracles và quality report. Integrity checks orphan/foreign keys/canonical/version/period/amount; restore pack theo Infra giữ same references/số dư.

P5 research riêng: code/config/prompt/catalog/gold/split freeze → fixed B1/P outputs → blind human labels → label hash → metrics. CLI hiện dùng G4 acknowledgment theo workflow cũ; không tự chuyển thành P4 bằng sửa manifest/protocol trong lần viết docs. Release product và research freeze là hai evidence scopes.

Bàn giao Eval/Backend/Infra raw fixtures đã giảm nhận diện, formulas/expected/constants, manifests/status/limitations. DATA-01..07 lịch sử không còn source phạm vi sản phẩm.
