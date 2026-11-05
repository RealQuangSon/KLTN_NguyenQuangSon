# Khảo sát giao diện và UX flow HubHome — đối chiếu khoảng trống HomeMatch

**Ngày khảo sát:** 03/11/2026 (bổ sung cho [khảo sát chức năng 03/11](khao-sat-hubhome-dashboard-chu-nha.md) và [khảo sát 01/10](khao-sat-hubhome-da-dang-nhap.md)). **Phạm vi:** phía người thuê trên profile `Sơn` (tài khoản hiển thị `2 sss`), workspace Trợ lý AI với 1 căn thật trong kho (`hh-2661998730`, Bình Tân, 3,5 triệu/tháng). **Phương pháp:** điều khiển giao diện thật bằng computer-use, đọc cây accessibility từng trạng thái; chỉ quan sát và mở view, không gửi thêm truy vấn mới, không đặt lịch, không lưu/so sánh. Toàn bộ nhãn UI được chép nguyên văn; không suy công nghệ backend.

## 1. Mô hình layout tổng thể — "một workspace, ba view đồng bộ"

Workspace `/tro-ly-ai` giữ nguyên URL cho mọi chế độ: **chat (trái) + preview panel (phải)** với splitter kéo được. Preview luân chuyển giữa: bản đồ (Goong) → danh sách căn → thẻ phòng đơn → "Phân tích tổng chi phí" → chi tiết phòng đầy đủ. Toolbar có bộ đếm trực tiếp: "So sánh 0 căn", "Căn đã lưu (0)". Không có điều hướng trang — mọi thứ xảy ra trong 1 khung, kèm nút "Toàn màn hình workspace".

**Đối chiếu HomeMatch:** HomeMatch tách thành nhiều trang (Tìm phòng, Tìm theo bộ lọc, trang tin công khai) và mất ngữ cảnh khi nhảy trang. HubHome giữ hội thoại + kết quả + chi tiết trong một khung duy nhất — người dùng không bao giờ "rời" cuộc tư vấn.

## 2. Chat ↔ kết quả đồng bộ hai chiều

- Mỗi câu trả lời agent có chip dẫn tới view tương ứng vừa mở: "↗ Đã mở Bản đồ trong workspace", "↗ Đã mở Phân tích chi phí trong workspace" — bấm là preview nhảy đúng view.
- Nút **"Đã xử lý qua 3 bước"** bung được các bước agent đã chạy (minh bạch quy trình).
- Đánh giá từng câu trả lời: "Câu trả lời hữu ích / chưa hữu ích".
- **Ngữ cảnh căn gắn vào chat:** khi mở chi tiết phòng, phía trên ô nhập hiện chip tên căn kèm nút **"Bỏ ngữ cảnh căn (hỏi việc khác)"**; quick-replies đổi theo ngữ cảnh: "Tính tổng chi phí căn này" · "Chính sách thuê (cọc, nội thất)" · "Còn căn nào rẻ hơn khu này?" · "Gợi ý căn tương tự" · "Đặt lịch xem" · "Xem ảnh" · "Tổng chi phí thật?".
- Quick-replies trả lời tự do cũng theo ngữ cảnh: "Đặt lịch xem phòng", "So với 2 căn nổi bật còn lại", "Tính tổng chi phí thật".

**Đối chiếu HomeMatch:** chat HomeMatch có thẻ mô phỏng vay và nút "Xem danh sách gợi ý" (cuộn tới bảng kết quả) nhưng **không có chip ngữ cảnh căn, không có quick-replies theo căn, không bung được các bước agent**. Đề tài có checkpoint và reasoning log phía backend nhưng chưa lộ ra UI.

## 3. Danh sách căn — chip lọc sinh từ hội thoại

Preview dạng lưới/danh sách (đổi được), đếm kết quả, sắp xếp "Phù hợp nhất". Điểm đáng học:

- **Chip lọc thông minh đếm sẵn:** "🔥 Dưới 9 triệu (1)", "Máy giặt riêng (1)", "Diện tích > 25m² (1)" — sinh từ tiêu chí người dùng vừa nói, kèm số lượng.
- Thẻ phòng có: nhãn **"NỔI BẬT"**, giá, vị trí tới phường, 30 m², 1 PN, loại ("căn hộ mini"), **lời giải thích xếp hạng từng căn** ("cân bằng các mặt, không nổi trội riêng mặt nào"), nhãn tin cậy **"Chưa xác minh"** kèm tooltip nguyên văn ("Chủ nhà chưa nộp giấy tờ sở hữu để HubHome đối chiếu. Khi đi xem, đề nghị xem sổ hồng hoặc hợp đồng uỷ quyền bản gốc. Chưa có nhãn không có nghĩa là tin kém tin cậy."), tiện ích **ghi nguồn** ("Máy lạnh — theo tin đăng"), "Ngày chủ tin đăng 22/10/2026", trạng thái "Đang cho thuê", và **đánh giá riêng từng căn "Tin phù hợp / Tin chưa phù hợp"**.
- Nút "Gợi ý thêm căn" và disclaimer lặp: "HubHome Agent chỉ dùng dữ liệu tin đăng, không bịa căn/giá/…".

