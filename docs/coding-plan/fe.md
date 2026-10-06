# Coding plan — Frontend (FE)

Đọc [README.md](README.md) trước. FE chỉ sửa trong `frontend/`.

**FE không cần chờ BE.** Code theo hợp đồng ở README §7 và test bằng mock. Khi BE xong, so tên trường với `docs/openapi.json` rồi chạy lại test.

**Code mẫu cần đọc:**
- `frontend/src/api.ts`: `Api.get/post/put/patch/delete`, `ApiError` (`status`, `code`, `message`), `mutationKey()`.
- `frontend/src/App.tsx`: route theo vai trò (`/chu-nha/*`, `/quan-tri/*`, `/nguoi-thue/*`, `/tin/:id`).
- `frontend/src/pages/AdminWorkspace.tsx`: kiểu `AdminSection`, map `titles`, nạp dữ liệu theo `section`.
- `frontend/src/tests/inbox-admin.test.tsx`: mẫu test dùng `new Api("t")` và `vi.spyOn(api, "get").mockImplementation(...)`.
- `frontend/UI_SPEC.md`, `DESIGN.md`: nguyên tắc giao diện. Hiển thị trạng thái thật, khoản `null` hiện "Chưa rõ", chủ nhà không thấy thu nhập.

**Luật riêng của mảng:**
- Frontend **không** tính tiền, điểm, quyền hay công bố. Chỉ hiển thị số do API trả.
- Chỉ lưu token và `session_id` trong `sessionStorage`; không đưa dữ liệu nhạy cảm lên URL.
- Thao tác chính dùng được bằng bàn phím. Hộp thoại giữ focus và đóng bằng Escape (xem `ViewingPanel.tsx`).
- Chạy `npm --prefix frontend run format` trước khi báo xong.
- Không thêm thư viện state hay router. Chỉ thêm dependency khi thật cần, và ghi lý do trong báo cáo.

| ID | Task | Ưu tiên | Phụ thuộc (hợp đồng) |
|---|---|---|---|
| FE-01 | Sửa thông báo cũ ở màn đăng ký | P0 | — |
| FE-02 | Đăng ký chủ nhà; admin duyệt chủ nhà; banner "chờ duyệt" | P1 | §7.1 (BE-03) |
| FE-03 | Màn ticket hỗ trợ `/quan-tri/ho-tro` | P1 | §7.2 (BE-04) |
| FE-04 | Hiện chi phí AI quy ra VND ở Vận hành | P1 | §7.3 (BE-05) |
| FE-05 | Ảnh: upload ở trình sửa tin và báo hỏng; gallery | P2 | §7.5 (BE-06) |
| FE-06 | Ưu đãi: chủ nhà đặt; khách thấy nhãn | P2 | §7.6 (BE-07) |
| FE-07 | Thẻ mô phỏng vay trong chat | P1 | §7.4 (AG-02) |
| FE-08 | Tách `Pms.tsx` (tùy chọn) | P3 | — |
| FE-09 | Kịch bản demo trên trình duyệt và kiểm viewport | P2 | BE-08 |

---

## FE-01 — Sửa thông báo cũ ở màn đăng ký

- `frontend/src/pages/Register.tsx` ~dòng 66–68 đang có nhánh `err.status === 404` với câu "Máy chủ chưa có chức năng đăng ký…". Backend đã có `POST /auth/register`.
- Bỏ câu đó: mọi lỗi hiện `err.message` của `ApiError`; lỗi mạng (`status === 0`) hiện "Không kết nối được máy chủ".
- Sửa test cũ có câu này: `grep -rn "chưa có chức năng đăng ký\|no register endpoint" frontend/src/tests`. Test `auth-and-keys` đang kiểm "reports a truthful error when the server has no register endpoint"; đổi thành kiểm hiển thị đúng `message` từ server.

---

## FE-02 — Đăng ký chủ nhà và admin duyệt

**Hợp đồng:** README §7.1.

1. **`Register.tsx`:**
   - Thêm nhóm radio "Bạn là: Người thuê / Chủ nhà", mặc định Người thuê, gửi `account_type`.
   - Chọn Chủ nhà thì hiện ghi chú: "Sau khi xác minh email, tài khoản chủ nhà cần quản trị viên duyệt trước khi công khai tin."
2. **`AdminWorkspace.tsx`, section `tai-khoan`:**
   - Thêm khối "Chủ nhà chờ duyệt" (`GET /admin/landlord-applications?status=pending`). Bảng gồm tên, email, đã xác minh hay chưa, ngày đăng ký.
   - Nút **Duyệt** gọi POST approve.
   - Nút **Từ chối** mở hộp nhập lý do (bắt buộc, 1–500 ký tự) rồi gọi POST reject.
   - Sau mỗi thao tác thì nạp lại danh sách. Nếu không có ai chờ duyệt, hiện "Không có chủ nhà chờ duyệt."
