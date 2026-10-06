# Khảo sát chức năng HubHome trong phiên đã đăng nhập

**Ngày khảo sát:** 01/10/2026. **Mục đích:** Xác minh các luồng thao tác để hoàn thiện kế hoạch KLTN trợ lý tìm phòng trọ. **Trạng thái:** Đã khảo sát nhóm trang người thuê, bốn truy vấn AI giả lập và điểm chặn đăng nhập chủ nhà; chưa kiểm thử toàn bộ website.

**Môi trường:** Chrome, cửa sổ profile `si`, tài khoản có tên hiển thị `si nas`. Chỉ ghi tên hiển thị để xác nhận đúng phiên; không đưa email, thông tin liên hệ, dữ liệu hồ sơ hoặc lịch sử cá nhân vào tài liệu.

**Phương pháp:** Thao tác giao diện và đọc trạng thái hiện ra. Phân biệt chức năng chỉ quan sát được, chức năng đã thử bằng dữ liệu giả lập, chức năng có quyền truy cập hạn chế và bước tạo dữ liệu/liên hệ chưa gửi. Không suy công nghệ backend từ giao diện.

## 1. Danh mục cần khảo sát

| Nhóm | Luồng cần xem | Trạng thái hiện tại |
|---|---|---|
| Trang chủ đăng nhập | Composer, câu hỏi mẫu, chế độ tìm, ảnh, giọng nói, vị trí, lịch sử | Đã thấy giao diện; chưa thử hết |
| Tài khoản | Menu, hồ sơ/thiết lập, khu vực người thuê | Menu thiết lập dẫn về hồ sơ người thuê; không sửa/lưu/đổi mật khẩu |
| AI hội thoại | Hỏi rõ, tìm, điều chỉnh, dữ liệu thiếu, lịch sử/ngữ cảnh | Đã thử bốn truy vấn với các mục đích khác nhau; xem phần 3.1 |
| Không gian kết quả | Bộ lọc, sắp xếp, thẻ phòng, bản đồ, preview | Đã dùng bộ lọc loại; xem workspace trống; chưa có thẻ phòng |
| Phòng cụ thể | Ảnh, thuộc tính, nguồn, phí, tin cậy, tiện ích, vị trí | Chưa có phòng để mở chi tiết |
| So sánh/yêu thích | Thêm/bỏ lựa chọn, bảng so sánh, căn đã lưu | Nút so sánh/lưu 0 căn bị vô hiệu hóa; chưa kiểm thử bảng |
| Tài chính thuê | Tiền vào ở, chi phí tháng, kịch bản và khoản chưa rõ | Chưa kiểm thử công cụ theo căn; đã đọc trang chi phí người đang thuê |
| Lịch xem | Form, lựa chọn thời gian, trạng thái và người xác nhận | Đã mở trang lịch trống; chưa tạo/xác nhận lịch |
| Người thuê | Hồ sơ, lịch sử, yêu thích, lịch xem, thông báo | Đã mở 11 trang sidebar, popup thông báo; xem chi tiết ở phần 3 |
| Chủ nhà | Tin, form đăng, khách quan tâm, lịch, duyệt thay đổi | Quản lý tin chuyển tới cổng yêu cầu đăng nhập chủ nhà; đã đọc trang giới thiệu và form demo |
| Người thật/hỗ trợ | Live chat, liên hệ, báo cáo, góp ý | Đã xem form liên hệ/báo cáo và chủ đề; live chat tạo câu mẫu vào AI; chưa thấy kết nối người thật; chưa gửi form |
| Nội dung hỗ trợ | Cẩm nang, help, FAQ, an toàn, chính sách | Đã có nghiên cứu công khai; khảo sát thêm luồng tương tác |

## 2. Quan sát đã có

