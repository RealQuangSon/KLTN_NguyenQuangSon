# Kế hoạch chi tiết frontend HomeMatch

**Cập nhật 04/10/2026.** Theo [PLAN](PLAN.md) và [UI_SPEC](UI_SPEC.md), phạm vi là sản phẩm HM-01…HM-10 toàn vòng đời thuê. Mã FE-01…FE-10 giữ để truy vết nhưng đã mở rộng; FE-11…FE-18 bổ sung công việc. API 0.3.0/source hiện tại chỉ có subset trước thuê hai vai trò; API v1 và các screen mới là mục tiêu triển khai.

Đọc cùng [đặc tả](../docs/dac-ta-san-pham.md), [yêu cầu](../docs/yeu-cau-san-pham.md), [quy trình](../docs/quy-trinh-nghiep-vu.md), [nghiệm thu](../docs/tieu-chi-nghiem-thu.md) và [contract API mục tiêu](../docs/api-san-pham-v1.md). Không dùng các task dưới đây như chứng cứ đã hoàn thành. Không ấn định ngày/số giờ khi chưa xác nhận dependencies.

## Quy tắc áp dụng cho mọi task

- Component có DTO, role/scope, state loading/empty/error/success và mutation/version khi cần; fixtures không đi vào runtime fallback.
- Backend quyết định tiền/quyền/ranking/publication; client không đọc checkpoint/raw graph hoặc tự suy state transition.
- Action có API thật, validation, receipt/status và error handling; disable/ẩn theo projection nhưng vẫn kiểm thử enforcement backend.
- Evidence ghi source/API/data/config/môi trường/provider và bước đạt/chưa đạt. UI test không thay API/browser hoặc quality evaluation.
- Các mã `FE-xx.ACn` là tiêu chí riêng của task, nối HM module và UI-V IDs; tiêu chí nghiệp vụ chính theo docs sản phẩm. Không dùng AC cũ để miễn các module mới.

## FE-01 — Contract, evidence và coverage · P0

**Đầu vào:** nghiên cứu HubHome, source/types/API 0.3.0, product modules và API v1 mục tiêu. **Đầu ra:** screen/action/DTO/state matrix; reference register; fixture synthetic theo phiên bản contract.

- [ ] Audit App, Landing, hai workspace, Shared/ProfileForm/ViewingPanel, types/API/styles/tests; phân biệt source có, kiểm thử đã ghi và target.
- [ ] Chốt physical_room_id riêng listing_id/published_revision, public catalog vs AI recommendation projection, role/scope/assignment và target entity/version/error/key semantics.
- [ ] Chốt state machines lịch, contract, tenancy, handover, meter, invoice/payment và ticket trước xây mutation screens; đồng bộ tài liệu backend.
- [ ] Register tham chiếu gồm URL/ngày/viewport/state/phần chưa quan sát; giữ preview lịch sử như artifact riêng, không coi là baseline full product.

**FE-01.AC1:** S01…S21 và HM-01…HM-10 có owner task, API dependencies và nghiệm thu; không còn chức năng bắt buộc bị bỏ vì phạm vi cũ. **AC2:** Mỗi trường/screen phân biệt đã quan sát/website công bố/thiết kế HomeMatch/current implementation; target endpoint không bị trình bày là có sẵn.

## FE-02 — Token, landing, route và shell bốn vai trò · P1

**Phụ thuộc:** FE-01, role/scope auth. **Đầu ra:** hệ token/component; route navigation; shell renter/owner/manager/admin.

- [ ] Áp dụng token trắng/xám–cam sáng, Inter local hợp lệ/fallback; tái dùng Icon/Brand/minh họa gốc.
- [ ] Landing giữa trang/composer/Tìm nhanh/câu mẫu/nội dung; giữ nhu cầu chưa gửi trong memory qua login, không đưa vào URL.
- [ ] Router/deep link/reload/back, title/landmark, 401/403/404; selector chỉ cho role/context server cấp, cache theo actor/scope.
- [ ] Nav nhóm tìm chỗ ở/đang thuê, các portal có mật độ phù hợp; không hiển thị CTA chưa nối API trong release.

**FE-02.AC1:** Deep link và reload tới từng shell kiểm tra server quyền, không flash dữ liệu actor trước. **AC2:** Logout/role switch/401 gỡ dữ liệu cũ; nhu cầu trước login chỉ được gửi chủ động một lần. **AC3:** UI-V01/02/03 đạt trên landing và shells.

## FE-03 — Assistant, draft và xác nhận · P2

