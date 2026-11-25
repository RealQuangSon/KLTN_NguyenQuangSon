# Thiết kế AI Agent HomeMatch

Tài liệu này mô tả kiến trúc agent của HomeMatch, có sơ đồ luồng một lượt, đối chiếu trực tiếp với code. Biến môi trường ở [env-inventory.md](../infra/env-inventory.md).

## 1. Nguyên tắc (bất biến)

1. **LLM hiểu ngôn ngữ, code quyết định.** Tiền chỉ do `costs.py` tính (Decimal, VND); lọc cứng, xếp hạng, quyền và việc công bố là code tất định. LLM trích xuất, suy luận ngữ nghĩa, chọn tool và diễn đạt — mọi con số trong câu trả lời phải đến từ câu của khách hoặc kết quả tool (hậu kiểm `check_numbers`, sai → thay bằng câu template).
2. **Không còn bước chủ nhà duyệt** (quyết định D-10, 05/11/2026): kết quả công bố ngay sau khi xếp hạng, đúng phiên bản hồ sơ và kho hiện tại; chủ nhà biết có khách khi khách nhắn tin hoặc đặt lịch xem (lead bỏ 19/11/2026), không chặn khách.
3. **Điều kiện cứng không tự nới.** Agent chỉ đề nghị lựa chọn (chip làm rõ có `patch` cấu trúc); khách bấm mới áp với trạng thái `confirmed`, evidence `clarify:rN`.
4. **Thu nhập là bất kỳ.** `monthly_income_vnd` không bao giờ tới prompt, Jev, trace, DTO chủ nhà hay cassette. Văn bản tới LLM/Jev đi qua `agent_guard.redact` (che SĐT, email, tiền).
5. **Dữ liệu người dùng là dữ liệu, không phải lệnh.** Tin nhắn khách bị `screen_injection` sàng (nghiêm trọng → cách ly lượt); dữ liệu tool (mô tả tin đăng) được `neutralize_untrusted` vô hiệu giá trị chứa mẫu chèn lệnh rồi bọc khối *untrusted* trước khi trả model.
6. **Một worker API, tất định ở biên.** Concurrency dùng revision/CAS/idempotency key (`hm_agent_requests`, `hm_agent_tool_calls`).

## 2. Sơ đồ một lượt chat

