# HomeMatch AI Agent — trợ lý gợi ý căn thuê theo nhu cầu và năng lực tài chính

Khóa luận tốt nghiệp: nền tảng cho thuê phòng trọ, studio, căn hộ tại **TP.HCM và Hà Nội**, với trợ lý AI ở trung tâm.

- **Trợ lý AI:** hỏi nhu cầu, kiểm khả năng chi trả (kể cả ước tính vay ngắn hạn), xếp hạng top căn kèm lý giải. **Mỗi chủ nhà duyệt phòng của mình** trước khi khách thấy.
- **Nền tảng 5 phân hệ:**
  - cổng người thuê;
  - tự động hóa;
  - Admin Console;
  - cổng chủ nhà (PMS & CRM);
  - trợ lý AI cho chủ nhà.
- **Công nghệ:** GPT-4o, embedding + pgvector, LangGraph, FastAPI, React/TypeScript, Leaflet/OSM, Railway.
- **Phạm vi:** cho thuê, không mua bán. Đây là điều chỉnh có chủ đích so với đề bài gốc; xem D-01→D-08 trong [đề cương](docs/ke-hoach-kltn-homematch.md).

## Trạng thái

Ngày 05/10/2026, code có đủ trợ lý AI và 5 phân hệ (schema v9). Kết quả kiểm tra:
- `bash infra/check-local.sh` pass: 196 test Python, 41 test UI, oracle 22/22, 0 vi phạm điều kiện cứng, 142/142 khẳng định có bằng chứng;
- smoke qua HTTP thật trên server uvicorn pass.

| Còn thiếu | Ghi chú |
|---|---|
| Deploy Railway, chạy GPT-4o/pgvector thật | Cần tài khoản và API key |
| Demo trên trình duyệt, test PostgreSQL schema v9 | |
| Ảnh tin và ảnh sự cố, ưu đãi chăm sóc khách, tự đăng mạng xã hội | Đang ở mức một phần |
| Nhãn người chấm, khảo sát người dùng | GĐ5 |

Chi tiết ở [trạng thái](docs/trang-thai-trien-khai.md). Dữ liệu là **hoàn toàn tổng hợp**: 220 căn, 4 chủ nhà.

## Cài và chạy local

