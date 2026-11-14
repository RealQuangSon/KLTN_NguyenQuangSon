# Trạng thái và lỗi backend HomeMatch 0.4.0

Bảng này mô tả hành vi đang chạy. "Người thuê/renter" là **khách**; kết quả công bố ngay, không có bước duyệt (D-10). Mã lỗi đích (`invalid_loan`, `override_reason_required`, `tool_not_allowed`) nằm ở [API đích](api-san-pham-v1.md).

## Bản gợi ý

| Status | Ý nghĩa | Hành động tiếp theo | Phòng hiển thị với người thuê |
|---|---|---|---|
| `awaiting_confirmation` | Chưa có run | Người thuê xác nhận hồ sơ | Rỗng |
| `generating` | Đã lưu run, chưa tạo xong nháp | Người thuê chạy lại hoặc admin retry nếu process đã gián đoạn | Rỗng |
| `generation_failed` | Generation/checkpoint lỗi | Người thuê chạy lại hoặc admin retry tạo run mới | Rỗng |
| `published` | Xếp hạng xong và có căn đủ điều kiện | Xem kết quả, compare/viewing | Top căn theo đúng thứ tự xếp hạng |
| `no_match` | Không có phòng đủ điều kiện | Điều chỉnh nhu cầu hoặc kho | Rỗng |
| `needs_verification` | CHỈ run lịch sử (trước D-12, 08/11/2026): từng giữ tin thiếu dữ liệu. Không còn được sinh mới; tin thiếu phí/sức chứa nay `published` ngay kèm nhãn | Xác nhận lại hồ sơ để xem các tin đó kèm nhãn ước tính | Rỗng |
| `invalidated` | Hồ sơ đổi, hoặc kho đổi làm kết quả xếp hạng khác đi (D-11) | Xác nhận hồ sơ để tạo bản mới | Rỗng |

Profile/active run được kiểm lại khi đọc. Khi phiên bản kho khác với run, hệ thống xếp hạng lại rồi so với danh sách đã lưu: giống hệt thì giữ run và ghi phiên bản mới; khác thì `invalidated`. Run `generating` không được xét lại (D-11). Các trạng thái khác `published` không trả candidate, diagnostics hay quyết định nội bộ qua results của người thuê. Quản lý chỉ đọc/duyệt phiên được phân công.

Chat có `needs_clarification`, `cost_estimate`, `support_requested`; đây là trạng thái phản hồi chat, tách khỏi trạng thái run.

## Vòng đời lịch xem (crawl.md E-01/E-02, 08/11/2026)

Viewing bắt đầu `requested` rồi chuyển theo bảng dưới (chuyển sai → 409 `viewing_conflict`; lặp đúng trạng thái đích → trả kết quả cũ, không ghi event). Bên xử lý: chủ nhà với tin của mình (`handler=landlord`), admin điều phối với tin cào (`handler=concierge`).

| Từ | Đến | Ai được phép |
|---|---|---|
| `requested` | `confirmed`, `declined`, `reschedule_proposed`, `cancelled` | handler xác nhận/từ chối/đề xuất giờ; người thuê hủy |
| `reschedule_proposed` | `confirmed` (accept: chỉ khi đề xuất do bên xử lý tạo — `requested_at` nhận giờ đề xuất), `cancelled`, `requested` (choose_time: người thuê chọn giờ mới, `requested_at` cập nhật) | người thuê |
| `confirmed` | `completed`, `no_show`, `cancelled` (người thuê hủy), `requested` (người thuê choose_time — đổi giờ rồi chờ bên xử lý xác nhận lại), `reschedule_proposed` (CHỈ bên xử lý đề xuất) | handler hoàn tất/vắng mặt; người thuê hủy/đổi giờ về requested |

