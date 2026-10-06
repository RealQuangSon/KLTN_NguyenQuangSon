# API đích HomeMatch AI Agent

**Cập nhật:** 05/10/2026 (sau E6). Tài liệu này chỉ liệt kê các phần **chưa triển khai** so với API đang chạy ([api-contract.md](api-contract.md), [openapi.json](openapi.json)).

Các phần đã làm và đã chuyển sang `api-contract.md`:

- tài chính, căn hộ, lý do đổi thứ tự;
- mô phỏng, `GET /locations`;
- memory (`/me/memory`);
- provenance agent, `semantic_usage`;
- toàn bộ 5 phân hệ E1–E6 (tìm kiếm công khai, live chat, thông báo, PMS & CRM, trợ lý chủ nhà, admin).

Giữ nguyên quy ước: envelope lỗi `{error:{code,message,fields?},request_id}`, người gọi lấy từ token, CAS bằng revision, idempotency key cho các thao tác ghi quan trọng.

## 1. Chi phí vận hành theo VND

`GET /admin/metrics` bổ sung `estimated_cost_vnd`, tính từ `reported_tokens`, `query_embedding_calls` và bảng giá provider có ghi ngày áp dụng. Chưa cấu hình bảng giá thì trả `null`, không ước đoán.

## 2. Hỏi tài chính bằng chat

Thêm ý định `simulate_finance`. Ví dụ: khách hỏi "nếu vay 12 tháng thì sao" sau khi đã có danh sách duyệt. Supervisor chuyển câu hỏi cho agent tài chính, agent gọi tool `simulate_scenarios` cho căn được nhắc tới. Câu trả lời chỉ dùng số do tool trả về. Hiện tại khách mô phỏng qua giao diện (`POST /sessions/{id}/simulate`).

## 3. Ảnh tin và ảnh sự cố

- `POST /landlord/rooms/{id}/media` và `POST /maintenance/{id}/media`: upload có kiểm loại, kích thước, hash; lưu vào kho file (Railway volume hoặc object storage).
- Ảnh công khai chỉ dành cho tin đã công khai. Ảnh sự cố chỉ hai bên của hợp đồng xem được.

## 4. Ưu đãi trong chăm sóc khách

- `PATCH /landlord/rooms/{id}/promotion {text, valid_until}`.
- Job chăm sóc khách kèm ưu đãi còn hạn của căn tương đương. Ưu đãi không đổi giá thuê đã duyệt.
