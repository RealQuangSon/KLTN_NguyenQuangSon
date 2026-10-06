# API contract HomeMatch 0.4.0 (đang chạy)

Vai trò: `renter` là **khách**, `owner` là **chủ nhà** (duyệt phòng của mình trong danh sách AI, vận hành PMS và CRM), `admin` là quản trị viên. `manager` cũ không còn quyền nghiệp vụ. Phần còn chưa làm nằm ở [API đích](api-san-pham-v1.md).

API version `0.4.0`; source: `backend/app/main.py`, `models.py`, response contracts trong `schemas.py` và projections trong `service.py`. [OpenAPI snapshot](openapi.json) mô tả cả request/response/error schema; [dictionary](status-dictionary.md) khóa trạng thái và phản ứng với lỗi. FE gọi `/api` qua Vite proxy, backend route không có prefix `/api`.

Từ 0.4.0: bốn vai trò renter/owner/manager/admin (manager không còn quyền nghiệp vụ từ 05/10) (`backend/app/capabilities.py` là ma trận quyền duy nhất), domain organization/membership/ownership, audit log và public/private projection (`backend/app/projection.py`). Schema ledger là v3; luồng 0.3.0 renter/manager giữ nguyên hành vi.

## Auth và lỗi

`POST /auth/login {username,password}` → `{access_token,token_type:"bearer",expires_at,actor:{id,role}}`. Token do server cấp, không gửi role từ client. `GET /auth/me` trả actor; `POST /auth/logout` thu hồi token, trả `{status:"logged_out"}`. Các endpoint còn lại trừ `/health`, `/ready`, tài liệu Swagger và nhóm auth lifecycle dưới đây yêu cầu `Authorization: Bearer …`.

Tài khoản seed (mật khẩu mẫu `local-<username>-password`): `renter-a`, `renter-b` (renter), `owner-a`, `owner-b`, `owner-c`, `owner-d` (owner), `manager-a`, `manager-b` (manager cũ), `admin-a` (admin). Owner/manager/admin được bootstrap membership trong đơn vị mặc định `org-demo`; renter không thuộc đơn vị.

Tài khoản tự đăng ký phải xác minh email trước khi login: sai mật khẩu luôn trả `invalid_credentials`/401 (không tiết lộ tài khoản); đúng mật khẩu nhưng chưa xác minh trả `account_unverified`/403, bị vô hiệu hóa trả `account_disabled`/403.

Domain/validation/HTTP errors dùng `{error:{code,message,fields?},request_id}`; lỗi input không trả lại payload nhạy cảm. HTTP status 401: cần login; 403: sai quyền/phòng chưa được phép xem; 404: tài nguyên không được tìm/chiếu; 409: xung đột phiên bản/trạng thái/token; 422: input sai. Header `X-Request-ID` dùng đối chiếu, kể cả lỗi 500. Thiếu/sai bearer trả 401 với `WWW-Authenticate: Bearer`; 404/405 cũng dùng envelope thống nhất.

## Tài khoản, hồ sơ và phiên (0.4.0)

| Endpoint | Request / response |
|---|---|
| `POST /auth/register` (201) | `{username,password,email,display_name?}` → `{status:"pending_verification",user:{id,role:"renter"},delivery:"dev_stub_log_only"}`. Luôn tạo tài khoản renter chưa xác minh; role/org không nhận từ client. Mật khẩu ≥10 ký tự; username `^[a-z0-9][a-z0-9-]{2,49}$`; trùng tên → 409 `account_exists`, trùng email → 409 `email_in_use`. |
| `POST /auth/verify` | `{username,token}` → `{status:"verified"}`. Token đơn dụng, hạn 30 phút; sai → 409 `invalid_token`, đã dùng → `token_used`, hết hạn → `token_expired`. |
| `POST /auth/password-reset/request` | `{username}` → `{status:"reset_requested"}` giống hệt cho mọi username (không tiết lộ tồn tại). Tài khoản seed và bị disable không được cấp token. |
| `POST /auth/password-reset/confirm` | `{username,token,new_password}` → `{status:"password_reset"}`; thu hồi toàn bộ token đăng nhập, đánh dấu email đã xác minh. |
| `GET/PATCH /me/profile` | GET trả `{id,role,display_name,email,email_verified,status,consents,organizations}`. PATCH chỉ nhận `display_name?`,`email?`,`consents?` (`save_history`,`remember_sessions`); gửi role/organization bị 422. Đổi email đặt lại `unverified` và yêu cầu xác minh mới. |
| `GET /me/sessions` | Danh sách `{token_id,expires_at,revoked}`; `token_id` suy từ hash đã lưu, không lộ token/hash. |
| `DELETE /me/sessions/{token_id}` | `{status:"revoked"}`; không thuộc user → 404, đã thu hồi → 409 `session_revoked`. |