Sửa 08/11: người thuê KHÔNG tự dời lịch confirmed rồi tự duyệt — mọi đề xuất giờ mới đều do bên xử lý tạo; accept của người thuê chỉ hợp lệ khi có `proposed_at` (đề xuất từ bên xử lý). `accept`/`choose_time` cập nhật `requested_at` thật (giờ cũ → mới ghi vào `hm_viewing_events`) và xóa `proposed_at`. Hành động handler-only (`propose/confirm/decline/complete/no_show`) trả 403 TRƯỚC mọi kiểm tra trạng thái với người không phải bên xử lý (theo bản ghi: landlord đúng `landlord_id`, admin có capability `viewing:concierge`).

Mọi đường tới `confirmed` đều chạy kiểm tra `stale_viewing`. Mỗi chuyển trạng thái ghi vào `hm_viewing_events` (ai, lúc nào, từ đâu → đâu, lý do) và có thông báo in-app với dedup key. Liên hệ khách (tên + SĐT, có đồng ý khi đặt): người thuê thấy của mình; chủ nhà chỉ thấy từ `confirmed`; lịch `concierge` chỉ lộ qua route xem SĐT riêng cho admin và mỗi lần xem ghi audit (`viewing.contact_revealed`).

## Trạng thái tài khoản chủ nhà (BE-03, 08/10/2026)

`landlord_status` trên `GET /auth/me`: `null` với khách; owner seed luôn là `approved`.

| Status | Ý nghĩa | Hành động tiếp theo |
|---|---|---|
| `pending` | Chủ nhà tự đăng ký đã xác minh email, chưa được duyệt | Tạo/sửa tin nháp được; công khai tin bị chặn; chờ admin duyệt |
| `approved` | Admin đã duyệt; được membership `owner` trong `org-demo` | Công khai tin bình thường |

Lỗi mới: 403 `landlord_not_approved` — chủ nhà chưa được duyệt mà yêu cầu công khai tin; client hiển thị dòng chờ duyệt và khóa ô publish.

## Trạng thái ticket hỗ trợ (BE-04, 08/10/2026)

Ticket tạo từ chat khi khách muốn gặp nhân viên; chỉ admin liệt kê và chuyển trạng thái.

| Status | Ý nghĩa | Chuyển được sang |
|---|---|---|
| `requested` | Khách vừa yêu cầu, chưa ai nhận | `in_progress`, `resolved` |
| `in_progress` | Admin đã tiếp nhận (`assignee` là admin thực hiện) | `resolved` |
| `resolved` | Đã xử lý xong (bắt buộc có `note`; `resolved_at` được ghi) | `in_progress` (mở lại) |

Sai chuyển → 409 `ticket_state`; `resolved` thiếu `note` → 422 `note_required`; PATCH lặp lại đúng trạng thái hiện tại trả bản hiện tại, không ghi thêm và không thông báo lại. Mỗi lần đổi trạng thái, khách (chủ phiên) nhận một thông báo `support_update` với dedup `support:{id}:{status}`, link `/tro-ly-ai`.

## Lỗi và phản ứng của client

Envelope thống nhất: `{error:{code,message,fields?},request_id}`. Header `X-Request-ID` khớp body; 401 có `WWW-Authenticate: Bearer`. Validation chỉ trả vị trí/loại lỗi, không trả lại input.

