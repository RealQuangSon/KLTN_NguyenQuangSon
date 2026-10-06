# Kiểm chứng frontend HomeMatch — baseline và sản phẩm hoàn chỉnh

**Cập nhật 04/10/2026.** Các mục sản phẩm dưới đây là checklist chưa nghiệm thu cho HM-01…HM-10/API v1 mục tiêu. Đợt viết lại docs không chạy lại frontend/API/browser, không thay code và không đánh dấu screen target hoàn thành. Bằng chứng 02/10 được giữ riêng như lịch sử của subset API 0.3.0.

Đọc cùng [UI_SPEC](UI_SPEC.md), [PLAN](PLAN.md) và [tiêu chí nghiệm thu](../docs/tieu-chi-nghiem-thu.md). Các mục về chủ nhà, hợp đồng, hóa đơn bên dưới thuộc phạm vi cũ 04/10, ngoài đề tài. Kết quả fixture tests không chứng minh integration browser, PostgreSQL, live AI hoặc môi trường phát hành.

## 1. Quy tắc ghi kết quả

- Mỗi lần chạy ghi task/HM/UI-V, ngày, source/API/schema/data/config version, môi trường, browser/device/viewport và provider offline/live.
- Ghi case/expected/actual/pass-fail/evidence/limitation. Chỉ đánh dấu đạt khi đúng phạm vi được kiểm chứng; không kế thừa nhãn đạt từ screen hoặc contract cũ.
- Dùng dữ liệu tổng hợp, tài khoản cô lập, không lưu secrets/raw chats/DB/checkpoints hoặc tài chính thật vào evidence. Screenshot che thông tin không cần thiết.
- Mỗi module có happy path, wrong actor/scope, stale/version/conflict, loss/recovery và trạng thái empty/error phù hợp. Đóng task cần cả kiểm thử FE và enforcement API.
- P4 phát hành cần đủ các module bắt buộc và backend/infra readiness; P5 nghiên cứu matching là bằng chứng riêng.

## 2. Baseline lịch sử ngày 02/10/2026

**Phạm vi:** giao diện HomeMatch cam đỏ/nền ngà và luồng trước thuê renter/manager. Đây là ghi chép từ lượt kiểm chứng trước, không phải kết quả chạy ngày 04/10 hoặc bằng chứng các screen toàn vòng đời.

Môi trường được ghi: React 19.1.1/Vite 7.1.7; frontend `127.0.0.1:5173`, FastAPI `127.0.0.1:8000`; SQLite riêng trong `.local/`, một API worker; auth seed, LLM `demo`, matching `B1`, embedding `disabled`, public `false`; toàn bộ phòng/hồ sơ tổng hợp. Checkout chưa có commit nên không có Git SHA.

| Phần | Kết quả đã ghi tại lượt trước | Giới hạn |
|---|---|---|
| Vitest/RTL | 15/15 tests thuộc 4 files trên source lúc đó đạt; pending/reviewed/invalidated/error hidden; null/0/included; compare 2–3; stale session/actor; auth cleanup; key/CAS; correction giữ finance/scenario | Không xác nhận số tests/source hiện tại hoặc screen target |
| TypeScript/build | Đạt; 40 modules; JS 249,75 kB (gzip 77,67 kB), CSS 35,17 kB (gzip 8,12 kB) | Không phải performance hoặc bundle release hiện tại |
| API smoke in-process/HTTP | Hai chế độ đạt 7 nhóm: 4 actors, ownership/CAS, pending hidden, subset/replay/compare, viewing confirmed, catalog conflict/invalidation, token revocation | API thật với provider offline, không chứng minh GPT/live matching |
| Browser luồng chính | Renter/manager chat→profile→pending→duyệt 3→renter 3→compare 2; phiên mới duyệt 5→viewing→manager confirmed→renter đọc lại | Chưa chứng minh target routes, owner/admin hoặc nghiệp vụ sau thuê |
| Kho quản lý | `quan 7` không dấu + còn phòng trả 25/80; query không khớp empty; filter không sửa trạng thái | Kho nghiên cứu tổng hợp |
| Responsive/keyboard | Renter 1440×1000 và 390×844 không tràn trang; viewing modal focus/Tab/Escape/trả focus; không warn/error console hai workspace đã xem | Không xác nhận mọi screen, 320px, zoom hoặc toàn accessibility |