```
FE ──POST /v1/sessions/{id}/messages/stream (NDJSON)──►
┌──────────────────────────────────────────────────────────────────────┐
│ CỔNG VÀO (HN-06)                                                     │
│  screen_injection (cách ly nếu nghi injection) · giới hạn 2000 ký tự │
│  · budget.ensure_turn (60 lượt/phiên + trần 0,05 USD)                │
├──────────────────────────────────────────────────────────────────────┤
│ ĐỊNH TUYẾN                                                           │
│  human_support/handover/handbook hoặc có cost_input ──► graph luật   │
│  ANALYST ĐẦU VÀO (HN-13, input_analyst.py, chỉ nhánh openai):        │
│      một request Jev hai câu choice — route (needs|finance|          │
│      ranking|other) + clarity (clear|reason); state chỉ tin nhắn     │
│      + nháp đã tách tiền, pha, cờ có kết quả; timeout 3 s;           │
│      p(route)<0,6 → luật · Jev lỗi → luật (decided_by=fallback)      │
│      · cost usage.cost cộng trần phiên · off → giữ hành vi cũ        │
│  simulate_finance/calculate_cost (không cost_input): có kết quả →    │
│      agent TÀI CHÍNH, chưa có → graph luật (không tốn lượt Jev)      │
│  route ranking: có kết quả → agent XẾP HẠNG, chưa có → agent nhu cầu │
│  route needs/other: clarity=reason → thẳng agent nhu cầu; clear →    │
│      FAST PATH (HN-01): patch → lớp hỏi lại → confirm — 0 LLM        │
│  còn lại ──► VÒNG LẶP AGENT (HN-01) với role của agent được chọn     │
├──────────────────────────────────────────────────────────────────────┤
│ VÒNG LẶP (tối đa 4 lần gọi LLM / 6 bước tool / 45 s)                 │
│  NGỮ CẢNH (HN-04): nháp+hồ sơ ▸ workspace(≤30 căn+top5) ▸ bộ nhớ ▸   │
│  tóm tắt (mỗi 4 lượt, hm_sessions.summary_json) ▸ 6 lượt gần nhất    │
│  — cắt theo HOMEMATCH_CONTEXT_TOKEN_CAP đúng thứ tự ưu tiên          │
│  LLM ⇄ TOOLBOX (HN-03): specs theo PHA (HN-11) ∩ ROSTER role         │
│  (HN-13) · tool chỉ đọc chạy SONG SONG, tool ghi tuần tự ở           │
│  thread chính · timeout tool 8 s → tool_timeout                      │
│  ── ask_user(field) ──► LỚP HỎI LẠI (HN-02):                         │
│      build_clarification (kho thật: số căn, giá từ) → Jev/luật       │
│      (decisions.py, ngưỡng 0,85/0,40/0,2) → chip có count/patch/     │
│      decided_by; luật không tự áp bán kính                           │
│  ── confirm_and_search ──► preflight hỏi lại → confirm → công bố     │
│  ── chốt lượt bằng template (số từ tool), không gọi LLM thêm         │
├──────────────────────────────────────────────────────────────────────┤
│ BÀN GIAO XẾP HẠNG (HN-13, phụ): lượt vừa công bố run mới → MỘT lần   │
│  gọi model không tool, dữ liệu top căn có cấu trúc (tên, mã, tổng    │
│  tháng, tiền vào ở, diện tích, lý do, đánh đổi, cờ xác minh) viết    │
│  phần giải thích; qua guard + hậu kiểm (nguồn = đúng JSON đã cấp);   │
│  mọi lỗi/hết deadline/hết ngân sách → giữ câu mẫu, không 429;        │
│  KHÔNG tính vào llm_calls (ghi riêng bước handover)                  │
├──────────────────────────────────────────────────────────────────────┤
│ ĐƯỜNG LUI (HN-07): breaker (5 lỗi/60 s → bỏ qua 120 s) → retry 1 lần │
│  (backoff) → HOMEMATCH_AGENT_FALLBACK_MODEL → graph luật → template  │
├──────────────────────────────────────────────────────────────────────┤
│ GUARD ĐẦU RA (HN-06): check_numbers · không thu nhập · không tuyên   │
│  bố "đã đặt lịch/thanh toán/liên hệ" thiếu tool · không tự nới       │
│  → thay template an toàn + bước guard                                │
├──────────────────────────────────────────────────────────────────────┤
│ STREAM (HN-10): {"delta"} từng đoạn chữ → hậu kiểm toàn câu →        │
│  {"replace"} nếu vi phạm → {"done", MessageResult}                   │
├──────────────────────────────────────────────────────────────────────┤
│ TRACE BỀN (HN-05): hm_agent_turns (phase, agent_mode, tokens, cost,  │
│  outcome, error_code) + hm_agent_steps (llm/tool/guard/decision) —   │
│  không prompt/câu trả lời thô · GET /admin/agent-turns (audit)       │
└──────────────────────────────────────────────────────────────────────┘
```

FE đọc stream: mỗi `step` cập nhật "Đang xử lý — bước N"; `delta` nối dần bong bóng chat; `replace` thay toàn bộ; `done` là nguồn sự thật cuối. `HOMEMATCH_AGENT_RECORD/REPLAY` (HN-09) bao quanh hai điểm chạm provider (model + Jev) để ghi cassette và phát lại bằng chứng live không tốn phí.

## 3. Vòng lặp agent, pha và roster role

`agent_loop.run_turn` là vòng lặp duy nhất (thay cho cấu trúc multi-graph cũ — chat graph vẫn còn cho demo mode và các nhánh luật). Mỗi lượt suy **pha** từ trạng thái phiên (`service._agent_phase`, không LLM) và **role** do định tuyến chọn (HN-13); bộ tool của lượt = pha ∩ roster role:

| Pha | Điều kiện | Tool được cấp |
|---|---|---|
| `interview` | chưa có kết quả published | find_place, update_needs, search_rooms, confirm_and_search, ask_user, search_handbook |
| `results` | đã published | + room_details, estimate_cost, simulate_loan, compare_rooms, prepare_viewing |
| `transaction` | đã có lịch xem hoặc hội thoại chủ nhà | + open_landlord_chat |

