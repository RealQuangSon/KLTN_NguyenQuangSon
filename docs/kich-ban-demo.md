# Kịch bản demo HomeMatch trên trình duyệt

Các bước demo HomeMatch trên localhost. Các lệnh khởi động và đăng nhập ở Phần 0.

Kịch bản phủ:

| Yêu cầu | Bước |
|---|---|
| 3 vai trò: người thuê, chủ nhà, quản trị viên | renter (P1, P3, P4), owner2 / chủ-demo (P2, P4, P5, P6), admin (P7) |
| 5 phân hệ: cổng người thuê, tự động hóa, Admin Console, PMS, trợ lý AI chủ nhà | P1+P3, P7 (job + thông báo), P7, P2+P4, P5 |
| Kết quả tới khách ngay, không chờ chủ nhà; sửa phòng không liên quan không làm mất kết quả (D-10, D-11) | Bước 04, 07, 08, 10 |
| Đăng ký chủ nhà + admin duyệt (BE-03) | Bước 18–22 |
| Ticket hỗ trợ + `/quan-tri/ho-tro` (BE-04) | Bước 05, 23 |
| Chi phí AI VND (BE-05) | Bước 24 |
| Ảnh (BE-06), ưu đãi (BE-07) | Bước 09, 12, 16, 17 |
| Mô phỏng vay qua chat (AG-02/FE-07) | Bước 11 |

---

## Phần 0 — Chuẩn bị môi trường (terminal, chưa cần đăng nhập)

### Bước 01 — Tạo DB mới, nạp dữ liệu, khởi động hai dịch vụ

- **Tài khoản:** chưa cần.
- **URL:** sau bước này `http://127.0.0.1:8000` (API) và `http://127.0.0.1:5173` (giao diện).
- **Thao tác:** mở terminal tại thư mục gốc repo và chạy đúng lệnh trong README:

```bash
# DB mới mỗi lần quay để kịch bản luôn lặp lại được
rm -f .local/homematch-demo.sqlite*

export HOMEMATCH_DB_PATH=.local/homematch-demo.sqlite
export HOMEMATCH_CATALOG_PATH=data/catalog/rooms.json
export HOMEMATCH_AUTH_MODE=seed HOMEMATCH_LLM_MODE=demo HOMEMATCH_MATCHING_METHOD=B1 HOMEMATCH_EMBEDDING_MODE=disabled

.venv/bin/python -m backend.manage setup
.venv/bin/python -m backend.manage seed-users
.venv/bin/python -m backend.manage seed-demo

# Terminal 1 — API
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --log-config backend/logging.json

# Terminal 2 — giao diện
npm --prefix frontend run dev
```

- **Kết quả mong đợi:** `setup` in `{"storage": "sqlite", "schema_version": …, "rooms": 220}`; `seed-users` in `{"status": "seeded", "passwords_rotated": false}`; `seed-demo` in trạng thái đã nạp kịch bản PMS (hợp đồng, hóa đơn, sự cố, hội thoại của `owner2`/`renter`, toàn bộ nội dung có tiền tố `[DEMO]`). Uvicorn ghi `Application startup complete`, Vite ghi sẵn sàng ở `http://127.0.0.1:5173/`.
> **Đã có `seed-demo` (BE-08, 08/10/2026):** lệnh `python -m backend.manage seed-demo` tạo sẵn dữ liệu PMS `[DEMO]` cho `owner2`/`renter` (hợp đồng, 2 kỳ hóa đơn — kỳ 1 đã thu đủ, kỳ 2 quá hạn kèm báo chuyển một phần, 1 sự cố đang xử lý, 1 hội thoại). Lệnh idempotent — chạy lại chỉ báo `already_seeded`; từ chối chạy khi `HOMEMATCH_PUBLIC=true`.

**Tài khoản dùng trong demo** (mật khẩu chung `123456`, tạo bởi `seed-users`):

| Username | Vai trò | Mật khẩu |
|---|---|---|
| `renter` | Người thuê | `123456` |
| `owner2` | Chủ nhà TP.HCM (đã được duyệt sẵn) | `123456` |
| `owner1` | Chủ nhà Hà Nội, có phòng trong kết quả Cầu Giấy (Bước 07) | `123456` |
| `admin` | Quản trị viên | `123456` |
| `owner-demo` | Chủ nhà tự đăng ký trong Bước 18 | `demo-owner-2026` |

