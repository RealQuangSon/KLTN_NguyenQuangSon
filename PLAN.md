# PLAN — HomeMatch Agent end-to-end

**Lập:** 05/11/2026. Thay toàn bộ `docs/coding-plan/` (đã xóa). Các file `backend|frontend|data|eval|infra/PLAN.md` giữ lại làm bối cảnh module; khi mâu thuẫn, **file này thắng**.

**Cách giao việc cho coding agent:** "Đọc `CLAUDE.md` và `PLAN.md`, làm task `<ID>`". Mỗi task tự đủ: mục tiêu, file, các bước, test, điều kiện xong. Làm theo thứ tự ưu tiên ở §3, mỗi task một commit.

---

## 0. Mục tiêu sản phẩm

1. **Workflow agent end-to-end:** tìm phòng bằng câu nói tự nhiên, **ảnh** và **giọng nói** → kết quả hiện và tương tác ngay trong workspace (danh sách, bản đồ, so sánh) → **đặt lịch xem** → **xem nhà online** → **chốt căn online** → **review hợp đồng** → **nhận nhà**.
2. **Hỏi đáp thông minh** về nhà ở và quyền lợi người thuê.
3. **15 luồng tự động hóa** đồng bộ người thuê ↔ chủ nhà.
4. **Live chat + handover:** khách muốn nói chuyện trực tiếp thì agent chuyển cho **chủ nhà** của căn đó, kèm ngữ cảnh.
5. **Xem căn hộ online** (cuộc gọi video).
6. **Agent nhanh hơn, thông minh hơn, gợi ý tốt hơn:** điểm chất lượng tổng hợp tăng **từ ~39% (MVP) lên ≥ 60%**, đo theo §5.
7. **Trang cá nhân:** lịch sử trò chuyện, căn đã xem, căn đã lưu, nhu cầu tìm nhà.

## 1. Bất biến không được phá (tóm tắt từ `CLAUDE.md`)

- LLM chỉ **trích xuất, diễn đạt, điều phối**. Tiền chỉ do `costs.py` tính; lọc, xếp hạng, quyền, công bố là code tất định. Mọi con số trong câu trả lời phải đến từ tool.
- **Không còn bước chủ nhà duyệt** (quyết định 05/11/2026: nhiều chủ nhà, nhiều người thuê, duyệt từng căn không khả thi). Kết quả tới khách ngay sau khi chạy xếp hạng, nhưng vẫn chỉ đúng phiên bản hồ sơ và kho hiện tại. Không tự nới điều kiện cứng.
- Thu nhập không bao giờ tới DTO chủ nhà, handover, prompt, embedding. Text phải qua `agent_guard.redact` trước khi tới LLM.
- Mọi tool gọi qua `ToolBox.call(agent, tool, ...)`; tool mới phải thêm vào `AGENT_TOOLS` (`agents.py`) và `agent_capability.py`.
- D-07/D-08: không cổng thanh toán, không email/SMS thật, không chữ ký điện tử pháp lý. "Chốt căn" và "hợp đồng" là click-accept + payment claim do chủ nhà xác nhận.
- Test không gọi API trả phí. Không ghi bí mật, DB local, transcript thô vào git.
- Một worker API. SQL dùng `?`. Migration mới tăng schema (hiện v14) và có test cả SQLite (PG khi có `HOMEMATCH_TEST_DATABASE_URL`).

## 2. Kiểm kê hiện trạng (rà code 04–05/11/2026)

| # | Năng lực | Đã có | Thiếu / lỗi chặn | Task |
|---|---|---|---|---|
| 1a | Tìm bằng câu nói | Chat graph `route→interview`, `OpenAIInterpreter` (OpenRouter `chat_completions`), auto-confirm FE; đã sửa lỗi không chạy lại vòng tìm sau khi chấp nhận dữ liệu ước tính (04/11) | Không hiểu **điểm đến** ("gần HUST" → `destination=null`); "nới thêm 1 triệu" đọc thành trần 1 triệu; kho Chợ Tốt thiếu sức chứa nên vòng đầu luôn `needs_verification` | AG-01, AG-02, AG-03 |
| 1a' | Phỏng vấn khai thác nhu cầu | `_questions` chỉ hỏi "thành phố nào?"; chip nới tiêu chí cố định ở FE | Không phân tích mơ hồ, không hỏi lại có lựa chọn, không đo khi nào nên hỏi | AG-11, AG-12 |
| H | Harness của agent (06/11/2026) | Vòng lặp tool `agent_loop.py` (≤6 bước), `ToolBox` allowlist, hậu kiểm số, fallback graph, stream bước, Jev (`decisions.py`, sửa định dạng 06/11) | `ask_user` của LLM bỏ qua clarify/Jev; lượt 16 s; ngân sách 50 **lần gọi LLM**/phiên ≈ 10 câu là hết; trace chỉ trong RAM; chưa có eval kịch bản nhiều lượt; memory không vào vòng lặp | HN-01…HN-12 |
| 1b | Tìm bằng giọng nói | `VoiceInput.tsx` (Web Speech, vi-VN) | Đủ cho demo; chỉ cần test E2E | E2E-01 |
| 1c | Tìm bằng ảnh | Không có | Toàn bộ: upload ảnh khách → trích đặc điểm → nháp | AG-04 |
| 1d | Kết quả + tương tác workspace | Danh sách, bản đồ MapLibre/OSM, so sánh ≤3, xem nhanh, lưu | Agent không tham chiếu được căn kiểu Chợ Tốt: `ROOM_REFERENCE` chỉ khớp `demo-NN` → "đặt lịch căn số 2", hỏi nội quy, mô phỏng vay theo căn đều hỏng | AG-05 |
| 1d' | Đường đi trên bản đồ | Marker giá trên MapLibre (Goong tile/OSM); lọc và xếp hạng theo **đường chim bay** (`catalog.distance_m`); `GOONG_API_KEY` (REST) có trong `.env` nhưng chưa dùng | Không vẽ đường đi phòng → điểm đến, không có quãng đường/thời gian thực tế | MP-01 |
| 1e | Đặt lịch xem | `POST /sessions/{id}/viewings`, `/listings/{id}/viewings`, chủ nhà phản hồi, nhắc lịch | Chat chỉ "chuẩn bị", không chọn giờ được trong chat | AG-06 |
| 1f | Xem nhà online | `mode=online` → link `meet.jit.si` | Không có nút "Vào phòng" đúng giờ, không ghi tham dự | FL-01 |
| 1g | Chốt căn online | Lead stage `won`, occupancy `deposited`, lease do **chủ nhà** tạo | Khách **không có** cách yêu cầu chốt; không có luồng giữ chỗ/cọc | FL-02 |
| 1h | Review hợp đồng | Văn bản lease, version, click-accept | Không có trợ lý giải thích/đối chiếu điều khoản | AG-07 |
| 1i | Nhận nhà | `activate` lease, chỉ số điện nước | Không có biên bản bàn giao (checklist, chỉ số đầu kỳ, ảnh hiện trạng, hai bên xác nhận) | FL-03 |
| 2 | Hỏi đáp quyền lợi | `handbook.py`: 12 mục, chấm điểm từ khóa | Không trả lời được câu diễn đạt khác; không tổng hợp; ít nội dung | AG-08 |
| 3 | Tự động hóa | ~22 loại thông báo, 5 job nền | Chưa có danh mục 15 luồng chính thức, chưa có test/trang theo dõi theo luồng; thiếu luồng chốt căn, bàn giao | AU-01 |
| 4 | Live chat handover | `conversations.py` + ngữ cảnh, nút "Chat với chủ nhà" | Câu chat "cho tôi nói chuyện với chủ nhà" đi `human_support` → ticket **admin**, không tới chủ nhà | AG-09 |
| 5 | Xem online | như 1f | | FL-01 |
| 6 | Chất lượng agent | Eval extraction/ranking/invariants; chưa có điểm tổng hợp; nhãn người chưa có | Chưa có thước đo "39% → 60%"; chưa đo latency theo lượt | EV-01, EV-02, AG-10 |
| 7 | Trang cá nhân | `/nguoi-thue/da-luu` (đã lưu + đã xem), `/tai-khoan/ho-so` (memory, phiên đăng nhập) | **Không có** API/trang lịch sử trò chuyện; không có danh sách nhu cầu đã xác nhận | PR-01, PR-02 |

## 3. Thứ tự làm

| Đợt | Task | Lý do |
|---|---|---|
| P0 — agent chạy được | AG-00, AG-13, WS-02, WS-01, AG-05, AG-11, AG-01, AG-02, AG-03, AG-09 | Gỡ các lỗi khiến luồng chính đứt ngay ở demo |
| P0 — harness agent | HN-00, HN-03, HN-02, HN-01, HN-04, HN-06, HN-05 | Agent chạy đúng, đủ nhanh, không chết giữa phiên, quan sát được |
| P1 — harness agent | HN-07, HN-08, HN-09, HN-10, HN-11, HN-12 | Đo được, tái lập được, an toàn hơn |
| P1 — đủ vòng đời | AG-06, FL-01, FL-02, AG-07, FL-03, AU-01 | Nối từ kết quả tới nhận nhà |
| P1 — trải nghiệm | MP-01, AG-14, MP-02, AG-15, WS-03, AG-12, PR-01, PR-02, AG-08, AG-04 | Trang cá nhân, hỏi đáp, ảnh |
| P2 — đo và tối ưu | EV-01, AG-10, EV-02, E2E-01 | Chứng minh 39% → 60%, demo trình duyệt |

---

## 4. Task chi tiết

### AG-00 — Bỏ hẳn bước chủ nhà duyệt gợi ý (P0, làm đầu tiên)