**Đối chiếu HomeMatch:** thẻ phòng HomeMatch có giá/tổng tháng, tiện ích, khu vực — nhưng **không có lời giải thích vì sao căn này được đề xuất cho người dùng này**, không nhãn nguồn tiện ích, không nhãn tin cậy, và không có kênh feedback từng căn (đề tài đang cần nhãn relevance từ người dùng cho phần thực nghiệm — HubHome đã có sẵn pattern này).

## 4. Chi tiết phòng (mở trong preview, không rời workspace)

Cấu trúc: gallery ảnh (pager "1/1") → loại "CĂN HỘ MINI" → tiêu đề → huy hiệu khớp **"Gần đúng"** (mức khớp với nhu cầu) → nhãn tin cậy → vị trí + nút "Xem trên bản đồ" → giá → thuộc tính (30 m², căn hộ mini, 1 phòng ngủ, **Tầng: chưa có thông tin, Hướng: chưa có thông tin**) → hàng CTA: **Đặt lịch xem phòng · Xem đường đi · Lưu căn này · So sánh · Chia sẻ** → các section: "Tổng quan" (ghi thẳng "Tin đăng không có phần mô tả."), "Vị trí & khu vực" (cảnh báo "Toạ độ tin đăng hiện chỉ tới cấp quận nên vị trí trên bản đồ…"), "Tiện ích trong phòng" (10 mục + "Tiện ích theo tin đăng — nên xác minh lại khi đi xem."), "Điều khoản thuê" (Giá/Diện tích/Cọc/Kỳ thanh toán/Thời hạn — mỗi trường trống ghi "chưa có thông tin"), Mã tin.

Khối **"Chi phí theo tin đăng"**: bảng Tiền thuê/Điện/Nước/Phí dịch vụ/Gửi xe — các khoản tin không nêu ghi **"tin chưa nêu"**, tổng "Cố định đã biết …/tháng", chú "(*) ước tính tham khảo — xác nhận lại với chủ nhà", nút **"Phân tích chi phí đầy đủ →"** dẫn sang view phân tích (mục trước). Cuối trang: bản đồ Goong nhúng + "Mở bản đồ →" + "Xem đường đi" + disclaimer "HubHome chỉ cung cấp thông tin tham khảo. Vui lòng kiểm tra …".

**Đối chiếu HomeMatch:** trang tin công khai HomeMatch có gallery, thuộc tính, `addressLine`, cảnh báo vị trí gần đúng (circle uncertainty) — tương đương hướng đi. Nhưng HomeMatch **hiển thị ít khi thiếu dữ liệu** (trường None thường bị ẩn), chưa có khối "chi phí theo tin đăng + phần chưa nêu", chưa có nút "Phân tích chi phí đầy đủ" ngay trên trang tin, chưa có nhãn khớp "Gần đúng/Chính xác", chưa có "Xem đường đi".

## 5. Phân tích tổng chi phí (chat + panel kép)

Chat trả tóm tắt 4 gạch đầu dòng; preview mở panel đầy đủ 3 mục (cố định/biến đổi/cọc & ban đầu), tổng ≈ 4,94 tr/tháng, tiền vào ban đầu ≈ 7 triệu+, **so sánh trung vị thị trường** ("rẻ hơn mặt bằng: 3,5 triệu so với trung vị 5 triệu, từ 12 tin cùng khu, cùng loại hình"), "Mẹo tiết kiệm chi phí", biểu đồ tỷ lệ, 4 nút hỏi tiếp, disclaimer "* là ước tính mặt bằng chung" + "Agent chỉ dùng dữ liệu tin đăng, không bịa căn/giá". Đã kiểm chứng số học khớp 100% (4.141.667 + 800.000 = 4.941.667).

**Đối chiếu HomeMatch:** engine `costs.py` tính cùng lớp phép tính (tổng tháng, tiền vào ở) nhưng **chưa có so sánh trung vị thị trường theo khu+loại**, chưa có "mẹo tiết kiệm", chưa có nút hỏi tiếp theo ngữ cảnh chi phí. Đây là khoảng trống rõ nhất về UX tài chính.

## 6. Sidebar chủ nhà — các pattern đáng mượn (từ buổi sáng)

