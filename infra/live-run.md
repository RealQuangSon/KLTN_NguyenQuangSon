# Chạy live GPT-4o + pgvector (AG-04, người dùng tự chạy)

**Trạng thái:** script đã chuẩn bị, **chưa ai chạy** (L8 — không ghi là đã kiểm chứng). Chạy bằng:
`bash infra/live_run.sh` từ root repo. Agent/CI không bao giờ chạy file này.

## 1. Điều kiện trước khi chạy

1. `OPENAI_API_KEY` đã export trong shell (script không bao giờ in giá trị).
2. `HOMEMATCH_LIVE_BUDGET_VND` đã export, số nguyên > 0 — ngân sách bạn chấp nhận chi. Lưu ý:
   ngân sách này **chỉ là kê khai** (`declaration_only_not_an_enforced_spend_limit`), hệ thống
   không tự ngắt khi hết; bạn tự theo dõi usage (mục 3).
3. Máy có PostgreSQL 17 + pgvector qua `pg_config` (`infra/local-pg.sh` tự dựng cluster tại
   `.local/pgdata`, port 55432, không đụng dịch vụ hệ thống).
4. Dữ liệu nghiên cứu đã đóng băng: `python -m eval validate` đạt và manifest dev
   (`data/manifests/development_manifest.json`) ở trạng thái frozen; đổi dữ liệu trước khi chạy
   sẽ làm kết quả không so được với các lần trước.
5. Chạy khi không có API worker nào khác dùng cùng `.local` (một worker — L7).
6. Không đặt `OPENAI_MODEL` khác `gpt-4o-2024-08-06` nếu protocol đã khóa model này
   (script sẽ lỗi `Extraction model differs from frozen protocol` khi có trở ngại).

## 2. Chi phí ước tính

Số lượt gọi (in trong bước kế hoạch của script): **18 lượt GPT-4o** (extraction — 1 lượt/câu gold
dev, `store=False`, tối đa 600 token output) + **tối đa 220 lượt embedding** `text-embedding-3-small`
(chỉ embed lại căn có hash văn bản semantic đổi; lần chạy sau thường rẻ hơn nhiều). Ranking và
measure không gọi model.

**Chi phí tiền: _để trống._** Điền giá từ trang giá chính thức của provider vào file giá của
BE-05 (`infra/provider-prices.example.json`, trỏ qua `HOMEMATCH_PROVIDER_PRICES_PATH`, có ghi
`effective_date` và `vnd_per_usd`) — sau đó `GET /admin/metrics` trả `cost.estimated_cost_vnd`
kèm `basis` và mục `missing` khi thiếu giá. Không ước lượng trong tài liệu này.

## 3. Cách đọc kết quả

Kết quả nằm trong `eval/runs/live-<ngày>/` (không bao giờ đè `eval/runs/development/`):

| File | Ý nghĩa |
|---|---|
| `extraction.json` | GPT-4o trích xuất so với gold dev: `metrics` (độ chính xác ý định, micro-F1 trường), `model_calls`, `mode: "live"`, usage từng câu |
| `rankings.jsonl` + `run_manifest.json` | Xếp hạng B1 (baseline) và P (hybrid pgvector, α = 0.3) trên cùng tập đủ điều kiện; `P` fallback cấu trúc sẽ bị ghi `status: "unavailable"` chứ không giả thành P |
| `oracle.json` | Oracle chi phí tất định (bắt buộc để `measure` chạy trong cùng thư mục) |
| `measurements.json` | Trễ p50/p95 (extraction, B1, P) và số lượt gọi model |

So sánh với baseline offline trong `eval/runs/development/`; số token thật theo model nằm ở
`provider_usage` trong `/admin/metrics` nếu bạn chạy kèm API. Sau khi chạy xong, cập nhật
`docs/trang-thai-trien-khai.md` (ngày, model, số lượt gọi, chi phí, kết quả); đạt yêu cầu thì
đóng FR-11 và NFR-06 — không đóng trước khi có số liệu thật.

## 4. Cách dừng và rủi ro

- Dừng giữa chừng: `Ctrl-C`. Các bước đã xong vẫn giữ kết quả trong `eval/runs/live-<ngày>/`;
  chạy lại cùng ngày sẽ bị chặn nếu thư mục đã có dữ liệu — di chuyển thư mục cũ trước.
- Tắt PostgreSQL cục bộ: `bash infra/local-pg.sh stop`.
- Chỉ tốn tiền ở bước 3 (index) và 4 (extraction); Ctrl-C trước bước 3 thì chưa tốn gì.
- Mọi test phát triển vẫn offline (`HOMEMATCH_LLM_MODE=demo`, embedding disabled) — script chỉ
  export các biến trong tiến trình của nó, không ghi vào `.env` hay repo.