Chế độ `HOMEMATCH_LLM_MODE=demo` dùng trình hiểu ngôn ngữ ngoại tuyến nên không cần API key và không phát sinh chi phí; hành vi ý định giống bản GPT nhưng câu trả lời cố định.

---

## Phần 1 — Cổng người thuê: trợ lý AI (renter)

### Bước 02 — Đăng nhập người thuê

- **Tài khoản:** `renter` / `123456`.
- **URL:** `http://127.0.0.1:5173/dang-nhap`
- **Thao tác:** nhập tên đăng nhập, mật khẩu, bấm **Đăng nhập**.
- **Kết quả mong đợi:** chuyển tới `/tro-ly-ai`; thanh bên ghi "KHÔNG GIAN NGƯỜI THUÊ"; khung chat mở với câu chào của trợ lý; tên `renter` ở góc dưới thanh bên.
### Bước 03 — Chat nhu cầu ban đầu

- **Tài khoản:** `renter`.
- **URL:** `http://127.0.0.1:5173/tro-ly-ai`
- **Thao tác:** gõ vào khung chat: `Tìm căn hộ 1 phòng ngủ ở Cầu Giấy, Hà Nội cho 2 người, view thoáng` rồi gửi.
- **Kết quả mong đợi:** trợ lý ghi vào nháp hồ sơ (thành phố Hà Nội, khu vực Cầu Giấy, 2 người) và hỏi tối đa 2 câu làm rõ còn thiếu; khung "Hồ sơ nhu cầu" bên cạnh cập nhật nháp kèm nhãn `Nháp · v…` và gợi ý ngân sách nếu bạn nhắc số tiền.
### Bước 04 — Xác nhận hồ sơ và kịch bản tài chính

- **Tài khoản:** `renter`.
- **URL:** `http://127.0.0.1:5173/tro-ly-ai` (cùng trang, khung "Hồ sơ nhu cầu").
- **Thao tác:** trong khung hồ sơ chọn Thành phố **Hà Nội**, Khu vực **Cầu Giấy**, Loại chỗ ở **Căn hộ**, Số phòng ngủ tối thiểu **1**; đặt **Ngân sách tổng tháng (VND)** `16000000`, **Tiền mặt sẵn có cho vào ở (VND)** `15000000`; ở khung "Năng lực tài chính" nhập **Thu nhập mỗi tháng (VND)** `30000000`; tích **"Nếu thiếu tiền vào ở, ước tính khoản vay ngắn hạn"** với **Lãi suất (%/năm)** `12` và **Số tháng trả góp** `12`. Bấm **Xác nhận & tìm phòng**.
- **Kết quả mong đợi:** nhãn hồ sơ đổi thành `Đã xác nhận · v2`; danh sách phòng hiện **ngay trong lượt này**, không chờ ai duyệt; chuông có thông báo "Danh sách phòng phù hợp đã sẵn sàng". Với catalog tổng hợp và DB mới, hồ sơ này cho 3 căn của `owner1` (đã chạy qua API, chưa chạy trên trình duyệt).
**Kho Chợ Tốt (D-12, 08/11/2026):** khi nhiều tin thiếu phí hoặc sức chứa, kết quả vẫn hiện ngay, không còn bước bấm "Chấp nhận dữ liệu ước tính". Dòng đếm ở khung kết quả ghi "N căn khớp, đây là 5 căn xếp đầu" kèm liên kết "Xem đủ trong Tìm kiếm" (mở `/tim-kiem` cùng thành phố, khu, loại, trần, số người). Thẻ thiếu phí ghi "/tháng · ước tính"; thẻ thiếu sức chứa ghi "Sức chứa: chưa rõ"; phí không biết không bao giờ hiện 0.

### Bước 05 — Yêu cầu gặp người thật (tạo ticket hỗ trợ, BE-04)

- **Tài khoản:** `renter`.
- **URL:** `http://127.0.0.1:5173/tro-ly-ai`
- **Thao tác:** gõ vào khung chat: `Tôi muốn gặp nhân viên hỗ trợ`.
- **Kết quả mong đợi:** máy chủ nhận diện ý định hỗ trợ (không gọi LLM), tạo ticket trạng thái "Chờ xử lý" và trả lời xác nhận đã chuyển cho nhân viên; không hiện số điện thoại hay email nào.
---

