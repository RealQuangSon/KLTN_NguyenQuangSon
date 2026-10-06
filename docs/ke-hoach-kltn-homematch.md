# Đề cương KLTN — HomeMatch AI Agent

**Cập nhật:** 05/10/2026 (mở rộng theo 5 phân hệ). Đây là văn bản gốc của bộ tài liệu; mọi đặc tả, kế hoạch, tiêu chí khác phải khớp với đề cương này.

**Tên đề tài:** HomeMatch AI Agent – Trợ lý gợi ý căn hộ theo nhu cầu và năng lực tài chính.

**Phạm vi áp dụng:** nền tảng **cho thuê** phòng trọ, studio, căn hộ tại **TP.HCM và Hà Nội**. AI Agent tư vấn cho người thuê; **chủ nhà** duyệt gợi ý và vận hành cho thuê; quản trị viên giám sát. Xem [quyết định điều chỉnh](#7-quyết-định-điều-chỉnh-so-với-đề-bài).

## 1. Thực trạng

Khách thường mô tả nhu cầu mơ hồ, ví dụ "gần trường, thoáng, tầm 7 triệu, view đẹp". Chủ nhà phải tự lọc khách, trả lời từng tin nhắn, hẹn lịch, rồi quản lý hợp đồng, điện nước, công nợ và sửa chữa bằng sổ tay hoặc nhiều ứng dụng rời rạc. Gợi ý thường chậm, thiếu nhất quán và khó giải thích. Giá thuê niêm yết cũng không cho khách thấy tổng chi phí tháng hay tiền cần chuẩn bị khi vào ở.

## 2. Vấn đề cần giải quyết

Xây dựng một AI Agent:

1. Phỏng vấn để khai thác nhu cầu.
2. Chuyển nhu cầu thành tiêu chí.
3. Kiểm tra khả năng tài chính: ngân sách, tiền vào ở, tỷ lệ trên thu nhập, ước tính khoản vay ngắn hạn.
4. Truy vấn kho và xếp hạng top căn kèm lý giải đánh đổi.

Đặt agent trong một nền tảng đủ để đi hết hành trình thuê: tìm, so sánh, trao đổi với chủ nhà, xem phòng, ký hợp đồng, thanh toán, sửa chữa.

## 3. Ràng buộc

| Ràng buộc | Cách đáp ứng |
|---|---|
| HITL: người bán duyệt danh sách gợi ý trước khi trình khách | **Mỗi chủ nhà duyệt phòng của mình** trong danh sách AI. Khách thấy dần các phòng đã được chủ duyệt. Danh sách gắn phiên bản hồ sơ và kho; hồ sơ hoặc kho đổi thì danh sách hết hiệu lực. |
| Minh bạch lý do gợi ý | Lý do, đánh đổi, điểm thành phần truy về dữ liệu căn và dòng chi phí, được kiểm bằng `eval grounding`. |
| Không thiên vị căn tồn | Xếp hạng không dùng hoa hồng hay thời gian tồn; có kiểm thử phản thực tế. Chủ nhà bỏ hoặc đổi thứ tự phòng phải ghi lý do, và chỉ đổi được trong phần phòng của mình. |
| Bảo mật thông tin tài chính | Chủ nhà chỉ thấy băng khả năng chi trả, không thấy thu nhập hay tỷ lệ. Tiền và liên hệ được tách khỏi prompt LLM và embedding. Chat lưu có che số điện thoại, email, số tài khoản; giữ 90 ngày. |
| Tối ưu chi phí truy vấn ngữ nghĩa | Lọc cứng trước khi chấm semantic. Vector căn chỉ tính lại khi nội dung đổi. Cache embedding truy vấn bền. Giới hạn lượt gọi mỗi phiên. Đo lượt gọi và lượt trúng cache. |

## 4. Mục tiêu

**Cơ bản (đề bài):** trợ lý hỏi nhu cầu, trả top căn kèm giải thích và ước tính tài chính; chủ nhà duyệt hoặc lọc trước khi khách thấy.

**Nâng cao (đề bài):**
- multi-agent (nhu cầu, tài chính, xếp hạng);
- so sánh trực quan;
- mô phỏng kịch bản vay;
- memory xuyên phiên;
- đánh giá độ hài lòng và độ chính xác.

**Nền tảng (5 phân hệ người dùng yêu cầu ngày 05/10/2026):**

1. **Cổng người thuê:**
   - tìm kiếm kết hợp chat AI và bộ lọc;
   - khung xem nhanh cạnh luồng chat; xem dạng danh sách hoặc bản đồ;
   - AI so sánh và đề xuất căn tối ưu;
   - live chat với chủ nhà có chuyển ngữ cảnh;
   - đặt lịch xem trực tiếp hoặc trực tuyến;
   - cẩm nang số.
2. **Động cơ tự động hóa:**
   - nhắc lịch xem, nhắc thanh toán, nhắc gia hạn;
   - chăm sóc khách đã xem tin;
   - đồng bộ trạng thái và giá;
   - tự tạo hợp đồng, hóa đơn, biên lai.
3. **Admin Console:** giám sát hội thoại AI, quản lý luồng chuyển giao và tỷ lệ phản hồi của chủ nhà.
4. **Cổng chủ nhà (PMS & CRM):**
   - dashboard sức khỏe vận hành;
   - phòng và tin đăng;
   - hợp đồng và khách thuê;
   - hóa đơn và công nợ;
   - sửa chữa;
   - khách tiềm năng, hộp thư hợp nhất, phòng xem trực tuyến, lịch hẹn;
   - báo cáo.
5. **Trợ lý AI cho chủ nhà:** viết bài đăng theo kênh, chia sẻ đa kênh, cố vấn điều hành bằng văn bản hoặc giọng nói.

## 5. Công nghệ

| Thành phần | Lựa chọn |
|---|---|
| LLM | GPT-4o structured output. Chế độ `demo` dùng luật offline để phát triển và kiểm thử. |
| Matching semantic | Embedding OpenAI + PostgreSQL pgvector, kết hợp B1 thành phương pháp P |
| Điều phối agent | LangGraph: supervisor và các agent; `interrupt()` chờ chủ nhà duyệt |
| Engine tài chính | Python `Decimal`, làm tròn VND: chi phí thuê, khả năng chi trả, vay annuity, hóa đơn |
| Backend | FastAPI; một worker có luồng job nền cho tự động hóa |
| Frontend | React + TypeScript; Leaflet + OpenStreetMap cho bản đồ |
| Triển khai | Railway (PostgreSQL + pgvector) |

## 6. Câu hỏi nghiên cứu

| Câu hỏi | Phép đo |
|---|---|
| RQ1: Trích xuất nhu cầu tiếng Việt và biết khi cần hỏi lại | Độ chính xác ý định; F1 từng trường; tỷ lệ hỏi lại đúng |
| RQ2: P (semantic) có xếp hạng tốt hơn B1 (cấu trúc) trên cùng tập đủ điều kiện | nDCG@5, P@5 theo cặp với nhãn người chấm mù |
| RQ3: Gợi ý đúng ràng buộc, đúng tiền, không thiên vị | Số vi phạm điều kiện cứng = 0; oracle tài chính và hóa đơn khớp; phản thực tế; tỷ lệ khẳng định có bằng chứng |
| RQ4: Người dùng hài lòng và hiểu chi phí | Khảo sát 5–10 người thuê và chủ nhà: hoàn thành tác vụ, thời gian, câu hỏi hiểu chi phí, thang hài lòng |
| RQ5: Chi phí và độ trễ | p50/p95 thời gian máy; lượt gọi, token; lượt trúng cache embedding |

## 7. Quyết định điều chỉnh so với đề bài

| Mã | Đề bài | Áp dụng | Trạng thái |
|---|---|---|---|
| D-01 | Mua căn hộ ("tầm 3 tỷ") | Thị trường **cho thuê** phòng, studio, căn hộ | Đã xác nhận 05/10 |
| D-02 | Engine tính vay đơn giản | Vay ngắn hạn (annuity) cho phần tiền vào ở còn thiếu | Đã xác nhận 05/10 |
| D-03 | Hai vai trò: sale và khách | **Khách** (`renter`) và **chủ nhà** (`owner`), cộng quản trị viên (`admin`). Vai trò `manager` cũ không còn quyền nghiệp vụ. | Đã xác nhận 05/10 |
| D-04 | Không nêu khu vực | TP.HCM và Hà Nội; tên quận quen gọi, nhận diện tên gọi khác | Đã xác nhận 05/10 |
| D-05 | Sale duyệt cả danh sách | **Mỗi chủ nhà duyệt phòng của mình**; khách thấy dần phòng đã duyệt | Người dùng chọn 05/10 |
| D-06 | — | Chat AI được lưu có che PII, giữ 90 ngày; mỗi lần admin mở đều ghi audit | Người dùng chọn 05/10 |
| D-07 | Tích hợp bên ngoài | Thay bằng phương án không cần tài khoản: bản đồ OSM; phòng họp Jitsi cho xem trực tuyến; email là stub ghi log; chia sẻ mạng xã hội bằng link và sao chép, không tự đăng; giọng nói bằng Web Speech API của trình duyệt; thanh toán đối soát thủ công, không qua cổng thanh toán | Thiết kế 05/10 |
| D-08 | Hợp đồng điện tử | Chấp thuận theo phiên bản trong ứng dụng cùng văn bản in được; **không** phải chữ ký số có giá trị pháp lý | Thiết kế 05/10 |

## 8. Phương pháp của trợ lý

1. **Supervisor** định tuyến từng lượt chat:
   - agent nhu cầu: trích xuất và hỏi lại;
   - agent tài chính: chi phí, vay, mô phỏng;
   - cẩm nang: truy xuất câu trả lời;
   - hỗ trợ.
   Mỗi agent chỉ dùng các tool được phép, tối đa 4 bước mỗi lượt.
2. Khách xác nhận hồ sơ trên form. Tiền nêu trong chat chỉ là gợi ý. Memory (khi khách đồng ý) chỉ điền sẵn dạng "đã suy luận".
3. Agent xếp hạng lọc cứng (khu vực, loại, phòng ngủ, sức chứa, tiện ích, bán kính, ngân sách, điều kiện vay), chấm B1/P, lấy top 5 kèm lý do.
4. Danh sách dừng ở `interrupt()`. Từng chủ nhà duyệt phần phòng của mình. Khi mọi chủ nhà đã quyết định, graph chạy tiếp để chốt kết quả.
5. Khách thấy phòng đã duyệt, so sánh có tư vấn, mô phỏng tài chính, chat với chủ nhà kèm ngữ cảnh, và đặt lịch xem.

## 9. Dữ liệu

Kho v2 hoàn toàn **tổng hợp**:
- 220 căn: TP.HCM 120, Hà Nội 100; 4 chủ nhà, mỗi người có nội quy riêng;
- 45 hồ sơ gold;
- 22 ca oracle tài chính.

Dữ liệu vận hành (hợp đồng, hóa đơn, tin nhắn, lượt xem) phát sinh khi dùng hệ thống. Không crawl hay tái sử dụng dữ liệu HubHome hay Chợ Tốt khi chưa có quyền. Chi tiết ở [kế hoạch dữ liệu](../data/PLAN.md).

## 10. Đánh giá

Có năm lớp đánh giá:
1. Đúng chức năng: test tự động, oracle, bất biến, grounding.
2. Trích xuất.
3. Xếp hạng B1 so với P.
4. Người dùng: khảo sát.
5. Vận hành: độ trễ, chi phí.

Khóa dữ liệu, cấu hình, prompt trước khi chạy tập test. Thiếu nhãn hoặc người thử thì báo "chưa đo". Chi tiết ở [kế hoạch đánh giá](../eval/PLAN.md).

## 11. Kế hoạch

Các giai đoạn GĐ1–GĐ3 và các đợt E1–E6 đã có code ngày 05/10 ([kế hoạch](ke-hoach-trien-khai.md), [trạng thái](trang-thai-trien-khai.md)). Còn lại:
- deploy Railway;
- chạy GPT-4o/pgvector thật;
- demo trên trình duyệt;
- đánh giá nghiên cứu (GĐ5).

## 12. Cơ sở tham khảo

- [A Survey on Conversational Recommender Systems](https://arxiv.org/abs/2004.00646).
- [Evaluating Conversational Recommender Systems: A Landscape of Research](https://arxiv.org/abs/2208.12061).
- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629).
- [Nghiên cứu HubHome](nghien-cuu-hubhome.md): tham khảo trải nghiệm tìm phòng có trợ lý AI, cổng chủ nhà, hợp đồng, thu tiền.