**Phụ thuộc:** FE-02, session/draft/profile/run APIs. **Đầu ra:** rail/chat–preview, composer, QuickFilters và profile drawer.

- [ ] Desktop rail 60px/chat–preview 35/65, cuộn riêng; mobile tab/sheet giữ draft/scroll/focus.
- [ ] Chat/history dùng server contract; composer Enter/Shift+Enter/IME, sending/error/cancel/stale rõ.
- [ ] Filter/form/chat cùng draft revision; unknown/inferred/confirmed, hard/soft và finance/scenario phân biệt; budget hint không tự confirmed.
- [ ] Confirm có summary/profile version, AI trạng thái thực; đổi profile/run invalidation/awaiting review theo backend.

**FE-03.AC1:** Không tạo run trước xác nhận; corrections giữ finance/scenario không bị thay bằng inference cũ. **AC2:** Generating/pending/reviewed không render phòng AI hoặc CTA của ứng viên. **AC3:** Request session cũ không thay draft/results phiên mới.

## FE-04 — Listing moderation và recommendation HITL · P1/P2

**Phụ thuộc:** FE-02/06, moderation/review/assignment APIs. **Đầu ra:** hai queue và panel quyết định tách biệt.

- [ ] Listing review kiểm tra source/media/location/quote/availability và required fields; approve/reject/request changes theo revision.
- [ ] Recommendation review hiển thị confirmed profile/scenario/version, candidate/source/fees/diagnostics đúng quyền, subset/reason.
- [ ] CAS/conflict/retry cùng key-payload ở endpoint hỗ trợ; mất response đọc lại, không optimistic published.

**FE-04.AC1:** Listing approval chỉ làm tin đủ điều kiện public; không approve recommendation cá nhân hóa. **AC2:** Manager khác assignment không đọc/duyệt run; renter không truy cập preview nháp. **AC3:** Server trả subset nào renter chỉ thấy subset đó sau published/current.

## FE-05 — Discovery, detail và cost projection · P2

**Phụ thuộc:** FE-02/06/11, public search/details và renter results/cost APIs. **Đầu ra:** public room search/list/detail và preview AI dùng chung phần trình bày an toàn.

- [ ] Public filters/sort/pagination và query restoration theo contract; không apply quy tắc public sort lên AI rank đã duyệt.
- [ ] Card/list/detail có media, thuộc tính, quote/fees/availability/source/time/revision và quyền địa chỉ; phần thiếu có nhãn.
- [ ] Breakdown monthly/initial/known subtotal/full total/included/unknown; tiền thuê khác tổng ước tính và tiền ban đầu.
- [ ] Public refs `room_id+published_revision` và AI refs `run/profile/catalog+room_ids` published/current có projection/cache key riêng; listing thay revision/ẩn/hết phòng gỡ CTA trái rule.

**FE-05.AC1:** Public results chỉ tin moderation hợp lệ, AI results chỉ approved/current; không trộn nguồn ngầm. **AC2:** `null`, 0 và included đúng DTO/oracle; UI không tự tính/rank. **AC3:** Loading/error/no-match giữ nguyên filter và có bước tiếp không tự nới hard constraints.

## FE-06 — Owner inventory và kho quản lý · P1

**Phụ thuộc:** FE-02/18, owner/property/listing/quote APIs. **Đầu ra:** owner CRUD và catalog workbench theo scope.

- [ ] Nhà/phòng/editor: dictionary, diện tích, vị trí/độ công khai, amenities unknown/yes/no, giá/cọc/fees/đơn vị/kỳ và availability.
- [ ] Lưu nháp/preview/gửi moderation/sửa theo phản hồi; disable/archiving có tác động và receipt; bảo vệ nội dung chưa gửi khi rời màn.
- [ ] Manager chỉ quản lý tin/phòng được cấp scope; revision/CAS đọc lại nếu conflict, invalidation gợi ý theo backend.

**FE-06.AC1:** Owner A không đọc/sửa tin/media của owner B; form không tự publish khi save. **AC2:** Dữ liệu thiếu phí/vị trí/amenity không biến thành 0/exact/yes. **AC3:** Catalog update không bị request đọc cũ ghi đè và recommendation ảnh hưởng hết hiệu lực.

## FE-07 — Renter overview và lifecycle navigation · P2/P3

**Phụ thuộc:** FE-03/12/13/14 và overview APIs. **Đầu ra:** tổng quan, nhu cầu và entry points toàn vòng đời thuê.

