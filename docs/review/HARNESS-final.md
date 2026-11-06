# Review tổng kết HARNESS — HN-00 → HN-12

Ngày: 06/11/2026 · Reviewer: GLM (tự review độc lập) · Phạm vi: PLAN.md §4H, thứ tự HN-00 → HN-03 → HN-02 → HN-01 → HN-04 → HN-06 → HN-05 → HN-08 → HN-09 → HN-07 → HN-11 → HN-10 → HN-12

## 1. Bảng 13 task

| Task | Trạng thái | Commit | Test chính | Phát hiện còn mở |
|---|---|---|---|---|
| HN-00 Định dạng Jev Decisions API | Đạt (offline; live là bằng chứng bàn giao 06/11) | `edb842c` | `test_jev_payload_matches_decisions_api_shape`, `test_jev_fake_accepts_and_falls_back_on_error` | — |
| HN-03 Registry + hợp đồng tool | Đạt | `4628c09` | `test_registry_generates_allowlist_capability_and_only_exposed_specs` | — |
| HN-02 ask_user đi qua kho + Jev | Đạt offline; live HUST chưa | `6cc1157` | `test_ask_user_uses_catalog_chips_and_stops_following_writes`, `test_confirm_requires_clarification_before_creating_run` | Live: chip bán kính có số căn thật trên kho Neon |
| HN-01 Vòng lặp: giới hạn, tốc độ, fast path | Đạt offline; p50/p95 live chưa | `60f0cbe` | `test_read_only_tools_in_one_response_run_in_parallel`, `test_loop_stops_after_four_llm_calls`, `test_fast_path_confirms_without_any_llm_call` | Đo p50 ≤ 4 s cần live |
| HN-04 Ngữ cảnh + bộ nhớ hội thoại | Đạt offline | `5ff3ae9` | `test_context_carries_workspace_and_results_but_never_income`, `test_summary_updates_every_four_turns_without_tools_call` | Hiệu quả tóm tắt trên model thật cần live |
| HN-06 Guardrail vào/ra + ngân sách | Đạt offline | `b8b8d65` | `test_twenty_ai_turns_spend_twenty_units_not_more`, `test_tool_payload_is_filtered_and_wrapped_as_untrusted`, `test_guard_replaces_unbacked_booking_and_income_claims` | Ảnh ≤ 5 MB gắn AG-04 (chưa làm); Jev cost chưa vào trần |
| HN-05 Trace bền + quan sát | Đạt offline | `bb90092` | `test_one_turn_row_and_n_step_rows_per_turn`, `test_admin_agent_turns_aggregates_and_audits` | Jev `usage.cost` chưa ghi vào turn; VND chưa nối panel |
| HN-08 Bộ kịch bản + chấm điểm | Đạt offline | `6f26097` | `test_demo_run_scores_all_scenarios`, `test_clarify_suite_reports_calibration_against_gold` | Recall clarify 0,5 còn dính giới hạn kho synthetic (CL08/09/15–20); eval live chưa chạy |
| HN-09 Cassette ghi/phát lại | Đạt offline (cơ chế) | `64ccfd8` | `test_record_then_replay_reproduces_identical_turn`, `test_jev_record_and_replay_without_network` | Chưa có cassette live thật |
| HN-07 Đường lui + circuit breaker | Đạt offline | `2fae3ab` | `test_fallback_model_takes_over_after_primary_fails`, `test_circuit_breaker_opens_after_five_consecutive_failures` | 429 rate-limit coi là non-transient — cần quan sát live |
| HN-11 Phân vai theo pha | Đạt offline | `c099138` | `test_interview_phase_hides_transaction_and_result_tools`, `test_transaction_phase_after_viewing_or_handover` | Hiệu quả chọn-tool đo live ở EV-01 |
| HN-10 Stream delta + replace | Đạt offline | `42518a8` | `test_stream_emits_steps_then_done`, `test_stream_replaces_answer_when_post_check_fails`; Vitest `HN-10: stream delta…` | Độ trễ delta thật cần live |
| HN-12 Tài liệu harness | Đạt | `f554010` | đối chiếu tài liệu ↔ code trực tiếp | `AGENTS.md` root còn mô tả HITL cũ — ngoài phạm vi §4H |

