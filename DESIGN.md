# HomeMatch AI Agent — hướng thiết kế giao diện

**Cập nhật:** 05/10/2026. Giao diện phục vụ ba vai trò, **khách**, **chủ nhà** và **quản trị viên**, theo [đặc tả sản phẩm](docs/dac-ta-san-pham.md). Danh sách màn và trạng thái chi tiết ở [UI_SPEC](frontend/UI_SPEC.md).

## 1. Nguyên tắc

1. **Hội thoại dẫn tới xác nhận.** Chat giúp khách diễn đạt nhu cầu, nhưng mọi thứ có hệ quả (ngân sách, tiền mặt, thu nhập, kịch bản vay) được chốt trên form có nhãn rõ.
2. **Phân biệt đã suy luận và đã xác nhận.** Trường do agent hoặc memory điền có nhãn "đã suy luận"; trường do khách nhập có nhãn "đã xác nhận".
3. **Tiền luôn có ngữ cảnh.** Tiền thuê, tổng tháng, tiền vào ở, khoản vay, tỷ lệ trên thu nhập là các con số riêng. Mỗi số kèm kỳ, kịch bản và phần còn thiếu. Khoản chưa biết hiển thị "chưa rõ", không hiển thị 0.
4. **Trạng thái thật.** "Đang tìm" khác "không có căn phù hợp" và khác "dữ liệu ước tính". Không tạo gợi ý giả bằng timer.
5. **Minh bạch.** Mỗi căn có lý do, đánh đổi, cờ dữ liệu chưa xác minh.
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
| Tìm kiếm | Thanh bộ lọc trên cùng; danh sách hoặc bản đồ bên trái, khung xem nhanh bên phải; khay so sánh dưới cùng |
| Tin nhắn | Danh sách cuộc trò chuyện bên trái (đếm chưa đọc), luồng tin bên phải, ngữ cảnh chuyển giao thu gọn ở đầu |
| Cổng chủ nhà | Thanh điều hướng `/chu-nha/*`; dashboard dạng thẻ số + lịch 7 ngày; bảng hợp đồng, hóa đơn, sự cố có bộ lọc trạng thái |
| Admin Console | 5 tab: hội thoại, chuyển giao, tài khoản, tin đăng, vận hành |

## 3. Token và nhận diện

**Cập nhật 15/11/2026.** Bảng màu đỏ burgundy + vàng đồng (`frontend/src/styles.css`):

| Token | Giá trị | Dùng cho |
|---|---|---|
| `--ink` | `#241a1e` | chữ chính |
| `--muted` | `#65585d` | chữ phụ |
| `--border` | `#ebe5e7` | viền |
| `--accent` | `#a5142f` | nút chính, liên kết, trạng thái đang chọn (chữ trắng trên nền này) |
| `--accent-hover` | `#82102a` | hover của nút chính |
| `--accent-soft` | `#fbeef1` | nền nhạt của chip, thẻ đang chọn |
| `--accent-text` | `#96122b` | chữ màu thương hiệu trên nền sáng |
| `--warm` | `#e5a93b` | điểm nhấn thứ hai: mảnh ghép phải trong logo, chi tiết minh hoạ. Không dùng làm nền cho chữ. |
| `--green` | `#157347` | băng `phu_hop` |

- **Logo:** ngôi nhà ghép từ hai mảnh ghép (Home + Match): nửa trái có núm cài vào hốc nửa phải. Mảnh trái trắng, mảnh phải vàng đồng, trên ô burgundy bo góc 11/40; khe giữa hai mảnh khoét bằng mask nên trong suốt. Thành phần `BrandMark` trong `frontend/src/components/Brand.tsx`; favicon ở `frontend/public/favicon.svg`. Chữ "Home" màu `--ink`, "Match" màu `--accent`. Trên nền đã có màu (thanh ray) dùng `tile={false}`: mảnh trái burgundy, mảnh phải vàng, không có ô nền.
- **Phông:** Be Vietnam Pro (400–800), dự phòng phông hệ thống. Input trên mobile ≥ 16px. Vùng chạm ≥ 44×44px.
- Bo góc 12px. Chuyển động 160ms, có `prefers-reduced-motion`.
- Màu ngữ nghĩa giữ nguyên và tách khỏi màu thương hiệu: hổ phách cho "cân nhắc"/"ước tính", đỏ cam cho lỗi/"vượt" (sáng hơn burgundy, luôn kèm icon và nhãn chữ), xanh lá cho "phù hợp". Băng khả năng chi trả dùng cả màu, nhãn chữ và icon, không dùng màu làm tín hiệu duy nhất.

## 4. Định dạng dữ liệu

- Tiền: `7.070.000 ₫`, làm tròn VND từ backend. Tỷ lệ: `32,1%`.
- Vị trí: khu vực và thành phố. Khoảng cách là đường thẳng có sai số, ghi "khoảng". Không hiển thị thời gian đi lại.
- Ảnh: `RoomIllustration` là minh họa, phải ghi rõ không phải ảnh căn thật. Dữ liệu tổng hợp có nhãn "dữ liệu mô phỏng".