Ảnh lịch sử được ghi tại `/Users/son/.codex/visualizations/2026/10/01/01a0f856-1543-7a43-85b2-b80f73595e12/`: `homematch-welcome.jpg`, `homematch-mobile.jpg`, `homematch-manager.jpg`. Lượt viết docs này không chụp lại hoặc xác nhận toàn bộ ảnh còn truy cập được.

SHA-256 ghi cho source của lượt trước: catalog `e5e91c011df2de5820efe571d1872321ad0c66edc64a3269df818530e5599c82`; App.tsx `c2cb04addfd8233214c79a3c71612338cd2732f33300195b549dd441c249bb53`; styles.css `865d56ddaa42ca5b396e93620138f794b05c5c68a82e59270651b09942a8c721`. Các hash này không là định danh source ngày 04/10.

**Chưa xác minh trong lượt trước:** declined trên browser, compare 3 qua browser, lỗi mạng/restart thật, PostgreSQL, GPT/embedding live hoặc cloud. Hướng HubHome mới, map/media/favorites/history/owner/admin/contracts/billing/maintenance chưa được nghiệm thu từ baseline này.

## 3. Checklist regression của subset hiện có

Các mục cần chạy lại khi sửa source/contract; ghi bằng chứng mới, không mặc nhiên xem baseline còn đủ.

- [ ] Login/me/logout và expiry; old token 401 không logout actor mới; cleanup private state/storage.
- [ ] Landing need→login→renter gửi một lần; corrections giữ scenario/finance và IME không gửi sớm.
- [ ] Draft CAS/confirm/profile version; pending/reviewed/invalidated/error không render phòng dù fixture có items.
- [ ] Manager assigned review subset/reason/key; sai manager không đọc/duyệt; lost response không giả published.
- [ ] Monthly/initial null/0/included/known subtotal/full total; compare 2–3 đúng run/scenario.
- [ ] Viewing future/timezone/key/requested→confirmed/declined; retry cùng payload/key.
- [ ] Catalog query/filter read-only; mutation revision/CAS; đọc cũ không đè revision mới; invalidation chặn compare/viewing cũ.
- [ ] Old session/results/actor response bị bỏ; polling/requests dừng khi đổi màn/logout.
- [ ] Desktop/mobile/keyboard/modal và bundle/env không secrets.

## 4. Checklist nghiệm thu HM-01…HM-10

### HM-01 — Tài khoản, bảo mật và cô lập

- [ ] Registration/verification/login/recovery/logout/revocation/profile/security sessions theo contract thật; expired/invalid/rate-limit/error có UI rõ.
- [ ] Vai trò/context do server cấp; protected deep link/reload/back không bypass; owner/manager/admin scope khác nhau.
- [ ] Hai renter/hai owner/hai manager và admin hạn chế scope không đọc/sửa bản ghi ngoài quyền qua UI, API, media/document URLs hoặc notifications.
- [ ] Actor/context đổi làm sạch cache/private state; response cũ không flash dữ liệu; credential không persist; policy phiên v1 được kiểm chứng.

### HM-02 — Owner inventory, media và moderation

- [ ] Owner CRUD nhà/phòng/quote/phí/amenities/location/availability với draft/revision/validation; owner khác bị chặn.
- [ ] Upload/gallery/tour/order/alt/delete/progress/error/quyền và moderation có receipt; không có ảnh/nguồn sao HubHome.
- [ ] Listing draft→submit→approve/request changes/reject; sửa sau duyệt theo contract; save không tự publish.
- [ ] Null availability/fee/amenity/location precision giữ ý nghĩa; CAS conflict đọc lại; thay tin ảnh hưởng recommendation đúng rule.