- 8 thẻ KPI đều có huy hiệu **"Chất lượng dữ liệu: Đã đối soát"** + nút **"Cách tính"** (giải thích công thức) + drill-through "Mở …".
- Hàng đợi "Việc cần xử lý" xếp theo "điểm ưu tiên do policy tính", lọc gồm tab **"Do Agent đề xuất"** và "Chờ phê duyệt".
- Trang tin: điểm **Chất lượng tin** (Tốt/Cần cải thiện/Chưa hoàn thiện), cột Hiệu quả, panel **"Đề xuất từ Agent"** với nguyên tắc "Agent chỉ đề xuất — sửa tin bằng nút Chỉnh sửa".
- Trang "Agent & tự động hóa" liệt kê điều kiện chạy thật: `agent_runs` / `agent_suggestions` (mức rủi ro + trạng thái duyệt) / `agent_config`; nguyên tắc "agent vẫn chỉ được ĐỀ XUẤT".

## 7. Bảng khoảng trống đề xuất cho HomeMatch

Nhóm theo mức ưu tiên để đưa vào kế hoạch (chưa có mã FR/task — cần đưa vào `yeu-cau-san-pham` trước khi làm):

| # | Khoảng trống | Pattern HubHome | Nơi gắn vào HomeMatch |
|---|---|---|---|
| 1 | ~~Giải thích đề xuất từng căn~~ **ĐÃ CÓ SẴN** (cập nhật 03/11 sau audit): RoomCard hiển thị `reasons` + tradeoffs + cần xác minh + nguồn + thuật toán, chi tiết hơn HubHome | HubHome: "Vì sao mình đưa căn này ra", huy hiệu "Gần đúng" | HomeMatch đã thể hiện ở `RoomCard` (`Shared.tsx`); có thể bổ sung huy hiệu mức khớp sau |
| 2 | Feedback từng căn "phù hợp/chưa phù hợp" | checkbox trên thẻ + trên chi tiết | phục vụ trực tiếp mục tiêu thực nghiệm relevance của đề tài |
| 3 | Ngữ cảnh căn trong chat + quick-replies theo căn | chip tên căn + "Bỏ ngữ cảnh căn" | `RenterWorkspace` sendText kèm `room_id` |
| 4 | So sánh giá với trung vị khu vực | "trung vị 5 triệu từ 12 tin cùng khu, cùng loại" | mở rộng `costs.py` + seed catalog đã có đủ dữ liệu |
| 5 | Trung thực với dữ liệu thiếu | "chưa có thông tin", "tin chưa nêu", "theo tin đăng — nên xác minh" | đúng tinh thần docs hiện tại ("không ghi đạt nếu chưa có bằng chứng") — hiển thị thay vì ẩn |
| 6 | Nhãn tin cậy tin đăng + tooltip giải thích | "Chưa xác minh" + giải thích nguyên văn | cần trạng thái xác minh chủ nhà (HomeMatch đã có landlord_status, mở rộng lên tin) |
| 7 | Khối chi phí theo tin ngay trên chi tiết phòng | bảng thuê/điện/nước/phí + "Phân tích chi phí đầy đủ →" | `PublicListing` |
| 8 | Chip lọc sinh từ hội thoại kèm số lượng | "🔥 Dưới 9 triệu (1)" | đồng bộ profile ↔ SearchPage |
| 9 | Bung các bước agent đã chạy | "Đã xử lý qua 3 bước" | HomeMatch có checkpoint/langgraph events — lộ ra UI |
| 10 | KPI chủ nhà có "Cách tính" + nhãn chất lượng dữ liệu | huy hiệu "Đã đối soát" | PMS dashboard HomeMatch |
| 11 | Hàng đợi việc với nguồn người/Agent + ưu tiên policy | "Do Agent đề xuất", "Chờ phê duyệt" | automation jobs HomeMatch đã có nền |
| 12 | Điểm chất lượng tin đăng cho chủ nhà | Tốt/Cần cải thiện/Chưa hoàn thiện | landlord review flow |

**Giữ điểm khác biệt của đề tài (không copy):** quản lý duyệt shortlist cá nhân hoá trước khi người thuê thấy (HubHome không có cổng duyệt tương đương), engine tài chính deterministic có giả định công khai + kiểm chứng oracle độc lập, và thực nghiệm so sánh phương pháp matching. Vị trí công khai là vòng sai số riêng tư của HomeMatch là thiết kế riêng (HubHome dùng toạ độ cấp quận + cảnh báo tương đương nhưng không có vòng sai số).

## 8. Giới hạn