- Trang chủ sau đăng nhập thay phần giới thiệu đầu trang bằng ô nhập nhu cầu và các câu hỏi mẫu.
- Có chọn chế độ tìm, thêm ảnh, giọng nói và vị trí. Chưa cấp quyền microphone/vị trí hoặc tải ảnh lên.
- Menu tài khoản có hồ sơ/thiết lập, khu vực người thuê và đăng xuất. Không thao tác đăng xuất.
- Điều khiển Chrome hiện dùng giao diện native vì browser connector chưa thấy profile `si`; cửa sổ có thể đổi khi người dùng thao tác ở profile khác. Đã phát hiện đúng cửa sổ qua menu Window và xác nhận tên tài khoản.
- Đã mở trang chủ đăng nhập, trợ lý AI và 11 trang trong không gian người thuê. Các thông tin tài khoản riêng không được chép vào tài liệu.
- Chưa gửi lịch xem, đặt phòng, hợp đồng, góp ý, báo cáo hoặc đăng tin. Nút live chat tự phát sinh một câu mẫu vào agent; chưa quan sát được bàn giao người thật. Bốn truy vấn AI mẫu đã gửi, tạo hai hội thoại thử xuất hiện trên giao diện; chưa kiểm tra lưu trữ/xóa phía server.
- Các thao tác bị ngắt hoặc chưa có trạng thái cuối không được tính là kiểm thử thành công. Chrome thường đổi sang profile khác giữa các bước, nên khảo sát toàn bộ chưa hoàn tất.

## 3. Kết quả theo luồng

### 3.1. Tìm nhanh và trợ lý AI

Mở **Tìm nhanh** hiện thành phố TP.HCM, quận tất cả, loại tất cả và ngân sách 2–10 triệu. Menu loại có phòng trọ, studio, căn hộ 1/2 phòng ngủ và ở ghép. Các nút tiện ích gồm máy lạnh, máy giặt, ban công, nội thất, gác lửng, thang máy, WC riêng và nuôi thú cưng.

Chọn **Phòng trọ** tự điền câu tìm phòng trọ TP.HCM, ngân sách 2–10 triệu/tháng. Nhấn **Tìm theo bộ lọc** chuyển sang workspace. Đây là hành vi đồng bộ bộ lọc với ô hội thoại đã quan sát; chưa chứng minh mọi điều kiện được thực thi đúng ở backend.

**Một ca thử đã xác nhận:** Truy vấn trên được nhận, xuất hiện trạng thái định tuyến rồi agent báo không tìm thấy tin phù hợp trong kho HubHome, đồng thời phân biệt kho này với toàn bộ thị trường. Có nút nới ngân sách, đổi khu vực, bỏ tiện ích và nhãn nguồn kho tin HubHome/truy vấn SQL. Preview không có phòng; bản đồ chờ; chip có loại phòng trọ và trần 10 triệu. Nút so sánh/lưu chưa hoạt động vì số phòng bằng 0.

Nhấn **Danh sách căn** không tạo danh sách hay điều hướng mới quan sát được. Không quy việc không đổi giao diện thành lỗi nếu nút chỉ chuyển tiêu điểm về preview đang trống.

Thao tác gửi câu hỏi tiếp theo bị gián đoạn do Chrome đổi cửa sổ, nhưng lần quan sát sau **đã xác nhận câu hỏi và phản hồi xuất hiện**. Vì vậy ca này được tính hoàn thành, thay cho trạng thái chưa xác minh trong ghi chép trung gian.

| Ca | Đầu vào / hành động | Kết quả quan sát |
|---|---|---|
| A1 — tìm có bộ lọc | Phòng trọ TP.HCM, 2–10 triệu/tháng | Không tìm thấy tin; preview trống; nhãn nguồn SQL |
| A2 — yêu cầu bỏ giới hạn | Xin tối đa 5 tin đang có; bỏ loại/khu vực/ngân sách; ghi rõ giả lập, không nhớ/đặt lịch/liên hệ | Vẫn không trả thẻ; workspace có các bộ lọc mọi thành phố/loại/giá; không chứng minh backend thực sự bỏ mọi điều kiện |
| A3 — hỏi rõ nhu cầu | Giả lập “3 triệu, gần trường, thoáng, 2 người”; yêu cầu hỏi rõ 1–2 thông tin trước tìm | Không hỏi tên trường hoặc phạm vi ngân sách; mặc định TP.HCM có thông báo giả định; trả kết quả rỗng; chip ≤3 triệu/gần trường |
| A4 — tính chi phí | Giả lập thuê 2,5 triệu, các khoản điện/nước/xe/dịch vụ, cọc/trả trước/chuyển đồ/mua đồ; chỉ yêu cầu tính, không tìm | Trả thông báo không có căn phù hợp và nguồn SQL; chưa trả phép tính tháng/ban đầu |
| B1 — nút live chat | Nhấn nút gặp người cho thuê thật | Tự gửi câu muốn gặp tư vấn vào agent; phản hồi vẫn không có căn; không có màn hình/kết quả kết nối người thật được xác nhận |

