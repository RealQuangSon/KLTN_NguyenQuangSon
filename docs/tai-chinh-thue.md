# Engine tài chính thuê và ước tính vay

**Cập nhật:** 05/10/2026. Đặc tả cho yêu cầu FR-05…FR-08 trong [danh mục yêu cầu](yeu-cau-san-pham.md). Engine là code xác định: LLM không tính tiền, không đoán số còn thiếu và không quyết định khách có đủ khả năng hay không.

Toàn bộ engine đã chạy trong `backend/app/costs.py` (cập nhật GĐ2, 05/10/2026). Lọc cứng dùng engine này trong `backend/app/catalog.py`. Mô phỏng có cả API và giao diện (nút "Mô phỏng tài chính" trên thẻ căn đã duyệt).

## 1. Nguyên tắc

- Tiền là số nguyên VND. Đơn giá dùng `Decimal`, làm tròn `ROUND_HALF_UP` tại từng dòng.
- `null` nghĩa là chưa biết. `0` nghĩa là đã biết bằng 0 và phải có nguồn. Thiếu một khoản bắt buộc thì tổng đầy đủ là `null`. Tổng các khoản đã biết (`*_known_vnd`) chỉ là tổng tạm.
- Mọi kết quả kèm giả định (kịch bản) và nguồn từng dòng, để chủ nhà và khách kiểm lại được.
- Đây là ước tính hỗ trợ quyết định, **không phải tư vấn tài chính**. Không có bên cho vay, không chấm điểm tín dụng.

## 2. Chi phí thuê (Đã có)

**Tổng tháng** = tiền thuê + các phí định kỳ bắt buộc `electricity, water, internet, parking, service` + phí định kỳ khác trong báo giá.

Mỗi phí có cách tính (`mode`):

| Mode | Số lượng nhân với đơn giá |
|---|---|
| `fixed` | 1 |
| `person` | số người ở |
| `vehicle` | số xe |
| `kwh` | số kWh điện mỗi tháng trong kịch bản (mặc định 140) |
| `m3` | số m³ nước mỗi tháng trong kịch bản |

Phí "đã gồm trong tiền thuê" tính là 0 và giữ nguồn.

**Tiền vào ở** = cọc + tiền thuê × số tháng trả trước + phí một lần + chi phí chuyển nhà + chi phí sắm sửa. Không cộng lại tiền thuê tháng đầu, vì đã nằm trong phần trả trước.

## 3. Hồ sơ năng lực tài chính

| Trường | Trạng thái | Ý nghĩa |
|---|---|---|
| `max_monthly_cost_vnd` | Đã có | Trần tổng tháng. Điều kiện cứng. |
| `max_rent_vnd` | Đã có | Trần riêng cho tiền thuê, tùy chọn. |
| `max_initial_cash_vnd` | Đã có | Tiền mặt sẵn có cho vào ở, tùy chọn. Điều kiện cứng khi không bật kịch bản vay. |
| `monthly_income_vnd` | Đã có | Thu nhập tháng, tùy chọn. Chỉ dùng tính tỷ lệ. |
| `loan` | Đã có | `{annual_rate, term_months, max_principal_vnd?}` do khách tự nhập. `null` nghĩa là không vay. |
| `cost_split` | Đã có | `none` hoặc `equal`: chia đều cho số người ở ghép. |
| `min_bedrooms` | Đã có | Số phòng ngủ tối thiểu (căn hộ). Điều kiện cứng; căn chưa rõ số phòng ngủ vào "cần xác minh". |

Mọi trường tiền chỉ vào hồ sơ qua **biểu mẫu xác nhận**. Tiền xuất hiện trong chat bị tách trước khi gửi LLM (`redact`) và chỉ thành gợi ý `budget_hint`.

## 4. Kiểm tra khả năng chi trả (Đã có)

- **Phần thiếu khi vào ở:** `shortfall = max(0, initial_total − max_initial_cash)`. Bằng `null` khi `initial_total` hoặc tiền mặt chưa biết.
- **Gánh nặng tháng:** `burden = monthly_total + installment`, trong đó `installment` lấy từ mục 5 (bằng 0 khi không vay).
- **Phần của khách:** `renter_burden = burden / số người` (làm tròn VND) khi `cost_split = equal`, ngược lại bằng `burden`.
- **Tỷ lệ chi phí nhà ở:** `housing_ratio = renter_burden / monthly_income`, làm tròn `ROUND_HALF_UP` 4 chữ số. Băng được xét trên tỷ lệ **đã làm tròn**: 0,29999 → 0,3000 → `phu_hop`. Bằng `null` khi thiếu thu nhập hoặc tổng tháng.

Băng đánh giá (ngưỡng là cấu hình, ghi kèm kết quả):

| Băng | Điều kiện mặc định | Hiển thị |
|---|---|---|
| `phu_hop` | `housing_ratio ≤ 0,30` | Trong mức khuyến nghị |
| `can_nhac` | `0,30 < housing_ratio ≤ 0,40` | Cần cân nhắc |
| `vuot` | `housing_ratio > 0,40` | Vượt mức khuyến nghị |
| `chua_ro` | Thiếu thu nhập hoặc tổng tháng | Chưa đủ dữ liệu |

Mốc 30% là quy tắc kinh nghiệm phổ biến, không phải chuẩn pháp lý. Băng **không phải điều kiện cứng**: nó chỉ hiển thị và giải thích, trừ khi khách chủ động đặt trần tổng tháng.

