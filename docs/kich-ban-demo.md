# Kịch bản demo HomeMatch trên trình duyệt (FE-09)

**Cập nhật:** 06/11/2026 (bỏ bước duyệt theo D-10, thêm D-11). Kịch bản này để **người dùng tự quay video demo**; agent chuẩn bị môi trường và đã xác minh các lệnh khởi động cũng như đăng nhập (xem Phần 8). Bám theo mục Demo của `README.md`, bổ sung các tính năng mới: đăng ký và duyệt chủ nhà (BE-03/FE-02), ticket hỗ trợ (BE-04/FE-03), chi phí AI quy VND (BE-05/FE-04), ảnh tin và ảnh sự cố (BE-06/FE-05), ưu đãi (BE-07/FE-06), mô phỏng vay qua chat (AG-02/FE-07) và màn `/quan-tri/ho-tro`.

Kịch bản phủ:

| Yêu cầu | Bước |
|---|---|
| 3 vai trò: người thuê, chủ nhà, quản trị viên | renter-a (P1, P3, P4), owner-a / chủ-demo (P2, P4, P5, P6), admin-a (P7) |
| 5 phân hệ: cổng người thuê, tự động hóa, Admin Console, PMS & CRM, trợ lý AI chủ nhà | P1+P3, P7 (job + thông báo), P7, P2+P4, P5 |
| Kết quả tới khách ngay, chủ nhà nhận lead; sửa phòng không liên quan không làm mất kết quả (D-10, D-11) | Bước 04, 07, 08, 10 |
| Đăng ký chủ nhà + admin duyệt (BE-03) | Bước 18–22 |
| Ticket hỗ trợ + `/quan-tri/ho-tro` (BE-04) | Bước 05, 23 |
| Chi phí AI VND (BE-05) | Bước 24 |
| Ảnh (BE-06), ưu đãi (BE-07) | Bước 09, 12, 16, 17 |
| Mô phỏng vay qua chat (AG-02/FE-07) | Bước 11 |

Quy ước ảnh: mỗi bước có một ô chèn ảnh `![](demo/buoc-xx.png)` — file lưu trong `docs/demo/`. Khi quay, chụp đúng khung hình nêu ở "Kết quả mong đợi".

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

- **Kết quả mong đợi:** `setup` in `{"storage": "sqlite", "schema_version": …, "rooms": 220}`; `seed-users` in `{"status": "seeded", "passwords_rotated": false}`; `seed-demo` in trạng thái đã nạp kịch bản PMS (hợp đồng, hóa đơn, sự cố, hội thoại của `owner-a`/`renter-a`, toàn bộ nội dung có tiền tố `[DEMO]`). Uvicorn ghi `Application startup complete`, Vite ghi sẵn sàng ở `http://127.0.0.1:5173/`.

![](demo/buoc-01.png)

> **Đã có `seed-demo` (BE-08, 08/10/2026):** lệnh `python -m backend.manage seed-demo` tạo sẵn dữ liệu PMS `[DEMO]` cho `owner-a`/`renter-a` (hợp đồng, 2 kỳ hóa đơn — kỳ 1 đã thu đủ, kỳ 2 quá hạn kèm báo chuyển một phần, 1 sự cố đang xử lý, 1 hội thoại). Lệnh idempotent — chạy lại chỉ báo `already_seeded`; từ chối chạy khi `HOMEMATCH_PUBLIC=true`.

**Tài khoản dùng trong demo** (mật khẩu `local-<username>-password`, tạo bởi `seed-users`):

| Username | Vai trò | Mật khẩu |
|---|---|---|
| `renter-a` | Người thuê | `local-renter-a-password` |
| `owner-a` | Chủ nhà TP.HCM (đã được duyệt sẵn) | `local-owner-a-password` |
| `owner-c` | Chủ nhà Hà Nội, có phòng trong kết quả Cầu Giấy (Bước 07) | `local-owner-c-password` |
| `admin-a` | Quản trị viên | `local-admin-a-password` |
| `owner-demo` | Chủ nhà tự đăng ký trong Bước 18 | `demo-owner-2026` |

Chế độ `HOMEMATCH_LLM_MODE=demo` dùng trình hiểu ngôn ngữ ngoại tuyến nên không cần API key và không phát sinh chi phí; hành vi ý định giống bản GPT nhưng câu trả lời cố định.

