# Khảo sát dashboard chủ nhà HubHome (owner/v2) và bổ sung phía người thuê

**Ngày khảo sát:** 03/11/2026. **Mục đích:** Nối tiếp [khảo sát 01/10](khao-sat-hubhome-da-dang-nhap.md) — lần này vượt được điểm chặn đăng nhập chủ nhà, đọc cấu trúc dashboard `/owner/v2` đầy đủ, và kiểm thử được công cụ tài chính theo căn ở phía người thuê.

**Môi trường:** Chrome macOS, điều khiển giao diện thật bằng computer-use (accessibility tree, không dùng cookie/CDP). Hai profile theo phân công của người dùng: profile `Sơn` — phía người thuê; profile `si` (hiển thị `si nas`) — phía chủ nhà. Chỉ ghi tên hiển thị để xác nhận đúng phiên; không đưa email, dữ liệu hồ sơ hay nội dung cá nhân vào tài liệu.

**Phương pháp:** Mở cửa sổ profile `si`, vào hubhome.vn (đã đăng nhập sẵn), chọn "Khu vực chủ nhà" từ menu tài khoản, đọc cấu trúc từng trang bằng cây accessibility. Chỉ quan sát và điều hướng; không tạo tin, không gửi form, không đổi cài đặt. Sổ của tài khoản này đang trống (0 căn, 0 tin) nên mọi số liệu đều là 0 — khảo sát được **cấu trúc và nhãn nghiệp vụ**, không phải hành vi trên dữ liệu thật.

## 1. Kết quả mới so với 01/10

| Hạn chế cũ | Hiện trạng 03/11 |
|---|---|
| Không vào được khu vực chủ nhà (bị chuyển tới trang yêu cầu đăng nhập) | Menu tài khoản trên trang chủ có sẵn mục **"Khu vực chủ nhà"** — một phiên tài khoản truy cập được cả hai vai, mở thẳng `/owner/v2` "Quản trị chủ nhà" |
| Chưa thấy dashboard chủ nhà | Đã đọc đầy đủ sidebar, 8 thẻ KPI, 5 nhóm nội dung tổng quan và 2 trang con |
| Nav công khai chỉ ghi nhận các mục cũ | Trang chủ sau đăng nhập có thêm **"Thiết kế home"** và **"Trở thành partner"** trong điều hướng chính, cùng nút **"Đăng tin"** trên header |

## 2. Cấu trúc dashboard chủ nhà (`/owner/v2`)

**Sidebar "Khu quản trị":**

- **TỔNG QUAN:** Tổng quan · Trợ lý của bạn
- **NGUỒN CUNG:** Tin bất động sản · Tạo tin cho thuê · Marketing tin đăng · Thiết kế home · Căn hộ & phòng
- **VẬN HÀNH THUÊ** (nhãn nhóm) · **KHÁCH HÀNG** (nhãn nhóm)
- Báo cáo & phân tích · **Agent & tự động hóa**
- **CÀI ĐẶT:** Thông báo · Cài đặt
- Kèm link "Xem website người thuê" và nút Đăng xuất.

**Thanh trên cùng:** tiêu đề "Đọc trực tiếp từ sổ của bạn" — bộ lọc chung **Toà nhà** (Tất cả toà nhà) · **Kỳ** (Tháng này) · **Xem với vai trò** (Chủ sở hữu), nút **Tạo nhanh**, banner **"Xác minh ngay"**, nút **"Mở trợ lý"** (co-pilot nổi).

**8 thẻ KPI tổng quan**, mỗi thẻ đều có huy hiệu **"Chất lượng dữ liệu: Đã đối soát"**, nút **"Cách tính"** (giải thích công thức) và nút **"Mở …"** (drill-through tới trang chi tiết): Căn đang có khách · Căn đang thuê (n/total) · Căn trống (sẵn sàng cho thuê) · Phải thu kỳ này (số tiền + số hoá đơn) · Đã thu (tổng đã phân bổ vào hoá đơn) · Công nợ còn lại (gồm phần quá hạn) · Hợp đồng sắp hết hạn (trong 30 ngày tới) · Tin đang hiển thị (n/total tin).

