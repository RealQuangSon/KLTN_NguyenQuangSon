# Thiết kế API sản phẩm HomeMatch v1

**Ngày:** 04/10/2026. **Trạng thái:** contract đích để phân rã và triển khai, chưa phải OpenAPI đang chạy. API hiện tại là [0.3.0](api-contract.md) và [snapshot](openapi.json). Không gọi endpoint bên dưới rồi kết luận backend hiện hỗ trợ.

## 1. Namespace, xác thực và projection

Target backend namespace `/v1`; trình duyệt có thể gọi `/api/v1` qua reverse proxy. Backend hiện không có prefix `/api`; không chuyển client đang chạy sang v1 trước migration tương thích. P0 phải sinh OpenAPI v1 và các ví dụ happy/negative trước khi FE nối từng module.

Actor lấy từ token, không từ body. Membership/capability và ownership/assignment kiểm server tại mỗi tài nguyên, file và export. Public projection khác owner/manager/renter projection. API không cung cấp raw checkpoints, nháp AI hoặc raw chat cho actor không có quyền.

Envelope lỗi giữ cấu trúc `{error:{code,message,fields?},request_id}`; 401 cần đăng nhập, 403 sai quyền, 404 tài nguyên không được tìm/chiếu theo policy, 409 stale/conflict, 422 validation, 429 limit, 503 unavailable. Không trả lại input riêng tư trong validation.

## 2. Quy tắc write, phiên bản và retry

| Nhóm | Quy tắc v1 |
|---|---|
| PATCH draft/profile/room/contract draft/meter draft | `expected_revision`; stale trả 409, đọc lại; không overwrite âm thầm |
| Confirm profile/review/publish/activation/move-in/out/invoice issue/payment verify/refund | Request có expected version/state và `Idempotency-Key`; scope actor+operation+resource; cùng key khác payload trả conflict |
| Viewing/create ticket/favorite/saved search | Idempotent theo operation/key hoặc unique actor-resource; response trả resource ID đọc lại được |
| Chat message | Client-generated message ID được dedup trong v1; nếu chưa triển khai vẫn giữ quy tắc 0.3.0 không auto-resend |
| Upload/file | Upload intent có quyền/type/size/hash; finalize kiểm asset thực; file read có access check/link có hạn; không lấy URL tùy ý làm trusted asset |
| Notification | Transactional outbox; dedup recipient+event+channel; delivery status độc lập status nghiệp vụ |

Phải chốt TTL/scope/key retention và race cases trong OpenAPI/implementation P0. Các thao tác làm thay đổi tiền hoặc hiệu lực thuê lưu ledger/audit bất biến; lỗi phản hồi sau commit không tạo lần ghi thứ hai. Quy tắc v1 này mở rộng khả năng 0.3.0, không được giả hiện đã có.

## 3. Resource và endpoint đích

Các path trong bảng đều tương đối với `/v1`. Tách action rõ để kiểm transition thay vì cho PATCH tự sửa mọi status.

