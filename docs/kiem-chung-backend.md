# Kiểm chứng backend HomeMatch 0.3.0

Backend được hoàn thiện trên mã MVP hiện có theo phạm vi BE-01–BE-12. Chạy một API process, dữ liệu tổng hợp, rule/B1 và provider fixtures. Các đầu vào nghiên cứu trong `data/` không bị sửa trong lượt triển khai này.

## Thay đổi đã triển khai

- Schema phản hồi cho toàn bộ API, bao gồm pending/published, login, catalog, review, compare/viewing, health/readiness và metrics; OpenAPI cập nhật lên 0.3.0.
- Envelope lỗi thống nhất cho auth, validation, 404/405 và lỗi bất ngờ; request ID có cả header/body, không trả raw input hoặc exception.
- Migration ledger có phiên bản 1/2, tự chạy khi startup; CLI `migrate`; nâng cấp DB MVP cũ và backfill lịch sử hồ sơ. Hồ sơ đã xác nhận có khóa `(session_id, profile_version)` và được lưu cùng transaction confirm.
- Transaction lồng nhau có savepoint trên SQLite/PostgreSQL. Confirm/run commit trước generation; review event commit trước graph resume. Resume lỗi giữ event và trả `review_resume_failed`, có thể phục hồi sau restart.
- Generation lỗi sau khi nháp đã được lưu chuyển thành `generation_failed`, xóa item hiển thị và hỗ trợ retry bằng run mới. Thiếu checkpoint không công bố theo event đơn lẻ.
- Ranking lưu config/version, profile/query/catalog hash và nhãn fallback. pgvector kiểm đủ coverage/text/model/dimension và từ chối khoảng cách không hữu hạn; adapter từ chối vector toàn 0.
- `/ready`, `/manager/metrics`, log dùng mẫu route và cấu hình bỏ access log thô. Usage lỗi provider được đếm; lượt thiếu token usage được ghi riêng.
- Login kiểm lại password hash trước cấp token để việc xoay mật khẩu trong lúc scrypt chạy không tạo token mới bằng mật khẩu cũ.

## Kết quả thực chạy

| Kiểm tra | Kết quả | Phạm vi |
|---|---|---|
| Python với PostgreSQL test DSN | **121 passed** | 104 backend + 17 eval; không skipped |
| Regression storage | **Đạt SQLite và PostgreSQL** | Schema/API, quyền, cost/filter, CAS, stale, subset/order, replay, viewing/support |
| Durability | **Đạt hai storage** | Observer connection thấy confirm/event đã commit trước graph, restart/retry giữ event, snapshot history, savepoint rollback, nâng cấp legacy idempotent |
| PG checkpoint/writer | **Đạt** | Khởi động lại, token còn hiệu lực, finalize chặn catalog đã đổi |
| pgvector exact | **Đạt với vector giả lập** | B1/P cùng eligible set/cost; blending; index lần hai 0 lượt; đổi giá không re-embed; đổi text cần re-index; vector thiếu/zero được xử lý |
| HTTP thật với SQLite | **7 nhóm smoke đạt** | Seed login, ownership/draft CAS, pending/assignment, approve/replay/compare, viewing, catalog stale, token revoke |
| HTTP thật với PostgreSQL | **7 nhóm smoke đạt** | Cùng luồng trên DB thử riêng và kho 80 phòng tổng hợp |
| CLI migrate/setup/seed | **Đạt SQLite** | Schema version 2, 80 phòng, seed accounts |
| Frontend | **15 tests + TypeScript/Vite build đạt** | Không sửa UI; kiểm tra tương thích hợp đồng hiện có |
| Dataset validation/demo | **Đạt** | 80 canonical rooms, 30 profiles, 38 utterances; offline demo qua review/compare/viewing |

Lệnh Python cuối:

```bash
HOMEMATCH_TEST_DATABASE_URL=postgresql://homematch@127.0.0.1:55433/homematch_backend_test .venv/bin/python -m pytest --tb=short --junitxml=.local/backend-test-report.xml
```

PostgreSQL 17.11/pgvector 0.8.6 chạy ở cluster thử riêng `.local/backend-verification-pg/`, không dùng cluster cũ của dự án. Tests tạo/drop schema riêng; các service được đóng trước teardown. HTTP smoke dùng port 8765/8766 và database tổng hợp riêng. Báo cáo JUnit và JSON smoke PostgreSQL ở `.local/`, không đưa DB/checkpoint/token vào source/artifact công khai.

Bộ kiểm tra cuối cũng bao gồm các thay đổi đang có trong workspace về provenance nhu cầu nháp và các ca Eval bổ sung; OpenAPI được đồng bộ lại sau các thay đổi đó.

## Giới hạn của bằng chứng

Vector fixtures chỉ chứng minh SQL exact, coverage, caching và công thức; chưa chứng minh chất lượng embedding/GPT thật. Chưa có browser FE↔BE, backup/restore, Docker/cloud hoặc kiểm chứng nhiều worker. Nhãn relevance/hài lòng vẫn cần người đánh giá độc lập. API giữ một process và manual retry; không có worker tự phục hồi.

Hướng dẫn sử dụng ở [Backend README](../backend/README.md), hợp đồng ở [API](api-contract.md), trạng thái/lỗi ở [dictionary](status-dictionary.md). Bản kiểm chứng MVP trước đó được giữ làm bằng chứng lịch sử trong [báo cáo MVP](kiem-chung-mvp.md).
