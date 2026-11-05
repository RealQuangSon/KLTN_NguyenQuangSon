# API contract HomeMatch 0.4.0 (đang chạy)

Vai trò: `renter` là **khách**, `owner` là **chủ nhà** (vận hành PMS và CRM; nhận lead khi căn của họ lọt top 5 gợi ý), `admin` là quản trị viên. `manager` cũ không còn quyền nghiệp vụ. Phần còn chưa làm nằm ở [API đích](api-san-pham-v1.md).

API version `0.4.0`; source: `backend/app/main.py`, `models.py`, response contracts trong `schemas.py` và projections trong `service.py`. [OpenAPI snapshot](openapi.json) mô tả cả request/response/error schema; [dictionary](status-dictionary.md) khóa trạng thái và phản ứng với lỗi. FE gọi `/api` qua Vite proxy, backend route không có prefix `/api`.

Từ 0.4.0: bốn vai trò renter/owner/manager/admin (manager không còn quyền nghiệp vụ từ 05/10) (`backend/app/capabilities.py` là ma trận quyền duy nhất), domain organization/membership/ownership, audit log và public/private projection (`backend/app/projection.py`). Schema ledger lúc mở 0.4.0 là v3 (hiện là v13, xem cuối tài liệu); luồng 0.3.0 renter/manager giữ nguyên hành vi.

## Auth và lỗi

`POST /auth/login {username,password}` → `{access_token,token_type:"bearer",expires_at,actor:{id,role}}`. Token do server cấp, không gửi role từ client. `GET /auth/me` trả actor kèm `landlord_status`: `null` với khách, còn chủ nhà là `pending`/`approved`/`rejected` (owner seed luôn là `approved`). `POST /auth/logout` thu hồi token, trả `{status:"logged_out"}`. Các endpoint còn lại trừ `/health`, `/ready`, tài liệu Swagger và nhóm auth lifecycle dưới đây yêu cầu `Authorization: Bearer …`.

Tài khoản seed (mật khẩu mẫu `local-<username>-password`): `renter-a`, `renter-b` (renter), `owner-a`, `owner-b`, `owner-c`, `owner-d` (owner), `manager-a`, `manager-b` (manager cũ), `admin-a` (admin). Owner/manager/admin được bootstrap membership trong đơn vị mặc định `org-demo`; renter không thuộc đơn vị.

Tài khoản tự đăng ký phải xác minh email trước khi login: sai mật khẩu luôn trả `invalid_credentials`/401 (không tiết lộ tài khoản); đúng mật khẩu nhưng chưa xác minh trả `account_unverified`/403, bị vô hiệu hóa trả `account_disabled`/403.

Domain/validation/HTTP errors dùng `{error:{code,message,fields?},request_id}`; lỗi input không trả lại payload nhạy cảm. HTTP status 401: cần login; 403: sai quyền/phòng chưa được phép xem; 404: tài nguyên không được tìm/chiếu; 409: xung đột phiên bản/trạng thái/token; 422: input sai. Header `X-Request-ID` dùng đối chiếu, kể cả lỗi 500. Thiếu/sai bearer trả 401 với `WWW-Authenticate: Bearer`; 404/405 cũng dùng envelope thống nhất.

## Tài khoản, hồ sơ và phiên (0.4.0)