3. **Chủ nhà đang chờ duyệt:**
   - `/auth/me` trả `landlord_status`. Lưu giá trị này ở nơi đang lưu `Actor` (`grep -n "auth/me" frontend/src`).
   - Khi `landlord_status === "pending"`, các trang `/chu-nha/*` hiện banner cố định: "Tài khoản đang chờ quản trị viên duyệt — bạn có thể soạn tin nhưng chưa công khai được."
   - Trong `RoomEditor.tsx`, khóa ô "Công khai" và hiện tooltip giải thích.
   - Nếu API vẫn trả 403 `landlord_not_approved`, hiện đúng thông báo đó.
4. **Kiểu dữ liệu:** thêm vào `frontend/src/types.ts`.

**Test** (`src/tests/landlord-signup.test.tsx`):
- Chọn Chủ nhà thì body gửi có `account_type: "owner"`.
- Admin thấy 1 hồ sơ chờ duyệt; bấm Duyệt gọi đúng path.
- Bấm Từ chối khi chưa nhập lý do thì không gọi API.
- Actor pending thấy banner và ô Công khai bị khóa.

---

## FE-03 — Màn ticket hỗ trợ

**Hợp đồng:** README §7.2.

1. Thêm `"ho-tro"` vào `AdminSection` và `titles`, ví dụ `["Yêu cầu hỗ trợ", "Khách muốn gặp người thật"]`. Thêm route `/quan-tri/ho-tro` trong `App.tsx` và một mục trong menu admin.
2. Màn gồm:
   - bộ lọc trạng thái (Tất cả, Chờ xử lý, Đang xử lý, Đã giải quyết);
   - bảng: thời điểm, phiên (link `/quan-tri/hoi-thoai` mở đúng phiên; xem cách section `hoi-thoai` chọn phiên), trạng thái, người xử lý, ghi chú;
   - nút **Nhận xử lý** (`requested` → `in_progress`);
   - nút **Đã giải quyết**: mở ô ghi chú bắt buộc rồi PATCH;
   - nút **Mở lại** (`resolved` → `in_progress`).
3. Lỗi 409 `ticket_state`: hiện thông báo rồi nạp lại.

**Test:** render danh sách; Đã giải quyết khi chưa có ghi chú thì không gọi API; gọi PATCH đúng body.

---

## FE-04 — Chi phí AI quy ra VND

**Hợp đồng:** README §7.3.

Trong section `van-hanh` của `AdminWorkspace.tsx`, thêm thẻ "Chi phí AI ước tính":
- `estimated_cost_vnd` khác `null`: hiện "≈ 12.345 đ (bảng giá ngày dd/mm/yyyy)";
- `null`: hiện "Chưa tính được — thiếu: {missing}". **Không hiện 0.**

**Test:** cả hai trường hợp.

---

## FE-05 — Ảnh tin và ảnh sự cố

**Hợp đồng:** README §7.5.

1. **`api.ts`:** thêm `upload(path: string, file: File): Promise<T>`.
   - Dùng `FormData` với field `file`; **không** đặt `Content-Type` thủ công.
   - Gửi kèm token như các hàm khác; xử lý lỗi bằng `ApiError`.
2. **`RoomEditor.tsx`**, chỉ hiện khi tin đã được tạo (có `id`):
   - input `type=file accept="image/jpeg,image/png,image/webp" multiple`; tải lần lượt từng file và hiện tiến độ;
   - lưới ảnh có nút Xóa và nút ↑/↓ đổi thứ tự (gọi `PATCH .../media/order`);
   - lỗi `invalid_media`, `media_too_large`, `media_limit` hiện tiếng Việt theo `message` từ server;
   - kiểm ở client (≤ 5 MB, đúng loại) chỉ để báo sớm; server vẫn là nơi quyết định.
3. **Gallery:** component mới `components/PhotoGallery.tsx` gồm ảnh chính, thumbnail, điều hướng bằng bàn phím ←/→ và `alt` có nghĩa. Dùng ở:
   - khung xem nhanh trong `SearchPage.tsx`;
   - `PublicListing.tsx`;
   - thẻ phòng (ảnh đầu tiên). Không có ảnh thì giữ `RoomIllustration` như hiện nay.
