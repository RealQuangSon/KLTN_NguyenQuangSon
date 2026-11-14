# Coding plan — Sửa luồng UX người thuê

**Ngày lập:** 12/11/2026.

**Phạm vi:** luồng người thuê từ trang chủ tới lúc đặt lịch xem: trang chủ → đăng nhập → trợ lý (`/tro-ly-ai`) → danh sách gợi ý → chi tiết căn → yêu cầu xem. Chưa kiểm tra cổng chủ nhà, quản trị, hợp đồng, hóa đơn.

**Cách kiểm tra:** chạy app thật trên localhost ngày 12/11/2026 (`bash infra/run-neon.sh`, kho Chợ Tốt 4.058 tin, LLM bật), tài khoản `renter-b`, đi 2 lượt chat:

1. "tìm phòng ở bình thạnh tầm 4 triệu cho 2 người"
2. "mấy căn này nhỏ quá, mình muốn phòng rộng hơn khoảng 20m2 có máy lạnh, giá thuê 3 đến 4 triệu"

Sau đó đọc code để tìm nguyên nhân từng lỗi. Mỗi dòng dưới đây ghi rõ là **đã thấy trên app**, **đã đọc code**, hay **chưa chắc**.

## 1. Kết luận ngắn

Luồng "ngu" vì ba nhóm lỗi, xếp theo mức gây hại:

| Nhóm | Vấn đề | Hậu quả với người thuê |
|---|---|---|
| A. Kết quả sai ý | Hiểu sai ngân sách, xếp căn rẻ nhất lên đầu, bỏ qua diện tích | Hỏi phòng 3–4 triệu, 20 m² cho 2 người; nhận phòng 1,2–2,8 triệu, 10–12 m², tin "ở ghép", "cho nữ thuê" |
| B. Luồng đứt và chậm | Mất câu đã gõ ở trang chủ, tin nhắn của mình biến mất khi chờ, chờ 30–40 giây | Phải gõ lại, không biết hệ thống có nhận câu hỏi không |
| C. Chữ nghĩa khó hiểu | Thuật ngữ nội bộ, khóa tiếng Anh, danh sách "chưa rõ" dài, thông tin lặp | Đọc không hiểu, không biết vì sao căn này được gợi ý |

Nhóm A phải sửa trước. Sửa chữ và giao diện trên một danh sách sai thì vẫn là danh sách sai.

## 2. Hiện trạng chi tiết

### Nhóm A — Kết quả sai ý

| # | Lỗi | Bằng chứng | Mức chắc chắn |
|---|---|---|---|
| A1 | **"Giá thuê 3–4 triệu" bị áp thành trần TỔNG tháng 4 triệu.** Tổng tháng = tiền thuê + khoảng 1 triệu phí giả định, nên mọi căn tiền thuê trên khoảng 3 triệu bị loại. Nháp ghi đúng `budget_scope: "rent"` nhưng không ai dùng | `profileFromDraft` gán `max_monthly_cost_vnd = budget_hint_vnd` bất kể `budget_scope` ([profile.ts:13](../../frontend/src/profile.ts)); hồ sơ sau xác nhận có cả `max_monthly_cost_vnd` và `max_rent_vnd` = 4.000.000; 5 căn trả về có tiền thuê 1,2–2,8 triệu | Đã thấy + đã đọc code |
| A2 | **Căn rẻ nhất luôn đứng đầu.** Điểm chi phí = `1 − tổng tháng / trần`, chiếm 50% trọng số. "Tầm 4 triệu" nghĩa là quanh 4 triệu, nhưng căn 1,2 triệu được điểm cao nhất | [catalog.py:150](../../backend/app/catalog.py); lượt 1 trả 5 căn 2,2–2,5 triệu tổng tháng, đều 10–15 m² | Đã thấy + đã đọc code |
| A3 | **Không có cận dưới ngân sách.** "3 đến 4 triệu" chỉ giữ số 4 triệu | Nháp chỉ có `budget_hint_vnd: 4000000`; căn tổng tháng 2,22 triệu vẫn nằm trong 5 căn đầu ở lượt 2 | Đã thấy |
| A4 | **Diện tích không phải là trường nhu cầu.** "Rộng hơn, khoảng 20 m²" chỉ được chép vào `soft_description`, không lọc, không tính điểm | Hồ sơ không có trường diện tích; lượt 2 căn đứng đầu 12 m², căn thứ năm 10 m² | Đã thấy + đã đọc code |
| A5 | **Tin "ở ghép" và tin giới hạn giới tính lọt vào danh sách cho 2 người.** Sức chứa "chưa rõ" được cho qua (đúng theo D-12), nhưng tiêu đề đã nói rõ "Tìm 1 bạn ở ghép", "CHO NỮ THUÊ" | Lượt 2: căn 1 "CHO NỮ THUÊ PHÒNG TRỌ…", căn 2 "Tìm 1 bạn ở ghép có thể dọn vào ngay" | Đã thấy |
| A6 | **Frontend tự dựng hồ sơ và tự xác nhận.** Trái với quy ước "frontend không tính điểm, quyền, công bố" và "tiền trong chat chỉ là gợi ý cho tới khi người thuê xác nhận" | Hiệu ứng tự xác nhận ở [RenterWorkspace.tsx:701-751](../../frontend/src/pages/RenterWorkspace.tsx); lỗi bị nuốt im lặng (dòng 740) | Đã đọc code |
| A7 | **Câu trả lời chỉ kể lại thứ tự giá**, không nói căn nào hợp ý nào của người thuê, và thừa nhận luôn "chưa đủ dữ liệu để xác nhận sức chứa cho 2 người" | Câu trả lời lượt 1: "Các phòng đứng đầu vì tổng tháng lần lượt là…" | Đã thấy |

### Nhóm B — Luồng đứt và chậm