Đáp án tham chiếu số học cho A4: **3.250.000 đồng/tháng**, **5.500.000 đồng ban đầu** theo đúng các giả định đã nhập. Đây là kết quả kiểm tra của kế hoạch HomeMatch, không phải kết quả HubHome trả về. Không suy từ A4 rằng website không có công cụ tài chính ở một luồng khác.

**Không suy ra được:** Kho rỗng, website lỗi, SQL thực tế đúng, semantic search/multi-agent hoạt động hoặc ranking chính xác. Nhãn SQL là thông tin hiển thị, không phải kiểm tra server. Ngân sách mẫu không phải nhu cầu/tài chính thật của người dùng.

Workspace có chat, preview, dạng lưới/danh sách, splitter, toàn màn hình, bản đồ, cuộc trò chuyện mới, lịch sử, nhu cầu, lịch xem, đã xem, so sánh và lưu. Có nút đánh giá hữu ích/chưa hữu ích và live chat. Những nút chưa thao tác hoặc không có dữ liệu không được coi là đã kiểm thử.

**Lịch sử và cuộc trò chuyện mới:** Đã mở lịch sử; popup ghi chỉ lưu trên máy người dùng, có mục hiện đang mở, các phiên trước và nút xóa. Không mở hoặc xóa các hội thoại cá nhân trước khảo sát. Nút tạo cuộc trò chuyện mới đưa về màn hình nhập nhu cầu; đã dùng để tách A3/A4 khỏi A1/A2/B1. Các lượt mẫu còn hiện khi quay lại trợ lý trong cùng trình duyệt; chưa thử đổi máy hoặc xóa cache.

**Ảnh và thiết bị:** Nút thêm ảnh mở trình chọn tệp; đã hủy, không chọn/tải tệp. Vị trí và giọng nói chỉ thấy công tắc, chưa cấp quyền hoặc kiểm tra nhận dạng.

### 3.2. Người thuê trước khi thuê

| Trang đã mở | Nội dung hiện ra | Giới hạn xác minh |
|---|---|---|
| Tổng quan | Số phòng xem, tin lưu, lịch, phiên chat; nhu cầu; chế độ tìm/đang thuê | Ban đầu các bộ đếm 0; chưa kiểm tra cập nhật sau chat |
| Nhu cầu của tôi | Mô tả hồ sơ tự hình thành từ lời nói với AI; link cập nhật qua trợ lý | Trạng thái chưa ghi nhận; chưa kiểm tra trích xuất, sửa/xóa memory |
| Tin đã lưu | Thống kê lưu, mở chi tiết, đặt lịch, chưa đặt lịch; mô tả đồng bộ tài khoản | Trống; chưa kiểm tra lưu/bỏ lưu/đổi máy |
| Phòng đã xem | Thống kê đã xem, đặt lịch, cân nhắc, đã loại; mô tả ghi lại khi mở chi tiết | Trống; chưa kiểm tra chuyển trạng thái |
| Lịch xem phòng | Sắp tới, xác nhận, chờ xác nhận, kết thúc; đặt lịch qua AI | Trống; chưa tạo/xác nhận lịch |
| Xem trực tuyến | Mô tả chọn hình thức trực tuyến, phòng gọi riêng xuất hiện tới giờ hẹn | Trống; chưa thử gọi hoặc quyền thiết bị |

Nội dung hướng dẫn cho thấy luồng dự kiến chat → nhu cầu → xem/lưu/cân nhắc → lịch → người phụ trách xác nhận. **Chờ xác nhận** là trạng thái riêng; yêu cầu đã gửi chưa đồng nghĩa lịch đã chốt. Chưa kiểm thử chuyển trạng thái với dữ liệu thật.

### 3.3. Người thuê sau khi thuê

