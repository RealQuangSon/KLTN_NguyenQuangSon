# Đặc tả giao diện HomeMatch AI Agent

**Cập nhật:** 05/10/2026 (sau E1–E6). Màn hình cho khách, chủ nhà và quản trị viên theo [đặc tả](../docs/dac-ta-san-pham.md) và [DESIGN.md](../DESIGN.md). Bản 04/10 được lưu ở [luu-tru](../docs/luu-tru/2026-10-04-vong-doi-thue/frontend/UI_SPEC.md).

## 1. Route

| Route | Vai trò | Màn | Test |
|---|---|---|---|
| `/` | Mọi người | Trang chủ, ô nhập nhu cầu, câu mẫu | |
| `/dang-nhap`, `/dang-ky` | Mọi người | Đăng nhập, đăng ký | |
| `/tin/:id` | Mọi người | Trang tin công khai (từ bài đăng chia sẻ) | `copilot.test.tsx` |
| `/tro-ly-ai` | Khách | Tư vấn: chat, hồ sơ, form tài chính, kết quả, so sánh, mô phỏng, chat với chủ nhà, lịch xem | `affordability-review`, `simulation-memory` |
| `/tim-kiem` | Khách | Bộ lọc, danh sách/bản đồ, xem nhanh, so sánh có tư vấn, đặt lịch | `search-portal.test.tsx` |
| `/tin-nhan` | Khách, chủ nhà | Hộp thư 1-1 | `inbox-admin.test.tsx` |
| `/cam-nang` | Mọi người | Cẩm nang, hỏi đáp | `search-portal.test.tsx` |
| `/nguoi-thue/lich-xem`, `/hop-dong`, `/hoa-don`, `/sua-chua` | Khách | Lịch xem; chấp thuận hợp đồng; hóa đơn, báo chuyển; báo hỏng | `pms.test.tsx` |
| `/chu-nha/tong-quan` | Chủ nhà | Dashboard và báo cáo | `pms.test.tsx` |
| `/chu-nha/duyet-goi-y` | Chủ nhà | Duyệt phòng của mình (↑/↓, lý do đổi thứ tự, chỉ hiện băng) | `landlord-state.test.tsx` |
| `/chu-nha/phong`, `/lich-xem`, `/hop-thu`, `/khach-tiem-nang` | Chủ nhà | Tin (tạo/sửa/trạng thái); lịch xem; hộp thư; CRM | `landlord-state`, `pms` |
| `/chu-nha/hop-dong`, `/hoa-don`, `/sua-chua` | Chủ nhà | Hợp đồng; chỉ số, hóa đơn, thu tiền, đối soát; sự cố | `pms.test.tsx` |
| `/chu-nha/tro-ly` | Chủ nhà | Bài đăng theo kênh, chia sẻ, đề xuất giá, cố vấn văn bản/giọng nói | `copilot.test.tsx` |
| `/quan-tri/hoi-thoai`, `/chuyen-giao`, `/tai-khoan`, `/tin-dang`, `/van-hanh` | Admin | Admin Console | `inbox-admin.test.tsx` |
| `/tai-khoan/ho-so` | Mọi vai trò | Đồng ý ghi nhớ, memory, phiên đăng nhập | `simulation-memory` |

Chuông thông báo hiện trên mọi màn khi đã đăng nhập (đọc lại 30 giây).

Không đưa nội dung chat, ngân sách, thu nhập hay token vào URL.

## 2. Màn tư vấn của khách