## Phần 2 — Chủ nhà: không duyệt gì, tình trạng phòng, ảnh tin, ưu đãi

### Bước 06 — Đăng nhập chủ nhà, tổng quan PMS

- **Tài khoản:** đăng xuất `renter`, đăng nhập `owner2` / `123456`.
- **URL:** `http://127.0.0.1:5173/dang-nhap` → về `http://127.0.0.1:5173/chu-nha/tong-quan`
- **Thao tác:** đăng nhập, quan sát trang Tổng quan.
- **Kết quả mong đợi:** thanh bên "KHÔNG GIAN CHỦ NHÀ"; Tổng quan hiển thị số liệu từ dữ liệu thật của owner2 (phòng, hợp đồng, nợ, sự cố) trong đó các mục do `seed-demo` tạo mang tiền tố `[DEMO]`.
### Bước 07 — Chủ nhà không phải duyệt hay theo dõi gì

- **Tài khoản:** đăng xuất `owner2`, đăng nhập `owner1` / `123456`.
- **URL:** `http://127.0.0.1:5173/chu-nha/khach-tiem-nang` (link cũ)
- **Thao tác:** mở link cũ của trang Khách tiềm năng.
- **Kết quả mong đợi:** chuyển về `/chu-nha/tong-quan`; thanh bên không có mục duyệt gợi ý hay khách tiềm năng (D-10, D-13). Kết quả của `renter` ở Bước 04 đã tới khách mà chủ nhà không phải làm gì; chủ nhà chỉ biết có khách khi khách nhắn tin hoặc đặt lịch (Bước 12–13). Ảnh `buoc-07.png` cần chụp lại.
### Bước 08 — Chủ nhà khác sửa phòng không liên quan

- **Tài khoản:** đăng xuất `owner1`, đăng nhập `owner2`.
- **URL:** `http://127.0.0.1:5173/chu-nha/phong`
- **Thao tác:** đổi tình trạng một phòng TP.HCM của owner2. Phòng này không nằm trong danh sách Cầu Giấy của `renter`.
- **Kết quả mong đợi:** lưu thành công. Bước 10 kiểm tra kết quả của `renter` không bị mất (D-11).
### Bước 09 — Tải ảnh tin và đặt ưu đãi (BE-06, BE-07)

- **Tài khoản:** `owner2`.
- **URL:** `http://127.0.0.1:5173/chu-nha/phong`
- **Thao tác:** bấm **Sửa** ở một phòng của owner2; trong khung "Ảnh tin" chọn 2–3 file ảnh JPEG/PNG (mỗi file ≤ 5 MB), đợi tải lên, dùng nút ↑/↓ để đổi ảnh bìa; ở khung "Ưu đãi" nhập nội dung `Giảm 50% phí dịch vụ tháng đầu` và ngày hết hạn (hôm nay + 30 ngày), bấm **Lưu ưu đãi**.
- **Kết quả mong đợi:** lưới ảnh hiện đủ, thông báo "Đã tải 3 ảnh. Ảnh đầu tiên là ảnh bìa của tin."; ưu đãi lưu thành công kèm ngày hết hạn; bấm **Lưu thay đổi** để đóng trình sửa.
---

## Phần 3 — Người thuê vẫn giữ kết quả và mô phỏng vay qua chat (renter)

### Bước 10 — Khách vẫn giữ kết quả sau khi kho đổi (D-11)

- **Tài khoản:** đăng xuất `owner2`, đăng nhập lại `renter`.
- **URL:** `http://127.0.0.1:5173/tro-ly-ai`
- **Thao tác:** xem vùng kết quả và chuông thông báo ở góc phải trên.
- **Kết quả mong đợi:** danh sách vẫn đủ các căn như Bước 04, đúng thứ tự, không phải xác nhận lại hồ sơ, vì các phòng owner2 vừa sửa không làm kết quả khác đi. Chỉ khi một căn trong danh sách đổi, hoặc có căn mới lọt vào danh sách, kết quả mới hết hiệu lực.
### Bước 11 — Hỏi mô phỏng vay ngay trong chat (AG-02/FE-07)