**Quyết định 05/11/2026.** Đã làm bước 1: `HOMEMATCH_AUTO_PUBLISH` mặc định bật; test, `backend.demo`, `infra.smoke_api` ghim `false` để giữ luồng cũ chạy được tới khi xóa.
**Bước:**
1. Graph khuyến nghị: `rank → save_draft → publish`, bỏ node `wait_for_review` và `interrupt()`. `repository.set_draft` ghi thẳng `published` (có căn) / `no_match` / `needs_verification`. Run `pending_review|partially_published|reviewed` cũ: migration v15 chuyển sang `invalidated`; bỏ checkpoint đang chờ.
2. Xóa `review`, `_auto_publish`, `drafts`, `draft`, `_landlord_projection` (nếu không còn ai dùng), `finish_review`, `visible_items` theo review; `results` trả thẳng `run.items` khi `published`. Bảng `hm_run_reviews` giữ lại read-only cho dữ liệu cũ (không xóa dữ liệu), không ghi mới.
3. API: xóa `GET/POST /landlord/recommendations*`; `retry` chuyển thành `POST /sessions/{id}/rerun` cho khách. Cập nhật `docs/api-contract.md`, sinh lại `openapi.json`.
4. Quyền: bỏ `run:review`, `run:draft_list`, `run:read` khỏi `capabilities.py`/`agent_capability.py`.
5. Thông báo: bỏ `landlord_review`; `rooms_approved` → `rooms_ready`. Chủ nhà thay vào đó nhận lead khi căn của họ lọt top 5 (`touch_lead(source="recommended")`) — đây là cách chủ nhà vẫn biết nhu cầu mà không chặn khách. Thu nhập vẫn không tới chủ nhà.
6. Frontend: xóa trang `/chu-nha/duyet-goi-y` và mục menu (redirect về `/chu-nha/khach-tiem-nang`); bỏ chữ "duyệt", "chờ chủ nhà" ở `Shared.tsx`, `RenterWorkspace.tsx`, `Journey.tsx`, `ProfileForm.tsx`; bỏ prop `autoPublish` và `useAutoPublish`; `/health` bỏ trường `auto_publish`.
7. Test: viết lại helper confirm-rồi-duyệt trong test (`test_workflow.py`, `test_landlord.py`, `test_backend_durability.py`, …) thành confirm → published; xóa test chỉ kiểm duyệt (thứ tự, `override_reason`, phạm vi từng chủ nhà); giữ test bất biến còn ý nghĩa: phiên bản hồ sơ/kho, không lộ thu nhập trong lead, ranking không đọc `posted_at`/hoa hồng. UI test `landlord-state`, `affordability-review` sửa tương ứng.
8. Docs: `CLAUDE.md` (bỏ câu "each landlord approves", phần graph khuyến nghị và HITL), `docs/ke-hoach-kltn-homematch.md` (ghi quyết định mới, lý do), `docs/yeu-cau-san-pham.md`, `docs/trang-thai-trien-khai.md`, `infra/RUNBOOK.md`.

**Xong khi:** `bash infra/check-local.sh` exit 0; không còn chuỗi `pending_review`, `/landlord/recommendations`, `wait_for_review` ngoài migration và docs lưu trữ; khách chat xong nhu cầu thấy kết quả + bản đồ trong một lượt.

### AG-13 — Agent thật: LLM tự suy luận và tự gọi tool (P0, nền cho mọi task agent)

> **Bổ sung từ nghiên cứu HubHome (§5):** dùng hợp đồng một endpoint + stream bước như HubHome (task WS-02): request mang **ngữ cảnh workspace** (view đang mở, căn đang chọn, ≤30 căn đang hiển thị, căn đính kèm ≤4, điểm đến, lịch đang đặt, GPS nếu khách bật); response là **chỉ thị giao diện** (WS-01) chứ không chỉ văn bản. Mỗi tool call phát một sự kiện `step` ngay khi chạy.

**Vì sao:** hiện LLM chỉ là bộ trích xuất JSON trong một graph cố định, prompt còn cấm dùng hiểu biết chung ("giữ null khi chưa nói quận") và agent không có tool tra cứu → "gần HUST" bị mất dù model biết HUST ở Đại Cồ Việt, Hai Bà Trưng. Yêu cầu của người dùng (05/11/2026): agent phải **tự hiểu như một AI bình thường** — dùng kiến thức chung, suy luận, tự quyết định gọi tool nào.

**Nguyên tắc phân vai (giữ bất biến luận văn):** LLM **quyết định và diễn giải**; tool **tính và kiểm**. Tiền, lọc cứng, xếp hạng, quyền, công bố vẫn là code tất định bên trong tool. Mọi thứ LLM đề xuất (địa điểm, quận, ngân sách) được tool kiểm chứng rồi mới ghi, và ghi ở trạng thái `inferred` kèm câu nói lại cho khách ("Mình hiểu HUST ở Hai Bà Trưng").

**Bước:**
1. **Vòng lặp agent** `backend/app/agent_loop.py`: chat completions với `tools` + `reasoning` (model `OPENAI_MODEL`, đã kiểm `openai/gpt-6-luna` hỗ trợ `tools`, `tool_choice`, `reasoning`). Mỗi lượt: system prompt + tóm tắt nháp/hồ sơ (không thu nhập) + 6 lượt chat gần nhất đã `redact` → model trả tool calls → thực thi qua `ToolBox.call` → đưa kết quả lại → lặp tới khi model trả lời văn bản hoặc chạm giới hạn (**6 bước**, nâng `MAX_STEPS` cho agent này; vượt → trả lời an toàn). Tool lỗi → trả lỗi có cấu trúc cho model tự xử lý, không ném 500.
2. **Bộ tool đầu tiên** (JSON schema từ Pydantic, thêm vào `AGENT_TOOLS["needs"]`):
   - `find_place(query, city_hint?)` → tra `data/places.json` (AG-01) trước, rồi Goong Geocoding/Place (`GOONG_API_KEY` REST, gọi từ backend) → `{name, lat, lng, district, city, source, confidence}`; kiểm tọa độ nằm trong HN/HCM.
   - `update_needs(patch)` → ghi nháp qua đường `interview` hiện có (CAS `draft_revision`, `inferred`, evidence `agent:rN`); từ chối trường tiền/thu nhập không đến từ câu của khách (`rent_budget_hint` của chính tin nhắn).
   - `search_rooms(overrides?)` → chạy `catalog.match` trên hồ sơ tạm (**không ghi**) để xem trước số căn, giá thấp nhất, lý do bị loại.
   - `confirm_and_search()` → xác nhận hồ sơ từ nháp và chạy vòng tìm (thay auto-confirm ở FE; FE chỉ cần refresh kết quả).
   - `ask_user(question, options[])` → kết thúc lượt bằng câu hỏi + chip (khung của AG-11; lựa chọn phải đến từ `search_rooms`/`find_place`, Jev chấm thứ tự khi bật).
   - `room_details(room_ref)` (dùng resolver AG-05), `estimate_cost(room_id)` (`costs.py`), `search_handbook(question)`, `open_landlord_chat(room_ref)` (AG-09), `prepare_viewing(room_ref, time_text)` (AG-06, chỉ chuẩn bị, khách bấm mới tạo).
3. **Prompt mới:** bỏ quy tắc cấm suy luận; thay bằng: "Dùng hiểu biết chung để hiểu địa danh, khu vực, nhu cầu ngầm; khi suy ra điều khách chưa nói, gọi tool để kiểm và nói lại giả định. Không tự bịa số tiền, không tự nới điều kiện cứng, mọi con số trong câu trả lời phải lấy từ kết quả tool."
4. **Câu trả lời:** văn bản tự nhiên của model + khối có cấu trúc (`clarification`, `results_ref`, `steps`) cho FE; hậu kiểm: số trong văn bản phải khớp số từ tool (regex), sai → thay bằng câu template.
5. **Minh bạch:** `steps` = danh sách tool đã gọi (tên + tóm tắt kết quả, không PII) → FE hiện "Đã xử lý qua N bước" như HubHome.
6. **Đường lui:** `HOMEMATCH_LLM_MODE=demo` hoặc model lỗi/hết ngân sách phiên → dùng graph cũ (`route → interview`) như hiện tại; ghi `agent_mode="loop"|"graph_fallback"`.
7. **Ngân sách và tốc độ:** đếm token/tool call vào `agent_budget`; mục tiêu p50 ≤ 4 s/lượt ở chế độ openai (AG-10 tối ưu tiếp).

**Test (không gọi mạng):** model giả kịch bản hóa tool calls: "phòng dưới 4 triệu gần HUST" → `find_place("HUST")` → `update_needs(destination, area, budget)` → `confirm_and_search()` → câu trả lời có kết quả; model đòi ghi thu nhập/tiền không có trong câu → tool từ chối; vượt 6 bước → trả lời an toàn; tool không có trong allowlist → bị chặn; số bịa trong văn bản → bị thay; demo mode → graph cũ. `eval invariants` vẫn qua.

**Quan hệ với task khác:** AG-01 trở thành dữ liệu + tool `find_place`; AG-11/AG-12 là tool `ask_user` + `search_rooms`; AG-05, AG-06, AG-08, AG-09 là các tool trong vòng lặp này thay vì nhánh `fixed_intent` riêng.

**Xong khi:** với OpenRouter thật, "Tìm phòng trọ dưới 4 triệu gần HUST" ra kết quả xếp theo khoảng cách tới HUST trong 1 lượt (hoặc 1 câu hỏi lại có chip), câu trả lời nói rõ "HUST ở Đại Cồ Việt, Hai Bà Trưng" và hiện các bước đã chạy.

### WS-01 — Agent điều khiển workspace (P0, cùng AG-13)

**Mục tiêu (theo HubHome):** mỗi câu trả lời của agent kèm **chỉ thị giao diện**; khung preview tự mở đúng view, chat có chip "↗ Đã mở … trong workspace".
**Hợp đồng response** (`schemas.AgentTurn`): `answer: list[str]` (nhiều bubble), `matches`, `total_matches`, `view: map|list|detail|gallery|compare|cost|route|nearby|area|trust|contract|booking|visit|saved|keep|clear`, payload theo view (`detail`, `cost`, `route`, `nearby`, `area`, `trust`, `contract`, `pending_booking[]`, `handoff`), `anchor` (mốc đã geocode), `criteria` (tiêu chí server giữ), `clarification` (AG-11), `suggested_prompts[]`, `steps[]`, `source_label`, `turn_id`.
**Request** thêm `workspace: {view, selected_room_id, visible_room_ids[≤30], focus_room_ids[≤4], destination?, booking_room_ids?, gps?}` để agent hiểu "căn này", "căn thứ 2", "từ chỗ mình".
**FE:** `RenterWorkspace` tách view router cho preview; mỗi view là component riêng (dùng lại `MapView`, `RoomCard`, so sánh, `Simulation`); `keep` giữ view hiện tại, `clear` dọn workspace.
**Test:** mỗi `view` render đúng payload; view lạ → bỏ qua, giữ view cũ; ngữ cảnh workspace gửi đúng.

### WS-02 — Stream các bước xử lý (P0, cùng AG-13)

**Theo HubHome:** response `application/x-ndjson`: dòng `{"type":"step","step":{"name","kind":"router|tool|pin|guardrail|system","detail","result"}}` phát ngay khi mỗi bước chạy, dòng cuối `{"type":"done","data":AgentTurn}`. FE hiện "Đang … — bước N" theo bước thật (không đoán theo từ khóa) và sau đó "Đã xử lý qua N bước" bung được; bước do hệ thống tự thêm (guardrail, ghim bản đồ) gắn nhãn "hệ thống tự bổ sung".
**BE:** `StreamingResponse` từ vòng lặp AG-13 (một worker vẫn đủ); timeout lượt 60 s; client thử lại tối đa 2 lần khi stream đứt, báo lỗi thân thiện.
**Test:** thứ tự sự kiện; stream đứt → retry; nội dung bước không chứa PII/tiền/thu nhập.

### WS-03 — Composer kiểu HubHome (P1)