1. Chỉ 1 căn trong kho nên chưa thấy UX khi nhiều kết quả (phân trang, so sánh bảng, cluster bản đồ); các nút So sánh/Căn đã lưu đang disabled ở 0 căn.
2. Chưa mở: đặt lịch xem (không gửi dữ liệu thật), "Nhu cầu của tôi", "Phòng đã xem", "Lịch sử trò chuyện", "Tìm kiếm nhanh ⌘K", "Thiết kế home", "Trở thành partner", "Live chat" thật, và các trang chủ nhà còn lại (Marketing, Căn hộ & phòng, Báo cáo & phân tích, Trợ lý của bạn, Tạo tin).
3. Toàn bộ là nhãn giao diện; không suy cấu trúc backend thật. Ảnh/giao diện HubHome chỉ dùng làm bằng chứng khảo sát, không tái sử dụng làm tài sản trong sản phẩm HomeMatch.

## 9. Ca khảo sát C1 — truy vấn "Tìm nhà trọ 4m một tháng gần HUST" (03/11)

Gửi bằng giao diện hội thoại mới (profile `Sơn`). Trước khi gửi, giao diện chat ban đầu gồm: heading "Bạn đang tìm một **nơi ở** như thế nào?", textarea "Nhu cầu tìm phòng", nút "Thêm ảnh hoặc nói", popup "Tìm nhanh", checkbox "Dùng vị trí của tôi (Gần tôi)", checkbox "Nhập bằng giọng nói", nút Gửi (khóa khi trống), 4 câu hỏi mẫu (sinh theo ngữ cảnh khu vực đã dùng: Bình Tân), tagline "Thông tin thật · Giá tốt · An tâm thuê", disclaimer "Agent có thể mắc lỗi. Vui lòng kiểm tra…", footer Cẩm nang / Lịch sử / Hướng dẫn sử dụng.

Cách agent chạy cho truy vấn "gần HUST" (kho không có phòng Hà Nội):

1. **Diễn giải địa điểm tham chiếu rồi nói ra:** "Mình hiểu mốc là *Hust Shop, 7a, 169/6, đường Hoàng Mai*" — geocode "HUST" thành một POI cụ thể và hiện cho người dùng xác nhận (ở ca này hiểu lệch thành quán tên Hust Shop ở Hoàng Mai thay vì trường Bách Khoa; người dùng thấy ngay và có nút "Chỉnh sửa" trên chip nhu cầu).
2. **Báo rỗng trung thực kèm đã hiểu gì:** "Kho HubHome hiện chưa có căn khớp mức tối đa 4 triệu/tháng ở Hoàng Mai, gần HUST." — nhắc lại cả ba tiêu chí đã parse (loại, giá tối đa, khu vực+lá cờ địa điểm).
3. **Đề nghị nới đúng một tiêu chí:** liệt kê 3 lựa chọn — *ngân sách / khu vực / khoảng cách tới HUST* — kèm cam kết "Mình chỉ đổi một tiêu chí để tìm lại cho sát nhu cầu."
4. **"Đã xử lý qua 5 bước"** bung ra pipeline đa agent: *Định tuyến câu hỏi → Chuyên viên tìm căn → Tìm căn khớp tiêu chí (0 căn) → Ghim bản đồ — dùng nguyên kết quả tìm (0 căn)* (còn 1-2 bước chỉ hiện icon trong cây accessibility).
5. Xung quanh câu trả lời: chip nhu cầu draft "Hoàng Mai" + "Chỉnh sửa", đánh giá "hữu ích/chưa hữu ích", quick-replies theo ngữ cảnh rỗng ("Tính tổng chi phí", "Giá có hớ không?", "Lọc thêm tiện ích", "Gợi ý căn tương tự"), header chat có badge nguồn "dữ liệu tin đăng HubHome". Preview panel 0 kết quả: chỉ placeholder, không vẽ bản đồ rỗng.

**Trạng thái đã nhân bản vào HomeMatch (03/11, cùng buổi):** dòng đếm "Kết quả đã duyệt: N căn" trên danh sách; khối "NỚI MỘT TIÊU CHÍ ĐỂ TÌM LẠI" với 3 nút điền câu nhắn vào chat (không tự gửi, giữ nguyên tắc "không tự nới điều kiện cứng"); badge "Chỉ dùng tin đã duyệt trong kho HomeMatch" trên header chat. Chưa nhân bản (cần backend): bung pipeline theo từng bước, geocode POI + xác nhận địa điểm, đánh giá từng câu trả lời, quick-replies theo ngữ cảnh căn.

## 10. Trạng thái nhân bản cập nhật 03/11 (buổi chiều)

