# HomeMatch Frontend

**Phạm vi 05/10/2026:** giao diện cho khách, chủ nhà và quản trị viên của [HomeMatch AI Agent](../docs/ke-hoach-kltn-homematch.md). Mô tả, lệnh chạy và bằng chứng dưới đây ứng với bản 0.4.0 đang có. [UI_SPEC](UI_SPEC.md) và [PLAN](PLAN.md) là phần cần triển khai tiếp.

React + TypeScript nối FastAPI qua API thật. Đã có: trợ lý AI (chat, form, top 5 đã duyệt, so sánh có tư vấn, mô phỏng); tìm kiếm + bản đồ Leaflet; tin nhắn; cẩm nang; cổng chủ nhà (duyệt, tin, lịch, hộp thư, khách tiềm năng, hợp đồng, hóa đơn, sửa chữa, trợ lý AI); Admin Console; trang tin công khai; chuông thông báo. Graph, tài chính, quyền và xếp hạng chạy ở backend.

Giao diện dùng cam đỏ và biểu tượng mái nhà HomeMatch theo lựa chọn của người dùng; xem [hướng thiết kế](../DESIGN.md). Có bố cục desktop/điện thoại, điều hướng dưới màn hình nhỏ, tiến trình bốn bước, gợi ý bắt đầu trò chuyện, gửi bằng Enter (Shift + Enter xuống dòng), tìm kiếm/lọc kho phòng và tổng quan từ dữ liệu API. Minh họa SVG không phải ảnh phòng. Hộp đặt lịch hỗ trợ Tab/Escape và trả focus khi đóng.

**Kế hoạch 05/10/2026:** [PLAN.md](PLAN.md) và [UI_SPEC.md](UI_SPEC.md) theo đề tài và 5 phân hệ. [Preview độc lập](design/hubhome-preview.html) là hiện vật minh họa trước đây, không phải màn đã triển khai.

## Chạy local

Cài Node.js phù hợp dependency khóa trong `package-lock.json`; bản hiện tại kiểm chứng với Node 26.7.0/npm 11.19.0.

```bash
cd frontend
npm ci
npm run dev
```

Mở `http://127.0.0.1:5173`. Vite proxy `/api` tới `http://127.0.0.1:8000`; khởi động backend theo README repository với auth tài khoản seed. Giao diện login cần `/auth/login`, `/auth/me`, `/auth/logout`; demo bearer tokens trong scaffold cũ không phải login bằng mật khẩu. Dùng credentials từ quy trình seed BE, không đặt mật khẩu/secret vào bundle.

`VITE_API_BASE_URL` là cấu hình công khai duy nhất, mặc định `/api`. Nếu API ở URL khác, đặt biến này khi build và cấu hình CORS tại BE. Không đưa `OPENAI_API_KEY`, DB credentials hoặc token seed vào biến `VITE_*`.

```bash
npm test
npm run typecheck
npm run build
npm run preview
```

`npm run format` định dạng mã bằng Prettier. Production hosting cần proxy API phù hợp; Vite dev server chỉ dùng cho môi trường local. Không có cloud deployment trong phần FE này.

## Luồng kiểm chứng

