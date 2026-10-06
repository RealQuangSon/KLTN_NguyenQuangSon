# Runbook HomeMatch local

Runbook này mô tả bản local (schema v9: luồng khách–chủ nhà và 5 phân hệ). Việc hạ tầng tiếp theo (Docker, Railway, GPT-4o/pgvector live) ở [PLAN](PLAN.md). Runbook local chưa phải hướng dẫn vận hành bản deploy.

Đường chạy mặc định là SQLite/rule/B1. Đọc README để cài, seed và mở hai workspace. Backend không tự nạp `.env`; kiểm tra biến process mà không in secret.

## Lệnh vận hành

```bash
.venv/bin/python -m backend.manage setup
.venv/bin/python -m backend.manage migrate
.venv/bin/python -m backend.manage seed-users
.venv/bin/python -m backend.manage import --catalog data/catalog/rooms.json
bash infra/check-local.sh
.venv/bin/python -m infra.smoke_api --in-process
```

Setup/startup chạy migration có phiên bản và tạo checkpointer nếu chưa có, không reset dữ liệu. `migrate` chỉ cập nhật ledger, không nạp kho/provider. Schema hiện tại là 2; DB MVP cũ được tiếp nhận và backfill lịch sử hồ sơ. Seed không tự đổi mật khẩu đã tồn tại. Import validate/merge theo revision, conflict rollback cả lô; không xóa ID vắng mặt. Initial file chỉ dùng lúc kho trống.

## Lỗi thường gặp

| Hiện tượng | Xử lý |
|---|---|
| FE không kết nối/login | API phải chạy port 8000, FE port 5173; xem proxy/CORS/health. Không thay response bằng dữ liệu giả |
| DB URL không kết nối | Kiểm tra PG chạy/port/extension; sai URL không tự fallback SQLite. Muốn offline thì chủ động bỏ DATABASE_URL và đặt DB_PATH |
| Catalog không phải 220 căn v2 | DB đã có seed cũ; initial file không ghi đè. Tái tạo ở DB mới hoặc import có chủ đích; import cũ có thể tạo kho trộn |
| 401/403 | Login lại hoặc dùng actor đúng bản ghi; chủ nhà chỉ thấy phòng, lịch, hợp đồng của mình; khách chỉ thấy dữ liệu của mình |
| 409 draft/catalog | Đọc lại phiên/kho, sửa từ revision mới; không auto-resend confirm/toggle |
| AI timeout/context limit | Dùng form nhu cầu rồi confirm; finance/auth/HITL vẫn chạy bằng code. Không gửi lại chat tự động |
| P thiếu vector/provider | App fallback B1 gắn nhãn; eval P ghi unavailable. Không tạo vector giả để điền metric |
| Run generation lỗi | Admin xem `/admin/failed-runs` rồi gọi `/landlord/recommendations/{run}/retry`; run mới cần duyệt mới |
| Quyết định đã ghi, chưa finalize | Run `reviewed` hoặc lỗi `review_resume_failed`: chủ nhà của run hoặc admin retry hoặc replay đúng review payload/key; quyết định đã commit và graph chỉ resume bằng event ID trong ledger |
| Checkpoint không còn điểm resume | Không chỉnh raw state để bypass HITL; khách xác nhận lại và duyệt run mới |
| Stale sau đổi hồ sơ/kho | Khách confirm profile hiện tại, tạo và duyệt lại. Không công bố nháp cũ |
| Viewing vẫn requested | Cần chủ nhà của phòng xác nhận/từ chối; yêu cầu ban đầu chưa là hẹn được xác nhận |
| Không thấy thông báo nhắc | Kiểm `HOMEMATCH_JOBS_INTERVAL_SECONDS` (0 là tắt); chạy tay `python -m backend.manage jobs` hoặc Admin Console → Vận hành; xem `hm_job_runs` |
| Không lập được hóa đơn | Thiếu chỉ số đầu/cuối kỳ hoặc đơn giá phí (`invoice_incomplete`), hoặc kỳ đã có hóa đơn (`invoice_exists`) |

## Auth và public mode

Đổi mật khẩu seed: dừng API, đặt đủ bốn biến password mạnh rồi chạy `python -m backend.manage seed-users --rotate-passwords`; thao tác thu hồi token. Sau đó khởi động API và kiểm tra login. Public mode kiểm PG/auth/password khớp stored hash/CORS, không tự biến credential local thành credential public. Container/cloud còn cần build và smoke thực tế.

## Kiểm chứng vận hành

Backend 0.3.0 đã chạy 121 Python tests, PG checkpoint/restart và real HTTP smoke trên SQLite/PostgreSQL; xem [báo cáo backend](../docs/kiem-chung-backend.md). `/ready` kiểm schema/catalog/checkpoint, `/manager/metrics` yêu cầu manager. Chạy API với `--no-access-log --log-config backend/logging.json` để log dùng route mẫu và không ghi URL/query/body. Browser desktop/mobile và backup/restore còn cần kiểm chứng; các kết quả này không tự đóng G4/nghiên cứu live.

PG local trust cluster và FE dev server là tiến trình tạm. PG dừng bằng `bash infra/local-pg.sh stop`; FE dùng Ctrl+C. DB/checkpoint ở `.local` không đưa vào Git hoặc gói công khai.