- **Bản đồ Goong đã hoạt động thật trên HomeMatch**: key loại Map tiles hợp lệ; Goong hiện chỉ cung cấp vector style (MapLibre GL) nên engine đổi từ Leaflet sang `maplibre-gl`; marker pill giá "2,4 tr" như tham chiếu. Lỗi "Worker failed to load" (MapLibre v6 tách worker, Vite pre-bundle làm URL đứt) được khắc phục bằng plugin vite phục vụ/emit `maplibre-gl-worker.mjs` tại URL cố định + `setWorkerUrl`. Bằng chứng: attribution "© Goong Maps" render, 100/100 điểm lấy mẫu canvas có pixel nội dung, không rơi nhánh fallback OSM (trang `/tin/synthetic-room-042`); build emit worker vào `dist/` (519 KB). Fallback OSM giữ nguyên cho trường hợp thiếu key/lỗi style (kèm lý do trong hint).
- **Luồng "đăng nhập là chat được"**: đã bỏ màn chặn "Bắt đầu phiên tư vấn"; `/tro-ly-ai` hiện composer "Bạn đang tìm một nơi ở như thế nào?" — gửi câu đầu tự tạo phiên + gửi luôn; đăng nhập/chuyển trải nghiệm giữ khóa phiên từng tài khoản (`session-storage.ts`), đăng xuất mới xoá sạch. Đã verify live: đăng nhập renter-a → gõ "Tìm nhà trọ 4 triệu một tháng gần HUST" → agent hỏi làm rõ ngân sách/số người ngay trong phiên mới tạo.

## 11. Re-skin theo token gốc của hubhome.vn (03/11, buổi tối)

Trích **trực tiếp từ CSS production** của hubhome.vn (5 file `/_next/static/chunks/*.css`) thay vì suy đoán: font **Inter** (next/font 100–900), nền `#f7f8fa`, thẻ trắng bo 16px viền `#e5eaf0` bóng `0 1px 2px #14213d0f`, chữ navy `#14213d`/phụ `#536278`/mờ `#5f6f85`, **cam #ff7518** (đậm #c74600, chữ-cam-an-toàn #ba4100, nền nhạt #fff1e6), lam #175cd3/#eff5ff, lục #157347/#eaf7ef, đỏ #b42318/#fff0ee, cỡ chữ compact 14/12.5/12px.

Áp lên HomeMatch (giữ logo + minh họa riêng): toàn bộ token `:root` và literal màu đổi sang bảng trên; font Inter qua Google Fonts; thẻ thêm bóng mềm; CTA đăng nhập/đăng ký gradient cam như nút chính; welcome panel gradient `#fff7ed→#fff`; bubble chat người dùng nền cam (giống HubHome). Lưu ý AA: chữ trắng trên #ff7518 chỉ 2.56:1 — HubHome cũng dùng vậy (ưu tiên giống thị giác); chữ cam cỡ nhỏ dùng #ba4100 (4.8:1). 93/93 test + build sạch.

## 12. Bỏ form khỏi luồng chính — chat xong là có kết quả (03/11)

Điểm khác UX lớn cuối cùng: HomeMatch cũ chặn kết quả sau form "Hồ sơ nhu cầu" + nút "Xác nhận". Đã đổi theo tham chiếu: **cột phải mặc định là kết quả preview**; gửi tin nhắn xong, nếu nháp đủ tối thiểu (thành phố + ngân sách) frontend **tự xác nhận nháp** (`profileFromDraft` + kịch bản mặc định như form) để vòng tìm tự chạy — lỗi thiếu dữ liệu bỏ qua im lặng vì trợ lý sẽ hỏi thêm. Form chuyển thành nút **"Nhu cầu của tôi"** gập/mở ở đầu cột phải; auto-confirm chỉ chạy khi chưa có hồ sơ xác nhận và mỗi draft_revision một lần. Đã verify live: gửi "căn hộ 1PN Hà Nội tổng tháng 8 triệu" → agent hỏi làm rõ → Journey nhảy thẳng bước "Quản lý kiểm tra" (nháp cũ bị thay bằng nhu cầu mới qua vòng auto-confirm kế tiếp), không có form nào chặn. Manager duyệt vẫn là bước backend giữ nguyên (khác biệt cốt lõi của đề tài).

## 13. Nhân bản bố cục trả lời 4 phần (04/11 — khảo sát lại không cần profile)

Khảo sát lại `hubhome.vn` bằng trình duyệt tích hợp **phiên mới, không đăng nhập**: trang `/tro-ly-ai` cho chat ẩn danh; gửi câu hỏi có kết quả thì giao diện trả lời chia **4 phần**:

1. **Sidebar icon mảnh** (~64px): home, tìm kiếm, chat, lịch sử, preview, pin bản đồ, so sánh, đã lưu; dưới cùng là tài khoản.
2. **Cột chat** cố định: header mascot + nguồn dữ liệu; bubble trợ lý xám nhạt / bubble người dùng cam; "Đã xử lý qua N bước", đánh giá 👍👎 từng câu; composer bo tròn + nút gửi tròn cam; quick-replies dạng pill dưới composer; banner mời đăng nhập khi ẩn danh hết lượt.
3. **Bản đồ**: chip "N căn phù hợp", marker pill giá, legend giá (triệu/tháng), attribution Goong.
4. **Danh sách đề xuất**: header "SẮP XẾP" + "Phù hợp nhất ▾", lưới thẻ phòng 2 cột, nút "Xem tất cả N căn".