| # | Lỗi | Bằng chứng | Mức chắc chắn |
|---|---|---|---|
| B1 | **Câu gõ ở trang chủ bị mất sau khi đăng nhập.** Trang đăng nhập hứa "trợ lý bắt đầu phiên tư vấn từ nhu cầu này", nhưng vào trợ lý là màn trống | Chuỗi request: `POST /sessions` → `GET /auth/me` → không có `POST /messages`. Sau đăng nhập, `AppShell` bật lại `boot` để gọi `/auth/me` ([App.tsx:267-273](../../frontend/src/App.tsx)), làm `RenterWorkspace` bị gỡ ra giữa lúc đang tạo phiên; khi gắn lại thì `pendingNeed` đã bị xóa | Đã thấy + đã đọc code |
| B2 | **Câu trả lời ở trang chủ là câu soạn sẵn.** Người dùng đã nói khu vực và số người, vẫn bị bảo "sẽ hỏi rõ thành phố, số người" | Hằng chuỗi ở [Landing.tsx:14](../../frontend/src/pages/Landing.tsx); dòng "Lượt trò chuyện đầu được phản hồi ngay" (dòng 289) không đúng thực tế | Đã thấy + đã đọc code |
| B3 | **Tin nhắn của người dùng không hiện trong lúc chờ.** Chỉ thấy câu chào và "Trợ lý đang xử lý…" | Tin nhắn người dùng chỉ được thêm sau khi có phản hồi ([RenterWorkspace.tsx:609-611](../../frontend/src/pages/RenterWorkspace.tsx)) | Đã thấy + đã đọc code |
| B4 | **Câu chào hỏi lại đúng điều người dùng vừa nói** ("Bạn muốn tìm phòng ở đâu, cho bao nhiêu người…") | `create()` luôn chèn câu chào, kể cả khi gửi kèm câu đầu ([RenterWorkspace.tsx:537](../../frontend/src/pages/RenterWorkspace.tsx)) | Đã thấy + đã đọc code |
| B5 | **Lượt chat mất 30–40 giây**, trong lúc đó chỉ có một dòng trạng thái | Đo bằng ảnh chụp: gửi lúc 0 giây, 24 giây vẫn đang ở bước `update_needs`, có kết quả ở khoảng 34 giây. Chưa đo từng chặng (LLM, Neon, xếp hạng) | Đã thấy, chưa tách nguyên nhân |
| B6 | **Danh sách đổi chậm hơn câu trả lời.** Chat đã tả 3 căn mới, khung danh sách còn hiện 5 căn cũ | Ở lượt 2, cùng một thời điểm chat nói "căn đầu 12 m²" còn danh sách vẫn là căn 10 m²; vài giây sau mới đổi. Tự xác nhận chạy sau khi lượt chat xong, danh sách chờ thêm vòng đọc lại 5 giây | Đã thấy, cần tái hiện để đo |
| B7 | **Bấm một thẻ là cả khung nhảy sang bản đồ + chi tiết**, mất danh sách | Bấm thẻ đầu ở lượt 1 | Đã thấy |
| B8 | **Nền bản đồ xám, chỉ có marker giá** | Không thấy request tải ô bản đồ nào trong trình duyệt nhúng của Claude. Có thể chỉ do trình duyệt này (WebGL), **cần mở lại bằng Chrome trước khi kết luận** | Chưa chắc |
| B9 | **Form yêu cầu xem không điền sẵn** họ tên, không gợi ý ngày | Mở form từ chi tiết căn; chưa gửi form | Đã thấy |
| B10 | **Nút "Chat với chủ nhà" hiện trên tin cào**, nơi không có chủ nhà thật trong hệ thống | Chi tiết căn `chotot-…`; trùng với G1 trong [e2e-thue-phong.md](e2e-thue-phong.md) | Đã thấy, chưa bấm |

### Nhóm C — Chữ nghĩa và trình bày

| # | Lỗi | Bằng chứng |
|---|---|---|
| C1 | Dòng trạng thái lộ tên bước nội bộ: "Đang xử lý — bước: route — Phân tích tin nhắn: chuyển sang agent nhu cầu", "update_needs — Đã ghi nhu cầu vào hồ sơ nháp" | [RenterWorkspace.tsx:1204](../../frontend/src/pages/RenterWorkspace.tsx) |
| C2 | Hai nút "Đã xử lý qua N bước" cạnh nhau (một của tin nhắn, một của kết quả), kèm dòng "Đã mở bản đồ trong khung preview" | [RenterWorkspace.tsx:1254, 1331, 1335](../../frontend/src/pages/RenterWorkspace.tsx) |
| C3 | Thuật ngữ nội bộ trong câu chữ cho người thuê: "trong kịch bản đã xác nhận", "giả định chuẩn", "Đã xác nhận nhu cầu và công bố kết quả", "Chưa đủ dữ liệu thu nhập" | Câu lý do sinh ở [catalog.py:162](../../backend/app/catalog.py); câu trả lời lượt 2 |
| C4 | Khóa tiếng Anh lọt ra giao diện: "deposit, first_rent, one_time", "electricity, water, internet, service", "Đáp ứng sở thích air_conditioning", "structured_baseline_v1" | [catalog.py:164-172](../../backend/app/catalog.py); [Shared.tsx:612](../../frontend/src/components/Shared.tsx) |
| C5 | Chi tiết căn liệt kê 17 dòng "Tiện ích chưa rõ: …" nối nhau | Khối "Cần xác minh" ở [Shared.tsx:605](../../frontend/src/components/Shared.tsx) |
| C6 | Thẻ phòng không có tiền thuê theo tin đăng, không có lý do hợp; tổng tháng hiện hai lần với hai kiểu số ("2,220,000 VND" và "2.220.000 ₫") | Thẻ ở lượt 1 |
| C7 | "Kịch bản đã xác nhận: người: 2 · xe: 1 · kWh điện: 140 · chuyển nhà: 300000" — người thuê chưa từng xác nhận các số này, và số không định dạng | Bảng phí trong chi tiết căn |
| C8 | Gợi ý trả lời "Còn căn nào rẻ hơn khu này?" khi danh sách đã là các căn rẻ nhất | Chip dưới ô nhập |
| C9 | Trang chủ còn chữ cũ: bước "03 Quản lý kiểm tra" (đã bỏ từ 05/11), "Kho phòng giả lập" (kho đang là tin thật) | [Landing.tsx:384](../../frontend/src/pages/Landing.tsx) |

## 3. Luật khi sửa

| # | Luật |
|---|---|
| L1 | Giữ mọi bất biến trong `CLAUDE.md`: phí chưa biết là `null`; điều kiện cứng không tự nới; xếp hạng là code tất định; thu nhập không tới chủ nhà, prompt, embedding; tiền chỉ do `costs.py` tính. |
| L2 | Tiền người dùng nói trong chat đọc tất định từ câu của họ, model không tự ghi. Giữ nguyên. |
| L3 | **Đổi công thức xếp hạng (A2, A4) là đổi kết quả đánh giá.** Phải tăng `RANKING_CONFIG.version`, chạy lại `eval ranking`, `eval invariants`, và ghi số cũ/mới. Không sửa dữ liệu gold đã đóng băng. |
| L4 | Frontend không tự dựng hồ sơ, không tự quyết ngân sách. Việc đó chuyển về backend (UX-02). |
| L5 | Mỗi task: viết test trước, sửa, chạy test liên quan, rồi **mở app đi lại đúng 2 câu ở đầu tài liệu** và ghi kết quả. Không ghi "đã kiểm" nếu chưa chạy. |
| L6 | Không gọi API trả phí trong test. Đi thử bằng LLM thật là việc riêng, báo trước cho người dùng. |
| L7 | Chữ hiển thị viết bằng tiếng Việt thường ngày, không mã nội bộ, không khóa tiếng Anh. |