Mỗi task có file review riêng `docs/review/HN-xx.md` (đối chiếu PLAN, checklist bất biến, kết quả lệnh, phát hiện BLOCKER/MAJOR/MINOR và xử lý). Tổng cộng 13/13 task đã commit, không còn BLOCKER/MAJOR mở; các MINOR được ghi lý do giữ lại trong từng review.

## 2. Đối chiếu "Xong harness khi" (PLAN §4H)

| # | Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|---|
| 1 | "Tìm phòng trọ dưới 4 triệu gần HUST" live trên kho Neon: chip bán kính có số căn thật, Jev xếp thứ tự, bấm chip → kết quả + bản đồ, lượt đầu ≤ 6 s | **Chưa** — cần người dùng duyệt live (mục 4) | Offline đã phủ: `test_fast_path_returns_catalog_chip_when_ambiguous` (chip count/patch/decided_by), `test_confirm_requires_clarification_before_creating_run`; chưa có bằng chứng live nào, không đánh dấu Đạt |
| 2 | 20 lượt liên tiếp trong một phiên không hết ngân sách | **Đạt (offline)** — logic ngân sách tất định | `test_twenty_ai_turns_spend_twenty_units_not_more` (20 lượt × 2 lần gọi LLM = đúng 20 đơn vị, còn 40 dư) |
| 3 | `eval agent --mode demo` chạy đủ kịch bản, báo cáo p50/p95/chi phí | **Đạt (demo)** — 44/44 hoàn thành, turn_pass 1,0; p50 30,9 ms / p95 71,8 ms; `cost_usd` ở demo là null (chi phí chỉ có ở live — đúng hợp đồng "không ước lượng") | `eval/runs/development/agent.json`; `test_demo_run_scores_all_scenarios` |
| 4 | Mọi lượt có trace bền xem được ở trang admin | **Đạt (offline)** | `hm_agent_turns`+`hm_agent_steps` (v20/v21); `test_one_turn_row_and_n_step_rows_per_turn`, `test_admin_agent_turns_aggregates_and_audits`; panel `/quan-tri/van-hanh` |
| 5 | `bash infra/check-local.sh` exit 0 | **Đạt** | Chạy 06/11: EXIT=0 — eval pipeline (gồm `eval agent --mode demo` 44/44 + `eval clarify`) + pytest **657 passed, 8 skipped** + Vitest **109 passed** (25 file) + build + demo + smoke |

Bổ sung: `.venv/bin/python -m eval agent --mode demo` chạy riêng 06/11 — completion 1,0; `eval clarify`: precision 1,0 / recall 0,5 / top1 1,0 (8 ca còn lại là giới hạn kho synthetic — xem HN-08).

## 3. Bằng chứng tổng

- `bash infra/check-local.sh` → **EXIT=0** (log đầy đủ đã chạy 06/11): eval validate/oracle/extraction/ranking/metrics/invariants/intents/invoices/grounding/measure/report/**agent demo**/**clarify**; pytest 657/8; Vitest 109; build; demo; smoke.
- Số schema: v21 (`hm_agent_turns`/`steps` + `phase`); `docs/openapi.json` 103 paths, khớp app.
- Không có bí mật/DB/`.local`/checkpoint trong bất kỳ commit nào (đã kiểm `git status`/`git add` từng file ở mọi commit).

## 4. Việc cần người dùng (live — chưa có bằng chứng, chưa chạy lần nào)

Tất cả mục dưới đây **chưa chạy**: cần key OpenRouter (`OPENAI_API_KEY`), model `OPENAI_MODEL=openai/gpt-6-luna` (đã kiểm hỗ trợ tools 06/11) và kho Neon. Không có bảng giá công khai đáng tin của `gpt-6-luna` tại thời điểm này nên mọi con số USD dưới đây là **ước tính để duyệt trần, chưa phải chi phí đo** — kiểm bảng giá OpenRouter trước khi chạy.

