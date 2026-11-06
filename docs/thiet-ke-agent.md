# Thiết kế AI Agent HomeMatch

**Cập nhật:** 06/11/2026 (sau đợt harness HN-00…HN-12; thay bản 08/10/2026 — bản cũ lưu ở git lịch sử). Tài liệu này là **chương kiến trúc agent của luận văn**: viết cho người đọc mới, có sơ đồ luồng một lượt, đối chiếu trực tiếp với code. Chi tiết vận hành (biến môi trường, quy trình test, quan sát) nằm ở [nghiep-vu-va-harness.md](nghiep-vu-va-harness.md).

## 1. Nguyên tắc (bất biến)

1. **LLM hiểu ngôn ngữ, code quyết định.** Tiền chỉ do `costs.py` tính (Decimal, VND); lọc cứng, xếp hạng, quyền và việc công bố là code tất định. LLM trích xuất, suy luận ngữ nghĩa, chọn tool và diễn đạt — mọi con số trong câu trả lời phải đến từ câu của khách hoặc kết quả tool (hậu kiểm `check_numbers`, sai → thay bằng câu template).
2. **Không còn bước chủ nhà duyệt** (quyết định D-10, 05/11/2026): kết quả công bố ngay sau khi xếp hạng, đúng phiên bản hồ sơ và kho hiện tại; chủ nhà biết nhu cầu qua lead (`touch_lead` khi căn của họ lọt top 5), không chặn khách.
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
│  fixed_intent (chi phí/vay/handbook/handover/hỗ trợ) ──► graph luật   │
│  DemoInterpreter trích đủ + không mơ hồ ──► FAST PATH (HN-01):       │
│      patch → lớp hỏi lại → confirm  — 0 lần gọi LLM                  │
│  còn lại ──► VÒNG LẶP AGENT (HN-01)                                  │
├──────────────────────────────────────────────────────────────────────┤
│ VÒNG LẶP (tối đa 4 lần gọi LLM / 6 bước tool / 45 s)                 │
│  NGỮ CẢNH (HN-04): nháp+hồ sơ ▸ workspace(≤30 căn+top5) ▸ bộ nhớ ▸   │
│  tóm tắt (mỗi 4 lượt, hm_sessions.summary_json) ▸ 6 lượt gần nhất    │
│  — cắt theo HOMEMATCH_CONTEXT_TOKEN_CAP đúng thứ tự ưu tiên          │
│  LLM ⇄ TOOLBOX (HN-03): specs theo PHA (HN-11) interview/            │
│  results/transaction · tool chỉ đọc chạy SONG SONG, tool ghi         │
│  tuần tự ở thread chính · timeout tool 8 s → tool_timeout            │
│  ── ask_user(field) ──► LỚP HỎI LẠI (HN-02):                         │
│      build_clarification (kho thật: số căn, giá từ) → Jev/luật       │
│      (decisions.py, ngưỡng 0,85/0,40/0,2) → chip có count/patch/     │
│      decided_by; luật không tự áp bán kính                           │
│  ── confirm_and_search ──► preflight hỏi lại → confirm → công bố     │
│  ── chốt lượt bằng template (số từ tool), không gọi LLM thêm         │
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

## 3. Vòng lặp agent và phân vai theo pha

`agent_loop.run_turn` là vòng lặp duy nhất (thay cho cấu trúc multi-graph cũ — chat graph vẫn còn cho demo mode và các nhánh luật). Mỗi lượt suy **pha** từ trạng thái phiên (`service._agent_phase`, không LLM):

| Pha | Điều kiện | Tool được cấp |
|---|---|---|
| `interview` | chưa có kết quả published | find_place, update_needs, search_rooms, confirm_and_search, ask_user, search_handbook |
| `results` | đã published | + room_details, estimate_cost |
| `transaction` | đã có lịch xem hoặc hội thoại chủ nhà | + prepare_viewing, open_landlord_chat |

Ít tool hơn mỗi lượt → model chọn đúng hơn, prompt ngắn hơn. Gọi nhầm tool ngoài pha trả lỗi có cấu trúc `tool_unavailable` cho model tự sửa. Tham số model qua env: `HOMEMATCH_AGENT_REASONING` (low|medium|high), `HOMEMATCH_AGENT_MAX_TOKENS` (800), `parallel_tool_calls=true`; model reasoning không nhận `temperature`.

Đường tắt tất định (**fast path**): câu mà luật hiểu đủ (DemoInterpreter trích được thành phố, có mức tiền, không nhắc điểm đến/mơ hồ) chạy thẳng `patch → lớp hỏi lại → confirm` với 0 lần gọi LLM (`agent_mode="fast_path"`). Ý định rõ (`fixed_intent`: chi phí, vay, cẩm nang, handover, hỗ trợ) đi graph luật ngay. Chỉ khi luật không đủ thì mới vào vòng LLM (`agent_mode="loop"`).

## 4. Registry tool và hợp đồng tool (HN-03)

Mỗi tool khai báo **một lần** trong `agent_tools.py`: `name, agent, description, Args (Pydantic → JSON schema tự sinh), writes (chỉ đọc hay ghi), timeout_s (8 s), view (workspace mở khi thành công), capability, summarize() (dòng bước không PII), redact(), phases, handler (nghiệp vụ đặt cạnh khai báo)`. Từ registry sinh tự động: JSON schema gửi model, allowlist theo agent (`AGENT_TOOLS`), capability (`agent_capability.py`), specs theo pha. Kết quả tool chuẩn hóa `{ok:true, data}` hoặc `{ok:false, error, message, hint}` — hint giúp model tự sửa ("gọi find_place trước"). Tool ghi có idempotency key `turn_id + tool + hash(args)` trong ledger — retry stream không tạo bản ghi đôi. **Thêm tool mới cho các task chức năng (AG-06, MP-01…): 1 khai báo + 1 test hợp đồng tự sinh.**