## 4. Quyết định của người dùng

Ba việc này đổi hành vi sản phẩm. **Người dùng đã chốt theo cột "Quyết định" ngày 12/11/2026.**

| # | Câu hỏi | Quyết định |
|---|---|---|
| Q1 | "Tầm 4 triệu" không nói rõ là tiền thuê hay tổng tháng thì hiểu thế nào? | Hiểu là **tiền thuê** (người thuê Việt Nam thường nói giá phòng), hiện rõ "tiền thuê ≤ 4 triệu, tổng tháng ước tính khoảng X" và cho đổi bằng một chip |
| Q2 | Căn nên xếp theo gì khi đều nằm trong ngân sách? | Bỏ "càng rẻ càng tốt". Trong khoảng người thuê nêu thì điểm chi phí bằng nhau; thứ tự do sở thích, diện tích, khoảng cách quyết định. Chỉ ưu tiên rẻ khi người thuê nói "rẻ nhất" |
| Q3 | Diện tích tối thiểu là điều kiện cứng hay mềm? | **Mềm** theo mặc định (tính điểm, ghi nhãn "nhỏ hơn mong muốn"); cứng khi người thuê nói "ít nhất", "tối thiểu" |

## 5. Các task

Làm theo thứ tự. Đợt 1 sửa kết quả, đợt 2 sửa luồng, đợt 3 sửa chữ.

| ID | Task | Đợt | Sửa lỗi | Ưu tiên |
|---|---|---|---|---|
| UX-01 | Tách tiền thuê và tổng tháng khi áp ngân sách | 1 | A1, A3 | P0 |
| UX-02 | Chuyển việc dựng hồ sơ và tự xác nhận về backend | 1 | A6, B6 | P0 |
| UX-03 | Sửa điểm chi phí, thêm diện tích | 1 | A2, A4 | P0 |
| UX-04 | Gắn nhãn tin ở ghép và tin giới hạn đối tượng | 1 | A5 | P1 |
| UX-05 | Giữ câu gõ ở trang chủ qua đăng nhập | 2 | B1, B2 | P0 |
| UX-06 | Khung chat: hiện tin nhắn ngay, bỏ câu chào thừa, trạng thái dễ hiểu | 2 | B3, B4, C1, C2 | P0 |
| UX-07 | Đo và giảm thời gian chờ | 2 | B5 | P1 |
| UX-08 | Thẻ phòng và chi tiết căn | 3 | B7, C4–C7 | P1 |
| UX-09 | Câu lý do và câu trả lời của trợ lý | 3 | A7, C3, C8 | P1 |
| UX-10 | Việc lặt vặt: trang chủ, form xem, bản đồ, nút chat | 3 | B8–B10, C9 | P2 |

### UX-01 — Tách tiền thuê và tổng tháng

1. Backend quyết trần theo `budget_scope` của nháp: `rent` → chỉ đặt `max_rent_vnd`; `total` → đặt `max_monthly_cost_vnd`. Không đặt cả hai từ cùng một con số.
2. `Profile.max_monthly_cost_vnd` đang bắt buộc và là mẫu số của điểm chi phí. Khi người thuê chỉ nêu tiền thuê, cần cho phép trường này trống và tính điểm trên tiền thuê (xem UX-03). Kiểm tra mọi chỗ đang giả định nó có giá trị.
3. Thêm cận dưới tùy chọn (`min_rent_vnd` hoặc tương đương) khi người thuê nói khoảng "3 đến 4 triệu". Cận dưới là mềm: căn dưới khoảng không bị loại, chỉ bị xếp sau và ghi nhãn.
4. Link "Xem đủ trong Tìm kiếm" mang đúng tham số (`max_rent` thay cho `max_monthly` khi phạm vi là tiền thuê).
5. Dòng tóm tắt phía trên danh sách nói rõ đang lọc theo gì: "Tiền thuê đến 4 triệu · tổng tháng ước tính 3,9–5,1 triệu".

**Test:** câu "giá thuê 3 đến 4 triệu" phải giữ được căn tiền thuê 3,5 triệu dù tổng tháng ước tính vượt 4 triệu; câu "tổng tháng 4 triệu" vẫn lọc theo tổng như cũ; thêm ca vào `data/oracles/relative_budget_cases.json` theo đúng quy trình manifest.

### UX-02 — Dựng hồ sơ ở backend

1. Lượt chat đủ dữ liệu thì backend tự xác nhận và chạy xếp hạng **trong cùng lượt** (chế độ agent đã có `confirm_and_search`; đường `fast_path` và `graph_fallback` cần làm tương tự). Phản hồi lượt chat mang luôn kết quả mới.
2. Xóa hiệu ứng tự xác nhận ở frontend và hai hàm `profileFromDraft`, `profileUpdateFromChat` khỏi luồng chat. Form "Nhu cầu của tôi" vẫn gọi `/confirm` khi người thuê bấm lưu.
3. Frontend gắn kết quả từ chính phản hồi của lượt chat, không chờ vòng đọc lại 5 giây.
4. Lỗi xác nhận phải hiện ra cho người thuê bằng một câu, không nuốt im lặng.

**Test:** một lượt chat đủ dữ liệu trả về câu trả lời và danh sách cùng `run_id`; không có khoảng nào câu trả lời nói về danh sách khác với danh sách đang hiện; test tự xác nhận cũ ở frontend chuyển thành test backend.

### UX-03 — Điểm chi phí và diện tích

1. Điểm chi phí: căn nằm trong khoảng người thuê nêu được điểm tối đa; căn dưới cận dưới hoặc sát trần giảm dần. Khi người thuê nói "rẻ nhất", "càng rẻ càng tốt" thì dùng lại công thức cũ.
2. Thêm trường diện tích mong muốn vào nháp và hồ sơ (`min_area_m2`, cờ cứng/mềm). Trợ lý ghi trường này qua `update_needs`; thêm vào `agent_tools.py`, `clarify.py`, form nhu cầu, `locations`/`types` phía frontend.
3. Diện tích thành một thành phần điểm (căn thiếu diện tích có nhãn "nhỏ hơn mong muốn X m²" trong `tradeoffs`). Căn không ghi diện tích: không cộng, không trừ, có nhãn "chưa rõ diện tích".
4. Tăng `RANKING_CONFIG.version`. Chạy `eval ranking --split dev`, `eval invariants --split dev`, ghi bảng số trước/sau vào báo cáo task. Bộ gold không có nhu cầu diện tích nên số cũ chỉ đổi do điểm chi phí; nêu rõ điều này.