1. Renter login → bắt đầu phiên → chat về thành phố/khu vực/người/ưu tiên.
2. Kiểm tra nháp, điền tổng ngân sách tháng/tiền ban đầu và scenario. Điểm đến mặc định là **tọa độ giả lập**, chỉ bật điều kiện khi chủ động xác nhận.
3. Confirm → pending, khách không có card phòng. Chủ nhà có phòng trong danh sách login → duyệt phòng của mình (lý do nếu đổi thứ tự).
4. Renter đọc lại → thấy phòng đã duyệt (`partially_published`/`published`) → so sánh 2–3 phòng → chat với chủ nhà hoặc tạo lịch xem.
5. Chủ nhà xác nhận/từ chối lịch; khách xem trạng thái. Các luồng hợp đồng, hóa đơn, sửa chữa, trợ lý chủ nhà, Admin Console xem ở [README gốc](../README.md#demo).

Review/viewing giữ đúng key/payload khi manual retry. Chat/confirm/draft/catalog không được tự gửi lại sau lỗi mạng; UI đọc lại server state trước hành động tiếp. Kết quả cũ và compare bị gỡ khi invalidated. Nhu cầu sửa chưa xác nhận không thay chi phí trên card đã duyệt.

## Lịch sử: router và shell bốn vai trò (trước E1–E6)

> Mục này ghi lại trạng thái trước đợt 5 phân hệ. Route `/quan-ly/*` và trang giữ chỗ chủ nhà/admin đã được thay bằng `/chu-nha/*` và `/quan-tri/*` có chức năng thật; xem [UI_SPEC](UI_SPEC.md).

- **Router/deep link:** bộ định tuyến history gọn trong `src/router.tsx` (không thêm dependency); điều hướng theo route thay state tab, hỗ trợ deep link, back/forward, 401 đưa về đăng nhập, 403/404 có màn riêng. Route UI theo [UI_SPEC](UI_SPEC.md) mục 3: `/`, `/dang-nhap`, `/dang-ky`, `/tro-ly-ai`, `/nguoi-thue/lich-xem`, `/quan-ly/duyet-goi-y|kho|lich-xem`, `/tai-khoan/ho-so|bao-mat`.
- **Shell bốn vai trò:** nav/guard theo `GET /auth/me`. Renter/manager giữ nguyên chức năng cũ. Owner (`/chu-nha/*`) và admin (`/quan-tri/*`) là khung mới chỉ có empty state trung thực "chức năng cần API v1" kèm endpoint chờ — không gọi API, không dữ liệu minh họa.
- **Đăng ký (FE-18 UI):** `/dang-ky` gọi `POST /api/v1/auth/register` theo contract mục tiêu. Máy chủ 0.3.0 chưa có namespace `/v1` nên màn hiển thị lỗi thật (404) thay vì thành công giả; validation chạy tại client. Hồ sơ/bảo mật `/tai-khoan/*` là stub trung thực chờ `/v1/me/profile`, `/v1/me/sessions`.
- **Hạn chế đã biết:** lịch sử chat hiển thị là state trong phiên component — rời màn trợ lý rồi quay lại (ví dụ sang `/tai-khoan/ho-so`) sẽ mất phần hiển thị hội thoại cũ (phiên/draft/profile vẫn khôi phục từ server); hạn chế có từ trước vì server history chưa được render. Màn đăng ký chưa thử với backend thật vì endpoint chưa tồn tại; chỉ kiểm thử fixture. Browser visual/QA chưa chạy lại trên router mới.

## Dữ liệu và bảo mật client

Runtime **không dùng fake API hoặc phòng hardcode để thay response**. Synthetic fixture chỉ trong `src/tests/`. Source giả lập được gắn nhãn, tiền null không chuyển thành 0, known subtotal không hiển thị thành full total.

Token chỉ ở sessionStorage; profile, tài chính và chat không lưu vào localStorage/sessionStorage. Logout/xác thực hết hạn/đổi account xóa token và session ID của app, unmount workspace riêng. UI chỉ hỗ trợ kiểm soát trình bày; backend vẫn kiểm tra quyền theo bản ghi.

## Trạng thái kiểm chứng

**Ngày 05/10/2026:** TypeScript/typecheck, build và 25 Vitest tests (6 files) đạt trên máy cục bộ; gồm 7 test router/guard/đăng ký mới trong `src/tests/routing.test.tsx` (deep link, redirect chưa đăng nhập, 403 sai vai trò, nav theo vai trò, validation đăng ký, 404 trung thực, kết quả do máy chủ trả). Chạy song song có thể chậm khi máy bận tác vụ khác; các test tích hợp đã nới trần thời gian, không đổi điều kiện khẳng định. Đợt này chưa chạy lại browser/visual QA và chưa thử đăng ký với backend thật.

TypeScript/build và 15 UI tests đã đạt trước đó trên giao diện cam đỏ. Tests dùng request fixtures để kiểm tra pending privacy, unknown cost, compare limits, stale replies, logout/account change, catalog CAS và manual mutation replay. Đã kiểm tra 7 nhóm API qua HTTP localhost và các luồng thuê/duyệt/so sánh/đặt lịch trên trình duyệt với backend offline, dữ liệu giả lập; có kiểm tra bố cục desktop/điện thoại và focus hộp thoại. Chưa kiểm chứng PG/checkpoint, GPT/embedding live hoặc cloud. Xem [TEST_CHECKLIST.md](TEST_CHECKLIST.md) cho phạm vi và bằng chứng ngày 02/10/2026.

V1 còn cần signup/reset/profile/consent, owner CRUD/media/moderation, public/map, account favorites/history, support/notification, contracts/tenancy/billing/meters/maintenance/admin. Manual payment evidence/receipt/reconciliation và contract acceptance là bắt buộc; gateway/legal e-sign/video-call riêng/AI ảnh-giọng/SSE là mở rộng theo nhu cầu. Không có module target nào được xác nhận hoàn tất từ việc viết lại docs.
