# Dữ liệu tổng hợp HomeMatch

**Phạm vi 05/10/2026:** dữ liệu hiện hành là **dataset v2** (`homematch-synthetic-v2`), mô tả ở [PLAN](PLAN.md). Các mục bên dưới đã cập nhật theo v2. `fixtures/v1` (hợp đồng, hóa đơn, công tơ, sửa chữa) thuộc phạm vi cũ 04/10, ngoài đề tài, giữ lại nhưng không dùng.

Kho này do dự án tự tạo, **không phải dữ liệu xuất từ HubHome, phòng thật hoặc biểu giá thị trường**. Chỉ dùng để phát triển và thử nghiệm KLTN. Tọa độ là fixture, không định danh địa chỉ thật; không có tài chính hay liên hệ khách thật.

- `catalog/rooms.json`: 220 căn, revision 1. TP.HCM 120 (80 phòng v1 giữ nguyên ID, cộng 40 studio/căn hộ ở Gò Vấp, Thủ Đức, Quận 7, Bình Thạnh). Hà Nội 100 (phòng/studio/căn hộ ở Cầu Giấy, Đống Đa, Hai Bà Trưng, Thanh Xuân, Nam Từ Liêm, Hoàng Mai). Căn hộ có `bedrooms`; căn v2 có `features_text`. Có các ca phí, tiện ích, sức chứa, tình trạng, số phòng ngủ chưa biết. Tiện ích dùng từ điển 9 mã (tham chiếu bộ lọc HubHome): `window, quiet, parking, private_bathroom, air_conditioning, washing_machine, balcony, furniture, pets_allowed`; giá thuê theo loại (phòng 1,8–5,5 triệu; studio 4,2–8,5; căn hộ 1PN 7,5–13; 2PN 10,5–19) để có nhóm vượt trần và các ca biên. Mở rộng này làm trước freeze; mọi thay đổi sau freeze phải là version dataset mới.
- `catalog/pilot.json`: 25 phòng thử ban đầu, gồm ca sai số khoảng cách.
- `catalog/metadata.json`: provenance và mô tả đặc tính có bằng chứng.
- `catalog/alias_fixtures.json`: hai alias cùng một phòng; alias không tăng số phòng eligible.
- `catalog/source_register.json`: nguồn, tỷ lệ tổng hợp và phạm vi sử dụng.
- `profiles/{dev,test}/profiles.jsonl`: 45 hồ sơ gốc, 15 dev/30 test (30 hồ sơ v1 + 15 hồ sơ v2: Hà Nội, căn hộ, alias khu vực, thu nhập, vay); paraphrase giữ cùng group/split.
- `oracles/cost_cases.json`: 22 ca tính tay độc lập: 15 ca chi phí `C01`–`C15` và 7 ca khả năng chi trả/vay `L01`–`L07`. Mỗi ca có số học và hằng số kỳ vọng; cần người kiểm tra chéo trước khi dùng cho nghiên cứu.
- `manifests/development_manifest.json`: hash đầu vào; `frozen=false`. G4 là tên guard lịch sử trong CLI hiện có; protocol/freeze nghiên cứu mới phải đối chiếu P5, không suy sản phẩm v1 đã đạt P4.
- `fixtures/v1/`: fixture packs vận hành soạn 05/10/2026 cho HM-01 (identity/access matrix 28 ca allow/deny), HM-02 (listing lifecycle: 7 listings/9 versions, draft→published→changes_requested→suspended→archived, stale review, alias dedup), HM-07 (9 contracts/12 versions/14 acceptances, 5 tenancies, sổ cọc), HM-08 (7 meters/26 readings/8 tariffs/9 invoices + oracle độc lập 10 ca BILL, 8 ca đối soát), HM-09 (4 tickets, 5 cost events). Toàn bộ `synthetic=true`, không credential thật. Chi tiết bố cục và hợp đồng dữ liệu xem [fixtures/v1/README.md](fixtures/v1/README.md).

## Lệnh

Từ root repository, không gọi provider:

```bash
.venv/bin/python -m eval validate
.venv/bin/python data/validate_fixtures.py
.venv/bin/python -m data.generate --output .local/regenerated-data
```

Generator có seed `20261001` (phòng v1) và `20261005` (căn v2). Không ghi đè dataset đã freeze; tạo version/output mới. Bộ gold extraction là các tình huống tổng hợp được soạn trước, chưa được kiểm chứng bằng người dùng thật. Nhãn relevance phòng vẫn để trống để người đánh giá chấm độc lập.

## Quy ước schema

Schema code ở `backend/app/models.py` là nguồn kiểm tra payload. `null` là chưa biết; `0` là biết bằng 0 và cần nguồn. Giá tiền nguyên VND; đơn giá phí dùng Decimal dưới dạng string JSON. Mỗi fee có tên, mode `fixed/person/vehicle/kwh/m3`, source và cờ included. `published` là duyệt tin; approval của recommendation là bước riêng. `available=null` cần xác minh.

`Profile` chứa form đã xác nhận, tách khỏi `Extraction` và tiền được nhắc trong chat. Location có accuracy và uncertainty; không suy diễn thời gian di chuyển. `soft_description` chỉ chứa ưu tiên mềm; loại tiền/liên hệ trước embedding.

Import kho bằng CLI backend là merge có kiểm revision; không tự xóa ID bị bỏ khỏi JSON. Dùng DB mới để tái tạo đúng 220 căn của dataset v2, thay vì trộn với kho demo hoặc kho v1 cũ.