- [ ] Tổng quan lấy số liệu server: việc cần làm, phiên/lưu/lịch, thuê active, hóa đơn/ticket; 0 khác chưa tải/chưa quyền.
- [ ] Nhu cầu/preferences/scenario có history/version theo contract; chuyển màn không tự tạo phiên mới.
- [ ] Chế độ tìm/đang thuê cho đúng tenant context, nhiều hợp đồng/tenancy có selector khi được phép.

**FE-07.AC1:** Counter/deep link phản ánh dữ liệu cùng account, không đếm AI candidate pending. **AC2:** Vẫn tìm chỗ ở mới khi có tenancy mà không mất context hợp đồng/tiền đang thuê. **AC3:** Postrent screen chưa có dữ liệu có empty state đúng tiền đề, không fake agreement/invoice.

## FE-08 — Trạng thái, cache và recovery · Xuyên suốt

**Phụ thuộc:** Error/version/key semantics từng API. **Đầu ra:** shared state/error handling và cache isolation.

- [ ] 401/403/404/409/422/429/503/network có thông điệp và bước tiếp riêng; giữ dữ liệu nhập cần sửa trong memory.
- [ ] Discard response theo actor/scope/session/entity/version/filter; abort/polling dừng khi rời màn/logout hoặc status kết thúc.
- [ ] Mutation không tự resend khi không biết kết quả; read state, retry cùng key/payload chỉ khi API hỗ trợ; receipt không giả success.
- [ ] Stale contract/invoice/meter/ticket có revision warning và action đúng rule, không overwrite server.

**FE-08.AC1:** Delay/loss/conflict không làm rò dữ liệu hoặc duplicate hành động tài chính/consent/lịch. **AC2:** Các trạng thái mục 5 UI_SPEC có coverage cho từng screen liên quan. **AC3:** Role/account switch không nhận notification/detail của context cũ.

## FE-09 — Visual QA, responsive và accessibility · Xuyên suốt/P4

**Phụ thuộc:** Mỗi screen đã tích hợp API và UI_SPEC. **Đầu ra:** ảnh, measurements và keyboard/mobile report.

- [ ] Đối chiếu tham chiếu cùng viewport/state tại vùng có evidence; màn bổ sung là thiết kế HomeMatch, không claim baseline HubHome chưa có.
- [ ] Desktop 1440×900/1280×720, tablet 768px, mobile 360px/390×844/320px, zoom 200%; bảng/map cuộn riêng, bàn phím mobile không che CTA.
- [ ] Keyboard/focus/labels/landmarks/status announcements, contrast và reduced motion; upload/splitter có alternative không kéo thả.
- [ ] UI-V01…16 và regression nghiệp vụ kiểm tra theo từng module, không chỉ landing.

**FE-09.AC1:** Không cuộn ngang toàn trang; mọi thao tác trọng yếu dùng được bằng keyboard/mobile. **AC2:** Contrast/focus measured; ảnh/screens evidence ghi rõ state và module. **AC3:** Độ giống không làm suy giảm quyền/null/0/stale/HITL.

## FE-10 — E2E và release evidence · P4

**Phụ thuộc:** FE-01…18 và backend/infra readiness của module bắt buộc. **Đầu ra:** bộ demo toàn vòng đời, release report và docs đúng source.

- [ ] Chạy current subset riêng khi cần regression; chạy product full lifecycle bốn vai trò với API thật cho P4.
- [ ] Bao gồm negative flows: wrong scope/actor, stale/overlap/slot conflict, notification retry, mất response, billing partial/dispute/correction, maintenance reopen.
- [ ] Kiểm chứng môi trường release, migration/backup/restore/recovery/ops/support cùng backend/infra; kiểm tra bundle/env public không secrets.
- [ ] Ghi versions, providers, số liệu test, screenshots/video và hạn chế; không dùng test/ảnh cũ để chốt screen mới.

**FE-10.AC1:** HM-01…HM-10 đều có nghiệm thu bắt buộc; P2 không được gắn “sản phẩm hoàn chỉnh”. **AC2:** Full lifecycle demo theo DEMO_CHECKLIST đạt với state/receipt có thật và quyền bốn vai trò. **AC3:** Optional gateway/legal e-sign/video platform/voice-image AI có trạng thái riêng, không làm sai nghiệp vụ core.

## FE-11 — Media, tour và map · P1/P2

**Phụ thuộc:** Media policy/storage/access, location/provider contracts, FE-06/05. **Đầu ra:** upload/gallery/tour và map/list synchronization.

- [ ] Upload validation/progress/cancel/error/retry, alt/order/delete/quyền/moderation, placeholder minh họa rõ; URL private theo server scope.
- [ ] Gallery/tour links có loading/error, controls accessible; link ngoài theo policy được chốt, không tự download/sao assets.
- [ ] Map dùng tọa độ precision/source/uncertainty; marker/card cùng ID/version; area-only không giả ghim exact, geolocation chỉ khi user chủ động.