Gửi email xác minh là **stub phát triển ghi log** (`dev_stub_log_only`), nhãn rõ, không gọi dịch vụ ngoài. Ở chế độ public (`HOMEMATCH_PUBLIC=true`), `register`, `password-reset/request` và PATCH đổi email trả 503 `delivery_unavailable` thay vì giả gửi.

## Đơn vị, membership và audit (0.4.0)

| Endpoint | Quy tắc |
|---|---|
| `GET /organizations` | Admin: tất cả; thành viên khác: đơn vị mình kèm `actor_role`; renter không membership: `[]`. |
| `POST /organizations` (201) | Chỉ admin (`org.create`); người tạo nhận membership `admin`; tên 2–120 ký tự. |
| `GET /organizations/{org}/memberships` | Thành viên active hoặc admin; người ngoài 403. |
| `POST /organizations/{org}/memberships` (201) | Admin toàn cục hoặc owner của đơn vị đó; cấm tự sửa membership của chính mình (403 `cannot_modify_own_membership`); user tồn tại và đã active/verified (404 `user_not_found`, 409 `account_unverified`); trùng → 409 `membership_exists`; membership revoked được cấp lại bằng cách tăng revision. |
| `DELETE /organizations/{org}/memberships/{id}` | Như grant; không thể tự thu hồi; thu hồi lại → 409 `membership_revoked`; thành viên revoked mất quyền đọc ngay. |

Mỗi mutation ghi audit entry cùng transaction (`hm_audit_log`: actor, action, resource, organization, detail chỉ tên trường, không PII). Đọc audit qua module `backend/app/organizations.py::audit_entries`; endpoint đọc audit dành cho W-16. Bảng `hm_room_ownership` map phòng kho vào đơn vị/owner khi bootstrap (phòng demo về `org-demo`, owner `owner-a` khi có tài khoản).

## Hồ sơ và kết quả khách

| Endpoint | Request / response |
|---|---|
| `POST /sessions` (201), `GET /sessions/{id}` | Renter sở hữu: session DTO |
| `POST /sessions/{id}/messages` | `{text,cost_input?:{quote,scenario}}`; session DTO + intent/status/questions/message hoặc cost/ticket_id; thêm `provenance` (nguồn nội dung lượt chat) và `guard` (kết quả sàng lọc injection/PII) tùy chọn |
| `PATCH /sessions/{id}/draft` | `{expected_draft_revision,set?,clear_fields?,remove_preferences?}` → session DTO + questions |
| `POST /sessions/{id}/confirm` | `{expected_draft_revision,profile}` → **results DTO**, không phải session DTO; FE GET session để lấy revision mới |
| `GET /sessions/{id}/results` | results DTO; chỉ published/current có phòng; `suggestions` (bước nới lỏng mềm khi `no_match`/`needs_verification`) và `provenance` (engine/node/run status) tùy chọn |
| `POST /sessions/{id}/compare` | `{room_ids:[2–3 ID khác nhau]}` → `{run_id,items}` từ cùng published run |
| `POST /costs/estimate` | `{quote,scenario}` → CostResult; không lưu hồ sơ |

Thành phố và khu vực trong draft/profile được so khớp qua từ điển `backend/app/locations.py` (TP.HCM, Hà Nội; alias như "Sài Gòn", "Q7", "Bình Thạnh", "Cầu Giấy"). Tên lạ được giữ nguyên và so khớp sau khi chuẩn hóa khoảng trắng và chữ hoa/thường.