- **Tài khoản:** `renter`.
- **URL:** `http://127.0.0.1:5173/tro-ly-ai`
- **Thao tác:** gõ: `vay 20 triệu lãi 10% trong 12 tháng thì sao` rồi gửi.
- **Kết quả mong đợi:** dưới câu trả lời xuất hiện **thẻ mô phỏng vay**: tên căn, kịch bản (gốc vay 20.000.000 đ, lãi 10%/năm, 12 tháng), số trả góp mỗi tháng, tổng lãi, tỷ lệ chi trả và băng đánh giá. Nếu chưa có căn nào đủ điều kiện để mô phỏng, máy chủ trả `needs_results`: hiện câu giải thích kèm nút "Xem danh sách gợi ý".
### Bước 12 — Tìm theo bộ lọc: gallery ảnh, nhãn ưu đãi, so sánh, đặt lịch

- **Tài khoản:** `renter`.
- **URL:** `http://127.0.0.1:5173/tim-kiem`
- **Thao tác:** lọc khu vực Cầu Giấy; bấm **Xem nhanh** ở tin có ảnh — dùng ←/→ để chuyển ảnh trong gallery; quan sát nhãn **"Ưu đãi"** kèm dòng "đến dd/mm"; tích 2 tin rồi bấm **So sánh & tư vấn**; mở lại khung xem nhanh và bấm **Đặt lịch xem** (chọn trực tuyến).
- **Kết quả mong đợi:** gallery chuyển ảnh bằng bàn phím; nhãn ưu đãi chỉ hiện ở tin owner2 vừa đặt, giá hiển thị **không đổi**; bảng so sánh có ưu/nhược điểm theo dữ liệu; đặt lịch thành công và owner2 nhận yêu cầu xem.
---

## Phần 4 — PMS chạy bằng dữ liệu [DEMO] (owner2 ↔ renter)

### Bước 13 — Chat với chủ nhà

- **Tài khoản:** `renter` gửi, sau đó `owner2` trả lời.
- **URL:** renter: `http://127.0.0.1:5173/tin-nhan` (mở hội thoại của phòng); owner: `http://127.0.0.1:5173/chu-nha/hop-thu`
- **Thao tác:** renter bấm **Chat với chủ nhà** từ khung xem nhanh rồi gửi một tin; đổi sang owner2, mở Hộp thư, trả lời.
- **Kết quả mong đợi:** hai bên thấy tin của nhau, có bộ đếm tin chưa đọc; ngữ cảnh chuyển giao (phòng, nhu cầu, băng tài chính) hiển thị phía trên hội thoại phía chủ nhà — **không** có thu nhập, tỷ lệ, SĐT hay email.
### Bước 14 — Hợp đồng [DEMO]: chấp thuận và kích hoạt

- **Tài khoản:** `renter` chấp thuận, rồi `owner2` kích hoạt.
- **URL:** renter: `http://127.0.0.1:5173/nguoi-thue/hop-dong`; owner: `http://127.0.0.1:5173/chu-nha/hop-dong`
- **Thao tác:** renter mở hợp đồng `[DEMO]` ở trạng thái "Đã gửi", đọc văn bản, bấm **Chấp thuận phiên bản 1**; đổi sang owner2, bấm **Kích hoạt**.
- **Kết quả mong đợi:** renter thấy hợp đồng chờ chấp thuận đúng phiên bản; sau khi kích hoạt, hợp đồng sang "Có hiệu lực" và phòng chuyển thành "Đã thuê" trong kho của owner2.
### Bước 15 — Hóa đơn [DEMO]: báo chuyển tiền, xác nhận thu, biên lai

- **Tài khoản:** `renter` báo đã chuyển, rồi `owner2` xác nhận.
- **URL:** renter: `http://127.0.0.1:5173/nguoi-thue/hoa-don`; owner: `http://127.0.0.1:5173/chu-nha/hoa-don`
- **Thao tác:** renter bấm **Báo đã chuyển** trên hóa đơn `[DEMO]`; owner2 mở Hóa đơn & công nợ, ở phần yêu cầu chuyển tiền bấm **Đã nhận** để xác nhận thu.
- **Kết quả mong đợi:** renter thấy trạng thái "Đã báo chuyển tiền" trước, sau khi chủ nhà xác nhận chuyển "Đã thanh toán" và có biên lai; chủ nhà ghi được thu đúng số còn nợ, không thu vượt.
### Bước 16 — Sự cố [DEMO] kèm ảnh (BE-06)