`prepare_viewing` có từ pha `results` (18/11): pha `transaction` chỉ có khi đã có lịch xem hoặc hội thoại, nên trước đó model không bao giờ chuẩn bị được lịch xem đầu tiên. Tool này không tạo bản ghi — chỉ mở căn đó để khách chọn giờ và gửi biểu mẫu. `open_landlord_chat` tạo hội thoại nên vẫn chỉ ở `transaction`. `room_ref` của model được chuẩn hóa ("3", "thứ ba", "đầu tiên" → "căn …") và chỉ trả căn trong danh sách hiện tại; mã căn trong câu trả lời của model được đổi thành "Căn N" theo thứ tự khách thấy.

| Role (HN-13) | Nhiệm vụ | Roster tool | Ghi chú bất biến |
|---|---|---|---|
| `needs` | Hiểu ý ngầm, tách điều kiện cứng vs sở thích, nói lại giả định, một câu/lượt | find_place, update_needs, search_rooms, confirm_and_search, ask_user, room_details, search_handbook, open_landlord_chat, prepare_viewing | tool ghi nhu cầu chỉ có ở role này |
| `finance` | Giải thích chi phí và đánh đổi tài chính | room_details, estimate_cost, simulate_loan, search_handbook | `simulate_loan` không nhận tham số tiền — chạy lại nhánh `simulate_finance` bằng chính câu khách, thẻ mô phỏng giữ số `costs.py`; khai báo `writes=True` vì gọi hàm giữ `service.lock` (chạy thread chính, không deadlock với tool chỉ đọc) |
| `ranking` | Giải thích vì sao căn đứng trên, đánh đổi; KHÔNG đổi thứ hạng | room_details, compare_rooms | `compare_rooms` chỉ đọc, dùng kết quả hiện tại + `advisor.advise`, không đi qua `service.compare` (hàm đó lấy lock) |

Roster khai báo một chỗ trong `agent_tools.py` (`ROLE_ROSTER`: system prompt + tools); `ToolBox.invoke` chặn lại một tầng ở biên model. Model gọi nhầm tool ngoài pha/role trả lỗi có cấu trúc `tool_unavailable`/`tool_not_allowed`. Tham số model qua env: `HOMEMATCH_AGENT_REASONING` (low|medium|high), `HOMEMATCH_AGENT_MAX_TOKENS` (800), `parallel_tool_calls=true`; model reasoning không nhận `temperature`.

Đường tắt tất định (**fast path**): câu mà luật hiểu đủ (DemoInterpreter trích được thành phố, có mức tiền, không nhắc điểm đến/mơ hồ) chạy thẳng `patch → lớp hỏi lại → confirm` với 0 lần gọi LLM để hiểu câu (`agent_mode="fast_path"`; lần gọi bàn giao xếp hạng — nếu có — được ghi riêng, không tính vào đây). Ý định rõ (`human_support`, `landlord_handover`, `handbook`, hoặc message có `cost_input`) đi graph luật ngay; `simulate_finance`/`calculate_cost` không `cost_input` được định tuyến sang agent tài chính khi đã có kết quả. Chỉ khi luật không đủ hoặc clarity=reason thì mới vào vòng LLM (`agent_mode="loop"`). Trích tiền tất định (`budget_hint`) hiểu các kiểu viết phổ biến: "3 triệu5"/"3tr5" (đuôi số dính liền đơn vị — có khoảng trắng như "3 triệu 2 người" vẫn là 3 triệu), "5 triệu rưỡi", slang "4 củ/5 cây".

