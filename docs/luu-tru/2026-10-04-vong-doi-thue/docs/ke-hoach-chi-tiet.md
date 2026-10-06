# Chỉ mục kế hoạch chi tiết HomeMatch v1

**Cập nhật:** 04/10/2026. Bộ plan mới phục vụ sản phẩm hoàn thiện, không còn dùng tổng 62 task/322 bước/205 tiêu chí của đợt MVP làm chuẩn hoàn thành. Các ID lịch sử chỉ được giữ trong báo cáo cũ.

## Cách dùng

1. Đọc [đặc tả](dac-ta-san-pham.md), [yêu cầu](yeu-cau-san-pham.md), [quy trình](quy-trinh-nghiep-vu.md) và [AC](tieu-chi-nghiem-thu.md).
2. Chọn W-01–W-18 trong [backlog](ke-hoach-trien-khai.md), xem dependency và gate.
3. Theo plan chuyên môn bên dưới để triển khai. AC chuyên môn bổ sung kiểm kỹ thuật; AC-HM là điều kiện sản phẩm chung.
4. Sau kiểm chứng, cập nhật [trạng thái](trang-thai-trien-khai.md) bằng bằng chứng có ngày/config, không sao checklist kế hoạch thành kết quả.

## Plan chuyên môn

| Nhóm | Tóm tắt | Chi tiết | Hợp đồng liên quan |
|---|---|---|---|
| FE | [PLAN](../frontend/PLAN.md) | [DETAILED_PLAN](../frontend/DETAILED_PLAN.md) | [UI_SPEC](../frontend/UI_SPEC.md), API thực thi/v1, AC-HM |
| BE | [PLAN](../backend/PLAN.md) | [DETAILED_PLAN](../backend/DETAILED_PLAN.md) | [Kiến trúc](kien-truc-homematch.md), [API v1](api-san-pham-v1.md), migrations |
| AG | [AGENT_PLAN](../backend/AGENT_PLAN.md) | [AGENT_DETAILED_PLAN](../backend/AGENT_DETAILED_PLAN.md) | [Agent](thiet-ke-agent.md), deterministic boundaries, provider configs |
| DATA | [PLAN](../data/PLAN.md) | [DETAILED_PLAN](../data/DETAILED_PLAN.md) | Source/license register, schemas, fixture/oracle versions |
| EV | [PLAN](../eval/PLAN.md) | [DETAILED_PLAN](../eval/DETAILED_PLAN.md) | Protocol/freeze/judgments và QA release |
| INF | [PLAN](../infra/PLAN.md) | [DETAILED_PLAN](../infra/DETAILED_PLAN.md) | [Runbook hiện tại](../infra/RUNBOOK.md), target deploy/restore/outbox |
| DOC | [PLAN](PLAN.md) | [DETAILED_PLAN](DETAILED_PLAN.md) | Research→requirements→process→AC→design→evidence |

## Phân biệt nguồn

[API 0.3.0](api-contract.md), [kiến trúc local](kien-truc-trien-khai.md), các báo cáo kiểm chứng và manifest 01/10 là dữ liệu về nền tảng đang có. [API v1](api-san-pham-v1.md) và kiến trúc sản phẩm là thiết kế cần xây. Nghiên cứu HubHome có nguồn HH-01–HH-12 và ngày/giới hạn; không dùng URL website để xác nhận module HomeMatch đã chạy.

## Cổng và bằng chứng

P0: contract không mâu thuẫn. P1: accounts/catalog. P2: discovery/AI/compare/history/viewing/notification. P3: contracts/tenancy/meters/invoices/reconcile/maintenance. P4: mọi AC/NFR, browser E2E, deployment/restore/ops. P5: nghiên cứu freeze và labels thật. Định nghĩa chi tiết ở [tiêu chí nghiệm thu](tieu-chi-nghiem-thu.md).
