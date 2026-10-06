# HomeMatch AI Agent — hướng thiết kế giao diện

**Cập nhật:** 05/10/2026. Giao diện phục vụ ba vai trò, **khách**, **chủ nhà** và **quản trị viên**, theo [đặc tả sản phẩm](docs/dac-ta-san-pham.md). Danh sách màn và trạng thái chi tiết ở [UI_SPEC](frontend/UI_SPEC.md).

## 1. Nguyên tắc

1. **Hội thoại dẫn tới xác nhận.** Chat giúp khách diễn đạt nhu cầu, nhưng mọi thứ có hệ quả (ngân sách, tiền mặt, thu nhập, kịch bản vay) được chốt trên form có nhãn rõ.
2. **Phân biệt đã suy luận và đã xác nhận.** Trường do agent hoặc memory điền có nhãn "đã suy luận"; trường do khách nhập có nhãn "đã xác nhận".
3. **Tiền luôn có ngữ cảnh.** Tiền thuê, tổng tháng, tiền vào ở, khoản vay, tỷ lệ trên thu nhập là các con số riêng. Mỗi số kèm kỳ, kịch bản và phần còn thiếu. Khoản chưa biết hiển thị "chưa rõ", không hiển thị 0.
4. **Trạng thái thật.** "Đang chờ chủ nhà duyệt" khác "không có căn phù hợp" và khác "cần xác minh dữ liệu". Không tạo gợi ý giả bằng timer.
5. **Minh bạch.** Mỗi căn có lý do, đánh đổi, cờ dữ liệu chưa xác minh. Chủ nhà thấy điểm thành phần và thứ tự gốc của agent cho phòng của mình.
6. **Riêng tư.** Màn chủ nhà không hiển thị thu nhập hay tỷ lệ, chỉ hiển thị băng. Admin xem chat AI đã che PII.
7. **Dùng được trên điện thoại và bằng bàn phím.**

## 2. Bố cục

| Màn | Bố cục |
|---|---|
| Trang chủ | Tiêu đề, ô nhập nhu cầu khoảng 720px, câu mẫu cho cả TP.HCM và Hà Nội |
| Tư vấn (khách) | Desktop: chat bên trái, panel kết quả bên phải. Mobile: tab chat/kết quả. Drawer hồ sơ nhu cầu và form tài chính. |
| Kết quả | Thẻ căn: tiêu đề, khu vực/thành phố, diện tích, tổng tháng, tiền vào ở, băng khả năng chi trả, lý do, đánh đổi, cờ xác minh |
| So sánh | Bảng 2–3 cột cạnh nhau, cuộn ngang trong container. Đánh dấu giá trị tốt nhất và phần chênh lệch. Biểu đồ cột chi phí và tư vấn ưu/nhược điểm. |
| Mô phỏng | Tối đa 3 kịch bản cạnh nhau cho một căn: tổng tháng, tiền vào ở, trả góp, tỷ lệ |
| Hàng đợi chủ nhà | Danh sách chờ duyệt có phòng của mình, tiến độ các chủ nhà khác |
| Tìm kiếm | Thanh bộ lọc trên cùng; danh sách hoặc bản đồ bên trái, khung xem nhanh bên phải; khay so sánh dưới cùng |
| Tin nhắn | Danh sách cuộc trò chuyện bên trái (đếm chưa đọc), luồng tin bên phải, ngữ cảnh chuyển giao thu gọn ở đầu |
| Cổng chủ nhà | Thanh điều hướng `/chu-nha/*`; dashboard dạng thẻ số + lịch 7 ngày; bảng hợp đồng, hóa đơn, sự cố, khách tiềm năng có bộ lọc trạng thái |
| Admin Console | 5 tab: hội thoại, chuyển giao, tài khoản, tin đăng, vận hành |
| Chi tiết duyệt | Hồ sơ đã xác nhận ở bên trái. Danh sách nháp có checkbox, kéo hoặc nút để đổi thứ tự, ô lý do. Diagnostics lọc thu gọn. |

## 3. Token

Source hiện dùng bảng màu ấm theo lựa chọn của người dùng (`frontend/src/styles.css`):

| Token | Giá trị |
|---|---|
| `--ink` | `#35312e` |
| `--muted` | `#7d746d` |
| `--border` | `#e9e2dc` |
| `--accent` | `#c6543c` |
| `--accent-hover` | `#ab4530` |
| `--accent-soft` | `#fcf0e9` |
| `--green` | `#32765a` (băng `phu_hop`) |

- Bo góc 18px. Chuyển động 160ms, có `prefers-reduced-motion`.
- Băng khả năng chi trả dùng cả màu, nhãn chữ và icon. Không dùng màu làm tín hiệu duy nhất.
- Phông hệ thống hỗ trợ tiếng Việt. Input trên mobile ≥ 16px. Vùng chạm ≥ 44×44px.

Hướng token cam sáng kiểu HubHome trong bản 04/10 không còn là mục tiêu. Xem bản lưu ở [luu-tru](docs/luu-tru/2026-10-04-vong-doi-thue/DESIGN.md).

## 4. Định dạng dữ liệu

- Tiền: `7.070.000 ₫`, làm tròn VND từ backend. Tỷ lệ: `32,1%`.
- Vị trí: khu vực và thành phố. Khoảng cách là đường thẳng có sai số, ghi "khoảng". Không hiển thị thời gian đi lại.
- Ảnh: `RoomIllustration` là minh họa, phải ghi rõ không phải ảnh căn thật. Dữ liệu tổng hợp có nhãn "dữ liệu mô phỏng".
