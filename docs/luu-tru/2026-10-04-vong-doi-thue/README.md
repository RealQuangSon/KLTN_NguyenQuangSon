# HomeMatch — tìm và quản lý thuê phòng với trợ lý AI

**Định hướng sản phẩm cập nhật 04/10/2026:** HomeMatch hoàn thiện toàn vòng đời thuê phòng/studio: tìm và so sánh → xem phòng → hợp đồng/bàn giao → công tơ/hóa đơn/đối soát → sửa chữa/gia hạn/trả phòng. Bốn vai trò đích là người thuê, chủ nhà, quản lý và quản trị viên. [Bộ docs sản phẩm](docs/README.md) viết lại từ nghiên cứu HubHome, với 10 module bắt buộc, yêu cầu, quy trình, API đích và tiêu chí nghiệm thu.

**Mã hiện có là nền tảng local 0.3.0, chưa phải sản phẩm v1 hoàn thiện.** Đang chạy luồng hai vai trò: hỏi rõ → xác nhận nhu cầu/ngân sách → lọc/rank → quản lý duyệt → xem/so sánh/đề xuất lịch. Chức năng sau thuê và portal owner/admin cần triển khai theo [kế hoạch mới](docs/ke-hoach-trien-khai.md). Phạm vi phòng trọ cho thuê; không có vay mua căn hộ.

Đã có React/TypeScript, FastAPI, hai LangGraph, finance engine, B1, auth seed, SQLite/PostgreSQL adapters và adapter GPT/embedding/pgvector tùy chọn. Kho 80 phòng TP.HCM **hoàn toàn tổng hợp**, không phải inventory HubHome. Bản local dùng rule/B1, không gọi API trả phí.

**Bằng chứng lịch sử:** báo cáo 01/10 ghi 121 Python tests (104 backend + 17 eval), 15 UI tests, TypeScript/build và HTTP thật trên SQLite/PostgreSQL; checkpoint/restart, migration và pgvector exact dùng dữ liệu/vector giả lập. Xem [báo cáo backend 0.3.0](docs/kiem-chung-backend.md), [hướng dẫn backend](backend/README.md) và [hướng dẫn frontend](frontend/README.md) cho phạm vi kiểm chứng theo đợt. Live GPT/P quality, restore, Docker/cloud và toàn bộ nghiệm thu v1 chưa có bằng chứng đủ; lần viết lại docs không chạy lại kiểm thử ứng dụng.

## Cài và chạy local

