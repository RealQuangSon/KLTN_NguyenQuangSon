# Nghiên cứu HubHome cho sản phẩm HomeMatch hoàn thiện

> **Ghi chú phạm vi 05/10/2026:** đề tài là trợ lý AI gợi ý căn cho thuê theo nhu cầu và năng lực tài chính ([đề cương](ke-hoach-kltn-homematch.md)). Từ nghiên cứu này, đề tài dùng HH-01…HH-06 (tìm kiếm, AI, chi phí, so sánh, tài khoản, lịch xem) và HH-12 (riêng tư). HH-07…HH-11 (chủ nhà, hợp đồng, hóa đơn, công tơ, sửa chữa) nằm **ngoài đề tài**. Các đoạn bên dưới nhắc tới "HomeMatch v1" là phạm vi cũ ngày 04/10. Theo HH-02, "Tìm nhanh" của HubHome chỉ có TP.HCM; HomeMatch bổ sung Hà Nội.

**Cập nhật nghiên cứu:** 04/10/2026, múi giờ Việt Nam. **Nguồn tham chiếu:** [HubHome](https://hubhome.vn/). **Phạm vi HomeMatch:** Toàn vòng đời thuê phòng: tìm và lựa chọn → xem phòng → hợp đồng và bàn giao → hóa đơn, sử dụng, sửa chữa → gia hạn hoặc kết thúc thuê. Các phần sau thuê và cổng chủ nhà thuộc mục tiêu sản phẩm, không bị loại khỏi phạm vi chỉ vì phiên bản hiện tại mới có lõi tư vấn.

HubHome là nguồn tham khảo hành trình và nghiệp vụ. Bằng chứng hiện có chưa đủ để xem HubHome là sản phẩm production đã được kiểm chứng hoặc để kết luận mọi module công bố đều vận hành. HomeMatch phải có đặc tả, dữ liệu, phân quyền và kiểm chứng của chính mình; không dùng mô tả của website tham chiếu để tuyên bố HomeMatch đã hoàn thiện.

## 1. Phương pháp và mức bằng chứng

Đợt **04/10/2026** đọc các trang công khai bằng trình duyệt tích hợp, không đăng nhập. Công cụ đọc web trả HTTP 403 cho trang chủ; trình duyệt đọc được qua điều hướng trên website. Đã mở composer, bộ lọc và popup lịch sử; không gửi truy vấn AI, form, ảnh, lịch xem hoặc tin nhắn cho người thật. Không cấp quyền vị trí, microphone, camera; không chỉnh tài khoản hay dữ liệu HubHome. Không đọc mã nguồn, API nội bộ, cơ sở dữ liệu hoặc thử ký số/thanh toán.

[Khảo sát đã đăng nhập ngày 01/10/2026](khao-sat-hubhome-da-dang-nhap.md) là bằng chứng lịch sử riêng: 11 trang người thuê, bốn truy vấn giả lập, live chat và cổng chủ nhà. Không coi kết quả ngày 01/10 là kiểm thử lặp lại ngày 04/10. Nội dung riêng của tài khoản/hội thoại cá nhân không được chép vào nghiên cứu này.

| Nhãn | Ý nghĩa | Có thể kết luận | Không thể kết luận |
|---|---|---|---|
| **O — Quan sát hiện tại** | UI trực tiếp thấy ngày 04/10/2026 | Trang hoặc điều khiển hiện ra trong phiên công khai | Backend đúng, dữ liệu thật, chức năng hoàn tất |
| **C — Website công bố** | HubHome tự mô tả, đọc ngày 04/10/2026 | Website đang đưa ra mô tả đó | Đã triển khai hoặc kiểm chứng độc lập |
| **H — Bằng chứng lịch sử** | Ghi nhận trong phiên 01/10/2026 | Hành vi/trạng thái trong phiên được báo cáo | Trạng thái hiện tại hoặc mọi tài khoản |
| **D — Thiết kế HomeMatch** | Bài học và yêu cầu của dự án | Nội dung cần triển khai và nghiệm thu | Kiến trúc HubHome hoặc HomeMatch đã có |
| **U — Chưa xác minh** | Thiếu quyền/dữ liệu/ca kiểm thử | Giới hạn của nghiên cứu | Chức năng không tồn tại hoặc bị lỗi |

Nhãn O áp dụng cho việc nhìn thấy nội dung; tính đúng đắn của lời cam kết vẫn thuộc C. Nhìn thấy câu về RLS hoặc nhãn SQL không chứng minh server có RLS hoặc truy vấn SQL đúng.

## 2. Nguồn chính thức và ngày đọc

S01–S10 được đọc trực tiếp ngày **04/10/2026**. Ngày cập nhật do website ghi được nêu riêng, không dùng làm ngày kiểm thử. S11 là hồ sơ lịch sử trong repository.

| Mã | Nguồn gốc | Phạm vi và giới hạn |
|---|---|---|
| S01 | [Trang chủ](https://hubhome.vn/) | Composer, hành trình tìm, chi phí, so sánh và lời giới thiệu kiểm duyệt; chưa kiểm chứng nguồn cung |
| S02 | [Trợ lý AI](https://hubhome.vn/tro-ly-ai) | Màn hình bắt đầu, Tìm nhanh, popup lịch sử; không gửi câu hỏi đợt này |
| S03 | [FAQ](https://hubhome.vn/faq) | Đã mở đáp án về còn phòng, bản đồ, lưu tin, lịch, kiểm duyệt, quyền khách, thanh toán và quyền dữ liệu; đây là mô tả website |
| S04 | [Hướng dẫn Trợ lý AI](https://hubhome.vn/help/tro-ly-ai) | Mô tả kết quả, chi tiết, chi phí, sửa tiêu chí và form lịch; ảnh/ví dụ không phải ca kiểm thử của dự án |
| S05 | [Cổng chủ nhà](https://hubhome.vn/help/cong-chu-nha) | Tự mô tả 19 module/7 nhóm và khối rỗng; chưa mở dashboard có dữ liệu |
| S06 | [Đăng và quản lý tin](https://hubhome.vn/help/dang-va-quan-ly-tin), [đăng nhập chủ nhà](https://hubhome.vn/owner/login) | Vòng đời tin và màn hình đăng nhập; không xác thực/gửi/cập nhật tin |
| S07 | [Hợp đồng và ký số](https://hubhome.vn/help/hop-dong-va-ky-so) | Tự mô tả nháp, góp ý, SmartCA và nhắc việc; chưa soạn/ký/kiểm tra tích hợp |
| S08 | [Thu tiền và công nợ](https://hubhome.vn/help/thu-tien-cong-no) | Tự mô tả kỳ thu, số thu, hạn và đối soát; chưa kiểm chứng giao dịch |
| S09 | [Xem phòng trực tuyến](https://hubhome.vn/help/phong-xem-truc-tuyen), [cẩm nang ngân sách](https://hubhome.vn/cam-nang/ngan-sach-that) | Mô tả xem từ xa và nhóm chi phí; cẩm nang ghi cập nhật 19/08/2026. Không dùng làm tư vấn/biểu giá có hiệu lực |
| S10 | [Chính sách bảo mật](https://hubhome.vn/legal/privacy) | Ghi dự thảo nghiên cứu 16/07/2026, còn việc trước production; chưa kiểm tra biện pháp bảo mật |
| S11 | [Khảo sát đã đăng nhập 01/10/2026](khao-sat-hubhome-da-dang-nhap.md) | Hồ sơ lịch sử; không làm mới ngày hoặc đổi thành chứng nhận vận hành |

Nghiên cứu không sao chép kho phòng, ảnh hoặc thương hiệu HubHome. Chưa xác minh API/export công khai hoặc quyền dùng dữ liệu HubHome cho HomeMatch.

## 3. Phát hiện và chuyển thành phạm vi sản phẩm

**HH-01–HH-12** là mã truy vết ổn định giữa nghiên cứu, kế hoạch và yêu cầu. Mã vẫn tồn tại khi bằng chứng là U; thiếu bằng chứng không được thay bằng tuyên bố chức năng đã làm.

### HH-01 — Trang đầu, tìm kiếm và composer

- **O, 04/10/2026:** Trang chủ/trợ lý công khai có ô nhu cầu, câu mẫu, Tìm nhanh, ảnh/nói, vị trí, lịch sử và cảnh báo AI có thể sai. Gửi bị vô hiệu hóa khi chưa nhập. Nguồn: [S01](https://hubhome.vn/), [S02](https://hubhome.vn/tro-ly-ai). Chỉ xác minh giao diện; chưa thử nhận dạng/upload/định vị.
- **H, 01/10/2026:** Phiên đăng nhập cũng có composer và khu vực người thuê. Nguồn: S11, phần 2–3.1; không chứng minh mọi luồng tìm hoạt động.
- **D — HomeMatch:** Bắt đầu bằng chat hoặc bộ lọc, dùng một hồ sơ tiêu chí có phiên bản. Trang giới thiệu, đăng nhập, trợ giúp và workspace nối cùng hành trình, có tải/rỗng/lỗi.
- **U:** Phương thức nhập, điều kiện đăng nhập khi gửi, thiết bị và khả năng tiếp cận chưa kiểm thử lại. Chỉ công bố phương thức nhập có bằng chứng nghiệm thu.

### HH-02 — AI, tiêu chí và kết quả

- **O, 04/10/2026:** Mở Tìm nhanh hiện TP.HCM, quận/loại tất cả, 2–10 triệu và tiện ích máy lạnh, máy giặt, ban công, nội thất, gác, thang máy, WC riêng, thú cưng. Nguồn: [S02](https://hubhome.vn/tro-ly-ai). Không nhấn tìm; chưa xác minh lọc.
- **C, 04/10/2026:** Guide mô tả chat/preview, mã căn và sửa điều kiện. Nguồn: [S04](https://hubhome.vn/help/tro-ly-ai); không chứng minh kho đang còn phòng hoặc routing đúng.
- **H, 01/10/2026:** A1/A2 không trả thẻ; A3 yêu cầu hỏi rõ nhưng nhận tìm rỗng. Nhãn SQL chưa được kiểm tra server. Nguồn: S11, phần 3.1.
- **D — HomeMatch:** Tách hỏi rõ/tìm/tính/so sánh/xem/hỗ trợ. Không tự nới điều kiện cứng; sửa nhu cầu tạo phiên bản. Lọc/ranking/lý do theo thuộc tính truy về dữ liệu. Người quản lý duyệt danh sách cá nhân hóa vẫn là yêu cầu riêng.
- **U:** Model, framework, multi-agent, semantic search, SQL thật, chất lượng/độ trễ/giá vận hành HubHome. Kết quả rỗng không chứng minh kho rỗng hoặc thị trường không có phòng.

### HH-03 — Chi phí trước quyết định thuê

- **C, 04/10/2026:** Cẩm nang tách tiền vào ở và khoản định kỳ; guide AI nói phí thiếu ghi cần xác minh. Nguồn: [cẩm nang S09](https://hubhome.vn/cam-nang/ngan-sach-that), [S04](https://hubhome.vn/help/tro-ly-ai). Ví dụ/tỷ lệ không thành phí hoặc ngưỡng mặc định HomeMatch.
- **H, 01/10/2026:** A4 yêu cầu tính giả lập nhưng nhận tìm rỗng. S11 tính độc lập 3.250.000 đồng/tháng, 5.500.000 đồng ban đầu; không phải đáp án HubHome. Nguồn: S11, phần 3.1; không suy website thiếu công cụ ở luồng khác.
- **D — HomeMatch:** Engine xác định tính thuê/cọc/trả trước/điện nước/xe/mạng/dịch vụ/phí một lần. Tách ước tính trước thuê với hóa đơn thực tế. Giữ scenario, đơn vị, khoản bao gồm và unknown; thiếu phí không thành 0. Cọc có đối chiếu riêng, không coi là chi phí tiêu dùng tháng.
- **U:** Độ đúng engine, biểu phí hoặc hoàn trả cọc HubHome chưa kiểm chứng.

### HH-04 — So sánh, bản đồ và vị trí

- **C, 04/10/2026:** Landing nói lưu/so sánh tối đa 3; FAQ nói vị trí công khai có thể gần đúng, địa chỉ chi tiết xác nhận khi đặt lịch. Nguồn: [S01](https://hubhome.vn/), [S03](https://hubhome.vn/faq). Chưa thử bảng/ghim có dữ liệu.
- **H, 01/10/2026:** Workspace có map/lưới/danh sách/lưu/so sánh; không có thẻ và nút 0 căn vô hiệu hóa. Nguồn: S11, phần 3.1.
- **D — HomeMatch:** So sánh tối đa 3 theo cùng nguồn: thuê/tổng tháng/vào ở/diện tích/tiện ích/nội quy/thiếu. Map thuộc sản phẩm, ghi nguồn/độ chính xác/loại khoảng cách. Tâm quận không chứng minh đạt bán kính cứng. Giá/tình trạng đổi phải đánh dấu và kiểm tra lại lựa chọn.
- **U:** Geocoding, đường đi, thời gian di chuyển và đồng bộ thẻ/ghim HubHome.

### HH-05 — Tài khoản, hồ sơ, lịch sử và yêu thích

- **O, 04/10/2026:** Popup lịch sử công khai ghi lưu trên máy và cần bật ghi nhớ. Nguồn: [S02](https://hubhome.vn/tro-ly-ai); không sửa ghi nhớ hoặc tạo chat.
- **C, 04/10/2026:** FAQ nói đăng nhập để yêu thích đồng bộ thiết bị. Nguồn: [S03](https://hubhome.vn/faq); chưa thử đồng bộ/xóa hoặc lời cam kết không lưu server.
- **H, 01/10/2026:** Đã mở hồ sơ/nhu cầu/lưu/xem/thông báo, phần chính trống. Chat mẫu hiện ở lịch sử nhưng bộ đếm/hồ sơ chưa đổi. Nguồn: S11, phần 3.2/3.4; chưa đủ cơ sở kết luận lỗi.
- **D — HomeMatch:** Tách lịch sử chat, hồ sơ xác nhận, yêu thích, phòng đã xem, phản hồi và cache; định nghĩa nguồn chuẩn/quyền/consent/thời hạn/xem-sửa-xóa. Tin hết/bị gỡ vẫn có trạng thái trong mục đã lưu, không bị đổi thành phòng khác.
- **U:** Lưu server/cục bộ, memory, thu hồi phiên, đổi máy và quyền dữ liệu thực tế HubHome.

### HH-06 — Lịch xem, trực tuyến và người thật

- **C, 04/10/2026:** FAQ tách thời gian mong muốn với lịch bên phụ trách xác nhận. Guide video mô tả link khi chủ nhà bật phòng gọi, phản hồi sau xem. Nguồn: [S03](https://hubhome.vn/faq), [S09](https://hubhome.vn/help/phong-xem-truc-tuyen); chưa gửi/gọi.
- **H, 01/10/2026:** Lịch/video trống. B1 live chat tạo câu mẫu vào AI, chưa thấy kết nối người thật. Nguồn: S11, phần 3.1–3.2; không suy không có nhân sự.
- **D — HomeMatch:** Yêu cầu → chờ → xác nhận/từ chối/đề xuất giờ → hoàn tất/hủy/vắng mặt; lưu người xử lý/lịch sử. Chuyển người thật có người nhận và trạng thái tiếp nhận. V1 hỗ trợ ảnh/media hoặc link tour hợp lệ; tích hợp gọi video trực tiếp là mở rộng, chỉ bật khi kiểm soát người tham gia/thiết bị/link và có bằng chứng riêng.
- **U:** Live chat, thông báo, video, quyền phòng gọi và chuyển trạng thái HubHome.

### HH-07 — Chủ nhà, danh mục và nguồn cung

- **O, 04/10/2026:** Login owner có email/mật khẩu/đăng ký/quên mật khẩu và mô tả thay đổi tin/giá/tiền chờ duyệt. Nguồn: [S06](https://hubhome.vn/owner/login); không xác thực.
- **C, 04/10/2026:** Guide tin nêu dữ liệu có cấu trúc, nháp/chờ duyệt/xuất bản/từ chối/hết/lưu trữ. Guide cổng nêu 19 module/7 nhóm và dấu gạch khi thiếu bảng. Nguồn: [S06](https://hubhome.vn/help/dang-va-quan-ly-tin), [S05](https://hubhome.vn/help/cong-chu-nha); chưa kiểm thử các module.
- **H, 01/10/2026:** Phiên người thuê bị chặn quản lý tin; chỉ đọc giới thiệu/form demo. Nguồn: S11, phần 3.5.
- **D — HomeMatch:** Cổng owner và quản lý nguồn là phạm vi chính. Tách chủ thể/tòa nhà/phòng thực/tin, quyền quản lý và version. Owner tạo/cập nhật; quản lý kiểm tra/xuất bản; người thuê dùng tin hợp lệ hiện tại. Duyệt tin khác duyệt danh sách cá nhân. 0, không dữ liệu và chưa kết nối hiển thị khác nhau.
- **U:** Quyền sở hữu, lượng còn phòng, chống trùng, kiểm duyệt server, thống kê owner HubHome.

### HH-08 — Hợp đồng và bàn giao

- **C, 04/10/2026:** Guide nêu mẫu nháp, góp ý, SmartCA/hai bên và nhắc sau ký. Nguồn: [S07](https://hubhome.vn/help/hop-dong-va-ky-so); chưa xác minh tích hợp/chứng thư/giá trị pháp lý/nhắc.
- **H, 01/10/2026:** Hợp đồng trống, mô tả nháp → thuê điền → chốt sau xem/đặt; hồ sơ nói không chữ ký pháp lý. Nguồn: S11, phần 3.3–3.4; khác ngày/trang, chưa biết đổi phiên bản hay phạm vi.
- **D — HomeMatch:** Hợp đồng đúng phòng/hai bên/giá-phí-cọc/hiệu lực/kỳ trả/nội quy/gia hạn-kết thúc, biên bản bàn giao. Nháp có version; xác nhận đúng bản; sửa sau chốt có phụ lục/dấu vết. Đính kèm bản ký ngoài hệ thống là phương thức có thể nghiệm thu. Ký số là tích hợp chỉ công bố khi điều kiện/nhà cung cấp/bằng chứng đủ.
- **U:** Không kết luận HubHome ký số production hoặc hợp đồng trong ứng dụng tự có hiệu lực pháp lý.

### HH-09 — Hóa đơn, ghi nhận tiền và công nợ

- **C, 04/10/2026:** Guide nêu kỳ phải thu/đã thu/còn lại, trạng thái theo tiền+hạn và khối chờ đối soát khi thiếu bảng bank. FAQ nói prototype không nhận thanh toán/giữ cọc/xác nhận giao dịch. Nguồn: [S08](https://hubhome.vn/help/thu-tien-cong-no), [S03](https://hubhome.vn/faq); theo dõi nợ không chứng minh nhận/chuyển tiền.
- **H, 01/10/2026:** Hóa đơn trống; mô tả sổ đối chiếu thuê đã chuyển/owner đã nhận, không gateway. Nguồn: S11, phần 3.3.
- **D — HomeMatch:** Hóa đơn theo hợp đồng/kỳ/dòng phí/snapshot giá; phát hành đúng thuê; trả một phần/toàn bộ, đối chiếu. Tách báo đã chuyển, xác nhận đã nhận, giao dịch cổng. Điều chỉnh/đảo thay xóa lịch sử; số dư xác định. Đối soát thủ công kiểm chứng đủ cho nghiệp vụ; gateway/bank sync cần nghiệm thu riêng.
- **U:** Giao dịch, ngân hàng, hoàn tiền/thanh toán trực tuyến HubHome.

### HH-10 — Công tơ và phí sử dụng

- **H, 01/10/2026:** Trang chi phí nêu điện/nước/mạng/xe/quản lý, công tơ hoặc khoán người, chỉ số đầu/cuối/giá/ảnh; lúc đó nói mô hình chốt chưa hoàn thiện. Nguồn: S11, phần 3.3. **Không đổi thành quan sát 04/10.**
- **C, 04/10/2026:** Cẩm nang phân biệt đơn vị điện/nước/xe/mạng/dịch vụ. Nguồn: [S09](https://hubhome.vn/cam-nang/ngan-sach-that); không chứng minh module chốt.
- **D — HomeMatch:** Công tơ gắn phòng/hợp đồng, kỳ/số/ảnh/người ghi-xác nhận; kiểm tra âm/đảo/trùng/thiếu/thay công tơ, giá theo hiệu lực. Khoán người/xe/cố định có thời gian áp dụng. Chốt tạo dòng hóa đơn truy nguồn; sửa kỳ phát hành tạo điều chỉnh. Không dùng ước tính làm số đo thật.
- **U:** Chưa kiểm tra lại trang đăng nhập hoặc ca chốt số HubHome.

### HH-11 — Sửa chữa sau thuê

- **H, 01/10/2026:** Trang sửa chữa nêu yêu cầu/ảnh/tiến độ/lịch thợ/hợp đồng hoạt động, chưa có dữ liệu thử. Nguồn: S11, phần 3.3; mô tả không thành luồng vận hành.
- **U, 04/10/2026:** Đợt công khai không có ca sửa chữa hiện tại. Không xuất hiện trên landing không có nghĩa chức năng bị bỏ.
- **D — HomeMatch:** Thuê lập yêu cầu đúng phòng, ảnh/mô tả; owner/nhân sự tiếp nhận/phân công/hẹn/xử lý/chờ xác nhận/đóng/mở lại. Có mức khẩn/trách nhiệm/lịch sử/phí đã xác nhận, liên kết hóa đơn khi có. Không suy thuê chịu phí từ ảnh/chat. Sau hợp đồng vẫn giữ hồ sơ và quyền phù hợp chính sách.
- **U:** Phân công thợ/thông báo/phí/kết quả thực tế HubHome.

### HH-12 — Riêng tư, xác minh và tin cậy

- **O/C, 04/10/2026:** Privacy là dự thảo 16/07/2026, cần pháp nhân/đầu mối/thời hạn/nhà cung cấp/rà soát trước production. FAQ gọi kiểm duyệt dự kiến và quyền khách cần server/RLS. Nguồn: [S10](https://hubhome.vn/legal/privacy), [S03](https://hubhome.vn/faq); không là chứng nhận tuân thủ/RLS.
- **H, 01/10/2026:** Hồ sơ nói đồng bộ/quyền/cache; chưa thử truy cập trái quyền/xóa. Nguồn: S11, phần 3.4.
- **D — HomeMatch:** Quyền theo vai trò/bản ghi cho thuê/owner/nhân sự; consent memory, chia sẻ liên hệ/vị trí, retention/xóa/báo cáo/audit. Thuộc tính/phí/tình trạng có nguồn và thời điểm. Độ đầy đủ/cũ/mâu thuẫn không thành kết luận gian lận/chứng nhận pháp lý.
- **U:** Quyền thực, mã hóa, nơi lưu, nhà cung cấp, retention/xóa/consent và xử lý sự cố HubHome.

## 4. Mô tả chưa thống nhất

| Điểm | Bằng chứng/ngày | Xử lý trong HomeMatch |
|---|---|---|
| Ký số/prototype | S07 04/10 nói SmartCA; H 01/10 nói không chữ ký pháp lý; S10 04/10 vẫn dự thảo | Không kết luận tích hợp hoạt động. Chốt phương thức/giá trị tài liệu bằng bằng chứng riêng |
| Lịch sử/memory | S02 04/10 nói trên máy; FAQ nói yêu thích đồng bộ; H có bộ đếm/hồ sơ riêng | Định nghĩa từng lớp và nguồn chuẩn |
| Tin kiểm duyệt | S01 nói kiểm duyệt; S03 04/10 nói quy trình dự kiến | Xuất bản cần quyết định server có dấu vết |
| Thu tiền/thanh toán | S08 nói đã thu; S03 không nhận tiền/giữ cọc | Tách hóa đơn/báo trả/xác nhận/gateway |
| Kho và 0 kết quả | S04 04/10 nói kho thật; query H 01/10 trả 0 | Không suy nguồn cung từ marketing/một phiên; catalog HomeMatch có nguồn và ca có kết quả/rỗng |

Có thể nội dung khác phiên bản/vai trò/phạm vi; chưa xác minh nguyên nhân. Không chọn lời mô tả thuận lợi nhất làm sự thật.

## 5. Hành trình hoàn chỉnh HomeMatch

Phần này là **D — thiết kế HomeMatch**, không mô tả backend HubHome. Chia đợt là thứ tự triển khai; chỉ gọi hoàn thiện khi nghiệp vụ đã chọn có luồng thực, quyền, ngoại lệ và bằng chứng.

~~~text
Owner tạo/cập nhật phòng → quản lý duyệt tin → catalog có phiên bản
                                            ↓
Thuê chat/lọc → hỏi rõ/xác nhận → matching + chi phí → quản lý duyệt danh sách
                                            ↓
Xem/lưu/so sánh/bản đồ → yêu cầu xem → đầu mối xác nhận → phản hồi sau xem
                                            ↓
                       nháp/chốt hợp đồng → bàn giao
                                            ↓
Công tơ/phí kỳ → hóa đơn → ghi nhận/đối chiếu tiền ↔ sửa chữa
                                            ↓
               gia hạn hoặc kết thúc → bàn giao/cọc/đóng dư
~~~

Không nối tắt gửi lịch thành đã thuê, AI gợi ý thành đã duyệt, báo chuyển thành đã nhận hoặc nhấn đồng ý thành ký pháp lý. Mỗi chuyển cần điều kiện, actor, phiên bản và dấu vết.

| Nhóm mục tiêu | Mã | Nghiệp vụ trong đặc tả sản phẩm |
|---|---|---|
| Khám phá/lựa chọn | HH-01–HH-05 | Landing, AI/bộ lọc/tiêu chí, catalog/chi tiết, chi phí/so sánh/map, tài khoản/hồ sơ/lưu/xem/lịch sử |
| Xem/bàn giao người thật | HH-06, HH-12 | Yêu cầu/xác nhận/đổi/hủy, người xử lý, trực tiếp/trực tuyến theo khả năng thực, phản hồi |
| Nguồn cung | HH-07, HH-12 | Owner, phòng/tin, giá/phí/tình trạng, kiểm duyệt/quyền |
| Bắt đầu/kết thúc thuê | HH-08, HH-03 | Hợp đồng version/xác nhận/đính kèm, bàn giao/cọc/gia hạn/kết thúc/dư nợ |
| Thu phí/phục vụ | HH-09–HH-11 | Công tơ/phí/hóa đơn/đối chiếu/công nợ/sửa chữa/lịch sử |
| Chất lượng/vận hành | HH-12 xuyên suốt | Quyền/consent/nguồn/audit/khôi phục/thông báo/trợ giúp/xử lý sự cố |

Video-call, ký số pháp lý, gateway và bank sync là mở rộng cần gate riêng. In-app và email giao dịch là bắt buộc v1; provider/delivery phải được nghiệm thu. Hợp đồng/hóa đơn/công tơ/sửa chữa vẫn nằm trong sản phẩm dù tích hợp nâng cao chưa sẵn sàng; ghi nhận tài liệu/chấp thuận và đối soát thủ công phải hoạt động, không chỉ là trang trống.

## 6. Quy tắc dữ liệu và kiểm chứng

Các quy tắc là D nhằm chuyển nghiên cứu thành yêu cầu:

1. **Định danh:** Phòng thực khác tin; cùng phòng ở nhiều nguồn không thành nhiều lựa chọn. Hợp đồng/công tơ/hóa đơn/sự cố gắn đúng phòng/quyền.
2. **Nguồn/độ mới:** Giá/phí/tiện ích/nội quy/tình trạng/tọa độ có nguồn/ngày/độ chính xác; unknown khác 0/false. Thay đổi ảnh hưởng danh sách duyệt cần kiểm tra lại.
3. **Tiền xác định:** Scenario ước tính khác phát sinh hợp đồng/số đo. Dòng hóa đơn truy kỳ/giá/input; cọc/thuê/trả trước/phí không tính lặp.
4. **Quyền/version:** Server kiểm quyền bản ghi cả URL/file/cập nhật. Đúng actor xác nhận đúng bản; retry không nhân đôi lịch/hóa đơn/khoản thu.
5. **Liên tục:** Nghiệm thu từ owner đưa phòng tới thuê chọn/xem/thuê, một kỳ công tơ-hóa đơn-đối chiếu, một sự cố và kết thúc/gia hạn; reload/restart dữ liệu đúng.
6. **Trạng thái:** Không dữ liệu, không khớp, thiếu tiêu chí/bằng chứng, lỗi AI/dịch vụ, chờ duyệt và chưa kết nối khác nhau, có bước tiếp.
7. **Riêng tư:** Không ghi nhớ khớp DB/log/checkpoint/cache; retention nói đúng cấu hình vận hành. Không đưa dữ liệu/tài chính thật vào giả lập/công bố.
8. **Bằng chứng:** HubHome truy vết lý do cần chức năng; mã/kiểm thử/demo/browser/quyền/hướng dẫn vận hành HomeMatch mới chứng minh đã làm.

## 7. Nghiên cứu tiếp và giới hạn

| Khoảng trống | Xác minh phù hợp |
|---|---|
| Chi tiết/so sánh/map có dữ liệu | Phòng demo hoặc nguồn được phép; không đoán URL, tự đăng tin thật hoặc suy nguồn cung từ marketing |
| Owner/hợp đồng/hóa đơn/công tơ/sửa chữa | Phiên/demo được phép, dữ liệu thử; public không đủ |
| Routing/chi phí AI hiện tại | Ca giả lập tách ý định nếu được khảo sát tiếp; ghi kết quả từng ca, không gửi tài chính thật |
| Người thật/video/ký/thanh toán | Quyền/môi trường thử; không liên hệ/ký/giao dịch chỉ để tăng bằng chứng |
| Quyền/lưu trữ/nguồn | Audit hoặc API/DB được phép; UI/policy không thay bằng chứng kỹ thuật |
| Quyền lấy dữ liệu | Giấy phép/điều khoản/nguồn được phép; public không tự cho quyền export/crawl/tái sử dụng |

Tài liệu không kết luận HubHome không có dữ liệu/AI, có lỗi backend hoặc đã đạt production. Mục tiêu là HomeMatch đủ hành trình đã chọn và có bằng chứng riêng. Theo dõi phạm vi ở [kế hoạch sản phẩm](ke-hoach-kltn-homematch.md), [kế hoạch triển khai](ke-hoach-trien-khai.md). S11 được giữ như hồ sơ lịch sử.