Session DTO: `session_id,draft_revision,draft,profile_version,confirmed_profile,active_run_id`. Draft bổ sung `field_status` (`unknown/inferred/confirmed`) và `evidence_ref` theo từng trường; nguồn dùng reference revision như `chat:r1`/`form:r2`, không chứa raw chat. Server xác định các metadata này, client không được patch trực tiếp. Draft chỉ là suy luận; money hint chưa thành trần ngân sách. Draft kèm `field_status` và `evidence_ref` cho các trường được theo dõi (`city,area,people,preferences,room_type,needs_destination,soft_description,budget_hint`): giá trị do chat suy ra là `inferred` với evidence `chat:r<revision>`, nhập/sửa qua form là `confirmed` với `form:r<revision>`, trường bị xóa về `unknown`; FE dùng để phân biệt mục cần khách kiểm tra, không tự ghi 2 map này từ client. Patch chỉ sửa `city,area,people,preferences,room_type,needs_destination,soft_description`, không sửa role/manager/version. Confirm tăng profile version **và draft revision**, tạo run hiện tại; replay revision cũ trả 409, không tạo run trùng.

Lỗi provider AI không còn làm hỏng lượt chat: service trả fallback biểu mẫu có nhãn mã (`ai_unavailable`/`context_limit`) trong `questions`, không tự bịa extraction; usage vẫn đếm lượt gọi lỗi (`calls_without_token_usage`), không tuyên bố số token.

Results DTO:

```json
{"session_id":"…","run_id":"…","status":"pending_review","profile_version":1,"results":[]}
```

Chưa có run thì status `awaiting_confirmation`, không có run_id. Published results chứa Candidate: ID/revision/title/location, CostResult, score/components, reasons/tradeoffs, source, synthetic, algorithm và `verification` (cờ dữ liệu chưa rõ: `amenity_unknown:*`, `fee_rate_unknown:*`, `location_approximate`/`area_only`, `location_uncertainty_{n}m`). Khi status là `no_match`/`needs_verification`, results DTO kèm `suggestions`: các bước nới lỏng mềm do người thuê tự quyết (mở rộng khu vực, hạ tiện ích bắt buộc xuống ưu tiên, bán kính, xem lại trần đã xác nhận); hệ thống không tự nới điều kiện cứng. Không trả raw graph/review event hoặc candidate pending. `null` full cost là thiếu dữ liệu; `*_known_vnd` là subtotal. P unavailable có thể fallback B1 trong app, nhãn algorithm/diagnostics nói rõ; eval không dùng fallback làm P.

Public projection (module `backend/app/projection.py`) là allowlist: chỉ phòng `published=true` vào danh sách công khai, tọa độ exact bị hạ xuống `approximate`, trường ngoài allowlist không thể lộ; item AI chỉ public khi run `published`. Đường public API catalog sẽ đến ở HM-03/W-06; module này là nguồn projection cho đường đó.

## Tài chính, căn hộ và mô phỏng (GĐ2, 05/10/2026)

**`Profile`** (body xác nhận) có thêm các trường tùy chọn:

- `min_bedrooms` (1–5);
- `monthly_income_vnd`;
- `cost_split`: `none` | `equal`;
- `loan`: `{annual_rate: "0.12", term_months: 1–36, max_principal_vnd?}`. `null` nghĩa là không vay.

`room_type` nhận `room` | `studio` | `apartment`. **`Room`** và **`Candidate`** có thêm `room_type`, `bedrooms`. `Room` có thêm `features_text` (mô tả mềm, được đưa vào văn bản semantic).

`POST /sessions` điền sẵn nháp từ memory khi khách đã đồng ý: `field_status = inferred`, `evidence_ref = memory:<phiên>`, `draft_revision` vẫn bằng 0. Chat provenance có thêm `agent`, `tools`, `steps`; run diagnostics có `agent` của agent xếp hạng. `/admin/metrics` có thêm `semantic_usage: {query_embedding_calls, query_cache_hits}`.

**`CostResult.affordability`** là `null` khi không có dữ liệu tài chính. Khi có:

```json
{"shortfall_vnd": 5500000,
 "loan": {"principal_vnd": 5500000, "installment_vnd": 949016, "total_interest_vnd": 194096,
          "term_months": 6, "annual_rate": "0.12", "method": "annuity", "exceeds_max_principal": false},
 "burden_vnd": 8019016, "renter_burden_vnd": 8019016,
 "housing_ratio": "0.3208", "band": "can_nhac",
 "thresholds": {"phu_hop": "0.30", "can_nhac": "0.40"}}
```

