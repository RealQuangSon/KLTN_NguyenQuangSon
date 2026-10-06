# Quy trình nghiệp vụ HomeMatch v1

**Cập nhật:** 04/10/2026. Tài liệu mô tả quy trình đích theo [đặc tả](dac-ta-san-pham.md). Các trạng thái hợp đồng/hóa đơn/sửa chữa chưa có trong backend 0.3.0. Dictionary đang chạy được giữ riêng tại [status-dictionary](status-dictionary.md).

## 1. Quyền và điểm bàn giao

| Tài nguyên/hành động | Renter | Owner | Manager | Admin |
|---|---|---|---|---|
| Tin công khai | Đọc projection published | Đọc | Đọc | Đọc |
| Tin nháp/media gốc/cập nhật kho | Không | Trong đơn vị có quyền | Trong đơn vị/phân công | Quản trị kiểm duyệt theo quyền; audit |
| Hồ sơ/chat và draft AI | Hồ sơ của mình; không đọc candidates pending | Không mặc định được đọc chat/ngân sách | Phiên được phân công | Chỉ truy cập đặc biệt có lý do/audit |
| Duyệt AI | Không | Không chỉ vì sở hữu phòng | Manager assigned, đúng version | Phải có assignment/capability phù hợp |
| Lịch xem | Lịch của mình, gửi/hủy/đề xuất đổi | Lịch liên quan phòng của mình, đề xuất slot | Xác nhận và cập nhật lịch được giao | Quản trị/điều phối theo quyền |
| Hợp đồng/tenancy/tài liệu | Bên thuê liên quan | Đơn vị/bên cho thuê liên quan | Có phân công và ủy quyền nghiệp vụ | Truy cập quản trị có audit |
| Công tơ/invoice/receipt | Đọc của mình, gửi chứng từ, phản ánh | Tạo/đối soát nếu được cấp quyền | Xác minh/phát hành trong phạm vi được giao | Đối soát/quản trị theo capability |
| Sửa chữa | Ticket liên quan quan hệ thuê của mình | Phòng/đơn vị liên quan | Ticket được giao | Phân công/quản trị |
| Role/assignment/audit/export | Hồ sơ/yêu cầu của mình | Membership được cấp quyền | Phân công trong đơn vị nếu có quyền | Theo quyền quản trị, không bỏ access check |

Server suy ra organization, ownership và assignment từ dữ liệu đã xác thực. Người gửi không thể thay những trường này bằng patch tùy ý. Chuyển người phụ trách phải ghi audit và thu hồi phạm vi đọc của người cũ theo policy; không đổi chủ sở hữu session.

## 2. Nguồn phòng: soạn → kiểm duyệt → công bố

**Tiền điều kiện:** owner có membership, quyền dùng ảnh/dữ liệu và phòng thuộc đơn vị. Owner nhập thông tin/phí, metadata nguồn và độ chính xác vị trí, lưu draft rồi gửi revision cần duyệt. Manager kiểm completeness, bằng chứng, nội dung public/private và quyết định publish hoặc yêu cầu sửa.

`draft → submitted → published` hoặc `submitted → changes_requested → submitted`. Tin published có thể suspended/archived. Khi sửa trường ảnh hưởng lựa chọn như giá/phí/địa chỉ/tiện ích bắt buộc, tạo revision pending; public tiếp tục dùng bản approved trước nếu vẫn hợp lệ, hoặc ẩn ngay nếu dữ liệu cũ không còn đúng. Không công bố ngầm thay đổi pending.

Phòng thực có `physical_room_id` ổn định, khóa duy nhất theo organization/building/room_code; listing/source IDs và draft/published revisions riêng. Migration từ `room.id` 0.3.0 cần mapping được rà, không tự hợp nhất hai phòng chỉ vì giống địa chỉ. Matching/availability/lease dedup và khóa theo phòng thực, không theo từng tin.