### 4.1. Một lượt HUST trên Neon (tiêu chí #1) — ước ≤ 0,05–0,10 USD
```bash
bash infra/run-neon.sh                      # server + kho Neon (chỉ đọc)
export OPENAI_API_KEY=… OPENAI_MODEL=openai/gpt-6-luna \
       HOMEMATCH_LLM_MODE=openai HOMEMATCH_DECISION_MODE=jev \
       HOMEMATCH_DATABASE_URL="$(grep HOMEMATCH_DATABASE_URL .local/neon.env | cut -d= -f2-)"
HOMEMATCH_AGENT_RECORD=.local/cassette-hust.json .venv/bin/python -m uvicorn backend.app.main:app \
  --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --log-config backend/logging.json
```
Rồi gửi đúng câu "Tìm phòng trọ dưới 4 triệu gần HUST cho 1 người" từ `/tro-ly-ai`: kiểm chip bán kính có `count` thật + `decided_by="jev"`, bấm chip → kết quả + bản đồ, đo thời gian lượt đầu (mục tiêu ≤ 6 s). Sau đó phát lại không mạng: `HOMEMATCH_AGENT_REPLAY=.local/cassette-hust.json` (không key, không mạng). **Rà soát cassette trước khi lưu vào luận văn** (`jq` kiểm không có PII) — nội dung là bản đã redact nhưng vẫn nên kiểm mắt một lần.
Ước gọi: 3–6 lần model + 1–2 Jev. Trần đề xuất: **0,10 USD**.

### 4.2. Đo p50/p95 trên 20 câu (tiêu chí tốc độ HN-01) — ước ≤ 0,05–0,15 USD
20 câu tìm phòng phổ biến (HN/HCM) qua `/messages/stream`, đọc p50/p95 từ `GET /admin/agent-turns?limit=40`. Trần đề xuất: **0,15 USD**.

### 4.3. `eval agent --mode live` (44 kịch bản) — ước 90–180 lần gọi model + ~44 Jev, trần **0,50 USD**
```bash
.venv/bin/python -m eval agent --mode live --allow-live --api-budget-vnd 500000 \
  --output eval/runs/development/agent-live.json
```
Sau khi chạy: bổ sung số thật vào §9 `docs/thiet-ke-agent.md`, mục 2.7 `docs/nghiep-vu-va-harness.md`, và đánh dấu lại tiêu chí #1/#3 của bảng trên.

### 4.4. Việc nhỏ kèm theo (không tốn phí)
- Cập nhật `AGENTS.md` theo D-10 (còn mô tả "landlord approves").
- Ghi `usage.cost` của Jev vào `hm_agent_turns.cost_usd` + quy VND (`cost_metrics.py`) vào panel admin (đang chỉ USD từ model).
- Nếu đo lại clarify trên kho Neon (có phí, có căn sân bay/KCN): chạy lại `eval clarify` và cập nhật recall.

## 5. Tự đánh giá trung thực

- 13/13 task theo §4H đã làm đủ 6 bước quy trình (kế hoạch → code → test → review độc lập → sửa phát hiện → commit kèm review); mọi BLOCKER/MAJOR tìm thấy (deadlock service.lock, crash sqlite đa luồng, UnboundLocalError cache quyết định, regex "thạnh", AMENITIES thiếu 10 khóa, mất nhãn replace…) đã sửa và có test ghim.
- Không có gì trong bản này tuyên bố "đã chạy live/PG/E2E" — PG test vẫn skip (không cấu hình `HOMEMATCH_TEST_DATABASE_URL`), live chưa được phép, trình duyệt chưa quay.
- Phạm vi ngoài §4H không đụng tới: AG-06/MP-01/FL-xx/EV-01/EV-02/E2E-01… theo đúng bàn giao.