| Module | Endpoint dự kiến | Giới hạn nghiệp vụ |
|---|---|---|
| HM-01 | `POST /auth/register`, `/auth/verify`, `/auth/login`, `/auth/logout`, `/auth/password-reset/request`, `/auth/password-reset/confirm`; `GET /auth/me` | Xác minh/reset có hạn/một lần; rate limit; actor/capability từ server |
| HM-01 | `GET/PATCH /me/profile`; `GET/DELETE /me/sessions/{token_id}`; `GET/PATCH /me/preferences` | Consent/retention, token revoke; không patch role/org |
| HM-01/10 | `GET/POST /organizations`, `GET/POST /organizations/{id}/memberships`, action grant/revoke/assign theo capability | Không self-elevate; audit, chuyển giao assignment |
| HM-02 | `GET/POST /owner/buildings`, `GET/POST /owner/rooms`, `GET/PATCH /owner/rooms/{id}` | CRUD phạm vi đơn vị, revision, archive thay hard-delete bản ghi đã dùng |
| HM-02 | `POST /rooms/{id}/submit`, `/moderation/rooms/{id}/review`, `/rooms/{id}/suspend`, `/rooms/{id}/archive`; `POST /rooms/{id}/availability` | Draft/published snapshot riêng; availability không đồng nhất moderation |
| HM-02 | `POST /assets/upload-intents`, `/assets/{id}/finalize`; `GET /assets/{id}/download` | Type/size/hash/quyền, private contract/evidence; public media đã approved |
| HM-03 | `GET /catalog/rooms`, `/catalog/rooms/{id}`, `/catalog/map`; `POST /catalog/rooms/{id}/reports` | Public published projection, filters/sort/cursor/approximate location |
| HM-04 | `POST /consultations`; `GET /consultations/{id}`; messages/draft/confirm/results/retry/review theo contract mục tiêu | Duy trì profile/run/catalog versions, pending hidden; không owner đọc private chat |
| HM-04 | `POST /costs/estimate`; `GET /manager/recommendations`; `POST /manager/recommendations/{run_id}/review`, `/retry` | Cost không cần chạy tìm; review assigned; finalize atomic |
| HM-05 | `GET/PUT/DELETE /me/favorites/{room_id}`; `GET/POST /me/saved-searches`; `PATCH/DELETE /me/saved-searches/{id}` | Account persistence, tin hết hiệu lực có status, không copy approval |
| HM-05 | `GET /me/consultations`; `POST /comparisons` | Mode `public_catalog`/`ai_recommendation`, 2–3 phòng thực khác nhau, một scenario; history không bypass visibility |
| HM-06 | `GET/POST /viewings`; `GET /viewings/{id}`; action confirm/decline/cancel/reschedule/complete/no-show | Expected revision, timezone, slot conflicts; manager assigned confirm |
| HM-06 | `GET/POST /support-tickets`; `GET/PATCH /support-tickets/{id}`; action assign/resolve/close/reopen | Scope theo liên hệ nghiệp vụ, transition và lý do |
| HM-06 | `GET /me/notifications`; `POST /me/notifications/{id}/read`; `GET /operations/notification-failures` | Recipient only; operations theo capability; retry event không gửi trùng |
| HM-07 | `GET/POST /contracts`; `GET/PATCH /contracts/{id}`; action submit/accept/activate/cancel/terminate/renew | Document/terms snapshot và acceptance đúng version của hai bên |
| HM-07 | `GET/POST /reservations`; release/expire theo policy; `GET /tenancies/{id}`; move-in/move-out/close | Reservation có hạn, overlap transaction, bàn giao/sổ cọc |
| HM-07 | `GET /tenancies/{id}/deposit-ledger`; `POST /tenancies/{id}/deposit-events` | Receipt/refund/deduction bằng event có evidence/approval, không free-form overwrite balance |
| HM-08 | `GET/POST /meters`; `GET/POST /meters/{id}/readings`; action verify/correct/replace | Quantity/unit/source/evidence; correction có history |
| HM-08 | `GET/POST /invoices`; `GET/PATCH /invoices/{id}`; action issue/void/adjust | PATCH chỉ draft; kỳ/terms/rates snapshot, tiền trả trước và rounding |
| HM-08 | `POST /invoices/{id}/payment-evidence`; `GET/POST /receipts`; action verify/reject/allocate/reverse/refund | Evidence chưa paid; verified allocation tính balance; idempotency/ledger |
| HM-08 | `GET/POST /billing-disputes`; `GET /organizations/{id}/receivables` | Outstanding/overpayment và quyền scope, không lộ người thuê khác |
| HM-09 | `GET/POST /maintenance-tickets`; `GET/PATCH /maintenance-tickets/{id}`; action triage/assign/schedule/approve-cost/resolve/close/reopen/cancel | Tenancy scope, private attachments, cost event chuyển billing một lần |
| HM-10 | `GET /operations/dashboard`, `/operations/audit`, `/operations/queues`; `POST /privacy-requests`; `GET /privacy-requests/{id}` | Dashboard thật, audit projection có quyền, privacy workflow có status/retention |
| HM-10 | `GET /health`, `/ready`, metrics có kiểm quyền | Readiness DB/schema/checkpoints/media/queue tùy vai trò process, không lộ secrets |

## 4. DTO chung cần khóa ở P0