4. **Ảnh sự cố** (`MaintenancePage` trong `Pms.tsx`):
   - khi báo hỏng cho chọn tối đa 5 ảnh, tải sau khi ticket được tạo;
   - xem ảnh: vì cần token, tải bằng `fetch` có header rồi `URL.createObjectURL`, và `revokeObjectURL` khi unmount.
5. **URL ảnh:** ghép tiền tố API như các lệnh gọi khác (`VITE_API_BASE_URL`, mặc định `/api`), tức `/api/media/{id}`.

**Test:**
- Chọn file gọi `upload` đúng path.
- File 6 MB bị chặn ở client.
- Gallery render, bấm → chuyển ảnh.
- Không có ảnh thì hiện minh họa.

---

## FE-06 — Ưu đãi

**Hợp đồng:** README §7.6.

1. **`RoomEditor.tsx`:** khối "Ưu đãi" gồm ô nội dung (≤ 200 ký tự, có bộ đếm), ngày hết hạn (input `date`, giới hạn từ hôm nay đến hôm nay + 90 ngày), nút Lưu và nút Gỡ.
2. **Hiển thị cho khách:** nhãn "Ưu đãi" trên thẻ tin, khung xem nhanh và `PublicListing`. Tooltip hoặc dòng phụ "đến dd/mm". Chỉ hiện khi `promotion` khác `null`.
3. Ưu đãi **không** làm đổi giá hiển thị, và không có nhãn nào ngụ ý xếp hạng ưu tiên.

**Test:** lưu gọi PUT đúng body; nhãn hiện khi có `promotion`, không hiện khi `null`.

---

## FE-07 — Thẻ mô phỏng vay trong chat

**Hợp đồng:** README §7.4.

- `RenterWorkspace.tsx` dựng tin nhắn trả lời ở khoảng dòng 255–275 (`response.answers`, `response.message`). Thêm nhánh: khi `response.status === "simulation"` và có `response.simulation`, hiện thẻ nhỏ trong luồng chat gồm:
  - tên căn;
  - kịch bản (lãi suất năm, số tháng, gốc vay);
  - trả góp mỗi tháng, tổng tháng, tỷ lệ (chỉ khách thấy);
  - băng đánh giá.

  Dùng lại component hiển thị kết quả trong `components/Simulation.tsx` nếu tách được; không viết lại cách format.
- `status === "needs_results"`: hiện `message` kèm nút "Xem danh sách gợi ý".
- Giá trị `null` hiện "Chưa rõ".

**Test:** response giả có `simulation` → thẻ hiện đúng số trả góp; `needs_results` → hiện nút.

---

## FE-08 — Tách `Pms.tsx` (tùy chọn, cần người dùng đồng ý)

- Tách `Pms.tsx` (~1160 dòng) thành `pages/pms/Dashboard.tsx`, `Leases.tsx`, `Billing.tsx`, `Maintenance.tsx`, `Leads.tsx` và `shared.tsx` (helper dùng chung ở đầu file hiện tại).
- `Pms.tsx` re-export đủ các export cũ: `LandlordDashboard`, `LeasesPage`, `BillingPage`, `MaintenancePage`, `LeadsPage`. Như vậy `App.tsx` và test không phải đổi import.
- Số test giữ nguyên, typecheck và build pass.

---

## FE-09 — Kịch bản demo trên trình duyệt và kiểm viewport

**Agent chuẩn bị, người dùng quay.**

1. Viết `docs/kich-ban-demo.md`, dựa trên mục Demo của `README.md` gốc. Mỗi bước có:
   - tài khoản;
   - URL;
   - thao tác;
   - **kết quả mong đợi**;
   - ô chèn ảnh `![](demo/bước-xx.png)`.

   Phủ 3 vai trò, 5 phân hệ và luồng duyệt theo chủ nhà, gồm cả bước khách thấy dần phòng trong trạng thái `partially_published`. Bắt đầu bằng DB mới, `setup`, `seed-users` và `seed-demo` (BE-08).
2. Nếu môi trường có trình duyệt tự động, ví dụ Playwright đã cài sẵn: chạy kịch bản ở viewport 360, 768 và 1280 px, lưu ảnh vào `docs/demo/`, ghi lỗi giao diện tìm thấy. **Không** cài Playwright khi người dùng chưa đồng ý. Không có trình duyệt thì ghi "chưa chạy".
3. Lỗi giao diện tìm thấy (tràn ngang, nút bị che, focus mất) thì sửa trong `frontend/` và thêm test nếu được.

**Xong khi:** có `docs/kich-ban-demo.md`; `docs/tieu-chi-nghiem-thu.md` ghi đúng trạng thái demo: chưa quay, hoặc đã quay kèm ngày.
