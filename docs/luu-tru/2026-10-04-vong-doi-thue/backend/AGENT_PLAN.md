# Kế hoạch AI Agent HomeMatch

Phiên bản 04/10/2026. Agent phục vụ HM-04 và nối thông tin/tác vụ trong toàn sản phẩm HM-01..10. Đọc [thiết kế Agent](../docs/thiet-ke-agent.md), [plan chi tiết](AGENT_DETAILED_PLAN.md), [Backend plan](PLAN.md) và [AC sản phẩm](../docs/tieu-chi-nghiem-thu.md).

## 1. Hiện trạng

Rule/OpenAI interpreter, hai graph, draft provenance, confirm/CAS, deterministic cost/B1/P adapter, HITL/event resume và SQLite/PG checkpoint đã có mã. Default offline; fake clients/vector fixtures chưa chứng minh live quality. Chưa có tools contract/billing/maintenance hoặc memory account đầy đủ; chỉ hai roles hiện tại. API thực tế giữ [0.3.0](../docs/api-contract.md).

**Trạng thái 05/10/2026 (slice W-07 + guardrails HM-01/10 phía agent):** `agent_capability.py` (ma trận action/role + ownership/assignment, chặn payload đặc quyền khi resume), `agent_guard.py` (screen injection, `redact_tree`, taxonomy provider + fallback guided-form, viewing prep), `agent_budget.py` (ngân sách call theo phiên, `budget_exceeded` 429), `agent_provenance.py` (stamp nguồn/node) đã có và được service dùng; test `test_agent_guardrails.py`, `test_agent_capability.py`, `test_agent_provenance.py` chạy offline. Provenance/guard chi tiết nằm ở `HomeMatchService.agent_trace` (service-level) vì schemas hiện tại `extra="forbid"` — cần BE thêm trường optional để lộ qua HTTP. Injection screening là heuristic offline (best-effort), chưa phải bằng chứng chống injection toàn diện; chưa có live quality/token thực.

## 2. Công việc theo HM

| ID | Trách nhiệm Agent | Phụ thuộc/gate | Điều kiện xong |
|---|---|---|---|
| HM-01/10 | Context/tool scope theo actor/resource, prompt injection/privacy/call budgets, không role từ model | Backend permission P0/P1 | Wrong actor/resource bị service chặn; trace không raw PII; quota/error rõ |
| HM-02/03 | Chuẩn hóa từ điển tiêu chí, đọc public projection/evidence; phân biệt public và AI | Catalog/public schema P1/P2 | Không lộ draft/tin chưa duyệt hoặc bịa nguồn/địa chỉ |
| HM-04 | Extraction/routing/questions/edit/remove/confirm UX, cost tools, B1/P grounding/HITL/recovery | Backend ledger/finance, dev fixtures → P2 | Mơ hồ hỏi/form; money/approval xác định; stale/replay/restart đúng |
| HM-05 | History/preferences/context consent và public/AI compare navigation | Account storage/privacy → P2 | Không nhớ ngầm tài chính; clear/history khác profile/checkpoint |
| HM-06 | Handoff và viewing request preparation/status read; notifications chỉ service | Viewing/queue → P2; thuê events P3 | Requested khác confirmed/accepted, không tự liên hệ/giữ phòng |
| HM-07 | Hướng dẫn đọc terms/contract/tenancy có quyền, dẫn đến acceptance/handover form | Contract/tenancy service → P3 | Không chốt/activate từ chat, version/actor acceptance rõ |
| HM-08 | Giải thích estimate/invoice/remaining amount từ engine/DTO, hướng dẫn payment record | Billing/reconcile service → P3 | Không tự tính số/chốt paid; “đã chuyển” khác “đã nhận” |
| HM-09 | Hướng dẫn hoặc chuẩn bị maintenance form, đọc tiến độ đúng quyền | Maintenance service → P3 | Không tự đặt thợ/chi phí; completion có actor/evidence |
| HM-10 | Operational error taxonomy/usage/version/runbook và live quality evidence | Cắt ngang → P4; research P5 | Fixtures/live riêng, errors không bị che, output có provenance |

Năng lực sau thuê bắt buộc có trải nghiệm hướng dẫn phù hợp; không bắt buộc thêm một LLM tự trị cho từng module. Form/navigation/service deterministic có thể hoàn thành tác vụ rõ. Nhiều node không tự là multi-agent.

## 3. Bất biến

Model không tính tiền, viết SQL tùy ý, cấp quyền, xác nhận profile, duyệt recommendation, giữ phòng, chốt hợp đồng, phát hành invoice hoặc ghi nhận received/reconciled. Backend/tools làm các bước đó từ actor có quyền, CAS và consent.

Public catalog đã moderation được xem/so sánh/đặt yêu cầu theo listing revision; AI recommendations pending vẫn ẩn. Cost/support rõ dùng routing trực tiếp; provider lỗi chuyển form, không bịa kết quả. Estimate khác bill; handoff requested khác người nhận xử lý.

## 4. Gates và evidence

P0 schema/tool/intent/permission/state; P2 draft/routing/finance/grounding/HITL/public isolation/viewing/handoff; P3 sau thuê đúng state; P4 error/quota/privacy/injection/browser/runbook; P5 freeze prompt/config rồi đánh giá provider thật và B1/P với nhãn độc lập.

Bàn giao version schema/prompt/model/tool, fake/live test reports, dev error analysis, usage/token/machine latency thực và review waiting riêng. F1/nDCG/grounding/latency là kết quả cần đo; không hứa đạt hoặc lấy fake client làm chất lượng model. AG-01..09/checklist MVP là lịch sử.