---

## Phần 1 — Cổng người thuê: trợ lý AI (renter-a)

### Bước 02 — Đăng nhập người thuê

- **Tài khoản:** `renter-a` / `local-renter-a-password`.
- **URL:** `http://127.0.0.1:5173/dang-nhap`
- **Thao tác:** nhập tên đăng nhập, mật khẩu, bấm **Đăng nhập**.
- **Kết quả mong đợi:** chuyển tới `/tro-ly-ai`; thanh bên ghi "KHÔNG GIAN NGƯỜI THUÊ"; khung chat mở với câu chào của trợ lý; tên `renter-a` ở góc dưới thanh bên.

![](demo/buoc-02.png)

### Bước 03 — Chat nhu cầu ban đầu

- **Tài khoản:** `renter-a`.
- **URL:** `http://127.0.0.1:5173/tro-ly-ai`
- **Thao tác:** gõ vào khung chat: `Tìm căn hộ 1 phòng ngủ ở Cầu Giấy, Hà Nội cho 2 người, view thoáng` rồi gửi.
- **Kết quả mong đợi:** trợ lý ghi vào nháp hồ sơ (thành phố Hà Nội, khu vực Cầu Giấy, 2 người) và hỏi tối đa 2 câu làm rõ còn thiếu; khung "Hồ sơ nhu cầu" bên cạnh cập nhật nháp kèm nhãn `Nháp · v…` và gợi ý ngân sách nếu bạn nhắc số tiền.

![](demo/buoc-03.png)

### Bước 04 — Xác nhận hồ sơ và kịch bản tài chính

- **Tài khoản:** `renter-a`.
- **URL:** `http://127.0.0.1:5173/tro-ly-ai` (cùng trang, khung "Hồ sơ nhu cầu").
- **Thao tác:** trong khung hồ sơ chọn Thành phố **Hà Nội**, Khu vực **Cầu Giấy**, Loại chỗ ở **Căn hộ**, Số phòng ngủ tối thiểu **1**; đặt **Ngân sách tổng tháng (VND)** `16000000`, **Tiền mặt sẵn có cho vào ở (VND)** `15000000`; ở khung "Năng lực tài chính" nhập **Thu nhập mỗi tháng (VND)** `30000000`; tích **"Nếu thiếu tiền vào ở, ước tính khoản vay ngắn hạn"** với **Lãi suất (%/năm)** `12` và **Số tháng trả góp** `12`. Bấm **Xác nhận & tìm phòng**.
- **Kết quả mong đợi:** nhãn hồ sơ đổi thành `Đã xác nhận · v2`; danh sách phòng hiện **ngay trong lượt này**, không chờ ai duyệt; chuông có thông báo "Danh sách phòng phù hợp đã sẵn sàng". Với catalog tổng hợp và DB mới, hồ sơ này cho 3 căn của `owner-c` (đã chạy qua API, chưa chạy trên trình duyệt).

![](demo/buoc-04.png)

**Kho Chợ Tốt (D-12, 08/11/2026):** khi nhiều tin thiếu phí hoặc sức chứa, kết quả vẫn hiện ngay, không còn bước bấm "Chấp nhận dữ liệu ước tính". Dòng đếm ở khung kết quả ghi "N căn khớp, đây là 5 căn xếp đầu" kèm liên kết "Xem đủ trong Tìm kiếm" (mở `/tim-kiem` cùng thành phố, khu, loại, trần, số người). Thẻ thiếu phí ghi "/tháng · ước tính"; thẻ thiếu sức chứa ghi "Sức chứa: chưa rõ"; phí không biết không bao giờ hiện 0.

### Bước 05 — Yêu cầu gặp người thật (tạo ticket hỗ trợ, BE-04)

- **Tài khoản:** `renter-a`.
- **URL:** `http://127.0.0.1:5173/tro-ly-ai`
- **Thao tác:** gõ vào khung chat: `Tôi muốn gặp nhân viên hỗ trợ`.
- **Kết quả mong đợi:** máy chủ nhận diện ý định hỗ trợ (không gọi LLM), tạo ticket trạng thái "Chờ xử lý" và trả lời xác nhận đã chuyển cho nhân viên; không hiện số điện thoại hay email nào.

![](demo/buoc-05.png)

---

