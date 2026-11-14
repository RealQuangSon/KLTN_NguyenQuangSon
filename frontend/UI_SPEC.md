# Đặc tả giao diện HomeMatch AI Agent

**Cập nhật:** 30/10/2026 (trang đăng nhập: chọn loại tài khoản, ô gạch chân, nút pill, cảnh phố CSS — icon/hình dùng bộ HomeMatch; FE-01–FE-07 từ 08/10: đăng ký chủ nhà, duyệt hồ sơ, ticket hỗ trợ, chi phí AI VND, ảnh tin & ảnh sự cố, ưu đãi, thẻ mô phỏng vay trong chat). Màn hình cho khách, chủ nhà và quản trị viên theo [đặc tả](../docs/dac-ta-san-pham.md) và [DESIGN.md](../DESIGN.md). Bản 04/10 được lưu ở [luu-tru](../docs/luu-tru/2026-10-04-vong-doi-thue/frontend/UI_SPEC.md).

## 1. Route

| Route | Vai trò | Màn | Test |
|---|---|---|---|
| `/` | Mọi người | Trang chủ, ô nhập nhu cầu, câu mẫu | |
| `/dang-nhap` | Mọi người | Đăng nhập bố cục mới: chọn loại tài khoản (Người thuê/Chủ nhà — chỉ đổi dòng mô tả, quyền do tài khoản thật quyết), ô gạch chân, nút pill tối, "Quên mật khẩu?" gọi API đặt lại (email là stub), link Đăng ký; cột phải là cảnh phố CSS kèm tagline | `routing`, `auth-and-keys`, `landing-flow` |
| `/dang-ky` | Mọi người | Đăng ký người thuê hoặc chủ nhà (`account_type`, ghi chú chờ duyệt) — bố cục cũ, chép kiểu đăng nhập sau | `routing`, `landlord-signup` |
| `/tin/:id` | Mọi người | Trang tin công khai (từ bài đăng chia sẻ); gallery ảnh, nhãn ưu đãi | `copilot.test.tsx`, `promotion`, `media-photos` |
| `/tro-ly-ai` | Khách | Tư vấn: chat, hồ sơ, form tài chính, kết quả, so sánh, mô phỏng, chat với chủ nhà, lịch xem | `affordability-review`, `simulation-memory`, `chat-simulation` |
| `/tim-kiem` | Khách | Bộ lọc, danh sách/bản đồ, xem nhanh, so sánh có tư vấn, đặt lịch | `search-portal.test.tsx`, `media-photos`, `promotion` |
| `/tin-nhan` | Khách, chủ nhà | Hộp thư 1-1 | `inbox-admin.test.tsx` |
| `/cam-nang` | Mọi người | Cẩm nang, hỏi đáp | `search-portal.test.tsx` |
| `/nguoi-thue/lich-xem`, `/hop-dong`, `/hoa-don`, `/sua-chua` | Khách | Lịch xem; chấp thuận hợp đồng; hóa đơn, báo chuyển; báo hỏng | `pms.test.tsx` |
| `/chu-nha/tong-quan` | Chủ nhà | Dashboard và báo cáo | `pms.test.tsx` |
| `/chu-nha/duyet-goi-y` | Chủ nhà | Duyệt phòng của mình (↑/↓, lý do đổi thứ tự, chỉ hiện băng) | `landlord-state.test.tsx` |
| `/chu-nha/phong`, `/lich-xem`, `/hop-thu`, `/khach-tiem-nang` | Chủ nhà | Tin (tạo/sửa/trạng thái); lịch xem; hộp thư; CRM | `landlord-state`, `pms` |
| `/chu-nha/hop-dong`, `/hoa-don`, `/sua-chua` | Chủ nhà | Hợp đồng; chỉ số, hóa đơn, thu tiền, đối soát; sự cố | `pms.test.tsx` |
| `/chu-nha/tro-ly` | Chủ nhà | Bài đăng theo kênh, chia sẻ, đề xuất giá, cố vấn văn bản/giọng nói | `copilot.test.tsx` |
| `/quan-tri/hoi-thoai`, `/chuyen-giao`, `/ho-tro`, `/tai-khoan`, `/tin-dang`, `/van-hanh` | Admin | Admin Console: ticket hỗ trợ, duyệt hồ sơ chủ nhà, chi phí AI VND ở Vận hành | `inbox-admin`, `support-tickets`, `landlord-signup` |
| `/tai-khoan/ho-so` | Mọi vai trò | Đồng ý ghi nhớ, memory, phiên đăng nhập | `simulation-memory` |

Chuông thông báo hiện trên mọi màn khi đã đăng nhập (đọc lại 30 giây).

Không đưa nội dung chat, ngân sách, thu nhập hay token vào URL. Phiên mở từ màn ticket sang Hội thoại AI cũng đi qua `sessionStorage`, không qua URL.

Chủ nhà có `landlord_status: "pending"` (từ `/auth/me`) thấy banner chờ duyệt trên mọi trang `/chu-nha/*`; ô "Công khai" trong biên tập tin bị khóa kèm chú thích. Nếu máy chủ vẫn trả 403 `landlord_not_approved`, UI hiển thị đúng `message` trả về (`landlord-signup.test.tsx`).

## 2. Màn tư vấn của khách