**5 tab nội dung tổng quan:** Tài chính · Tăng trưởng & tin đăng · Vận hành · Khách & lịch xem · Hoạt động & Agent. Trong tab Tài chính:

- "Dòng tiền kỳ này": Phải thu / Đã nhận / Chờ đối soát / Công nợ / **Tiền cọc giữ hộ** / Chi phí vận hành.
- "Theo toà nhà": Phải thu · đã thu · công nợ, trạng thái Đã thu / Công nợ / Chưa tới hạn → "Mở Thu tiền & công nợ".
- "Sức khoẻ dòng tiền" (hiện "chưa đo được").
- "Hợp đồng sắp hết hạn" (cửa sổ 60 ngày) → "Mở Hợp đồng thuê".
- "Việc cần xử lý" — hàng đợi công việc xếp theo "điểm ưu tiên do policy tính", lọc theo: Tất cả / Của tôi / Đội của tôi / Quá hạn / **Chờ phê duyệt** / **Do Agent đề xuất** / Cảnh báo hệ thống.

## 3. Hai trang đã mở chi tiết

### 3.1. Tin bất động sản (NGUỒN CUNG)

Mô tả: "Rao phòng ra thị trường và theo dõi tin nào thực sự ra khách". Bộ đếm theo trạng thái: tổng tin / đang hiển thị / bản nháp / cần cập nhật / bị tạm ẩn. Tab lọc: Tất cả · Đang hiển thị · Bản nháp · **Chờ duyệt** · Tạm ẩn · **Đã cho thuê**. Bộ lọc Tòa nhà / Trạng thái / Sắp xếp (mặc định cập nhật gần nhất), tìm kiếm, đổi dạng danh sách/lưới.

Bảng tin có các cột: **Tin đăng · Căn liên kết · Trạng thái · Nhãn · Chất lượng · Hiệu quả · Cập nhật · Thao tác** — tức tin tách biệt với "căn" trong sổ và có hai trục đánh giá riêng (điểm chất lượng tin, chỉ số hiệu quả/lượt xem). Panel bên: "Chất lượng tin" phân Tốt / Cần cải thiện / Chưa hoàn thiện kèm sắp xếp theo điểm; "Việc cần xử lý"; "**Đề xuất từ Agent**" với chú thích nguyên tắc: *"Agent chỉ đề xuất — sửa tin bằng nút Chỉnh sửa tin trong trang"*.

### 3.2. Agent & tự động hóa

Mô tả nguyên tắc: *"Agent làm việc lặp và chuẩn bị sẵn thao tác; người có thẩm quyền duyệt"*. Module chưa chạy thật; trang liệt kê điều kiện cần để chạy: `agent_runs` (mỗi lượt agent chạy: lúc nào, trên dữ liệu gì, kết quả ra sao) · `agent_suggestions` (từng đề xuất, kèm **mức rủi ro** và **trạng thái duyệt**) · `agent_config` (agent nào bật, chạy lịch nào, được đụng vào gì). Ghi chú hiển thị: *"Khi có dữ liệu thật, agent vẫn chỉ được ĐỀ XUẤT — mọi thay đổi [cần người có thẩm quyền duyệt]"*.

## 4. Liên hệ với HomeMatch

