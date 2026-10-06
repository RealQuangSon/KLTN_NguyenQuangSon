# Chuẩn bị deploy Railway

**Trạng thái: local-only.** Chưa tạo tài nguyên, chưa phát sinh phí cloud, chưa build Docker hoặc kiểm chứng deployment. Máy triển khai hiện không có Docker. `compose.yaml` và Dockerfile là cấu hình chuẩn bị, cần chạy lại trước khi dùng.

## Cấu hình đã chuẩn bị

- `Dockerfile.api`: Python 3.14, cài từ `requirements.lock`, một uvicorn worker, đọc `PORT`.
- `railway.toml`: cấu hình riêng cho API; đặt config path `/infra/railway.toml`, build context ở root repository.
- `Dockerfile.frontend` và `nginx.conf`: phục vụ SPA và proxy `/api` trong Compose local. Host `api` trong Nginx thuộc Compose; phải thay bằng hostname dịch vụ thật hoặc API base URL khi dùng cloud.
- `compose.yaml`: PostgreSQL/pgvector, API và frontend, cổng host chỉ bind loopback. Credential mẫu chỉ dùng local.

Railway hỗ trợ [config as code](https://docs.railway.com/config-as-code/reference), [Dockerfile](https://docs.railway.com/builds/dockerfiles) và [healthcheck](https://docs.railway.com/deployments/healthchecks). Start command phải lắng nghe `PORT`; Docker CMD hiện thực hiện bước đó. Image pgvector tham khảo [kho chính thức](https://github.com/pgvector/pgvector) và [tag 0.8.6-pg17-trixie](https://hub.docker.com/r/pgvector/pgvector/tags). Nguồn được kiểm tra ngày 2026-10-01; cấu hình còn cần thử tại lúc deploy.

## Công việc trước khi mở public

1. Kiểm chứng local, Docker build và luồng hai vai trò; tạo Git release phù hợp.
2. Chốt tài khoản/project Railway, phạm vi tài nguyên và ngân sách với người dùng.
3. Dựng PostgreSQL có extension `vector`; migration/seed/import bằng lệnh backend, giữ volume bền vững và backup riêng.
4. Cấu hình API bằng server secret: DB URL, bốn mật khẩu seed mạnh riêng, auth `seed`, `HOMEMATCH_PUBLIC=true`, CORS chính xác. Không dùng mật khẩu hoặc token demo.
5. Frontend chỉ nhận URL công khai của API hoặc proxy; không đưa DB/model key vào build.
6. Kiểm tra `/health`, login, quyền âm, pending không lộ phòng, approve/compare/viewing, stale và restart. Đảm bảo một instance/worker theo scope hiện tại.
7. Khi có API key và ngân sách model, chủ động chọn mode live. Không cần gọi model trả phí để kiểm chứng B1/offline.

Chỉ ghi cloud hoàn thành sau khi có URL, log build/smoke/restart thật. Health thành công không thay thế nghiệm thu nghiệp vụ.
