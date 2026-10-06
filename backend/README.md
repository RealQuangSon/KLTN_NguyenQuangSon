# Backend HomeMatch

**Phạm vi 05/10/2026:** trợ lý gợi ý căn thuê theo nhu cầu và năng lực tài chính ([đề cương](../docs/ke-hoach-kltn-homematch.md)); việc tiếp theo ở [PLAN](PLAN.md) và [AGENT_PLAN](AGENT_PLAN.md), API cần bổ sung ở [API đích](../docs/api-san-pham-v1.md). Lệnh và hành vi dưới đây mô tả backend đang có (schema v9): luồng khách (`renter`) – chủ nhà (`owner`, mỗi chủ duyệt phòng của mình), admin, và 5 phân hệ (tìm kiếm, live chat, thông báo/job, PMS & CRM, trợ lý chủ nhà). Danh sách endpoint ở [api-contract](../docs/api-contract.md).

Backend FastAPI `0.4.0` chạy một process. Dữ liệu demo là kho v2 tổng hợp (220 căn, 4 chủ nhà); mặc định SQLite, rule interpreter và B1, không gọi dịch vụ AI trả phí.

## Chạy từ thư mục gốc dự án

Nếu chưa có môi trường Python:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
```

Backend đọc biến môi trường của process; cần export các giá trị, không tự nạp `.env`:

```bash
unset HOMEMATCH_DATABASE_URL
export HOMEMATCH_DB_PATH=.local/homematch-backend.sqlite
export HOMEMATCH_CATALOG_PATH=data/catalog/rooms.json
export HOMEMATCH_PUBLIC=false
export HOMEMATCH_AUTH_MODE=seed
export HOMEMATCH_LLM_MODE=demo
export HOMEMATCH_MATCHING_METHOD=B1
export HOMEMATCH_EMBEDDING_MODE=disabled
.venv/bin/python -m backend.manage setup
.venv/bin/python -m backend.manage seed-users
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --log-config backend/logging.json
```

Swagger: <http://127.0.0.1:8000/docs>. Frontend hiện có gọi `/api` qua proxy tới port 8000. Tài khoản seed, mật khẩu theo mẫu `local-<username>-password`: `renter-a`, `renter-b` (renter), `owner-a`…`owner-d` (chủ nhà), `admin-a` (admin), `manager-a`, `manager-b` (vai trò cũ, không còn quyền nghiệp vụ); staff seed có membership trong đơn vị mặc định `org-demo`. Ở `HOMEMATCH_PUBLIC=true`, mọi biến `HOMEMATCH_PASSWORD_<USER>` của tài khoản seed (ví dụ `HOMEMATCH_PASSWORD_OWNER_A`) phải đặt mật khẩu mạnh riêng.

## Nghiệp vụ và dữ liệu

Người thuê tạo phiên → nhập/sửa nhu cầu nháp → xác nhận ngân sách, tiện ích và kịch bản chi phí → chờ quản lý duyệt. Quản lý kiểm tra nháp, chọn thứ tự/subset phòng rồi duyệt, từ chối hoặc yêu cầu sửa. Người thuê chỉ thấy kết quả đã duyệt còn hiệu lực, so sánh 2–3 phòng và gửi yêu cầu xem. Yêu cầu xem chỉ thành lịch xác nhận khi quản lý phản hồi.

| Module | Trách nhiệm |
|---|---|
| `app/main.py`, `app/schemas.py`, `app/models.py` | API, schema đầu vào/phản hồi, lỗi có request ID |
| `app/auth.py` | Mật khẩu scrypt, opaque token có hạn/thu hồi, bảo vệ khi xoay mật khẩu; đăng ký/xác minh/reset, hồ sơ, consent, thu hồi phiên (W-03) với stub email ghi log |
| `app/capabilities.py` | Ma trận quyền bốn vai trò là nguồn duy nhất, state dictionary cho organization/membership/account |
| `app/organizations.py` | Đơn vị, membership, room ownership, audit log; bootstrap bất biến khi mở DB |
| `app/projection.py` | Allowlist projection công khai; nháp/tin chưa duyệt/AI pending không thể vào public |
| `app/repository.py`, `app/database.py`, `app/migrations.py` | Giao dịch SQLite/PostgreSQL, CAS, lịch sử hồ sơ và sổ quyết định |
| `app/costs.py`, `app/catalog.py` | Decimal/VND, khoản thiếu khác 0, điều kiện bắt buộc, B1/P và phiên bản xếp hạng |
| `app/service.py`, `app/interpreter.py` | Hai LangGraph, phân quyền, duyệt/công bố, checkpoint và thử lại |
| `app/semantic.py` | Cache embedding theo text/model/dimension, pgvector exact, kiểm tra coverage/vector |
| `app/operations.py`, `logging.json` | Số liệu trong process và log dùng mẫu route, không ghi nội dung người dùng |

Giá/phí cập nhật bằng JSON import có revision; thay kho hoặc xác nhận hồ sơ mới làm gợi ý cũ hết hiệu lực. Tổng chi phí thiếu dữ liệu giữ `null`, không dùng subtotal để tuyên bố đạt ngân sách. Tiền vào ở gồm cọc, thuê trả trước, phí một lần, chuyển nhà và sắm sửa; không cộng tháng đầu lần thứ hai.

Contract API thực thi ở [API contract](../docs/api-contract.md), [OpenAPI](../docs/openapi.json), [trạng thái và lỗi](../docs/status-dictionary.md). Module hợp đồng thuê thuộc v1 thiết kế, chưa có trong mã.

## Tài khoản, đơn vị và projection (mới ở 0.4.0)

Đăng ký/xác minh/khôi phục mật khẩu (`/auth/register`, `/auth/verify`, `/auth/password-reset/*`), hồ sơ + consent (`GET/PATCH /me/profile`) và quản lý phiên (`GET /me/sessions`, `DELETE /me/sessions/{token_id}`) hoạt động offline: thư xác minh do **stub phát triển ghi log** phát (`dev_stub_log_only`), không gọi dịch vụ email thật; ở `HOMEMATCH_PUBLIC=true` các endpoint cần gửi thư trả 503 `delivery_unavailable`. Tài khoản tự đăng ký luôn là renter chưa xác minh; staff role chỉ được cấp qua membership.

Đơn vị (`/organizations`, `/organizations/{id}/memberships`) và ma trận quyền nằm trong `app/capabilities.py`; admin không phải cờ bỏ qua access check. Audit log ghi cùng transaction cho mọi mutation mới; endpoint đọc audit dành cho W-16. Public projection (`app/projection.py`) là allowlist và là nguồn cho catalog công khai HM-03.

## Migration và nhập kho

```bash
.venv/bin/python -m backend.manage migrate
.venv/bin/python -m backend.manage setup
.venv/bin/python -m backend.manage seed-users
.venv/bin/python -m backend.manage import --catalog data/catalog/rooms.json
```

`migrate` chỉ cập nhật schema ledger, không khởi tạo graph/provider hoặc nạp kho. Startup/setup cũng tự chạy migration. `hm_schema_migrations` ghi phiên bản; phiên bản hiện tại là 3 (organizations, memberships, room ownership, audit log, account profiles, verification tokens). DB MVP v1/v2 được tiếp nhận và backfill lịch sử hồ sơ từ run/session, không xóa phiên hay quyết định; bootstrap sau migration tạo đơn vị mặc định, membership cho staff seed tồn tại và mapping ownership cho phòng chưa có. Backend từ chối DB có schema mới hơn code đang chạy. Các bảng checkpoint do LangGraph quản lý; vector do adapter pgvector quản lý.

Kho initial chỉ nạp khi trống. Import validate và commit toàn lô; nhập lại cùng ID/revision/payload giữ nguyên số phòng và catalog hash. Cùng revision khác dữ liệu trả conflict. ID vắng trong file import vẫn được giữ trong kho. Khi thay schema mới, thêm migration vào cuối danh sách; giữ migration đã áp dụng.

## PostgreSQL và pgvector

```bash
bash infra/local-pg.sh start
export HOMEMATCH_DATABASE_URL=postgresql://homematch@127.0.0.1:55432/homematch_dev
.venv/bin/python -m backend.manage setup
.venv/bin/python -m backend.manage seed-users
```

Giữ các biến offline ở trên rồi chạy API. PostgreSQL dùng cùng nghiệp vụ và checkpointer bền vững. Nếu URL kết nối lỗi, ứng dụng báo lỗi, không tự chuyển sang SQLite.

Đường P cần embedding provider và index đầy đủ. Việc gọi provider thật là tùy chọn, cần key server và `index --allow-live`; xem [biến môi trường](../infra/env-inventory.md). Khi thiếu vector/provider, ứng dụng ghi rõ `B1_fallback`; benchmark không coi fallback là P. `diagnostics` của chủ nhà lưu catalog/profile/query hash, ranking config/version và phương pháp thực chạy.

## Phục hồi và vận hành

`GET /health` kiểm tra kết nối ledger; `GET /ready` kiểm tra schema, catalog và checkpoint. Khi không sẵn sàng, trả 503 với lỗi đã lọc. `GET /admin/metrics` yêu cầu admin, trả số request/thời gian tổng theo mẫu route, số lượt generation theo trạng thái/algorithm và usage provider. Số liệu reset khi process khởi động lại; `calls_without_token_usage` phân biệt lượt gọi thiếu usage với lượt không dùng provider.

Quyết định được commit trước khi graph tiếp tục. Nếu resume lỗi, API trả `review_resume_failed`/503; quyết định vẫn ở `reviewed`. Chủ nhà của run hoặc admin đọc lại nháp rồi gọi `POST /landlord/recommendations/{run_id}/retry`, hoặc replay đúng review payload/key. Checkpoint thiếu trả `recovery_required`; người thuê xác nhận lại để tạo và duyệt bản mới. Run `generating`/`generation_failed` được retry thành run mới và phải duyệt lại. Nháp được lưu nhưng generation lỗi vẫn bị ẩn và có thể retry.

Log `homematch.api` chỉ ghi request ID, method, route mẫu, status và thời gian. Cấu hình được cung cấp tắt access log thô. DB/checkpoint và báo cáo thử nghiệm local nằm trong `.local/`, được loại khỏi Git. Hướng dẫn mật khẩu/public và backup ở [runbook](../infra/RUNBOOK.md).

## Kiểm chứng

```bash
.venv/bin/python -m pytest
HOMEMATCH_TEST_DATABASE_URL=postgresql://homematch@127.0.0.1:55432/homematch_test .venv/bin/python -m pytest
.venv/bin/python -m infra.smoke_api --in-process
.venv/bin/python -m infra.smoke_api
```

Tests PostgreSQL tạo schema riêng và dọn sau mỗi ca; các test dùng fixture storage được chạy cho cả SQLite và PostgreSQL khi có test DSN. Ở lần cập nhật 0.4.0 này, tổ hợp test backend do wave backend sở hữu đạt **69 passed, 4 skipped** (PostgreSQL bỏ qua khi không có `HOMEMATCH_TEST_DATABASE_URL`; đã chạy thêm bộ PG/pgvector thật: pass). HTTP thật đã kiểm tra luồng hai vai trò trên cả SQLite và PostgreSQL qua `infra/smoke_api`. Chi tiết ở [báo cáo backend](../docs/kiem-chung-backend.md).

GPT/embedding thật, browser FE↔BE, backup/restore và triển khai cloud cần bằng chứng riêng; vector giả lập chỉ kiểm chứng adapter SQL và công thức xếp hạng.