## Phần 2 — Chủ nhà: khách tiềm năng, tình trạng phòng, ảnh tin, ưu đãi

### Bước 06 — Đăng nhập chủ nhà, tổng quan PMS

- **Tài khoản:** đăng xuất `renter-a`, đăng nhập `owner-a` / `local-owner-a-password`.
- **URL:** `http://127.0.0.1:5173/dang-nhap` → về `http://127.0.0.1:5173/chu-nha/tong-quan`
- **Thao tác:** đăng nhập, quan sát trang Tổng quan.
- **Kết quả mong đợi:** thanh bên "KHÔNG GIAN CHỦ NHÀ"; Tổng quan hiển thị số liệu từ dữ liệu thật của owner-a (phòng, hợp đồng, nợ, sự cố) trong đó các mục do `seed-demo` tạo mang tiền tố `[DEMO]`.

![](demo/buoc-06.png)

### Bước 07 — Chủ nhà thấy khách tiềm năng từ gợi ý AI

- **Tài khoản:** đăng xuất `owner-a`, đăng nhập `owner-c` / `local-owner-c-password`.
- **URL:** `http://127.0.0.1:5173/chu-nha/khach-tiem-nang`
- **Thao tác:** xem danh sách khách tiềm năng.
- **Kết quả mong đợi:** có `renter-a` ở các phòng vừa lọt top 5, giai đoạn mới, mức "Mới xem · 0 điểm". Chủ nhà không phải duyệt gì; không có thu nhập hay tỷ lệ của khách.

![](demo/buoc-07.png)

### Bước 08 — Chủ nhà khác sửa phòng không liên quan

- **Tài khoản:** đăng xuất `owner-c`, đăng nhập `owner-a`.
- **URL:** `http://127.0.0.1:5173/chu-nha/phong`
- **Thao tác:** đổi tình trạng một phòng TP.HCM của owner-a. Phòng này không nằm trong danh sách Cầu Giấy của `renter-a`.
- **Kết quả mong đợi:** lưu thành công. Bước 10 kiểm tra kết quả của `renter-a` không bị mất (D-11).

![](demo/buoc-08.png)

### Bước 09 — Tải ảnh tin và đặt ưu đãi (BE-06, BE-07)

- **Tài khoản:** `owner-a`.
- **URL:** `http://127.0.0.1:5173/chu-nha/phong`
- **Thao tác:** bấm **Sửa** ở một phòng của owner-a; trong khung "Ảnh tin" chọn 2–3 file ảnh JPEG/PNG (mỗi file ≤ 5 MB), đợi tải lên, dùng nút ↑/↓ để đổi ảnh bìa; ở khung "Ưu đãi" nhập nội dung `Giảm 50% phí dịch vụ tháng đầu` và ngày hết hạn (hôm nay + 30 ngày), bấm **Lưu ưu đãi**.
- **Kết quả mong đợi:** lưới ảnh hiện đủ, thông báo "Đã tải 3 ảnh. Ảnh đầu tiên là ảnh bìa của tin."; ưu đãi lưu thành công kèm ngày hết hạn; bấm **Lưu thay đổi** để đóng trình sửa.

![](demo/buoc-09.png)

---

## Phần 3 — Người thuê vẫn giữ kết quả và mô phỏng vay qua chat (renter-a)

### Bước 10 — Khách vẫn giữ kết quả sau khi kho đổi (D-11)

- **Tài khoản:** đăng xuất `owner-a`, đăng nhập lại `renter-a`.
- **URL:** `http://127.0.0.1:5173/tro-ly-ai`
- **Thao tác:** xem vùng kết quả và chuông thông báo ở góc phải trên.
- **Kết quả mong đợi:** danh sách vẫn đủ các căn như Bước 04, đúng thứ tự, không phải xác nhận lại hồ sơ, vì các phòng owner-a vừa sửa không làm kết quả khác đi. Chỉ khi một căn trong danh sách đổi, hoặc có căn mới lọt vào danh sách, kết quả mới hết hiệu lực.

![](demo/buoc-10.png)

### Bước 11 — Hỏi mô phỏng vay ngay trong chat (AG-02/FE-07)