| Trang đã mở | Nội dung website tự mô tả | Mức kiểm thử |
|---|---|---|
| Hợp đồng | Nháp chủ nhà, phần người thuê điền, bản chốt; xuất hiện sau đi xem và đặt phòng | Trống; chưa thử soạn/chốt |
| Hóa đơn & thanh toán | Sổ đối chiếu chủ nhà đã nhận/người thuê đã chuyển; không có cổng thanh toán hoặc giữ tiền | Trống; chưa thử tạo hóa đơn/đối chiếu |
| Chi phí sử dụng | Điện, nước, internet, xe, quản lý và biểu đồ; website ghi chưa hoàn thiện mô hình chốt công tơ | Chỉ đọc thông báo; chưa có biểu đồ/số liệu |
| Sửa chữa | Yêu cầu kèm ảnh, tiến độ, lịch thợ, gắn hợp đồng đang hoạt động; website ghi chưa có dữ liệu | Chỉ đọc thông báo; chưa thử toàn luồng |

Dashboard nói các mục này chưa kích hoạt vì chưa có phòng thuê thật. Trang chi phí phân biệt tính theo công tơ và khoán đầu người, nhắc chỉ số đầu/cuối kỳ, đơn giá và ảnh chốt số. Đây là mô tả từ website; không chứng minh cấu trúc DB hoặc xử lý backend đã hoàn thành.

### 3.4. Hồ sơ, thông báo và riêng tư

Trang hồ sơ có tên, điện thoại, email đăng nhập, lưu thay đổi và đổi mật khẩu. Có mô tả đồng bộ đám mây, RLS/quyền theo tài khoản, bản lưu trình duyệt, không thanh toán và không tạo chữ ký pháp lý. Không nhập hoặc lưu dữ liệu, đổi mật khẩu, xóa tài khoản hoặc kiểm thử thu hồi phiên. Tuyên bố riêng tư trên UI chưa phải bằng chứng phân quyền server.

Popup thông báo đã mở/đóng, hiện không có việc cần xử lý. Chưa kiểm tra thông báo từ một sự kiện thật.

Sau A1/A2, quay lại hồ sơ vẫn thấy bộ đếm phiên chat 0 và trang nhu cầu vẫn trống. Popup lịch sử lại hiển thị cuộc trò chuyện thử và nói lưu cục bộ. Có thể đây là các lớp dữ liệu khác nhau; chưa đủ cơ sở kết luận mất dữ liệu hoặc lỗi đồng bộ. HomeMatch cần định nghĩa rõ session history, hồ sơ sở thích và đồng bộ tài khoản.

### 3.5. Khu vực chủ nhà

Đã mở `/owner/login`: trang đăng nhập email/mật khẩu, đăng ký, quên mật khẩu. Không nhập hoặc tạo tài khoản.

Mở liên kết quản lý tin `/owner/properties` được chuyển tới `/owner/v2?m=tin-bat-dong-san`. Trang yêu cầu đăng nhập để quản lý chỗ ở, có liên kết đăng nhập chủ nhà và quay lại trang chủ nhà. Phiên người thuê hiện tại **chưa mở được dữ liệu quản trị chủ nhà**. Website nhắc tài khoản Supabase; đây là nội dung giao diện, không phải kiểm tra công nghệ nội bộ.

Trang `/for-owners` giới thiệu tin có cấu trúc, khách quan tâm, lịch xem, trạng thái còn/hết/gửi duyệt; luồng tài khoản → thông tin → kiểm duyệt → nhận yêu cầu xem. Form gồm tên, điện thoại, email, loại bất động sản, số lượng, khu vực; trang ghi biểu mẫu demo chưa gửi dữ liệu. Chỉ đọc form, chưa gửi. Không dùng phần giới thiệu như bằng chứng dashboard đã vận hành.

### 3.6. Liên hệ, báo cáo và góp ý

Đã mở `/contact?topic=report`, chủ đề chọn sẵn báo cáo tin. Các trường gồm tên/email bắt buộc, điện thoại, chủ đề, URL liên quan và nội dung; có checkbox xác nhận không gửi mật khẩu/OTP/dữ liệu thanh toán. Menu chủ đề có câu hỏi chung, hỗ trợ tìm phòng, hỗ trợ chủ nhà, báo cáo tin. Không điền hoặc gửi, nên chưa xác minh tiếp nhận/định tuyến yêu cầu.

Nút góp ý hiện trên các trang; lần thao tác mở bị gián đoạn, chưa xác nhận form đã mở, không tính là đã khảo sát form. Các trang nội dung công khai trước đó xem trong tài liệu nghiên cứu riêng.

### 3.7. Giới hạn kết nối

