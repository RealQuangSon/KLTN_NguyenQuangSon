# Bằng chứng đánh giá phát triển HomeMatch — split `dev`

Stage: `development` · rankings hash: `ab5f310b96275a4e…` · catalog hash: `e89d0b3a3e50cf68…`

Mọi bảng dưới đây truy được về artifact trong `evidence_index.csv`. Đây là kết quả phát triển/khám phá, **không phải kết quả nghiên cứu**: nhãn relevance người chấm và phép đo GPT/P thật còn thiếu.

## Dữ liệu

| Đặc tính | Giá trị |
|---|---|
| Phòng canonical | 220 |
| Hồ sơ dev/test | 15/30 |
| Câu phát biểu gold | 53 |
| Capacity chưa biết | 9 |
| Availability chưa biết | 7 |
| Phí theo đơn giá chưa biết | 18 |
| Tiện ích chưa biết | 20 |
| Độ chính xác vị trí | approximate: 213, area_only: 7 |
| Tỷ lệ synthetic | 1 |

## Oracle tài chính (22/22 đạt)

| Ca | Kết quả | Tổng tháng (VND) | Tiền ban đầu (VND) | Thiếu |
|---|---|---|---|---|
| C01-reference | đạt | 3250000 | 5500000 | — |
| C02-people-vehicles | đạt | 3610000 | 5500000 | — |
| C03-water-m3 | đạt | 3230000 | 5500000 | — |
| C04-included | đạt | 3150000 | 5500000 | — |
| C05-zero-with-source | đạt | 3150000 | 5500000 | — |
| C06-unknown-water | đạt | — | 5500000 | water |
| C07-absent-service | đạt | — | 5500000 | service |
| C08-unknown-deposit | đạt | 3250000 | — | deposit |
| C09-three-months | đạt | 3250000 | 10500000 | — |
| C10-one-time | đạt | 3250000 | 5650000 | — |
| C11-zero-usage | đạt | 2650000 | 5500000 | — |
| C12-round-half-up | đạt | 2833001 | 5500000 | — |
| C13-included-unknown-rate | đạt | 2830000 | 5500000 | — |
| C14-missing-initial | đạt | 3250000 | — | first_rent, one_time |
| C15-extra-monthly | đạt | 3325000 | 5500000 | — |
| L01-worked-example | đạt | 7070000 | 13500000 | — |
| L02-zero-rate | đạt | 3250000 | 5500000 | — |
| L03-no-shortfall | đạt | 3250000 | 5500000 | — |
| L04-equal-split | đạt | 3610000 | 5500000 | — |
| L05-exceeds-cap | đạt | 3250000 | 5500000 | — |
| L06-boundary-30 | đạt | 3250000 | 5500000 | — |
| L07-boundary-40 | đạt | 3250000 | 5500000 | — |

## Trích xuất nhu cầu (mode `demo_rules`)

Micro-F1: **1** · Intent accuracy: **1** · lỗi/tổng câu: 0/18

| Trường | TP | FP | FN | F1 |
|---|---|---|---|---|
| area | 16 | 0 | 0 | 1 |
| city | 16 | 0 | 0 | 1 |
| needs_destination | 18 | 0 | 0 | 1 |
| people | 16 | 0 | 0 | 1 |
| preferences | 24 | 0 | 0 | 1 |

Tiền nhắc trong chat chỉ là hint cục bộ, không nằm trong F1 model.

## Xếp hạng trên tập eligible đầy đủ

Elite set/profile: min 1, median 3, max 10

| Phương pháp | successful | no_match | needs_verification | unavailable |
|---|---|---|---|---|
| B1 | 15 | 0 | 0 | 0 |
| P | 0 | 0 | 0 | 15 |

Provider semantic: `unavailable`; P offline ghi `unavailable`, không tự thay bằng B1.

## Chỉ số relevance

| Mục | Giá trị |
|---|---|
| Trạng thái nhãn | pending_human_judgments |
| Chỉ số chất lượng | chưa tính |

Nhãn người chấm còn trống; đầu ra máy không tự thành gold.

## Bất biến điều kiện cứng (đạt)

| Kiểm tra | Kết quả |
|---|---|
| Hồ sơ kiểm tra | 15 |
| Ứng viên eligible đã kiểm | 62 |
| Vi phạm | 0 |
| Phản thực tế hoa hồng giữ rank | đạt |
| Đối chứng available=false loại phòng | True |

## Grounding lời giải thích (đạt)

Items kiểm tra: 48 · claims: 142 · không hỗ trợ: 0

| Loại claim | Số lượng | Không hỗ trợ |
|---|---|---|
| affordability_band | 4 | 0 |
| distance_radius | 17 | 0 |
| loan_estimate | 4 | 0 |
| monthly_total | 48 | 0 |
| preference_missing | 11 | 0 |
| preference_satisfied | 43 | 0 |
| required_amenity | 15 | 0 |

## Đo máy (ms, offline)

| Pha | Số mẫu | p50 | p95 | Model calls |
|---|---|---|---|---|
| extraction | 18 | 0.1033 | 0.4883 | 0 |
| finance_oracle | 22 | 0.043 | 0.1608 | 0 |
| ranking_B1 | 15 | 6.8942 | 10.8226 | 0 |
| ranking_P | 15 | 6.7445 | 7.2485 | 0 |

Tổng logical model calls: 0 · thời gian chờ duyệt: `excluded_machine_phases_only`. Không suy ra latency provider thật từ các số này.

## Giới hạn bằng chứng

- Dữ liệu 80 phòng/30 hồ sơ hoàn toàn tổng hợp, một thành phố; không đại diện thị trường.
- Nhãn relevance độc lập chưa có; mọi chỉ số ranking đang `pending_human_judgments`.
- P cần vector thật (PostgreSQL + embedding live); bản offline ghi `unavailable`, fallback cấu trúc không được tính là P.
- Chưa chạy GPT-4o/embedding thật; F1 extraction ở đây là của rule demo.
- Latency đo trên một process local, không phải tải production.
- Đúng thứ tự nghiên cứu: freeze → pool → nhãn blind → khóa hash nhãn → metric; xem `eval/REPRODUCE.md`.
