# Thêm công cụ vào harness

Đăng ký một `ToolDefinition` trong `backend/app/agent_tools.py`: tên duy nhất, agent, mô tả tiếng Việt, lớp `ToolArgs` (Pydantic, extra forbid), `writes`, timeout, view, capability và args mẫu. Mọi tool graph cũng nằm trong registry, với `exposed=False` để không gửi schema nội bộ cho model. Không nhập `agents.py` từ registry để tránh vòng phụ thuộc.

Đặt hàm nghiệp vụ cùng file registry và gán `handler=` vào khai báo. Hàm nhận `(service, session, actor, toolbox, **args)`; harness tự bind ngữ cảnh đã xác thực, không cần sửa loop. Như vậy tool mới chỉ sửa **một file** và được test hợp đồng tham số hóa kiểm tự động. Các closure tool cũ được giữ để tương thích. Luồng gọi là executor → `ToolBox.invoke` → `ToolBox.call` → hàm nghiệp vụ; không gọi hàm thay đổi trạng thái trực tiếp từ output model. `AGENT_TOOLS`, `TOOL_CAPABILITIES`, schema gửi model và view đều sinh từ registry; quyền trên bản ghi vẫn được service kiểm độc lập.

`invoke` trả `{ok:true,data}` hoặc `{ok:false,error,message,hint}`. Kết quả được bỏ trường thu nhập/tỷ lệ suy ra thu nhập và che SĐT/email/tiền trong văn bản trước khi đưa cho model. Summary chỉ dùng câu và mã lỗi đã khai báo, không echo exception hoặc tham số. Dữ liệu tiền số chỉ lấy từ tool tất định; không để model ghi vào `NeedsPatch`.

Tool ghi chạy tuần tự. Executor lưu SHA256 args và kết quả đã lọc với khóa `turn_id:tool:hash(args)` trong transaction cùng mutation; lỗi rollback. Frontend tái dùng mã lượt cho retry. Chỉ thêm tool giao dịch dạng chuẩn bị: thao tác đặt lịch/chốt/gửi claim thật phải chờ khách bấm xác nhận.

Thêm args mẫu để test tham số hóa `backend/tests/test_agent_tools.py` tự kiểm schema/envelope/summary/redact. Thêm ít nhất một test hành vi thật của handler và các nhánh quyền/lỗi; với tool ghi, kiểm retry và rollback trong `test_agent_idempotency.py`. Chạy pytest, kiểm frontend nếu sửa FE, và `bash infra/check-local.sh`; không dùng provider live trong test.