### HM-03 — Public search, filter, map và detail

- [ ] Chỉ tin được moderation đủ điều kiện public; pagination/filter/sort/deep link/back/refresh đồng bộ server.
- [ ] Hard filters không tự nới; no-match khác missing/AI lỗi; dictionary current/target đúng contract.
- [ ] Map/list cùng IDs/revisions; marker/card selection đúng; approximate/area-only không giả exact; source/time/distance unit rõ.
- [ ] Map/media lỗi hoặc không cấp GPS vẫn dùng list/detail; archived/hidden/unavailable/stale listing chặn action mới trái rule.

### HM-04 — Assistant, chi phí và HITL

- [ ] Draft unknown/inferred/confirmed; hỏi rõ và confirm có hard/soft/budget/scenario/version, không auto-confirm budget hint.
- [ ] Pending/generating/reviewed/invalidated/error không lộ candidate/card/thumbnail/detail/compare/viewing AI qua mọi projection.
- [ ] Manager assigned quyết định đúng run/profile/catalog version/subset/reason; reject/needs_revision/approve và retry/CAS không bypass HITL.
- [ ] Published current mới hiện tối đa 5 theo core contract; run/profile/catalog đổi gỡ stale selection và action.
- [ ] Cost oracle/null/0/included/subtotal/missing/source/assumptions đúng; rent/monthly/initial phân biệt; UI không tự tính hoặc rank.

### HM-05 — Saved, viewed, history và compare

- [ ] Save/unsave/saved search create-edit-delete-rerun/viewed/cân nhắc/loại/session history continue/delete đồng bộ account qua hai phiên; account khác bị chặn.
- [ ] Tin thay revision/giá/hết phòng/ẩn hiển thị nhãn và hành động phù hợp; snapshot không giả dữ liệu hiện hành.
- [ ] Compare 2–3 cùng source public hoặc AI, scenario và listing/run version; pending/invalidated AI bị chặn.
- [ ] Cross-source selection không trộn ngầm; unknown không xếp như 0; mobile/table và keyboard hoạt động; không browser storage chat/finance.

### HM-06 — Viewing, handoff và notifications

- [ ] Public/AI source/revision/run context đúng; request future timezone chuyển UTC đúng, requested không giữ phòng.
- [ ] Owner propose slot, assigned manager confirm/decline, renter cancel/reschedule, completed/no-show theo API; overlap/conflict/late replies không sai lịch.
- [ ] Handoff có assigned contact/receipt/status; không giả người thật đã nhận; xem tại chỗ/trực tuyến có media/tour/link phù hợp.
- [ ] In-app + email giao dịch outbox events deduplicate/retry/read-unread/deep link/delivery failure; actor/scope đúng và mail không tài liệu private; SMS/push tùy chọn chỉ báo trạng thái kênh có thật.

### HM-07 — Contract, tenancy và handover

- [ ] Reservation có thỏa thuận/expiry/release/history; requested viewing không giữ phòng; hết hạn giải phóng theo policy và race không giữ/thuê trùng.
- [ ] Nháp/tài liệu/participants/price/fees/deposit/term/version/consent/permissions và export có API thật.
- [ ] Renter + owner/authorized manager consent đúng version và contract allocation period không overlap mới activate; change làm consent cũ hết hiệu lực theo rule.
- [ ] Tenancy không active/occupied trước move-in checklist; reservation hợp lệ + contract active/planned chặn overlap theo physical_room_id dù có nhiều listing; contract expired chưa giải phóng occupied trước move-out; assets/media/keys/initial meters và confirmations đúng.
- [ ] Renewal/termination/move-out/final meter/settlement/deposit có state và audit; deduction proposed/accepted/disputed và dispute hold chưa khấu trừ/financial settlement settled; không xóa/sửa mất history; legal e-sign optional riêng.

### HM-08 — Meters, invoices và đối chiếu tiền