- **Tài khoản:** `renter` báo hỏng, rồi `owner2` xử lý.
- **URL:** renter: `http://127.0.0.1:5173/nguoi-thue/sua-chua`; owner: `http://127.0.0.1:5173/chu-nha/sua-chua`
- **Thao tác:** renter bấm **Báo hỏng**, nhập mô tả `Điều hòa [DEMO] chạy tiếng ồn`, đính kèm 1–2 ảnh, mức "Bình thường", gửi; owner2 mở Sửa chữa, xem ảnh trong ticket, lần lượt bấm **Phân công** → **Bắt đầu xử lý** → **Đã xử lý**.
- **Kết quả mong đợi:** ticket tạo thành công, tối đa 5 ảnh được tải sau khi tạo; ảnh sự cố chỉ hai bên xem được; owner2 nhận sự cố mới và đổi được trạng thái; renter thấy cập nhật và có thể đóng hoặc mở lại kèm lý do.
---

## Phần 4b — Luồng thuê phòng end-to-end

Hai nhánh bổ sung để quay demo luồng mới (chạy sau Phần 4, cùng DB):

**Nhánh chủ nhà (owner2 ↔ renter):**
1. renter mở tin owner2 từ tìm theo bộ lọc (`/tim-kiem`) → bấm "Đặt lịch xem": form dùng chung — chọn ngày + khung giờ (Sáng/Chiều/Tối), họ tên điền sẵn từ tài khoản, SĐT điền sẵn từ lần đặt lịch gần nhất (lần đầu người thuê tự nhập vì SĐT không lưu trên tài khoản), ô đồng ý chia sẻ liên hệ. Câu chữ nói rõ đây là thời gian **mong muốn**.
2. Gửi xong: renter xem `/nguoi-thue/lich-xem` — trạng thái "Chờ xác nhận"; **chưa thấy SĐT hiện cho chủ nhà**.
3. owner2 mở `/chu-nha/lich-xem` → lịch mới hiện với liên hệ bị ẩn → bấm "Xác nhận" → giờ owner2 thấy tên + SĐT khách.
4. owner2 bấm "Đề xuất giờ khác" → renter thấy "Có đề xuất giờ mới" → bấm "Đồng ý giờ mới".
5. owner2 bấm "Hoàn tất" → renter bấm "Gửi phản hồi" (1–5 sao).
6. owner2 vào `/chu-nha/lich-xem`... hợp đồng tạo từ lịch: tin `completed` mở PMS → tạo hợp đồng mới — form đã điền sẵn phòng/người thuê (không gõ mã tài khoản). Gửi → renter chấp nhận → kích hoạt → ghi số điện nước → hóa đơn → renter "Báo đã chuyển" → owner2 xác nhận → phiếu thu.
7. renter quay lại `/nguoi-thue/lich-xem` — lịch xem có link "Xem hợp đồng".

**Nhánh tin cào (điều phối, admin):**
1. Cần catalog Chợ Tốt (HOMEMATCH_CATALOG_PATH trỏ snapshot cào; trên DB mới). renter đặt lịch một tin cào → giao diện nói rõ: "HomeMatch sẽ liên hệ người đăng để xác nhận; đây chưa phải lịch đã chốt".
2. admin vào `/quan-tri/dieu-phoi`: hàng đợi lịch với link tin gốc, nút "Xem SĐT khách" (mỗi lần xem ghi audit), các nút xác nhận/từ chối/hoàn tất. Ghi rõ: người điều phối TỰ liên hệ người đăng, không tự động gọi/nhắn.
3. owner2 đăng nhập: không thấy lịch này ở bất kỳ đâu.
4. admin xác nhận → hoàn tất; renter gửi phản hồi. Tin cào **không** có nút tạo hợp đồng: "Tin cào: hợp đồng ký trực tiếp với người đăng, ngoài hệ thống".