- **Tài khoản:** `renter-a`.
- **URL:** `http://127.0.0.1:5173/tro-ly-ai`
- **Thao tác:** gõ: `vay 20 triệu lãi 10% trong 12 tháng thì sao` rồi gửi.
- **Kết quả mong đợi:** dưới câu trả lời xuất hiện **thẻ mô phỏng vay**: tên căn, kịch bản (gốc vay 20.000.000 đ, lãi 10%/năm, 12 tháng), số trả góp mỗi tháng, tổng lãi, tỷ lệ chi trả và băng đánh giá. Nếu chưa có căn nào đủ điều kiện để mô phỏng, máy chủ trả `needs_results`: hiện câu giải thích kèm nút "Xem danh sách gợi ý".

![](demo/buoc-11.png)

### Bước 12 — Tìm theo bộ lọc: gallery ảnh, nhãn ưu đãi, so sánh, đặt lịch

- **Tài khoản:** `renter-a`.
- **URL:** `http://127.0.0.1:5173/tim-kiem`
- **Thao tác:** lọc khu vực Cầu Giấy; bấm **Xem nhanh** ở tin có ảnh — dùng ←/→ để chuyển ảnh trong gallery; quan sát nhãn **"Ưu đãi"** kèm dòng "đến dd/mm"; tích 2 tin rồi bấm **So sánh & tư vấn**; mở lại khung xem nhanh và bấm **Đặt lịch xem** (chọn trực tuyến).
- **Kết quả mong đợi:** gallery chuyển ảnh bằng bàn phím; nhãn ưu đãi chỉ hiện ở tin owner-a vừa đặt, giá hiển thị **không đổi**; bảng so sánh có ưu/nhược điểm theo dữ liệu; đặt lịch thành công và owner-a nhận yêu cầu xem.

![](demo/buoc-12.png)

---

## Phần 4 — PMS & CRM chạy bằng dữ liệu [DEMO] (owner-a ↔ renter-a)

### Bước 13 — Chat với chủ nhà

- **Tài khoản:** `renter-a` gửi, sau đó `owner-a` trả lời.
- **URL:** renter: `http://127.0.0.1:5173/tin-nhan` (mở hội thoại của phòng); owner: `http://127.0.0.1:5173/chu-nha/hop-thu`
- **Thao tác:** renter bấm **Chat với chủ nhà** từ khung xem nhanh rồi gửi một tin; đổi sang owner-a, mở Hộp thư, trả lời.
- **Kết quả mong đợi:** hai bên thấy tin của nhau, có bộ đếm tin chưa đọc; ngữ cảnh chuyển giao (phòng, nhu cầu, băng tài chính) hiển thị phía trên hội thoại phía chủ nhà — **không** có thu nhập, tỷ lệ, SĐT hay email.

![](demo/buoc-13.png)

### Bước 14 — Hợp đồng [DEMO]: chấp thuận và kích hoạt

- **Tài khoản:** `renter-a` chấp thuận, rồi `owner-a` kích hoạt.
- **URL:** renter: `http://127.0.0.1:5173/nguoi-thue/hop-dong`; owner: `http://127.0.0.1:5173/chu-nha/hop-dong`
- **Thao tác:** renter mở hợp đồng `[DEMO]` ở trạng thái "Đã gửi", đọc văn bản, bấm **Chấp thuận phiên bản 1**; đổi sang owner-a, bấm **Kích hoạt**.
- **Kết quả mong đợi:** renter thấy hợp đồng chờ chấp thuận đúng phiên bản; sau khi kích hoạt, hợp đồng sang "Có hiệu lực" và phòng chuyển thành "Đã thuê" trong kho của owner-a.

![](demo/buoc-14.png)

### Bước 15 — Hóa đơn [DEMO]: báo chuyển tiền, xác nhận thu, biên lai

- **Tài khoản:** `renter-a` báo đã chuyển, rồi `owner-a` xác nhận.
- **URL:** renter: `http://127.0.0.1:5173/nguoi-thue/hoa-don`; owner: `http://127.0.0.1:5173/chu-nha/hoa-don`
- **Thao tác:** renter bấm **Báo đã chuyển** trên hóa đơn `[DEMO]`; owner-a mở Hóa đơn & công nợ, ở phần yêu cầu chuyển tiền bấm **Đã nhận** để xác nhận thu.
- **Kết quả mong đợi:** renter thấy trạng thái "Đã báo chuyển tiền" trước, sau khi chủ nhà xác nhận chuyển "Đã thanh toán" và có biên lai; chủ nhà ghi được thu đúng số còn nợ, không thu vượt.