- [ ] Chốt số đầu/cuối/ảnh/kỳ/đơn giá/cách tính; missing/zero/reset/replacement/correction có validation và oracle.
- [ ] Invoice line quantity/rate/total/due/version theo deterministic server; lifecycle draft/issued/void tách payment_status unpaid/partially_paid/paid, overdue = balance>0 và now>due_at; correction không sửa trực tiếp lịch sử đã chốt.
- [ ] Renter report transfer chưa payment_status paid; owner/authorized manager confirm receipt/allocate/reconcile; multi/partial/overpayment đúng số dư.
- [ ] Wrong actor/duplicate/lost response/dispute/reversal/correction giữ ledger/audit; không double receive hoặc giả thành công.
- [ ] UI tách ước tính scenario và hóa đơn thực tế; manual recording/reconciliation hoạt động dù không gateway.

### HM-09 — Maintenance

- [ ] Renter create ticket đúng tenancy/media/category/priority/access time; người ngoài scope không thấy ticket/attachments.
- [ ] Owner/assigned manager accept/assign/schedule/process/complete; renter accept/reopen; timeline không mất sau retry/restart.
- [ ] Worker completed chưa thành renter accepted; charge có payer/acceptance bên chịu tiền hoặc verified term snapshot, owner technical approval chưa đủ charge renter và không tạo billing trùng; notification/quyền contact khẩn cấp đúng cấu hình.

### HM-10 — Admin, vận hành, riêng tư và audit

- [ ] Admin role/scope/assignment/report/moderation/support có impact/reason/receipt và backend enforcement; không cấp quyền từ client.
- [ ] Audit lọc/pagination/actor/time/entity/version/outcome; không raw token/checkpoint/secret và không default toàn bộ private chats.
- [ ] Export/delete/privacy/preferences/retention có policy/state/quyền; support/report có mã tiếp nhận và trạng thái xử lý.
- [ ] Ops/migration/recovery/backup-restore/monitoring/support được backend/infra xác nhận trong môi trường phát hành; UI không giả telemetry.

## 5. Checklist UI xuyên suốt

- [ ] S01…S21 đúng route/title/landmark/auth/deep-link/reload/back và states; UI-V01…V16 có bằng chứng tương ứng.
- [ ] Tokens/component/icon/fonts/assets đúng quyền sử dụng; ảnh đối chiếu cùng viewport/state tại vùng có baseline; màn mới ghi thiết kế HomeMatch.
- [ ] 1440×900/1280×720/768px/360px/390×844/320px và zoom 200% không tràn trang; bảng/map cuộn riêng; keyboard mobile không che CTA.
- [ ] Hoàn tất flow quan trọng bằng keyboard: focus/Tab/Escape/return focus/IME/labels/errors/live status; splitter/upload có alternative.
- [ ] Contrast chữ thường ≥4,5:1/chữ lớn ≥3:1 theo UI_SPEC, đo trên component; không chỉ màu; reduced motion.
- [ ] Loading/empty/error/stale/conflict/success rõ, giữ form khi lỗi; 401/403/404/409/422/429/503/network không giả no-match/success.
- [ ] Requests cũ bị bỏ theo actor/scope/entity/version; mutation recovery/key đúng API; polling có điểm dừng.
- [ ] Không lỗi console trọng yếu/broken CTA; bundle/env/storage/evidence không secrets hoặc dữ liệu thật.

## 6. Gate P4 và hồ sơ evidence

- [ ] Các HM-01…HM-10 bắt buộc đều đạt nghiệp vụ/API/browser, các UI-V tương ứng đạt; không đóng P4 chỉ từ demo trước thuê.
- [ ] Môi trường release/schema/data/config/providers rõ; PostgreSQL hoặc dịch vụ deployment thực dùng phải được kiểm chứng riêng, không thay bằng SQLite fixture.
- [ ] End-to-end full lifecycle và negative/recovery flows theo [DEMO_CHECKLIST](DEMO_CHECKLIST.md); operational sign-off theo docs backend/infra.
- [ ] README/specs/checklists phản ánh source hiện tại, hạn chế ghi thật; optional integrations có trạng thái riêng, không claim đã triển khai.