Menu "+" (Đính kèm ảnh, Nói), nút **"Gần tôi"** (GPS, bật/tắt rõ ràng, lỗi quyền thì nói thẳng), **"Tìm nhanh"** (bộ lọc nhanh điền câu vào ô), lệnh `/moi`, `/tieuchi`, `/quen` có gợi ý khi gõ `/`; placeholder đổi theo ngữ cảnh ("Hỏi về “{tên căn}”…", "Nhắn cho {chủ nhà}…"); hàng chip tiêu chí đang áp dụng (≤ ngân sách, loại, khu, tiện ích) gỡ được từng chip.

### AG-14 — Nhận xét chủ động khi mở một căn (P1)

**Theo HubHome** (`/api/can/doi-chieu`): khi khách mở chi tiết căn, server so căn với nhóm đang hiển thị (giá/tháng, giá/m², hạng trong danh sách, tiện ích) và chèn **một** tin nhắn trợ lý ngắn + chip hỏi tiếp ("Còn căn nào rẻ hơn khu này?", "Tính tổng chi phí căn này", "Đặt lịch xem").
**HomeMatch:** `POST /v1/sessions/{id}/rooms/{room_id}/insight` → số liệu do code tính (trung vị giá cùng khu + loại từ kho Chợ Tốt, chênh lệch %, xếp hạng); LLM chỉ diễn đạt; không số nào ngoài kết quả tool. Không gọi lại khi mở lại cùng căn trong 10 phút.
**Test:** trung vị đúng trên kho mẫu; nhóm < 5 căn → không nêu trung vị; câu trả lời không chứa số lạ.

### MP-02 — Tiện ích xung quanh và phân tích khu vực (P1, sau MP-01)

**Theo HubHome:** view **"Tiện ích xung quanh"** (nhóm: chợ/siêu thị, trường, bệnh viện, bến xe buýt…; mỗi điểm km + phút đi bộ, ghi "khoảng cách đường chim bay", "vị trí xấp xỉ theo khu" nếu căn không chính xác) với hai nút "Xem đường đi cụ thể" và "Phân tích khu vực"; view **"Khu vực"** cho câu "khu này sống thế nào".
**HomeMatch:** dữ liệu POI tĩnh `data/poi/{hn,hcm}.geojson` lấy một lần từ OpenStreetMap (ODbL, ghi attribution), không gọi API trả phí lúc chạy; tool `nearby(room_id, kinds[])` (chim bay + phút đi bộ = km/4,8 km/h, ghi rõ ước lượng); `area_profile(district)` tổng hợp số liệu tất định từ kho (giá trung vị theo loại, số tin, mật độ POI). LLM chỉ diễn đạt, không bịa về an ninh/ngập lụt.
**Test:** khoảng cách đúng; căn `approximate` hiện cảnh báo; không có số ngoài tool.

### AG-15 — Tín hiệu tin cậy của tin đăng (P1)

**Theo HubHome:** view **"Tín hiệu tin cậy"**: danh sách tín hiệu `tot | canh_bao | khong_ro`, tóm tắt "N điểm cần hỏi rõ, M mục chưa kiểm được (tự động từ dữ liệu, không phải chứng nhận)", form báo tin sai.
**HomeMatch:** `trust.py` tất định trên dữ liệu Chợ Tốt: giá lệch > 40 % trung vị cùng khu/loại, cọc > 3 tháng, thiếu sức chứa/phí, người đăng là môi giới, tin trùng ảnh/tiêu đề, tin cũ > 60 ngày, chủ nhà đã/ chưa xác minh trên HomeMatch. **Không** dùng để xếp hạng (bất biến F2: ranking không đọc `posted_at`/`poster_kind`) — chỉ hiển thị. `POST /v1/listings/{id}/report` cho khách báo tin sai → admin.
**Test:** từng luật dương/âm; `eval invariants` vẫn qua (ranking không đổi).

### AG-05 — Agent tham chiếu được căn trong kết quả (P0)

**Lỗi:** `agent_guard.ROOM_REFERENCE = r"\bdemo[- ]?(\d{1,3})\b"` và `FINANCE_ROOM_REFERENCE` chỉ khớp id demo/synthetic. Kho thật dùng `chotot-<số>`.
**Bước:**
1. Thêm `resolve_room_reference(text, visible_items) -> room_id | None` trong `agent_guard.py`, theo thứ tự: id đầy đủ (`chotot-\d+`, `synthetic-room-\d{3}`, `room-[0-9a-f]{10}`, `demo-\d+`); thứ tự trong danh sách ("căn số 2", "căn thứ hai", "căn đầu tiên", "căn cuối"); khớp tiêu đề rút gọn duy nhất. **Chỉ** trả id nằm trong `visible_items` của run hiện tại.
2. Thay mọi chỗ gọi `room_reference` / `finance_room_reference` trong `service.py` (`_prepare_viewing`, `handbook_node`, `simulate_finance`) bằng hàm mới, truyền `self.results(...)["results"]`.
3. FE: mã phòng và "Căn N" trong tin trợ lý bấm được, mở xem nhanh.

**Test:** `backend/tests/test_agent_room_reference.py`: id Chợ Tốt, thứ tự 1..5, id ngoài danh sách → `None`, câu không nhắc căn → `None`.
**Xong khi:** "đặt lịch căn số 2", "nội quy căn đầu tiên", "nếu vay 12 tháng cho căn 3" chạy đúng với kho Chợ Tốt.

### AG-11 — Phỏng vấn nhu cầu: LLM phân tích + kho phòng + Jev quyết định (P0)

> **Bổ sung từ nghiên cứu HubHome (§5):** HubHome chỉ có **quick-reply dạng chữ, đặt dưới ô nhập, bấm là gửi lại câu cho agent đọc** (tối đa 7, gợi ý của server trước, chip theo căn đang xem sau), và trong khảo sát A3 nó **không hỏi lại** tên trường. HomeMatch làm hơn: chip **trên đầu** câu trả lời, mang `patch` có cấu trúc, có số căn thật, thứ tự do Jev chấm. Vẫn giữ thêm hàng quick-reply theo ngữ cảnh dưới ô nhập như HubHome (dedup, tối đa 7).

**Mục tiêu:** agent tự phân tích câu nói, phát hiện chỗ mơ hồ và **hỏi lại kiểu HubHome**: câu hỏi ngắn, các lựa chọn trả lời đặt **lên đầu** (chip bấm được), xếp theo khả năng đúng. Chỉ hỏi khi câu trả lời thực sự làm đổi kết quả.

**Jev là gì (đã đọc docs 05/11/2026):** `typesafe/jev-1.14`, mô hình ra quyết định có kiểu trên OpenRouter Decisions API (`POST https://openrouter.ai/api/alpha/decisions`, Bearer = key OpenRouter). Request `{model, state, questions}`; loại câu hỏi `choice` (chọn 1 trong `criteria`), `noul` (đúng/sai), `score` (thang), `box` (vùng ảnh). Trả **nhãn + xác suất từng phương án + confidence + `usage.cost`**, không trả văn bản/giải thích. Giá chỉ tính token vào (~0,042 USD/1M). API alpha, một nhà cung cấp → bắt buộc có đường lui. Docs: https://openrouter.ai/docs/guides/community/jev

**Kiến trúc 3 lớp (mỗi lượt chat `find_room`):**
1. **Phân tích (model chat, structured output).** Mở rộng `Extraction` thành `NeedsAnalysis`: các trường như cũ + `confidence` từng trường + `ambiguities[]`, mỗi mục `{field, interpretations[] (giá trị có cấu trúc + nhãn ngắn)}` + `persona` (`student|worker|family|unknown`) + `implicit_needs[]`. Ví dụ: "4 triệu" → `{rent_cap, monthly_total_cap}`; "gần HUST" → `{radius 2 km, radius 5 km, area Hai Bà Trưng}`; "phòng 2 người" → `{ở ghép, phòng đôi}`. `DemoInterpreter` có luật tương đương cho các mẫu phổ biến.
2. **Dựng lựa chọn từ kho thật (code tất định, `backend/app/clarify.py`).** Với mỗi cách hiểu, áp lên hồ sơ tạm và chạy `catalog.match` (không ghi gì). Gắn số liệu: số căn, giá thấp nhất, khoảng cách điển hình. Loại cách hiểu ra 0 căn (trừ khi tất cả đều 0 → chuyển sang gợi ý nới). Tính **mức ảnh hưởng** = 1 − Jaccard(top 5 của các cách hiểu); nếu < 0,2 thì **không hỏi**, chọn cách hiểu phổ biến nhất và nói rõ giả định.
3. **Quyết định (Jev).** Một câu `choice` với `state` = 3 lượt chat gần nhất **đã qua `agent_guard.redact`** + tóm tắt nháp (không tiền tuyệt đối, không thu nhập), `criteria` = các lựa chọn ở bước 2. Luật:
   - `p_max ≥ 0,80` → nhận cách hiểu đó (`inferred`), tìm luôn, câu trả lời ghi "Mình hiểu là …, sai thì bấm sửa".
   - `0,40 ≤ p_max < 0,80` → hỏi lại; chip xếp theo xác suất giảm dần.
   - `p_max < 0,40` → hỏi câu mở kèm 2 chip phổ biến nhất.
   - Mỗi lượt hỏi **tối đa 1** câu; trước kết quả đầu tiên tối đa **2** câu; nếu nhiều điểm mơ hồ thì chọn điểm có mức ảnh hưởng × (1 − p_max) cao nhất.
   - Ngưỡng 0,80/0,40 và 0,2 hiệu chỉnh trên gold (bước Test).

**Câu hỏi và chip:** lời câu hỏi theo template tiếng Việt theo `field` (không cần LLM); chế độ `openai` có thể cho model chat diễn đạt lại nhưng không được đổi số. Chip luôn có thêm "Khác…" (mở ô nhập) và "Bỏ qua, cứ tìm". Mỗi chip mang `patch` có cấu trúc (`DraftPatch`); bấm chip → `PATCH /sessions/{id}/draft` với evidence `clarify:rN` và trạng thái `confirmed` → FE tự xác nhận và chạy vòng tìm (mở rộng `profileUpdateFromChat` nhận `clarify:`). Không để LLM đọc lại câu chữ của chip.

**API/DTO:** `MessageResult` thêm `clarification: {id, field, question, options:[{id, label, detail, patch, probability}], decided_by: "jev"|"rules"|"fallback"} | null`. FE (`RenterWorkspace`): render chip **trên đầu** khung trả lời, trước phần chữ; bàn phím: số 1–4 chọn nhanh.

**Cấu hình:** `HOMEMATCH_DECISION_MODE=jev|rules` (mặc định `rules` khi `HOMEMATCH_LLM_MODE=demo`, `jev` khi `openai`), `HOMEMATCH_DECISION_MODEL=typesafe/jev-1.14`, timeout 2 s. Client `backend/app/decisions.py` (httpx), có retry 0 lần.

**Đường lui:** Jev lỗi/timeout/HTTP ≠ 200 → dùng xác suất từ `confidence` của bước 1 (luật), ghi `decided_by="fallback"` và mã lỗi; không chặn lượt chat. Ghi chi phí `usage.cost` vào `agent_budget`/`cost_metrics`.