![](demo/buoc-15.png)

### Bước 16 — Sự cố [DEMO] kèm ảnh (BE-06)

- **Tài khoản:** `renter-a` báo hỏng, rồi `owner-a` xử lý.
- **URL:** renter: `http://127.0.0.1:5173/nguoi-thue/sua-chua`; owner: `http://127.0.0.1:5173/chu-nha/sua-chua`
- **Thao tác:** renter bấm **Báo hỏng**, nhập mô tả `Điều hòa [DEMO] chạy tiếng ồn`, đính kèm 1–2 ảnh, mức "Bình thường", gửi; owner-a mở Sửa chữa, xem ảnh trong ticket, lần lượt bấm **Phân công** → **Bắt đầu xử lý** → **Đã xử lý**.
- **Kết quả mong đợi:** ticket tạo thành công, tối đa 5 ảnh được tải sau khi tạo; ảnh sự cố chỉ hai bên xem được; owner-a nhận sự cố mới và đổi được trạng thái; renter thấy cập nhật và có thể đóng hoặc mở lại kèm lý do.

![](demo/buoc-16.png)

---

## Phần 4b — Luồng thuê phòng end-to-end (crawl.md E-09, 08/11/2026)

Hai nhánh bổ sung để quay demo luồng mới (chạy sau Phần 4, cùng DB):

**Nhánh chủ nhà (owner-a ↔ renter-a):**
1. renter-a mở tin owner-a từ tìm theo bộ lọc (`/tim-kiem`) → bấm "Đặt lịch xem": form dùng chung — chọn ngày + khung giờ (Sáng/Chiều/Tối), họ tên và SĐT điền sẵn, ô đồng ý chia sẻ liên hệ. Câu chữ nói rõ đây là thời gian **mong muốn**.
2. Gửi xong: renter-a xem `/nguoi-thue/lich-xem` — trạng thái "Chờ xác nhận"; **chưa thấy SĐT hiện cho chủ nhà**.
3. owner-a mở `/chu-nha/lich-xem` → lịch mới hiện với liên hệ bị ẩn → bấm "Xác nhận" → giờ owner-a thấy tên + SĐT khách.
4. owner-a bấm "Đề xuất giờ khác" → renter-a thấy "Có đề xuất giờ mới" → bấm "Đồng ý giờ mới".
5. owner-a bấm "Hoàn tất" → renter-a bấm "Gửi phản hồi" (1–5 sao).
6. owner-a vào `/chu-nha/lich-xem`... hợp đồng tạo từ lịch: tin `completed` mở PMS → tạo hợp đồng mới — form đã điền sẵn phòng/người thuê (không gõ mã tài khoản). Gửi → renter-a chấp nhận → kích hoạt → ghi số điện nước → hóa đơn → renter-a "Báo đã chuyển" → owner-a xác nhận → phiếu thu.
7. renter-a quay lại `/nguoi-thue/lich-xem` — lịch xem có link "Xem hợp đồng".

**Nhánh tin cào (điều phối, admin-a):**
1. Cần catalog Chợ Tốt (HOMEMATCH_CATALOG_PATH trỏ snapshot cào; trên DB mới). renter-a đặt lịch một tin cào → giao diện nói rõ: "HomeMatch sẽ liên hệ người đăng để xác nhận; đây chưa phải lịch đã chốt".
2. admin-a vào `/quan-tri/dieu-phoi`: hàng đợi lịch với link tin gốc, nút "Xem SĐT khách" (mỗi lần xem ghi audit), các nút xác nhận/từ chối/hoàn tất. Ghi rõ: người điều phối TỰ liên hệ người đăng, không tự động gọi/nhắn.
3. owner-a đăng nhập: không thấy lịch này ở bất kỳ đâu.
4. admin-a xác nhận → hoàn tất; renter-a gửi phản hồi. Tin cào **không** có nút tạo hợp đồng: "Tin cào: hợp đồng ký trực tiếp với người đăng, ngoài hệ thống".

**Nhánh lỗi (minh họa giữa luồng):** chủ nhà đánh dấu phòng hết trong lúc chờ → xác nhận lịch trả 409 `stale_viewing`; khách hủy lịch → mọi thao tác sau trả 409 `viewing_conflict`.