| Quan sát HubHome | Đối chiếu HomeMatch |
|---|---|
| "Agent chỉ đề xuất", đề xuất kèm mức rủi ro + trạng thái duyệt; người có thẩm quyền mới được sửa | Trùng hướng thiết kế hiện có: HITL duyệt shortlist, capability gate, audit. Đây là xác nhận mô hình cùng hướng của sản phẩm tham chiếu |
| Hàng đợi "Việc cần xử lý" có tab "Do Agent đề xuất" và "Chờ phê duyệt", xếp ưu tiên theo policy | HomeMatch có automation jobs + nhãn `verification`/cờ xếp hàng duyệt; có thể học cách gắn nhãn nguồn công việc (người/Agent) ngay ở UI |
| KPI có huy hiệu "Đã đối soát" + nút "Cách tính" | HomeMatch chưa có lớp "chất lượng dữ liệu" hiển thị cho chủ nhà; cân nhắc ghi rõ nguồn số liệu (sổ phòng vs tin đăng) trên PMS |
| Tin tách "Căn liên kết", cột Chất lượng + Hiệu quả | HomeMatch tách room/listing tương tự; chưa có điểm chất lượng tin — ghi nhận là ý tưởng mở rộng, không phải MVP |
| Một phiên dùng được cả vai người thuê và chủ nhà (menu "Khu vực chủ nhà") | HomeMatch hiện tách role cứng theo tài khoản; trải nghiệm chuyển vai nhanh vừa thêm (quick-experience) cho demo khớp hướng này |
| Dashboard đọc "trực tiếp từ sổ" với bộ lọc Toà nhà/Kỳ/Vai trò | HomeMatch PMS đọc ledger theo ownership; mô hình "xem với vai trò" phù hợp khi có manager/staff |

Điểm riêng cần giữ của đề tài: **quản lý duyệt danh sách cá nhân hóa trước khi người thuê thấy** (HubHome chưa có cổng duyệt shortlist tương đương trong phạm vi đã quan sát), engine tổng tháng/tiền vào ở deterministic có giả định công khai, và thực nghiệm so sánh các phương pháp matching (B1/P).

## 5. Bổ sung buổi cùng ngày — phía người thuê (profile `Sơn`, tài khoản hiển thị `2 sss`)

Profile `Sơn` cũng còn phiên đăng nhập hubhome.vn. Không gửi thêm truy vấn tìm kiếm mới; chỉ dùng lại hội thoại có sẵn trong workspace và bấm một quick action. Các kết quả:

**Workspace Trợ lý AI** (`hubhome.vn/tro-ly-ai`) — thanh công cụ như 01/10 (Danh sách căn, Bản đồ, So sánh, Căn đã lưu, Nhu cầu của tôi, Lịch xem phòng, Phòng đã xem) kèm mục mới **"Tìm kiếm nhanh (⌘K)"**. Chat có nút **"Live chat — gặp người cho thuê thật"**, nút **"Đã xử lý qua 3 bước"** (bung các bước agent đã chạy), và cặp nút đánh giá "Câu trả lời hữu ích / chưa hữu ích".

**Kho tin đã có dữ liệu thật** (khác 01/10 khi kho rỗng): agent tìm "Phường An Lạc, 2–10 triệu" → báo chưa có căn khớp đúng phường, **tự nới lên toàn quận Bình Tân kèm giải thích** ("nới ra toàn Bình Tân thì có 1 căn gần nhất"), và khi mô tả căn có trích dẫn điều kiện khớp ("khớp cả 1 điều bạn nêu: ngân sách ≤ 10 triệu") cùng lý do xếp hạng ("cân bằng các mặt, không nổi trội riêng mặt nào"). Agent cũng nêu "trung vị 5 triệu, tính từ **12 tin cùng khu, cùng loại hình**" — cho thấy kho có ít nhất 12 tin trong khu vực.

**Thẻ phòng trong PREVIEW** (thay cho "preview trống" của 01/10): tiêu đề, phường, diện tích 30 m², 1 PN, tiện ích, giá 3.500.000 đ/tháng, **"Ngày chủ tin đăng 22/10/2026"**, trạng thái "Đang cho thuê", nút Lưu căn / So sánh, checkbox đánh giá riêng từng căn **"Tin phù hợp / Tin chưa phù hợp"**, và nhãn tin cậy **"Chưa xác minh"** kèm giải thích đầy đủ ("Chủ nhà chưa nộp giấy tờ sở hữu để HubHome đối chiếu… Chưa có nhãn không có nghĩa là tin kém tin cậy").

