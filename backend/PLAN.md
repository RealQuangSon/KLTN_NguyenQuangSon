# Kế hoạch Backend

**Cập nhật:** 05/10/2026. Task theo [kế hoạch triển khai](../docs/ke-hoach-trien-khai.md); yêu cầu ở [danh mục](../docs/yeu-cau-san-pham.md). Phần agent ở [AGENT_PLAN.md](AGENT_PLAN.md). Cách chạy và kiểm chứng ở [README.md](README.md).

> **Việc tiếp theo (06/10/2026):** làm theo [coding plan](../docs/coding-plan/be.md); đọc [phần chung](../docs/coding-plan/README.md) trước.

## 1. Nền tảng hiện có (0.4.0)

- FastAPI `main.py`; service và hai graph LangGraph `service.py`; ledger SQLite/PostgreSQL (`database.py`, `repository.py`, `migrations.py`, schema v9).
- `costs.py` (tổng tháng, tiền vào ở), `catalog.py` (lọc cứng, B1/P), `semantic.py` (embedding, pgvector), `locations.py` (alias thành phố/khu vực).
- Auth seed và tự đăng ký có xác minh (stub log), token thu hồi được. Vai trò nghiệp vụ: khách, chủ nhà, admin; đơn vị, audit (`auth.py`, `capabilities.py`, `organizations.py`).
- Đợt E1–E6: `listings.py`, `advisor.py`, `handbook.py`, `conversations.py`, `notifications.py`, `automation.py`, `pms.py`, `copilot.py` (chi tiết ở [kiến trúc đang chạy](../docs/kien-truc-trien-khai.md)).

## 2. Bất biến không được phá

- Tiền chỉ do `costs.py` (và engine tài chính mới) tính, bằng `Decimal`, giữ `null` cho khoản chưa biết.
- Lọc cứng trước xếp hạng; không tự nới; B1 và P trên cùng tập đủ điều kiện.
- Khách chỉ thấy run `published` đúng phiên bản hồ sơ và kho. Node trước `interrupt()` không ghi. Quyết định commit trước resume.
- Dùng CAS/revision cho nháp, hồ sơ, kho; idempotency key cho duyệt và lịch xem.
- Một API worker. SQL viết với `?`, adapter tự đổi sang `%s` cho psycopg.

## 3. Việc theo giai đoạn

| Task | Việc | File chính | Test cần có |
|---|---|---|---|
| T2.1 ✓ | `room_type` thêm `apartment`; `bedrooms`, `features_text`, `min_bedrooms`. Không cần migration vì căn lưu JSON. | `models.py`, `catalog.py`, `interpreter.py`, `semantic.py` | `test_finance.py` (lọc phòng ngủ) |
| T2.3 ✓ | `monthly_income_vnd`, `cost_split`; khối `affordability` trong `CostResult` | `costs.py`, `models.py` | `test_finance.py`, oracle `L03`–`L07` |
| T2.4 ✓ | Vay annuity, điều kiện `loan_principal`/`loan_burden` | `costs.py`, `catalog.py` | Oracle `L01`, `L02`, `L05`; `test_finance.py` |
| T2.5 ✓ | DTO chủ nhà bỏ thu nhập, `housing_ratio = null` | `service.py` | `test_sale_projection_hides_income_and_exact_ratio` |
| T2.6 ✓ | `override_reason`, lưu `agent_order`, `overridden` | `repository.py`, `models.py`, `schemas.py` | `test_workflow.py` |
| T2.7 ✓ | `GET /locations` | `main.py`, `locations.py` | `test_locations_endpoint_and_cost_estimate_with_affordability` |
| T3.1–T3.2 ✓ | `agents.py` (`ToolBox`, danh sách tool), node chat theo agent, `diagnostics.agent` | `agents.py`, `service.py` | `test_agents_memory.py` |
| T3.3 ✓ | `hm_preference_memory` (migration v4), `memory.py`, `/me/memory` | `memory.py`, `main.py`, `migrations.py` | `test_agents_memory.py` |
| T3.4 ✓ | `QueryEmbeddingCache` (`hm_query_embeddings`), `semantic_usage` | `semantic.py`, `operations.py` | `test_query_embedding_cache_survives_a_new_cache_instance` |
| T4.2 ✓ (API) | `POST /sessions/{id}/simulate` | `main.py`, `service.py` | `test_simulation_is_read_only_and_limited_to_approved_rooms` |

Mỗi thay đổi API phải cập nhật `docs/api-contract.md` và sinh lại `docs/openapi.json`.