1. **Chat:** Enter để gửi, Shift+Enter xuống dòng, không gửi khi đang gõ IME. Hiển thị trạng thái đang gửi. Câu hỏi của agent (tối đa 2) hiện dưới tin nhắn.
2. **Hồ sơ nhu cầu:** thành phố (TP.HCM/Hà Nội), khu vực (gợi ý theo thành phố từ `frontend/src/locations.ts`, có test giữ đồng bộ với backend; nhập tự do vẫn được), loại hình (phòng/studio/căn hộ), số phòng ngủ, số người/xe, tiện ích bắt buộc, sở thích, điểm đến và bán kính. Mỗi trường có nhãn "đã suy luận" hoặc "đã xác nhận".
3. **Form tài chính:** trần tổng tháng (bắt buộc), trần tiền thuê, tiền mặt sẵn có, thu nhập tháng (tùy chọn, có ghi chú "chỉ dùng tính tỷ lệ, chủ nhà không thấy số này"), kịch bản vay (bật/tắt, lãi suất năm, số tháng, gốc tối đa), kịch bản điện/nước/chuyển nhà/sắm sửa.
4. **Trạng thái run:** chờ xác nhận, đang tạo, chờ chủ nhà duyệt, đã duyệt một phần (thấy phòng đã duyệt), đã công bố, không có căn phù hợp (kèm gợi ý nới lỏng), cần xác minh, hết hiệu lực. Không hiển thị thẻ căn chưa được chủ nhà duyệt.
5. **Kết quả:** tối đa 5 thẻ theo thứ tự trợ lý, chỉ gồm phòng đã được chủ nhà duyệt. Mỗi thẻ có chi phí, băng khả năng chi trả, khoản vay (nếu có), lý do, đánh đổi, cờ xác minh.
6. **So sánh:** chọn 2–3 căn từ cùng run. Bảng các hàng tiền thuê, tổng tháng, tiền vào ở, trả góp, tỷ lệ, diện tích, loại hình, tiện ích, phần chưa rõ. Giá trị `null` hiển thị "Chưa rõ" và không được xếp như số 0.
7. **Mô phỏng:** 1 căn, tối đa 3 kịch bản cạnh nhau. Có ghi chú "không thay đổi hồ sơ đã xác nhận".
8. **Lịch xem:** chọn thời điểm tương lai. Hộp thoại giữ focus, Escape để đóng.

## 3. Màn duyệt của chủ nhà

- Chỉ hiện phòng của chủ nhà đang đăng nhập và tiến độ duyệt của các chủ khác.
- Hồ sơ đã xác nhận: không hiện thu nhập hay tỷ lệ, chỉ hiện băng.
- Danh sách nháp theo thứ tự của agent, kèm điểm thành phần (chi phí, sở thích, vị trí, semantic), chi phí, cờ xác minh. Diagnostics lọc hiện dạng số căn bị loại theo lý do.
- Chọn tập con, đổi thứ tự bằng nút lên/xuống (không phụ thuộc kéo thả). Khi tập hoặc thứ tự khác của agent thì ô lý do là bắt buộc.
- Quyết định: duyệt, từ chối, yêu cầu sửa. Có xử lý xung đột phiên bản: tải lại và hiện thông báo.

## 4. Trạng thái và lỗi

| Tình huống | UI |
|---|---|
| 401 | Về trang đăng nhập, giữ nhu cầu đang nhập trong bộ nhớ |
| 409 phiên bản | "Dữ liệu đã thay đổi", tải lại phiên hoặc kho rồi cho thao tác lại |
| 429 `budget_exceeded` | Ẩn chat, hướng dẫn dùng form |
| 503 `ai_unavailable` | Thông báo trợ lý tạm không khả dụng, form vẫn dùng được |
| Mất mạng khi duyệt hoặc đặt lịch | Giữ nguyên payload và khóa idempotency để gửi lại |

## 5. Tiêu chí kiểm tra

- Vitest cho các luồng: khách chờ duyệt không thấy căn; thu nhập không xuất hiện ở màn chủ nhà; chủ nhà chỉ thấy phòng mình; hóa đơn, hợp đồng, tin nhắn, tư vấn; so sánh tối đa 3; `null` hiển thị "Chưa rõ"; lỗi 409/429/503.
- Chạy ở các viewport 360, 768, 1280px. Thao tác chính dùng được bằng bàn phím.
- Ảnh chụp hoặc ghi màn hình demo đầu-cuối cho báo cáo.