**FE-11.AC1:** Owner/tenant media không bị người ngoài scope đọc qua URL/detail. **AC2:** Không có marker/distance giả; lỗi map vẫn tìm/xem bằng list được. **AC3:** Xem trực tuyến dùng media/tour/lịch thật mà không bắt dựng video call platform.

## FE-12 — Favorites, saved searches, viewed, session history và compare · P2

**Phụ thuộc:** FE-03/05 và persistence/compare APIs. **Đầu ra:** account lists, status cân nhắc/loại và compare.

- [ ] Lưu/bỏ lưu, saved search criteria/name/scenario sửa/xóa/chạy lại, viewed trạng thái, session history/continue/delete theo policy; server là nguồn đồng bộ giữa thiết bị.
- [ ] Saved stale/hidden/unavailable hiển thị đúng snapshot được phép và thay đổi; không cho action dựa giá cũ.
- [ ] Compare 2–3, cùng `public_catalog` hoặc `ai_recommendation`, listing/run revisions và scenario; đổi source/state làm mới selection.

**FE-12.AC1:** Hai phiên cùng account nhận kết quả sau refresh; account khác không đọc lists/history/saved searches. **AC2:** AI compare chặn pending/invalidated; public compare dùng tin published current. **AC3:** Unknown khác 0; mobile bảng không tràn trang; không lưu chat/finance vào browser storage.

## FE-13 — Viewing, handoff và notifications · P2/P3

**Phụ thuộc:** FE-05/12, listing/run/slot/assignment/outbox APIs. **Đầu ra:** lịch detail/timeline/action, bàn giao người phụ trách và notification center.

- [ ] Public/AI source context, timezone và hình thức xem; owner propose slot, assigned manager confirm/decline; renter cancel/reschedule theo rule.
- [ ] Timeline requested/confirmed/rescheduled/cancelled/completed/no-show theo API; request không giữ phòng, conflict rõ.
- [ ] Handoff có receipt/assigned contact/status; notifications read/unread/deep links/quyền, deduplicate sự kiện và lỗi dịch vụ.
- [ ] Bổ sung contract/invoice/meter/payment/ticket events khi P3; email giao dịch là kênh bắt buộc có delivery status, SMS/push là kênh thêm; mail không chứa tài liệu/chat/chứng từ private.

**FE-13.AC1:** Timestamp server UTC và display timezone đúng, slot conflict không giả confirmed. **AC2:** Không báo đã bàn giao hoặc thông báo thành công trước receipt server; event retry không tạo duplicate UI item. **AC3:** Deep link notification kiểm tra lại quyền và version trước hiển thị/hành động.

## FE-14 — Reservation, contract, tenancy và move-in/out · P3

**Phụ thuộc:** FE-06/13, contract/consent/tenancy/handover APIs. **Đầu ra:** document editor/review, consent, thuê và bàn giao.

- [ ] Reservation theo thỏa thuận có expiry/release/history, không sinh từ requested viewing; expired giải phóng theo server policy.
- [ ] Nháp điều khoản/participants/price/fees/deposit/term/document, validation và shared review theo scope; export versioned artifact.
- [ ] Consent của renter + owner/authorized manager đúng version; change tạo revision và consent mới theo state machine.
- [ ] Reservation hợp lệ và contract active/tenancy planned chặn allocation periods giao nhau theo physical_room_id, dù tin được đăng lại; contract expired chưa giải phóng occupied trước move-out, contract activate khác tenancy active; move-in checklist tài sản/ảnh/khóa/số công tơ/confirmation, overlap prevention.
- [ ] Gia hạn/kết thúc/move-out, số cuối/tài sản/settlement/cọc và lịch sử có audit; deduction proposed/accepted/disputed, dispute hold không tự khấu trừ hoặc final close; pháp lý e-sign optional riêng.

**FE-14.AC1:** Chưa đủ consent/version không activate; contract active chưa tự tenancy active. **AC2:** Chỉ move-in checklist hợp lệ mới active tenancy; owner khác không đọc document. **AC3:** Reservation expiry/release và change/termination/move-out không chỉnh mất lịch sử hoặc tự đánh dấu hoàn cọc.

## FE-15 — Meter, invoice và reconciliation · P3

**Phụ thuộc:** FE-14, meter/billing/ledger/reconciliation APIs xác định. **Đầu ra:** period readings, invoice detail và sổ đối chiếu.

