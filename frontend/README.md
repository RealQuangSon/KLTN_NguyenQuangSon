# HomeMatch Frontend

React 19 + TypeScript + Vite, gọi FastAPI qua API thật. Không dùng thư viện router hay quản lý state: `src/router.tsx` là bộ định tuyến history gọn, hỗ trợ deep link và back/forward.

Màn hình và route: [UI_SPEC.md](UI_SPEC.md). Màu, phông, bố cục: [DESIGN.md](../DESIGN.md).

## Cấu trúc

- `src/pages/`: trợ lý AI, tìm kiếm, tin nhắn, cẩm nang, cổng chủ nhà (PMS), Admin Console, trang tin công khai, đăng nhập/đăng ký.
- `src/components/`: thành phần dùng chung (bản đồ, thẻ phòng, form lịch xem, thư viện ảnh).
- `src/api.ts`: gọi API, lỗi `ApiError`, `mutationKey()` chống gửi trùng.
- `src/locations.ts`: danh mục khu vực, có test giữ đồng bộ với `backend/app/locations.py`.
- `src/tests/`: test và fixture Vitest.

## Chạy local

Kiểm chứng với Node 26, npm 11. Khởi động backend trước theo [README gốc](../README.md).

```bash
cd frontend
npm ci
npm run dev
```

Mở `http://127.0.0.1:5173`. Vite proxy `/api` tới `http://127.0.0.1:8000`.

Biến môi trường (đặt trong `.env.local`, xem `.env.example`):

- `VITE_API_BASE_URL`: mặc định `/api`.
- `VITE_GOONG_API_KEY`: tùy chọn, dùng tile bản đồ Goong. Không có thì dùng OpenStreetMap.

Không đưa khóa LLM hay thông tin kết nối DB vào biến `VITE_*`.

```bash
npm test
npm run typecheck
npm run build
npm run format
```

## Dữ liệu và bảo mật client

- Không có API giả hay phòng hardcode khi chạy; fixture chỉ nằm trong `src/tests/`.
- Khoản tiền `null` hiển thị "Chưa rõ", không đổi thành 0.
- Token và mã phiên chỉ ở `sessionStorage`; đăng xuất, hết hạn hoặc đổi tài khoản thì xóa.
- Frontend không tính điểm, quyền hay công bố; backend kiểm tra quyền theo từng bản ghi.
