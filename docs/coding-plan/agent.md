# Coding plan — AI Agent (AG)

Đọc [README.md](README.md) trước, đặc biệt §2: AG chỉ được sửa các file agent và hàm `_build_chat_graph` trong `service.py`.

**Code và tài liệu mẫu cần đọc:**
- `docs/thiet-ke-agent.md`: vai trò từng agent, tool, giới hạn.
- `backend/app/agents.py`: `ToolBox.call(agent, tool, fn, ...)`, `AGENT_TOOLS`, `MAX_STEPS = 4`.
- `backend/app/service.py` `_build_chat_graph` (~dòng 1173–1282):
  - node `route` (supervisor), `interview`, `finance`, `support`, `handbook`;
  - provenance được gắn bằng `stamp(...)`.
- `backend/app/interpreter.py`: `fixed_intent` (luật, chạy trước LLM), `DemoInterpreter`, `OpenAIInterpreter` (structured output, `store=False`).
- `backend/tests/test_agents_memory.py`: cách test allowlist, giới hạn bước, provenance.

**Nguyên tắc của agent (không được phá):**
- LLM **không** tính tiền, không duyệt, không đổi hồ sơ đã xác nhận, không tự nới điều kiện cứng.
- Mọi số trong câu trả lời phải do tool tất định tính ra.
- Ý định rõ ràng đi nhánh luật (`fixed_intent`) và **không gọi LLM**.
- Không gửi tiền, thu nhập, số điện thoại hay email vào prompt. Văn bản phải qua `agent_guard.redact` trước khi tới LLM, xem cách `interview` đang làm.

| ID | Task | Ưu tiên | Phụ thuộc |
|---|---|---|---|
| AG-01 | Đồng bộ `Literal` intent và thêm test cho interpreter | P0 | — |
| AG-02 | Ý định chat `simulate_finance` | P1 | DA-02 (có thể bắt đầu bằng các ca mẫu ở README §7.4) |
| AG-03 | Tách token input, output và embedding trong usage | P1 | — (BE-05 dùng kết quả) |
| AG-04 | Chuẩn bị chạy live GPT-4o và pgvector (người dùng tự chạy) | P1 | AG-03, BE-01 |
| AG-05 | Viết lại bài đăng của chủ nhà bằng LLM (tùy chọn) | P3 | AG-03 |

---

## AG-01 — Đồng bộ `Literal` intent

**Lỗi:** `models.Extraction.intent` (`models.py` ~dòng 240) là `Literal["find_room","calculate_cost","human_support","unknown"]`, trong khi `schemas.MessageResult.intent` có thêm `"handbook"`. `OpenAIInterpreter` dùng `Extraction` làm schema đầu ra, nên ở chế độ `openai` model không thể trả `handbook`.

**Các bước:**
1. Thêm `"handbook"` vào `Extraction.intent`. Đây là phần README §2 cho AG sửa trong `models.py`.
2. Kiểm prompt hoặc hướng dẫn của `OpenAIInterpreter` có mô tả intent `handbook`; nếu chưa, thêm một dòng mô tả.
3. Test (`backend/tests/test_interpreter_intents.py`):
   - với **mỗi** giá trị trong `MessageResult.intent`, `Extraction.model_validate` chấp nhận được; dùng `typing.get_args` để test tự bắt lệch về sau;
   - `OpenAIInterpreter` với **client giả** (class trả JSON cố định, xem cách test hiện có mock client: `grep -rn "OpenAIInterpreter(" backend/tests`) trả `intent="handbook"` → không lỗi;
   - không gọi mạng.

**Xong khi:** check-local exit 0.

---

## AG-02 — Ý định chat `simulate_finance`

**Hợp đồng:** README §7.4. **Spec:** `docs/api-san-pham-v1.md` §2.

**Mục tiêu:** khách đã có danh sách được duyệt hỏi bằng chat ("nếu vay 12 tháng thì sao", "vay 20 triệu lãi 10% thì trả bao nhiêu"). Agent tài chính mô phỏng cho căn được nhắc tới (hoặc căn đầu tiên đang hiển thị) và trả lời chỉ bằng số do tool tính.

**Các bước:**
1. **`interpreter.fixed_intent`:** thêm nhánh `simulate_finance`, **đặt trước** nhánh `calculate_cost`. Nhận diện trên văn bản đã bỏ dấu (`folded`) bằng các mẫu:
   - `r"\bneu vay\b"`;
   - `r"\bvay\b.*\b\d+\s*thang\b"`;
   - `r"\btra gop\b"`;
   - `r"\blai suat\b"`;
   - `"mo phong vay"`.

   Giữ "mo phong chi phi" thuộc `calculate_cost`.
