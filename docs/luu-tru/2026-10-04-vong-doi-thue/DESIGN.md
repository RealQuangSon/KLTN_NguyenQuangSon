# HomeMatch — hướng thiết kế sản phẩm hoàn chỉnh

**Cập nhật 04/10/2026.** HomeMatch phục vụ toàn bộ hành trình thuê: tìm chỗ ở → xem và lựa chọn → lập hợp đồng và bàn giao → sử dụng, thanh toán, sửa chữa → kết thúc thuê. Hướng thiết kế kế thừa nghiên cứu HubHome, giữ nhận diện HomeMatch và các kiểm soát riêng về gợi ý AI, chi phí và quyền. Đây là **chuẩn mục tiêu**, không phải tuyên bố source hiện tại đã hoàn thiện.

Đọc cùng [đặc tả sản phẩm](docs/dac-ta-san-pham.md), [yêu cầu sản phẩm](docs/yeu-cau-san-pham.md), [quy trình nghiệp vụ](docs/quy-trinh-nghiep-vu.md), [UI_SPEC](frontend/UI_SPEC.md) và [kế hoạch frontend](frontend/PLAN.md).

## 1. Cơ sở và mức bằng chứng

| Cơ sở | Điều được dùng | Điều chưa được chứng minh |
|---|---|---|
| [Nghiên cứu công khai HubHome 04/10/2026](docs/nghien-cuu-hubhome.md) | HH-01…HH-12: UI công khai và mô tả trợ lý, owner portal, hợp đồng/thu tiền; truy vết yêu cầu riêng HomeMatch | Kiến trúc nội bộ, chất lượng AI, số nguồn cung và khả năng vận hành thực tế |
| [Khảo sát đăng nhập 01/10/2026](docs/khao-sat-hubhome-da-dang-nhap.md) | Cách tổ chức người thuê: tổng quan, nhu cầu, tin lưu, đã xem, lịch, hợp đồng, hóa đơn, chi phí và sửa chữa | Phần lớn màn trống; chưa thử hợp đồng, công tơ, đối chiếu tiền hoặc sửa chữa có dữ liệu; chưa vào dashboard chủ nhà |
| Đo giao diện công khai 02/10/2026, ghi tại UI_SPEC | Landing giữa trang, composer, rail, chat–preview, bảng token | Không phải đo toàn site; chưa có baseline card/compare có dữ liệu hoặc owner dashboard |
| Source HomeMatch hiện tại | Landing/login, hai workspace renter/manager, chat/profile/confirm/HITL/results/compare/catalog status/viewing | Chưa có portal owner/admin, map/media, lịch sử tài khoản, lưu tin hoặc nghiệp vụ sau thuê |

Các màn bổ sung là thiết kế HomeMatch rút ra từ nhu cầu toàn vòng đời thuê. Không dùng nội dung tự công bố của HubHome làm bằng chứng tính năng đã vận hành. [Preview độc lập](frontend/design/hubhome-preview.html) chỉ minh họa bố cục lịch sử; không đại diện cho toàn sản phẩm và không là bằng chứng tích hợp API.

## 2. Nguyên tắc sản phẩm

1. **Một hành trình liên tục.** Người thuê chuyển giữa tìm phòng và đang thuê trong cùng tài khoản; lịch, hồ sơ, hợp đồng và yêu cầu được nối theo đúng quan hệ dữ liệu.
2. **Hai cách tìm.** Tìm kiếm trực tiếp dùng tin đã kiểm duyệt; trợ lý cá nhân hóa dùng hồ sơ đã xác nhận và danh sách được quản lý duyệt. Trình bày rõ nguồn kết quả, không nhập hai loại duyệt làm một.
3. **Hành động có trạng thái thật.** Yêu cầu lịch chưa phải lịch xác nhận; báo đã chuyển tiền chưa phải đã nhận; hợp đồng được chấp thuận chưa phải đã nhận phòng. Sau thao tác phải thấy trạng thái từ server và bước tiếp theo.
4. **Số tiền có ngữ cảnh.** Tiền thuê, tổng tháng ước tính, tiền ban đầu và số tiền hóa đơn là các khái niệm riêng. Luôn giữ khoản chưa biết, kỳ tính, đơn vị, nguồn và giả định.
5. **Quyền theo công việc.** Renter, owner, manager và admin có shell phù hợp; chuyển vai trò không cấp thêm quyền. Không lộ nháp AI, hồ sơ thuê hoặc thông tin thanh toán cho người không liên quan.
6. **Dữ liệu đáng tin cậy.** Media có quyền sử dụng, vị trí có mức chính xác, giá có thời điểm và revision; màn cũ phải biết dữ liệu đã thay đổi.
7. **Có thể sử dụng trên điện thoại và bàn phím.** Các thao tác quan trọng không phụ thuộc hover, kéo thả, màu hoặc bản đồ.

## 3. Hệ giao diện và bố cục

