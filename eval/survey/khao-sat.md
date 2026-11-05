# Khảo sát người dùng HomeMatch (GĐ5) — biểu mẫu chính thức

**Đối tượng:** 5–10 người dùng thử kịch bản demo đầu-cuối (tìm phòng → duyệt → gợi ý → chi phí).
**Đồng ý:** mỗi người trả lời cần được xin phép trước; kết quả ẩn danh, chỉ dùng cho đề tài.
**Cách ghi:** điền CSV với các cột dưới đây (một dòng một người); chạy
`python -m eval survey-report --csv <file>.csv` để tính trung bình và độ lệch chuẩn.
Agent không tự tạo câu trả lời; file CSV do người vận hành nhập từ phiếu thu được.

## Cột CSV

| Cột | Ý nghĩa |
|---|---|
| `respondent_id` | Mã ẩn danh (S01, S02, …) |
| `sus1`…`sus6` | SUS rút gọn, thang 1–5 (1 = hoàn toàn không đồng ý, 5 = hoàn toàn đồng ý) |
| `trust_explanation` | 1–5: tôi tin lời giải thích vì sao phòng được gợi ý |
| `satisfaction_suggestions` | 1–5: tôi hài lòng với các gợi ý phòng |
| `privacy_financial` | 1–5: tôi yên tâm về quyền riêng tư tài chính (thu nhập không bị lộ) |
| `duration_minutes` | (tùy chọn) phút hoàn thành kịch bản |
| `task_completed` | (tùy chọn) 1 hoàn thành / 0 không |

## Câu hỏi SUS rút gọn (thang 1–5)

1. Tôi thấy việc dùng hệ thống dễ dàng. *(sus1, câu thuận)*
2. Tôi thấy các bước trong hệ thống phức tạp. *(sus2, câu nghịch)*
3. Tôi nghĩ hệ thống dễ sử dụng. *(sus3, câu thuận)*
4. Tôi cần sự trợ giúp của người có kỹ thuật mới dùng được. *(sus4, câu nghịch)*
5. Tôi thấy các chức năng hợp nhất tốt với nhau. *(sus5, câu thuận)*
6. Tôi gặp nhiều vướng mắc khi dùng hệ thống. *(sus6, câu nghịch)*

Điểm SUS = 2,5 × tổng điểm sau hiệu chỉnh (câu thuận lấy điểm−1, câu nghịch lấy 5−điểm), thang 0–100.

## Câu hỏi cảm nhận (thang 1–5)

7. **Độ tin cậy lời giải thích:** lời giải thích của hệ thống có căn cứ, đúng với dữ liệu phòng tôi thấy. *(trust_explanation)*
8. **Hài lòng với gợi ý:** các phòng được gợi ý phù hợp với nhu cầu của tôi. *(satisfaction_suggestions)*
9. **Quyền riêng tư tài chính:** tôi yên tâm khi khai báo khả năng chi trả vì hệ thống không lộ thu nhập cho chủ nhà. *(privacy_financial)*

## Câu mở (không tính điểm, ghi chú thêm vào báo cáo)

- Điều gì khiến bạn chưa tin lời giải thích của hệ thống?
- Có thông tin nào bạn lo sẽ bị lộ cho chủ nhà không?