- Ứng viên trong run luôn có `affordability`. Thiếu tiền mặt hoặc thu nhập thì các trường tương ứng là `null` và `band = "chua_ro"`.
- **DTO của chủ nhà** bỏ `monthly_income_vnd` khỏi `profile` và trả `housing_ratio: null`. Chủ nhà chỉ thấy `band`.
- Lý do loại căn mới trong diagnostics: `bedrooms`, `loan_principal`, `loan_burden`. Căn hộ chưa rõ số phòng ngủ vào `verification.bedrooms`.
- Lý do và đánh đổi mới: "Cần vay X VND, trả góp Y VND/tháng trong N tháng."; "Tỷ lệ chi phí nhà ở trên thu nhập ở mức cần cân nhắc." hoặc "…vượt mức khuyến nghị."

| Endpoint | Mô tả |
|---|---|
| `POST /costs/estimate` | Thêm `affordability?: {available_cash_vnd?, monthly_income_vnd?, cost_split?, loan?}`. Không gửi thì `affordability = null` như trước. |
| `POST /sessions/{id}/simulate` | `{room_id, scenarios: [1–3 × {label, scenario?, cost_split?, loan?}]}` → `{run_id, room_id, room_revision, items: [{label, cost}]}`. Trường bỏ trống lấy từ hồ sơ đã xác nhận; `loan: null` là không vay. Chỉ cho căn thuộc run đã công bố hiện tại (khác → 403 `not_visible`). Không lưu, không đổi hồ sơ hay run. |
| `GET /me/memory` | `{consented, memory: {fields, source_session, updated_at} \| null}`. `fields` chỉ gồm `city, area, room_type, bedrooms, preferences, soft_description`, không có tiền. |
| `DELETE /me/memory`, `DELETE /me/memory/{field}` | Xóa toàn bộ hoặc một trường (trường lạ → 422 `invalid_memory_field`). `PATCH /me/profile` với `consents.remember_sessions=false` cũng xóa memory. |
| `GET /locations` | Không cần đăng nhập. `{cities: [{name, aliases, areas: [{name, aliases}]}]}` từ `locations.py`. |

## Chủ nhà duyệt gợi ý (mỗi chủ duyệt phòng của mình)

| Endpoint | Quy tắc |
|---|---|
| `GET /landlord/recommendations` | Các run còn hiệu lực có phòng của chủ nhà này |
| `GET /landlord/recommendations/{run}` | DTO chỉ gồm phòng của chủ nhà này, kèm `review_progress {landlords, decided}`. Chủ nhà không liên quan → 403. |
| `POST /landlord/recommendations/{run}/review` | Quyết định cho phần phòng của mình → DTO |
| `POST /landlord/recommendations/{run}/retry` | Chủ nhà của run hoặc admin: resume quyết định cuối đã ghi. Chỉ admin được tạo lại run lỗi. Run mới không thừa kế quyết định. |
| `GET /admin/failed-runs` | Admin: các run `generating` hoặc `generation_failed` |

DTO: `run_id,session_id,status,profile_version,catalog_version,profile,items,diagnostics,decision,review_progress`. `decision` là quyết định của chính chủ nhà đó.

Quy tắc trạng thái:
- Run ở `pending_review` cho tới khi có chủ nhà đầu tiên duyệt; từ đó là `partially_published` và khách thấy ngay phòng đã duyệt.
- Khi mọi chủ nhà có phòng trong run đã quyết định, ledger ghi `decision` cuối (`event_id`), run chuyển sang `reviewed`, graph resume, rồi chốt `published` (có ít nhất một phòng được duyệt), `needs_revision` hoặc `rejected`.
- Thứ tự khách thấy giữ thứ tự của trợ lý. Mỗi chủ nhà chỉ đổi thứ tự trong các vị trí phòng của mình.

Review request:

```json
{"decision":"approve","expected_profile_version":1,"keep_room_ids":["room-id"],"reason":"Đã kiểm tra nguồn và tổng phí.","idempotency_key":"unique-review-key"}
```

Khi `keep_room_ids` khác thứ tự đề xuất của trợ lý (bỏ căn hoặc đổi thứ tự), request phải có `override_reason` (1–1000 ký tự). Thiếu thì trả 422 `override_reason_required`. Review event lưu `agent_order` (thứ tự của trợ lý) và `overridden`. Event ghi trước GĐ2 không có hai trường này. `keep_room_ids` chỉ được gồm phòng của chính chủ nhà (phòng khác → 422 `invalid_selection`); mỗi chủ nhà quyết định một lần cho mỗi run (khác payload → 409 `review_conflict`).