Đã kiểm chứng trong Python sạch 3.14.6 và Node 26.7.0/npm 11.19.0. Chạy từ root repository:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
npm --prefix frontend ci
```

Backend không tự đọc `.env`; `.env.example` chỉ là mẫu. Bản mới với 80 phòng dùng DB riêng:

```bash
export HOMEMATCH_DB_PATH=.local/homematch-mvp.sqlite
export HOMEMATCH_CATALOG_PATH=data/catalog/rooms.json
export HOMEMATCH_AUTH_MODE=seed
export HOMEMATCH_LLM_MODE=demo
export HOMEMATCH_MATCHING_METHOD=B1
export HOMEMATCH_EMBEDDING_MODE=disabled
.venv/bin/python -m backend.manage setup
.venv/bin/python -m backend.manage seed-users
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --log-config backend/logging.json
```

Ở terminal khác:

```bash
npm --prefix frontend run dev
```

Mở [HomeMatch](http://127.0.0.1:5173) và [Swagger](http://127.0.0.1:8000/docs). Vite proxy `/api` tới port 8000. Tài khoản local, không dùng public:

| Username | Password | Vai trò |
|---|---|---|
| `renter-a` | `local-renter-a-password` | Khách demo |
| `renter-b` | `local-renter-b-password` | Khách khác để thử quyền |
| `manager-a` | `local-manager-a-password` | Quản lý phân công phiên mới |
| `manager-b` | `local-manager-b-password` | Quản lý khác để thử quyền |

Kho chung cho managers đọc/toggle; session/recommendation/viewing vẫn kiểm tra phân công. Mật khẩu băm scrypt; bearer token ngẫu nhiên có hạn, lưu hash và thu hồi được. Frontend chỉ lưu token/session ID trong sessionStorage. Token cố định chỉ hoạt động khi chọn `HOMEMATCH_AUTH_MODE=demo` ở localhost.

## Demo hai vai trò

1. Renter-a đăng nhập, bắt đầu phiên; nhập “Tìm phòng TP.HCM Quận 7 cho 1 người, thoáng và yên tĩnh, tầm 3,5 triệu”.
2. Kiểm tra nháp; nhập trần tổng tháng 3.500.000 VND, tiền ban đầu 6.500.000 VND, scenario và tiện ích. Tiền trong chat chỉ là hint, chưa tự xác nhận.
3. **Xác nhận & tìm phòng** → pending, khách không có card phòng.
4. Trong cửa sổ/browser riêng, manager-a mở phiên trong hàng đợi, kiểm tra nguồn/chi phí/đánh đổi, chọn subset và ghi lý do duyệt.
5. Khách **Đọc lại**, so sánh 2–3 phòng đã duyệt và tạo yêu cầu xem tương lai; quản lý xác nhận/từ chối lịch.
6. Đổi kho hoặc xác nhận hồ sơ mới → kết quả cũ hết hiệu lực, compare/viewing cũ bị chặn.

Khoản chưa biết là `null`; subtotal không thành tổng đầy đủ. Tiền ban đầu = cọc + thuê trả trước + phí một lần + chuyển nhà + sắm sửa, không cộng lại tháng đầu. Khoảng cách là đường thẳng có xét sai số; điểm mặc định ở UI là fixture cần chủ động xác nhận. Từ điển tiện ích 9 mã (kể cả máy giặt/ban công/nội thất/thú cưng); Candidate mang cờ `verification` cho dữ liệu chưa rõ; khi không có phòng hợp lệ, hệ thống gợi ý bước nới lỏng mềm do người thuê tự xác nhận — không tự nới điều kiện cứng.

## Kiểm tra và đánh giá

```bash
.venv/bin/python -m pytest
.venv/bin/python -m infra.smoke_api --in-process
.venv/bin/python -m backend.demo
npm --prefix frontend test
npm --prefix frontend run build
.venv/bin/python -m eval validate
.venv/bin/python -m eval oracle
.venv/bin/python -m eval ranking --split dev
.venv/bin/python -m eval metrics
.venv/bin/python -m eval invariants --split dev
.venv/bin/python -m eval grounding
.venv/bin/python -m eval measure
.venv/bin/python -m eval report
```

Hoặc `bash infra/check-local.sh`. Khi API đã chạy, `python -m infra.smoke_api` kiểm tra HTTP thật; script tạo phiên thử và tăng revision khi toggle, chỉ dùng kho tổng hợp. In-process không thay thế browser/PG E2E.

[Eval guide](eval/README.md) mô tả freeze, blind annotation và paired metrics; [REPRODUCE.md](eval/REPRODUCE.md) ghi thứ tự tái lập. Mở [gói gán nhãn dev](eval/runs/development/annotation.html) để chấm; nhãn đang trống. B1 dev chạy được, P thiếu vector thật nên unavailable. `invariants`/`grounding`/`measure`/`report` là suite chức năng máy kiểm được (điều kiện cứng, claim-evidence, latency/calls, evidence index). Chưa có nDCG nghiên cứu, điểm hài lòng hoặc test GPT thật. CLI giữ guard G4 lịch sử; protocol mới phải chốt readiness P5/freeze trước test research, tách khỏi P4 release sản phẩm.

## PostgreSQL và provider tùy chọn

Có PostgreSQL/pgvector thì `bash infra/local-pg.sh start` tạo cluster `.local/` tại 127.0.0.1:55432, dev/test DB; trust auth chỉ cho local. Sau đó:

```bash
export HOMEMATCH_DATABASE_URL=postgresql://homematch@127.0.0.1:55432/homematch_dev
.venv/bin/python -m backend.manage setup
.venv/bin/python -m backend.manage seed-users
HOMEMATCH_TEST_DATABASE_URL=postgresql://homematch@127.0.0.1:55432/homematch_test .venv/bin/python -m pytest backend/tests/test_postgres.py
```

Initial JSON chỉ nạp khi kho trống. `python -m backend.manage import --catalog data/catalog/rooms.json` merge có revision, không xóa ID vắng mặt. Dùng DB mới cho benchmark để không trộn kho demo cũ.

GPT extraction bật bằng `HOMEMATCH_LLM_MODE=openai`; P cần PG, `HOMEMATCH_EMBEDDING_MODE=openai`, key server và index thật qua `python -m backend.manage index --allow-live`, rồi `HOMEMATCH_MATCHING_METHOD=P`. Live có thể phát sinh phí và chưa chạy. App fallback B1 ghi rõ algorithm khi semantic unavailable; eval không xem fallback là P.

Đọc [env](infra/env-inventory.md), [runbook](infra/RUNBOOK.md), [backup/restore](infra/backup-restore.md), [Railway draft](infra/deploy-railway.md). Public yêu cầu PG, seed auth và bốn mật khẩu mạnh khớp DB; đổi env không tự xoay hash cũ. Giữ một API worker/instance.

## Cấu trúc và tài liệu

```text
frontend/   React/TypeScript, UI tests, styles, package lock
backend/    FastAPI, schemas, auth, costs, catalog, graph, adapters, CLI, tests
data/       generator, 80 rooms, pilot, gold/splits, 15 oracle, manifests
eval/       validation, metrics, runner, protocol, tests, dev artifacts
infra/      local DB/check/smoke/backup scripts, env, container/cloud drafts
docs/       plans, surveys, architecture, contract, thesis design and evidence
```

- [Trạng thái](docs/trang-thai-trien-khai.md), [kiến trúc thực tế](docs/kien-truc-trien-khai.md), [API contract](docs/api-contract.md).
- [Đặc tả v1](docs/dac-ta-san-pham.md), [30 yêu cầu](docs/yeu-cau-san-pham.md), [quy trình](docs/quy-trinh-nghiep-vu.md), [nghiệm thu](docs/tieu-chi-nghiem-thu.md).
- [Plan chi tiết](docs/ke-hoach-chi-tiet.md), [kế hoạch từng phần](docs/ke-hoach-tung-phan.md), [W-01–W-18](docs/ke-hoach-trien-khai.md), [API v1 đích](docs/api-san-pham-v1.md).
- [Kiến trúc thiết kế](docs/kien-truc-homematch.md), [agent](docs/thiet-ke-agent.md), [đề cương](docs/ke-hoach-kltn-homematch.md).
- [Rà soát docs](docs/ra-soat-tai-lieu.md), [khảo sát HubHome](docs/khao-sat-hubhome-da-dang-nhap.md), [từ điển](CONTEXT.md).

Scope v1 bắt buộc thêm signup/reset/profile/consent, owner inventory/media/moderation, public/map, favorites/history, vòng đời lịch/hỗ trợ/thông báo, hợp đồng/tenancy, công tơ/hóa đơn/receipt/reconciliation, sửa chữa và admin/ops/privacy. Gateway tự động, legal e-sign, video-call platform, AI ảnh/giọng và toàn quốc là mở rộng. Giữ một API worker tới khi audit concurrency/checkpoint; research/report/slide/video cần evidence riêng.

Manifest và báo cáo 01/10 giữ vai trò snapshot lịch sử, không đại diện cho docs mới. [Trạng thái sản phẩm](docs/trang-thai-trien-khai.md) phân biệt nền tảng hiện có với P0–P4/P5 chưa đạt.