Availability riêng: `unknown / available / reserved / occupied / unavailable`. Reservation phải có thỏa thuận, actor, khoảng kỳ `[start,end)`, expiry và xử lý hết hạn; lịch xem không tạo reservation. Reservation còn hạn và active contract/planned tenancy tạo allocation kiểm overlap trong transaction. Conversion reservation→contract allocation nguyên tử; expiry contract không giải phóng occupied khi chưa bàn giao ra. Archived không hard-delete room đã tham chiếu trong run/viewing/lease/invoice.

**Ngoại lệ:** thiếu phí vẫn giữ unknown, nhưng không dùng phòng đó cho hard constraint tổng phí cần xác định. Tin bị báo sai được triage; suspension thu hồi public projection và làm gợi ý liên quan mất hiệu lực, không xóa bằng chứng giao dịch lịch sử.

## 3. Tìm phòng và tư vấn

Public search dùng tin published/available theo filters; người thuê có thể xem detail và map gần đúng. Khi chọn tổng phí, phải nhập/kiểm tra scenario. Public projection không chứa địa chỉ chính xác/liên hệ private nếu chưa có quyền.

Assistant nhận ý định. Câu chỉ tính phí gọi finance service với quote/scenario; câu hỗ trợ tạo ticket; câu chưa đủ dữ liệu hỏi rõ. Tìm phòng tạo draft, hiển thị `unknown/inferred/confirmed` và nguồn từng trường. Người thuê xác nhận nhu cầu/scenario/ngân sách → profile version mới → hard filter → B1/P → nháp pending → manager review → published/current.

Quản lý approve subset và thứ tự, reject hoặc needs_revision. Decision commit trước resume; `reviewed` chưa là `published`. Finalize và đọc kết quả đều kiểm active run, profile và catalog. Thay đổi làm stale thì không công bố từ approval cũ. Retry generation có thể tạo run mới cho cùng profile đã xác nhận, nhưng cần review mới.

Không có phòng hợp lệ (`no_match`), thiếu bằng chứng (`needs_verification`), lỗi provider (`ai_unavailable`) và chờ duyệt (`pending_review`) có thông điệp/bước tiếp theo riêng. Không biến lỗi dịch vụ thành kết luận kho không có phòng. Model không tự nới điều kiện cứng; người thuê tự chấp thuận điều chỉnh.

## 4. Lưu, so sánh và lịch xem

Favorites lưu listing ID cùng physical room ref và metadata cần thiết; đọc lại trạng thái mới. History hiển thị phiên và snapshot theo consent, nhưng kết quả cũ không thành current. Compare dùng 2–3 phòng thực khác nhau cùng scenario và một mode: `public_catalog` hoặc `ai_recommendation`. Public refs có listing ID/published revision; AI refs có run/profile/catalog versions và room IDs cùng run published/current. Không ghép pending hoặc chạy lại phép tính trên quote mới mà giữ nhãn approval cũ.

Renter chọn lịch tương lai có múi giờ. Public viewing tham chiếu room revision published; AI viewing tham chiếu thêm run/profile version. Gửi `requested`; owner có thể gợi slot, manager được phân công kiểm tình trạng/slot và confirm hoặc decline. Đổi lịch tạo đề xuất mới cần xác nhận, lưu lịch sử; cancel/reschedule ghi lý do, actor, thông báo. UI hiển thị giờ Việt Nam, server lưu timestamp có timezone.

`requested → confirmed / declined / cancelled`; `confirmed → completed / no_show / cancelled`. Đổi lịch không tự chuyển thành confirmed. Trùng slot xử lý trong transaction cho cùng phòng/người phụ trách; tài nguyên đã hết phòng cần báo lại, không âm thầm giữ lịch hợp lệ. Notification failure không đổi confirmed về requested.

## 5. Hợp đồng và vào ở