**Test:** với hai căn cùng thỏa ngân sách, căn hợp sở thích hơn đứng trước căn rẻ hơn; nhu cầu 20 m² đưa căn 20 m² lên trên căn 10 m²; `posted_at`, `poster_kind`, hoa hồng vẫn không làm đổi thứ hạng.

### UX-04 — Tin ở ghép, tin giới hạn đối tượng

1. Luật tất định đọc tiêu đề và mô tả đã che PII: nhận ra "ở ghép", "tìm bạn ở ghép", "share phòng", "cho nữ thuê", "chỉ nhận nam". Ghi vào `verification` của ứng viên thành nhãn, **không** vào điểm.
2. Hồ sơ từ 2 người trở lên: tin "tìm 1 bạn ở ghép" bị loại như sức chứa không đủ (sức chứa rõ là 1 chỗ). Các trường hợp còn lại chỉ gắn nhãn trên thẻ.
3. Không suy đoán giới tính người thuê. Chỉ hiện nhãn "Tin ghi: chỉ cho nữ thuê".

**Test:** bộ câu mẫu có và không có từ khóa; tin ở ghép không lọt vào kết quả cho 2 người; nhãn không làm đổi điểm.

### UX-05 — Giữ câu gõ ở trang chủ

1. Sau đăng nhập, `onAuthenticated` đã có `actor` từ phản hồi đăng nhập. Không bật lại màn `boot` trong trường hợp này (chỉ kiểm `/auth/me` khi mở lại trang với token cũ), để `RenterWorkspace` không bị gỡ giữa chừng.
2. `pendingNeed` chỉ xóa sau khi câu đó đã gửi thành công, không xóa ngay khi bắt đầu.
3. Sửa câu trả lời ở trang chủ thành câu đúng sự thật, không liệt kê thứ "còn thiếu" khi chưa đọc câu hỏi. Ví dụ: "Mình đã nhận câu này. Đăng nhập để mình tìm phòng theo đúng nhu cầu bạn vừa nêu." Sửa dòng "Lượt trò chuyện đầu được phản hồi ngay" cho khớp.

**Test (vitest):** gõ nhu cầu ở trang chủ → đăng nhập (cả nút tài khoản mẫu và form mật khẩu) → có đúng một `POST /messages` mang câu đó; không tạo phiên rỗng thừa.

### UX-06 — Khung chat

1. Thêm tin nhắn của người dùng vào khung ngay khi gửi; lỗi thì đánh dấu "chưa gửi được" kèm nút gửi lại.
2. Phiên mới tạo kèm câu đầu thì không chèn câu chào. Câu chào chỉ hiện khi người dùng bấm "phiên mới" mà chưa gõ gì.
3. Dòng trạng thái dùng nhãn cho người đọc, ánh xạ một chỗ: `route` → "Đang đọc yêu cầu", `update_needs` → "Đang ghi nhu cầu", `search_rooms` → "Đang lọc kho phòng", `confirm_and_search` → "Đang xếp hạng". Bước lạ dùng "Đang xử lý". Đặt dòng này ở cuối khung chat, chỗ câu trả lời sẽ hiện.
4. Chỉ giữ **một** nút "Đã xử lý qua N bước", gắn vào tin nhắn của lượt đó. Bỏ nút thứ hai và dòng "Đã mở bản đồ trong khung preview".

**Test (vitest):** tin nhắn người dùng có trong DOM trước khi API trả lời; không có chuỗi `route`, `update_needs` trong DOM; chỉ một nút bước xử lý cho mỗi lượt.

### UX-07 — Thời gian chờ

1. Đo trước khi sửa: dùng `hm_agent_turns`/`hm_agent_steps` (`GET /admin/agent-turns`) lấy thời gian từng bước của 5 lượt thật; tách LLM, công cụ, Neon. Ghi bảng vào báo cáo.
2. Chỉ sửa chặng chiếm nhiều nhất. Ứng viên theo thứ tự nghi ngờ: số lần gọi LLM mỗi lượt (tối đa 4, cộng 1 lượt giải thích), input analyst `jev` chạy trước mỗi lượt, truy vấn Neon theo từng dòng.
3. Câu đơn giản như câu 1 ở đầu tài liệu nên đi `fast_path` (0 lần gọi LLM) rồi mới gọi 1 lượt giải thích. Kiểm tra vì sao lượt đi thử không vào đường này.
4. Mục tiêu: có danh sách trong 10 giây với câu đơn giản. Chưa đạt thì ghi rõ con số đạt được, không ghi "đã tối ưu".

### UX-08 — Thẻ phòng và chi tiết căn

1. Thẻ: tiền thuê theo tin đăng là số chính; tổng tháng ước tính là dòng phụ; một kiểu số duy nhất (hàm `money`). Thêm tối đa 2 nhãn lý do ("Có máy lạnh", "Đúng 20 m²") và tối đa 1 nhãn lưu ý ("Nhỏ hơn mong muốn", "Tin ghi ở ghép").
2. Backend trả lý do và đánh đổi dạng có cấu trúc (mã + tham số), frontend dịch ra chữ bằng một bảng nhãn. Hết chuỗi "deposit, first_rent", "air_conditioning".
3. Chi tiết: gộp tiện ích chưa rõ thành một dòng "Tin chưa ghi 17 tiện ích — xem danh sách", bấm mới bung. Chỉ nêu riêng các tiện ích người thuê đã yêu cầu.
4. Bỏ "Phiên bản 1 · structured_baseline_v1" khỏi giao diện người thuê (giữ ở trang quản trị). Bỏ khối tổng tháng lặp lần hai. Dòng "Chưa đủ dữ liệu thu nhập" chỉ hiện khi người thuê đã mở phần mô phỏng tài chính.
5. "Kịch bản đã xác nhận" đổi thành "Cách tính: 2 người, 1 xe, 140 kWh điện, 3 m³ nước mỗi tháng — đổi trong Nhu cầu của tôi", số có định dạng.
6. Bấm thẻ mở chi tiết dạng ngăn bên cạnh hoặc lớp phủ, danh sách vẫn còn; có nút quay lại rõ ràng.

### UX-09 — Câu lý do và câu trả lời

1. Sửa câu sinh ở `catalog.py`: bỏ "trong kịch bản đã xác nhận"; phí giả định gọi là "phí ước tính vì tin không ghi".
2. Prompt lượt giải thích (ranking handover): mở bằng căn hợp nhất và **hợp ở điểm nào người thuê đã nêu**; mỗi căn một dòng ngắn; nêu một điểm cần hỏi lại chủ nhà; không dùng "công bố", "xác nhận hồ sơ", "kịch bản". Giữ `guard_output` và `check_numbers`.
3. Mẫu dự phòng (`confirm_template`) viết lại cùng giọng.
4. Chip gợi ý trả lời sinh theo tình trạng danh sách: không hỏi "còn căn nào rẻ hơn" khi đang xếp theo giá thấp; ưu tiên chip về điều người thuê vừa nêu mà danh sách chưa đáp ứng ("Chỉ xem căn từ 20 m²").

