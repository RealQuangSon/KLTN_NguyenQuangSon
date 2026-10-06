# Trạng thái và lỗi backend HomeMatch 0.4.0

Bảng này mô tả hành vi đang chạy. Người duyệt là **chủ nhà** (`owner`) của từng phòng, "người thuê/renter" là **khách**. Mã lỗi đích (`invalid_loan`, `override_reason_required`, `tool_not_allowed`) nằm ở [API đích](api-san-pham-v1.md).

## Bản gợi ý

| Status | Ý nghĩa | Hành động tiếp theo | Phòng hiển thị với người thuê |
|---|---|---|---|
| `awaiting_confirmation` | Chưa có run | Người thuê xác nhận hồ sơ | Rỗng |
| `generating` | Đã lưu run, chưa tạo xong nháp | Quản lý có thể retry nếu process đã gián đoạn | Rỗng |
| `generation_failed` | Generation/checkpoint lỗi | Manager retry tạo run mới, cần duyệt mới | Rỗng |
| `pending_review` | Nháp đang chờ các chủ nhà có phòng trong danh sách | Từng chủ nhà duyệt phần phòng của mình | Rỗng |
| `partially_published` | Đã có chủ nhà duyệt, còn chủ nhà khác chưa quyết định | Các chủ nhà còn lại duyệt | Phòng đã được duyệt (đúng thứ tự trong phần của từng chủ) |
| `reviewed` | Mọi chủ nhà đã quyết định, chưa hoàn tất graph | Retry hoặc replay đúng payload/key | Phòng đã duyệt (nếu có) |
| `published` | Manager approve và finalize thành công | Xem kết quả, compare/viewing | Subset đã duyệt theo đúng thứ tự |
| `rejected` | Manager từ chối | Điều chỉnh/xác nhận hồ sơ để tạo run mới | Rỗng |
| `needs_revision` | Manager yêu cầu sửa | Người thuê sửa và xác nhận lại | Rỗng |
| `no_match` | Không có phòng đủ điều kiện | Điều chỉnh nhu cầu hoặc kho | Rỗng |
| `needs_verification` | Không có phòng đủ bằng chứng cho điều kiện bắt buộc | Xác minh kho hoặc điều chỉnh nhu cầu | Rỗng |
| `invalidated` | Hồ sơ/run hiện tại hoặc catalog đã thay đổi | Tạo và duyệt bản mới | Rỗng |

Profile/catalog/active run được kiểm lại khi đọc và trước finalize. Các trạng thái khác `published` không trả candidate, diagnostics hay quyết định nội bộ qua results của người thuê. Quản lý chỉ đọc/duyệt phiên được phân công.

Chat có `needs_clarification`, `cost_estimate`, `support_requested`; đây là trạng thái phản hồi chat, tách khỏi trạng thái run. Viewing bắt đầu `requested`, sau phản hồi manager thành `confirmed` hoặc `declined`.

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