Bổ sung 19/11 (đo chất lượng đề xuất trên LLM thật, hai lỗi lặp 3/3 lần):
- **Tiện ích bắt buộc.** Câu có dấu hiệu mạnh ("bắt buộc có", "phải có", "nhất định", "chỉ lấy phòng có …") đưa các tiện ích cùng vế câu vào `must_amenities` của nháp, rồi thành `Profile.must_amenities` (lọc cứng, căn không ghi rõ có tiện ích bị loại). Dấu hiệu mềm ("thì tốt", "ưu tiên", "cần có") vẫn là ưu tiên. "Không cần máy giặt nữa" gỡ khỏi danh sách bắt buộc. Đọc tất định ở `must_amenities_hint`/`dropped_amenities_hint` (`interpreter.py`), áp trên cả fast path, vòng LLM và graph luật; model không ghi trường này.
- **Chỉnh mức tiền sau khi đã có kết quả.** "Rẻ hơn nữa, dưới 3,5 triệu thôi" không có từ tìm phòng nên luật đọc ý định `unknown`; trước đây câu rơi vào vòng LLM và model trả lời mà không tìm lại. Nay `is_budget_refinement` (`agent_loop.py`) cho fast path nhận câu này như tìm lại khi: phiên đã có hồ sơ xác nhận, câu có dấu hiệu mức tiền ("dưới", "tối đa", "rẻ hơn", "giảm", "X triệu thôi"…), không nói về tiền cọc/điện nước/phí/lương/vay, và không nhắc một căn cụ thể.

## 4. Registry tool và hợp đồng tool (HN-03)

Mỗi tool khai báo **một lần** trong `agent_tools.py`: `name, agent, description, Args (Pydantic → JSON schema tự sinh), writes (chỉ đọc hay ghi), timeout_s (8 s), view (workspace mở khi thành công), capability, summarize() (dòng bước không PII), redact(), phases, handler (nghiệp vụ đặt cạnh khai báo)`. Từ registry sinh tự động: JSON schema gửi model, allowlist theo agent (`AGENT_TOOLS`), capability (`agent_capability.py`), specs theo pha. Kết quả tool chuẩn hóa `{ok:true, data}` hoặc `{ok:false, error, message, hint}` — hint giúp model tự sửa ("gọi find_place trước"). Tool ghi có idempotency key `turn_id + tool + hash(args)` trong ledger — retry stream không tạo bản ghi đôi. **Thêm tool mới cho các task chức năng (AG-06, MP-01…): 1 khai báo + 1 test hợp đồng tự sinh.**

### `find_place`: danh mục, bản đồ, mơ hồ (LOC-001)

`find_place(query, city_hint?)` tra theo thứ tự:

1. **Nhánh `own_place`**: "tôi/đây/công ty tôi" không phải địa danh, không tra.
2. **Danh mục đã kiểm chứng** `data/places.json` (`locations.resolve_place_candidates`): một kết quả → `{found: true, source: "catalog", place_id}`; nhiều kết quả (ví dụ "Bách Khoa" khi chưa biết thành phố) → `{found: false, reason: "ambiguous", candidates: [{label, city}]}` kèm ghi chú gọi `ask_user(field="city")`.
3. **Bản đồ** (`geocode.py`, `HOMEMATCH_GEOCODER=auto|nominatim|goong|off`): Goong nếu key REST gọi được, không thì Nominatim; 401/403 tắt Goong tới khi khởi động lại. Kết quả phải nằm trong khung bao thành phố (thành phố nháp, hoặc cả hai khi chưa biết), loại kết quả hành chính thô, quận/huyện chỉ trả `reason: "area_only"` để ghi `area`, `uncertainty_m` lấy từ bbox kẹp trong [150, 2000] m. Chưa biết thành phố mà cả hai đều có kết quả → mơ hồ. Thành công trả `{found: true, source: "geocoder", place_id: "geo:<hash>", approximate: true}`.
4. Không tìm thấy (hoặc bản đồ tắt/lỗi): ghi chú "không tìm thấy trên bản đồ", model chỉ ghi `area` khi khách đã nói rõ quận, nếu không thì hỏi lại; không tự đoán quận hay tọa độ.

**Quy tắc gửi ra ngoài:** chỉ tên địa danh đã bỏ chữ "gần" và qua `redact`, tối đa 80 ký tự, kèm thành phố (qua viewbox); không gửi session id, user id hay tọa độ. Câu có số nhà hoặc dấu hiệu liên lạc (`số 12`, `ngõ 34`, `hẻm 5/7`, số điện thoại, email...) không được gửi: trả `reason: "address_not_sent"` để hỏi tên đường hoặc địa danh gần đó. Cache LRU 512 mục trong process; Nominatim tối đa 1 yêu cầu/giây, timeout 3 s, lỗi coi như không tìm thấy.

