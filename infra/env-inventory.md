# Biến môi trường

Backend đọc biến process, không tự nạp `.env`. Frontend Vite đọc `.env.local` theo cơ chế riêng; file đó không đưa vào Git. Giá trị root `.env.example` là mẫu, không phải secret thực tế.

| Biến | Mặc định/hành vi | Nơi đọc |
|---|---|---|
| `HOMEMATCH_DATABASE_URL` | Nếu có phải là PostgreSQL URL; không fallback khi kết nối lỗi | API/manage/service |
| `HOMEMATCH_DB_PATH` | `.local/homematch.sqlite` khi không dùng PG (README dùng `.local/homematch-v2.sqlite` cho kho v2) | API/manage |
| `HOMEMATCH_CATALOG_PATH` | JSON initial catalog; chỉ nạp khi kho lưu trữ trống. Nếu bỏ trống dùng 12 phòng demo | Service |
| `HOMEMATCH_AUTH_MODE` | `seed`; `demo` dùng token cố định ở localhost | API |
| `HOMEMATCH_PUBLIC` | `false`; chỉ nhận `true/false` | API |
| `HOMEMATCH_TOKEN_TTL_SECONDS` | 3600, khoảng hợp lệ 60–86400 | API |
| `HOMEMATCH_PASSWORD_<USERNAME>` (vd. `RENTER_A`, `OWNER_A`…`OWNER_D`, `ADMIN_A`) | Mật khẩu seed; giá trị local mặc định ghi ở README, public yêu cầu ≥16 ký tự khác mặc định và khớp DB | SeedAuth |
| `HOMEMATCH_CORS_ORIGINS` | Hai origin localhost:5173, phân cách dấu phẩy; public cấm wildcard | API |
| `HOMEMATCH_LLM_MODE` | `demo/openai`; default `demo`, không gọi provider | Interpreter |
| `HOMEMATCH_SESSION_LLM_BUDGET` | 50 lượt gọi interpreter tối đa mỗi phiên (đếm cả lần lỗi); vượt → lỗi `budget_exceeded` 429 | Service (agent budget) |
| `OPENAI_API_KEY` | Secret server, chỉ cần khi chủ động chọn live | SDK adapters |
| `OPENAI_BASE_URL` | Không đặt → endpoint OpenAI chính thức; đặt `https://openrouter.ai/api/v1` để gọi qua OpenRouter | SDK adapters |
| `OPENAI_MODEL` | `gpt-4o-2024-08-06`; khi qua OpenRouter dùng id đầy đủ của gateway, vd. `openai/gpt-6-luna` | Extraction adapter |
| `HOMEMATCH_LLM_API` | `responses` (mặc định, API Responses của OpenAI) hoặc `chat_completions` cho gateway chỉ có `/chat/completions` như OpenRouter; giá trị khác làm service không khởi động được | Interpreter |
| `HOMEMATCH_CONTEXT_TOKEN_CAP` | 4000; giới hạn ước lượng đầu vào, không phải tokenizer chính xác | Extraction adapter |
| `HOMEMATCH_MATCHING_METHOD` | `B1/P`; default B1 | Service |
| `HOMEMATCH_EMBEDDING_MODE` | `disabled/openai`; live cần PG/key/index | Service |
| `HOMEMATCH_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding adapter |
| `HOMEMATCH_EMBEDDING_DIMENSIONS` | 1536 | Embedding adapter |
| `HOMEMATCH_SEMANTIC_ALPHA` | 0.3, khoảng 0–1 | Service |
| `HOMEMATCH_JOBS_INTERVAL_SECONDS` | 300; chu kỳ job nền trong API (nhắc lịch, thanh toán, gia hạn, chăm sóc khách, dọn chat); 0 tắt | API |
| `HOMEMATCH_REENGAGE_AFTER_HOURS` | 24; khách xem tin quá số giờ này mà chưa đặt lịch thì được gợi ý căn tương đương | Automation |
| `HOMEMATCH_CHAT_RETENTION_DAYS` | 90; số ngày giữ chat AI đã che PII | Service |
| `HOMEMATCH_MEDIA_DIR` | `.local/media`; thư mục chứa file ảnh tin và ảnh sự cố trên đĩa local; metadata ảnh nằm trong bảng `hm_media` | Service/media |
| `HOMEMATCH_PROVIDER_PRICES_PATH` | Không đặt → `/admin/metrics` trả `cost: null`. Đường dẫn file JSON bảng giá provider (mẫu `infra/provider-prices.example.json`, không chứa giá thật; người dùng tự điền giá và `effective_date` từ trang giá chính thức). File lỗi/không đọc được được coi như chưa cấu hình | API (`/admin/metrics`, BE-05) |
| `HOMEMATCH_PUBLIC_BASE_URL` | `http://127.0.0.1:5173`; gốc URL cho trang tin `/tin/{id}` trong bài đăng | Service |
| `LANGGRAPH_STRICT_MSGPACK` | `true` | Checkpoint serialization |
| `HOMEMATCH_TEST_DATABASE_URL` | Không đặt thì skip integration PG; tests dùng schema riêng rồi dọn | pytest |
| `HOMEMATCH_PG_BIN`, `HOMEMATCH_PG_PORT` | `pg_config --bindir`, 55432 | Infra local scripts |
| `HOMEMATCH_PYTHON` | `.venv/bin/python` | `check-local.sh` |
| `HOMEMATCH_LIVE_BUDGET_VND` | Bắt buộc > 0 khi chạy `infra/live_run.sh`; chỉ kê khai, không phải trần chi (AG-04) | `infra/live_run.sh` |
| `VITE_API_BASE_URL` | `/api`; proxy dev tới API localhost:8000 | Frontend, công khai |

Không đưa model key, DB URL, mật khẩu hoặc raw checkpoint vào frontend/artifact công khai. Opaque token không cần signing key. Thay env password không tự ghi đè hash cũ: dùng `python -m backend.manage seed-users --rotate-passwords`; thao tác này thu hồi token của bốn tài khoản seed.