1. **Chat:** Enter để gửi, Shift+Enter xuống dòng, không gửi khi đang gõ IME. Hiển thị trạng thái đang gửi. Câu hỏi của agent (tối đa 2) hiện dưới tin nhắn.
2. **Hồ sơ nhu cầu:** thành phố (TP.HCM/Hà Nội), khu vực (gợi ý theo thành phố từ `frontend/src/locations.ts`, có test giữ đồng bộ với backend; nhập tự do vẫn được), loại hình (phòng/studio/căn hộ), số phòng ngủ, số người/xe, tiện ích bắt buộc, sở thích, điểm đến và bán kính. Mỗi trường có nhãn "đã suy luận" hoặc "đã xác nhận".
3. **Form tài chính:** trần tổng tháng (bắt buộc), trần tiền thuê, tiền mặt sẵn có, thu nhập tháng (tùy chọn, có ghi chú "chỉ dùng tính tỷ lệ, chủ nhà không thấy số này"), kịch bản vay (bật/tắt, lãi suất năm, số tháng, gốc tối đa), kịch bản điện/nước/chuyển nhà/sắm sửa.
4. **Trạng thái run:** chờ xác nhận, đang tạo, chờ chủ nhà duyệt, đã duyệt một phần (thấy phòng đã duyệt), đã công bố, không có căn phù hợp (kèm gợi ý nới lỏng), cần xác minh, hết hiệu lực. Không hiển thị thẻ căn chưa được chủ nhà duyệt.
5. **Kết quả:** tối đa 5 thẻ theo thứ tự trợ lý, chỉ gồm phòng đã được chủ nhà duyệt. Mỗi thẻ có chi phí, băng khả năng chi trả, khoản vay (nếu có), lý do, đánh đổi, cờ xác minh.
6. **So sánh:** chọn 2–3 căn từ cùng run. Bảng các hàng tiền thuê, tổng tháng, tiền vào ở, trả góp, tỷ lệ, diện tích, loại hình, tiện ích, phần chưa rõ. Giá trị `null` hiển thị "Chưa rõ" và không được xếp như số 0.
7. **Mô phỏng:** 1 căn, tối đa 3 kịch bản cạnh nhau. Có ghi chú "không thay đổi hồ sơ đã xác nhận". Hỏi vay trong chat (`status: "simulation"`) hiện thẻ nhỏ trong luồng chat: tên căn, kịch bản (lãi/năm, số tháng, gốc vay), bảng kết quả tái dùng đúng component mô phỏng và băng đánh giá; `status: "needs_results"` hiện `message` kèm nút "Xem danh sách gợi ý" cuộn tới bảng kết quả (`chat-simulation.test.tsx`). Giá trị `null` hiện "Chưa rõ".
8. **Lịch xem:** chọn thời điểm tương lai. Hộp thoại giữ focus, Escape để đóng.
9. **Ảnh và ưu đãi:** thẻ phòng có ảnh bìa (ảnh đầu) hoặc hình minh họa khi chưa có ảnh; xem nhanh và tin công khai có gallery, đổi ảnh bằng nút ‹ › hoặc phím ←/→ khi đang focus. Nhãn "Ưu đãi" chỉ hiện khi máy chủ trả `promotion` khác `null`, kèm dòng phụ "đến dd/mm"; nhãn không đổi giá hiển thị và không ngụ ý thứ tự xếp hạng (`media-photos.test.tsx`, `promotion.test.tsx`).

## 3. Màn duyệt của chủ nhà

- Chỉ hiện phòng của chủ nhà đang đăng nhập và tiến độ duyệt của các chủ khác.
- Hồ sơ đã xác nhận: không hiện thu nhập hay tỷ lệ, chỉ hiện băng.
- Danh sách nháp theo thứ tự của agent, kèm điểm thành phần (chi phí, sở thích, vị trí, semantic), chi phí, cờ xác minh. Diagnostics lọc hiện dạng số căn bị loại theo lý do.
- Chọn tập con, đổi thứ tự bằng nút lên/xuống (không phụ thuộc kéo thả). Khi tập hoặc thứ tự khác của agent thì ô lý do là bắt buộc.
- Quyết định: duyệt, từ chối, yêu cầu sửa. Có xử lý xung đột phiên bản: tải lại và hiện thông báo.
- Ảnh tin (chỉ khi tin đã có `id`): chọn nhiều file JPEG/PNG/WebP ≤ 5 MB (kiểm sớm ở client để báo nhanh, máy chủ vẫn chốt), tải lần lượt có tiến độ; mỗi ảnh có nút ↑/↓ (`PATCH .../media/order`) và Xóa; lỗi `invalid_media`/`media_too_large`/`media_limit` hiện đúng `message` máy chủ (`media-photos.test.tsx`).
- Ưu đãi: nội dung ≤ 200 ký tự có bộ đếm, hạn chọn từ hôm nay tới +90 ngày; Lưu gọi PUT, Gỡ gọi DELETE; ưu đãi không đổi các ô giá trong biên tập (`promotion.test.tsx`).
- Báo hỏng: chọn tối đa 5 ảnh, chỉ tải lên sau khi ticket được tạo; xem ảnh sự cố qua object URL tạo bằng fetch có bearer token, hủy toàn bộ URL khi rời trang.

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