Trạng thái chưa có phiên là màn chào giữa trang: mascot glow + heading "Bạn đang tìm một **nơi ở** như thế nào?" (chữ cam giữa câu) + composer lớn viền cam + 4 thẻ câu hỏi mẫu + dòng cam kết "Thông tin thật · Giá tốt · An tâm thuê".

**Đã nhân bản vào HomeMatch (04/11):** `/tro-ly-ai` đổi sang bố cục `icon-rail | chat | map | đề xuất` (`agent-shell` trong `RenterWorkspace.tsx`, rail trong `App.tsx` — mỗi icon dẫn tới trang thật của app); khung preview có header "PREVIEW" + nút bật/tắt bản đồ, danh sách, toàn màn hình; "Nhu cầu của tôi" là nút đè lên cột đề xuất; đang xử lý hiện bộ khung thẻ + mascot vòng nét đứt; màn chào giữa trang như tham chiếu (mascot SVG vẽ riêng, không dùng tài sản của HubHome); quick-replies 3 pill gửi thật ("Tính tổng chi phí", "Gợi ý căn tương tự", "Đổi khu vực"); đánh giá 👍👎 **chỉ lưu trên máy** (localStorage, ghi rõ trong tooltip); chat **lưu lịch sử lượt theo phiên** vào sessionStorage — reload còn nguyên hội thoại (đã verify live kèm run được chủ nhà duyệt: map Goong + 2 pill giá, danh sách 2 căn). Trang đăng nhập chỉnh theo tham chiếu: nút chính **navy đậm**, cảnh phố thành **thẻ bo góc chôn trong nền trắng** kèm tagline đè góc dưới trái. 93/93 test + `tsc` + build sạch.

**Chưa nhân bản (cần backend hoặc cố ý giữ khác biệt):** "Đã xử lý qua N bước" (cần lộ pipeline events), geocode POI + xác nhận địa điểm, quick-replies theo ngữ cảnh từng căn, chip lọc sinh từ hội thoại kèm số lượng, banner "Đăng nhập với Google" (HomeMatch dùng seed local có điều kiện), "Live chat" người thật (không có tích hợp thật — không giả lập theo nguyên tắc đề tài), mascot/logo (giữ tài sản riêng).

## 14. Gói "agent thông minh hơn" + trang cá nhân (04/11, buổi tối) — chỉ localhost

Triển khai phần còn thiếu của danh sách tính năng tham chiếu, không VPS/Docker, không dịch vụ ngoài:

- **Kịch bản kho rỗng trong khung chat** (trước đây chỉ hiện ở khung preview): máy chủ trả thêm `diagnostics_summary` (scanned/kept/rejected/verification — chỉ số tổng hợp, không có danh tính phòng) và `steps` trong payload `/sessions/{id}/results` (`service._transparency`). Khi run về `no_match`/`needs_verification`, chat tự nói lại nhu cầu đã nắm, nêu tiêu chí loại nhiều nhất kèm số tin, rồi đề nghị **nới đúng MỘT tiêu chí** do người dùng chọn — không tự nới (đã verify live: "500 nghìn một tháng ở TP.HCM" → "quét 208 tin... bị loại chủ yếu vì thành phố (95), trần tổng tháng (57), loại phòng (38); riêng 12 tin chờ xác minh").
- **"Đã xử lý qua N bước"**: bung được 4 bước thật (quét → lọc cứng với số liệu → xếp hạng theo phương pháp → trạng thái hiện tại) từ dữ liệu run, không bịa.
- **Đọc tiền thuê dưới 1 triệu**: tách `rent_budget_hint` (hiểu "500 nghìn"/"800k") khỏi `budget_hint` nghiêm ngặt — oracle vay LP15 đã đóng băng quy ước "nghìn không đọc làm tiền vay", nên kịch bản vay giữ nguyên parser cũ; trước đây trần 500k bị bỏ qua im lặng khiến auto-confirm không chạy.
- **Nhập giọng nói thật**: nút mic Web Speech API (`VoiceInput`, vi-VN) ở cả hai composer; trình duyệt không hỗ trợ thì nói thẳng thay vì giả trạng thái. "Thêm ảnh" của tham chiếu không làm vì không có pipeline ảnh thật.
- **Trang cá nhân `/nguoi-thue/da-luu`**: "Đã lưu" (bảng `hm_room_saves` mới, migration 15; nút Lưu ♥ trên thẻ phòng, tối ưu + hoàn tác khi lỗi) và "Đã xem" (đọc từ `hm_room_views` vốn đã ghi khi mở chi tiết tin). Capability mới `saved:read/write`, `viewed:read` chỉ cho người thuê. Sidebar + rail có mục "Đã lưu & đã xem".
- **Đã có từ trước, khớp danh sách tham chiếu**: đặt lịch xem + nhắc lịch (automation), hợp đồng/hóa đơn/sửa chữa (PMS hai phía), live-chat handover ("Chat với chủ nhà" → Inbox mang ngữ cảnh phiên), 5 luồng automation thật (nhắc lịch xem, tái kết nối lead, nhắc thanh toán, nhắc gia hạn, dọn transcript).
- **Menu tài khoản + trang chủ khi đã đăng nhập** (04/11, muộn): avatar cuối rail mở popover kiểu tham chiếu (menu tài khoản có hồ sơ/thiết lập + đăng xuất) — "Đã lưu & đã xem", "Tài khoản & bảo mật", "Về trang chủ", khối đổi trải nghiệm seed (tự ẩn khi public) và **Đăng xuất bằng chữ**; trước đây nút đăng xuất chỉ là icon mờ cuối rail. `/` không còn ép chuyển hướng khi đã đăng nhập: landing vẫn mở được, nút auth đổi thành "Mở trợ lý", nhu cầu gõ ở landing đi thẳng vào phiên trợ lý đang mở (`pendingNeed` + điều hướng). Khớp quan sát HubHome: "Menu tài khoản có hồ sơ/thiết lập, khu vực người thuê và đăng xuất".

