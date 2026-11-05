# Kế hoạch hạ tầng

**Cập nhật:** 05/10/2026. Phục vụ NFR-05, NFR-06, NFR-09 và task T4.3/T4.4 trong [kế hoạch triển khai](../docs/ke-hoach-trien-khai.md). Tài liệu liên quan: [env-inventory](env-inventory.md), [RUNBOOK](RUNBOOK.md), [backup-restore](backup-restore.md).

## 1. Hiện có

- `check-local.sh`: toàn bộ kiểm tra offline, pass ngày 05/10/2026.
- `smoke_api.py`: kiểm tra luồng qua HTTP (in-process hoặc server thật).
- `local-pg.sh`: PostgreSQL local; script backup và restore.
- Cấu hình Docker/Railway (`Dockerfile.api`, `Dockerfile.frontend`, `compose.yaml`, `railway.toml`, `nginx.conf`, `deploy-railway.md`): bản nháp, chưa build, chưa deploy; đã **xóa khỏi repo ngày 28/10/2026** (D-09): đồ án chỉ chạy localhost.

## 2. Việc

| Task | Việc | Bằng chứng xong |
|---|---|---|
| T4.3a | ~~Build Docker~~ (ngoài phạm vi, D-09) | — |
| T4.3b | ~~Deploy Railway~~ (ngoài phạm vi, D-09) | — |
| T4.4a | `backend.manage index --allow-live` trên PostgreSQL + pgvector local (`local-pg.sh`, `live_run.sh`) | Số vector bằng số căn; `HOMEMATCH_MATCHING_METHOD=P` chạy không fallback |
| T4.4b | GPT-4o live với ngân sách được người dùng chốt; giới hạn chi tiêu ở tài khoản provider | `eval measure`: p50/p95, lượt gọi, token, VND mỗi phiên |
| — | Backup PostgreSQL trước demo và trước khi chạy đánh giá | File backup và một lần restore thử |

## 3. Nguyên tắc

- Một API worker cho tới khi kiểm chứng concurrency của checkpoint.
- Secret chỉ để trong biến môi trường server, không đưa vào `VITE_*` hay repo.
- Không tạo tài nguyên cloud hay phát sinh phí khi người dùng chưa đồng ý về tài khoản và ngân sách.
- Chỉ ghi "đã deploy" khi có URL và log thật.