Thử mở trang trợ giúp HubHome bằng trình duyệt tích hợp sau các lần Chrome gián đoạn đã bị xét duyệt tự động từ chối: kết nối đó mới, nằm ngoài phiên Chrome đã được người dùng chỉ định. Không có nội dung thu được từ lần mở này; không tiếp tục bằng đường vòng hoặc chuyển cookie. Phần khảo sát chưa hoàn tất được ghi rõ thay vì coi đợt public trước đó là kiểm thử chức năng đã đăng nhập.

## 4. Liên hệ với kế hoạch KLTN

Đối chiếu sau khảo sát với [kế hoạch HomeMatch](/Users/son/KLTN_NguyenQuangSon/docs/ke-hoach-kltn-homematch.md) và [nghiên cứu công khai](/Users/son/KLTN_NguyenQuangSon/docs/nghien-cuu-hubhome.md). Kết quả của phiên tài khoản này không đại diện cho mọi vai trò/tài khoản hoặc toàn bộ nguồn phòng.

| Bài học | Áp dụng cho HomeMatch |
|---|---|
| Bộ lọc có thể dẫn sang chat | Dùng chung schema tiêu chí; hiển thị và xác nhận thay đổi |
| Dashboard gắn nhu cầu/lưu/lịch | Tập trung hành trình trước khi thuê; lưu tin/lịch sử bổ sung khi còn thời gian |
| Kết quả rỗng cần bước tiếp | Tách không có tin phù hợp, dữ liệu thiếu, lỗi dịch vụ; không tự nới điều kiện cứng |
| Nguồn cùng câu trả lời | Bằng chứng theo từng phòng/thuộc tính; nhãn nguồn chung chưa đủ |
| Lịch cần người phụ trách phản hồi | Giữ yêu cầu/chờ/xác nhận/từ chối riêng và test quyền |
| Trang giới thiệu chưa có dữ liệu | Báo cáo phân biệt đã làm, đã kiểm thử và mở rộng |
| Vận hành thuê kéo theo nhiều nghiệp vụ | Hợp đồng, hóa đơn, công tơ, sửa chữa và video ngoài MVP |
| Cùng phản hồi tìm phòng xuất hiện với yêu cầu hỏi rõ/tính chi phí/live chat | Kiểm tra routing theo ý định và điều kiện tiền đề, không chỉ kiểm tra câu trả lời có nội dung |
| Lịch sử cục bộ và hồ sơ tài khoản có cách trình bày khác nhau | Định nghĩa riêng dữ liệu hội thoại, hồ sơ sở thích, cache và đồng bộ; kiểm thử từng lớp |

Giữ điểm riêng của đề tài: người quản lý duyệt danh sách cá nhân hóa trước khi người thuê nhận, engine tổng tháng/tiền vào ở có giả định, và thực nghiệm các phương pháp matching. Chưa có bằng chứng HubHome có cổng duyệt danh sách tương đương.

## 5. Phần cần khảo sát tiếp

1. Cần cửa sổ HubHome profile `si` ổn định trong thời gian thao tác. Connector hiện chỉ thấy profile khác; không chuyển cookie hoặc tự đăng nhập lại sang profile khác.
2. Hai truy vấn tìm phòng chưa có thẻ; cần nguồn phòng/demo hoặc một phòng được người dùng xác nhận để thử chi tiết, so sánh, bản đồ và tài chính. Không đoán URL hoặc tự đăng phòng mẫu lên hệ thống thật.
3. Lịch sử, nhu cầu và thiết lập đã xem; còn chuyển trạng thái lưu/cân nhắc/loại, đồng bộ, phản hồi đánh giá, bộ lọc/sắp xếp trên dữ liệu có kết quả và popup góp ý.
4. Người dùng cần tự đăng nhập khu vực chủ nhà nếu muốn khảo sát tiếp dashboard. Không yêu cầu gửi mật khẩu; không thể kiểm thử quyền/dữ liệu chủ nhà chỉ với trang giới thiệu.
5. Form liên hệ/báo cáo đã đọc; còn form lịch và kết nối live chat thật. Gửi cho người thật cần chỉ dẫn cụ thể của người dùng.
6. Hợp đồng, hóa đơn, sửa chữa và cuộc gọi cần phiên/demo có dữ liệu phù hợp để kiểm thử; trang trống không đủ.