**Test:** không có chuỗi cấm ("kịch bản đã xác nhận", "công bố", khóa tiếng Anh) trong lý do, đánh đổi, mẫu dự phòng; test guard số liệu hiện có vẫn qua.

### UX-10 — Việc lặt vặt

1. Trang chủ: bỏ bước "Quản lý kiểm tra", sửa "Kho phòng giả lập" theo kho đang chạy.
2. Form yêu cầu xem: điền sẵn họ tên từ tài khoản, ngày mặc định là ngày mai, chặn ngày quá khứ.
3. Bản đồ: mở bằng Chrome, xem nền có tải không. Nền không tải thì hiện thông báo và tự chuyển về danh sách, không để khung xám.
4. Nút "Chat với chủ nhà" trên tin cào: ẩn hoặc đổi thành liên hệ qua điều phối, làm cùng E-02 trong [e2e-thue-phong.md](e2e-thue-phong.md).

## 6. Tiêu chí xong

Đi lại đúng 2 câu ở đầu tài liệu trên app thật, bằng tài khoản mới:

| # | Phải thấy |
|---|---|
| 1 | Gõ câu 1 ở trang chủ, đăng nhập, trợ lý tự chạy câu đó; không phải gõ lại |
| 2 | Tin nhắn của mình hiện ngay khi gửi; dòng trạng thái là tiếng Việt thường |
| 3 | Sau câu 2, 5 căn đầu có tiền thuê trong khoảng 3–4 triệu hoặc có nhãn giải thích vì sao lệch; căn 20 m² có máy lạnh đứng trên căn 10 m² |
| 4 | Không có tin "tìm bạn ở ghép" trong danh sách cho 2 người |
| 5 | Câu trả lời và danh sách luôn nói về cùng một bộ căn |
| 6 | Thẻ phòng có tiền thuê và lý do hợp; không còn chữ tiếng Anh hay mã nội bộ ở bất kỳ màn nào trong luồng |
| 7 | `bash infra/check-local.sh` qua; số `eval ranking` trước/sau được ghi lại |

## 7. Trạng thái sau lần sửa 12–13/11/2026

Đã sửa UX-01 đến UX-06, UX-08, UX-09, UX-10 (mục 1, 2). Chưa commit. Test offline: pytest lúc đó qua trừ 2 test trong `test_dialog_fixes.py` (đã tìm ra nguyên nhân và sửa ngày 14/11, xem F4 ở mục 9), 136 test frontend qua, typecheck sạch, `eval invariants` và `eval grounding` trên tập dev qua. Phiên bản xếp hạng là `b1-p-v2`; trên 15 hồ sơ dev, số căn đủ điều kiện giữ nguyên, căn đứng đầu giữ nguyên ở 7/15 hồ sơ.

Đi lại 2 câu mẫu trên app thật (Neon, LLM bật), đối chiếu mục 6:

| # | Kết quả |
|---|---|
| 1 | Đạt: câu gõ ở trang chủ tự chạy sau đăng nhập |
| 2 | Đạt: tin nhắn hiện ngay, trạng thái "Đang đọc yêu cầu" |
| 3 | Đạt sau câu 2: 5 căn đầu tiền thuê 3–4 triệu, từ 20 m², có máy lạnh |
| 4 | Chưa thấy tin "tìm bạn ở ghép"; 2 tin loại này bị loại ở bước lọc |
| 5 | Đạt ở câu 2. Ở câu 1 khung danh sách còn hiện "Đang soạn danh sách…" vài giây sau khi có câu trả lời |
| 6 | Thẻ có tiền thuê; chưa rà hết mọi màn để tìm chữ tiếng Anh |
| 7 | Đạt ngày 14/11: `bash infra/check-local.sh` qua toàn bộ (mục 9) |

Còn lại:

- **Thứ tự khi hòa điểm (đã sửa 13/11, người dùng chốt).** Trước đó, với câu 1 (không sở thích, không diện tích), cả 67 căn cùng điểm 1,0 nên 5 căn đầu là 5 căn có mã nhỏ nhất. Nay các căn hòa điểm xếp theo số mục tin không ghi (từng khoản phí phải tạm tính, sức chứa, diện tích): ít mục thiếu hơn đứng trước, sau đó mới tới mã phòng (`missing_info` trong `catalog.py`). Luật này không đổi điểm và không đọc ngày đăng, loại người đăng hay thuộc tính thương mại. Có test trong `test_ux_batch1.py`; `eval invariants` và `eval grounding` trên tập dev vẫn qua. Chạy lại câu 1 trên app thật ngày 13/11: 5 căn đầu đều chỉ thiếu 3 mục (sức chứa và 2 khoản phí), thay cho các căn thiếu 5–6 mục trước đó; tiền thuê 1,8–4 triệu, diện tích 12–20 m². Không căn nào trong 67 căn khớp có ghi sức chứa, nên luật này chủ yếu phân biệt theo số khoản phí tin có ghi. Một tin "cho nữ thuê" 12 m², thuê 1,8 triệu vẫn nằm thứ năm: khi người thuê chỉ nói "tầm 4 triệu", hệ thống chưa ưu tiên căn gần mức đó.
- **Ưu tiên căn gần mức tiền khi người thuê nói "tầm/khoảng X" (đã sửa 13/11, người dùng chốt).** Câu có "tầm", "khoảng", "quanh", "xấp xỉ" đi với một mức tiền bật cờ `budget_approx` (đọc tất định bằng `budget_approx_hint` trong `interpreter.py`). Khi cờ bật, điểm chi phí = tiền thuê / mức X, nên căn gần X đứng trước; X vẫn là trần cứng. "Dưới/tối đa X" hoặc một khoảng "3 đến 4 triệu" tắt cờ; "rẻ nhất" thắng cờ này. Có 3 test trong `test_ux_batch1.py`. Chạy lại câu 1 trên app thật: 5 căn đầu đều thuê đúng 4.000.000 ₫, diện tích 15–50 m².
- **Tin ở ghép còn lọt.** Lần chạy trên có tin "pass trọ hoặc kiếm 1 nữ vô ở ghép" đứng thứ tư cho hồ sơ 2 người: nó có nhãn "Tin ghi ở ghép" nhưng không bị loại, vì luật loại chỉ nhận dạng "tìm N bạn ở ghép".
- **Tin "cho nữ thuê" vẫn có thể đứng đầu** (chỉ gắn nhãn, không trừ điểm, vì không biết giới tính người thuê).
- **Lượt chat vẫn mất 35–45 giây** (UX-07 chưa làm).
- UX-08 mục 6 (chi tiết dạng ngăn bên), dòng tóm tắt ngân sách phía trên danh sách, lỗi tự xác nhận chưa hiện thành câu cho người thuê, `frontend/src/profile.ts` còn nằm lại dù không ai gọi.
- Chuỗi lý do trong `catalog.py` giữ nguyên vì `eval/suites.py` đọc chúng bằng regex; phần dịch sang lời thường nằm ở frontend.
- Lưới an toàn trong `agent_loop.py` (model ghi nhu cầu mà không tìm lại thì backend tự xác nhận) mới kiểm trên app thật, chưa có test riêng.
- `eval/runs/development/*` đã bị ghi đè bằng kết quả chạy mới.