## 15. Đồng bộ sidebar từng vai với bảng màu tham chiếu (04/11, tối)

Đã soi từng trang trong sidebar của cả ba vai trên trình duyệt và quét toàn bộ `styles.css`:

- **Quét hết màu ấm cũ còn sót** (~30 giá trị hex: `#f4f1ee`, `#e8e3e0`, `#7b6e65`, `#907a6b`, `#e1dcd8`…) đổi sang token HubHome (xám mát `#f2f4f8`/`#e5eaf0`, chữ phụ `#66788f`, cam an toàn `#ba4100`); khối vẽ cảnh hoàng hôn trang đăng nhập được bảo toàn nguyên vẹn.
- **Dashboard chủ nhà**: thẻ KPI trước đây bị cắt số ("3.280.00đ") do cột 170px — đổi `stat-grid` sang `minmax(215px,1fr)`, số về 19px + được phép xuống dòng; giờ hiển thị đủ "3.280.000 ₫ / 3.310.000 ₫" trên lưới 4 cột.
- **Toggle công khai tin** nền nâu cũ → xám mát, bật = cam tham chiếu; **hội thoại chủ nhà** (Tin nhắn): bubble bên mình đổi từ cam nhạt sang **cam đậm chữ trắng** đồng bộ màn trợ lý.
- Các trang đã soi và đạt chuẩn cùng bảng màu: renter (Tin nhắn, Hợp đồng, Hóa đơn, Đã lưu & đã xem, Tài khoản), chủ nhà (Tổng quan, Duyệt gợi ý, Phòng & tin, Trợ lý AI), admin (Giám sát hội thoại AI). Cẩm nang + Lịch xem dùng chung panel/heading đã đồng bộ từ trước.
- Kiểm chứng: frontend 96/96 test pass, `tsc` + build sạch; verify trực quan từng trang bằng ảnh chụp.

## 16. Auto-publish — bỏ người ra khỏi đường tới kết quả (04/11, đêm)

Phản hồi của người dùng: người thuê quan trọng là tìm phòng, bước "có người ngồi duyệt nhu cầu" tốn nhân lực và thời gian chờ. Giải pháp **không xoá cổng duyệt** (vẫn là điểm khác biệt HITL của đề tài) mà chuyển nó ra khỏi đường tới kết quả:

