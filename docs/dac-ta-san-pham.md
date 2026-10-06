# Đặc tả sản phẩm HomeMatch AI Agent

**Cập nhật:** 05/10/2026. Cụ thể hóa [đề cương](ke-hoach-kltn-homematch.md). Yêu cầu có mã ở [yeu-cau-san-pham.md](yeu-cau-san-pham.md).

## 1. Tổng quan

HomeMatch là nền tảng cho thuê phòng trọ, studio, căn hộ tại TP.HCM và Hà Nội, có trợ lý AI ở trung tâm:

- **Người thuê** tìm phòng bằng chat AI hoặc bộ lọc. Họ thấy chi phí thật và khả năng chi trả (cả khoản vay ngắn hạn khi thiếu tiền vào ở), so sánh có tư vấn, chat với chủ nhà, đặt lịch xem trực tiếp hoặc trực tuyến. Sau khi thuê, họ ký hợp đồng, nhận hóa đơn, báo chuyển tiền và báo hỏng trên cùng tài khoản.
- **Chủ nhà** duyệt các phòng của mình mà AI gợi ý cho khách. Họ quản lý tin, hợp đồng, công tơ, hóa đơn, công nợ, sửa chữa, khách tiềm năng và hộp thư. Họ dùng trợ lý AI để viết bài đăng và hỏi về giá thuê hay lý do phòng trống.
- **Quản trị viên** giám sát hội thoại AI (đã che PII), luồng chuyển giao sang chủ nhà, người dùng, tin đăng và vận hành.

## 2. Vai trò

| Vai trò | Code | Tài khoản mẫu |
|---|---|---|
| Người thuê | `renter` | `renter-a`, `renter-b` |
| Chủ nhà | `owner` | `owner-a`, `owner-b` (TP.HCM), `owner-c`, `owner-d` (Hà Nội) |
| Quản trị viên | `admin` | `admin-a` |
| Nhân viên (cũ) | `manager` | `manager-a`, `manager-b`: giữ để tương thích, không còn quyền nghiệp vụ |

## 3. Phân hệ và màn hình

| Phân hệ | Màn (route) |
|---|---|
| Trợ lý AI | Tư vấn `/tro-ly-ai`: chat, hồ sơ, form tài chính, kết quả, so sánh, mô phỏng, chat với chủ nhà |
| Cổng người thuê | `/tim-kiem` (bộ lọc, danh sách/bản đồ, xem nhanh, so sánh và tư vấn, đặt lịch); `/tin-nhan`; `/cam-nang`; `/nguoi-thue/lich-xem`; `/nguoi-thue/hop-dong`; `/nguoi-thue/hoa-don`; `/nguoi-thue/sua-chua`; trang tin công khai `/tin/:id` |
| Cổng chủ nhà | `/chu-nha/tong-quan` (dashboard, báo cáo); `/chu-nha/duyet-goi-y`; `/chu-nha/phong`; `/chu-nha/lich-xem`; `/chu-nha/hop-thu`; `/chu-nha/khach-tiem-nang`; `/chu-nha/hop-dong`; `/chu-nha/hoa-don`; `/chu-nha/sua-chua`; `/chu-nha/tro-ly` (trợ lý AI cho chủ nhà) |
| Admin Console | `/quan-tri/hoi-thoai`, `/quan-tri/chuyen-giao`, `/quan-tri/tai-khoan`, `/quan-tri/tin-dang`, `/quan-tri/van-hanh` |
| Chung | `/tai-khoan/ho-so` (đồng ý ghi nhớ, memory, phiên đăng nhập); chuông thông báo trên mọi màn |

## 4. Tích hợp và phương án thay thế (D-07, D-08)

| Nhu cầu | Cách làm trong hệ thống | Không làm |
|---|---|---|
| Bản đồ | Leaflet + OpenStreetMap; ghim gần đúng kèm vòng sai số | Geocoding địa chỉ, chỉ đường |
| Xem phòng trực tuyến | Link phòng họp Jitsi tạo theo lịch | Tích hợp video riêng, ghi hình |
| Hợp đồng điện tử | Chấp thuận theo phiên bản trong ứng dụng; văn bản HTML in hoặc lưu PDF | Chữ ký số có giá trị pháp lý |
| Thanh toán | Khách báo đã chuyển, chủ nhà xác nhận đã nhận; biên lai; đối soát theo kỳ | Cổng thanh toán, đồng bộ ngân hàng |
| Thông báo | Trong ứng dụng (chuông); email là stub ghi log | Email, SMS hay push thật |
| Đăng tin đa kênh | Tạo nội dung theo kênh, link chia sẻ Facebook, trang tin công khai, sao chép | Tự đăng qua API Facebook, Zalo, diễn đàn |
| Giọng nói | Web Speech API của trình duyệt (vi-VN) | Nhận dạng phía server |
| Live chat | Đọc lại định kỳ 5 giây | WebSocket hay realtime |

## 5. Ngoài phạm vi

- Mua bán căn hộ, vay mua nhà, chấm tín dụng.
- Ảnh và media của tin (chưa có kho lưu file).
- Ưu đãi do chủ nhà tự đặt trong luồng chăm sóc khách.
- Các thành phố khác ngoài TP.HCM và Hà Nội.

## 6. Giả định

| Mã | Giả định | Nếu sai |
|---|---|---|
| A-01 | D-01/D-02 được chấp nhận. **Đã xác nhận 05/10.** | Bổ sung engine vay mua nhà |
| A-02 | Dữ liệu tổng hợp đủ để đánh giá phương pháp | Kết luận chỉ áp dụng cho dữ liệu tổng hợp |
| A-03 | Có API key OpenAI và ngân sách cho chạy live | Chỉ báo cáo kết quả offline |
| A-04 | Có 5–10 người tham gia khảo sát | RQ4 báo "chưa đo" |
| A-05 | Có tài khoản Railway | NFR-09 báo "chưa triển khai" |

Thuật ngữ ở [CONTEXT.md](../CONTEXT.md).
