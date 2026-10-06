# Bộ tài liệu sản phẩm HomeMatch

**Phiên bản định hướng:** sản phẩm v1 hoàn thiện. **Cập nhật:** 04/10/2026.

HomeMatch phục vụ toàn bộ hành trình thuê phòng: tìm chỗ ở, quyết định thuê và vận hành sau khi vào ở. Yêu cầu này thay thế giới hạn MVP trong các kế hoạch trước. Bộ tài liệu là đặc tả để phát triển; mã hiện tại vẫn là nền tảng local 0.3.0, chưa phải sản phẩm v1 đã nghiệm thu.

## Đọc theo mục đích

| Muốn biết | Tài liệu chính |
|---|---|
| Sản phẩm hoàn thiện gồm những gì | [Đặc tả sản phẩm](dac-ta-san-pham.md) |
| Chức năng bắt buộc, nguồn và mã yêu cầu | [Danh mục yêu cầu](yeu-cau-san-pham.md) |
| Vai trò, bàn giao, quy tắc và trạng thái | [Quy trình nghiệp vụ](quy-trinh-nghiep-vu.md) |
| Khi nào đủ điều kiện gọi là hoàn thiện | [Tiêu chí nghiệm thu](tieu-chi-nghiem-thu.md) |
| Nghiên cứu HubHome và giới hạn bằng chứng | [Nghiên cứu](nghien-cuu-hubhome.md), [khảo sát đăng nhập lịch sử](khao-sat-hubhome-da-dang-nhap.md) |
| Cấu trúc hệ thống cần xây | [Kiến trúc sản phẩm](kien-truc-homematch.md), [thiết kế agent](thiet-ke-agent.md) |
| API đang chạy và API cần bổ sung | [Contract 0.3.0](api-contract.md), [thiết kế API v1](api-san-pham-v1.md) |
| Việc phải làm và thứ tự phụ thuộc | [Kế hoạch triển khai](ke-hoach-trien-khai.md), [phân công từng phần](ke-hoach-tung-phan.md), [plan chi tiết](ke-hoach-chi-tiet.md) |
| Mã hiện có và bằng chứng kiểm chứng | [Trạng thái](trang-thai-trien-khai.md), [kiến trúc local](kien-truc-trien-khai.md), [kiểm chứng backend](kiem-chung-backend.md) |
| Đóng góp và thực nghiệm khóa luận | [Đề cương KLTN](ke-hoach-kltn-homematch.md), [eval](../eval/PLAN.md) |
| Kết quả rà soát bộ docs mới | [Rà soát 04/10](ra-soat-tai-lieu.md) |

## Cách đọc trạng thái

- **Yêu cầu v1:** phải triển khai và nghiệm thu trước khi phát hành sản phẩm hoàn thiện.
- **Đã có nền tảng:** có mã tương ứng; chưa mặc định đã đáp ứng toàn bộ yêu cầu v1.
- **Bằng chứng lịch sử:** kết quả của phiên kiểm chứng có ngày, phạm vi và cấu hình; không phải kết quả vừa chạy lại.
- **Mở rộng:** không chặn v1, chỉ triển khai khi có nhu cầu cụ thể.

Mã `HM-01` đến `HM-10` định danh module. Mã `HM-xx-Rnn` định danh yêu cầu và `AC-HM-xx-nn` định danh ca nghiệm thu tương ứng. Nguồn `HH-01` đến `HH-12` là các mục nghiên cứu HubHome; các quy tắc riêng của HomeMatch phải ghi là đề xuất sản phẩm.

## Thứ tự ưu tiên khi tài liệu khác nhau

Đặc tả sản phẩm → danh mục yêu cầu → quy trình/tiêu chí nghiệm thu → kiến trúc/API v1 → plan từng phần. Với hành vi **đang chạy**, mã nguồn và contract 0.3.0 là nguồn đối chiếu. Các báo cáo khảo sát, kiểm chứng và manifest cũ giữ vai trò bằng chứng lịch sử, không quyết định phạm vi sản phẩm mới.

Thay đổi phạm vi phải sửa yêu cầu, quy trình, AC và các plan liên quan trong cùng đợt. Các mã AC01–AC16, T01–T15 và bộ 62 task MVP trước đây là định danh lịch sử; không dùng chúng để kết luận đã hoàn thành v1.