**Nhánh lỗi (minh họa giữa luồng):** chủ nhà đánh dấu phòng hết trong lúc chờ → xác nhận lịch trả 409 `stale_viewing`; khách hủy lịch → mọi thao tác sau trả 409 `viewing_conflict`.

## Phần 5 — Trợ lý AI chủ nhà (owner2)

### Bước 17 — Viết bài đăng, trang tin công khai, hỏi co-pilot

- **Tài khoản:** `owner2`.
- **URL:** `http://127.0.0.1:5173/chu-nha/tro-ly`
- **Thao tác:** chọn phòng vừa tải ảnh, yêu cầu **viết bài đăng**, bấm **Sao chép nội dung**; mở link trang tin công khai trong bài (`/tin/{id}`); quay lại hỏi `Vì sao phòng trống lâu?`.
- **Kết quả mong đợi:** bài đăng chỉ dùng dữ liệu tin và có link trang tin công khai; trang `/tin/{id}` xem được không cần đăng nhập, có gallery ảnh và nhãn ưu đãi; co-pilot trả lời "Vì sao phòng trống lâu" dựa trên dữ liệu phòng của owner2 (đề xuất giá cần ít nhất 3 căn tương đương).
---

## Phần 6 — Chủ nhà tự đăng ký và luồng duyệt (BE-03)

### Bước 18 — Đăng ký tài khoản chủ nhà mới

- **Tài khoản:** chưa cần (tạo mới `owner-demo`).
- **URL:** `http://127.0.0.1:5173/dang-ky`
- **Thao tác:** chọn radio **Chủ nhà** (hiện ghi chú "Sau khi xác minh email, tài khoản chủ nhà cần quản trị viên duyệt trước khi công khai tin."); điền: Họ và tên `Chủ Demo`, Email `owner-demo@example.com`, Tên đăng nhập `owner-demo`, Mật khẩu `demo-owner-2026`, nhập lại mật khẩu; bấm **Đăng ký**.
- **Kết quả mong đợi:** thông báo xanh "Đã tạo tài khoản, đang chờ xác minh email…"; log máy chủ (Terminal 1) in dòng `DEV-STUB fake delivery … verification_code=…` — đây là mã xác minh giả lập, không có email thật.
### Bước 19 — Xác minh email bằng mã trong log (terminal)

- **Tài khoản:** `owner-demo`.
- **URL:** `http://127.0.0.1:8000` (gọi trực tiếp API; giao diện chưa có màn nhập mã).
- **Thao tác:** đọc mã `verification_code` trong log backend rồi chạy:

```bash
curl -s -X POST http://127.0.0.1:8000/auth/verify \
  -H "Content-Type: application/json" \
  -d '{"username":"owner-demo","token":"THAY_MÃ_VỪA_ĐỌC"}'
```

- **Kết quả mong đợi:** API trả `{"status":"verified", …}`; tài khoản chuyển thành chủ nhà **chờ duyệt** (`landlord_status = pending`).
### Bước 20 — Chủ nhà chờ duyệt: soạn được nhưng chưa công khai được

- **Tài khoản:** `owner-demo` / `demo-owner-2026`.
- **URL:** `http://127.0.0.1:5173/chu-nha/phong`
- **Thao tác:** đăng nhập; quan sát banner; bấm **Thêm phòng**, điền tối thiểu các ô bắt buộc, lưu tin nháp; thử tìm ô "Công khai tin cho khách tìm thấy".
- **Kết quả mong đợi:** banner cố định trên mọi trang `/chu-nha/*`: "Tài khoản đang chờ quản trị viên duyệt — bạn có thể soạn tin nhưng chưa công khai được."; tạo tin nháp thành công; ô **Công khai bị khóa** kèm giải thích; không có nút nào cho phép công khai.
### Bước 21 — Quản trị viên duyệt hồ sơ

- **Tài khoản:** đăng xuất, đăng nhập `admin` / `123456`.
- **URL:** `http://127.0.0.1:5173/quan-tri/tai-khoan`
- **Thao tác:** trong khối "Chủ nhà chờ duyệt", thấy hàng `Chủ Demo · owner-demo@example.com · Đã xác minh`; bấm **Duyệt**.
- **Kết quả mong đợi:** hàng biến mất, khối hiện "Không có chủ nhà chờ duyệt."; `owner-demo` được cấp membership chủ nhà và nhận thông báo; (nút **Từ chối** mở hộp nhập lý do bắt buộc 1–500 ký tự — có thể demo thêm bằng tài khoản thứ hai).
### Bước 22 — Chủ nhà đã duyệt công khai tin

