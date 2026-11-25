# Dữ liệu tổng hợp HomeMatch

Dữ liệu chính là **dataset v2** (`homematch-synthetic-v2`), mô tả bên dưới. Ngoài ra có **catalog demo riêng** gồm tin cào công khai từ Chợ Tốt bằng `python -m data.crawl_chotot`: lưu trên PostgreSQL, không nằm trong repository, nội dung đã che SĐT/email, cân bằng số tin giữa TP.HCM và Hà Nội. Catalog này chỉ để trình diễn, không dùng cho đánh giá.

Kho này do dự án tự tạo, **không phải phòng thật hoặc biểu giá thị trường**. Chỉ dùng để phát triển và thử nghiệm KLTN. Tọa độ là fixture, không định danh địa chỉ thật; không có tài chính hay liên hệ khách thật.

- `catalog/rooms.json`: 220 căn, revision 1. TP.HCM 120 (80 phòng v1 giữ nguyên ID, cộng 40 studio/căn hộ ở Gò Vấp, Thủ Đức, Quận 7, Bình Thạnh). Hà Nội 100 (phòng/studio/căn hộ ở Cầu Giấy, Đống Đa, Hai Bà Trưng, Thanh Xuân, Nam Từ Liêm, Hoàng Mai). Căn hộ có `bedrooms`; căn v2 có `features_text`. Có các ca phí, tiện ích, sức chứa, tình trạng, số phòng ngủ chưa biết. Tiện ích dùng từ điển 9 mã: `window, quiet, parking, private_bathroom, air_conditioning, washing_machine, balcony, furniture, pets_allowed`; giá thuê theo loại (phòng 1,8–5,5 triệu; studio 4,2–8,5; căn hộ 1PN 7,5–13; 2PN 10,5–19) để có nhóm vượt trần và các ca biên. Mở rộng này làm trước freeze; mọi thay đổi sau freeze phải là version dataset mới.
- `catalog/pilot.json`: 25 phòng thử ban đầu, gồm ca sai số khoảng cách.
- `catalog/metadata.json`: provenance và mô tả đặc tính có bằng chứng.
- `catalog/alias_fixtures.json`: hai alias cùng một phòng; alias không tăng số phòng eligible.
- `catalog/source_register.json`: nguồn, tỷ lệ tổng hợp và phạm vi sử dụng.
- `profiles/{dev,test}/profiles.jsonl`: 45 hồ sơ gốc, 15 dev/30 test (30 hồ sơ v1 + 15 hồ sơ v2: Hà Nội, căn hộ, alias khu vực, thu nhập, vay); paraphrase giữ cùng group/split.
- `oracles/cost_cases.json`: 22 ca tính tay độc lập: 15 ca chi phí `C01`–`C15` và 7 ca khả năng chi trả/vay `L01`–`L07`. Mỗi ca có số học và hằng số kỳ vọng; cần người kiểm tra chéo trước khi dùng cho nghiên cứu.
- `profiles/intent_cases.json`: 38 ca gold ý định chat cho bộ định tuyến (`I001`–`I038`; handbook 8, human_support 6, calculate_cost 6, simulate_finance 8, find_room 6, unknown 4; dev 15 / test 23), đo bằng `eval intents`. Gold là nhãn người soạn; `simulate_finance` dự kiến bị đoán sai cho tới khi AG-02 thêm ý định này — sai được ghi lại, không sửa nhãn.
- `oracles/loan_parse_cases.json`: 19 ca oracle parse câu hỏi vay `LP01`–`LP19` cho `interpreter.parse_loan_terms` (AG-02), kèm trường `rules` (kỳ hạn 1–60 tháng, lãi 0–50%, dấu phẩy thập phân, hai số thì lấy số đầu, đơn vị triệu/tr). Tính tay độc lập với code backend.
- `oracles/invoice_cases.json`: 12 ca oracle hóa đơn PMS `INV-01`–`INV-12` tính tay (kwh lẻ làm tròn, nước m³/người, phí gồm trong thuê, chỉ số giảm, thiếu đơn giá, 0 kWh, nhiều xe, căn hộ 2PN), kiểm bằng `eval invoices` trên DB tạm; lệch thì ghi lại để BE rà `pms.py`, không sửa oracle cho khớp code.
- `manifests/development_manifest.json`: hash đầu vào; `frozen=false`. G4 là tên guard lịch sử trong CLI hiện có; protocol/freeze nghiên cứu mới phải đối chiếu P5, không suy sản phẩm v1 đã đạt P4. Quy trình chốt dữ liệu xem [eval/FREEZE.md](../eval/FREEZE.md).

