# Trạng thái triển khai HomeMatch AI Agent

**Cập nhật:** 05/10/2026, sau đợt E1–E6 (5 phân hệ). **Code:** API 0.4.0 mở rộng (89 đường dẫn), schema ledger **v9**. **Dữ liệu:** dataset v2 (220 căn, 4 chủ nhà). Đối chiếu với [danh mục yêu cầu](yeu-cau-san-pham.md) và [cổng nghiệm thu](tieu-chi-nghiem-thu.md#cổng-hoàn-thành).

## 1. Bằng chứng chạy ngày 05/10/2026

**`bash infra/check-local.sh`** (SQLite, offline: luật demo, B1, không embedding): **exit 0**.

| Bước | Kết quả |
|---|---|
| `eval validate` | `valid`: 220 căn, 45 hồ sơ gold |
| `eval oracle` | 22/22 ca khớp |
| `eval extraction --split dev` | Độ chính xác ý định 1,0; micro-F1 1,0 |
| `eval invariants` | 0 vi phạm trên 62 cặp hồ sơ–căn; phản thực tế hoa hồng và thời gian tồn: thứ hạng không đổi |
| `eval grounding` | 142/142 khẳng định có bằng chứng |
| `pytest` | **196 passed**, 4 skipped (PostgreSQL không cấu hình) |
| Vitest | **41/41**; TypeScript và `vite build` thành công |
| `backend.demo`, `infra.smoke_api --in-process` | Passed |

**Kiểm thêm:**

| Việc | Kết quả |
|---|---|
| Nâng cấp một bản sao DB local cũ (`.local/homematch-mvp.sqlite`) | Lên schema 9, không lỗi |
| Server uvicorn thật, DB mới, kho v2, `HOMEMATCH_JOBS_INTERVAL_SECONDS=5` | `/ready` = `ready`, schema 9 |
| `infra.smoke_api` qua **HTTP thật** | Passed: duyệt theo nhiều chủ nhà, lịch xem trực tuyến, CAS, hết hiệu lực |
| Job nền | Tự chạy và ghi `hm_job_runs` |

**Giới hạn:**
- Micro-F1 1,0 chỉ là sanity check, vì luật offline và bộ câu gold cùng tác giả.
- Chưa có bằng chứng cho:
  - GPT-4o và P với vector thật;
  - PostgreSQL ở phiên bản này (lần gần nhất là [01/10](kiem-chung-backend.md));
  - demo trên trình duyệt;
  - Railway;
  - nhãn người chấm và khảo sát người dùng.

## 2. Đối chiếu yêu cầu

| Nhóm | Đã có | Một phần |
|---|---|---|
| Trợ lý AI (FR-01–25) | Tất cả, trừ hai mục bên phải | FR-11 (P chưa chạy live), FR-23 (chưa có nhãn và khảo sát) |
| Cổng người thuê (FR-26–31) | Tất cả | — |
| Tự động hóa (FR-32–35) | FR-32, 34, 35 | FR-33 (chưa có ưu đãi do chủ nhà đặt) |
| Admin Console (FR-36–38) | Tất cả | — |
| Cổng chủ nhà (FR-39–45) | FR-39, 41, 42, 44, 45 | FR-40 (chưa có ảnh), FR-43 (chưa đính ảnh) |
| Trợ lý chủ nhà (FR-46–48) | FR-46, 48 | FR-47 (không tự đăng lên mạng xã hội) |

**Cổng:**
- G1, G2, G-NT: các AC đều có test tự động pass; còn demo trên trình duyệt.
- G3 (Railway, live) và G4 (nghiên cứu): chưa đạt.

## 3. Thay đổi code theo đợt (05/10/2026)

| Đợt | Nội dung chính | Module | Test |
|---|---|---|---|
| GĐ1 | Alias khu vực TP.HCM/Hà Nội; chặn token cũ kích hoạt lại tài khoản bị vô hiệu hóa; dùng token nguyên tử | `locations.py`, `auth.py` | `test_locations.py`, `test_account_lifecycle.py` |
| GĐ2 | Căn hộ, phòng ngủ; khả năng chi trả, vay annuity; kho v2; `override_reason`; ẩn thu nhập; API mô phỏng | `costs.py`, `catalog.py`, `data/generate.py` | `test_finance.py` |
| GĐ3 | Multi-agent `ToolBox`; memory có đồng ý (v4); cache embedding truy vấn | `agents.py`, `memory.py`, `semantic.py` | `test_agents_memory.py` |
| GĐ4 (code) | UI mô phỏng; so sánh có biểu đồ | `Simulation.tsx`, `Shared.tsx` | `simulation-memory.test.tsx` |
| E1 | Chủ nhà thay sale: mỗi chủ duyệt phòng của mình (`hm_run_reviews`, v5), `partially_published`; CRUD tin; trống/đã cọc/đã thuê; lịch xem gửi chủ nhà, xem trực tuyến | `repository.py`, `service.py`, `LandlordWorkspace.tsx`, `RoomEditor.tsx` | `test_landlord.py` |
| E2 | Tìm theo bộ lọc, xem nhanh, bản đồ; đặt lịch từ tin (v6); tư vấn so sánh; cẩm nang (cả trong chat) | `listings.py`, `advisor.py`, `handbook.py`, `SearchPage.tsx`, `MapView.tsx` | `test_tenant_portal.py`, `search-portal.test.tsx` |
| E3 | Live chat và chuyển giao ngữ cảnh (v7); lưu chat AI che PII, giữ 90 ngày; Admin Console | `conversations.py`, `Inbox.tsx`, `AdminWorkspace.tsx` | `test_conversations_admin.py`, `inbox-admin.test.tsx` |
| E4 | Thông báo chống trùng (v8); job nền: nhắc lịch, chăm sóc khách, dọn chat; đồng bộ trạng thái và giá | `notifications.py`, `automation.py`, `NotificationBell.tsx` | `test_automation.py` |
| E5 | PMS & CRM (v9): hợp đồng, công tơ, hóa đơn, báo chuyển và xác nhận, biên lai, đối soát, bảo trì, khách tiềm năng, dashboard, báo cáo; nhắc thanh toán và gia hạn | `pms.py`, `Pms.tsx`, `DocumentViewer.tsx` | `test_pms.py`, `pms.test.tsx` |
| E6 | Bài đăng theo kênh, chia sẻ, trang tin công khai, cố vấn (giá, phòng trống, doanh thu), giọng nói | `copilot.py`, `Copilot.tsx`, `PublicListing.tsx` | `test_copilot.py`, `copilot.test.tsx` |

Vai trò `manager` không còn quyền nghiệp vụ. Route `/manager/*` được thay bằng `/landlord/*` và `/admin/*`. Trang giữ chỗ `OwnerWorkspace` đã bỏ vì có dashboard thật thay thế.

## 4. Việc tiếp theo

1. Demo đầu-cuối trên trình duyệt cho cả ba vai trò: ảnh hoặc video, để chốt G1, G2, G-NT.
2. Chạy test PostgreSQL (`HOMEMATCH_TEST_DATABASE_URL`) cho schema v9.
3. Deploy Railway; chạy GPT-4o/pgvector với ngân sách người dùng cấp (G3).
4. Mục còn "Một phần":
   - ảnh tin và ảnh sự cố (cần kho lưu file);
   - ưu đãi chăm sóc khách;
   - ý định chat `simulate_finance`;
   - số liệu chi phí bằng VND.
5. GĐ5: đánh giá nghiên cứu.
