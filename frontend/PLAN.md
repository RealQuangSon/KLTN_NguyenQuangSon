# Kế hoạch Frontend

**Cập nhật:** 05/10/2026. Màn hình và trạng thái ở [UI_SPEC.md](UI_SPEC.md); hướng thiết kế ở [DESIGN.md](../DESIGN.md); task tổng ở [kế hoạch triển khai](../docs/ke-hoach-trien-khai.md).

> **Việc tiếp theo (06/10/2026):** làm theo [coding plan](../docs/coding-plan/fe.md); đọc [phần chung](../docs/coding-plan/README.md) trước.

## 1. Hiện có

React 19 + Vite, router tự viết (`router.tsx`), không dùng thư viện state. Có trang chủ, đăng nhập/đăng ký, workspace khách (`RenterWorkspace.tsx`), tìm kiếm và bản đồ (`SearchPage.tsx`, `MapView.tsx`, Leaflet), tin nhắn (`Inbox.tsx`), cẩm nang, cổng chủ nhà (`LandlordWorkspace.tsx`, `Pms.tsx`, `Copilot.tsx`), Admin Console (`AdminWorkspace.tsx`), trang tin công khai, chuông thông báo. 41 test Vitest pass ngày 05/10/2026 (sau E1–E6). ✓ = đã làm.

## 2. Việc

| Task | Việc | Test |
|---|---|---|
| T2.7 ✓ | Form tài chính: thu nhập, tiền mặt, vay. Hiển thị băng và khoản vay trên thẻ và trong so sánh. | `affordability-review.test.tsx` |
| T2.7 ✓ | Chọn thành phố, gợi ý khu vực (danh sách tĩnh, có test đồng bộ với backend); câu mẫu Hà Nội trên trang chủ và chat | `test_frontend_location_list_matches_backend_dictionary` |
| T2.1 ✓ | Loại hình căn hộ, số phòng ngủ trong form, thẻ, bảng so sánh | Vitest |
| T2.5 ✓ | Màn chủ nhà không hiển thị thu nhập hay tỷ lệ | `affordability-review.test.tsx` |
| T2.6 ✓ | Nút ↑/↓; ô lý do bắt buộc khi đổi thứ tự hoặc bỏ căn | `affordability-review.test.tsx` |
| T3.3 ✓ | Trang tài khoản: bật/tắt ghi nhớ, xem và xóa memory, thu hồi phiên đăng nhập | `simulation-memory.test.tsx` |
| T4.1 ✓ | So sánh trực quan: nhãn "Tốt nhất" (không gán cho giá trị chưa rõ), biểu đồ cột chi phí | `simulation-memory.test.tsx` |
| T4.2 ✓ | Mô phỏng 3 kịch bản (nút trên thẻ căn đã duyệt) | `simulation-memory.test.tsx` |

## 3. Quy tắc

- Frontend không tính tiền, không xếp hạng, không quyết định quyền. Mọi số lấy từ DTO.
- Chỉ lưu token và session ID trong `sessionStorage`. Không lưu chat hay tài chính trong browser storage.
- Định dạng code bằng Prettier (`npm --prefix frontend run format`).

## 3. Đợt 5 phân hệ (E1–E6, xong 05/10)

| Task | Việc | Test |
|---|---|---|
| E1 ✓ | Đổi workspace sale thành chủ nhà; trình sửa tin; trạng thái trống/đã cọc/đã thuê; lịch xem trực tuyến | `landlord-state.test.tsx` |
| E2 ✓ | Tìm kiếm, bản đồ, xem nhanh, tư vấn so sánh, cẩm nang, đặt lịch từ tin | `search-portal.test.tsx` |
| E3 ✓ | Hộp thư, chuyển giao từ trợ lý, Admin Console | `inbox-admin.test.tsx` |
| E4 ✓ | Chuông thông báo | `inbox-admin.test.tsx` |
| E5 ✓ | Dashboard, hợp đồng, hóa đơn, sửa chữa, khách tiềm năng; xem/in văn bản | `pms.test.tsx` |
| E6 ✓ | Trợ lý chủ nhà (bài đăng, chia sẻ, giá, giọng nói), trang tin công khai | `copilot.test.tsx` |

Còn lại: demo trên trình duyệt (ảnh/video), kiểm viewport 360/768/1280, tải ảnh tin.