2. **`Literal`:** thêm `"simulate_finance"` vào `models.Extraction.intent` và `schemas.MessageResult.intent`. Thêm `"simulation"`, `"needs_results"` vào `MessageResult.status`. Thêm trường `simulation: dict | None = None`.
3. **`interpreter.parse_loan_terms(text) -> dict`:** hàm thuần, trả về `{"term_months": int|None, "annual_rate": float|None, "principal_vnd": int|None}`.
   - `term_months`: `(\d{1,3})\s*thang`, trong khoảng 1–60.
   - `annual_rate`: `(\d{1,2}(?:[.,]\d{1,2})?)\s*%`; dấu phẩy đổi thành dấu chấm; trong khoảng 0–50.
   - `principal_vnd`: dùng lại hàm đọc tiền "20 triệu" đã có trong file (hàm trả `int(Decimal(...) * 1_000_000)`, ~dòng 30).
   - Ngoài khoảng → `None`.
4. **`AGENT_TOOLS["finance"]`** đã có `simulate_scenarios`; không cần thêm.
5. **`_build_chat_graph`:**
   - Supervisor `route` map `simulate_finance → finance`.
   - Trong node `finance`, khi intent là `simulate_finance`:
     1. Lấy danh sách đang hiển thị bằng `self.repo.visible_items(...)` (đọc chữ ký hàm trong `repository.py`). Rỗng → `status="needs_results"`, `message="Bạn cần có danh sách phòng đã được chủ nhà duyệt trước khi mô phỏng vay."`.
     2. Căn đích: ID trong câu (`synthetic-room-\d{3}`, `room-[0-9a-f]{10}`, `demo-\d{2}`), nếu không có thì căn đầu tiên.
     3. Kịch bản: lấy `loan` trong hồ sơ đã xác nhận làm gốc, ghi đè bằng các giá trị parse được. Hồ sơ không có `loan` và câu thiếu lãi suất → dùng `annual_rate=None` và trả lời yêu cầu nêu lãi suất; **không tự đặt lãi suất mặc định**.
     4. Gọi `state["toolbox"].call("finance", "simulate_scenarios", <hàm>, ...)`, tái dùng đúng logic của `HomeMatchService.simulate` (~dòng 687). Nếu cần, tách phần tính thành hàm nội bộ dùng chung; không viết lại công thức. Tối đa 1 kịch bản mỗi lượt.
     5. `message` dựng từ template tiếng Việt với số đã format (cách format VND có sẵn trong code UI hoặc `copilot._money`). **Không** gọi LLM để viết câu trả lời.
     6. `provenance = stamp("deterministic-engine", "finance", ...)`.
   - **Không** sửa hồ sơ đã xác nhận, run hay danh sách duyệt.
6. **Kiểm riêng tư:** câu trả lời không chứa thu nhập. Tỷ lệ trên thu nhập chỉ trả về cho chính khách (chủ phiên), đúng như `/simulate`.

**Test** (`backend/tests/test_finance_chat.py`):
- Có run đã duyệt (dựng như `test_landlord.py`) và chat "nếu vay 12 tháng lãi 12% thì sao" → `intent=="simulate_finance"`, `status=="simulation"`, `simulation.result` **bằng đúng** kết quả của `POST /sessions/{id}/simulate` với cùng kịch bản.
- Chưa có kết quả → `needs_results`.
- Thiếu lãi suất và hồ sơ không có `loan` → hỏi lại, không có số trả góp.
- `HOMEMATCH_LLM_MODE=openai` với client giả: client **không** được gọi cho câu này.
- Hồ sơ và run không đổi sau khi chat.
- `parse_loan_terms` chạy đúng mọi ca trong `data/oracles/loan_parse_cases.json` (DA-02). Nếu file chưa có thì dùng 3 ca ở README §7.4 và đánh dấu `TODO(DA-02)`, nhưng phải xóa dấu này trước khi báo xong.
- "mô phỏng chi phí" vẫn ra `calculate_cost`.

**Docs:**
- `docs/thiet-ke-agent.md`: bảng agent tài chính thêm "mô phỏng vay qua chat";
- xóa §2 khỏi `api-san-pham-v1.md`;
- FR-08: ghi "giao diện và chat".

