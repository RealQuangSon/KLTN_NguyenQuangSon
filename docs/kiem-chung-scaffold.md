# Kiểm chứng khung agent HomeMatch

Ngày 01/10/2026; chạy tại repository `/Users/son/KLTN_NguyenQuangSon` trên macOS, Python 3.14.6. Runtime `.venv` sử dụng các package nền đã có và SQLite checkpointer cài riêng; các phiên bản trực tiếp khớp requirements.txt. Chưa thử cài toàn bộ trên máy sạch hoặc các phiên bản Python khác.

## Kết quả

| Kiểm tra | Kết quả quan sát |
|---|---|
| `.venv/bin/python -m pytest` | **26 passed**, 1,25 giây ở lần kiểm tra cuối |
| `.venv/bin/python -m backend.demo` | Hoàn tất interview → pending → approved → compare → viewing |
| Pending projection | results rỗng; không chứa items/diagnostics |
| Quote tham chiếu | Tổng tháng 3.250.000 VND; tiền ban đầu 5.500.000 VND |
| Restart/checkpoint | Mở lại pending run và duyệt tiếp được |
| Crash window event/resume | Sự kiện đã ghi nhưng chưa resume: retry hoàn tất công bố |
| Dependency chính | Tất cả phiên bản đã kiểm tra khớp requirements |

TestClient có một cảnh báo deprecation từ Starlette về httpx; không làm các test thất bại. Chưa thay runtime test sang httpx2 trong scaffold này.

## Những hành vi đã kiểm tra

- Finance: số tiền tham chiếu, thay số người/xe/kWh, phí đã gồm, thiếu phí/cọc và trần ban đầu bằng 0.
- Matching: tiền thuê rẻ nhưng tổng vượt trần; unknown ở phí/tiện ích bắt buộc; tọa độ gần đúng sát bán kính; nguồn giải thích.
- HITL/quyền: khách không đọc nháp, khách khác/quản lý khác bị từ chối, không thêm phòng ngoài nháp, duyệt subset/thứ tự, reject/needs_revision không công bố.
- Phiên bản/idempotency: profile đổi, catalog đổi trước/sau duyệt, payload duyệt lặp/xung đột, restart và retry event.
- Compare/viewing: chỉ phòng công bố hiện tại, giới hạn số phòng, yêu cầu chưa xác nhận, chống tạo trùng và quyền phản hồi.
- Agent/API: không tự mặc định city hoặc xác nhận hint ngân sách; chi phí/hỗ trợ rõ không gọi model; adapter che mẫu tiền/liên hệ và trả lỗi an toàn bằng SDK client giả; luồng FastAPI hai vai trò.

## Giới hạn của bằng chứng

Đây là kiểm chứng chức năng scaffold, không phải đánh giá chất lượng GPT-4o hay hybrid retrieval. Không có cuộc gọi model/embedding thật, benchmark nDCG/Precision, user study hoặc Railway deployment. Rule interpreter chỉ nhận một số cách viết tiếng Việt; profile form là bước xác nhận đáng tin.

Dữ liệu gồm 12 phòng tổng hợp, không thể suy chất lượng trên thị trường thuê thật. Phân quyền dùng demo tokens công khai; chưa là security assessment cho ứng dụng public. SQLite/RLock được kiểm tra một process; chưa có kiểm thử nhiều worker và worker/outbox tự recovery khi run chết ở bước generating.

Các phần chưa triển khai và kế hoạch bổ sung được nêu ở [README](/Users/son/KLTN_NguyenQuangSon/README.md) và [kế hoạch triển khai](/Users/son/KLTN_NguyenQuangSon/docs/ke-hoach-trien-khai.md).
