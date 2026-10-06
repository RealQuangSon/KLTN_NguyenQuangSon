# Kế hoạch dữ liệu

**Cập nhật:** 05/10/2026. Phục vụ FR-24 (kho TP.HCM + Hà Nội, phòng/studio/căn hộ) và phần đánh giá trong [đề cương](../docs/ke-hoach-kltn-homematch.md). Dataset hiện có mô tả ở [README.md](README.md).

> **Việc tiếp theo (06/10/2026):** làm theo [coding plan](../docs/coding-plan/data.md); đọc [phần chung](../docs/coding-plan/README.md) trước.

## 1. Dataset v1 (giữ trong v2)

- 80 phòng/studio tổng hợp tại TP.HCM, 5 khu vực: Quận 1, 3, 7, 10, Bình Thạnh.
- 30 hồ sơ gold (10 dev, 20 test), 15 ca oracle chi phí.
- `development_manifest.json` với `frozen=false`. Seed generator `20261001`.

Toàn bộ là dữ liệu tổng hợp. `crawl_chotot.py` tồn tại nhưng **không** được dùng để nạp kho, vì chưa có xác nhận quyền sử dụng dữ liệu Chợ Tốt. `fixtures/v1` (hợp đồng, hóa đơn, công tơ) thuộc phạm vi cũ, giữ lại nhưng không dùng.

## 2. Dataset v2 (T2.2, đã sinh 05/10/2026), gộp vào kho chính

| Thành phần | Nội dung |
|---|---|
| Thành phố | TP.HCM 120, Hà Nội 100 |
| Khu vực | TP.HCM: Quận 1, 3, 7, 10, Bình Thạnh, Gò Vấp, TP. Thủ Đức. Hà Nội: Cầu Giấy, Đống Đa, Hai Bà Trưng, Thanh Xuân, Nam Từ Liêm, Hoàng Mai. Long Biên cố ý không có căn, để có ca không tìm thấy. Tên chuẩn theo `backend/app/locations.py`. |
| Loại hình | 120 `room`, 40 `studio`, 60 `apartment` (1–2 phòng ngủ) |
| Quy mô | 220 căn; 80 phòng v1 giữ nguyên ID và nội dung, sinh từ seed `20261001`; 140 căn mới sinh từ seed `20261005` |
| Ca khó | Phí chưa biết; tiện ích chưa biết; vị trí `area_only`; biên bán kính; căn không trống; trùng alias; hoa hồng hoặc thời gian tồn trong tiêu đề (để kiểm tra không thiên vị) |
| Mô tả mềm | `features_text` (view, ánh sáng, yên tĩnh); không chứa tiền hay liên hệ |
| Hồ sơ gold | 15 hồ sơ v2 (`profile-031`…`045`, 5 dev / 10 test). Có alias ("Sài Gòn", "Q7", "HN", "hanoi"), căn hộ và số phòng ngủ, thu nhập, chia đều, kịch bản vay. Tổng 45 hồ sơ (15 dev / 30 test). |
| Oracle | `L01`–`L07`: ví dụ tính tay, lãi 0%, không thiếu tiền, chia đều, vượt gốc tối đa, biên 0,30 và 0,40. Người khác vẫn cần tính lại độc lập. |
| Manifest | `homematch-synthetic-v2`, `dataset_version = 2`. Sinh lại phòng và hồ sơ v1 bằng `python -m data.generate --rooms 80 --profiles 30 --output <thư mục khác>`; file oracle khi đó vẫn có đủ 22 ca. |

Giá thuê tổng hợp nên nằm trong khoảng thực tế để tình huống có ý nghĩa, nhưng không phải biểu giá thị trường:

| Loại | Khoảng giá |
|---|---|
| Phòng trọ | 1,8–5,5 triệu |
| Studio | 4–9 triệu |
| Căn hộ 1 phòng ngủ | 7–14 triệu |
| Căn hộ 2 phòng ngủ | 10–20 triệu |

## 3. Quy ước

- Schema là `backend/app/models.py`. `null` là chưa biết, `0` là biết bằng 0 và có nguồn.
- Không có dữ liệu cá nhân hay tài chính thật. Tọa độ là fixture, không định danh địa chỉ thật.
- Không ghi đè dataset đã freeze; tạo version mới. Đổi kho thì chạy lại `eval validate` và cập nhật manifest.