**Ghi điểm đến:** kết quả `find_place` được giữ theo phiên (`service._resolved_places`, mất khi khởi động lại thì model gọi lại). `update_needs` nhận `destination_place_id` (đường ưu tiên: đúng tọa độ vừa tra); chỉ có `destination_text` thì tra danh mục rồi cache phiên. Kiểm tra "khách đã nêu tên" (HN-13.3.5) so với tên, alias, câu hỏi gốc model đã gửi `find_place` và nhãn kết quả; kiểm tra "điểm đến ngoài khu vực đang ghim" giữ nguyên; không tra được thì `unknown_place`. Nhánh graph/demo (`service.py`) vẫn chỉ dùng danh mục, tất định và offline.

## 5. Lớp hỏi lại kho + Jev (HN-02, AG-11)

`ask_user(field=…)` — model chỉ chọn **điểm cần hỏi**, không tự bịa lựa chọn (trừ `other`, tối đa 4 lựa chọn chữ đánh dấu `source="model"`). Harness dựng lựa chọn từ kho thật (`clarify.build_clarification`): mỗi cách hiểu áp lên hồ sơ tạm và xếp hạng kho → mỗi chip có `count` (số căn toàn tập đủ điều kiện), `min_monthly_total_vnd`, `patch`. Mức ảnh hưởng = max(Jaccard top-5, chênh số căn) giữa các cách hiểu — dưới 0,2 thì không hỏi. `decisions.decide` (Jev `typesafe/jev-1.14` trên OpenRouter Decisions API, lỗi → luật dự phòng) xếp chip theo xác suất; luật dự phòng **không tự áp bán kính** (5 km thường nhiều căn hơn nhưng "gần" nghĩa là gần nhất) và chỉ tự áp khi p ≥ 0,85. Ngưỡng 0,85/0,40/0,2 hiệu chỉnh trên 40 ca gold bằng `eval clarify`. Confirm khi còn mơ hồ ≥ 0,2 trả lỗi cấu trúc `needs_clarification` kèm field → model phải `ask_user`. Giới hạn: 1 câu/lượt, 2 câu trước kết quả đầu tiên (bền ở `hm_sessions.clarification_questions`, schema v18).

**Chip hỏi lại (HN-13.2, sau đo hội thoại):** FIELD_PRIORITY giữ nhóm cũ trước để
không phá hiệu chỉnh gold HN-08; thêm ba nhóm: `destination` (chip ĐIỂM MỐC THẬT
trong places.json theo thành phố nháp, chỉ nơi có căn, tự hỏi CHỈ khi khách nói
"gần" mà không nêu tên), `city` (thiếu thành phố — chip thành phố đang có căn,
được hỏi TRƯỚC mọi nhóm khi thiếu) và `budget_cap` (chưa có mức tiền — mức gợi ý
từ phân bố KHO THẬT: đủ ≥5 căn có tổng tháng → "Tổng tháng dưới X"; thiếu phí →
GIÁ THUÊ với nhãn nói rõ "Tiền thuê dưới X", không bao giờ gọi giá thuê là tổng
chi phí; thiếu dữ liệu giá → không chip). `city`/`budget_cap`/`destination` là
ASK_ONLY — không bao giờ tự chấp nhận hộ khách. Nhãn chip tự nhiên kèm số căn
thật "Trong 2 km (1 căn, từ 3.230.000 ₫)", căn bị giữ chờ xác minh được nói thật
("thêm M tin cần xác minh"); DTO option thêm `action: "patch"|"text"` + `text`
(chip chữ bấm là GỬI CÂU đó — tiền được đọc tất định `budget_scope_hint` từ câu)
và `reason` (một câu vì sao hỏi, model viết qua hậu kiểm, FE hiển thị dưới câu
hỏi). Chip trạng thái (`state_chips`) thay bộ 3/5/8 triệu cố định; có câu hỏi
đang chờ thì KHÔNG chip trạng thái. Giả định engine trả qua
`MessageResult.assumptions` (câu người đọc: "Tạm tìm phòng trọ" — không phải nhãn
chip có số); mode off giữ chuỗi nối cũ. Model tự hỏi trong câu trả lời mà không
qua `ask_user` → giữ câu hỏi, không gắn chip đoán, ghi chỉ số
`question_without_chip` vào trace. Câu hỏi đang chờ lưu trong bộ nhớ tiến trình
(mất khi restart chỉ là thiếu ngữ cảnh) và xoá khi: khách bấm chip, field vào
nháp, có run mới, hoặc lượt khách nói sang việc khác.