Mẫu ghi một case: `HM/task/UI-V | phiên bản | môi trường/provider | actor/scope | dữ liệu/expected | actual | pass/fail | artifact | hạn chế`. Lưu summary và evidence tại vị trí đã thống nhất của dự án; không commit raw logs/chat/checkpoints/DBs. Sau mọi thay đổi hợp đồng có tác động, chạy lại nhóm kiểm tra liên quan trước tổng hợp release.

## 7. Bằng chứng đợt 05/10/2026 — router/deep link và shell bốn vai trò (FE-02 slice + FE-18 UI)

**Phạm vi:** FE-01 (một phần — coverage theo route), FE-02 (router/deep link, shell bốn vai trò), FE-18 (UI đăng ký + stub hồ sơ/bảo mật). Không đụng backend/data/docs; không đánh dấu bất kỳ gate P1–P4 nào đạt.

Môi trường: React 19.1.1/Vite 7.1.7/Vitest 3.2.4, jsdom offline, không gọi mạng ngoài; request fixtures trong `src/tests/`. Backend tham chiếu API 0.3.0 (renter/manager); namespace `/v1` chưa tồn tại.

Kết quả chạy (lệnh từ `frontend/`): `npm run typecheck` đạt; `npm test` đạt 25/25 tests, 6 files (song song và tuần tự `--no-file-parallelism` đều đạt); `npm run build` đạt (JS 273,89 kB / gzip 83,63 kB; CSS 40,66 kB / gzip 9,24 kB); `npm run format` (Prettier) chạy sạch. Chưa chạy lại browser/visual QA, responsive, keyboard trên router mới — các mục UI-V01…V16 chưa có bằng chứng mới.

| Case | Expected | Actual | Ghi chú |
|---|---|---|---|
| Deep link `/nguoi-thue/lich-xem` với token renter (fixture) | Boot gate `/auth/me` xong mới render; màn lịch xem + gọi `GET /viewings` | Đạt (routing.test) | Fixture, chưa chạy với backend thật qua browser |
| Nav link + browser back | URL đổi theo route, back trả về route cũ | Đạt (routing.test) | history API jsdom |
| Deep link khu vực bảo vệ khi chưa đăng nhập | Redirect `/dang-nhap`, không flash dữ liệu | Đạt (routing.test) | |
| Renter mở route manager | Màn 403 trung thực, không gọi API manager | Đạt (routing.test) | Enforcement thật vẫn thuộc backend |
| Token owner (fixture) mở `/chu-nha/nha` | Shell owner + empty state "chức năng cần API v1", nav owner | Đạt (routing.test) | Skeleton không gọi API, không mock dữ liệu |
| `/dang-ky` validation client | Lỗi theo trường, không gửi mạng khi sai | Đạt (routing.test) | |
| `POST /v1/auth/register` 404 (fixture) | Thông báo máy chủ chưa hỗ trợ, không có thông báo thành công | Đạt (routing.test) | Endpoint chưa có thật; chưa thử live |
| `POST /v1/auth/register` 201 (fixture) | Chỉ hiển thị message máy chủ trả, không tự đăng nhập | Đạt (routing.test) | DTO chưa khóa ở P0 — cần BE chốt |

Regression: 18 test cũ giữ nguyên điều kiện khẳng định, chỉ nới trần thời gian (timeout) cho các test tích hợp nhiều bước vì máy chạy song song với tác vụ khác; một trường hợp đợi lời gọi `GET /viewings` đổi từ đếm ngay sau render sang `waitFor` để hết race effect-mount. `src/tests/setup.ts` thêm reset URL về `/` trước mỗi test vì router đọc location thật.

Hạn chế: đăng ký chỉ kiểm chứng fixture; owner/admin là khung chờ API v1; lịch sử chat hiển thị mất khi rời màn trợ lý (giới hạn có từ trước, server history chưa render); chưa kiểm chứng 401/role thật của owner/admin trên server; UI-V responsive/keyboard chưa chạy lại.