| Màn | Bố cục mục tiêu | Việc chính |
|---|---|---|
| Trang chủ/cẩm nang | Header nhẹ, tiêu đề giữa, composer khoảng 720px, Tìm nhanh và câu mẫu, nội dung/footer | Bắt đầu tìm hoặc đăng tin; hiểu quy trình và chi phí |
| Trợ lý AI | Desktop rail 60px + chat/preview 35/65; drawer nhu cầu; mobile tab chat/kết quả | Hỏi rõ, xác nhận hồ sơ, theo dõi duyệt, xem kết quả |
| Khám phá phòng | Bộ lọc, danh sách/lưới và bản đồ đồng bộ; detail có gallery và chi phí | Tự tìm tin đã kiểm duyệt, lưu, so sánh, đề xuất lịch |
| Người thuê | Sidebar có nhãn khoảng 220px, tổng quan có việc cần làm; nhóm Tìm chỗ ở/Đang thuê/Tài khoản | Nhu cầu, tìm kiếm đã lưu, lịch sử, lịch, giữ phòng, hợp đồng, hóa đơn, công tơ, sửa chữa |
| Chủ nhà | Sidebar, overview, bảng/danh sách, editor và panel chi tiết | Nhà/phòng/media, lịch, hợp đồng, vận hành và đối chiếu |
| Quản lý | Hàng đợi và chi tiết, bảng có bộ lọc, dòng thời gian quyết định | Moderation, HITL, lịch và vận hành được phân công |
| Quản trị | Bảng, tìm kiếm và chi tiết có log/permission | Tài khoản, phân công, báo cáo, bảo vệ dữ liệu và vận hành |

Dùng cùng token, nhưng mật độ bảng chủ nhà/quản lý/quản trị cao hơn người thuê. Mỗi menu phải có dữ liệu hoặc empty state với hành động phù hợp; phần đã có API mới được bật ở bản triển khai tương ứng. Các màn còn chờ backend phải có kế hoạch và tiêu chí nghiệm thu, không dùng số liệu minh họa như dữ liệu thật.

## 4. Token và tương tác

Các token mục tiêu giữ hướng đã chọn theo tham chiếu công khai: nền trang `#f8fafc`, surface `#ffffff`, tiêu đề `#0f172a`, body `#334155`, chữ phụ `#64748b`, border `#e2e8f0`, accent `#f97316`, accent chữ nhỏ/hover `#c2410c`, nền nhấn `#fff7ed`. Cam sáng dùng nhận diện; control/text phải chọn cặp màu đạt contrast trên component thực tế.

Font Inter local khi có tài sản hợp lệ; fallback hệ thống/Arial hỗ trợ tiếng Việt. Hero desktop 38/46px weight 800, mobile 28–32px; body 15–16/24px; input mobile ≥16px. Spacing 4/8/12/16/24/32/48/64; composer/card radius 16–18px; control 10–12px; chip pill; vùng chạm ≥44×44px. Bảng rộng cuộn trong container và có bản trình bày phù hợp màn hẹp.

Motion CSS 140–180ms ease-out, dịch 0–4px; ưu tiên giữ vị trí nội dung. `prefers-reduced-motion` bỏ chuyển động không cần thiết. Drawer/modal giữ focus, Escape đóng khi phù hợp, trả focus; form lỗi giữ nội dung và đưa focus tới trường cần sửa. Trạng thái loading/empty/error/stale/success có thông điệp và hành động riêng.

**Chênh lệch hiện tại:** source còn dùng cam đỏ `#c6543c`, nền ngà và landing hai cột. Việc viết lại tài liệu ngày 04/10 không thay source hay xác nhận hướng token mới đã triển khai.

## 5. Media, bản đồ và định dạng dữ liệu

- Tái dùng wrapper SVG `Icon`: lưới 24px, stroke 1,6px, nét bo, `currentColor`; mọi icon action có accessible name. `RoomIllustration` là minh họa gốc và phải được ghi là minh họa khi thay ảnh phòng.
- Ảnh phòng thật do owner/nguồn được phép cung cấp: có alt text, loading/error, thứ tự gallery và trạng thái moderation; không sao ảnh/logo/mascot hoặc kho tin HubHome.
- Bản đồ dùng tọa độ/độ chính xác từ API và nhà cung cấp đã chọn. Vị trí gần đúng có nhãn/vùng sai số; không suy ra địa chỉ chính xác hoặc khoảng cách đường đi. Danh sách vẫn sử dụng được khi map lỗi.
- Tour ảo có thể dùng gallery, video/tour link và lịch xem trực tuyến. Nền tảng video call riêng, voice/image AI, legal e-sign và cổng thanh toán là tích hợp tùy chọn, không thay các nghiệp vụ cốt lõi.
- Chi phí do backend tính bằng quy tắc xác định. Giao diện dùng DTO và tiền VND đã làm tròn; không tự rank, tính tổng hoặc quyết định publication.

## 6. Tiêu chuẩn nghiệm thu

[UI_SPEC](frontend/UI_SPEC.md) định nghĩa inventory màn/routes/trạng thái và UI-V01…UI-V16. [TEST_CHECKLIST](frontend/TEST_CHECKLIST.md) phân biệt bằng chứng cũ với checklist sản phẩm hoàn chỉnh. [DEMO_CHECKLIST](frontend/DEMO_CHECKLIST.md) có demo hiện có và demo toàn vòng đời cần triển khai.

Nghiệm thu cần ảnh cùng viewport/trạng thái, kiểm thử API/browser các vai trò, bàn phím/mobile, quyền và phản hồi cũ. Chỉ đối chiếu HubHome ở vùng có baseline phù hợp; phần chưa quan sát được ghi là thiết kế HomeMatch. Không dùng phần trăm “giống” hoặc fixture tests để chứng minh sản phẩm đã vận hành, và không đánh dấu toàn bộ frontend hoàn tất khi mới chạy luồng tìm phòng.