**Bất biến:** tiền vẫn chỉ là gợi ý cho tới khi khách bấm chip hoặc xác nhận; chip ngân sách phải là **mức tuyệt đối** tính bằng code (vd. "Trần tổng tháng 4,5 tr · 31 căn"), không phải câu "thêm 1 triệu". Không tự nới điều kiện cứng: chip nới chỉ xuất hiện như lựa chọn, khách bấm mới áp. Thêm tool `analyze_needs`, `build_options`, `decide_clarification` cho agent `needs` trong `AGENT_TOOLS` và `agent_capability.py` (giới hạn bước vẫn 4/lượt).

**Test:**
- `test_clarify.py`: lựa chọn 0 căn bị loại; ảnh hưởng thấp → không hỏi; ngưỡng p → đúng nhánh; tối đa 1 câu/lượt, 2 câu trước kết quả; patch của chip áp đúng trường và thành `confirmed`.
- Client Jev **giả** trả xác suất cố định; test lỗi/timeout → fallback; không gọi mạng.
- Kiểm `state` gửi Jev không chứa số tiền tuyệt đối, SĐT, email, thu nhập.
- Gold `data/gold/clarify_cases.json` (≥ 40 câu mơ hồ/không mơ hồ HN+HCM, nhãn "nên hỏi?" + lựa chọn đúng). Suite `eval clarify`: precision/recall của quyết định hỏi, accuracy lựa chọn top-1, số câu hỏi trung bình trước kết quả. Chạy live Jev chỉ khi người dùng cho phép (tốn phí nhỏ).
- UI test: chip hiện trên đầu, bấm chip gửi `PATCH` đúng `patch` rồi chạy lại vòng tìm.

**Xong khi:** "Tìm phòng dưới 4 triệu gần HUST" → agent hỏi đúng 1 câu kèm chip có số căn thật (hoặc tìm luôn nếu không mơ hồ), bấm chip → kết quả + bản đồ.

### AG-12 — Phỏng vấn sáng tạo hơn (P1, sau AG-11)

Mỗi mục dùng chung hạ tầng AG-11 (phân tích → lựa chọn từ kho → Jev quyết định → chip có `patch`).

1. **Hỏi bằng bản đồ.** Mơ hồ về khoảng cách ("gần trường") → bản đồ trong workspace vẽ 2–3 vòng bán kính quanh điểm đến (AG-01), mỗi vòng ghi "N căn · từ X tr". Bấm vòng = chọn chip tương ứng. FE: `MapView` nhận `clarification.options` có `geometry`.
2. **Đánh đổi thay vì hỏi trống.** Khi kho ít căn, `clarify.py` tìm cặp tiêu chí xung đột (gần ↔ rẻ, rộng ↔ rẻ, khu ↔ tiện ích) bằng cách chạy match với từng tiêu chí nới riêng; Jev `choice` chọn đánh đổi đáng hỏi nhất. Chip: "Gần trường · 12 căn · từ 3,8 tr" / "Rẻ hơn · 31 căn · từ 2,2 tr · xa thêm ~3 km". Mọi số do code tính.
3. **Thẻ "Mình hiểu bạn thế này".** Sau mỗi lượt, đầu khung chat hiện chip các trường nháp; trường có `confidence < 0,8` hoặc `inferred` có dấu "?". Bấm chip → popover sửa nhanh (giá trị gợi ý từ kho), lưu bằng `PATCH /draft` (`confirmed`).
4. **Hỏi ngược từ hành vi.** Khách lưu hoặc bấm "Không thích" một căn (nút mới trên thẻ căn, `POST /rooms/{id}/feedback {reason?}`) → Jev `choice` phân loại lý do (giá, xa, chật, thiếu tiện ích, khác) trên mô tả căn so với hồ sơ; `p_max ≥ 0,8` → cập nhật ưu tiên mềm (không đổi điều kiện cứng) và nói ra; thấp hơn → hỏi lại kèm chip lý do. Ghi lead cho chủ nhà chỉ khi khách lưu, không khi chê.
5. **Câu hỏi theo vai.** `persona` từ AG-11 (Jev `choice` khi chưa chắc) chọn bộ câu hỏi ưu tiên: sinh viên → ở ghép, gần trường, giờ giấc; đi làm → thời gian đi lại, chỗ để xe; gia đình → số phòng ngủ, trường cho con, an ninh. Không suy vai từ tên; vai chỉ là gợi ý thứ tự câu hỏi, khách sửa được.
6. **Không hỏi lại điều đã nhớ.** Câu đầu phiên mới: memory (đã có, không gồm tiền/điểm đến) hiện thành chip "Dùng lại: Cầu Giấy · studio · có máy giặt?" → bấm là áp vào nháp `confirmed`. Khách đã rút đồng ý ghi nhớ thì không hiện.

**Test:** mỗi mục có test backend (lựa chọn từ kho, không lộ tiền/thu nhập, Jev giả) và UI test chip. **Đo:** đưa vào kịch bản EV-01: số lượt tới kết quả đầu tiên, tỉ lệ khách bấm chip thay vì gõ, điểm tổng hợp.

### AG-01 — Hiểu điểm đến (P0)

> **Bổ sung từ nghiên cứu HubHome (§5):** HubHome geocode qua proxy backend (`/api/goong/geocode`), ghim **mốc** lên bản đồ (pin + đường nét đứt tới căn) và nói lại "Mình hiểu mốc là …"; khảo sát C1 cho thấy nó geocode nhầm "HUST" thành quán "Hust Shop" ở Hoàng Mai → HomeMatch phải **tra danh mục địa danh trước, Goong sau**, ưu tiên loại POI (trường/bệnh viện/KCN) và luôn cho khách bấm sửa mốc.

**Mục tiêu:** "gần HUST / Bách Khoa / ĐH Quốc gia / Times City" thành `destination` có tọa độ để xếp theo khoảng cách.
**Bước:**
1. `data/places.json`: danh mục điểm mốc tĩnh (≥ 60 trường ĐH, bệnh viện, KCN, ga, TTTM ở HN và TP.HCM), mỗi mục `{id, names[], aliases[], city, latitude, longitude, uncertainty_m}`. Nguồn tọa độ ghi trong `data/README.md`. Không gọi geocoder trả phí lúc chạy.
2. `locations.py`: `resolve_place(text) -> Place | None` (fold dấu, alias như "hust", "bk", "bach khoa"). Mirror alias sang `frontend/src/locations.ts` nếu FE cần gợi ý; giữ test đồng bộ hiện có.
3. `Extraction` thêm `destination_text: str | None`; prompt mô tả trường này; `DemoInterpreter` lấy cụm sau "gần/cạnh/quanh".
4. `interview`: nếu `resolve_place` ra kết quả → `draft.destination` (thêm vào `DraftProfile`, `DRAFT_TRACKED_FIELDS`) với `field_status=inferred`, `needs_destination=False`; ghim `city` nếu chưa có.
5. FE `profileFromDraft` và `profileUpdateFromChat` (`frontend/src/profile.ts`) mang `destination` với `max_distance_m` mặc định 3000.
6. Memory **không** lưu destination (bất biến).

**Test:** resolve alias; chat "phòng dưới 4 triệu gần HUST" → hồ sơ có destination HUST, run xếp theo khoảng cách (`components.location` khác 0); thiếu điểm mốc → giữ hành vi cũ.

### MP-01 — Đường đi trên bản đồ (P1, sau AG-01)

> **Bổ sung từ nghiên cứu HubHome (§5):** HubHome có view **Lộ trình** riêng: nhiều phương án ("Lộ trình 1 (Đề xuất)" gắn nhãn TỐI ƯU, LT2…), mỗi phương án km + phút, bấm để đổi tuyến đang vẽ; ghi rõ "theo đường đi" hay "đường chim bay"; nút bật **ảnh vệ tinh** (style `goong_satellite`); nút **"Gần tôi"** (GPS trình duyệt, chỉ khi khách bấm) → "Tìm phòng quanh chỗ bạn" và "Đường đi từ chỗ bạn tới căn đang xem". Thêm cả ba vào MP-01: `alternatives=true` của Goong → mảng phương án; tọa độ GPS **không lưu**, chỉ dùng trong lượt.

**Mục tiêu:** khi hồ sơ có điểm đến (AG-01, vd. HUST), bản đồ trong workspace vẽ **đường đi thực tế** từ căn tới điểm đến, kèm quãng đường và thời gian theo phương tiện; thẻ căn hiện "🛵 3,2 km · 11 phút".

**Nguồn dữ liệu đường đi:** Goong Direction API (`GET https://rsapi.goong.io/Direction?origin=lat,lng&destination=lat,lng&vehicle=bike|car|taxi|hd&api_key=…`), dùng `GOONG_API_KEY` loại **REST** — gọi từ **backend**, key không bao giờ xuống frontend. Thiếu key hoặc Goong lỗi → trả `mode="straight_line"` (đoạn thẳng nét đứt + khoảng cách chim bay, ghi rõ "ước lượng đường thẳng"), không bịa thời gian.

**Backend (`backend/app/routes_map.py`):**
1. `GET /v1/rooms/{room_id}/route?vehicle=bike` (khách đã đăng nhập; điểm đến lấy từ **hồ sơ đã xác nhận** của phiên, không nhận tọa độ tùy ý từ client để tránh biến API thành proxy miễn phí): trả `{mode: "goong"|"straight_line", vehicle, distance_m, duration_s|null, geometry: GeoJSON LineString, origin_accuracy: "approximate"|"exact", uncertainty_m, attribution}`.
2. Giải mã `overview_polyline` (polyline5) thành GeoJSON ở backend.
3. Cache bảng `hm_route_cache` (migration v15): khóa = tọa độ làm tròn 4 chữ số (~10 m) cả hai đầu + vehicle; TTL 7 ngày; giới hạn 60 lượt gọi Goong/khách/giờ.
4. Endpoint lô `POST /v1/sessions/{id}/routes` cho tối đa 5 căn đang hiển thị (gọi song song, có cache) để thẻ căn có số liệu mà không N+1 round trip tới Neon.
5. Riêng tư: chỉ gửi Goong **tọa độ làm tròn**, không gửi tên điểm đến, user id hay nội dung chat; không lưu route theo người dùng (cache theo tọa độ). Ghi vào `docs/kien-truc-trien-khai.md` như một tích hợp ngoài.

**Frontend (`MapView.tsx`, `RenterWorkspace.tsx`):**
1. Marker riêng cho điểm đến (icon trường/công ty + nhãn).
2. Chọn một căn (bấm marker/thẻ) → vẽ route: layer `line` màu thương hiệu, viền trắng; `straight_line` vẽ nét đứt xám. Fit bounds cả căn và điểm đến.
3. Căn có `location_accuracy="approximate"` → vẽ vòng tròn `uncertainty_m` quanh điểm đầu và ghi "vị trí căn gần đúng ~300 m".
4. Bộ chọn phương tiện: Xe máy (mặc định) / Ô tô; chỉ thêm Đi bộ nếu Goong có hồ sơ đi bộ, không tự quy đổi từ đường thẳng.
5. Thẻ căn và bảng so sánh: cột "Đi tới {điểm đến}" = quãng đường + thời gian; so sánh ≤3 căn vẽ cả 3 route với màu khác nhau.
6. Thiếu key tile Goong vẫn chạy trên nền OSM (đã có).

