# Backend HomeMatch

Backend của trợ lý gợi ý căn thuê theo nhu cầu và năng lực tài chính. Hợp đồng API ở [api-contract.md](../docs/api-contract.md), kiến trúc agent ở [thiet-ke-agent.md](../docs/thiet-ke-agent.md).

Backend FastAPI `0.4.0` chạy một process. Dữ liệu demo là kho v2 tổng hợp (220 căn, một tài khoản chủ nhà mỗi thành phố); mặc định SQLite, rule interpreter và B1, không gọi dịch vụ AI trả phí.

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

Swagger: <http://127.0.0.1:8000/docs>. Frontend hiện có gọi `/api` qua proxy tới port 8000. Bốn tài khoản dùng thử với mật khẩu chung `123456`: `renter` (người thuê), `owner1` (chủ nhà Hà Nội), `owner2` (chủ nhà TP.HCM), `admin` (quản trị viên); staff seed có membership trong đơn vị mặc định `org-demo`. Mỗi tài khoản có thể đặt mật khẩu riêng qua `HOMEMATCH_PASSWORD_<USERNAME>` (ví dụ `HOMEMATCH_PASSWORD_OWNER1`); ở `HOMEMATCH_PUBLIC=true` mọi biến này phải đặt mật khẩu mạnh riêng (≥16 ký tự).

## Nghiệp vụ và dữ liệu

Người thuê tạo phiên → nhập/sửa nhu cầu nháp → xác nhận ngân sách, tiện ích và kịch bản chi phí → xếp hạng chạy và công bố kết quả ngay trong lượt (quyết định 05/11/2026, không còn bước chủ nhà duyệt gợi ý). Người thuê so sánh 2–3 phòng và gửi yêu cầu xem; yêu cầu xem thành lịch xác nhận khi chủ nhà (hoặc admin điều phối) phản hồi.

| Module | Trách nhiệm |
|---|---|
| `app/main.py`, `app/schemas.py`, `app/models.py` | API, schema đầu vào/phản hồi, lỗi có request ID |
| `app/auth.py` | Mật khẩu scrypt, opaque token có hạn/thu hồi, bảo vệ khi xoay mật khẩu; đăng ký/xác minh/reset, hồ sơ, consent, thu hồi phiên (W-03) với stub email ghi log |
| `app/capabilities.py` | Ma trận quyền ba vai trò là nguồn duy nhất, state dictionary cho organization/membership/account |
| `app/organizations.py` | Đơn vị, membership, room ownership, audit log; bootstrap bất biến khi mở DB |
| `app/projection.py` | Allowlist projection công khai; nháp/tin chưa duyệt/AI pending không thể vào public |
| `app/repository.py`, `app/database.py`, `app/migrations.py` | Giao dịch SQLite/PostgreSQL, CAS, lịch sử hồ sơ và sổ quyết định |
| `app/costs.py`, `app/catalog.py` | Decimal/VND, khoản thiếu khác 0, điều kiện bắt buộc, B1/P và phiên bản xếp hạng |
| `app/service.py`, `app/interpreter.py` | Hai LangGraph, phân quyền, công bố, checkpoint và thử lại |
| `app/semantic.py` | Cache embedding theo text/model/dimension, pgvector exact, kiểm tra coverage/vector |
| `app/operations.py`, `logging.json` | Số liệu trong process và log dùng mẫu route, không ghi nội dung người dùng |

Giá/phí cập nhật bằng JSON import có revision; thay kho hoặc xác nhận hồ sơ mới làm gợi ý cũ hết hiệu lực. Tổng chi phí thiếu dữ liệu giữ `null`, không dùng subtotal để tuyên bố đạt ngân sách. Tiền vào ở gồm cọc, thuê trả trước, phí một lần, chuyển nhà và sắm sửa; không cộng tháng đầu lần thứ hai.

Contract API thực thi ở [API contract](../docs/api-contract.md), [OpenAPI](../docs/openapi.json), [trạng thái và lỗi](../docs/status-dictionary.md).

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

`migrate` chỉ cập nhật schema ledger, không khởi tạo graph/provider hoặc nạp kho. Startup/setup cũng tự chạy migration. `hm_schema_migrations` ghi phiên bản; phiên bản hiện tại là 24. DB MVP v1/v2 được tiếp nhận và backfill lịch sử hồ sơ từ run/session, không xóa phiên hay quyết định; bootstrap sau migration tạo đơn vị mặc định, membership cho staff seed tồn tại và mapping ownership cho phòng chưa có. Backend từ chối DB có schema mới hơn code đang chạy. Các bảng checkpoint do LangGraph quản lý; vector do adapter pgvector quản lý.

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

Quyết định được commit trước khi graph tiếp tục. Kết quả công bố ngay sau xếp hạng; người thuê chạy lại vòng tìm lỗi của phiên mình, quản trị viên khôi phục run lỗi toàn hệ thống. Run `generating`/`generation_failed` được retry thành run mới. Nháp được lưu nhưng generation lỗi vẫn bị ẩn và có thể retry.

Log `homematch.api` chỉ ghi request ID, method, route mẫu, status và thời gian. Cấu hình được cung cấp tắt access log thô. DB/checkpoint và báo cáo thử nghiệm local nằm trong `.local/`, được loại khỏi Git. Hướng dẫn mật khẩu/public và backup ở [runbook](../infra/RUNBOOK.md).

## Kiểm chứng

```bash
.venv/bin/python -m pytest
HOMEMATCH_TEST_DATABASE_URL=postgresql://homematch@127.0.0.1:55432/homematch_test .venv/bin/python -m pytest
.venv/bin/python -m infra.smoke_api --in-process
.venv/bin/python -m infra.smoke_api
```

Tests PostgreSQL tạo schema riêng và dọn sau mỗi ca; các test dùng fixture storage được chạy cho cả SQLite và PostgreSQL khi có test DSN.

GPT/embedding thật, browser FE↔BE, backup/restore và triển khai cloud cần bằng chứng riêng; vector giả lập chỉ kiểm chứng adapter SQL và công thức xếp hạng.