- **Tài khoản:** `owner-demo`.
- **URL:** `http://127.0.0.1:5173/chu-nha/phong`
- **Thao tác:** đăng nhập lại; bật **Công khai** cho tin nháp; sau đó đăng nhập `renter`, mở `http://127.0.0.1:5173/tim-kiem` và lọc khu vực của tin đó.
- **Kết quả mong đợi:** banner chờ duyệt biến mất; bật công khai thành công (không còn lỗi 403 `landlord_not_approved`); `renter` tìm thấy tin mới trong bộ lọc.
---

## Phần 7 — Quản trị viên: Admin Console (admin)

### Bước 23 — Xử lý ticket hỗ trợ (BE-04)

- **Tài khoản:** `admin`.
- **URL:** `http://127.0.0.1:5173/quan-tri/ho-tro`
- **Thao tác:** thấy ticket "Chờ xử lý" tạo ở Bước 05; bấm **Nhận xử lý**; lọc theo trạng thái; bấm **Đã giải quyết**, nhập ghi chú `Đã gọi lại và hướng dẫn khách cách xác nhận hồ sơ` và xác nhận; bấm link "phiên" trên bảng.
- **Kết quả mong đợi:** ticket chuyển Chờ xử lý → Đang xử lý → Đã giải quyết (không nhập ghi chú thì hộp không cho gửi); link mở đúng phiên ở `/quan-tri/hoi-thoai`; `renter` nhận đúng một thông báo theo mỗi lần đổi trạng thái.
### Bước 24 — Hội thoại AI, chuyển giao, vận hành (BE-05) và tự động hóa

- **Tài khoản:** `admin`.
- **URL:** `http://127.0.0.1:5173/quan-tri/hoi-thoai` → `/quan-tri/chuyen-giao` → `/quan-tri/van-hanh`
- **Thao tác:** mở phiên của `renter` lần đầu; chuyển sang Chuyển giao; mở Vận hành; (tùy chọn) chạy job tay trong terminal: `.venv/bin/python -m backend.manage jobs`.
- **Kết quả mong đợi:**
  - **Hội thoại AI:** transcript đã che SĐT/email; lần mở đầu tiên được ghi audit (mở lại thấy marker đã mở).
  - **Chuyển giao:** tỷ lệ và thời gian phản hồi đầu tiên của từng chủ nhà.
  - **Vận hành:** thẻ **"Chi phí AI ước tính"** hiện dạng `≈ <số> đ (bảng giá ngày dd/mm/yyyy)`; nếu chưa đủ dữ liệu thì hiện "Chưa tính được — thiếu: …", **không bao giờ hiện 0**; "Số liệu tiến trình" và "Bản gợi ý tạo lỗi" (khởi tạo lại được).
  - **Tự động hóa:** job nền chạy 5 phút một lần trong API; chạy tay in JSON kết quả các job và không sinh thông báo trùng (khóa chống trùng).
---

## Phần 8 — Kiểm viewport (360 / 768 / 1280 px)

Người quay nên đổi bề rộng cửa sổ (DevTools → Toggle device toolbar) và rà nhanh các màn chính ở ba bề rộng:

| Bề rộng | Màn cần rà | Tiêu chí đạt |
|---|---|---|
| 360 px | `/tro-ly-ai`, `/tim-kiem` (khung xem nhanh), `/chu-nha/lich-xem`, `/chu-nha/hoa-don`, `/quan-tri/ho-tro` | Không tràn ngang; mọi nút bấm được; bảng có cuộn ngang riêng trong khung, không làm vỡ trang; hộp thoại (lý do duyệt, ghi chú ticket) giữ focus và đóng bằng Escape |
| 768 px | cùng các màn trên | Bố cục hai cột co giãn hợp lý; không có vùng chữ bị cắt |
| 1280 px | toàn bộ kịch bản | Đây là bề rộng quay chính |