**Liên kết task khác:** AG-12 mục 1 (hỏi bằng vòng bán kính) dùng chung marker điểm đến; câu trả lời của agent có thể nói "Căn số 1 đi xe máy ~11 phút tới HUST" — **số lấy từ endpoint route**, không do LLM ước lượng.

**Không làm ở task này:** dùng thời gian đường đi để **lọc/xếp hạng** (đang dùng chim bay, đã có bất biến và eval). Nếu muốn đổi, mở task riêng, đo lại EV-01 và giữ fallback chim bay.

**Test:** client Goong giả (JSON mẫu có `overview_polyline`) → giải mã đúng LineString; thiếu key/timeout/HTTP lỗi → `straight_line`, `duration_s=null`; cache trúng không gọi lại; vượt hạn mức → 429; khách khác phiên không lấy được route theo hồ sơ của người khác; request gửi Goong không chứa nhãn điểm đến/user id. UI test: chọn căn → layer route được thêm; `straight_line` hiện nhãn ước lượng; vòng gần đúng hiện khi `approximate`. Test không gọi Goong thật.

**Xong khi:** chat "phòng dưới 4 triệu gần HUST" → kết quả + bản đồ có marker HUST; bấm một căn → đường đi xe máy kèm "x km · y phút"; tắt `GOONG_API_KEY` → vẫn hiện đường thẳng có nhãn ước lượng.

### AG-02 — Tiền tương đối trong chat (P0)

**Lỗi:** chip "Nới ngân sách" gửi "nới… thêm 1 triệu" → `rent_budget_hint` đọc thành **1 triệu**.
**Bước:** trong `interview` (không sửa `budget_hint` vì oracle vay đã đóng băng), nhận mẫu tương đối `(len|tang|noi)\s*(them)?\s*<số>` → `draft.budget_hint_vnd = cũ + delta`; "giảm … xuống" tương tự. Không có mức cũ thì hỏi lại, không đoán.
FE: `profileUpdateFromChat` được phép áp `budget_hint` **chỉ khi** lượt chat có `evidence_ref.budget_hint` mới **và** response cờ `budget_explicit=true` (BE trả khi câu chứa mức tiền tuyệt đối hoặc tương đối đã tính). Trợ lý nhắc lại mức mới trong câu trả lời.
**Test:** oracle mới `data/oracles/relative_budget_cases.json` (≥ 10 ca); `eval invariants` vẫn qua.

### AG-03 — Không để vòng đầu rỗng vì thiếu sức chứa (P0)

**Bước:** khi run ra `needs_verification` mà lý do chính là `availability_or_capacity`/`monthly_fees`, câu trả lời của `interview` đặt câu hỏi rõ: "Có N tin thiếu sức chứa/bảng phí. Xem kèm nhãn ước tính?" kèm chip; FE đã tự chạy lại khi khách đồng ý (sửa 04/11). Không bật ngầm `accept_estimated_data`.
Thêm: câu "Kết quả sẽ tự hiện…" ở `_questions` chỉ nói khi thật sự có run mới; nếu nhu cầu không đổi thì nói "Danh sách hiện tại vẫn đúng với nhu cầu".
**Test:** service test với kho thiếu `capacity` → câu hỏi có số tin; đồng ý → run mới có kết quả.

### AG-09 — Handover sang chủ nhà từ câu chat (P0)

> **Bổ sung từ nghiên cứu HubHome (§5):** HubHome có `pendingHandoff` → chuyển khung chat sang **người thật** ngay trong workspace (polling `/api/nguoi-that`), ô nhập đổi thành "Nhắn cho {tên}…". HomeMatch làm tương tự: sau handover, khung chat hiện hội thoại với chủ nhà **ngay trong workspace** (không bắt chuyển trang), có nút quay lại trợ lý.

**Bước:**
1. `fixed_intent`: tách "chat/nói chuyện/gặp **chủ nhà**" thành intent mới `landlord_handover`; "người thật/nhân viên/quản trị" giữ `human_support` (admin).
2. Node `handover`: dùng AG-05 tìm căn; có căn → `conversations.start(...)` (đúng hàm nút "Chat với chủ nhà" đang dùng) và trả `conversation_id`; không rõ căn → hỏi "căn nào?" kèm chip từng căn đang hiển thị.
3. Thêm tool `open_conversation` cho agent `support` trong `AGENT_TOOLS`; cập nhật `Extraction.intent`, `MessageResult.intent`, `agent_capability.py`.
4. FE: response `intent=landlord_handover` → chuyển sang `/tin-nhan` mở đúng hội thoại.
5. Chủ nhà nhận thông báo `conversation_started` (đã có) với ngữ cảnh chỉ gồm band, không thu nhập.

**Test:** intent routing; handover không lộ thu nhập; khách không thể mở hội thoại cho căn ngoài danh sách.

### AG-06 — Đặt lịch trọn trong chat (P1)

> **Bổ sung từ nghiên cứu HubHome (§5):** HubHome trả `pendingBooking(s)` → panel đặt lịch **điền sẵn** căn, ngày, giờ, hình thức (`tan_noi`/`truc_tuyen`) với lưới khung giờ 09:00–19:00; đặt nhiều căn một lần; hủy lịch qua chat. Làm giống: tool `prepare_viewing` trả `pending_booking`, FE mở panel điền sẵn, khách bấm mới tạo.

**Bước:** `_prepare_viewing` hiểu thời gian ("8h tối mai", "thứ 7 lúc 9 giờ", "online") bằng parser tất định `parse_viewing_time(text, now, tz=Asia/Ho_Chi_Minh)`; đủ căn + giờ → trả thẻ xác nhận (căn, giờ, hình thức). Khách bấm "Xác nhận" → FE gọi API viewing hiện có với `idempotency_key`. Agent **không** tự tạo lịch khi khách chưa bấm.
**Test:** ≥ 15 câu thời gian; giờ quá khứ bị từ chối; trùng lịch → thông báo.

### FL-01 — Xem nhà online (P1)

> **Bổ sung từ nghiên cứu HubHome (§5):** sau buổi xem, HubHome hiện panel "Cảm nhận sau khi xem" (gửi vào chat để agent dùng tiếp) và nút "Mở phòng xem trực tuyến". Thêm: sau giờ hẹn, panel cảm nhận → tin nhắn có cấu trúc `{room_id, rating, note}` → agent cập nhật ưu tiên mềm và gợi ý bước tiếp (chốt căn / xem căn khác).

**Bước:** trang `Lịch xem` của khách và chủ nhà: nút "Vào phòng xem online" bật từ 10 phút trước giờ hẹn tới 60 phút sau; mở link Jitsi trong tab mới. `POST /viewings/{id}/join` ghi `joined_at` từng bên (cột mới, migration v15). Sau giờ hẹn, khách được hỏi "Bạn muốn chốt căn này?" (dẫn tới FL-02).
**Test:** cửa sổ thời gian; quyền theo bản ghi; join idempotent.

### FL-02 — Chốt căn online (P1)

**Luồng:** khách bấm "Chốt căn" (sau khi xem hoặc từ thẻ căn) → `POST /listings/{room_id}/reservations` `{move_in_date, occupants, note, idempotency_key}` → chủ nhà `accept|decline` → `accept` tạo **lease nháp** từ báo giá phòng (`pms.create_lease`) và hóa đơn **tiền cọc** → chủ nhà gửi lease → khách review (AG-07) và accept → khách gửi payment claim cọc → chủ nhà xác nhận → phòng `occupancy=deposited`, lead `won`.
**Bước:** bảng `hm_reservations` (status `requested|accepted|declined|cancelled|expired`, hết hạn sau 48 h bằng job), migration v15; endpoint khách/chủ nhà; quyền theo bản ghi; thông báo hai chiều. Không có cổng thanh toán (D-07).
**Test:** máy trạng thái; một phòng chỉ một reservation `accepted`; hết hạn tự động; quyền.

### AG-07 — Review hợp đồng (P1)

> **Bổ sung từ nghiên cứu HubHome (§5):** HubHome có view **"Bản nháp hợp đồng"**: chỉ soạn khi chủ nhà đã khai đủ mục bắt buộc; thiếu thì liệt kê mục thiếu và nút **"Hỏi agent nên hỏi chủ nhà thế nào"**; mục không có dữ liệu ghi "Hai bên tự điền — không có dữ liệu". Áp dụng cùng nguyên tắc cho bản review: mục thiếu hiện rõ, không tự điền thay.

**Mục tiêu:** khách mở lease thấy "Trợ lý đọc hợp đồng": tóm tắt, bảng số liệu, điểm cần lưu ý.
**Bước:**
1. Số liệu (giá, cọc, kỳ hạn, ngày thanh toán, số người) lấy **trực tiếp** từ bản ghi lease; tổng tiền vào ở do `costs.py` tính.
2. Bộ kiểm tất định `lease_checks.py`: cọc > 3 tháng, thiếu điều khoản hoàn cọc, thiếu thời hạn báo trước, phí phát sinh không ghi rõ, khác báo giá tin đăng… mỗi cảnh báo trích đoạn điều khoản và mục cẩm nang liên quan.
3. LLM (tùy chọn, chế độ `openai`) chỉ diễn đạt lại `terms` dễ hiểu; đầu ra không được chứa số khác số trong lease (kiểm bằng regex, sai → bỏ, dùng bản tất định).
4. Agent mới `contract` với tool `review_lease` trong `AGENT_TOOLS`. Ghi rõ "không phải tư vấn pháp lý" (D-08).

**Test:** mỗi luật kiểm có ca dương/âm; LLM bịa số → bị loại; chủ nhà không xem được bản review của khách.

### FL-03 — Nhận nhà (P1)

**Bước:** khi lease `accepted` và cọc đã xác nhận, chủ nhà tạo **biên bản bàn giao**: checklist đồ đạc (mẫu theo `AMENITY_KEYS`), chỉ số điện/nước đầu kỳ (dùng `meter readings`), ảnh hiện trạng (`media.py`), ngày giao chìa. Khách xem, ghi chú, bấm "Xác nhận đã nhận nhà" → lease `active`, phòng `occupied`. Biên bản bất biến sau khi hai bên xác nhận; sửa phải tạo phiên bản mới.
**Bảng:** `hm_handover_reports` (migration v15).
**Test:** bất biến; chỉ số đầu kỳ dùng cho hóa đơn đầu; quyền.

### AU-01 — 15 luồng tự động hóa (P1)

Tạo `backend/app/flows.py`: registry `FLOWS` (id, tên, trigger, người nhận, kênh = in-app notification, dedup key). Admin `/quan-tri/van-hanh` thêm bảng "Luồng tự động" (số lần chạy 7 ngày, lần gần nhất). Mỗi luồng có **một test** tạo trigger và kiểm thông báo đúng người, không trùng.

