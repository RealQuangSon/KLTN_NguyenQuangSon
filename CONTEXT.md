# Từ điển và quyết định HomeMatch AI Agent

**Cập nhật:** 05/10/2026. Đề tài và phạm vi: [đề cương](docs/ke-hoach-kltn-homematch.md). Chỉ mục tài liệu: [docs/README.md](docs/README.md).

## Thuật ngữ

| Thuật ngữ | Nghĩa trong repository |
|---|---|
| HomeMatch AI Agent | Nền tảng cho thuê phòng, studio, căn hộ tại TP.HCM và Hà Nội, có trợ lý AI gợi ý theo nhu cầu và năng lực tài chính |
| Người thuê / khách (`renter`) | Người tìm và thuê phòng. Chỉ đọc dữ liệu của mình. |
| Chủ nhà (`owner`) | Sở hữu phòng (`Room.landlord_id`). Duyệt phòng của mình trong danh sách AI; vận hành tin, lịch, chat, hợp đồng, hóa đơn, sự cố, khách tiềm năng. |
| Quản trị viên (`admin`) | Giám sát hội thoại AI, chuyển giao, người dùng, tin đăng, vận hành |
| `manager` | Vai trò cũ (sale), không còn quyền nghiệp vụ |
| Căn | Đơn vị cho thuê: `room`, `studio`, `apartment` (có `bedrooms`) |
| Tình trạng (`occupancy`) | `vacant` (trống), `deposited` (đã cọc), `rented` (đã thuê); đặt luôn `available` |
| Hồ sơ nháp / đã xác nhận | Nhu cầu chưa xác nhận (trường có trạng thái và nguồn) / snapshot có phiên bản do khách xác nhận |
| Điều kiện cứng / sở thích mềm | Bắt buộc, kiểm bằng code, không tự nới / chỉ dùng để xếp hạng và giải thích |
| Tổng tháng / tiền vào ở | Thuê + phí định kỳ theo kịch bản / cọc + trả trước + phí một lần + chuyển nhà + sắm sửa |
| Khả năng chi trả | Phần thiếu khi vào ở, gánh nặng tháng, tỷ lệ trên thu nhập, băng `phu_hop`/`can_nhac`/`vuot`/`chua_ro` |
| Vay ngắn hạn | Ước tính trả góp đều cho phần tiền vào ở còn thiếu; không phải báo giá tín dụng |
| B1 / P | Xếp hạng cấu trúc / B1 kết hợp semantic trên cùng tập đủ điều kiện |
| Run | Một lần sinh danh sách gợi ý từ snapshot hồ sơ và kho |
| HITL theo chủ nhà | Mỗi chủ nhà duyệt phòng của mình; khách thấy dần (`partially_published`); chốt khi mọi chủ đã quyết định |
| Override | Chủ nhà bỏ phòng hoặc đổi thứ tự trong phần của mình; bắt buộc `override_reason` |
| Tin công khai | Phòng `published` của chủ nhà, tìm được bằng bộ lọc mà không cần duyệt danh sách AI |
| Chuyển giao (handover) | Mở live chat với chủ nhà kèm ngữ cảnh: phòng, nhu cầu, băng, chat AI gần nhất đã che PII |
| Transcript | Chat AI lưu có che SĐT, email, số tài khoản; giữ 90 ngày; admin mở thì ghi audit |
| Thông báo | Trong ứng dụng, có khóa chống trùng; email là stub ghi log |
| Job | Việc định kỳ: nhắc lịch, nhắc thanh toán, nhắc gia hạn, chăm sóc khách, dọn chat |
| Hợp đồng (lease) | `draft` → `sent` → `accepted` (khách chấp thuận đúng phiên bản) → `active` → `ended`/`terminated`; không phải chữ ký số |
| Hóa đơn / báo chuyển / biên lai | Lập từ chỉ số công tơ và bảng phí đã chụp, không sửa sau phát hành / khách báo đã chuyển, chưa phải đã thu / phát hành khi chủ ghi thu |
| Khách tiềm năng (lead) | Giai đoạn `new`→`contacted`→`viewing`→`negotiating`→`won`/`lost`; điểm quan tâm từ xem, chat, lịch, hợp đồng |
| Memory | Sở thích đã xác nhận, chỉ khi khách đồng ý; điền sẵn dạng `inferred`; không có tiền |
| Synthetic | Dữ liệu tổng hợp để phát triển và đánh giá |

## Quyết định đang áp dụng

- **D-01/D-02:** thị trường cho thuê; vay ngắn hạn cho tiền vào ở. Đã xác nhận.
- **D-03/D-05:** khách, chủ nhà, admin; mỗi chủ nhà duyệt phòng của mình.
- **D-04:** TP.HCM và Hà Nội trong một kho.
- **D-06:** chat AI lưu có che PII, giữ 90 ngày, đọc có audit.
- **D-07:** thay tích hợp bên ngoài bằng phương án không cần tài khoản: OSM, Jitsi, stub email, link chia sẻ, Web Speech, đối soát thủ công.
- **D-08:** hợp đồng là chấp thuận theo phiên bản, không phải chữ ký số.
- Tiền, điều kiện cứng, quyền, công bố là code xác định; LLM không tính tiền, không duyệt.
- Chủ nhà không thấy thu nhập hay tỷ lệ của khách, chỉ thấy băng.
- Xếp hạng không dùng hoa hồng hay thời gian tồn.
- Một API worker. PostgreSQL + pgvector cho bản triển khai; SQLite và chế độ demo cho phát triển.
