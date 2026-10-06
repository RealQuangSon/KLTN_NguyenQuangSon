# Tiêu chí nghiệm thu HomeMatch AI Agent

**Cập nhật:** 05/10/2026. Mỗi AC ứng với yêu cầu trong [danh mục](yeu-cau-san-pham.md). Một AC chỉ tính là đạt khi có bằng chứng chạy thật (test, lệnh, ảnh, log) kèm ngày và cấu hình. Test file nêu bên phải là nơi kiểm tự động hiện có.

## Trợ lý AI

| AC | Yêu cầu | Ca kiểm | Test |
|---|---|---|---|
| AC-01 | FR-01–03 | Alias khu vực ("Q7", "tim tro hanoi cau giay"); thành phố không mặc định; tối đa 2 câu hỏi; ý định chi phí, hỗ trợ, cẩm nang không gọi LLM | `test_locations.py`, `test_interpreter_api.py`, `test_tenant_portal.py` |
| AC-02 | FR-04 | Revision cũ → 409; tiền trong chat không thành ngân sách | `test_workflow.py`, `test_agent_field_status.py` |
| AC-03 | FR-05–06 | 15 ca oracle chi phí và 7 ca khả năng chi trả; băng ở mốc 0,30/0,40 | `eval oracle`, `test_finance.py` |
| AC-04 | FR-07–08 | Ví dụ vay tính tay; lãi 0%; vượt gốc tối đa; mô phỏng không đổi hồ sơ | `test_finance.py` |
| AC-05 | FR-09, 10, 14 | 0 vi phạm điều kiện cứng; `needs_verification`; gợi ý nới lỏng | `eval invariants` |
| AC-06 | FR-11 | Fallback ghi rõ nhãn; cache embedding truy vấn | `test_agents_memory.py` (chưa có vector thật) |
| AC-07 | FR-12 | Mọi khẳng định có bằng chứng | `eval grounding` |
| AC-08 | FR-13 | Phản thực tế hoa hồng và thời gian tồn; `override_reason`; chủ nhà chỉ đổi thứ tự trong phần phòng của mình | `test_workflow.py`, `test_landlord.py` |
| AC-09 | FR-15–17 | Chủ nhà chỉ thấy phòng mình; khách thấy dần (`partially_published`); hết hiệu lực khi hồ sơ hoặc kho đổi; khởi động lại không mất quyết định | `test_landlord.py`, `test_backend_durability.py` |
| AC-10 | FR-18–20 | Chỉ căn đã duyệt; so sánh có tư vấn; lịch xem gửi đúng chủ nhà | `test_workflow.py`, `test_tenant_portal.py` |
| AC-11 | FR-21 | Tool ngoài danh sách bị chặn; giới hạn bước; provenance ghi agent | `test_agents_memory.py` |
| AC-12 | FR-22 | Không đồng ý thì không ghi nhớ; không lưu tiền; rút đồng ý thì xóa | `test_agents_memory.py` |
| AC-13 | FR-24 | Kho v2 hợp lệ, có căn hộ, có Hà Nội | `eval validate`, `eval/tests` |
| AC-14 | FR-25 | 401/403 đúng vai trò; chủ nhà không vào được API admin | `test_backend_contract.py` |

## Nền tảng (5 phân hệ)

| AC | Yêu cầu | Ca kiểm | Test |
|---|---|---|---|
| AC-15 | FR-26–27 | Bộ lọc chỉ trả tin đã công khai và còn trống; tiện ích chưa rõ không thỏa bộ lọc; sắp xếp; tham số lạ → 422; giao diện danh sách và bản đồ | `test_tenant_portal.py`, `search-portal.test.tsx` |
| AC-16 | FR-28 | Không đề xuất căn vượt ngân sách hoặc căn thiếu tổng tháng; ưu/nhược điểm theo dữ liệu | `test_tenant_portal.py` |
| AC-17 | FR-29 | Ngữ cảnh chuyển giao không có thu nhập, tỷ lệ, SĐT, email; một cuộc trò chuyện cho mỗi phòng; người ngoài không đọc được; đếm tin chưa đọc | `test_conversations_admin.py`, `inbox-admin.test.tsx` |
| AC-18 | FR-30 | Lịch trực tuyến có link phòng họp; đặt từ tin đăng; phòng đã cọc/thuê → 409 | `test_landlord.py`, `test_tenant_portal.py` |
| AC-19 | FR-31 | Câu hỏi cọc, tạm trú trả đúng mục; nội quy chủ nhà theo chủ đề; trả lời trong chat không gọi LLM | `test_tenant_portal.py` |
| AC-20 | FR-32–34 | Nhắc lịch, thanh toán, gia hạn chạy lặp không trùng; chăm sóc khách chỉ gửi khi chưa đặt lịch; đổi trạng thái hoặc giá báo cho khách đã quan tâm | `test_automation.py`, `test_pms.py` |
| AC-21 | FR-35, 41 | Hợp đồng theo phiên bản: sửa thì phải chấp thuận lại; kích hoạt → phòng đã thuê; trùng kỳ → 409; thanh lý → phòng trống; văn bản in được | `test_pms.py` |
| AC-22 | FR-36–38 | Transcript che PII, có audit khi mở; số liệu phản hồi của chủ nhà; người không phải admin → 403 | `test_conversations_admin.py` |
| AC-23 | FR-39–40, 44–45 | Dashboard, báo cáo và khách tiềm năng tính từ dữ liệu; CRUD tin có CAS, không sửa được tin người khác | `test_landlord.py`, `test_pms.py`, `pms.test.tsx` |
| AC-24 | FR-42 | Hóa đơn khớp số tính tay; thiếu chỉ số hoặc đơn giá → từ chối lập; không lập trùng kỳ; báo chuyển chưa phải đã thu; không thu vượt số còn nợ; biên lai | `test_pms.py` |
| AC-25 | FR-43 | Chỉ người đang thuê báo hỏng được; chuyển trạng thái hợp lệ; mở lại phải có lý do | `test_pms.py` |
| AC-26 | FR-46–48 | Bài đăng chỉ dùng dữ liệu tin, có link trang tin công khai; đề xuất giá cần ít nhất 3 căn tương đương; cố vấn định tuyến đúng câu hỏi | `test_copilot.py`, `copilot.test.tsx` |

## Cổng hoàn thành

| Cổng | Điều kiện | Trạng thái 05/10 |
|---|---|---|
| G1 Cơ bản | AC-01–AC-10, 13, 14 có test pass; demo đầu-cuối trên trình duyệt | Test pass; chưa demo trên trình duyệt |
| G2 Nâng cao | AC-11, 12; FR-08, 19 | Test pass; chưa demo trên trình duyệt |
| G-NT Nền tảng | AC-15–AC-26 | Test pass; còn các mục "Một phần" (ảnh, ưu đãi, tự đăng đa kênh) |
| G3 Triển khai | NFR-06, NFR-09 trên Railway với GPT-4o và pgvector | Chưa |
| G4 Nghiên cứu | Freeze, nhãn người chấm, khảo sát, báo cáo RQ1–RQ5 | Chưa |