| ID | Luồng | Trigger | Người nhận | Hiện trạng |
|---|---|---|---|---|
| F01 | Gợi ý mới cần duyệt | run `pending_review` | chủ nhà | có (`landlord_review`) |
| F02 | Căn đã được duyệt/công bố | review approve | khách | có (`rooms_approved`) |
| F03 | Yêu cầu xem phòng | tạo viewing | chủ nhà | có |
| F04 | Phản hồi lịch xem | chủ nhà xác nhận/đổi/từ chối | khách | có |
| F05 | Nhắc lịch xem (offline/online, kèm link) | job, T-2 h | hai bên | có, bổ sung link online |
| F06 | Bắt đầu live chat / tin nhắn mới | handover, message | bên còn lại | có |
| F07 | Phòng đổi giá/trạng thái | sửa phòng | khách đã lưu/xem | có (`room_changed`) |
| F08 | Yêu cầu chốt căn | reservation | chủ nhà | **mới** (FL-02) |
| F09 | Kết quả chốt căn + hết hạn giữ chỗ | accept/decline/job | khách | **mới** (FL-02) |
| F10 | Hợp đồng gửi / được chấp nhận | lease send/accept | khách / chủ nhà | có |
| F11 | Hóa đơn phát hành, sắp đến hạn, quá hạn | invoice, job | khách | có |
| F12 | Khách báo đã thanh toán / chủ nhà xác nhận hoặc từ chối | claim | chủ nhà / khách | có |
| F13 | Bàn giao nhà cần xác nhận / đã nhận nhà | handover report | khách / chủ nhà | **mới** (FL-03) |
| F14 | Sửa chữa: tạo ticket và cập nhật trạng thái | maintenance | bên còn lại | có |
| F15 | Gia hạn hợp đồng sắp hết + chăm sóc lại khách tiềm năng | job | khách / chủ nhà | có (`lease_renewal`, `lead_reengagement`) |

### AG-08 — Hỏi đáp quyền lợi người thuê (P1)

**Bước:**
1. Mở rộng cẩm nang thành `data/handbook/*.md` (≥ 40 mục: cọc và hoàn cọc, tạm trú, chấm dứt sớm, tăng giá, điện nước theo giá nhà nước, sửa chữa, quyền riêng tư, tranh chấp…), mỗi mục có nguồn (điều luật/văn bản), ngày rà soát.
2. Truy hồi: B1 (từ khóa fold dấu + BM25 đơn giản) mặc định; nếu có embedding thì hybrid. Trả top 3 kèm nguồn.
3. Chế độ `openai`: LLM tổng hợp **chỉ từ** các mục truy hồi, bắt buộc trích id mục; câu không có căn cứ → "Chưa có trong cẩm nang" + gợi ý hỏi chủ nhà/admin. Có nhắc nội quy của căn khi câu hỏi gắn căn (AG-05).
4. Gold `data/gold/handbook_qa.json` (≥ 40 câu, gồm câu diễn đạt khác) và suite `eval handbook` (hit@3, tỉ lệ có trích nguồn).

### AG-04 — Tìm bằng ảnh (P1)

> **Bổ sung từ nghiên cứu HubHome (§5):** HubHome nén ảnh ở **client** (cạnh dài ≤1024 px, JPEG chất lượng 0,82, base64) rồi gửi chung request chat; câu mặc định "Tìm căn giống ảnh này giúp mình". Làm giống để giảm dung lượng và độ trễ.

**Bước:**
1. `POST /sessions/{id}/image` (multipart, JPEG/PNG/WebP ≤ 5 MB, kiểm magic bytes như `media.py`). Ảnh **không lưu** quá thời gian xử lý; chỉ lưu kết quả trích xuất.
2. `interpreter.extract_image(bytes)`: chế độ `openai` gửi ảnh tới model vision (`HOMEMATCH_VISION_MODEL`, mặc định = `OPENAI_MODEL`) qua `chat_completions` với `image_url` base64; đầu ra theo schema `ImageExtraction {room_type, amenities[], style_text}`. Chế độ demo trả "chưa hỗ trợ ảnh ở chế độ offline" (không giả kết quả).
3. Kết quả đi vào nháp như một lượt chat (`evidence_ref = "image:rN"`, `inferred`); FE `profileUpdateFromChat` coi `image:` như `chat:`.
4. FE: nút ảnh cạnh micro trong composer, xem trước, hiện "Mình thấy: studio, có cửa sổ, nội thất…" để khách sửa.
5. Ngân sách LLM: tính vào `agent_budget` của phiên.

**Test:** client giả cho vision; file sai định dạng/quá cỡ bị chặn; ảnh không xuất hiện trong DB hay log.

### PR-01 — Lịch sử trò chuyện (P1)

> **Bổ sung từ nghiên cứu HubHome (§5):** HubHome lưu lịch sử 15 cuộc gần nhất **trên máy**, lệnh `/moi` (bắt đầu lại, cuộc cũ vẫn xem được), `/tieuchi` (xem và gỡ tiêu chí đang lọc), `/quen` (quên hồ sơ, có xác nhận, không xóa lịch sử và lịch hẹn). HomeMatch lưu ở server (PR-01) và thêm ba lệnh này vào composer (WS-03).

**BE:** `GET /me/conversations/ai` → danh sách phiên AI của khách (`session_id`, câu đầu đã che PII, số lượt, thời gian, trạng thái run); `GET /me/conversations/ai/{session_id}` → các lượt từ `hm_chat_transcripts` (đã PII-mask, tôn trọng retention). Chỉ chủ phiên xem được.
**FE:** trang cá nhân tab "Lịch sử trò chuyện"; bấm một phiên → mở lại `/tro-ly-ai` với phiên đó (thay cho bản lưu `sessionStorage`). Khung chat tải lượt từ server.
**Test:** quyền; transcript quá hạn không trả; PII đã che.

### PR-02 — Trang cá nhân hợp nhất (P1)

`/nguoi-thue/ca-nhan` gồm 4 tab: **Lịch sử trò chuyện** (PR-01), **Căn đã xem** (`/rooms/viewed`), **Căn đã lưu** (`/rooms/saved`), **Nhu cầu tìm nhà** (`GET /me/needs`: các hồ sơ đã xác nhận từ `hm_profile_snapshots`, mới nhất trước, **không** hiện thu nhập; nút "Tìm lại với nhu cầu này" tạo phiên mới và xác nhận). Gộp mục `/nguoi-thue/da-luu` vào đây (giữ redirect).
**Test:** UI test từng tab; `/me/needs` không có `monthly_income_vnd`.

### AG-10 — Nhanh hơn (P2)

**Bước:**
1. Đo `latency_ms` mỗi lượt và mỗi bước (route, LLM, rank, publish) vào `metrics`, hiện p50/p95 ở `/admin/metrics`.
2. Bỏ LLM khi không cần: câu chỉ có số tiền/quận/loại phòng đã khớp luật thì dùng kết quả luật (`fixed_intent` + `DemoInterpreter`), chỉ gọi LLM khi luật không chắc.
3. Cache trích xuất theo `(hash(text đã che), draft_revision)` trong phiên.
4. `catalog.match`: lọc theo `city` từ chỉ mục trong bộ nhớ trước khi đánh giá từng phòng (kho 2.779 căn).
5. FE: hiện trạng thái "Đang tìm…" ngay khi gửi; không chờ `GET /sessions` thêm một vòng khi response đã có session.

**Mục tiêu:** p50 lượt chat ≤ 2,5 s (chế độ openai), ≤ 300 ms (demo); thời gian từ câu đầu tới kết quả ≤ 6 s.

### EV-01 — Thước đo "39% → 60%" (P2)

Con số 39% **chưa được đo**; phải đo lại trên MVP rồi mới công bố.
**Định nghĩa điểm chất lượng agent (0–100%)** trên bộ kịch bản đóng băng `eval/scenarios/agent_e2e.json` (≥ 40 kịch bản nhiều lượt, HN và HCM, gồm điểm đến, nới tiêu chí, đặt lịch, handover, hỏi đáp):

| Thành phần | Trọng số | Đo |
|---|---|---|
| Hoàn thành nhiệm vụ (đi tới bước mong đợi, không cần sửa tay) | 0,35 | tất định theo kịch bản |
| Trích xuất đúng trường (city, area, type, people, budget, destination) | 0,20 | so gold |
| Gợi ý tốt: tỉ lệ kịch bản có ≥ 1 căn đúng điều kiện cứng trong top 5 + nDCG@5 khi có nhãn | 0,25 | `eval ranking` + nhãn người khi có |
| Hỏi đáp: hit@3 có trích nguồn | 0,10 | `eval handbook` |
| Tốc độ: tỉ lệ lượt ≤ ngưỡng AG-10 | 0,10 | `measurements` |

**Bước:** `eval agent-score --baseline <git-ref>` chạy cùng bộ kịch bản trên MVP (commit `3f46bb3`) và bản hiện tại, chế độ demo (offline, miễn phí) và — khi người dùng cho phép — chế độ openai. Báo cáo ở `eval/runs/development/agent_score.json` + bảng trong `report.md`. Không gộp số offline và live.

### EV-02 — Nâng điểm tới ≥ 60% (P2)

Lặp: chạy EV-01 → xem 10 kịch bản tệ nhất → sửa prompt, luật, tool → chạy lại. Không đổi bộ kịch bản sau khi đóng băng (đổi thì tăng version và đo lại baseline).

### E2E-01 — Demo trình duyệt (P2)

Viết lại `docs/kich-ban-demo.md` theo §0.1 và quay lại trên localhost (Neon + OpenRouter): giọng nói → kết quả + bản đồ → đặt lịch online → vào phòng Jitsi → chốt căn → review hợp đồng → cọc → nhận nhà → trang cá nhân. Ghi chú mọi bước còn giả lập (thanh toán, email).

---

## 4H. Harness của agent (lập 06/11/2026)

**Harness** = mọi thứ bao quanh LLM để nó chạy như một agent đáng tin: vòng lặp và giới hạn, ngữ cảnh, bộ tool và hợp đồng tool, lớp hỏi lại, guardrail vào/ra, ngân sách và tốc độ, stream, trace, bộ nhớ, đánh giá và tái lập. Phần này hoàn thiện harness cho AG-13; các task chức năng P1 (AG-06, MP-01, …) chỉ việc **thêm tool** theo hợp đồng ở HN-03.

**Hiện trạng đã kiểm (06/11, chạy live `gpt-6-luna` + Jev):** agent tự gọi `find_place → update_needs → search_rooms → confirm_and_search → ask_user`, hiểu đúng HUST, mở bản đồ có ghim; nhưng lượt mất 16,4 s; `ask_user` trả lựa chọn do LLM tự viết; Jev chỉ chạy khi model **không** gọi `ask_user`; client Jev gửi sai định dạng (đã sửa trong working tree, chưa commit: `decisions.py`, `test_clarify.py`).

