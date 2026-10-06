# Đề cương KLTN — HomeMatch: nền tảng tìm và quản lý thuê phòng với trợ lý AI

**Cập nhật:** 04/10/2026. **Định hướng:** sản phẩm v1 hoàn thiện toàn vòng đời thuê. Đây là đề cương và thiết kế nghiên cứu, chưa phải báo cáo kết quả hoặc đề cương đã được giảng viên phê duyệt.

**Tên tiếng Anh đề xuất:** HomeMatch: An AI-assisted Room Rental and Management Platform with Cost Transparency and Human Review.

## 1. Bối cảnh và vấn đề

Người tìm phòng diễn đạt nhu cầu bằng ngôn ngữ tự nhiên, trong khi catalog dùng địa chỉ, giá, tiện ích và tình trạng có cấu trúc. Giá thuê riêng chưa cho thấy chi phí theo tháng và tiền cần chuẩn bị khi vào ở. Sau khi chọn phòng, lịch xem, điều khoản, bàn giao, phí công tơ, thanh toán và sửa chữa cần được nối bằng dữ liệu/quyền/trạng thái rõ ràng.

[Nghiên cứu HubHome](nghien-cuu-hubhome.md) ngày 04/10 và [khảo sát đăng nhập lịch sử](khao-sat-hubhome-da-dang-nhap.md) ngày 01/10 là nguồn tham khảo. Trải nghiệm chat–criteria–preview, nhóm chi phí, so sánh, bước người thật xác nhận và portal owner/rental operations giúp xác định phạm vi. Mô tả công bố hoặc màn hình trống không chứng minh chất lượng AI, backend hay khả năng vận hành toàn bộ của HubHome.

Yêu cầu mới của người dùng là sản phẩm hoàn thiện. Đề cương này thay thế giới hạn MVP gọn của bản trước; không tự áp một thời hạn hoặc cam kết chất lượng mới.

## 2. Mục tiêu sản phẩm và đóng góp nghiên cứu

**Mục tiêu sản phẩm:** đủ HM-01–HM-10 theo [đặc tả](dac-ta-san-pham.md), chạy toàn bộ hành trình từ tin của owner tới tìm/chọn/xem/thuê, một kỳ thu và sửa chữa/trả phòng. Bốn vai trò, quyền theo đơn vị/bản ghi, dữ liệu có nguồn, tài chính xác định và khả năng vận hành là điều kiện hoàn thành.

**Đóng góp nghiên cứu:** phương pháp hỗ trợ quyết định tìm phòng bằng extraction có xác nhận, hard constraints dựa tổng chi phí, kết hợp structured/semantic ranking, giải thích có bằng chứng và gate quản lý. Các module hợp đồng/billing/maintenance tạo sản phẩm liên tục; không mặc định mọi module đều là đóng góp AI mới.

| Câu hỏi | Phép đo để trả lời | Giới hạn cần giữ |
|---|---|---|
| RQ1: Extraction từ tiếng Việt nhận đúng ý định/trường và biết khi cần hỏi rõ đến đâu? | Intent accuracy, field precision/recall/F1, coverage, ambiguity cases, invalid output/fallback | Cùng schema/inputs; rules khác live model; không đo fixture thành chất lượng GPT |
| RQ2: P so với B1 cải thiện thứ hạng trên cùng điều kiện đủ và chi phí không? | Paired nDCG@5, relevance coverage, eligible-set audit, error/no-match rates | Nhãn độc lập; unjudged không thành negative; chỉ tune dev |
| RQ3: Ước tính/giải thích và HITL có giữ đúng dữ liệu/quyền/version không? | Cost oracle exact VND, hard-constraint violations, claim-evidence checks, stale/privacy/replay tests | Invariants chứng minh correctness trong ca đã kiểm, không tự chứng minh satisfaction |
| RQ4: Người dùng hoàn thành tác vụ và hiểu chi phí/trạng thái đến đâu? | Task success/time, hiểu subtotal/unknown/requested/paid, observations và questionnaire đã pilot | Study có protocol/người thật; mẫu nhỏ là thăm dò, không khái quát thị trường |
| RQ5: Độ trễ, số calls/tokens/chi phí của cấu hình đã chọn là bao nhiêu? | Latency distribution/error/timeout, provider reported usage và giá có ngày | Tách generation với thời gian chờ người duyệt; lượt thiếu usage phải báo |

Không hứa P phải thắng B1 hoặc hứa hệ thống làm tăng hài lòng trước khi đo. Kết quả âm là kết quả nghiên cứu hợp lệ, nhưng lỗi quyền hoặc sai tiền vẫn phải sửa trước phát hành.

## 3. Phạm vi hệ thống

| Module | Nội dung bắt buộc |
|---|---|
| HM-01 | Account verification/reset/profile/consent, roles/membership/sessions |
| HM-02 | Owner inventory/media/source/moderation/availability |
| HM-03 | Public catalog/filter/detail/map/report |
| HM-04 | AI conversation/confirmation/cost/ranking/HITL/grounded explanation |
| HM-05 | Favorites/saved searches/account history/compare |
| HM-06 | Viewing lifecycle/handoff/support/in-app/email notifications |
| HM-07 | Contract/acceptance/tenancy/reservation/move-in/out/deposit |
| HM-08 | Meter/rate/invoice/receipt allocation/reconciliation/refund/dispute |
| HM-09 | Maintenance/assignment/schedule/cost approval/reopen |
| HM-10 | Admin/audit/privacy/dashboard/queues/deploy/restore/operations |