| Endpoint | Request / response |
|---|---|
| `POST /auth/register` (201) | `{username,password,email,display_name?,account_type?}` → `{status:"pending_verification",user:{id,role},delivery:"dev_stub_log_only"}`. `account_type` nhận `renter` (mặc định) hoặc `owner`; giá trị khác → 422. Chọn `owner` tạo tài khoản chủ nhà chưa xác minh với `landlord_status='pending'`; role staff không bao giờ nhận từ client. Mật khẩu ≥10 ký tự; username `^[a-z0-9][a-z0-9-]{2,49}$`; trùng tên → 409 `account_exists`, trùng email → 409 `email_in_use`. |
| `POST /auth/verify` | `{username,token}` → `{status:"verified"}`. Token đơn dụng, hạn 30 phút; sai → 409 `invalid_token`, đã dùng → `token_used`, hết hạn → `token_expired`. |
| `POST /auth/password-reset/request` | `{username}` → `{status:"reset_requested"}` giống hệt cho mọi username (không tiết lộ tồn tại). Tài khoản seed và bị disable không được cấp token. |
| `POST /auth/password-reset/confirm` | `{username,token,new_password}` → `{status:"password_reset"}`; thu hồi toàn bộ token đăng nhập, đánh dấu email đã xác minh. |
| `GET/PATCH /me/profile` | GET trả `{id,role,display_name,email,email_verified,status,consents,organizations}`. PATCH chỉ nhận `display_name?`,`email?`,`consents?` (`save_history`,`remember_sessions`); gửi role/organization bị 422. Đổi email đặt lại `unverified` và yêu cầu xác minh mới. |
| `GET /me/sessions` | Danh sách `{token_id,expires_at,revoked}`; `token_id` suy từ hash đã lưu, không lộ token/hash. |
| `DELETE /me/sessions/{token_id}` | `{status:"revoked"}`; không thuộc user → 404, đã thu hồi → 409 `session_revoked`. |

Gửi email xác minh là **stub phát triển ghi log** (`dev_stub_log_only`), nhãn rõ, không gọi dịch vụ ngoài. Ở chế độ public (`HOMEMATCH_PUBLIC=true`), `register`, `password-reset/request` và PATCH đổi email trả 503 `delivery_unavailable` thay vì giả gửi.

## Đăng ký chủ nhà và duyệt (BE-03, 08/10/2026)

Chủ nhà tự đăng ký (`account_type:"owner"`) phải xác minh email, sau đó ở trạng thái `landlord_status='pending'`: đăng nhập được, tạo và sửa tin được, nhưng **không công khai tin được** — mọi yêu cầu publish (tạo tin `published=true`, PUT tin với `published=true`, PATCH status `published:true`) trả 403 `landlord_not_approved`. Tạo tin không gửi `published` thì mặc định là bản nháp chưa công khai. Owner seed (`owner-a`…`owner-d`) luôn được coi là `approved`.

| Endpoint | Quy tắc |
|---|---|
| `GET /admin/landlord-applications?status=pending\|approved\|rejected` | Chỉ admin (capability `account:review_landlord`); mặc định `pending`. Trả `[{user_id,email,display_name,landlord_status,created_at,verified}]`; owner seed không xuất hiện. |
| `POST /admin/landlord-applications/{user_id}/approve` (200) | `{user_id,landlord_status:"approved"}`. Cập nhật status, tạo membership `owner` trong `org-demo` (idempotent), ghi audit `account.landlord_approved`, thông báo cho chủ nhà (dedup `landlord:{user_id}:approved`). Người không phải admin → 403; user không phải owner ứng tuyển → 404. |
| `POST /admin/landlord-applications/{user_id}/reject` (200) | Body `{reason}` bắt buộc 1–500 ký tự (thiếu/sai → 422). Trả `{user_id,landlord_status:"rejected"}`, ghi audit `account.landlord_rejected`, thông báo kèm lý do (dedup `landlord:{user_id}:rejected`). |

## Ticket hỗ trợ (BE-04, 08/10/2026)

Ticket gặp nhân viên tạo từ chat (`hm_support`), chỉ admin thao tác:

| Endpoint | Quy tắc |
|---|---|
| `GET /admin/support-tickets?status=requested\|in_progress\|resolved` | Chỉ admin (capability `support:manage`/`support:list`). Trả `[{id,session_id,manager_id,status,assignee,note,created_at,updated_at,resolved_at}]`. |
| `PATCH /admin/support-tickets/{id} {status,note?}` | Chuyển trạng thái theo `requested → in_progress → resolved`, `resolved → in_progress` (mở lại). Sai chuyển → 409 `ticket_state`; `resolved` thiếu `note` → 422 `note_required`; gửi lại đúng trạng thái hiện tại → trả bản hiện tại, không ghi gì thêm. Chuyển sang `in_progress` đặt `assignee` là admin thực hiện. Mỗi lần đổi trạng thái, khách (chủ phiên) nhận một thông báo `support_update` (dedup `support:{id}:{status}`, link `/tro-ly-ai`). `GET /support-tickets` cũng chỉ còn admin; owner gọi → 403. |

## Ảnh tin và ảnh sự cố (BE-06, 08/10/2026)

Ảnh lưu metadata trong bảng `hm_media` (schema v12), file lưu theo hash nội dung tại `HOMEMATCH_MEDIA_DIR` (mặc định `.local/media` trên đĩa local). Loại ảnh quyết định bằng magic bytes (JPEG/PNG/WebP), **không** tin content-type của client. Giới hạn: 5 MB/ảnh (422 `media_too_large`), 10 ảnh/tin, 5 ảnh/sự cố (422 `media_limit`); sai loại → 422 `invalid_media`. Tải trùng (cùng tin + cùng hash) trả lại bản cũ với status 200. Không bao giờ dùng tên file người dùng gửi: đường dẫn là `{MEDIA_DIR}/{sha256[:2]}/{sha256}.{ext}`.

| Endpoint | Quy tắc |
|---|---|
| `POST /landlord/rooms/{room_id}/media` multipart `file` (201) | Chỉ chủ nhà của tin (người khác → 404). Trả `{id, url:"/media/{id}", content_type, size_bytes, position}`; trùng nội dung → 200 cùng bản cũ. |
| `DELETE /landlord/rooms/{room_id}/media/{media_id}` (204) | Chỉ chủ nhà của tin và ảnh phải thuộc tin đó, sai → 404. Xóa bản ghi; file chỉ bị xóa khi không còn bản ghi nào dùng hash đó. |
| `PATCH /landlord/rooms/{room_id}/media/order {media_ids:[…]}` (200) | Chỉ chủ nhà của tin; danh sách phải gồm đúng các ảnh hiện có → 422 `invalid_request`. Trả lại danh sách ảnh theo thứ tự mới. |
| `POST /maintenance/{ticket_id}/media` multipart `file` (201) | Khách của hợp đồng đang hiệu lực hoặc chủ nhà của phòng; người ngoài → 404. Trả media DTO; trùng → 200. |
| `GET /media/{media_id}` | Ảnh tin công khai: không cần token; ảnh tin ẩn: chỉ chủ nhà; ảnh sự cố: chỉ hai bên; người khác → 404. Trả file kèm `Cache-Control: private, max-age=300` (ảnh công khai dùng `public`). |

DTO mới: `photos:[{id,url}]` (theo `position`) có trong `GET /listings`, `GET /listings/{id}`, `GET /landlord/rooms` và `/landlord/rooms/{id}` (trường `photos` của room) và mỗi mục trong `GET /maintenance`.

## Ưu đãi của chủ nhà (BE-07, 08/10/2026)

Bảng `hm_promotions` (schema v13), mỗi tin một bản ghi. Ưu đãi **không đổi giá thuê và không vào xếp hạng** (`catalog.py`, `costs.py`, `semantic.py` không đọc `hm_promotions`).

| Endpoint | Quy tắc |
|---|---|
| `PUT /landlord/rooms/{room_id}/promotion {text, valid_until}` (200) | Chỉ chủ nhà của tin (người khác → 404). `text` 1–200 ký tự, lưu đã che PII (số điện thoại → `[SĐT đã che]`, email → `[email đã che]`); `valid_until` từ hôm nay (UTC+7) đến hôm nay + 90 ngày, sai → 422 `invalid_promotion`. Trả `{room_id, text, valid_until}`. |
| `DELETE /landlord/rooms/{room_id}/promotion` (204) | Chỉ chủ nhà của tin; chưa có ưu đãi → 404. |