- **`HOMEMATCH_AUTO_PUBLISH=1` (mặc định TẮT)**: khi bật, run có phòng đủ điều kiện được **công bố ngay** cho người thuê — `_generate` gọi `_auto_publish`, tái dùng nguyên luồng duyệt hiện có (graph resume, sổ `hm_run_reviews`, thông báo) nhưng quyết định do hệ thống ghi, `reason` ghi rõ "Tự công bố theo chế độ auto-publish…, chủ nhà thẩm định sau" — sổ audit không bịa "chủ nhà đã duyệt tay".
- **Không duyệt hồi tố**: các run tạo trước khi bật flag vẫn nằm lại hàng đợi cho duyệt tay như cũ; chỉ run mới được tự công bố (test khẳng định `drafts(owner) == []` sau luồng auto).
- **Copy đồng bộ**: `/health` trả thêm `auto_publish`; câu trả lời của trợ lý và khung chờ đổi thành "Kết quả sẽ tự hiện… trong chốc lát (chế độ tự công bố — chủ nhà vẫn được ghi nhận thẩm định sau)".
- **Verify live** (backend chạy `HOMEMATCH_AUTO_PUBLISH=1 HOMEMATCH_JOBS_INTERVAL_SECONDS=10`): phiên mới hỏi "phòng trọ dưới 4 triệu ở TP.HCM…" → **"5 căn phù hợp" hiện ở bản đồ + danh sách sau ~25 giây, không có bước duyệt**; ca kho rỗng vẫn chạy kịch bản nới một tiêu chí như thường.
- Kiểm chứng: thêm `test_auto_publish_puts_rooms_in_front_of_the_renter_without_a_human` (published ngay + sổ audit có lý do tự động + hàng đợi trống); full pytest + 96/96 test frontend + build sạch.
- Việc còn mở nếu cần: nút "gỡ căn" cho chủ nhà sau khi auto công bố (hiện quyết định tự động đã ghi sổ, gỡ cần endpoint riêng).

## 17. Bật agent LLM thật + kho 2.779 tin dùng được (04/11, đêm)

Nguyên nhân "agent chưa chạy, db dữ liệu phòng không dùng được": **backend không tự nạp .env** (thiết kế bảo mật có chủ đích) — các lần khởi động thiếu env khiến agent rơi về `demo_rules` và DB sqlite mặc định, trong khi `.env` của dự án cấu hình sẵn: LLM OpenRouter (`openai/gpt-6-luna`, key riêng), Postgres online Neon (`HOMEMATCH_DATABASE_URL`) với **2.779 tin** (crawl Chợ Tốt 2.446 + demo 333). Khởi động đúng: `set -a; source .env; set +a` trước khi chạy uvicorn.

Kho crawl dùng được nhờ cơ chế **"chấp nhận dữ liệu ước tính"** (opt-in, có nhãn, không bật ngầm):

- Chẩn đoán: 1.447 tin TP.HCM bị giữ 100% vì `capacity=None` (tin Chợ Tốt không ghi sức chứa) và 917/1.223 thiếu bảng phí; crawler regex chỉ đọc đủ 5 loại phí ở 14/2.779 tin. Chạy `data/llm_fees.py --limit 50` (kiểm chứng tất định) chỉ nhận được 10 giá trị phí — tin Chợ Tốt thật sự hiếm khi ghi giá điện/nước trong nội dung, nên trích LLM không phải chìa khóa.
- **Cờ `accept_estimated_data`** (DraftProfile/Profile/Extraction; nl đếm "chấp nhận phí/dữ liệu ước tính" cả hai bản interpreter): khi bật — phí vắng trong tin được thay bằng `ASSUMED_FEES` (điện 3.500đ/kWh, nước 20.000đ/m³, internet 100k, giữ xe 70k/xe, dịch vụ 300k — giữa khoảng tin đăng, nguồn ghi rõ trong từng dòng phí); `capacity=None` coi như vừa số người đã nêu; phí có trong tin nhưng không ghi giá vẫn giữ unknown (không đặt giá hộ). Phòng matched gắn `fee_assumed:…`, `capacity_unknown` (frontend đổi thành nhãn tiếng Việt) + tradeoff "…theo giả định chuẩn — cần xác minh lại khi xem".
- **Verify live**: "Chấp nhận dữ liệu ước tính, tìm phòng trọ dưới 4 triệu ở TP.HCM" → 5 căn thật hiện trên bản đồ Goong trong ~40 giây (LLM + job 10s + auto-publish), thẻ phòng tiêu đề tin thật, đánh đổi/nhãn xác minh đầy đủ.
- Kiểm chứng: `test_fee_assumptions_are_explicit_opt_in_unlocks_crawled_rooms` (giữ/mở theo cờ, không đặt giá hộ phí đã nêu, nhãn đủ); full pytest + 96/96 frontend + build sạch.
- Lưu ý vận hành: LLM thật tính token OpenRouter (~0.9-1k tokens/lượt trích xuất); tile Goong thỉnh thoảng chậm >20s thì tự fallback OpenStreetMap (đã có lý do trong hint).

Kiểm chứng: full pytest backend pass (thêm test compact_mvp cho diagnostics_summary/steps, tenant_portal cho lưu/xem, capability matrix mở rộng); frontend 96/96 pass (thêm `no-match-playbook.test.tsx`); build sạch; verify trực quan toàn bộ luồng no-match + lưu phòng + trang cá nhân trên localhost.