Phòng trọ/studio TP.HCM là phạm vi dữ liệu ban đầu; không mua nhà/vay hoặc chấm tín dụng. Payment gateway, legal e-sign provider, video-call platform, AI ảnh/giọng và toàn quốc là mở rộng. Ghi nhận hợp đồng/chấp thuận và payment evidence/receipt/reconciliation vẫn là bắt buộc, không bị loại cùng các tích hợp tùy chọn.

## 4. Phân tích và thiết kế

Nguồn yêu cầu: HH-01–HH-12 + quyết định HomeMatch + constraints thực tế repository. [Danh mục yêu cầu](yeu-cau-san-pham.md) có 30 ID và nguồn; [quy trình](quy-trinh-nghiep-vu.md) có quyền/trạng thái/bàn giao; [AC](tieu-chi-nghiem-thu.md) chốt hoàn thành. Tin công khai đã kiểm duyệt khác gợi ý AI đã duyệt; contract active khác move-in; uploaded chứng từ khác verified receipt.

[Kiến trúc](kien-truc-homematch.md) đích là modular monolith React/TypeScript + FastAPI + PostgreSQL/pgvector + private storage + outbox worker. Agent logic ở backend; code quyết định money/permission/hard filters/publication. Một API worker được giữ tới khi audit concurrency/checkpoint. SQLite/offline và rule/B1 là đường demo/regression, không thành release production hoặc benchmark live.

## 5. Phương pháp trợ lý

1. Phân loại ý định và trích xuất vào draft có field status/provenance.
2. Hỏi rõ hoặc form cho phần thiếu; không tự confirmed ngân sách từ câu chat.
3. Confirm profile/scenario theo revision → immutable snapshot/version → active run.
4. Tính cost, hard filter từ đúng catalog snapshot; unknown không giả đáp ứng.
5. B1 chấm cấu trúc; P = `(1-alpha)*B1 + alpha*semantic_fit`, normalization/alpha khóa trên dev.
6. Tạo draft có evidence/reason/tradeoff; manager assigned approve subset/order đúng version.
7. Commit decision → resume → finalize kiểm active/profile/catalog trong transaction; renter chỉ đọc published/current.
8. Provider unavailable/failure/no_match/needs_verification/pending có trạng thái riêng; hỗ trợ người thật có ticket và người nhận.

B1 và P dùng cùng eligible set/quote/scenario. Với catalog nghiên cứu nhỏ, exact semantic chấm toàn eligible set; ANN/shortlist là protocol khác phải nêu riêng. Semantic text không chứa budget/contact/private chat. Tool đọc hợp đồng/invoice về sau kiểm quyền; LLM không kích hoạt thuê/phát hành invoice/xác nhận tiền.

## 6. Finance và ledger

Engine hiện có dùng Decimal và ROUND_HALF_UP VND. Monthly = rent + các phí định kỳ theo scenario; initial = deposit + rent×advance_months + one-time + moving + setup. Known subtotal không là total khi thiếu khoản. Khoản included được hiển thị 0 có nguồn, khác unknown.

Mở rộng sản phẩm cần billing engine và oracle riêng: actual meter/rate theo kỳ, rent advance credit, issued immutable snapshots, adjustments, verified receipts/allocations, overpayment/refund/dispute và deposit ledger. Không dùng scenario ước tính của người tìm phòng làm actual consumption. Tính đúng ledger là nghiệm thu chức năng, không phải chất lượng sinh ngôn ngữ.

## 7. Dữ liệu và nguồn

Mã hiện có 80 phòng tổng hợp TP.HCM, pilot 25, 30 gold profiles (10 dev/20 test) và 15 cost oracle cases. Đây là hiện vật development, chưa mặc định là tập test nghiên cứu đã freeze hoặc nhãn relevance độc lập đã chấm.

Để v1 cần thêm fixtures bốn role/đơn vị, owner media/moderation, lịch, terms/acceptances, tenancy, readings, invoices/receipts/deposit và maintenance. Development/test dùng synthetic có nhãn. Public operation cần catalog/media được phép dùng, source register và kiểm tra độ mới; quyền xem HubHome không là quyền crawl/export dùng kho.

Mỗi record có ID/version/source/time/unit/privacy/synthetic phù hợp. Split theo profile gốc, không đặt paraphrase cùng người dùng ở dev/test. Gold extraction và oracle money do người kiểm độc lập rà; relevance labels khác field gold và cost oracle.

## 8. Thiết kế đánh giá