## Phần 5 — Trợ lý AI chủ nhà (owner-a)

### Bước 17 — Viết bài đăng, trang tin công khai, hỏi co-pilot

- **Tài khoản:** `owner-a`.
- **URL:** `http://127.0.0.1:5173/chu-nha/tro-ly`
- **Thao tác:** chọn phòng vừa tải ảnh, yêu cầu **viết bài đăng**, bấm **Sao chép nội dung**; mở link trang tin công khai trong bài (`/tin/{id}`); quay lại hỏi `Vì sao phòng trống lâu?`.
- **Kết quả mong đợi:** bài đăng chỉ dùng dữ liệu tin và có link trang tin công khai; trang `/tin/{id}` xem được không cần đăng nhập, có gallery ảnh và nhãn ưu đãi; co-pilot trả lời "Vì sao phòng trống lâu" dựa trên dữ liệu phòng của owner-a (đề xuất giá cần ít nhất 3 căn tương đương).

![](demo/buoc-17.png)

---

## Phần 6 — Chủ nhà tự đăng ký và luồng duyệt (BE-03)

### Bước 18 — Đăng ký tài khoản chủ nhà mới

- **Tài khoản:** chưa cần (tạo mới `owner-demo`).
- **URL:** `http://127.0.0.1:5173/dang-ky`
- **Thao tác:** chọn radio **Chủ nhà** (hiện ghi chú "Sau khi xác minh email, tài khoản chủ nhà cần quản trị viên duyệt trước khi công khai tin."); điền: Họ và tên `Chủ Demo`, Email `owner-demo@example.com`, Tên đăng nhập `owner-demo`, Mật khẩu `demo-owner-2026`, nhập lại mật khẩu; bấm **Đăng ký**.
- **Kết quả mong đợi:** thông báo xanh "Đã tạo tài khoản, đang chờ xác minh email…"; log máy chủ (Terminal 1) in dòng `DEV-STUB fake delivery … verification_code=…` — đây là mã xác minh giả lập, không có email thật.

![](demo/buoc-18.png)

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

![](demo/buoc-19.png)

### Bước 20 — Chủ nhà chờ duyệt: soạn được nhưng chưa công khai được

- **Tài khoản:** `owner-demo` / `demo-owner-2026`.
- **URL:** `http://127.0.0.1:5173/chu-nha/phong`
- **Thao tác:** đăng nhập; quan sát banner; bấm **Thêm phòng**, điền tối thiểu các ô bắt buộc, lưu tin nháp; thử tìm ô "Công khai tin cho khách tìm thấy".
- **Kết quả mong đợi:** banner cố định trên mọi trang `/chu-nha/*`: "Tài khoản đang chờ quản trị viên duyệt — bạn có thể soạn tin nhưng chưa công khai được."; tạo tin nháp thành công; ô **Công khai bị khóa** kèm giải thích; không có nút nào cho phép công khai.

![](demo/buoc-20.png)

### Bước 21 — Quản trị viên duyệt hồ sơ

- **Tài khoản:** đăng xuất, đăng nhập `admin-a` / `local-admin-a-password`.
- **URL:** `http://127.0.0.1:5173/quan-tri/tai-khoan`
- **Thao tác:** trong khối "Chủ nhà chờ duyệt", thấy hàng `Chủ Demo · owner-demo@example.com · Đã xác minh`; bấm **Duyệt**.
- **Kết quả mong đợi:** hàng biến mất, khối hiện "Không có chủ nhà chờ duyệt."; `owner-demo` được cấp membership chủ nhà và nhận thông báo; (nút **Từ chối** mở hộp nhập lý do bắt buộc 1–500 ký tự — có thể demo thêm bằng tài khoản thứ hai).

![](demo/buoc-21.png)

### Bước 22 — Chủ nhà đã duyệt công khai tin

- **Tài khoản:** `owner-demo`.
- **URL:** `http://127.0.0.1:5173/chu-nha/phong`
- **Thao tác:** đăng nhập lại; bật **Công khai** cho tin nháp; sau đó đăng nhập `renter-a`, mở `http://127.0.0.1:5173/tim-kiem` và lọc khu vực của tin đó.
- **Kết quả mong đợi:** banner chờ duyệt biến mất; bật công khai thành công (không còn lỗi 403 `landlord_not_approved`); `renter-a` tìm thấy tin mới trong bộ lọc.

