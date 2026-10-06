# Chi tiết công việc tài liệu HomeMatch v1

**Cập nhật:** 04/10/2026. Đích là bộ docs có thể triển khai, nghiệm thu và vận hành sản phẩm HM-01–HM-10. Đây là checklist cần duy trì, không tự xác nhận sản phẩm đã xong.

## DOC-V1-01 — Research và nguồn

- [ ] Rà nguồn công khai HubHome, giữ ngày truy cập và phân loại từng phát hiện HH-01..12.
- [ ] Giữ khảo sát đăng nhập lịch sử riêng; không sửa ca rỗng thành ca thành công.
- [ ] Ghi các mâu thuẫn website: guide có hợp đồng/thu tiền nhưng FAQ/privacy tự mô tả prototype hoặc quy trình dự kiến.
- [ ] Mỗi quyết định HomeMatch chỉ rõ là áp dụng bài học hoặc yêu cầu riêng; không tự gán backend/thuật toán/quality HubHome.
- [ ] Quyền dùng inventory/media là đầu vào riêng, không suy từ quyền xem website.

**AC:** mọi nhóm chức năng có nguồn và giới hạn; các kết luận chưa xác minh được nhận diện, không làm cơ sở claim production.

## DOC-V1-02 — Product và glossary

- [ ] Chốt hành trình guest/renter/owner/manager/admin và HM-01..10 trong đặc tả.
- [ ] Đồng bộ CONTEXT về public listing vs AI recommendation, requested vs confirmed/reserved, contract vs tenancy, estimate vs invoice/evidence vs paid.
- [ ] Assumptions có thời điểm cần chốt, người phụ trách khi bước vào implementation và ảnh hưởng gate.
- [ ] Tách mandatory manual receipt/contract consent khỏi optional gateway/legal e-sign/video platform.
- [ ] Thay mọi scope MVP hiện hành trong master/plans; báo cáo lịch sử giữ nguyên phạm vi.

**AC:** đọc đặc tả không thể hiểu rằng contracts/invoices/meters/maintenance còn tùy chọn; current code không bị gọi v1 đã hoàn thiện.

## DOC-V1-03 — Requirements và quy trình

- [ ] Mỗi HM-R có source, actor, hành vi và AC-HM.
- [ ] Quy trình có tiền điều kiện, bàn giao, hậu điều kiện và lỗi quyền/stale/unknown/replay.
- [ ] Permission matrix áp dụng cả API/file/export/notification, không chỉ màn hình.
- [ ] State machines và audit bất biến cho moderation/recommendation/viewing/contract/tenancy/billing/maintenance.
- [ ] Ba E2E liên kết source→viewing, terms→invoice→payment, maintenance→move-out→deposit.
- [ ] NFR có tải/cấu hình/mục tiêu đề xuất, không đổi chỉ tiêu thành kết quả.

**AC:** đủ trace 30 requirements→30 AC, 10 modules; không có path publish/activate/paid bỏ qua kiểm quyền/phiên bản/xác minh.

## DOC-V1-04 — Thiết kế và plans

- [ ] Sinh OpenAPI v1 thực thi từ DTO đã khóa khi BE triển khai; giữ contract/snapshot 0.3.0 cho mã cũ.
- [ ] Đối chiếu kiến trúc target với migrations/checkpointer/worker/media thực tế sau mỗi gate.
- [ ] FE UI spec/screen/routes có empty/loading/error/stale/mobile/keyboard.
- [ ] HM module, W task và P gate thống nhất giữa backend/frontend/data/eval/infra/docs.
- [ ] Rule concurrency/version/idempotency/retention được chốt trước integration.
- [ ] Mọi sơ đồ và bảng được gắn target hoặc current phù hợp.

**AC:** cùng một sự kiện có status/recipient/quyền giống nhau trong process/API/UI/plan; không mô tả thành phần dự kiến như đã deploy.

## DOC-V1-05 — Evidence và hướng dẫn

- [ ] Cập nhật bảng current/gap sau run thực, có ngày/version/data/config và URL/path evidence.
- [ ] Soạn hướng dẫn renter, owner, manager, admin cho các nhiệm vụ có thật.
- [ ] Runbook có moderation/assignment/support/privacy, escalation, backup/restore/rollback và queue delivery.
- [ ] Ghi điều kiện môi trường, provider/schema/media và các hạn chế còn mở.
- [ ] Screenshot/video lấy từ release thật; fixture/demo phải ghi synthetic.
- [ ] Giữ evidence cũ/manifest freeze, tạo bản mới khi phát hành, không tái gắn nhãn.

**AC:** người khác chạy lại và vận hành tác vụ theo guide; không cần secret cá nhân hoặc chat/checkpoint private trong gói chia sẻ.

## DOC-V1-06 — Nghiên cứu và KLTN

- [ ] Tách mục tiêu sản phẩm hoàn chỉnh khỏi câu hỏi nghiên cứu extraction/ranking/cost/grounding/HITL.
- [ ] Dataset/config/prompt/method/protocol freeze trước test; labels relevance độc lập và được khóa.
- [ ] Báo paired samples/coverage/failures/unjudged/no-match; fallback không gán P.
- [ ] User study có protocol/consent/tasks/order/observations; chưa chạy không claim cải thiện hài lòng.
- [ ] Báo cáo đúng mẫu, bibliography nguồn đã đọc, lỗi/giới hạn/kết quả âm.
- [ ] Slide/demo/video thể hiện cả ba E2E khi sản phẩm đủ chức năng; hiện chỉ demo subset đúng mã đang có.

**AC:** số trong report/slide truy raw evidence, cấu hình và cách tính; synthetic/mẫu nhỏ/provider chưa chạy được công bố.

## DOC-V1-07 — Review và bàn giao

- [ ] Rà thuật ngữ, scope, roles, statuses, error codes và assumptions xuyên bộ docs.
- [ ] Kiểm local links/anchors/fences, uniqueness/coverage IDs và mapping AC.
- [ ] Chạy reviewer độc lập đọc các đường quyền/tiền/hợp đồng/public-vs-AI; sửa issue nghiêm trọng.
- [ ] Đối chiếu checklist với evidence, không đánh passed khi blocked/not_run.
- [ ] Gói source/docs/schema/data được phép chia sẻ/config/result/guide/slide/video theo manifest mới.
- [ ] Ghi review date, actual scope/checks, unresolved issues và người sở hữu.

**AC:** bộ tài liệu sẵn sàng review/triển khai; quyết định sẵn sàng release chỉ khi P4 đạt bằng chứng thực. Tài liệu có thể sẵn sàng dù sản phẩm chưa đạt P4, nhưng phải nói rõ hai trạng thái.