| Lớp | Điều kiện đo | Đầu ra |
|---|---|---|
| Component correctness | Offline fixture/oracle, schema/constraint/rights/state/replay | Actual pass/fail + config/data, không quality live |
| Live extraction | Provider/model/prompt/schema đã chọn, budget được chốt, test sau freeze | Per-field/intent metrics, invalid/fallback/calls/latency |
| Ranking B1/P | Cùng test profiles/catalog/eligible, độc lập relevance rubric/pool | Paired defined samples, nDCG@5/coverage/error/no-match |
| Product integration | Browser/API/PG/storage/worker thật, bốn roles | Ba E2E, permissions/race/fault/restoration và NFR |
| User study | Recruitment/consent/protocol, cùng tasks và counterbalanced order | Success/time/comprehension/satisfaction + limits |
| Operations | Staging release config, load/backup/restore/delivery | p95/errors/RPO/RTO/runbook evidence |

Freeze catalog/profiles/splits/model/prompt/ranking config và code trước test research. Pool dựng bằng các phương pháp thực báo cáo, chấm blind rồi khóa nhãn; unjudged không mặc định âm tính. So sánh paired trên cùng profile IDs đủ defined, báo exclusions/coverage. Thiếu live provider/nhãn/người thử thì báo chưa đo, không điền số kỳ vọng.

Các mức F1/nDCG/grounding/latency của kế hoạch trước là mục tiêu lịch sử, không phải kết quả. Protocol mới cần ghi mục tiêu/denominators trước freeze; mọi công bố số có run/config/hash và giới hạn synthetic/mẫu nhỏ.

## 9. Cơ sở nghiên cứu liên quan

Nguồn metadata/abstract được đối chiếu ngày 04/10/2026; phần tổng quan của báo cáo cuối cần đọc toàn văn, chọn luận điểm và trích dẫn tương ứng.

- [A Survey on Conversational Recommender Systems](https://arxiv.org/abs/2004.00646): tham khảo phân loại tương tác, ý định và hướng đánh giá.
- [Evaluating Conversational Recommender Systems: A Landscape of Research](https://arxiv.org/abs/2208.12061): phân biệt chất lượng thành phần với cảm nhận người dùng, làm cơ sở tách benchmark và study.
- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629): tham khảo việc phối hợp model và công cụ; không chứng minh cần nhiều agent hoặc dùng kết quả paper làm số của HomeMatch.
- [Nghiên cứu HubHome](nghien-cuu-hubhome.md): nguồn sản phẩm/nghiệp vụ với mức bằng chứng cụ thể, không là benchmark thuật toán.

## 10. Kế hoạch và bàn giao

[Kế hoạch W-01–W-18](ke-hoach-trien-khai.md), [phân công](ke-hoach-tung-phan.md) và [plan chi tiết](ke-hoach-chi-tiet.md) thay bộ MVP cũ. P0 contract → P1 accounts/catalog → P2 discovery/AI → P3 rental operations → P4 release hoàn thiện. P5 nghiên cứu trên inputs đã freeze. Docs/data/oracles/FE mock/infra làm đồng thời theo dependencies.

Gói bàn giao sản phẩm: source/schema/API/docs, fixture có quyền, cấu hình không secret, báo cáo QA/evidence, user/admin guides/runbook, release manifest mới và demo/video release thật. Gói KLTN thêm protocol/raw runs/nhãn được phép công bố/báo cáo theo mẫu/slide. Không đưa DB thật/raw chat/checkpoint/media private vào source công khai.

## 11. Rủi ro, đầu vào và giới hạn

| Đầu vào/rủi ro | Cách xử lý |
|---|---|
| Phạm vi sau thuê lớn hơn MVP | Chia lát theo W/P, reuse core; không tự cắt module mandatory để giữ lịch cũ |
| Không có inventory/media được phép | Dùng synthetic dev; public release chờ nguồn hợp lệ |
| Thiếu provider/ngân sách/người chấm | Tiếp tục offline correctness; không claim live benchmark |
| Chưa có policy/nhân sự vận hành | Ghi owner quyết định và gate; không hứa pháp lý/SLA/delivery chưa kiểm chứng |
| Race/stale/retry đổi tiền/quyền/availability | Transaction/CAS/idempotency/ledger/audit và negative/fault tests |
| Synthetic/mẫu nhỏ | Hạn chế kết luận, study thăm dò và không đo thị trường từ benchmark local |
| Mẫu trường/giảng viên chưa chốt | Xem tên/đề cương là đề xuất; sửa format/đóng góp theo yêu cầu đã xác nhận |

## 12. Tiêu chí nghiệm thu dự kiến

Phần này giữ điểm dẫn từ đề cương cũ. Bộ tiêu chí hiện hành là [30 AC-HM và NFR](tieu-chi-nghiem-thu.md), không còn AC01–AC16 của MVP. Sản phẩm chỉ hoàn thiện khi P4 đạt toàn phạm vi; nghiên cứu chỉ có kết luận khi P5 đủ evidence.

Tại 04/10/2026, repository có nền tảng 0.3.0 và bằng chứng lịch sử; chưa đạt P1–P4/P5 theo scope mới. Viết lại docs không triển khai các module còn thiếu. [Bảng trạng thái](trang-thai-trien-khai.md) ghi khoảng cách thực tế.