Cùng một điểm chạm provider Jev còn phục vụ **analyst đầu vào** (HN-13): hàm POST tách thành `decisions.jev_post(payload, timeout_s)` dùng chung — chip làm rõ giữ timeout 2 s, analyst dùng 3 s — và cùng cassette `jev_call`, cùng breaker (`jev`). Analyst gửi một request hai câu choice (`route`, `clarity`) với state chỉ gồm tin nhắn + nháp đã qua `decision_context` (không `*_vnd`, không thu nhập, không khoản vay), pha phiên và cờ đã có kết quả; kiểm tra response như `decide()` (choice hợp lệ, xác suất hữu hạn, tổng xấp xỉ 1); p(route) < 0,6 → luật; p(clear) < 0,6 → clarity `reason`; Jev lỗi/timeout/breaker mở/hết ngân sách phiên → luật với `decided_by="fallback"`, clarity `clear` (không phát sinh lượt LLM khi không phân tích được). Tin bị cách ly bởi `screen_injection` không bao giờ tạo request Jev. Chi phí `usage.cost` của Jev cộng vào trần chi phí phiên. Chạy chỉ trong nhánh openai; demo mode không gọi Jev.

## 6. Guardrail vào/ra và ngân sách (HN-06)

- **Vào:** injection → cách ly; ≥2000 ký tự → 422; dữ liệu tool bọc *untrusted* + vô hiệu giá trị nghi nhiễm; tiền trong tin nhắn tách placeholder trước LLM.
- **Ngân sách phiên:** `HOMEMATCH_SESSION_TURN_BUDGET` (60 **lượt chat** cần AI — không phải lần gọi LLM) và `HOMEMATCH_SESSION_COST_CAP_USD` (0,05, từ `usage.cost` provider báo). Hết → 429 thân thiện gợi biểu mẫu; route tất định (chi phí, cẩm nang, đặt lịch) không tốn ngân sách.
- **Ra:** hậu kiểm số; cấm nhắc thu nhập; cấm tuyên bố "đã đặt lịch/thanh toán/chốt/liên hệ" không có tool ghi thành công tương ứng; cấm tự nhận nới điều kiện; **cấm để lộ placeholder tách PII/tiền** (`[TIEN_DA_TACH]`…) — model nhắc lại placeholder (lỗi thật ngày 06/11) sẽ bị thay câu template an toàn với mã `placeholder_leak` — vi phạm thay câu template + bước `guard_output`.
- Tool ghi cần xác nhận (đặt lịch, chốt căn) chỉ trả **bản chuẩn bị**; thao tác thật do FE gửi khi khách bấm.

## 7. Đường lui và độ bền (HN-07)

`model chính → (lỗi tạm thời 5xx/timeout) retry 1 lần (backoff 0,5 s) → HOMEMATCH_AGENT_FALLBACK_MODEL → graph luật (graph_fallback) → template`. Jev lỗi → luật; Goong lỗi → đường thẳng (MP-01). Circuit breaker: 5 lỗi liên tiếp trong 60 s → bỏ qua provider 120 s (model chat và Jev có breaker riêng). Mỗi lần lùi là một bước `guard` trong trace.

## 8. Trace bền và quan sát (HN-05)

Mỗi lượt ghi một dòng `hm_agent_turns` (phase, agent_mode loop|fast_path|graph_fallback, model, llm_calls, input/output_tokens, cost_usd do provider báo, decided_by, outcome answered|asked|handover|safe_reply|error, error_code) và N dòng `hm_agent_steps` (kind llm|tool|guard|decision, duration_ms, summary đã redact). Analyst ghi một bước `decision` (`input_analyst`: route/clarity/decided_by, không văn bản thô); bàn giao xếp hạng ghi một bước `llm` tên `handover` và `provenance.handover_calls` — **không** cộng vào `llm_calls`, để số liệu fast path/eval không bị lẫn (fast path vẫn nghĩa là 0 lần gọi LLM để hiểu câu). Không lưu prompt/câu trả lời thô (transcript đã PII-mask nằm ở `hm_chat_transcripts` với retention riêng). `GET /admin/agent-turns` trả lượt + p50/p95 + tỉ lệ fallback + chi phí (mỗi lần đọc ghi audit); trang `/quan-tri/van-hanh` hiển thị bảng này.