## 5. Ước tính vay ngắn hạn (Đã có)

Chỉ áp dụng khi khách bật kịch bản vay và `shortfall > 0`. Gốc vay `P = shortfall`, tối đa `max_principal_vnd`. Lãi suất tháng `r = annual_rate / 12`, số kỳ `n = term_months`.

Trả góp đều (annuity):

```
installment = P · r / (1 − (1 + r)^(−n))      nếu r > 0
installment = P / n                           nếu r = 0
```

- `installment` làm tròn đến VND.
- `total_paid = installment × n`.
- `total_interest = total_paid − P`.
- Kết quả ghi rõ: đây là ước tính lãi giảm dần theo dư nợ với lãi suất cố định do khách nhập, không phải báo giá của tổ chức tín dụng.

Khi bật kịch bản vay, điều kiện cứng chuyển thành:

1. `shortfall ≤ max_principal_vnd`.
2. `monthly_total + installment ≤ max_monthly_cost_vnd` trong thời gian vay.

Căn không đạt bị loại với lý do `loan_principal` hoặc `loan_burden`.

## 6. Mô phỏng kịch bản (đã có: API và giao diện)

Cho một căn, khách so sánh tối đa 3 kịch bản cạnh nhau, ví dụ:

- ở một mình và ở ghép hai người;
- cọc 1 tháng và cọc 2 tháng;
- vay 6 tháng và vay 12 tháng.

Mỗi kịch bản là một lần gọi hàm thuần, trả về cùng cấu trúc kết quả. Mô phỏng **không** đổi hồ sơ đã xác nhận hay danh sách đã duyệt. Muốn dùng kịch bản mới để tìm thì phải xác nhận hồ sơ phiên bản mới, và danh sách mới lại phải qua chủ nhà duyệt.

## 7. Ví dụ tính tay

Kịch bản: 2 người, 1 xe, 120 kWh. Thu nhập 25.000.000 VND. Tiền mặt 8.000.000 VND. Vay 12%/năm trong 6 tháng.

| Dòng | Cách tính | VND |
|---|---|---|
| Tiền thuê | | 6.000.000 |
| Điện | 3.500 × 120 kWh | 420.000 |
| Nước | 100.000 × 2 người | 200.000 |
| Internet | cố định | 150.000 |
| Gửi xe | 100.000 × 1 xe | 100.000 |
| Dịch vụ | cố định | 200.000 |
| **Tổng tháng** | | **7.070.000** |
| Cọc | 1 tháng | 6.000.000 |
| Trả trước | 1 tháng | 6.000.000 |
| Chuyển nhà + sắm sửa | | 1.500.000 |
| **Tiền vào ở** | | **13.500.000** |
| Phần thiếu | 13.500.000 − 8.000.000 | 5.500.000 |
| Trả góp/tháng | annuity, r = 1%, n = 6 | 949.016 |
| Tổng lãi | 949.016 × 6 − 5.500.000 | 194.096 |
| Tỷ lệ khi đang vay | (7.070.000 + 949.016) / 25.000.000 | 32,1% → `can_nhac` |
| Tỷ lệ sau khi trả hết | 7.070.000 / 25.000.000 | 28,3% → `phu_hop` |

Ca này là `L01-worked-example` trong `data/oracles/cost_cases.json`, cùng 6 ca `L02`–`L07`: lãi 0%, không thiếu tiền, chia đều, vượt gốc tối đa, biên 30% và biên 40%. `eval oracle` cho 22/22 ca khớp (15 ca chi phí + 7 ca khả năng chi trả). Người khác vẫn phải tính lại độc lập các hằng số này trước khi dùng cho nghiên cứu.

## 8. Bảo mật dữ liệu tài chính

- Thu nhập, tiền mặt, thông số vay chỉ nằm trong hồ sơ đã xác nhận của phiên. Không có trong embedding, prompt LLM, log, metrics hay checkpoint ngoài phạm vi cần thiết.
- Chủ nhà của phòng thấy trần tổng tháng, tiền mặt và kịch bản vay để kiểm tra độ phù hợp. Chủ nhà **chỉ thấy băng**, không thấy thu nhập và không thấy tỷ lệ: biết tỷ lệ cùng gánh nặng tháng thì suy ngược ra được thu nhập. Server bỏ `monthly_income_vnd` khỏi hồ sơ và đặt `housing_ratio = null` trong DTO của sale.
- Memory xuyên phiên không bao giờ lưu số tiền, thu nhập hay khoản vay ([thiết kế agent](thiet-ke-agent.md#6-memory-xuyên-phiên)).

## 9. Hóa đơn sau khi thuê (PMS)

Hóa đơn hằng tháng (`backend/app/pms.py`) dùng cùng quy tắc tiền: `Decimal`, làm tròn từng dòng, không coi đơn giá chưa biết là 0. Khác với ước tính trước khi thuê:
- dùng **chỉ số công tơ thật** (cuối kỳ − đầu kỳ) cho các phí tính theo kWh hoặc m³;
- dùng số người và số xe ghi trong hợp đồng;
- dùng bảng phí chụp lại lúc soạn hợp đồng.

Thiếu chỉ số hoặc đơn giá thì không lập được hóa đơn. Ví dụ kiểm thử: 2.500.000 + 150 kWh × 3.000 + 2 người × 80.000 + 100.000 + 1 xe × 100.000 + 50.000 = 3.360.000 VND (`test_pms.py`).