| DTO | Trường tối thiểu và quy tắc |
|---|---|
| Resource metadata | `id,revision,created_at,updated_at`; tổ chức/actor refs chỉ trong projection có quyền |
| PhysicalRoom/Listing | Physical room ID ổn định và unique organization/building/room_code; listing ID/source/draft revision/published revision riêng; overlap/dedup theo physical room |
| PublicRoom | Listing ID/physical room ID/published revision/title/type/area/capacity/amenities/media/approximate location/availability/quote/verification/source; không private exact address/contact |
| Quote/CostResult | Tiếp tục quote/scenario/Decimal VND/known subtotal/full nullable total/missing/lines/sources; không dùng float money |
| ComparisonRequest | Discriminated union: `mode=public_catalog` có `listing_refs:[{listing_id,published_revision}]` và scenario; `mode=ai_recommendation` có `run_id,profile_version,catalog_version,room_ids,scenario` cùng published/current. Mỗi mode 2–3 phòng thực khác nhau; không nhận fields mode kia |
| ViewingRequest | Discriminant `source_mode=public_catalog` có listing_id/published_revision; `source_mode=ai_recommendation` có run_id/profile_version/catalog_version/room_id. Cả hai có requested_at timezone và key; server resolve physical room, access/availability/current |
| Viewing | Physical room/listing/version/source refs đã resolve, proposed/confirmed time có timezone, status/revision/history |
| Contract | Parties/organization/room/period/terms/document refs/terms_version/acceptances/status; private projection |
| Tenancy | Contract/physical room/parties/period/status/move-in-out refs; settlement_status pending/disputed/settled riêng, closed không tự settled; ledger là nguồn balance |
| MeterReading | Meter/physical room/tenancy/period `[start,end)`/cumulative reading/unit/evidence/measured-or-estimated/verified_by/correction/replacement refs; consumption delta riêng. Rate đầu kỳ, chia đoạn chỉ theo accepted amendment+boundary measured reading |
| Invoice | Tenancy/period/terms version/due_at/lines/total/adjustments/allocated/balance/revision; lifecycle status draft/issued/void, payment_status unpaid/partially_paid/paid, overdue derived flag; line có source/unit/quantity/rate |
| Receipt | Payer/amount/time/evidence/verification status/allocations/reversal/refund refs; amount integer VND, raw bank credentials không lưu |
| DepositEvent/CostEvent | Amount/payer/source/terms ref/evidence/approval actor+version; proposed/accepted/disputed, reversal/refund refs; disputed không tự quyết toán/charge |
| Ticket | Related resource/creator/assignee/priority/status/timeline/private attachments/payer cost approval refs |
| Notification | Recipient/event/channel/status/read_at; URL nội bộ kiểm quyền khi mở; body tối thiểu |

`mode` dùng cho comparison, `source_mode` dùng cho viewing. Các giá trị đều là `public_catalog|ai_recommendation`; trường `source` hiện có của Room/Candidate vẫn là provenance nguồn dữ liệu, không bị đổi thành mode. Renter projection của AI run vẫn đọc theo quyền/current, dù một listing tương ứng đã public.

## 5. Ví dụ quy tắc cần kiểm

Một invoice 3.000.000 VND có receipt verified 1.000.000 VND allocation thì balance 2.000.000 VND, status issued và payment_status partially_paid. Tải evidence cho phần còn lại vẫn giữ balance tới khi verify/allocate. Cùng key verify lần nữa trả receipt cũ và không tăng allocation. Nếu quá due_at, overdue=true dù payment_status vẫn partially_paid.

Một contract terms v1 đã được renter accept, khi owner sửa rent thành v2 thì acceptance v1 không đủ activate. API trả conflict nếu client dùng revision cũ; không tự sao acceptance sang v2. Các ví dụ này là oracle hợp đồng/billing cần triển khai, không phải response đã đo từ backend hiện tại.

## 6. Tiến trình tương thích

P0 chốt DTO/state/error → backend viết OpenAPI/schema và migration → frontend mock/client → integration từng HM → browser/negative/race tests → cập nhật contract thực thi và trạng thái. 0.3.0 giữ nguyên cho demo đến khi có migration và client v1 tương ứng. Snapshot `docs/openapi.json` và `docs/release-manifest.json` cũ không được tái gắn nhãn là release v1.