**Bản đồ dùng Goong** (không phải OSM/Google): marker giá "3,5 tr", zoom, chế độ vệ tinh, chú giải "Giá (triệu/tháng)".

**Công cụ "Tính tổng chi phí thật" đã hoạt động** — khép lại khoảng trống lớn nhất của 01/10 (A4 chưa trả được phép tính). Kết quả trả về gồm cả khối chat và panel "Phân tích tổng chi phí" trong preview:

- Tổng ước tính **≈ 4,94 triệu/tháng** (1–2 người, 1 xe máy); tách **cố định 4.141.667 đ** (thuê 3.500.000 + cọc phân bổ 291.667 + internet 200.000 + gửi xe 150.000) và **biến đổi ước tính 800.000 đ** (điện nước; giặt sấy/vệ sinh "tuỳ nhu cầu").
- **Tiền vào ban đầu ≈ 7.000.000 đ+** (cọc 1–2 tháng = 3,5–7 triệu "xác minh với chủ nhà" + thuê tháng đầu 3,5 triệu).
- **So sánh mặt bằng**: "Giá thuê đang rẻ hơn mặt bằng: 3,5 triệu so với trung vị 5 triệu, tính từ 12 tin cùng khu, cùng loại hình"; ghi chú "Mình chưa thấy phí quản lý trong dữ liệu".
- Kèm "Mẹo tiết kiệm chi phí" (hỏi giá điện/nước trước khi cọc, thương lượng cọc 1 tháng, dùng giờ thấp điểm), biểu đồ tỷ lệ cố định/biến đổi, và 4 nút hỏi tiếp: "Chi phí khi ở 2 người", "Chi phí theo năm", "So với mặt bằng khu", "So sánh với căn khác".
- Tuyên bố minh bạch hiển thị: *"HubHome Agent chỉ dùng dữ liệu tin đăng, không bịa căn/giá"*; *"Các khoản đánh dấu (*) là ước tính mặt bằng chung — cần xác [minh]"*.

Kiểm chứng số học của HomeMatch cho ca này: 3.500.000 + 291.667 + 200.000 + 150.000 = **4.141.667 đ** và 4.141.667 + 800.000 = **4.941.667 đ ≈ 4,94 triệu** — khớp với con số HubHome hiển thị. Cọc phân bổ 291.667 đ đúng bằng 3.500.000/12 (cọc 1 tháng chia 12 tháng thuê).

## 6. Giới hạn và việc còn lại

1. Sổ chủ nhà trống nên chỉ đọc được cấu trúc rỗng; hành vi thực (tạo tin, duyệt, hoá đơn, công nợ) chưa kiểm thử. Không tự tạo dữ liệu lên hệ thống thật.
2. Chưa mở: Trợ lý của bạn, Marketing tin đăng, Thiết kế home, Căn hộ & phòng, Báo cáo & phân tích, Thông báo, Cài đặt và các trang VẬN HÀNH THUÊ / KHÁCH HÀNG (nhãn nhóm có thể có trang riêng).
3. Phía người thuê (profile `Sơn`) đã xác nhận phiên và kiểm thử được công cụ tài chính trên 1 căn duy nhất hiện có; chưa kiểm thử: trang chi tiết phòng đầy đủ (mở bằng nút ↗), luồng đặt lịch xem, lưu/so sánh trên nhiều căn, "Nhu cầu của tôi", "Phòng đã xem", "Thiết kế home" và "Trở thành partner". Cần thêm tin đăng hoặc người dùng chỉ định để kiểm thử tiếp; không tự đăng dữ liệu mẫu lên hệ thống thật.
4. Toàn bộ quan sát là nội dung giao diện hiển thị; không suy ra cấu trúc backend thật của HubHome (tên `agent_runs`/`agent_suggestions`/`agent_config` là nhãn UI tự mô tả, chưa xác minh).
