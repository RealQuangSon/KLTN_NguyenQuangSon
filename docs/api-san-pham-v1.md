# API đích HomeMatch AI Agent

**Cập nhật:** 08/10/2026 (sau đợt BE/AG 08/10). Tài liệu này chỉ liệt kê các phần **chưa triển khai** so với API đang chạy ([api-contract.md](api-contract.md), [openapi.json](openapi.json)).

Các phần đã làm và đã chuyển sang `api-contract.md`:

- tài chính, căn hộ, lý do đổi thứ tự;
- mô phỏng, `GET /locations`;
- hỏi tài chính bằng chat: ý định `simulate_finance` trên `POST /sessions/{id}/messages` (AG-02, 08/10/2026);
- memory (`/me/memory`);
- provenance agent, `semantic_usage`;
- toàn bộ 5 phân hệ E1–E6 (tìm kiếm công khai, live chat, thông báo, PMS & CRM, trợ lý chủ nhà, admin);
- ảnh tin và ảnh sự cố (BE-06, 08/10/2026);
- ưu đãi của chủ nhà (BE-07, 08/10/2026);
- chi phí vận hành quy VND trên `/admin/metrics` (BE-05, 08/10/2026).

Giữ nguyên quy ước: envelope lỗi `{error:{code,message,fields?},request_id}`, người gọi lấy từ token, CAS bằng revision, idempotency key cho các thao tác ghi quan trọng.