![](demo/buoc-22.png)

---

## Phần 7 — Quản trị viên: Admin Console (admin-a)

### Bước 23 — Xử lý ticket hỗ trợ (BE-04)

- **Tài khoản:** `admin-a`.
- **URL:** `http://127.0.0.1:5173/quan-tri/ho-tro`
- **Thao tác:** thấy ticket "Chờ xử lý" tạo ở Bước 05; bấm **Nhận xử lý**; lọc theo trạng thái; bấm **Đã giải quyết**, nhập ghi chú `Đã gọi lại và hướng dẫn khách cách xác nhận hồ sơ` và xác nhận; bấm link "phiên" trên bảng.
- **Kết quả mong đợi:** ticket chuyển Chờ xử lý → Đang xử lý → Đã giải quyết (không nhập ghi chú thì hộp không cho gửi); link mở đúng phiên ở `/quan-tri/hoi-thoai`; `renter-a` nhận đúng một thông báo theo mỗi lần đổi trạng thái.

![](demo/buoc-23.png)

### Bước 24 — Hội thoại AI, chuyển giao, vận hành (BE-05) và tự động hóa

- **Tài khoản:** `admin-a`.
- **URL:** `http://127.0.0.1:5173/quan-tri/hoi-thoai` → `/quan-tri/chuyen-giao` → `/quan-tri/van-hanh`
- **Thao tác:** mở phiên của `renter-a` lần đầu; chuyển sang Chuyển giao; mở Vận hành; (tùy chọn) chạy job tay trong terminal: `.venv/bin/python -m backend.manage jobs`.
- **Kết quả mong đợi:**
  - **Hội thoại AI:** transcript đã che SĐT/email; lần mở đầu tiên được ghi audit (mở lại thấy marker đã mở).
  - **Chuyển giao:** tỷ lệ và thời gian phản hồi đầu tiên của từng chủ nhà.
  - **Vận hành:** thẻ **"Chi phí AI ước tính"** hiện dạng `≈ <số> đ (bảng giá ngày dd/mm/yyyy)`; nếu chưa đủ dữ liệu thì hiện "Chưa tính được — thiếu: …", **không bao giờ hiện 0**; "Số liệu tiến trình" và "Bản gợi ý tạo lỗi" (khởi tạo lại được).
  - **Tự động hóa:** job nền chạy 5 phút một lần trong API; chạy tay in JSON kết quả các job và không sinh thông báo trùng (khóa chống trùng).

![](demo/buoc-24.png)

---

## Phần 8 — Kiểm viewport (360 / 768 / 1280 px)

Người quay nên đổi bề rộng cửa sổ (DevTools → Toggle device toolbar) và rà nhanh các màn chính ở ba bề rộng:

| Bề rộng | Màn cần rà | Tiêu chí đạt |
|---|---|---|
| 360 px | `/tro-ly-ai`, `/tim-kiem` (khung xem nhanh), `/chu-nha/khach-tiem-nang`, `/chu-nha/hoa-don`, `/quan-tri/ho-tro` | Không tràn ngang; mọi nút bấm được; bảng có cuộn ngang riêng trong khung, không làm vỡ trang; hộp thoại (lý do duyệt, ghi chú ticket) giữ focus và đóng bằng Escape |
| 768 px | cùng các màn trên | Bố cục hai cột co giãn hợp lý; không có vùng chữ bị cắt |
| 1280 px | toàn bộ kịch bản | Đây là bề rộng quay chính |

**Trạng thái kiểm trên trình duyệt của agent: chưa chạy.** Lý do: môi trường làm việc của agent không có trình duyệt tự động dùng được — cổng trình duyệt của ZCode trả lỗi "Browser is not available in subagent" và máy không có sẵn Playwright/Puppeteer (quy định không cài thêm). Agent đã xác minh phần còn lại của stack ngày 08/10/2026: `setup` (schema v13, 220 phòng), `seed-users`, khởi động uvicorn :8000 và Vite :5173 thành công, đăng nhập `renter-a` qua API trả đúng vai trò. Người quay tự rà viewport theo bảng trên khi quay video; nếu thấy tràn ngang hoặc nút bị che, ghi lại thời điểm (bước) để sửa. Video demo chính thức **chưa quay**.