## 8. Chưa kiểm tra

- Tìm kiếm bằng bộ lọc (`/tim-kiem`), trang đã lưu, so sánh căn, mô phỏng tài chính, tin nhắn.
- Gửi form yêu cầu xem và phần lịch xem hai phía.
- Trường hợp không có căn khớp và các chip nới điều kiện.
- Cổng chủ nhà, quản trị, hợp đồng, hóa đơn.
- Giao diện trên màn rộng: lần đi thử dùng khung trình duyệt hẹp (khoảng 1.024 px), bố cục chat xếp trên danh sách.

## 9. Kiểm tra tổng thể luồng e2e (13–14/11/2026)

**Cách kiểm tra:** chạy app thật (Neon, kho Chợ Tốt, LLM bật) trên trình duyệt với các tài khoản mẫu `renter-b`, `admin-a`, `owner-a`, `renter-a`; sau đó chạy `bash infra/check-local.sh`. Lần kiểm tra để lại trên Neon một lịch xem thử của `renter-b` cho tin `chotot-133336112` (tên "Khách thử E2E", trạng thái đã xem xong, đánh giá 5/5).

### Kết quả từng chặng

| Chặng | Kết quả |
|---|---|
| Trang chủ → đăng nhập → trợ lý → danh sách | Chạy được (mục 7) |
| Danh sách → "Xem đủ trong Tìm kiếm" | Chạy được sau khi sửa lỗi F1 |
| Xem nhanh tin → gửi yêu cầu xem | Chạy được; ngày mặc định là ngày mai, chặn ngày quá khứ |
| Lịch xem của người thuê | Hiện đúng trạng thái theo từng bước |
| Tin cào → hàng đợi điều phối của admin → xác nhận → hoàn tất | Chạy được |
| Phản hồi sau khi xem | Chạy được sau khi sửa lỗi F2 |
| Cổng chủ nhà: tổng quan | Chạy được sau khi sửa lỗi F3 |
| Hợp đồng, hóa đơn, báo chuyển tiền (hai phía) | Trang mở được và hiện đúng dữ liệu demo của `owner-a`/`renter-a`. **Chưa tự tạo hợp đồng mới, chưa bấm kích hoạt, lập hóa đơn hay xác nhận tiền trên trình duyệt** |
| Lịch xem tin chủ nhà → tạo hợp đồng từ lịch | Đã đi trọn trên trình duyệt ngày 14/11 bằng một phòng do `owner-a` tự đăng (mục 10) |
| `bash infra/check-local.sh` | Qua toàn bộ: 846 test backend (12 bỏ qua), 137 test frontend, build, demo, smoke |

### Lỗi đã sửa trong lần kiểm tra

| # | Lỗi | Sửa |
|---|---|---|
| F1 | Link "Xem đủ trong Tìm kiếm" mang `max_rent` nhưng trang tìm kiếm không đọc tham số này: hiện 109 tin thay vì 68 | `SearchPage.tsx` đọc thêm `max_rent`, `min_rent` từ URL |
| F2 | Nút "Gửi phản hồi" tự gửi 5 sao kèm ghi chú "Đã xem phòng." mà không hỏi người thuê | Thay bằng form chọn điểm 1–5 và ghi chú (`ViewingPanel.tsx`), có test |
| F3 | **Đăng nhập chủ nhà làm treo toàn bộ API nhiều phút.** `/landlord/analytics` chạy 4 truy vấn cho từng phòng; `owner-a` đang đứng tên 1.029 tin cào nên là hơn 4.000 truy vấn tới Neon, giữ khóa DB, `/health` cũng không trả lời | `pms.analytics` gộp thành 4 truy vấn `GROUP BY`; test `test_pms.py` qua |
| F4 | **Công cụ `search_rooms` của trợ lý luôn lỗi khi có kết quả** (đọc thuộc tính không tồn tại), nên model không nhận được số liệu và trả câu mẫu. Đây là nguyên nhân 2 test trong `test_dialog_fixes.py` hỏng, không phải test cũ lỗi thời | `agent_loop.py` lấy tên đường qua `_street_of`; 2 test đó giờ qua |
| F5 | Trạng thái lịch xem hiện chữ `completed` ở trang điều phối | Thêm nhãn tiếng Việt cho `completed`, `no_show`, `cancelled`, `reschedule_proposed` |

### Chỗ đứt còn lại

| # | Vấn đề | Mức |
|---|---|---|
| G1 | **Hai nửa luồng không nối với nhau trên kho thật.** Toàn bộ kho là tin cào: lịch xem đi về admin điều phối, không về chủ nhà. Chủ nhà `owner-a` có 0 lịch xem nên không có lịch nào để "tạo hợp đồng từ lịch xem". Muốn đi trọn luồng tới hợp đồng thì chủ nhà phải tự đăng một phòng riêng, hoặc cần E-10 (gán tin cào cho chủ nhà thật) | Cao |
| G2 | **Tin cào vẫn đứng tên chủ nhà mẫu.** `owner-a` thấy 1.029 tin cào như phòng của mình: bảng tổng quan dài 1.029 dòng không phân trang, ô chọn phòng khi soạn hợp đồng có 1.029 mục, và chủ nhà này nhận khách tiềm năng (13 lead) từ gợi ý AI cho tin không phải của họ | Cao |
| G3 | Trang tìm kiếm ghi tổng tháng "Chưa xác định" cho cùng căn mà trợ lý ghi "ước tính 5.020.000 ₫". Hai nơi dùng hai cách tính khác nhau; sắp xếp "Tổng tháng thấp → cao" vì thế không có nghĩa | Trung bình |
| G4 | Hết phiên đăng nhập thì bị đưa về trang đăng nhập, đăng nhập xong vào trang chủ của vai chứ không quay lại trang đang mở | Trung bình |
| G5 | Lịch xem và các bảng hợp đồng, hóa đơn hiện mã phòng (`chotot-133336112`) thay cho tên phòng; dòng mô tả lịch dính chữ "giờ Asia/SaigonHomeMatch sẽ liên hệ…" | Thấp |
| G6 | Trang điều phối của admin không có nút đề xuất giờ khác hay hủy; SĐT khách hiện bằng hộp `alert` của trình duyệt | Thấp |
| G7 | Nút "Chọn giờ khác" của người thuê tự chọn sáng ngày mai, không hỏi (cùng kiểu lỗi với F2; chưa sửa) | Thấp |
| G8 | Soạn hợp đồng thủ công vẫn phải gõ mã tài khoản người thuê | Thấp |
| G9 | Xem nhanh tin ở trang tìm kiếm không có khối kiểm chứng tin, giá mỗi m², chỗ ở tương tự hay nút báo cáo (E-04 đến E-06); chưa kiểm tra trang `/tin/:id` | Chưa rõ |
| G10 | Chân trang và trang đăng nhập còn ghi "Phòng giả lập", "dữ liệu giả lập", "kịch bản đã xác nhận" | Thấp |