**Sơ đồ đích của một lượt:**
```
FE ─POST /v1/sessions/{id}/turn (stream)─► Cổng vào (HN-06) ─► Dựng ngữ cảnh (HN-04)
   ─► Vòng lặp (HN-01): LLM ⇄ ToolBox (HN-03) ── tool "ask_user" ─► Lớp hỏi lại kho+Jev (HN-02)
   ─► Hậu kiểm ra (HN-06) ─► AgentTurn + stream bước ─► Trace bền (HN-05) ─► Eval/replay (HN-08/09)
```

### HN-00 — Commit sửa định dạng Jev (P0, làm ngay)
Commit `backend/app/decisions.py` + `backend/tests/test_clarify.py` (định dạng Decisions API: `state` object, `questions.clarify.{type,instructions,criteria{id:nhãn}}`, đọc `answers.clarify.{choice,probabilities}`, xếp chip theo xác suất Jev). Bằng chứng live 06/11: HTTP 200, 0,85–1,14 s, ~0,00002 USD/lần, `decided_by="jev"`. Ghi vào `docs/trang-thai-trien-khai.md`.

### HN-01 — Vòng lặp: giới hạn, tốc độ, kết thúc rõ ràng (P0)
1. **Tham số model** qua env: `HOMEMATCH_AGENT_REASONING=low|medium|high` (mặc định `low`), `HOMEMATCH_AGENT_MAX_TOKENS` (mặc định 800), `temperature` không đặt nếu model reasoning. Truyền `parallel_tool_calls=true`.
2. **Thực thi tool song song** khi một lượt model trả nhiều tool call **chỉ đọc** (`find_place`, `search_rooms`, `room_details`, `estimate_cost`, `search_handbook`, `route`…); tool **ghi** (`update_needs`, `confirm_and_search`, `prepare_viewing`, `open_landlord_chat`) luôn tuần tự theo thứ tự model gọi. Phân loại bằng cờ `writes: bool` trong registry (HN-03).
3. **Đường tắt tất định:** câu mà luật đã hiểu đủ (fixed_intent, hoặc DemoInterpreter trích đủ city/area + không mơ hồ) → bỏ vòng LLM, chạy thẳng `update_needs → confirm_and_search` bằng code, LLM chỉ viết 1 câu trả lời (hoặc template). Ghi `agent_mode="fast_path"`.
4. **Gộp lượt cuối:** sau `confirm_and_search` thành công, không quay lại LLM chỉ để “nói lại” nếu đã có template đủ ý; nếu cần LLM viết câu trả lời thì gọi **không kèm tools** (rẻ, nhanh).
5. **Giới hạn:** 6 bước tool, 4 lần gọi LLM/lượt, 45 s/lượt (tool > 8 s → lỗi có cấu trúc `tool_timeout`). Vượt → `SAFE_REPLY` + trạng thái nháp vẫn lưu.
6. **Đo** thời gian từng lần gọi LLM, từng tool, tổng lượt → vào trace (HN-05).
**Mục tiêu:** p50 ≤ 4 s, p95 ≤ 10 s với câu tìm phòng thường (đo trên 20 câu, HN-08). **Test:** model giả trả 2 tool đọc cùng lúc → chạy song song (đo bằng tool giả có sleep); tool ghi tuần tự; fast path không gọi LLM tools; timeout tool → lỗi cấu trúc.

### HN-02 — `ask_user` đi qua lớp hỏi lại kho + Jev (P0)
**Lỗi hiện tại:** model gọi `ask_user(question, options[])` với lựa chọn tự viết → bỏ qua `clarify.py`/Jev; lớp AG-11 chỉ chạy khi model không hỏi.
1. Đổi schema: `ask_user(field: "destination_radius"|"budget_scope"|"area"|"room_type"|"people"|"other", question?: str)` — model chọn **điểm cần hỏi**, không tự đặt lựa chọn (trừ `other`, khi đó tối đa 4 lựa chọn chữ, đánh dấu `source="model"`).
2. Harness gọi `clarify.build_clarification(field=…)` → lựa chọn từ kho thật (số căn, giá từ) → `decisions.decide` (Jev khi `HOMEMATCH_DECISION_MODE=jev`) → chip có `patch`, xếp theo xác suất; Jev `p ≥ 0,8` → tự áp + nói giả định, **không** hỏi.
3. Thêm `area` (top 3 quận có nhiều căn khớp quanh điểm đến/thành phố) và `room_type`, `people` vào `clarify._interpretations`.
4. **Hỏi trước khi tìm:** system prompt + harness: nếu còn điểm mơ hồ có `impact ≥ 0,2` thì `confirm_and_search` trả lỗi cấu trúc `needs_clarification` kèm field gợi ý → model phải gọi `ask_user`. Mỗi lượt tối đa 1 câu hỏi, trước kết quả đầu tiên tối đa 2.
5. Bán kính mặc định 3 km (đang tự đặt) chỉ dùng khi Jev/luật quyết định không cần hỏi; nói rõ trong câu trả lời.
**Test:** model giả gọi `ask_user(field="destination_radius")` → DTO `clarification.options` có `count`, `patch`, `decided_by`; Jev giả p=0,9 → không hỏi, nháp ghi `clarify:auto`; `confirm_and_search` khi còn mơ hồ → lỗi `needs_clarification`. **Live:** "phòng dưới 4 triệu gần HUST" trên kho Neon → hỏi bán kính với chip có số căn thật (ghi bằng chứng).

### HN-03 — Registry tool và hợp đồng tool (P0)
1. `backend/app/agent_tools.py`: mỗi tool khai báo **một lần**: `name`, `agent` (needs/finance/ranking/support/handbook/booking/contract/map), `description`, Pydantic `Args` → JSON schema tự sinh, `writes`, `timeout_s`, `view` (view workspace mở khi tool thành công, thay `pick_view` if-else), `summarize(result) -> str` (dòng bước hiển thị, không PII), `redact(result)`.
2. `AGENT_TOOLS`/`agent_capability.py` sinh từ registry; test đối chiếu không lệch.
3. Kết quả tool chuẩn hóa: `{"ok": true, "data": …}` hoặc `{"ok": false, "error": code, "message": …, "hint": …}` (hint giúp model tự sửa, vd. "gọi find_place trước").
4. Tool ghi nhận `idempotency_key = turn_id + tool + hash(args)` để retry stream không tạo bản ghi đôi.
5. Hướng dẫn thêm tool mới (cho AG-06, MP-01, AG-07, …): 1 file, 1 test hợp đồng tự sinh (schema hợp lệ, `summarize` không lộ PII, chạy với args mẫu).
**Test:** test tham số hóa chạy mọi tool trong registry với args mẫu; schema gửi model khớp Pydantic.

### HN-04 — Ngữ cảnh và bộ nhớ hội thoại (P0)
1. Ngữ cảnh mỗi lượt gồm: nháp + hồ sơ (không thu nhập, không tiền tuyệt đối ngoài trần khách nêu), **tóm tắt hội thoại** (≤ 600 token, cập nhật mỗi 4 lượt bằng 1 lần gọi LLM rẻ, lưu `hm_sessions.summary_json`), 6 lượt gần nhất, **workspace** (view, căn đang chọn, ≤30 căn hiển thị dạng `{room_id, title, giá, khoảng cách}`), **kết quả run hiện tại** (top 5 rút gọn), bộ nhớ sở thích (`memory.recall`, chỉ khi khách đồng ý, không tiền/điểm đến).
2. Đếm token ngữ cảnh, cắt theo `HOMEMATCH_CONTEXT_TOKEN_CAP` (đã có biến 4000) theo thứ tự ưu tiên: hướng dẫn > nháp > workspace > tóm tắt > lượt cũ.
3. Tiền trong lượt chat vẫn thay placeholder trước khi tới LLM (giữ nguyên).
**Test:** ngữ cảnh không có `monthly_income_vnd`, SĐT, email; vượt cap → cắt đúng thứ tự; "căn thứ 2" hiểu được nhờ workspace.

### HN-05 — Trace bền và quan sát (P0)
1. Bảng `hm_agent_turns` (migration): `turn_id, session_id, user_id, started_at, duration_ms, agent_mode (loop|fast_path|graph_fallback), model, llm_calls, input_tokens, output_tokens, cost_usd, decided_by, outcome (answered|asked|handover|safe_reply|error), error_code` và `hm_agent_steps`: `turn_id, seq, kind (llm|tool|guard|decision), name, duration_ms, ok, summary` (đã redact). Không lưu prompt thô hay câu trả lời thô (transcript đã PII-mask nằm ở `hm_chat_transcripts`, giữ retention cũ).
2. Thay `self._traces` (RAM) bằng đọc bảng; `GET /admin/agent-turns` (admin, có audit) + trang `/quan-tri/van-hanh` thêm bảng lượt agent, p50/p95, tỉ lệ fallback, chi phí/ngày.
3. Chi phí: lấy `usage` của OpenRouter (có `cost` khi bật `usage: {include: true}`) và `usage.cost` của Jev; quy VND qua `cost_metrics.py`.
**Test:** mỗi lượt sinh đúng 1 dòng turn + N dòng step; không có PII/tiền trong `summary`; renter không đọc được trace.

### HN-06 — Guardrail vào/ra và ngân sách (P0)
1. **Ngân sách:** đổi đơn vị từ "lần gọi LLM" sang **lượt chat** (`HOMEMATCH_SESSION_TURN_BUDGET`, mặc định 60) + trần chi phí phiên (`HOMEMATCH_SESSION_COST_CAP_USD`, mặc định 0,05). Hết → thông báo rõ, gợi ý dùng form; tool tất định vẫn chạy.
2. **Vào:** giữ `screen_injection`; thêm giới hạn 2000 ký tự, ảnh ≤ 5 MB (AG-04); nội dung tool trả về (mô tả tin đăng) bọc trong khối `untrusted` và lọc mẫu injection trước khi đưa lại model.
3. **Ra:** giữ hậu kiểm số; thêm kiểm: không nhắc thu nhập; không khẳng định "đã đặt lịch/đã liên hệ/đã thanh toán" nếu không có tool ghi tương ứng thành công trong lượt; không tuyên bố đã nới điều kiện cứng; tên căn/giá chỉ từ kết quả tool. Vi phạm → thay câu template + ghi `guard` step.
4. **Tool ghi cần xác nhận người dùng** (`prepare_viewing`, chốt căn, gửi claim) chỉ trả bản **chuẩn bị**; thao tác thật do FE gửi khi khách bấm (giữ nguyên tắc).
**Test:** 20 lượt liên tiếp không hết ngân sách; lượt vượt trần chi phí → 429 thân thiện; câu "đã đặt lịch" không có tool → bị thay; injection trong mô tả tin không đổi hành vi (test với tin giả chứa "bỏ qua hướng dẫn…").

