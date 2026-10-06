# Kiến trúc bản đang chạy (schema v9)

**Cập nhật:** 05/10/2026, sau E1–E6. Tài liệu này mô tả code hiện có. Kiến trúc đích (deploy, live) ở [kien-truc-homematch.md](kien-truc-homematch.md); khoảng cách giữa hai bản ở [trang-thai-trien-khai.md](trang-thai-trien-khai.md).

## Thành phần

```mermaid
flowchart LR
  R[Người thuê] --> FE[React + TypeScript]
  O[Chủ nhà] --> FE
  A[Quản trị] --> FE
  FE --> API[FastAPI: auth, quyền, DTO]
  API --> S[HomeMatchService]
  S --> C[Chat graph: supervisor → nhu cầu / tài chính / cẩm nang / hỗ trợ]
  S --> G[Recommendation graph: xếp hạng → nháp → interrupt → chủ nhà duyệt → chốt]
  S --> T[Tìm kiếm, tư vấn so sánh, cẩm nang]
  S --> L[Live chat + chuyển giao]
  S --> P[PMS & CRM: hợp đồng, hóa đơn, bảo trì, khách tiềm năng]
  S --> K[Trợ lý chủ nhà: bài đăng, giá, phòng trống]
  S --> N[Thông báo + job nền]
  C -. LLM_MODE=openai .-> GPT[GPT-4o]
  G --> F[costs.py + lọc cứng + B1/P]
  F -. P .-> V[pgvector + cache truy vấn]
  S --> DB[(SQLite / PostgreSQL: ledger, kho, checkpoint)]
```

| Module backend | Vai trò |
|---|---|
| `main.py` | Route, auth bearer, luồng job nền (`HOMEMATCH_JOBS_INTERVAL_SECONDS`) |
| `service.py` | Quy tắc nghiệp vụ, kiểm vai trò và quyền bản ghi, gửi thông báo, hai graph LangGraph |
| `agents.py` | `ToolBox`: danh sách tool theo agent (needs, finance, ranking, support, handbook), tối đa 4 bước |
| `catalog.py`, `costs.py`, `locations.py`, `semantic.py` | Kho và lọc cứng, B1/P; tiền và vay; tên khu vực; embedding và cache |
| `repository.py` | Phiên, hồ sơ, run, duyệt theo chủ nhà (`hm_run_reviews`), lịch xem |
| `listings.py`, `advisor.py`, `handbook.py` | Tìm theo bộ lọc, tư vấn so sánh, cẩm nang |
| `conversations.py`, `notifications.py`, `automation.py` | Live chat và che PII, thông báo chống trùng, job định kỳ |
| `pms.py`, `copilot.py` | Hợp đồng, công tơ, hóa đơn, thanh toán, bảo trì, CRM, dashboard; bài đăng, giá, cố vấn |
| `memory.py`, `auth.py`, `organizations.py`, `capabilities.py`, `agent_capability.py` | Memory có đồng ý; tài khoản; đơn vị và audit; ma trận quyền |

## Vai trò

Có ba vai trò nghiệp vụ: `renter` (khách), `owner` (chủ nhà), `admin`. Phòng thuộc chủ nhà qua `Room.landlord_id`; phòng không có giá trị này mặc định thuộc `owner-a`. Vai trò `manager` cũ vẫn đăng nhập được nhưng không có quyền nghiệp vụ.

## Dữ liệu (schema v9)

| Nhóm | Bảng |
|---|---|
| Tài khoản, đơn vị | `hm_users`, `hm_tokens`, `hm_account_profiles`, `hm_verification_tokens`, `hm_organizations`, `hm_memberships`, `hm_room_ownership`, `hm_audit_log` |
| Trợ lý AI | `hm_sessions`, `hm_profile_snapshots`, `hm_runs`, `hm_run_reviews` (v5), `hm_preference_memory` (v4), `hm_query_embeddings` (v4), `hm_chat_transcripts` (v7) |
| Kho | `hm_rooms`, `hm_catalog_meta`, `hm_embeddings` (chỉ PG), `hm_room_views` (v6) |
| Giao tiếp | `hm_viewings` (v6: lịch từ tin; v5: mode, link họp), `hm_conversations`, `hm_messages` (v7), `hm_notifications`, `hm_job_runs` (v8), `hm_support` |
| PMS & CRM (v9) | `hm_leases`, `hm_meter_readings`, `hm_invoices`, `hm_payments`, `hm_payment_claims`, `hm_maintenance`, `hm_leads` |

**Nguyên tắc dữ liệu:**
- CAS theo revision cho nháp, hồ sơ, kho và tin.
- Khóa chống gửi trùng cho duyệt, lịch xem, thông báo.
- Hóa đơn đã phát hành không sửa được; thanh toán chỉ thêm bản ghi mới.
- Hợp đồng có phiên bản; sửa hợp đồng thì phải chấp thuận lại.

## Luồng duyệt theo chủ nhà

```mermaid
sequenceDiagram
  participant R as Khách
  participant S as Service
  participant G as Graph
  participant O as Các chủ nhà
  R->>S: Confirm hồ sơ
  S->>G: Xếp hạng → lưu nháp → interrupt
  O->>S: Mỗi chủ quyết định phần phòng của mình
  S-->>R: partially_published: phòng đã duyệt hiện dần
  S->>S: Mọi chủ đã quyết định → ghi decision cuối
  S->>G: Resume bằng event_id → kiểm phiên bản → chốt
```

## Giới hạn vận hành

- Một API process: luồng job chạy trong cùng process; không có outbox riêng.
- Live chat và thông báo cập nhật bằng đọc lại định kỳ (5 giây / 30 giây), không dùng WebSocket.
- Email là stub ghi log. Bản đồ dùng tile OpenStreetMap, cần internet ở trình duyệt.
- Docker và Railway mới là cấu hình chuẩn bị.