## 9. Đo và tái lập (HN-08, HN-09)

- `eval/scenarios/agent_e2e.json`: 44 kịch bản nhiều lượt HN/HCM; `python -m eval agent --mode demo` chấm offline (completion, độ chính xác nháp, số câu hỏi trước kết quả, p50/p95); `--mode live` phải `--allow-live` + ngân sách tuyên bố, mặc định in ước tính rồi dừng.
- `eval clarify`: precision/recall/top-1 của lớp hỏi lại trên 40 ca gold.
- `HOMEMATCH_AGENT_RECORD/REPLAY`: cassette JSON ghi request/response model + Jev (đã redact) — phát lại bằng chứng live không tốn phí, cùng message/steps/usage từng chữ.
- Ngưỡng 0,85/0,40/0,2 hiệu chỉnh trên gold; bộ kịch bản đóng băng trước khi đo EV-01 (điểm tổng hợp 39 % → ≥ 60 %).

## 10. Memory và giới hạn

`memory.py` chỉ nhớ sở thích phi tài chính khi khách đồng ý (`/me/memory`), prefill nháp ở trạng thái `inferred` (tối đa 6 sở thích, mạnh nhất trước), rút đồng ý là xoá. Sở thích tích lũy bằng luật tất định: xác nhận trong phiên thì thêm một phiên bằng chứng; nháp có mà khách bỏ thì quên và không gợi ý lại; vắng 2 phiên xác nhận liên tiếp thì phai; tiện ích có ở ≥ 2 và ≥ 60% phòng đã lưu, đồng thời phổ biến hơn kho ít nhất 1,5 lần, được gợi ý nhưng khách vẫn phải xác nhận. Khu vực và loại phòng giữ giá trị mới nhất; không lưu tiền, điểm đến. Workspace context (căn đang xem/chọn) chỉ sống trong tiến trình của lượt. Không cổng thanh toán, email/SMS thật, chữ ký số (D-07/D-08); chạy localhost (D-09).

## 11. Agent cho chủ nhà (23/11/2026)

`landlord_agent.py` + `POST /landlord/agent` (khung chat nổi `LandlordAgentDock` ở mọi trang `/chu-nha/*`). Cùng nguyên tắc: LLM suy luận, tool tính và kiểm. Khác agent người thuê ở ba điểm:

- **Chỉ đọc và gợi ý.** Chỉ có tool đọc (`get_overview`, `list_rooms`, `room_performance`, `price_advice`, `vacancy_report`, `draft_post`, `list_viewings`, `list_conversations`, `billing_overview`, `list_maintenance`); không có tool ghi. Đổi trạng thái phòng, xác nhận lịch, nhắn khách, đăng bài đều do chủ nhà tự bấm; agent chỉ chỉ đường tới màn tương ứng.
- **Quyền theo vai và bản ghi** nằm trong các hàm service đã có (`_owner`, `_own_room`); kết quả tool bỏ liên hệ khách, che PII, vô hiệu mẫu chèn lệnh trong mô tả tin.
- **Không lưu hội thoại ở máy chủ.** Trình duyệt giữ lịch sử trong phiên và gửi kèm tối đa 8 tin gần nhất (đã redact). Giới hạn tần suất `HOMEMATCH_LANDLORD_AGENT_HOURLY` (mặc định 40 lượt/giờ/chủ nhà).

Giới hạn lượt 5 bước tool, 4 lần gọi model, 40 s. Hậu kiểm đầu ra chặn nhắc thu nhập, rò placeholder, từ nội bộ, tuyên bố "mình đã gửi/cập nhật…" (agent không có tool ghi) và số không có trong kết quả tool. Demo mode hoặc lỗi nhà cung cấp rơi về trợ lý theo luật `copilot.assistant` (`agent_mode="rules"` / `"rules_fallback"`), không ném 500. Chưa ghi `hm_agent_turns` cho agent này (bảng đó gắn với phiên người thuê). Chưa chạy live với GPT-4o.