## Lệnh

Từ root repository, không gọi provider:

```bash
.venv/bin/python -m eval validate
.venv/bin/python -m data.generate --output .local/regenerated-data
.venv/bin/python -m eval intents --split dev
.venv/bin/python -m eval invoices
```

Generator có seed `20261001` (phòng v1) và `20261005` (căn v2). Không ghi đè dataset đã freeze; tạo version/output mới. Bộ gold extraction là các tình huống tổng hợp được soạn trước, chưa được kiểm chứng bằng người dùng thật. Nhãn relevance phòng vẫn để trống để người đánh giá chấm độc lập.

## Quy ước schema

Schema code ở `backend/app/models.py` là nguồn kiểm tra payload. `null` là chưa biết; `0` là biết bằng 0 và cần nguồn. Giá tiền nguyên VND; đơn giá phí dùng Decimal dưới dạng string JSON. Mỗi fee có tên, mode `fixed/person/vehicle/kwh/m3`, source và cờ included. `published` là duyệt tin; approval của recommendation là bước riêng. `available=null` cần xác minh.

`Profile` chứa form đã xác nhận, tách khỏi `Extraction` và tiền được nhắc trong chat. Location có accuracy và uncertainty; không suy diễn thời gian di chuyển. `soft_description` chỉ chứa ưu tiên mềm; loại tiền/liên hệ trước embedding.

Import kho bằng CLI backend là merge có kiểm revision; không tự xóa ID bị bỏ khỏi JSON. Dùng DB mới để tái tạo đúng 220 căn của dataset v2, thay vì trộn với kho demo hoặc kho v1 cũ.

## places.json (AG-01, 05/11/2026)

`places.json` là danh mục điểm mốc đã kiểm chứng (88 điểm: trường ĐH, bệnh viện, KCN, ga, bến xe, TTTM, khu đô thị ở TP.HCM và Hà Nội) dùng để hiểu "gần HUST" trong chat và xếp hạng theo khoảng cách. Mỗi mục có `names[]`, `aliases[]` (không dấu, lowercase), `city`, `kind` (`school|hospital|transit|mall|work|area`), tọa độ, `uncertainty_m` (≥ 150 m), `source` (`osm` hoặc `manual`), `verified_at` và, khi tên trần cho kết quả sai, `geocode_query` (tên + đường + quận).

**Nguồn tọa độ (LOC-001, 23/11/2026):** đối chiếu Nominatim (OpenStreetMap) từng điểm, duyệt tay từng kết quả. `source=osm` là kết quả mà `display_name` nêu đúng cơ sở; `source=manual` là tọa độ suy ra gián tiếp (tòa chung địa chỉ, tên đường, một cửa hàng trong cùng tòa nhà) nên `uncertainty_m` ≥ 500. Bản 05/11 lấy "xấp xỉ từ kiến thức địa lý" và nhiều điểm lệch hàng km (ĐH Xây dựng 6,7 km, Bến xe Miền Đông mới 7 km...), nay đã thay. Tọa độ vẫn chỉ để xếp khoảng cách tương đối, không phải dữ liệu đo đạc.

**Chạy lại kiểm tra:** `python -m data.verify_places` (chỉ kiểm cấu trúc, không gọi mạng) hoặc `python -m data.verify_places --live [--only id,…] [--json-out file]` (gọi Nominatim, User-Agent `HomeMatch-localhost/1.0`, cách nhau ≥ 1,1 s; trên macOS đặt `SSL_CERT_FILE` trỏ tới `certifi/cacert.pem` của venv). Script chỉ in id, khoảng lệch và `display_name` để người duyệt; không tự ghi đè tọa độ. Sau khi sửa `places.json`, cập nhật hash trong `manifests/development_manifest.json`. Ngoài danh mục này, `find_place` tra bản đồ lúc chạy (xem `docs/thiet-ke-agent.md`, `HOMEMATCH_GEOCODER`).
