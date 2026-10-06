# Bản xem trước kế hoạch FE

Đây là hiện vật minh họa lịch sử 02/10/2026. [UI_SPEC v1](../UI_SPEC.md) cập nhật 04/10 đã mở sang toàn vòng đời thuê; preview chưa chứa đủ các màn owner/admin/hợp đồng/hóa đơn/sửa chữa của bản mới.

[hubhome-preview.html](hubhome-preview.html) minh họa hướng trong [UI_SPEC](../UI_SPEC.md): trang chủ/composer giữa, trợ lý chat–preview và khu vực người thuê. Mở file HTML bằng trình duyệt; không cần build, tài khoản hoặc kết nối API. Đây là bản bố cục rút gọn, chưa triển khai toàn bộ màn/component của kế hoạch.

Thanh trên cùng dùng để đổi màn và trạng thái minh họa. Có thể mở Tìm nhanh, chọn câu mẫu, đổi lưới/danh sách, chọn 2–3 phòng mẫu để xem bảng so sánh và mở chi tiết. Phòng, số tiền, hồ sơ, bộ đếm và trạng thái đều là dữ liệu tổng hợp trong preview độc lập; không đưa vào runtime app.

## Kiểm tra ngày 02/10/2026

- Đã kiểm tra cú pháp JavaScript.
- Đã xem landing và assistant ở 1280×720; chat/preview hiện đồng thời; pending không render card; mẫu published có 3 card, compare 2 phòng mở/đóng được và giữ khoản chưa biết.
- Đã xem tab kết quả và tổng quan người thuê ở 390×844; chiều rộng trang 390px, không cuộn ngang trang.
- Đã đọc chiều rộng tổng quan ở 320px: chiều rộng trang 320px. Kiểm tra các màn còn lại ở 320px bị ngắt bởi công cụ, chưa xác nhận đầy đủ.

Preview dùng font fallback hệ thống và minh họa SVG tự tạo. Không có map, không kiểm chứng API/auth/HITL/tính tiền; không đánh dấu UI-V hay task FE hoàn tất từ preview. Ảnh và kiểm thử source runtime sau refactor thuộc FE-09/10.