## 5. Lớp hỏi lại kho + Jev (HN-02, AG-11)

`ask_user(field=…)` — model chỉ chọn **điểm cần hỏi**, không tự bịa lựa chọn (trừ `other`, tối đa 4 lựa chọn chữ đánh dấu `source="model"`). Harness dựng lựa chọn từ kho thật (`clarify.build_clarification`): mỗi cách hiểu áp lên hồ sơ tạm và xếp hạng kho → mỗi chip có `count` (số căn toàn tập đủ điều kiện), `min_monthly_total_vnd`, `patch`. Mức ảnh hưởng = max(Jaccard top-5, chênh số căn) giữa các cách hiểu — dưới 0,2 thì không hỏi. `decisions.decide` (Jev `typesafe/jev-1.14` trên OpenRouter Decisions API, lỗi → luật dự phòng) xếp chip theo xác suất; luật dự phòng **không tự áp bán kính** (5 km thường nhiều căn hơn nhưng "gần" nghĩa là gần nhất) và chỉ tự áp khi p ≥ 0,85. Ngưỡng 0,85/0,40/0,2 hiệu chỉnh trên 40 ca gold bằng `eval clarify`. Confirm khi còn mơ hồ ≥ 0,2 trả lỗi cấu trúc `needs_clarification` kèm field → model phải `ask_user`. Giới hạn: 1 câu/lượt, 2 câu trước kết quả đầu tiên (bền ở `hm_sessions.clarification_questions`, schema v18).

## 6. Guardrail vào/ra và ngân sách (HN-06)

- **Vào:** injection → cách ly; ≥2000 ký tự → 422; dữ liệu tool bọc *untrusted* + vô hiệu giá trị nghi nhiễm; tiền trong tin nhắn tách placeholder trước LLM.
- **Ngân sách phiên:** `HOMEMATCH_SESSION_TURN_BUDGET` (60 **lượt chat** cần AI — không phải lần gọi LLM) và `HOMEMATCH_SESSION_COST_CAP_USD` (0,05, từ `usage.cost` provider báo). Hết → 429 thân thiện gợi biểu mẫu; route tất định (chi phí, cẩm nang, đặt lịch) không tốn ngân sách.
- **Ra:** hậu kiểm số; cấm nhắc thu nhập; cấm tuyên bố "đã đặt lịch/thanh toán/chốt/liên hệ" không có tool ghi thành công tương ứng; cấm tự nhận nới điều kiện — vi phạm thay câu template + bước `guard_output`.
- Tool ghi cần xác nhận (đặt lịch, chốt căn) chỉ trả **bản chuẩn bị**; thao tác thật do FE gửi khi khách bấm.

## 7. Đường lui và độ bền (HN-07)

`model chính → (lỗi tạm thời 5xx/timeout) retry 1 lần (backoff 0,5 s) → HOMEMATCH_AGENT_FALLBACK_MODEL → graph luật (graph_fallback) → template`. Jev lỗi → luật; Goong lỗi → đường thẳng (MP-01). Circuit breaker: 5 lỗi liên tiếp trong 60 s → bỏ qua provider 120 s (model chat và Jev có breaker riêng). Mỗi lần lùi là một bước `guard` trong trace.

## 8. Trace bền và quan sát (HN-05)

Mỗi lượt ghi một dòng `hm_agent_turns` (phase, agent_mode loop|fast_path|graph_fallback, model, llm_calls, input/output_tokens, cost_usd do provider báo, decided_by, outcome answered|asked|handover|safe_reply|error, error_code) và N dòng `hm_agent_steps` (kind llm|tool|guard|decision, duration_ms, summary đã redact). Không lưu prompt/câu trả lời thô (transcript đã PII-mask nằm ở `hm_chat_transcripts` với retention riêng). `GET /admin/agent-turns` trả lượt + p50/p95 + tỉ lệ fallback + chi phí (mỗi lần đọc ghi audit); trang `/quan-tri/van-hanh` hiển thị bảng này.

## 9. Đo và tái lập (HN-08, HN-09)

- `eval/scenarios/agent_e2e.json`: 44 kịch bản nhiều lượt HN/HCM; `python -m eval agent --mode demo` chấm offline (completion, độ chính xác nháp, số câu hỏi trước kết quả, p50/p95); `--mode live` phải `--allow-live` + ngân sách tuyên bố, mặc định in ước tính rồi dừng.
- `eval clarify`: precision/recall/top-1 của lớp hỏi lại trên 40 ca gold.
- `HOMEMATCH_AGENT_RECORD/REPLAY`: cassette JSON ghi request/response model + Jev (đã redact) — phát lại bằng chứng live không tốn phí, cùng message/steps/usage từng chữ.
- Ngưỡng 0,85/0,40/0,2 hiệu chỉnh trên gold; bộ kịch bản đóng băng trước khi đo EV-01 (điểm tổng hợp 39 % → ≥ 60 %).

## 10. Memory và giới hạn

`memory.py` chỉ nhớ sở thích phi tài chính khi khách đồng ý (`/me/memory`), prefill nháp ở trạng thái `inferred`, rút đồng ý là xoá; không lưu tiền, điểm đến. Workspace context (căn đang xem/chọn) chỉ sống trong tiến trình của lượt. Không cổng thanh toán, email/SMS thật, chữ ký số (D-07/D-08); chạy localhost (D-09).