Decision là approve/reject/needs_revision; approve cần ≥1 ID thuộc nháp, có thể chọn thứ tự qua API. Cùng key và toàn bộ payload/actor cho cùng run replay quyết định cũ; khác payload trả conflict. Không có publish client flag. Review event commit trước resume; nếu graph lỗi, `review_resume_failed`/503 giữ event ở `reviewed` để retry. Finalize kiểm active run/profile/catalog dưới transaction khóa catalog chung với writer. Thiếu điểm resume trả `recovery_required`, không công bố chỉ từ event.

## Nền tảng: 5 phân hệ (E1–E6, 05/10/2026)

| Nhóm | Endpoint | Ghi chú |
|---|---|---|
| Tìm kiếm công khai | `GET /listings` (query: `city, area, room_type, min_rent, max_rent, max_monthly, min_area_m2, min_bedrooms, people, amenities[], sort, page, page_size`) | Không cần đăng nhập. Chỉ tin `published`, chưa cọc/thuê. Tham số lạ → 422. |
| | `GET /listings/{id}?people=` | Chi tiết, chi phí ước tính, nội quy, `landlord_id`. Ghi lượt xem (gắn khách nếu có token). |
| | `POST /listings/compare {room_ids, people, budget?, preferences}` | Kèm `advice {recommended_room_id, summary, rooms[{pros, cons}]}` |
| Cẩm nang | `GET /handbook`, `POST /handbook/ask {question, room_id?}` | Truy xuất mục chung và nội quy chủ nhà; kèm `disclaimer` |
| Live chat | `POST /conversations {room_id, session_id?}` (201) | Khách mở; một cuộc cho mỗi khách, chủ nhà và phòng. `context` gồm phòng, nhu cầu, băng tài chính, chat AI gần nhất đã che PII. |
| | `GET /conversations`; `GET /conversations/{id}/messages?after=`; `POST /conversations/{id}/messages {body}` | Chỉ hai bên. Đánh dấu đã đọc khi đọc; `unread` theo bên. |
| Thông báo | `GET /notifications`; `POST /notifications/read`; `POST /notifications/{id}/read` | `{unread, items[{kind, title, body, link, created_at, read_at}]}` |
| Chủ nhà: tin | `GET/POST /landlord/rooms`; `GET/PUT /landlord/rooms/{id}`; `PATCH /landlord/rooms/{id}/status {expected_revision, published?, available?, occupancy?}` | Chỉ phòng của mình. `occupancy` (`vacant`/`deposited`/`rented`) đặt `available` tương ứng. Đổi trạng thái hoặc giá báo cho khách đã quan tâm. |
| Chủ nhà: PMS | `GET /landlord/dashboard`; `GET /landlord/analytics`; `POST /landlord/leases`; `PUT /landlord/leases/{id}`; `POST /landlord/leases/{id}/send` \| `activate` \| `renew` \| `terminate`; `POST /landlord/leases/{id}/readings`; `POST /landlord/leases/{id}/invoices`; `GET /landlord/billing/summary`; `POST /landlord/invoices/{id}/payments`; `POST /landlord/payment-claims/{id}/confirm` \| `reject` | Hợp đồng chống trùng kỳ (409 `lease_overlap`). Hóa đơn thiếu chỉ số hoặc đơn giá → 422 `invoice_incomplete`; trùng kỳ → 409. Thu vượt số còn nợ → 422 `overpayment`. |
| Chủ nhà: CRM | `GET /landlord/leads`; `PATCH /landlord/leads/{id} {stage?, notes?}` | Điểm quan tâm: xem 1, chat 3, lịch xem 5, hợp đồng 8 |
| Chủ nhà: trợ lý AI | `POST /landlord/rooms/{id}/marketing {channel: facebook\|zalo\|forum}`; `GET /landlord/rooms/{id}/price-advice`; `POST /landlord/assistant {question}` | Bài đăng chỉ dùng dữ liệu tin, kèm `share_url` (Facebook) và `listing_url` (trang `/tin/{id}`). Đề xuất giá cần ít nhất 3 căn tương đương. |
| Hai bên | `GET /leases`; `GET /leases/{id}`; `GET /leases/{id}/document`; `POST /leases/{id}/accept {expected_version}` | Khách không thấy bản nháp. Chấp thuận sai phiên bản → 409 `lease_version`. |
| | `GET /invoices`; `GET /invoices/{id}`; `GET /invoices/{id}/document?receipt_no=`; `POST /invoices/{id}/claims {amount_vnd, reference}`; `GET /payment-claims` | Báo đã chuyển chưa phải đã thu. `payment_status` `unpaid`/`partially_paid`/`paid`; `overdue` tính từ số dư và hạn. |
| | `GET /maintenance`; `POST /maintenance {room_id, title, description, priority}`; `PATCH /maintenance/{id} {status?, assignee?, cost_vnd?, note?}` | Chỉ người đang thuê gửi được (403 `no_active_lease`). Khách chỉ chuyển sang `closed` hoặc `reopened` (cần ghi chú). |
| Admin | `GET /admin/transcripts`; `GET /admin/transcripts/{session}`; `GET /admin/handovers`; `GET /admin/users`; `GET /admin/rooms`; `PATCH /admin/rooms/{id}/status`; `GET /admin/metrics`; `POST /admin/jobs/run`; `GET /admin/jobs` | Mở transcript ghi audit `transcript.viewed`. Transcript đã che PII, giữ 90 ngày. |