### Chưa kiểm tra

- Tự tạo phòng của chủ nhà rồi đi trọn nhánh chủ nhà trên trình duyệt (đặt lịch → đề xuất giờ → hoàn tất → hợp đồng → chấp nhận → kích hoạt → hóa đơn → báo chuyển → xác nhận → phiếu thu).
- Lưu căn, so sánh căn, mô phỏng tài chính, chat với chủ nhà, sửa chữa, cẩm nang.
- Trang tin công khai `/tin/:id`, trợ lý của chủ nhà, các trang quản trị ngoài điều phối.
- Trường hợp lỗi: phòng hết trong lúc chờ, hủy lịch, vắng mặt, không có căn khớp.
- Màn hình rộng và màn hình 360 px.

## 10. Nhánh chủ nhà đi trọn trên trình duyệt (14/11/2026)

**Cách làm:** `owner-a` tự đăng một phòng riêng (`room-6ab8773a84`, tiêu đề "[THỬ E2E] Phòng 22 m² có máy lạnh gần chợ Bà Chiểu"), `renter-b` đặt lịch xem phòng đó, rồi đi tiếp tới biên lai. App chạy với Neon. Dữ liệu thử còn nằm trên Neon: phòng trên (đang ở trạng thái đã thuê), một lịch xem đã hoàn tất, một hợp đồng đang hiệu lực 01/12/2026–01/06/2027, một hóa đơn kỳ 2026-12 đã thanh toán và biên lai `BL-202612-00002`.

| Bước | Kết quả |
|---|---|
| Chủ nhà đăng phòng, bật công khai | Chạy được |
| Trang tin công khai `/tin/:id` | Hiện đủ: chi phí từng khoản, tổng tháng 4.782.000 ₫, kiểm chứng tin, chỗ ở tương tự, nút báo cáo, cảnh báo không chuyển tiền trước |
| Người thuê đặt lịch xem | Chạy được; lịch về đúng chủ nhà |
| Chủ nhà xác nhận → hoàn tất | Chạy được |
| Chủ nhà thấy tên và SĐT khách sau khi xác nhận | Chạy được sau khi sửa H1 |
| Tạo hợp đồng từ lịch đã xem xong | Chạy được sau khi sửa H2; không phải gõ mã tài khoản |
| Gửi khách → khách chấp thuận → kích hoạt | Chạy được; kích hoạt mất 10 giây |
| Chốt số điện nước → lập hóa đơn | Chạy được; 4.882.000 ₫ khớp bảng phí (thuê 3.800.000 + điện 532.000 + nước 200.000 + internet 100.000 + xe 100.000 + dịch vụ 150.000) |
| Khách báo đã chuyển → chủ nhà xác nhận đã nhận | Chạy được; hóa đơn chuyển "Đã thanh toán" |
| Biên lai | Mở được |
| `bash infra/check-local.sh` sau các sửa đổi | Qua toàn bộ: 846 test backend, 138 test frontend, build, demo, smoke |

### Lỗi đã sửa

| # | Lỗi | Sửa |
|---|---|---|
| H1 | Chủ nhà không thấy tên và SĐT khách dù máy chủ đã trả về sau khi xác nhận lịch | `ViewingPanel.tsx` hiện dòng "Liên hệ khách" cho bên xử lý |
| H2 | **Lịch "Đã xem xong" của tin chủ nhà không có nút tạo hợp đồng.** Máy chủ đã hỗ trợ `viewing_id` nhưng giao diện chưa nối, nên luồng đứt ở đây | Thêm nút "Tạo hợp đồng" (tin cào không có nút này); trang hợp đồng mở sẵn phòng từ lịch; `pms.create_lease` lấy người thuê từ lịch khi không gửi `renter_id`. Có test backend và frontend |

### Còn lại (chưa sửa)

| # | Vấn đề | Mức |
|---|---|---|
| H3 | Chủ nhà không có nút "Đề xuất giờ khác" khi lịch còn chờ xác nhận (chỉ có sau khi đã xác nhận); nút đó tự chọn 9 giờ sáng hôm sau, không hỏi | Trung bình |
| H4 | Kích hoạt hợp đồng mất 10 giây, không có báo đang xử lý; trang hợp đồng hiện "Chưa có hợp đồng" trong lúc còn đang tải; lần tải danh sách phòng đầu tiên sau khi khởi động mất 16 giây | Trung bình |
| H5 | "Báo đã chuyển" gửi ngay toàn bộ số tiền với nội dung tự sinh, không cho nhập số tiền hay mã giao dịch; nút vẫn hiện sau khi đã báo | Trung bình |
| H6 | Form chốt số điện nước lệch hàng; ô kỳ mặc định là tháng hiện tại dù hợp đồng bắt đầu tháng sau | Thấp |
| H7 | Thông báo sau khi tạo tin ghi "Tin chỉ hiện với khách khi bạn bật công khai" dù tin đã bật công khai | Thấp |
| H8 | Trang tin công khai: nguồn phí hiện `landlord-form/electricity`; "Tiêu đề nhất quán: Không rõ" dù tiêu đề có ghi 22 m²; "Ngày đăng: Chưa có thông tin" với tin vừa tạo; chữ "ownership"; không có điều hướng về app khi đã đăng nhập | Thấp |
| H9 | Sau khi tạo hợp đồng từ lịch, form vẫn ở chế độ "từ lịch xem" cho tới khi tải lại trang (bấm lần nữa bị máy chủ chặn vì trùng thời hạn) | Thấp |
| H10 | Form đặt lịch không điền sẵn tên và SĐT đã dùng ở lần đặt trước (chỉ lấy từ hồ sơ tài khoản) | Thấp |

