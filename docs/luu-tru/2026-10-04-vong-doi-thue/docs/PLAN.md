# Kế hoạch tài liệu sản phẩm HomeMatch

**Ngày:** 04/10/2026. Docs phục vụ sản phẩm v1 hoàn thiện và nghiên cứu KLTN. [Chỉ mục](README.md) xác định nguồn chính; [chi tiết](DETAILED_PLAN.md) là checklist duy trì/bàn giao.

| Task | Việc cần giao | Điều kiện xong |
|---|---|---|
| DOC-V1-01 | Research HubHome có nguồn/ngày/giới hạn | HH-01..12 phân biệt quan sát/công bố/lịch sử/đề xuất/chưa rõ |
| DOC-V1-02 | Product/scope/roles/glossary và assumptions | HM-01..10 bắt buộc, mở rộng/đầu vào tách rõ; không áp lại MVP |
| DOC-V1-03 | Requirements/process/state/permission/AC | 30 HM-R có AC-HM, negative cases và hành trình E2E; source trace rõ |
| DOC-V1-04 | Architecture/API/UI/plans theo cùng contract | Current 0.3.0 khác target v1; pending/public/acceptance/payment semantics thống nhất |
| DOC-V1-05 | Evidence trạng thái và hướng dẫn sử dụng/vận hành | Chỉ ghi đã đạt từ run/browser/deploy thực; role guides và runbook theo release |
| DOC-V1-06 | Protocol/report/thesis/slide/demo | Freeze/labels/results truy được, không mock thành live hoặc satisfaction |
| DOC-V1-07 | Consistency review và gói bàn giao | Links/IDs/source/state không lệch, release manifest mới đúng phạm vi và không secret/PII |

DOC-V1-01..04 đã có bản đặc tả trong lần viết lại này; phải cập nhật theo implementation và kết quả review. DOC-V1-05..07 không được tự đánh dấu hoàn thành từ việc tạo file docs. Hướng dẫn chạy local trong README giữ hành vi mã hiện tại, chưa là runbook đủ cho sản phẩm v1.

Tài liệu lịch sử gồm khảo sát đăng nhập 01/10, kiểm chứng scaffold/MVP/backend và release manifest 01/10. Không thay số cũ hoặc giả đó là lần kiểm thử hôm nay. Khi phát hành v1, tạo evidence/manifest mới cùng code/data/config release.

Báo cáo KLTN cần mẫu trường, giảng viên và dữ liệu/nhãn thực tế; viết các chương thiết kế ngay, chỉ điền kết quả khi thực nghiệm đã chạy.