Đã kiểm chứng với Python 3.14, Node 26/npm 11.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
npm --prefix frontend ci
```

Backend **không** tự đọc `.env`, nên export biến môi trường. Kho chỉ được nạp từ JSON khi DB trống, nên hãy dùng DB mới:

```bash
export HOMEMATCH_DB_PATH=.local/homematch-v2.sqlite
export HOMEMATCH_CATALOG_PATH=data/catalog/rooms.json
export HOMEMATCH_AUTH_MODE=seed HOMEMATCH_LLM_MODE=demo HOMEMATCH_MATCHING_METHOD=B1 HOMEMATCH_EMBEDDING_MODE=disabled
.venv/bin/python -m backend.manage setup
.venv/bin/python -m backend.manage seed-users
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --log-config backend/logging.json
npm --prefix frontend run dev      # terminal khác → http://127.0.0.1:5173
```

Job tự động hóa chạy 5 phút một lần trong API (`HOMEMATCH_JOBS_INTERVAL_SECONDS`, đặt 0 để tắt). Có thể chạy tay: `.venv/bin/python -m backend.manage jobs`.

Tài khoản local (mật khẩu `local-<username>-password`, không dùng khi public):

| Username | Vai trò |
|---|---|
| `renter-a`, `renter-b` | Người thuê |
| `owner-a`, `owner-b` | Chủ nhà TP.HCM |
| `owner-c`, `owner-d` | Chủ nhà Hà Nội (owner-c: Cầu Giấy, Đống Đa, Hai Bà Trưng) |
| `admin-a` | Quản trị viên |
| `manager-a`, `manager-b` | Vai trò cũ, không còn quyền nghiệp vụ |

## Demo

1. **Khách** `renter-a` chat: "Tìm căn hộ 1 phòng ngủ ở Cầu Giấy, Hà Nội cho 2 người, view thoáng".
   - Trên form, nhập trần tổng tháng 16.000.000 VND, tiền mặt 15.000.000 VND, thu nhập 30.000.000 VND, bật vay 12%/năm trong 12 tháng.
   - Bấm **Xác nhận & tìm phòng**.
2. **Chủ nhà** `owner-c` mở **Duyệt gợi ý**. Màn này chỉ có phòng của owner-c và chỉ hiện băng tài chính. Duyệt (đổi thứ tự thì phải ghi lý do).
3. **Khách** thấy phòng đã duyệt ngay cả khi chủ khác chưa duyệt. Khách có thể:
   - so sánh có tư vấn và mô phỏng vay;
   - **Chat với chủ nhà** (ngữ cảnh được chuyển kèm);
   - đặt lịch xem trực tuyến (có link phòng họp).
4. **Tìm theo bộ lọc**: lọc, chuyển sang **Bản đồ**, xem nhanh, hỏi cẩm nang ("gửi xe thế nào?"), đặt lịch ngay từ tin.
5. **Chủ nhà** xác nhận lịch, rồi đi tiếp:
   - **Hợp đồng**: soạn → gửi → khách chấp thuận → kích hoạt (phòng chuyển sang đã thuê);
   - **Hóa đơn**: chốt số → lập hóa đơn; khách báo đã chuyển → chủ xác nhận → biên lai;
   - **Sửa chữa**, **Khách tiềm năng**, **Tổng quan**;
   - **Trợ lý AI**: viết bài đăng, chia sẻ, hỏi "Vì sao phòng trống lâu?".
6. **Admin** `admin-a`:
   - **Hội thoại AI**: đã che SĐT và email, mỗi lần mở được audit;
   - **Chuyển giao**: tỷ lệ phản hồi của chủ nhà;
   - **Vận hành**: chạy job.

## Kiểm tra và đánh giá

```bash
bash infra/check-local.sh                 # toàn bộ kiểm tra offline
.venv/bin/python -m pytest backend/tests/test_pms.py   # một file
npm --prefix frontend test
.venv/bin/python -m eval validate         # oracle | extraction --split dev | ranking --split dev | invariants --split dev | grounding | measure | report
```

## PostgreSQL, GPT-4o và pgvector

- `bash infra/local-pg.sh start`; đặt `HOMEMATCH_DATABASE_URL=postgresql://homematch@127.0.0.1:55432/homematch_dev`.
- Test PostgreSQL: đặt `HOMEMATCH_TEST_DATABASE_URL`.
- GPT: `HOMEMATCH_LLM_MODE=openai` cùng `OPENAI_API_KEY`.
- P: PostgreSQL + `HOMEMATCH_EMBEDDING_MODE=openai` + `python -m backend.manage index --allow-live` + `HOMEMATCH_MATCHING_METHOD=P`.

Chế độ live phát sinh phí và chưa được chạy. Biến môi trường ở [env-inventory](infra/env-inventory.md). Luôn giữ một API worker.

## Cấu trúc

```text
backend/   FastAPI; LangGraph (service.py); costs/catalog/locations; agents, memory; listings, advisor, handbook;
           conversations, notifications, automation; pms, copilot; tests
frontend/  React/TypeScript: trợ lý, tìm kiếm + bản đồ, tin nhắn, cẩm nang, cổng chủ nhà (PMS/CRM, trợ lý), Admin Console
data/      generator v2, kho tổng hợp, hồ sơ gold, oracle, manifest
eval/      CLI đánh giá, protocol, kết quả development
infra/     script local, Docker/Railway (chưa deploy), runbook
docs/      đề cương, đặc tả, yêu cầu, thiết kế, kế hoạch, bằng chứng
```

Bắt đầu đọc từ [docs/README.md](docs/README.md). Thuật ngữ ở [CONTEXT.md](CONTEXT.md).