Sau buổi xem hoặc lựa chọn trực tiếp, bên được ủy quyền tạo draft hợp đồng gắn phòng, bên thuê/bên cho thuê, kỳ hạn, rent/fees, kỳ thu, số cọc, trả trước, điều khoản bàn giao/chấm dứt và tài liệu. Hai bên nhận cùng version và chấp thuận; thay bất kỳ điều khoản cần chấp thuận tạo version mới và xóa hiệu lực acceptance cũ.

`draft → pending_acceptance → active / cancelled`; active có thể `termination_pending → ended`, hoặc `expired`. Activation chỉ khi đủ chấp thuận/quyền và không xung đột kỳ thuê. Tính toàn vẹn không phụ thuộc agent hoặc nút xác nhận UI. Ứng dụng ghi nhận tài liệu và ý chí chấp thuận; việc này không tự là chứng nhận chữ ký điện tử hợp lệ pháp lý.

Tenancy riêng: `planned → active → ending → closed` hoặc `planned → cancelled`. Move-in cần biên bản bàn giao, ngày, inventory tài sản, chỉ số đầu và trạng thái cọc/trả trước có chứng từ. Hợp đồng active chưa đủ tự giả rằng người thuê đã vào ở. Transaction chặn hai tenancy hiệu lực giao nhau cho một phòng. Cùng key retry activation/move-in trả cùng bản ghi.

## 6. Công tơ, hóa đơn và đối soát

Theo kỳ `[start,end)`, owner/người được giao ghi chỉ số tích lũy công tơ có ảnh, timestamp, công tơ/phòng và nguồn. Consumption = end reading − start reading; chỉ số cuối ≥ đầu. Replacement/reset phải có old-last và new-first reading; consumption là tổng hiệu hợp lệ từng công tơ. Thiếu đoạn giữ unknown, không tự nối hai dãy chỉ số. Correction lưu sự kiện/lý do/xác minh; estimate không giả số thực đo.

Mặc định rate snapshot lấy tại đầu kỳ; giá đổi giữa kỳ áp dụng kỳ kế tiếp. Chỉ chia rate segments trong kỳ khi có amendment được hai bên chấp thuận và boundary reading thực đo cho từng đoạn; không suy lượng tiêu thụ theo tỷ lệ ngày. Phí người/xe lấy quantity đã chốt cho kỳ; thay giữa kỳ theo cùng rule amendment. Pro-rate rent khi vào/ra giữa tháng dùng số ngày thực trong tháng lịch theo điều khoản đã chốt, có ngày/công thức/source; oracle phải kiểm ranh tháng/kỳ, không chọn công thức sau khi thấy kết quả.

Người có quyền kiểm draft invoice: kỳ, rent phân bổ, điện/nước, phí cố định/người/xe, credit thuê trả trước, khoản sửa chữa được duyệt và khoản điều chỉnh. Mỗi dòng có quantity/unit/rate/source/rounding; missing data chặn issued hoặc phải có ngoại lệ ước tính được công khai/chấp thuận đúng policy. Tiền cọc giữ trong sổ cọc, không mặc định thành tiền thuê hoặc receipt trả hóa đơn.

Invoice có ba trục: lifecycle `status = draft / issued / void`; `payment_status = unpaid / partially_paid / paid` theo allocation và số phải thu; `overdue = true` khi issued, balance > 0 và thời điểm hiện tại vượt due_at. Một invoice có thể vừa partially_paid vừa overdue. Issued chỉ void trực tiếp khi chưa có receipt allocation; trường hợp đã phân bổ cần reversal/adjustment đúng ledger trước khi void. Issued không sửa/xóa âm thầm.

Renter gửi evidence thanh toán → `submitted`; người có quyền kiểm tài khoản/số tiền/thời điểm/nguồn → `verified` hoặc `rejected`. Chỉ receipt verified được phân bổ invoice. Số đã trả là tổng allocation hợp lệ, còn nợ = tổng phải thu sau adjustments − allocation; dư giữ unallocated credit hoặc refund có phê duyệt. Replay key không tạo receipt/allocation thứ hai. Void/reversal phải để audit và bản ghi đối ứng.

