# Rà soát bộ tài liệu sản phẩm HomeMatch v1

**Ngày:** 04/10/2026. **Phạm vi:** viết lại research/scope/requirements/process/AC/architecture/UI/API đích và các plan cho sản phẩm hoàn thiện. Đối chiếu mã 0.3.0 để ghi current/gap; chỉ kiểm tài liệu, không chạy lại test ứng dụng, live model hoặc deployment.

[Bộ docs](README.md) xác định nguồn hiện hành và [trạng thái sản phẩm](trang-thai-trien-khai.md) ghi các gate chưa đạt.

## 1. Kết luận

**Bộ tài liệu sẵn sàng để review và bắt đầu triển khai v1 theo W-01/W-02.** Phạm vi đủ HM-01–HM-10, từ tìm phòng tới vận hành sau thuê. P0 implementation contract chưa được đóng vì cần OpenAPI/schema/migrations thực thi và rà đầu vào. P1–P4 sản phẩm và P5 nghiên cứu đều chưa đạt.

Viết lại docs không làm sản phẩm đã hoàn thiện. Các số test/bằng chứng cũ vẫn có ngày và phạm vi; API 0.3.0, snapshot OpenAPI và manifest 01/10 không được gắn nhãn v1.

## 2. Thay đổi chính

| Hạng mục | Kết quả trong bộ tài liệu mới |
|---|---|
| Phạm vi | 10 module bắt buộc, bốn role và organization/bản ghi isolation |
| Research | HH-01..12; public 04/10, lịch sử 01/10, website claims và đề xuất riêng tách rõ |
| Chức năng sau thuê | Contracts/tenancy/handovers/deposit, meter/invoice/receipt allocation/reconciliation và maintenance bắt buộc |
| Traceability | 30 HM-R → 30 AC-HM, W-01..18 và plans chuyên môn; NFR đề xuất có tải/cấu hình/cách đo |
| Trải nghiệm | Public catalog khác AI HITL; 21 màn target, mobile/tablet/keyboard/stale/error; current code riêng |
| Vận hành | Outbox/in-app/email/private media/audit/privacy/restore/rollback; một API worker đến audit |
| Nghiên cứu | P5 freeze/labels/paired metrics riêng; không nDCG thay E2E hoặc fixture thay live quality |

## 3. Các vấn đề phát hiện khi review và đã sửa

Các mức ảnh hưởng dưới đây áp dụng cho tài liệu thiết kế, không phải lỗi runtime mới đã chứng minh.

| ID | Vấn đề | Quyết định đã đồng bộ |
|---|---|---|
| DOC-R01 | Catalog public dễ bị đồng nhất với AI gợi ý đã duyệt | Public published listing projection riêng; nháp AI vẫn hidden; mode/source_mode có discriminator và revision refs |
| DOC-R02 | Overdue loại trừ partially_paid trong máy trạng thái | Lifecycle draft/issued/void, payment_status unpaid/partially_paid/paid, overdue derived flag riêng |
| DOC-R03 | Owner duyệt chi phí có thể bị hiểu đủ charge renter | Cost event có payer, đúng bên chấp thuận hoặc terms snapshot được xác minh; disputed chưa thành phải thu xác định |
| DOC-R04 | Cọc tranh chấp có thể bị coi đã khấu trừ | Proposed/accepted/disputed; hold chưa settled; invariant cọc và receipt/allocate/refund; closed tenancy khác financial settlement |
| DOC-R05 | Chống thuê trùng theo tin đăng bỏ lọt cùng phòng nhiều nguồn | Physical room ID ổn định, listing ID/revision riêng; allocation/overlap/dedup theo phòng thực |
| DOC-R06 | Active contract/planned tenancy và reservation chưa thống nhất giữ kỳ | Reservation interval/expiry, conversion atomic, active/planned allocation transaction; expired contract không release occupied trước move-out |
| DOC-R07 | Rate đổi giữa kỳ và meter replacement chưa đủ expected oracle | Kỳ [start,end), rate đầu kỳ, amendment+boundary reading mới chia segment; sum deltas từng công tơ, missing giữ unknown |
| DOC-R08 | Video/email scope khác giữa research và spec | Tour/media/link hỗ trợ v1; video-call riêng mở rộng; in-app+email giao dịch v1 bắt buộc |
| DOC-R09 | Consent opt-out dễ bị hiểu xóa toàn ledger/checkpoint | Lịch sử dài hạn consent riêng, dữ liệu tối thiểu có purpose/TTL/retention công khai; không giữ history bằng tên checkpoint |
| DOC-R10 | Plans G4/62 task cũ dễ trở thành scope mới | HM/W/P là nguồn hiện hành; CLI ack-G4 giữ guard hiện có và cần version protocol khi freeze P5 |

## 4. Các kiểm tra tài liệu đã thực hiện

- Kiểm 55 file Markdown, 330 liên kết/anchors nội bộ và 34 khối code bằng công cụ kiểm nội bộ: không có đường dẫn/anchor thiếu hoặc code fence chưa đóng. Đây là kiểm cấu trúc, không là số liệu test ứng dụng.
- Kiểm 30 requirement ID và 30 acceptance ID không trùng, mapping AC trong requirements khớp danh mục nghiệm thu.
- Kiểm đủ 12 nhóm HH của nghiên cứu, scope 10 HM xuyên các plan, UI spec 21 màn/16 UI-V và FE plan 18 task.
- Rà độc lập các đường công bố/quyền/contract/tenancy/billing/cọc và nguồn nghiên cứu; sửa các điểm DOC-R01..10.
- Đối chiếu tên/metadata/abstract ba nguồn học thuật trong đề cương qua trang gốc; nghiên cứu HubHome đọc website công khai, không thao tác tài khoản/giao dịch.

Kiểm tra đường dẫn không chứng minh website/link ngoài luôn truy cập được, không kiểm layout browser hoặc backend. Báo cáo tự động sau lần sửa cuối là bằng chứng cấu trúc docs; không thay kiểm chứng sản phẩm.

## 5. Quyết định và đầu vào còn cần ở triển khai

| Đầu vào | Chủ trách nhiệm cần xác định | Gate |
|---|---|---|
| Schema/DTO/OpenAPI thực thi, migration room/organization và retry/key TTL | Backend + FE + người sở hữu domain | P0/P1 |
| Catalog/media hợp lệ, quyền dùng và quy trình xác minh | Owner/data/operations | P1 trước public operation |
| Email/map/private storage provider và cấu hình môi trường | Infra + product owner | P1/P2/P4 |
| Terms, retention/privacy, dispute/refund và giờ hỗ trợ | Product owner + người vận hành phù hợp | P3/P4 trước dùng dữ liệu/giao dịch thật |
| Model/embedding/config/budget và labels/judges/study protocol | Agent + eval + người đánh giá độc lập | P2 release AI integration; P5 research |
| Mẫu trường/tên đề tài/phạm vi đóng góp được chấp nhận | Sinh viên + giảng viên | Bàn giao KLTN |

Các đầu vào này không ngăn dùng bộ docs để phát triển độc lập bằng synthetic fixtures. Chỉ đóng gate sau evidence thực. Không có đợt test/live/deploy mới trong lần viết lại này; [các tiêu chí nghiệm thu](tieu-chi-nghiem-thu.md) vẫn là việc phải thực hiện.
