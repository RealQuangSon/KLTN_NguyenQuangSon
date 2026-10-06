# Kế hoạch AI Agent

**Cập nhật:** 05/10/2026. Thiết kế ở [thiet-ke-agent.md](../docs/thiet-ke-agent.md). Yêu cầu FR-01–04, FR-21–22 ở [danh mục](../docs/yeu-cau-san-pham.md).

> **Việc tiếp theo (06/10/2026):** làm theo [coding plan](../docs/coding-plan/agent.md); đọc [phần chung](../docs/coding-plan/README.md) trước.

## 1. Hiện có

- `interpreter.py`: `DemoInterpreter` (luật, alias khu vực qua `locations.py`) và `OpenAIInterpreter` (GPT-4o structured output, `store=False`).
- `service.py`: chat graph (supervisor `route`, agent `interview`/`finance`/`support`/`handbook`) và recommendation graph (agent xếp hạng ở node `rank`, `interrupt()` chờ từng chủ nhà duyệt phòng của mình).
- `agents.py`: `ToolBox` với danh sách tool từng agent, tối đa 4 bước; `memory.py`: memory có đồng ý.
- `agent_guard.py` (injection/PII), `agent_budget.py` (giới hạn lượt), `agent_capability.py` (tool theo vai trò), `agent_provenance.py`.

## 2. Việc

| Task | Việc | Điều kiện xong |
|---|---|---|
| T2.1 ✓ | Extraction nhận `apartment`, `bedrooms`; prompt cập nhật; gold mới cho căn hộ và Hà Nội | `eval extraction` chạy với gold v2 |
| T3.1 ✓ | Supervisor + subgraph nhu cầu, tài chính, xếp hạng; danh sách tool được phép từng agent; tối đa 4 bước mỗi lượt | AC-11; số lượt gọi LLM mỗi lượt không tăng so với hiện tại ở cùng bộ câu |
| T3.2 ✓ | Recommendation graph trở thành phần của agent xếp hạng | Toàn bộ test HITL/durability vẫn pass |
| T3.3 ✓ | Đọc memory khi đã đồng ý, điền sẵn `inferred` với nguồn `memory:<phiên>` | AC-12 |
| Còn lại | Ý định `simulate_finance`: agent tài chính trả lời "nếu vay 6 tháng thì sao" bằng tool `estimate_loan`/`simulate_scenarios` | Mọi số trong câu trả lời trùng output tool |

## 3. Bất biến

- LLM không tính tiền, không xác nhận hồ sơ, không duyệt, không nới điều kiện.
- Tiền và liên hệ được tách trước khi gửi LLM. Thu nhập không bao giờ vào prompt.
- Lỗi provider → form fallback, không bịa kết quả trích xuất.
- Nhiều agent không đồng nghĩa nhiều lượt gọi LLM. Định tuyến rõ ràng dùng luật.
