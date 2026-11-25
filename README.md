# HomeMatch AI Agent

Khóa luận tốt nghiệp: nền tảng cho thuê phòng trọ, studio và căn hộ tại **TP.HCM và Hà Nội**, có trợ lý AI gợi ý căn theo nhu cầu và năng lực tài chính của người thuê.

## 1. Mô tả sản phẩm

- **Trợ lý AI:** hỏi nhu cầu bằng hội thoại, tính chi phí hằng tháng và tiền vào ở, đánh giá khả năng chi trả (kể cả ước tính vay ngắn hạn), xếp hạng và giải thích 5 căn phù hợp nhất. Kết quả đến người thuê ngay sau khi xếp hạng.
- **Cổng người thuê:** tìm theo bộ lọc, bản đồ, so sánh căn, nhắn tin với chủ nhà, đặt lịch xem trực tiếp hoặc trực tuyến, cẩm nang thuê nhà, hợp đồng, hóa đơn, báo sửa chữa.
- **Cổng chủ nhà:** quản lý tin đăng, lịch xem, hộp thư, hợp đồng, công tơ, hóa đơn, thu tiền, sửa chữa, báo cáo; trợ lý viết bài đăng và gợi ý giá.
- **Quản trị:** xem hội thoại AI đã che thông tin cá nhân, tài khoản, duyệt chủ nhà, kiểm duyệt tin, ticket hỗ trợ, số liệu vận hành.
- **Tự động hóa:** thông báo trong ứng dụng, nhắc lịch xem, nhắc thanh toán, nhắc gia hạn hợp đồng.

Mô hình ngôn ngữ chỉ hiểu câu hỏi, gọi công cụ và diễn giải. Tính tiền, điều kiện bắt buộc, xếp hạng và phân quyền do mã xác định thực hiện.

**Công nghệ:** Python, FastAPI, LangGraph, SQLite hoặc PostgreSQL (pgvector), OpenAI API, React 19, TypeScript, Vite, MapLibre GL.

**Giới hạn:** chạy trên localhost. Không có cổng thanh toán, email/SMS thật, tự đăng mạng xã hội hay chữ ký số có giá trị pháp lý. Dữ liệu đi kèm là dữ liệu tổng hợp: 220 căn (TP.HCM 120, Hà Nội 100).

## 2. Cấu trúc project

```text
backend/   API FastAPI và nghiệp vụ
  app/       service.py (hai graph LangGraph), agent_loop.py và agent_tools.py (agent),
             costs.py (tài chính), catalog.py (lọc và xếp hạng), pms.py, automation.py...
  tests/     test pytest
  manage.py  lệnh cài đặt, nạp dữ liệu, migration
frontend/  giao diện React + TypeScript
  src/pages, src/components, src/tests
data/      kho căn tổng hợp, bộ sinh dữ liệu, hồ sơ mẫu, oracle, manifest
eval/      công cụ đánh giá, quy trình và kết quả
infra/     script chạy, kiểm tra, sao lưu; danh mục biến môi trường
docs/      đặc tả, yêu cầu, thiết kế, API
```

Chỉ mục tài liệu: [docs/README.md](docs/README.md). Thuật ngữ: [CONTEXT.md](CONTEXT.md).

## 3. Cài đặt

Yêu cầu: Python 3.14, Node 26 và npm 11 (các phiên bản đã kiểm chứng).

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
npm --prefix frontend ci
```

## 4. Chạy trên máy local

Chế độ mặc định dùng SQLite và bộ luật, không cần khóa API và không phát sinh phí. Backend không tự đọc `.env`, nên cần export biến môi trường. Kho căn chỉ nạp khi cơ sở dữ liệu còn trống.

Cửa sổ 1, backend:

```bash
export HOMEMATCH_DB_PATH=.local/homematch-v2.sqlite
export HOMEMATCH_CATALOG_PATH=data/catalog/rooms.json
export HOMEMATCH_AUTH_MODE=seed HOMEMATCH_LLM_MODE=demo HOMEMATCH_MATCHING_METHOD=B1 HOMEMATCH_EMBEDDING_MODE=disabled
.venv/bin/python -m backend.manage setup
.venv/bin/python -m backend.manage seed-users
.venv/bin/python -m backend.manage seed-demo    # tùy chọn: hợp đồng, hóa đơn, sự cố mẫu gắn nhãn [DEMO]
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --log-config backend/logging.json
```

Cửa sổ 2, giao diện:

```bash
npm --prefix frontend run dev
```

Mở <http://127.0.0.1:5173>. Tài liệu API tự sinh: <http://127.0.0.1:8000/docs>.

Tài khoản dùng thử, mật khẩu chung `123456`:

| Tên đăng nhập | Vai trò |
|---|---|
| `renter` | Người thuê |
| `owner1` | Chủ nhà Hà Nội |
| `owner2` | Chủ nhà TP.HCM |
| `admin` | Quản trị viên |

Luôn chạy một API worker (`--workers 1`), vì job nền chạy trong cùng tiến trình.

## 5. Triển khai tùy chọn

- **Mô hình ngôn ngữ thật:** đặt `HOMEMATCH_LLM_MODE=openai` và `OPENAI_API_KEY`. Nếu nhà cung cấp chỉ có `/chat/completions`, đặt thêm `HOMEMATCH_LLM_API=chat_completions`. Có phát sinh phí.
- **PostgreSQL:** chạy `bash infra/local-pg.sh start`, rồi đặt `HOMEMATCH_DATABASE_URL=postgresql://homematch@127.0.0.1:55432/homematch_dev`.
- **Xếp hạng ngữ nghĩa (pgvector):** cần PostgreSQL, `HOMEMATCH_EMBEDDING_MODE=openai`, `HOMEMATCH_MATCHING_METHOD=P` và lệnh `python -m backend.manage index --allow-live`. Có phát sinh phí.
- **Bản đồ Goong:** đặt `VITE_GOONG_API_KEY` trong `frontend/.env.local`. Không có thì dùng OpenStreetMap.

Danh sách đầy đủ biến môi trường: [infra/env-inventory.md](infra/env-inventory.md). Vận hành và xử lý lỗi: [infra/RUNBOOK.md](infra/RUNBOOK.md).

## 6. Dùng thử

1. Đăng nhập `renter`, vào **Trợ lý AI** và nhắn: "Tìm căn hộ 1 phòng ngủ ở Cầu Giấy, Hà Nội cho 2 người, view thoáng".
2. Xác nhận nhu cầu và ngân sách. Kết quả hiện ngay; có thể so sánh, mô phỏng vay, nhắn chủ nhà, đặt lịch xem.
3. Mở **Tìm kiếm** để lọc và xem bản đồ.
4. Đăng nhập `owner1` hoặc `owner2` để xác nhận lịch, lập hợp đồng và hóa đơn.
5. Đăng nhập `admin` để xem hội thoại đã che, tài khoản, tin đăng và số liệu.

Các bước chi tiết: [docs/kich-ban-demo.md](docs/kich-ban-demo.md).

## 7. Kiểm thử và đánh giá

```bash
.venv/bin/python -m pytest
npm --prefix frontend test
npm --prefix frontend run build
.venv/bin/python -m infra.smoke_api --in-process
bash infra/check-local.sh        # toàn bộ kiểm tra offline
```

Test mặc định chạy offline. Test PostgreSQL chỉ chạy khi đặt `HOMEMATCH_TEST_DATABASE_URL`. Cách đánh giá: [eval/README.md](eval/README.md) và [eval/REPRODUCE.md](eval/REPRODUCE.md).
