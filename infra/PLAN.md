# Kế hoạch hạ tầng

**Cập nhật:** 05/10/2026. Phục vụ NFR-05, NFR-06, NFR-09 và task T4.3/T4.4 trong [kế hoạch triển khai](../docs/ke-hoach-trien-khai.md). Tài liệu liên quan: [env-inventory](env-inventory.md), [RUNBOOK](RUNBOOK.md), [deploy-railway](deploy-railway.md), [backup-restore](backup-restore.md).

## 1. Hiện có

- `check-local.sh`: toàn bộ kiểm tra offline, pass ngày 05/10/2026.
- `smoke_api.py`: kiểm tra luồng qua HTTP (in-process hoặc server thật).
- `local-pg.sh`: PostgreSQL local; script backup và restore.
- `Dockerfile.api`, `Dockerfile.frontend`, `compose.yaml`, `railway.toml`: **mới là bản nháp**, chưa build, chưa deploy.

## 2. Việc

| Task | Việc | Bằng chứng xong |
|---|---|---|
| T4.3a | Build Docker API và frontend; chạy `compose.yaml` local với pgvector | Log build, `/ready` = `ready`, smoke HTTP pass |
| T4.3b | Railway: project, PostgreSQL có `vector`, API một worker, frontend; biến môi trường public mode, mật khẩu seed mạnh, CORS chính xác | URL thật, log deploy, smoke HTTP, khởi động lại vẫn giữ dữ liệu |
| T4.4a | `backend.manage index --allow-live` trên Railway PG | Số vector bằng số căn; `HOMEMATCH_MATCHING_METHOD=P` chạy không fallback |
| T4.4b | GPT-4o live với ngân sách được người dùng chốt; giới hạn chi tiêu ở tài khoản provider | `eval measure`: p50/p95, lượt gọi, token, VND mỗi phiên |
| — | Backup PostgreSQL trước demo và trước khi chạy đánh giá | File backup và một lần restore thử |

## 3. Nguyên tắc

- Một API worker cho tới khi kiểm chứng concurrency của checkpoint.
- Secret chỉ để trong biến môi trường server, không đưa vào `VITE_*` hay repo.
- Không tạo tài nguyên cloud hay phát sinh phí khi người dùng chưa đồng ý về tài khoản và ngân sách.
- Chỉ ghi "đã deploy" khi có URL và log thật.