- [ ] Số đầu/cuối/kỳ/ảnh/rule/đơn giá, missing và reset/replacement cases; chốt/sửa có revision/reason.
- [ ] Invoice lifecycle draft/issued/void và payment_status unpaid/partially_paid/paid, overdue boolean theo balance/due_at; line quantities/rates/totals/due/adjustment theo server; không tự cộng tiền.
- [ ] Renter report transfer; owner/authorized manager confirm receipt/allocate/reconcile; partial/overpayment/dispute/correction có trạng thái riêng.
- [ ] Receipt/document/privacy, ledger timeline, notification và retry semantics; gateway optional không thay manual recording.

**FE-15.AC1:** Known/missing/zero/included và meters oracle đúng; billing kỳ sai/reading giảm không tự cho qua. **AC2:** Reported transfer không paid; multiple/partial/overpayment không thất thoát hoặc nhận trùng. **AC3:** Invoice đã issue và receipt correction giữ revision/audit, không sửa số tiền lịch sử trực tiếp.

## FE-16 — Maintenance · P3

**Phụ thuộc:** FE-11/13/14, maintenance/assignment/scheduling APIs. **Đầu ra:** renter submit/detail và owner/manager workbench.

- [ ] Yêu cầu gắn tenancy, category/priority/description/media, thời gian/consent vào phòng; scope đúng.
- [ ] Tiếp nhận/assignment/hẹn/processing/completed/renter acceptance/reopen theo contract; timeline/notification.
- [ ] Cost/responsibility/attachments/private info theo quyền; charge có payer và acceptance bên chịu tiền hoặc verified term snapshot, owner technical approval chưa đủ charge renter; billing tham chiếu một lần; contact khẩn cấp lấy cấu hình thật.

**FE-16.AC1:** Người không liên quan tenancy không xem/tạo/sửa ticket/media. **AC2:** Người xử lý báo done không tự renter accepted; reopen giữ lịch sử. **AC3:** Lỗi upload/service giữ form và không gửi duplicate ticket sau response loss.

## FE-17 — Admin, audit, privacy và support · P0→P4

**Phụ thuộc:** RBAC/assignment/audit/report/privacy/ops APIs. **Đầu ra:** screens admin và account privacy/support dùng chung.

- [ ] Account role/scope/assignment có impact/reason/receipt; quyền nhạy cảm theo server, admin không mặc nhiên đọc tất cả raw chats.
- [ ] Report/support lifecycle, entity link/media, tiếp nhận/handling/outcome; moderation reports không thay recommendation review.
- [ ] Audit searchable/paginated, actor/time/action/entity/version/outcome; không render tokens/raw checkpoints/secrets.
- [ ] Export/delete/privacy preferences/policy và trạng thái retention; ops service/recovery views từ backend, không giả production telemetry.

**FE-17.AC1:** Mọi action nhạy cảm bị server chặn nếu scope sai và có audit khi hợp lệ. **AC2:** Report có receipt/status; export/delete có quyền/xác nhận/trạng thái theo policy. **AC3:** Notifications/logs không leak data; HM-10 đủ evidence từ nền tảng đến P4.

## FE-18 — Account lifecycle và security · P1

**Phụ thuộc:** FE-01/02, auth threat model/account/verification/recovery/session APIs. **Đầu ra:** registration, verify/recovery, profile/security và sessions.

- [ ] Registration role onboarding theo policy, verify/account activation, login/logout/revocation; client không tự cấp owner/manager/admin.
- [ ] Recovery/expired token/invalid link/rate limit; profile/contact/password/session management có validation và feedback.
- [ ] Đổi account/scope/session làm sạch cache và private state, tránh old 401 logout actor mới; credential/security input không persist.

**FE-18.AC1:** Recovery/token expiry và revocation hoạt động với server thật, không tiết lộ account trái policy. **AC2:** Vai trò/scope do server cấp; protected deep links và API không cho client bypass. **AC3:** Bundle/env/storage không chứa model/DB keys hoặc raw tài chính/chat của người dùng.

## Evidence khi đóng task

Ghi ít nhất: mã task/HM/UI-V; source/API/schema/data/config version; ngày/môi trường/browser/viewport; provider offline/live; test/API/browser steps và kết quả; đường dẫn artifact không có secrets; hạn chế và task còn mở. Tham khảo [TEST_CHECKLIST](TEST_CHECKLIST.md) và [DEMO_CHECKLIST](DEMO_CHECKLIST.md). Mọi screenshot/fixture mới phải có nhãn, không thay lịch sử evidence 02/10 hoặc coi screen target đã có trong runtime.