Nhờ BE sinh lại OpenAPI, vì `MessageResult` đổi.

---

## AG-03 — Tách token input, output và embedding

**Mục tiêu:** BE-05 cần số token tách riêng để quy ra VND. Hiện `operations.py` chỉ cộng dồn `reported_tokens`.

**Các bước:**
1. Đọc nơi `OpenAIInterpreter` ghi usage (`grep -n "usage\|record" backend/app/interpreter.py backend/app/operations.py backend/app/semantic.py`).
2. Ghi thêm `input_tokens` và `output_tokens` từ `response.usage` (Responses API: `input_tokens`/`output_tokens`; Chat Completions: `prompt_tokens`/`completion_tokens`; hỗ trợ cả hai). Giữ `reported_tokens` (tổng) để tương thích.
3. Embedding (`semantic.py`): ghi `embedding_tokens` từ `usage.total_tokens` nếu có. Nếu không có thì **không** ước lượng; tăng `embedding_calls_without_usage`.
4. Thêm các khóa mới vào `provider_usage` trả ra `/admin/metrics`. Sửa `operations.py`: file này thuộc BE, nhưng thay đổi nhỏ và AG được phép trong task này; ghi rõ trong báo cáo.
5. Ghi usage theo **model** (`by_model: {"gpt-4o": {...}, "text-embedding-3-small": {...}}`), vì giá khác nhau theo model.

**Test:** client giả trả `usage` theo cả hai dạng → metrics cộng đúng; thiếu usage → đếm vào `calls_without_token_usage` như cũ.

---

## AG-04 — Chuẩn bị chạy live GPT-4o và pgvector

**Không chạy.** Chỉ chuẩn bị script để người dùng tự chạy với key của họ.

1. Tạo `infra/live_run.sh` (`set -euo pipefail`):
   - kiểm `OPENAI_API_KEY` đã đặt (**không in ra**), và `HOMEMATCH_LIVE_BUDGET_VND` (bắt buộc, > 0);
   - in kế hoạch: số câu gold dev (đếm từ `data/profiles/dev`), số căn cần embedding (220), số lượt gọi ước tính;
   - đòi người dùng gõ `yes`;
   - các bước:
     1. `infra/local-pg.sh start`;
     2. `backend.manage setup` trên PostgreSQL;
     3. `backend.manage index --allow-live`;
     4. `python -m eval extraction --split dev --live --allow-live --api-budget-vnd $HOMEMATCH_LIVE_BUDGET_VND` (kiểm tên cờ trong `eval/__main__.py`);
     5. `python -m eval ranking --split dev` với `HOMEMATCH_MATCHING_METHOD=P`;
     6. `python -m eval measure`.
   - lưu kết quả vào `eval/runs/live-<ngày>/`, không ghi đè `development/`.
2. Viết `infra/live-run.md`: điều kiện, chi phí ước tính (để trống giá, tham chiếu BE-05), cách đọc kết quả, cách dừng.
3. **Kiểm offline:** chạy script **không có** `OPENAI_API_KEY` → phải dừng ở bước kiểm với thông báo rõ ràng, exit khác 0. Đây là kiểm tra duy nhất agent được tự chạy.

**Sau khi người dùng chạy:** cập nhật `trang-thai-trien-khai.md` (ngày, model, số lượt gọi, chi phí, kết quả). Đóng FR-11 và NFR-06 nếu đạt.

---

## AG-05 — Viết lại bài đăng bằng LLM (tùy chọn)

Chỉ làm khi người dùng đồng ý, vì mỗi lần dùng sẽ tốn phí khi bật live.

- `copilot.marketing_post` giữ bản template làm mặc định. Thêm tham số `rewrite: bool`; bật thì gửi **chỉ danh sách điểm đã có** (`highlights`, loại, khu vực; không gửi số tiền) cho LLM để viết văn phong. Sau đó **chèn lại** các dòng giá, cọc, link từ template.
- Kiểm sau khi LLM trả về:
  - nếu bài có chữ số mà không có trong dữ liệu tin, hoặc có tiện ích không thuộc `highlights` → bỏ bản LLM, dùng template, `rewrite_status="rejected"`.
- Đi qua `ToolBox` với một agent mới `marketing` (thêm vào `AGENT_TOOLS`) và `agent_budget`.
- Test dùng client giả: một bản hợp lệ, một bản bịa thêm "hồ bơi" → bị loại.
