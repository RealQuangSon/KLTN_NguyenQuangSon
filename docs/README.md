# Bộ tài liệu HomeMatch AI Agent

**Cập nhật:** 05/10/2026. **Đề tài:** HomeMatch AI Agent – Trợ lý gợi ý căn hộ theo nhu cầu và năng lực tài chính, áp dụng cho thị trường **cho thuê** phòng, studio, căn hộ tại TP.HCM và Hà Nội.

## Đọc theo mục đích

| Muốn biết | Tài liệu |
|---|---|
| Đề tài, câu hỏi nghiên cứu, quyết định điều chỉnh | [Đề cương KLTN](ke-hoach-kltn-homematch.md) |
| Sản phẩm gồm những gì, ngoài phạm vi là gì | [Đặc tả sản phẩm](dac-ta-san-pham.md) |
| Yêu cầu có mã, mức CB/NC, hiện trạng | [Danh mục yêu cầu](yeu-cau-san-pham.md) |
| Khi nào gọi là đạt | [Tiêu chí nghiệm thu](tieu-chi-nghiem-thu.md) |
| Vai trò, luồng, ai thấy gì | [Quy trình nghiệp vụ](quy-trinh-nghiep-vu.md), [trạng thái và lỗi](status-dictionary.md) |
| Cách tính chi phí, khả năng chi trả, khoản vay | [Engine tài chính thuê](tai-chinh-thue.md) |
| Agent, multi-agent, memory, tối ưu semantic | [Thiết kế agent](thiet-ke-agent.md) |
| Kiến trúc đích, kiến trúc đang chạy | [Kiến trúc đích](kien-truc-homematch.md), [bản 0.4.0](kien-truc-trien-khai.md) |
| API đang chạy, API cần bổ sung | [API 0.4.0](api-contract.md) + [OpenAPI](openapi.json), [API đích](api-san-pham-v1.md) |
| Việc cần làm, thứ tự | [Kế hoạch triển khai](ke-hoach-trien-khai.md); [coding plan cho AI agent](coding-plan/README.md), chia BE, FE, Agent, Data |
| Code đang ở đâu, bằng chứng | [Trạng thái](trang-thai-trien-khai.md) |
| Tham khảo HubHome | [Nghiên cứu](nghien-cuu-hubhome.md), [khảo sát đăng nhập 01/10](khao-sat-hubhome-da-dang-nhap.md) |
| Lần căn chỉnh docs 05/10 | [Rà soát](ra-soat-tai-lieu.md) |

## Quy ước

- Mã yêu cầu `FR-xx`/`NFR-xx` ↔ tiêu chí `AC-xx` ↔ task `Tx.y`. Quyết định điều chỉnh đề bài là `D-0x`, giả định là `A-0x`. Mục nghiên cứu HubHome là `HH-xx`.
- **Hiện có**: có code và test. **Đích**: thiết kế chưa triển khai. Không ghi đạt nếu chưa có bằng chứng chạy thật kèm ngày và cấu hình.
- Khi tài liệu mâu thuẫn, ưu tiên theo thứ tự: đề cương → đặc tả → yêu cầu/nghiệm thu → thiết kế/kiến trúc/API → kế hoạch. Với hành vi đang chạy, mã nguồn và `api-contract.md` là nguồn đối chiếu.

## Lưu trữ và bằng chứng lịch sử

- [luu-tru/2026-10-04-vong-doi-thue](luu-tru/2026-10-04-vong-doi-thue/): bộ docs hướng "nền tảng toàn vòng đời thuê" (HM-01…HM-10). Ngoài đề tài, chỉ để tham khảo.
- [kiem-chung-backend](kiem-chung-backend.md), [kiem-chung-mvp](kiem-chung-mvp.md), [kiem-chung-scaffold](kiem-chung-scaffold.md), [release-manifest.json](release-manifest.json): báo cáo có ngày, giữ nguyên.