DTO: `promotion:{text, valid_until}|null` (chỉ khi còn hạn) trong `GET /listings`, `GET /listings/{id}`, `GET /landlord/rooms`, `/landlord/rooms/{id}`. Job chăm sóc khách (`lead_reengagement`) nối vào câu gợi ý `" — Ưu đãi: {text} (đến {dd/mm})"` cho căn còn ưu đãi; dedup key giữ nguyên.

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
{"session_id":"…","run_id":"…","status":"published","profile_version":1,"results":["…Candidate…"]}
```

Chưa có run thì status `awaiting_confirmation`, không có run_id. Published results chứa Candidate: ID/revision/title/location, CostResult, score/components, reasons/tradeoffs, source, synthetic, algorithm và `verification` (cờ dữ liệu chưa rõ: `amenity_unknown:*`, `fee_rate_unknown:*`, `location_approximate`/`area_only`, `location_uncertainty_{n}m`). Khi status là `no_match`/`needs_verification`, results DTO kèm `suggestions`: các bước nới lỏng mềm do người thuê tự quyết (mở rộng khu vực, hạ tiện ích bắt buộc xuống ưu tiên, bán kính, xem lại trần đã xác nhận); hệ thống không tự nới điều kiện cứng. Không trả raw graph state hoặc candidate ngoài run đã công bố. `null` full cost là thiếu dữ liệu; `*_known_vnd` là subtotal. P unavailable có thể fallback B1 trong app, nhãn algorithm/diagnostics nói rõ; eval không dùng fallback làm P.

Public projection (module `backend/app/projection.py`) là allowlist: chỉ phòng `published=true` vào danh sách công khai, tọa độ exact bị hạ xuống `approximate`, trường ngoài allowlist không thể lộ; item AI chỉ public khi run `published`. Đường public API catalog sẽ đến ở HM-03/W-06; module này là nguồn projection cho đường đó.

## Tài chính, căn hộ và mô phỏng (GĐ2, 05/10/2026)

**`Profile`** (body xác nhận) có thêm các trường tùy chọn:

- `min_bedrooms` (1–5);
- `monthly_income_vnd`;
- `cost_split`: `none` | `equal`;
- `loan`: `{annual_rate: "0.12", term_months: 1–36, max_principal_vnd?}`. `null` nghĩa là không vay.

`room_type` nhận `room` | `studio` | `apartment`. **`Room`** và **`Candidate`** có thêm `room_type`, `bedrooms`. `Room` có thêm `features_text` (mô tả mềm, được đưa vào văn bản semantic).

`POST /sessions` điền sẵn nháp từ memory khi khách đã đồng ý: `field_status = inferred`, `evidence_ref = memory:<phiên>`, `draft_revision` vẫn bằng 0. Chat provenance có thêm `agent`, `tools`, `steps`; run diagnostics có `agent` của agent xếp hạng. `/admin/metrics` có thêm `semantic_usage: {query_embedding_calls, query_cache_hits}`.

`/admin/metrics` có thêm `cost` (BE-05, 08/10/2026): `{estimated_cost_vnd, price_effective_date, missing: [str], basis: {...}}` hoặc `null` khi chưa cấu hình bảng giá. Tính bằng `Decimal` từ `provider_usage.by_model` (token input/output và embedding tách riêng, làm tròn VND `ROUND_HALF_UP`); thiếu bất kỳ giá hay tỷ giá nào cần dùng → `estimated_cost_vnd: null` kèm `missing` liệt kê khóa còn thiếu, không ước đoán. Bảng giá đặt qua `HOMEMATCH_PROVIDER_PRICES_PATH` (mẫu `infra/provider-prices.example.json`, không chứa giá thật; người dùng tự điền từ trang giá chính thức).

Tiền tương đối trong chat (AG-02, 05/11/2026): mẫu "nới/lên/tăng thêm N" và "giảm N" cộng/trừ vào mức cũ đã nêu; "giảm … xuống N" là mức mới. Chưa có mức cũ thì hỏi lại, không dùng số trong câu làm trần (sửa bug chip "Nới ngân sách" đọc "lên thêm 1 triệu" thành trần 1 triệu). `MessageResult` thêm `budget_explicit: true` khi lượt áp được mức tiền — FE chỉ được đưa `budget_hint` vào trần tổng tháng khi thấy cờ này kèm evidence `chat:`/`agent:`. Oracle `data/oracles/relative_budget_cases.json` (12 ca).

Tham chiếu căn trong chat (AG-05, 05/11/2026): `resolve_room_reference(text, visible_items)` trong `agent_guard.py` hiểu id mọi nguồn (`chotot-\d+`, `synthetic-room-\d{3}`, `room-[hex10]`, `demo-\d+`), thứ tự danh sách ("căn số 2", "căn thứ hai", "căn đầu tiên", "căn cuối") và tiêu đề rút gọn duy nhất — chỉ trả id nằm trong kết quả hiện tại; id được nhắc nhưng ngoài danh sách → lỗi `not_visible` (không lặng thay bằng căn đầu). Áp dụng cho đặt lịch, mô phỏng vay, cẩm nang gắn căn và tool vòng lặp; FE hiển thị mã phòng trong câu trả lời bấm được.

Agent điều khiển workspace (WS-01, 05/11/2026): request `POST /messages` (và `/stream`) nhận thêm `workspace: {view, selected_room_id, visible_room_ids[≤30], focus_room_ids[≤4]}` để agent hiểu "căn này"/"căn thứ 2". Response `MessageResult` thêm `view` (map|list|detail|gallery|compare|cost|route|nearby|area|trust|contract|booking|visit|saved|keep|clear — view lạ client bỏ qua giữ view cũ), `view_payload`, `anchor` (mốc đã tra), `criteria` (tiêu chí server giữ, không thu nhập), `suggested_prompts`, `turn_id`. View được chọn TẤT ĐỊNH theo tool của lượt (confirm_and_search → map khi có điểm đến/list; room_details → detail; estimate_cost → cost; còn lại keep) — LLM không tự chọn view.

Stream các bước xử lý (WS-02, 05/11/2026): `POST /sessions/{id}/messages/stream` cùng body, trả `application/x-ndjson` — từng dòng `{"type":"step","step":{name,kind:"router|tool|guardrail|system",detail}}` phát ngay khi chạy (không PII/tiền/thu nhập), dòng cuối `{"type":"done","data":<MessageResult>}` hoặc `{"type":"error","error":{code,message}}`. Timeout lượt 60 s; client thử lại tối đa 2 lần khi đứt rồi fallback về endpoint trả một lần. Endpoint cũ `POST /messages` giữ nguyên.

Vòng lặp agent (AG-13, 05/11/2026, chỉ khi `HOMEMATCH_LLM_MODE=openai`): một lượt `POST /sessions/{id}/messages` cho phép LLM tự suy luận và tự gọi tool qua `ToolBox.call` (tối đa 6 bước; tool lỗi trả lỗi có cấu trúc cho model, không 500). `MessageResult` thêm `steps: ["tool: mô tả", …]` (không PII, không tiền/thu nhập) và `agent_mode: "loop" | "graph_fallback"` (model lỗi/hết ngân sách phiên → graph cũ `route → interview`, nhãn `graph_fallback`; chế độ demo không có hai trường này). Model không được tự ghi trường tiền; mức tiền trong câu khách được đọc tất định. Số trong câu trả lời được hậu kiểm regex — không khớp câu khách/kết quả tool thì thay bằng câu template.

Chat có thêm ý định `simulate_finance` (AG-02, 08/10/2026): `MessageResult` nhận thêm `status: "simulation" | "needs_results"` và `simulation: {room_id, room_title, scenario: {annual_rate, term_months, principal_vnd}, result} | null` với `result` giống một phần tử của `POST /sessions/{id}/simulate`. Số trả góp do tool tất định tính (không qua LLM); chưa có kết quả hiện tại → `needs_results`.

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

## Kết quả gợi ý — công bố ngay, không duyệt (quyết định 05/11/2026)

Bước chủ nhà duyệt gợi ý đã bị bỏ: `set_draft` ghi thẳng `published` (có căn) / `needs_verification` / `no_match`; graph là `rank → save_draft → publish`, không còn `interrupt()` hay resume. Người thuê nhận thông báo `rooms_ready` mỗi run công bố (trước đây `rooms_approved`); chủ nhà nhận lead `source="recommended"` khi căn của họ lọt top 5 (không kèm thu nhập). Bảng `hm_run_reviews` giữ nguyên dữ liệu cũ, chỉ đọc.

| Endpoint | Quy tắc |
|---|---|
| `POST /sessions/{id}/rerun` | Người thuê chạy lại vòng tìm khi run hiện tại `generating`/`generation_failed` → `ResultsResult`. 409 `retry_conflict` nếu run không lỗi, 409 `no_run` nếu chưa có run, 409 `stale_profile` nếu hồ sơ đã đổi. |
| `POST /admin/failed-runs/{run}/retry` | Chỉ admin: tạo lại run hiện tại đang lỗi generation → projection admin (không trả hồ sơ, `housing_ratio` bị che). Run mới không thừa kế gì ngoài hồ sơ đã xác nhận. |
| `GET /admin/failed-runs` | Admin: các run `generating` hoặc `generation_failed` |

Trạng thái run còn `generating, generation_failed, published, invalidated, no_match, needs_verification` — các trạng thái duyệt cũ (`pending_review`, `partially_published`, `reviewed`, `rejected`, `needs_revision`) chỉ còn trong migration v16 và dữ liệu lịch sử. Migration v16 chuyển run cũ đang chờ/đang duyệt sang `invalidated`; khách xác nhận lại hồ sơ để chạy vòng mới.

## Nền tảng: 5 phân hệ (E1–E6, 05/10/2026)

| Nhóm | Endpoint | Ghi chú |
|---|---|---|
| Tìm kiếm công khai | `GET /listings` (query: `city, area, room_type, min_rent, max_rent, max_monthly, min_area_m2, min_bedrooms, people, amenities[], sort, page, page_size`) | Không cần đăng nhập. Chỉ tin `published`, chưa cọc/thuê. Tham số lạ → 422. `sort` nhận `monthly_asc, monthly_desc, rent_asc, area_desc, posted_desc` (31/10: "Mới đăng" chỉ ở tìm theo bộ lọc). DTO tin có thêm `description, posted_at, poster_kind, ward, ward_2025, street, available_from` và quote có `payment_cycle_months, min_lease_months`; chưa biết là `null`. |
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
| Admin | `GET /admin/transcripts`; `GET /admin/transcripts/{session}`; `GET /admin/handovers`; `GET /admin/users`; `GET /admin/rooms`; `PATCH /admin/rooms/{id}/status`; `GET /admin/metrics`; `POST /admin/jobs/run`; `GET /admin/jobs`; `GET /admin/support-tickets`; `PATCH /admin/support-tickets/{id}` | Mở transcript ghi audit `transcript.viewed`. Transcript đã che PII, giữ 90 ngày. Ticket hỗ trợ xem mục riêng ở trên. |

Văn bản hợp đồng, hóa đơn, biên lai trả về `{html}` để giao diện hiển thị và in. Đây không phải chữ ký số.

## Lịch xem và retry

`POST /sessions/{id}/viewings` (201) nhận `{room_id,requested_at,idempotency_key,mode:"offline"|"online"}`; timestamp tương lai có múi giờ. `POST /listings/{id}/viewings` đặt thẳng từ tin đăng (không cần phiên AI; phòng đã cọc/thuê → 409 `not_available`). `GET /viewings`/`GET /viewings/{id}` theo quyền bản ghi (khách của lịch hoặc chủ nhà của phòng). `POST /landlord/viewings/{id}/respond {status:"confirmed"|"declined"}` chỉ chủ nhà của phòng. Viewing DTO: `id,session_id?,run_id?,room_id,requested_at,status,landlord_id,mode,meeting_url`; lịch trực tuyến có `meeting_url` (Jitsi). Tạo mới là `requested`, chưa là lịch xác nhận.

Review/viewing có replay key; giữ nguyên payload/key khi mất response. Message không auto-resend. Draft/confirm/catalog dùng CAS, đọc lại state khi 409/mạng trước thao tác tiếp. Retry generation không có key; đọc queue để tìm active run mới sau mất response. Hồ sơ/kho thay đổi làm results invalidated và chặn compare/viewing cũ.

Kho bootstrap JSON chỉ nạp khi trống; CLI import merge có revision và transaction, bỏ ID khỏi JSON không xóa bản ghi. Mọi dữ liệu demo đều synthetic. Một API process/worker, không có endpoint raw checkpoint hoặc worker tự recovery.

## Vận hành

`GET /health` giữ DTO status/storage/auth/method/workers/public (trường `auto_publish` đã bỏ cùng bước duyệt, 05/11/2026) và kiểm kết nối ledger; lỗi DB trả `storage_unavailable`/503. `public` là giá trị `HOMEMATCH_PUBLIC`: frontend chỉ bật trải nghiệm đăng nhập nhanh bằng tài khoản seed khi `auth_mode=seed` và `public=false` (môi trường demo local; bản public đã quay mật khẩu seed). `GET /ready` trả `{status:"ready",storage,schema_version:16,checks:{ledger:"ok",catalog:"ok",checkpoints:"ok"}}`; schema/catalog/checkpoint lỗi trả `not_ready`/503. Readiness kiểm storage cốt lõi; coverage/provider P được kiểm khi ranking và có fallback rõ ràng.

Metrics reset khi restart. `duration_seconds` là tổng thời gian máy xử lý, không phải p95. Provider metrics có `logical_calls,reported_tokens,calls_without_token_usage`; số tokens đã báo không bao gồm lượt thiếu usage. Log dùng route mẫu, không lưu URL/query/body, token hoặc raw chat; log duy nhất chứa mã xác minh là DEV-STUB có nhãn giả. Dùng `backend/logging.json` và `--no-access-log` khi chạy server.

Manager diagnostics bổ sung `ranking_version,ranking_config,profile_hash,query_text_hash,catalog_version,requested_method`. Các metadata này lưu trong snapshot run, không mở thêm đường đọc cho renter. Migration ledger tự chạy khi startup, hoặc chủ động dùng `python -m backend.manage migrate`. Schema hiện tại là v16 (v4 memory/cache embedding, v5 danh sách nháp theo chủ nhà, v6 lượt xem và lịch từ tin, v7 live chat/transcript, v8 thông báo/job, v9 PMS & CRM, v10 trạng thái duyệt chủ nhà, v11 vòng đời ticket hỗ trợ, v12 ảnh tin/ảnh sự cố, v13 ưu đãi chủ nhà, v14 số điện thoại liên hệ, v15 căn đã lưu của người thuê, v16 bỏ duyệt gợi ý — công bố ngay); DB v1/v2 được tiếp nhận, bootstrap tạo đơn vị mặc định và membership cho staff seed đã tồn tại, không xóa/sửa bản ghi cũ. Backend từ chối DB có schema mới hơn code.