### Dọn dữ liệu thử (14/11/2026)

Dọn qua chính giao diện của `owner-a`, không xóa dòng nào trong cơ sở dữ liệu:

- Hợp đồng thử với `renter-b` đã **thanh lý**; phòng thử trở lại "Còn trống". Hợp đồng demo của `renter-a` giữ nguyên.
- Tin thử `room-6ab8773a84` đã **ẩn khỏi công khai** ("Chưa duyệt"); `GET /listings/room-6ab8773a84` trả 404 nên tin không còn vào tìm kiếm hay gợi ý.

Còn lại trên Neon, vì app không có chức năng xóa: bản ghi phòng thử (đã ẩn), hai lịch xem đã hoàn tất của `renter-b`, hợp đồng đã thanh lý, hóa đơn kỳ 2026-12 đã thanh toán cùng biên lai `BL-202612-00002` (hóa đơn và khoản thu là bất biến), và các thông báo liên quan.

Ghi nhận thêm khi dọn: thanh lý một hợp đồng chưa tới ngày bắt đầu làm ngày kết thúc (14/11/2026) đứng trước ngày bắt đầu (01/12/2026) trong bảng hợp đồng.

## 11. Luồng e2e bắt đầu từ bước người thuê tìm phòng (14/11/2026)

**Định nghĩa (người dùng chốt):** luồng e2e phải bắt đầu từ việc người thuê tìm phòng, không phải từ trang tin công khai. Lần chạy ở mục 10 đặt lịch từ trang `/tin/:id` nên chưa đạt định nghĩa này.

**Cách làm:** chạy một mạch trên trình duyệt (Neon, LLM bật), cùng một căn từ đầu tới cuối. Căn đó là phòng do `owner-a` tự đăng (`room-6ab8773a84`, đã bổ sung "có máy lạnh"), vì tin cào không đi được tới hợp đồng. `renter-b` gõ: "tìm phòng ở bình thạnh khoảng 20m2 có máy lạnh, giá thuê tầm 3,8 triệu cho 2 người".

| Bước | Kết quả |
|---|---|
| Người thuê tìm phòng qua trợ lý | **Hai lần đầu không ra danh sách**; chạy được sau khi sửa K1 |
| Danh sách gợi ý | 61 căn khớp; căn của chủ nhà đứng đầu (đủ thông tin nhất trong các căn cùng điểm) |
| Mở chi tiết căn từ danh sách, bản đồ | Chạy được; nền bản đồ tải bình thường (ghi nhận B8 ở mục 2 là do trình duyệt nhúng lúc đó) |
| Đặt lịch xem ngay từ kết quả gợi ý | Chạy được; lịch gắn với phiên tìm kiếm |
| Chủ nhà xác nhận → hoàn tất | Chạy được |
| Chủ nhà thấy tên và SĐT khách | **Không thấy** với lịch đặt từ trợ lý; đã sửa K2 (có test, chưa chạy lại trên trình duyệt) |
| Tạo hợp đồng từ lịch → gửi khách → chấp thuận → kích hoạt | Chạy được |
| Chốt số → hóa đơn kỳ 2027-01 (4.882.000 ₫) | Chạy được |
| Khách báo đã chuyển → chủ nhà xác nhận → biên lai `BL-202701-00003` | Chạy được |
| `bash infra/check-local.sh` sau các sửa đổi | Qua toàn bộ: 849 test backend, 138 test frontend, build, demo, smoke |

### Lỗi đã sửa

| # | Lỗi | Sửa |
|---|---|---|
| K1 | **Bước tìm phòng không ổn định.** Lần 1: model ghi nhu cầu, gọi `ask_user` (công cụ trả "không cần hỏi") rồi nói "tiến hành tìm nhé" nhưng không tìm. Lần 2: model hỏi một câu không cần thiết ("có muốn giữ khu vực này không?") dù nhu cầu đã đủ. Cả hai lần trạng thái là "Chờ xác nhận nhu cầu", không có danh sách | Lưới an toàn trong `agent_loop.py`: nhu cầu đã đủ thì backend tự tìm ngay trong lượt, trừ khi có câu làm rõ từ kho (loại làm đổi cách hiểu nhu cầu). Câu hỏi tự do của model được giữ phía trên kết quả. Có 2 test mới trong `test_dialog_fixes.py` |
| K2 | **Lịch đặt từ kết quả của trợ lý bị mất tên, SĐT và khung giờ.** Form có gửi, nhưng route `/sessions/{id}/viewings` không chuyển xuống service, nên chủ nhà không liên hệ được khách | `main.py` chuyển liên hệ, khung giờ, ghi chú; có liên hệ thì bắt buộc đồng ý chia sẻ. Có test mới trong `test_e2e_rental_flow.py` |

### Kết luận

Có một luồng e2e hoàn chỉnh bắt đầu từ bước tìm phòng, **với điều kiện căn được chọn là tin do chủ nhà tự đăng**. Các giới hạn còn lại:

- **Tin cào:** người thuê tìm và đặt lịch được, nhưng luồng dừng ở "đã xem xong" (lịch về admin, không có hợp đồng trong hệ thống). Toàn bộ kho hiện tại là tin cào, nên với dữ liệu thật thì luồng tới hợp đồng không xảy ra nếu chủ nhà không tự đăng tin.
- **Model vẫn gọi sai công cụ ghi nhu cầu 2 lần mỗi lượt** (gửi trường tiền bị cấm, rồi gửi tên tiện ích không có trong từ điển). Lưới an toàn che được hậu quả nhưng mỗi lần sai tốn một lượt gọi model; lượt tìm vẫn mất khoảng 50–60 giây.
- **Câu giải thích còn sai chi tiết:** trợ lý nói "tin chưa ghi rõ sức chứa 2 người" dù tin của chủ nhà ghi sức chứa 2.
- Đặt lịch từ khung trợ lý xong không có thông báo thành công (hộp thoại chỉ đóng lại).
- K2 mới được kiểm bằng test tự động, chưa chạy lại trên trình duyệt.

### Dữ liệu thử

Đã dọn qua giao diện như lần trước: hợp đồng thử thứ hai (01/01/2027–01/07/2027) đã thanh lý, tin thử đã ẩn (`GET /listings/room-6ab8773a84` trả 404). Còn lại trên Neon thêm: một lịch xem đã hoàn tất, hợp đồng đã thanh lý, hóa đơn kỳ 2027-01 đã thanh toán và biên lai `BL-202701-00003`, ba phiên tìm kiếm của `renter-b`.