Văn bản hợp đồng, hóa đơn, biên lai trả về `{html}` để giao diện hiển thị và in. Đây không phải chữ ký số.

## Lịch xem và retry

`POST /sessions/{id}/viewings` (201) nhận `{room_id,requested_at,idempotency_key,mode:"offline"|"online"}`; timestamp tương lai có múi giờ. `POST /listings/{id}/viewings` đặt thẳng từ tin đăng (không cần phiên AI; phòng đã cọc/thuê → 409 `not_available`). `GET /viewings`/`GET /viewings/{id}` theo quyền bản ghi (khách của lịch hoặc chủ nhà của phòng). `POST /landlord/viewings/{id}/respond {status:"confirmed"|"declined"}` chỉ chủ nhà của phòng. Viewing DTO: `id,session_id?,run_id?,room_id,requested_at,status,landlord_id,mode,meeting_url`; lịch trực tuyến có `meeting_url` (Jitsi). Tạo mới là `requested`, chưa là lịch xác nhận.

Review/viewing có replay key; giữ nguyên payload/key khi mất response. Message không auto-resend. Draft/confirm/catalog dùng CAS, đọc lại state khi 409/mạng trước thao tác tiếp. Retry generation không có key; đọc queue để tìm active run mới sau mất response. Hồ sơ/kho thay đổi làm results invalidated và chặn compare/viewing cũ.

Kho bootstrap JSON chỉ nạp khi trống; CLI import merge có revision và transaction, bỏ ID khỏi JSON không xóa bản ghi. Mọi dữ liệu demo đều synthetic. Một API process/worker, không có endpoint raw checkpoint hoặc worker tự recovery.

## Vận hành

`GET /health` giữ DTO status/storage/auth/method/workers và kiểm kết nối ledger; lỗi DB trả `storage_unavailable`/503. `GET /ready` trả `{status:"ready",storage,schema_version:9,checks:{ledger:"ok",catalog:"ok",checkpoints:"ok"}}`; schema/catalog/checkpoint lỗi trả `not_ready`/503. Readiness kiểm storage cốt lõi; coverage/provider P được kiểm khi ranking và có fallback rõ ràng.

Metrics reset khi restart. `duration_seconds` là tổng thời gian máy xử lý, không phải p95 hoặc thời gian chủ nhà chờ duyệt. Provider metrics có `logical_calls,reported_tokens,calls_without_token_usage`; số tokens đã báo không bao gồm lượt thiếu usage. Log dùng route mẫu, không lưu URL/query/body, token hoặc raw chat; log duy nhất chứa mã xác minh là DEV-STUB có nhãn giả. Dùng `backend/logging.json` và `--no-access-log` khi chạy server.

Manager diagnostics bổ sung `ranking_version,ranking_config,profile_hash,query_text_hash,catalog_version,requested_method`. Các metadata này lưu trong snapshot run, không mở thêm đường đọc cho renter. Migration ledger tự chạy khi startup, hoặc chủ động dùng `python -m backend.manage migrate`. Schema hiện tại là v9 (v4 memory/cache embedding, v5 duyệt theo chủ nhà, v6 lượt xem và lịch từ tin, v7 live chat/transcript, v8 thông báo/job, v9 PMS & CRM); DB v1/v2 được tiếp nhận, bootstrap tạo đơn vị mặc định và membership cho staff seed đã tồn tại, không xóa/sửa bản ghi cũ. Backend từ chối DB có schema mới hơn code.