| HTTP / code | Ý nghĩa và xử lý |
|---|---|
| 401 `unauthorized`, `invalid_credentials` | Đăng nhập hoặc nhập lại thông tin đăng nhập |
| 403 `forbidden`, `demo_local_only` | Sai vai trò/phân công hoặc token demo được dùng từ xa |
| 403 `not_visible` | Phòng chưa thuộc gợi ý đã duyệt hiện tại; không compare/viewing từ nháp |
| 404 `not_found` | Tài nguyên không tồn tại |
| 405 `method_not_allowed` | Phương thức không được hỗ trợ |
| 422 `invalid_request` | Request không đúng schema; sửa các trường được chỉ ra |
| 422 `invalid_patch`, `invalid_amenity`, `invalid_selection`, `invalid_comparison` | Sửa nhu cầu, tiện ích hoặc danh sách ID |
| 422 `invalid_message`, `invalid_key`, `invalid_time`, `invalid_status`, `invalid_catalog` | Nội dung/key/thời gian/trạng thái chưa hợp lệ; viewing cần thời gian tương lai có timezone |
| 409 `stale_profile`, `catalog_conflict`, `stale_review`, `stale_viewing` | Đọc lại phiên/kho; tạo và duyệt bản hiện tại nếu đã stale |
| 409 `review_conflict`, `idempotency_conflict`, `viewing_conflict`, `retry_conflict` | Đã có thao tác khác; giữ key khi retry cùng payload, không tự ghi đè |
| 409 `recovery_required` | Thiếu checkpoint/điểm resume; xác nhận lại và duyệt bản mới |
| 503 `review_resume_failed` | Quyết định đã commit; manager đọc lại và retry để hoàn tất |
| 503 `ai_unavailable` | Dùng form xác nhận nhu cầu; finance và quyền vẫn do code kiểm soát |
| 422 `context_limit`, `private_semantic_text` | Rút ngắn nội dung hoặc loại tiền/liên hệ khỏi mô tả semantic |
| 503 `storage_unavailable`, `not_ready` | Kiểm tra DB/migration/checkpoint; không báo backend sẵn sàng |
| 403 `account_unverified`, `account_disabled` | Tài khoản chưa xác minh email hoặc đã bị vô hiệu hóa |
| 409 `lease_overlap`, `lease_state`, `lease_version`, `lease_not_accepted`, `invoice_exists`, `invoice_changed`, `claim_decided`, `ticket_state`, `conversation_closed`, `not_available` | Xung đột trạng thái hợp đồng, hóa đơn, sự cố, chat, phòng; đọc lại rồi thao tác |
| 422 `invoice_incomplete`, `overpayment`, `reading_start_required`, `reading_decreased`, `invalid_period`, `invalid_renter`, `note_required`, `invalid_mode` | Dữ liệu vận hành chưa hợp lệ |
| 422 `invalid_media`, `media_too_large`, `media_limit` | Ảnh không phải JPEG/PNG/WebP, vượt 5 MB hoặc vượt số ảnh tối đa (10 ảnh/tin, 5 ảnh/sự cố) |
| 422 `invalid_promotion` | Ưu đãi sai ngày hạn (phải từ hôm nay UTC+7 đến tối đa +90 ngày) hoặc nội dung trống |
| 403 `no_active_lease` | Chỉ người đang thuê mới báo hỏng được |
| 422 `invalid_memory_field` | Trường ghi nhớ không được hỗ trợ |
| 403 `tool_not_allowed`, 429 `agent_step_limit` | Lỗi nội bộ của agent (gọi tool ngoài danh sách hoặc quá số bước); lượt chat dừng, không bịa kết quả |
| 422 `override_reason_required` | Chủ nhà bỏ căn hoặc đổi thứ tự so với trợ lý mà không ghi `override_reason` |
| 403 `not_visible` (mô phỏng) | Chỉ mô phỏng căn thuộc danh sách đã duyệt hiện tại |
| 409 `invalid_token`, `token_used`, `token_expired`, `account_exists`, `email_in_use` | Mã xác minh/đặt lại sai, đã dùng, hết hạn; tên hoặc email đã tồn tại |
| 429 `budget_exceeded` | Phiên đã hết lượt gọi trợ lý; dùng biểu mẫu nhập nhu cầu |
| 503 `delivery_unavailable` | Chế độ public chưa có nhà cung cấp email; đăng ký/đặt lại mật khẩu bị tắt |
| 500 `internal_error` | Dùng request ID để đối chiếu log; đọc lại state trước khi thử mutation |

Message không auto-resend. Draft/confirm/catalog dùng revision CAS. Review/viewing giữ payload và key khi mất phản hồi. Generation retry có thể tạo run mới; đọc queue/session để tìm active run sau lỗi mạng.