Nhắc tiền/hóa đơn qua outbox; trạng thái gửi pending/delivered/failed không thay số dư. Tranh chấp gắn line/receipt và trạng thái xử lý, không tự đánh dấu paid để tắt nhắc.

## 7. Sửa chữa

Renter đang có quan hệ thuê liên quan tạo ticket kèm mô tả/ảnh, địa điểm, mức ưu tiên và lựa chọn thời gian vào phòng. Khẩn cấp hiển thị hướng dẫn liên hệ người phụ trách ngay; sản phẩm không hứa có đội cấp cứu nếu chưa có quy trình đó.

`submitted → triaged → scheduled → in_progress → resolved → closed`; ticket chưa triển khai có thể cancelled. Người phụ trách triage/phân công và đề xuất cost event có payer. Khi renter phải trả, cần renter chấp thuận đúng khoản/version hoặc căn cứ terms snapshot được người có quyền xác minh; owner duyệt việc kỹ thuật không đủ để charge renter. Khoản disputed giữ riêng chờ xử lý, chưa đưa vào phải thu xác định. Resolved cần mô tả/bằng chứng công việc. Renter xác nhận close hoặc reopen về triaged kèm lý do. SLA có giờ phục vụ và người nhận escalation, không tự suy ra từ mức ưu tiên.

Chi phí người thuê phải trả được chuyển sang invoice bằng tham chiếu ticket/cost event đã duyệt, duy nhất một lần; đóng ticket không tự tạo thu tiền. Ảnh bên trong phòng là dữ liệu private.

## 8. Trả phòng và kết thúc

Người có quyền gửi đề nghị chấm dứt theo điều khoản; hai bên xác nhận lịch bàn giao. Ghi tài sản/chỉ số cuối, invoice cuối, công nợ và sổ cọc. Deduction có trạng thái proposed/accepted/disputed, chứng từ, payer và acceptance của renter hoặc căn cứ terms được xác minh. Disputed amount có thể được giữ để xử lý theo policy nhưng chưa là deduction đã quyết toán. Invariant: tổng cọc đã nhận = tổng đã hoàn + khấu trừ hợp lệ + số còn giữ; reversal/correction có event đối ứng. Hoàn cọc phải có bằng chứng chuyển tiền/receipt refund; không đánh dấu refunded chỉ từ nhấn nút.

Tenancy closed khi bàn giao và các khoản quyết toán đã hoàn thành hoặc có tranh chấp/khoản nợ được ghi nhận chuyển xử lý riêng theo policy. Tách `settlement_status=pending/disputed/settled`: closed mô tả kết thúc việc ở, chưa khẳng định tiền/cọc đã quyết toán; disputed hold không thể thành settled trước giải quyết hợp lệ. Cập nhật availability sau kiểm tra phòng; kết thúc thuê không tự public lại tin archived/suspended. History/tài liệu theo retention; xóa tài khoản không hard-delete ledger nghĩa vụ còn hiệu lực.

## 9. Thông báo, hỗ trợ và ngoại lệ hệ thống

Mọi nghiệp vụ quan trọng commit event và outbox cùng transaction. Worker gửi in-app/email theo recipient projection, dedup key và retry có hạn; lỗi cuối vào queue cần người xử lý. Email không mang raw chat, hợp đồng hay chứng từ private; dùng link yêu cầu đăng nhập. Ticket hỗ trợ liên quan session/viewing/lease/invoice và chỉ người có quyền đọc.

Khi mất mạng, mutation quan trọng giữ payload/key; đọc state trước retry nếu endpoint chỉ dùng CAS. 409 không tự ghi đè; 401 yêu cầu đăng nhập lại và bảo toàn draft an toàn theo policy; 503 nêu tác vụ chưa rõ/đang xử lý và cách đọc lại. Lưu lịch sử nghiệp vụ và lỗi bằng reference, không log nội dung nhạy cảm.