### HN-07 — Đường lui và độ bền (P1)
Thứ tự lùi: model chính → (lỗi 5xx/timeout) thử lại 1 lần với backoff 0,5 s → model dự phòng `HOMEMATCH_AGENT_FALLBACK_MODEL` (tùy chọn) → graph cũ (`graph_fallback`) → template. Jev lỗi → luật (đã có). Goong lỗi → đường thẳng (MP-01). Mỗi lần lùi ghi vào trace. Circuit breaker: 5 lỗi liên tiếp trong 60 s → bỏ qua provider đó 120 s. **Test:** từng mức lùi bằng client giả.

### HN-08 — Bộ kịch bản và chấm điểm agent (P1, gắn EV-01)
1. `eval/scenarios/agent_e2e.json` (≥ 40 kịch bản nhiều lượt, HN/HCM): mỗi lượt có `user`, kỳ vọng `tools_called ⊇`, `tools_forbidden`, `view`, `clarification.field`, `draft` (trường kỳ vọng), `must_not_contain` (thu nhập, số bịa).
2. Lệnh `python -m eval agent --mode demo|live --model …` chạy kịch bản qua `run_turn`, xuất `eval/runs/<run>/agent.json`: tỉ lệ hoàn thành, độ chính xác trường nháp, tỉ lệ hỏi đúng lúc (precision/recall so với `data/gold/clarify_cases.json`), số câu hỏi trước kết quả, p50/p95, chi phí. Đây là đầu vào điểm tổng hợp EV-01.
3. Thêm suite `eval clarify` (AG-11 còn thiếu): chạy lớp 2+3 trên 40 ca gold, báo cáo theo `decided_by`.
**Live chỉ chạy khi người dùng cho phép** (ước chi phí in trước khi chạy).

### HN-09 — Ghi/phát lại lượt live (P1)
Chế độ `HOMEMATCH_AGENT_RECORD=path`: ghi request/response model + Jev (đã redact) thành cassette JSON; test và eval dùng `HOMEMATCH_AGENT_REPLAY=path` để phát lại **không gọi mạng** — tái lập được bằng chứng live trong luận văn, không tốn phí khi chạy lại. **Test:** ghi rồi phát lại cho cùng kết quả.

### HN-10 — Stream câu trả lời và trải nghiệm chờ (P1)
Sau các bước tool, stream **từng đoạn chữ** của câu trả lời cuối (`{"type":"delta","text":…}`) khi gọi LLM không kèm tools; FE hiện dần. Hậu kiểm số chạy trên toàn câu trước sự kiện `done`; nếu vi phạm, gửi `{"type":"replace","text":…}`. Hiện trạng "Đang … — bước N" theo bước thật (đã có).

### HN-11 — Phân vai agent trong harness (P1)
Giữ một vòng lặp nhưng **lọc bộ tool theo pha**: phỏng vấn (needs + clarify), kết quả (ranking, cost, map, trust), giao dịch (booking, contract, handover). Pha suy từ trạng thái phiên (chưa có run / có run / đã có lịch-lease) → ít tool hơn mỗi lượt → model chọn đúng hơn, prompt ngắn hơn. Ghi `phase` vào trace. **Test:** pha "chưa có run" không thấy tool hợp đồng.

### HN-12 — Tài liệu harness (P1)
Viết lại `docs/thiet-ke-agent.md` và `docs/nghiep-vu-va-harness.md` theo kiến trúc mới: sơ đồ lượt, registry tool, lớp hỏi lại kho+Jev, guardrail, trace, eval; cập nhật `CLAUDE.md` mục "Agents and memory". Đây cũng là chương kiến trúc agent cho luận văn.

**Thứ tự thực hiện harness:** HN-00 → HN-03 → HN-02 → HN-01 → HN-04 → HN-06 → HN-05 → HN-08 → HN-09 → HN-07 → HN-11 → HN-10 → HN-12. Sau HN-03, các task chức năng P1 thêm tool song song được.

**Xong harness khi:** (1) "Tìm phòng trọ dưới 4 triệu gần HUST" live trên kho Neon: hỏi bán kính bằng chip có số căn thật, Jev xếp thứ tự, bấm chip → kết quả + bản đồ, tổng thời gian lượt đầu ≤ 6 s; (2) 20 lượt liên tiếp trong một phiên không hết ngân sách; (3) `eval agent --mode demo` chạy đủ 40 kịch bản, báo cáo p50/p95/chi phí; (4) mọi lượt có trace bền xem được ở trang admin; (5) `bash infra/check-local.sh` exit 0.

## 5. Nghiên cứu HubHome (05/11/2026)

**Phương pháp:** đọc trang công khai `hubhome.vn`, `/tro-ly-ai` và 13 file JS giao diện công khai (`/_next/static/chunks/*`), kết hợp các khảo sát trước trong `docs/khao-sat-hubhome-*.md` (01/10, 03/11, 04/11). Không đăng nhập, không gửi tin nhắn tới agent của họ, không cào dữ liệu tin. `robots.txt` của HubHome: `use=reference`, `ai-train=no` — chỉ dùng để tham khảo thiết kế, không sao chép tài sản (logo, mascot, câu chữ), không huấn luyện mô hình. Mọi điều dưới đây suy từ code phía client; logic server của họ **không** được kiểm chứng.

**Kiến trúc agent nhìn từ client:**

| Khía cạnh | HubHome | HomeMatch hiện tại | Task |
|---|---|---|---|
| Endpoint | Một `POST /api/ai-assistant`, stream NDJSON: `{loai:"buoc"}` từng bước rồi `{loai:"xong",data}`; timeout 75 s, thử lại 2 lần | Nhiều endpoint, trả một lần | WS-02 |
| Ngữ cảnh gửi lên | `message`, `image`, 8 lượt gần nhất, `criteria`, `journey`, `dossiers`, `shortlist`, `focus` (≤4 căn), `workspace` (view, căn chọn, ≤30 căn đang hiện, điểm đến, lịch), `gps`, đồng ý lưu hồ sơ | Chỉ `text` | WS-01, AG-13 |
| Phản hồi | Agent **chọn view**: `detail, gallery, decision, cost, nearby, trust, hop_dong, area, route, compare, saved`; `actions` OPEN/CLEAR/KEEP_WORKSPACE; `anchor`, `near_miss`, `criteria`, `pendingBooking(s)`, `pendingHandoff`, `suggestedPrompts`, `trace` | Văn bản + câu hỏi; FE tự quyết | WS-01 |
| Các bước | Hiện trực tiếp "bước N", rồi "Đã xử lý qua N bước" (router, tool, ghim bản đồ, guardrail; bước hệ thống tự thêm có nhãn) | 4 bước dựng lại sau khi run xong | WS-02 |
| Hỏi lại / lựa chọn | Quick-reply chữ dưới ô nhập (≤7, server trước, chip theo căn sau), bấm = gửi câu; không thấy câu hỏi lại có cấu trúc | Chỉ hỏi "thành phố nào?" | AG-11 (làm hơn) |
| Địa điểm | Proxy `/api/goong/geocode`, `/api/quan-gan` (quận từ GPS), `/api/dia-gioi` (ranh giới); ghim mốc + đường nét đứt; C1 geocode nhầm HUST | Không có | AG-01, MP-01 |
| Đường đi | View Lộ trình: nhiều phương án, km/phút, "theo đường đi"/"chim bay", vệ tinh; "Đường đi từ chỗ bạn" (GPS) | Không có | MP-01 |
| Quanh căn / khu vực | View tiện ích xung quanh (km, phút đi bộ, chim bay), phân tích khu vực | Không có | MP-02 |
| Nhận xét chủ động | Mở căn → `/api/can/doi-chieu` so với nhóm, chèn tin nhắn + chip | Không có | AG-14 |
| Tin cậy | Nhãn "Chính chủ đã xác minh / Chưa xác minh", view tín hiệu tin cậy, báo tin sai | Không có | AG-15 |
| So sánh | ≤4 căn, giá/m², nhãn "rẻ nhất", "đáng tiền", "Tổng kết nhanh — Phù hợp nếu bạn muốn…" | ≤3 căn, bảng chi phí | (bổ sung vào so sánh hiện có) |
| Đặt lịch | Panel điền sẵn từ chat, lưới giờ 09:00–19:00, tại nơi/trực tuyến, nhiều căn, hủy qua chat, cảm nhận sau xem | Form, chat chỉ "chuẩn bị" | AG-06, FL-01 |
| Hợp đồng | Bản nháp chỉ khi chủ nhà khai đủ; liệt kê mục thiếu; "Hỏi agent nên hỏi chủ nhà thế nào" | Lease click-accept, không có trợ lý | AG-07 |
| Người thật | `pendingHandoff` → chat người thật ngay trong workspace | Trang Tin nhắn riêng | AG-09 |
| Ảnh / giọng nói / GPS | Ảnh nén client ≤1024 px; Web Speech vi-VN; "Gần tôi" | Giọng nói có; ảnh, GPS chưa | AG-04, WS-03 |
| Phản hồi | 👍/👎 từng câu và **từng tin** gửi server (`/api/feedback`) | 👍/👎 câu, chỉ lưu máy | EV-01 (nhãn relevance) |
| Bộ nhớ | Hồ sơ trên máy 30 ngày khi đồng ý, `/quen`, lịch sử 15 cuộc | Memory server có đồng ý | PR-01, WS-03 |

**HomeMatch giữ khác biệt có chủ đích:** tiền chỉ do `costs.py` tính và có oracle; mọi lựa chọn hỏi lại lấy từ kho thật và có `patch` cấu trúc (HubHome chỉ gửi lại chữ); Jev quyết định khi nào hỏi; dữ liệu tin cậy không ảnh hưởng xếp hạng; không lưu GPS.

**Giới hạn của nghiên cứu này:** chỉ đọc code client đã build; tên trường suy từ code rút gọn; chưa quan sát hành vi thật của từng view trong phiên này (không có trình duyệt). Trước khi đưa vào luận văn, nên xác nhận lại bằng phiên dùng thật có ảnh chụp (bổ sung vào `docs/khao-sat-hubhome-giao-dien-ux.md`).

## 6. Điều kiện hoàn tất chung cho mỗi task

1. `bash infra/check-local.sh` exit 0 (pytest, vitest, typecheck, build, demo, smoke).
2. API mới cập nhật `docs/api-contract.md` và sinh lại `docs/openapi.json`; trạng thái FR cập nhật trong `docs/yeu-cau-san-pham.md` và `docs/trang-thai-trien-khai.md` (ghi rõ đã chạy gì, không tuyên bố live/PG/E2E nếu chưa chạy).
3. Migration có test SQLite; chạy PG khi có `HOMEMATCH_TEST_DATABASE_URL`.
4. Prettier cho file FE đã sửa (chỉ phần mình sửa).

## 7. Ngoài phạm vi / để sau

- Cổng thanh toán, email/SMS thật, chữ ký điện tử pháp lý, đăng mạng xã hội tự động (D-07, D-08).
- Deploy Railway/Docker (D-09).
- Cập nhật catalog Chợ Tốt định kỳ (CR-01..07 trong plan cũ): làm sau EV-01. Bản sao plan cũ không nằm trong repo; lấy lại `README/agent/be/fe/data.md` bằng `git show HEAD:docs/coding-plan/<file>`.
