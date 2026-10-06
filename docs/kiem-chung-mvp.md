# Kiểm chứng bản MVP local HomeMatch

Ngày 2026-10-01. Phạm vi: mã của bốn agent, dữ liệu tổng hợp và đường offline. Đây là bằng chứng triển khai, chưa thay báo cáo KLTN hoặc kết quả nghiên cứu.

> Bằng chứng lịch sử trước backend 0.3.0. Kết quả mới về PostgreSQL, HTTP thật, migration và 100 tests ở [báo cáo backend](kiem-chung-backend.md).

## Môi trường

Python sạch 3.14.6 ở `.local/venv-check` (`include-system-site-packages=false`), dependencies khóa trong `requirements.lock`, `pip check` đạt. Node 26.7.0 / npm 11.19.0 và frontend package-lock. macOS arm64. Tests dùng temp DB, rule/B1 và SDK fixtures, không gọi provider. Source inventory/hash ở [release manifest](release-manifest.json).

`.venv` scaffold cũ kế thừa system packages; kiểm chứng release dùng venv sạch. README hướng dẫn tạo venv sạch từ đầu. Không có commit Git hoặc cloud release được tạo.

## Kết quả đã chạy

| Kiểm tra | Kết quả | Phạm vi/bằng chứng |
|---|---|---|
| Python backend + eval | **50 passed, 2 skipped** | Bộ tests; PG opt-in thiếu test DSN nên skipped |
| UI Vitest/RTL | **15/15 passed** | Pending/null/stale/auth/compare/CAS/replay, API fixtures |
| TypeScript + Vite build | **Đạt** | 36 modules; JS 236,40 KB / gzip 73,44 KB |
| API TestClient smoke | **7 nhóm đạt** | Identity, rights/draft CAS, pending/assignment, subset/order/replay/compare, viewing, catalog stale, revoke |
| Demo offline | **Đạt** | Interview → pending → review → compare → requested/confirmed; quote3.250.000/tháng,5.500.000/ban đầu |
| CLI setup/seed/import | **Đạt trên SQLite** | 80 phòng; import cùng batch hai lần giữ hash/count |
| Dataset validation | **Đạt** | 80 canonical, pilot25,30 profiles10/20,38 utterances;100% synthetic |
| Generator reproduction | **Đạt** | Output mới có manifest/artifact hashes khớp bộ đang dùng |
| Finance oracle | **15/15 exact VND/null** | Hằng số tính tay độc lập; người kiểm tra chéo còn pending |
| Ranking development | **B1:10 chạy; P:10 unavailable** | Thiếu provider/vector thật, không dùng B1 thay P |
| Blind annotation/metric | **Đã tạo gói, chưa có nhãn** | Nhãn trống, metrics pending, không có quality score |
| Local PG/pgvector | **Khởi tạo và query thử đạt** | PG 17.11, vector 0.8.6, cosine cùng vector=0; chưa là workflow integration |
| Infra shell/TOML/YAML | **Cú pháp/parse đạt** | Không đồng nghĩa Docker build/restore đạt |

Log kiểm tra gộp ở `.local/check-local.log`; các sửa cuối được kiểm lại ở `.local/python-final.log` (**50 passed**) và `.local/smoke-final.json`. Script `infra/check-local.sh` kiểm pip/dataset/Python/UI/build/demo/in-process smoke với `set -euo pipefail`; ca cố ý dùng executable thất bại trả exit 1, không chạy các bước tiếp. Tests và artifacts dev chia sẻ được nằm trong repo. Eval reports gắn input/code hashes và mode. Relevance dev chỉ là gói chuẩn bị, không có nhãn máy tự tạo.

Rule F1/intent trên 10 hồ sơ dev soạn sẵn ở `eval/runs/development/extraction.json`; không dùng làm điểm GPT, chất lượng thị trường hoặc bằng chứng giả thuyết KLTN. Không tính nDCG/P improvement khi thiếu nhãn/P thật.

## Thay đổi quan trọng

- Auth seed scrypt, token băm/expiry/revoke; public guard kiểm hash lưu trữ, rotation explicit thu hồi token.
- Draft/kho CAS; confirm tăng profile version. Results/compare/viewing/review kiểm quyền và phiên bản; kho writer/finalize phối hợp transaction gate.
- Graph lưu nháp trước interrupt, resume theo event ledger; retry generation tạo run mới và duyệt mới.
- Finance phân biệt thiếu/0/included, per-line Decimal HALF_UP, không cộng trùng tháng đầu. P thêm semantic trên cùng full eligible set.
- UI bỏ response trễ, không tự gửi lại mutation, giữ key review/viewing và đọc lại CAS conflict.

## Chưa kiểm chứng và đầu vào còn thiếu

- Hai tests `backend/tests/test_postgres.py` chưa chạy thành công: checkpoint/restart/auth/stale và writer-before-finalize. Test DB chưa tạo; backend agent dừng ở bước chuyển sang dev/schema thử. Không suy diễn PG đạt từ query nhỏ.
- API thật trên TCP, browser desktop/mobile, console/keyboard, FE↔BE thật và PG backup/restore còn pending. Máy không có Docker; container/cloud mới được parse.
- Không có OpenAI key nên chưa gọi GPT/embedding/index thật, chưa có live usage/cost/P quality. Budget CLI là khai báo, chưa là spend cap.
- G4 chưa đóng, dataset chưa freeze; nhãn độc lập/user study, test research, mẫu báo cáo trường, slide/video và Railway chưa hoàn thành.

## Giới hạn duyệt quyền

Automatic approval review từ chối bước **khởi động uvicorn API localhost:8000 với PostgreSQL** vì tài khoản chạm usage limit, quá trình duyệt không thể hoàn tất; hệ thống nói đây không phải đánh giá hành động không an toàn. Agent Backend/Data cũng dừng vì usage limit. Không dùng công cụ khác để bypass; root tiếp tục hoàn thiện mã/tests/docs offline theo yêu cầu người dùng. Lệnh khởi động/kiểm tra tiếp theo đã có trong README/runbook để chạy khi môi trường cho phép.

Giới hạn synthetic/mẫu nhỏ/nhãn người chấm cần ghi trong KLTN. Hiện không có bằng chứng hài lòng, cải thiện nDCG hoặc production scalability.
