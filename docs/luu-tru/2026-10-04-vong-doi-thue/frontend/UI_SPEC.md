# Đặc tả giao diện sản phẩm HomeMatch

**Cập nhật 04/10/2026 — chuẩn mục tiêu toàn vòng đời thuê.** Tài liệu mô tả màn hình, dữ liệu, trạng thái và tiêu chí kiểm tra cho sản phẩm hoàn chỉnh; không giới hạn ở luồng tìm phòng hiện tại. Đọc cùng [đặc tả sản phẩm](../docs/dac-ta-san-pham.md), [yêu cầu](../docs/yeu-cau-san-pham.md), [quy trình](../docs/quy-trinh-nghiep-vu.md), [nghiệm thu](../docs/tieu-chi-nghiem-thu.md) và [API mục tiêu v1](../docs/api-san-pham-v1.md).

## 1. Bằng chứng, hiện trạng và phạm vi

| Nhãn | Ý nghĩa | Áp dụng |
|---|---|---|
| Quan sát HubHome | Đã đọc/thao tác giao diện tại ngày khảo sát, không suy backend | Landing/composer và AI workspace công khai; tổ chức 11 trang người thuê ngày 01/10 |
| HubHome công bố | Nội dung website tự mô tả, chưa thử có dữ liệu | Hợp đồng, đối chiếu tiền, công tơ, sửa chữa, xem trực tuyến và owner portal |
| Thiết kế HomeMatch | Quyết định cho sản phẩm của dự án | HITL trước gợi ý AI; portal bốn vai trò; screens/flows sau thuê và tiêu chí nghiệm thu |
| Đã có source | Thành phần tìm thấy trong repository, khác với đã nghiệm thu | React/TypeScript, Landing, App, RenterWorkspace, ManagerWorkspace, API client và components |
| Chưa triển khai | Yêu cầu phải xây/kiểm chứng để phát hành đầy đủ | Các routes mới, owner/admin, map/media/lưu tin/lịch sử/thông báo/vận hành thuê |

Nguồn: [nghiên cứu công khai 04/10/2026, HH-01…HH-12](../docs/nghien-cuu-hubhome.md), [khảo sát đăng nhập 01/10/2026](../docs/khao-sat-hubhome-da-dang-nhap.md), đo style công khai 02/10 ghi dưới đây. Card/compare có dữ liệu, owner dashboard và giao dịch sau thuê của HubHome chưa được kiểm chứng đầy đủ. Không gọi các thiết kế tương ứng là bản sao đã xác minh.

**API hiện tại 0.3.0:** UI có hai role `renter`/`manager`; điều hướng bằng state tab, chưa có router/deep link; có chat/draft/confirm/review/results/compare/catalog status/viewing. Current viewing chỉ `requested/confirmed/declined`; current profile chỉ `room/studio`. Candidate/Room DTO hiện không có media và dữ liệu tọa độ đủ để dựng bản đồ. **API sản phẩm v1 là contract mục tiêu**, không gọi endpoint dự kiến như thể đã có. Namespace backend mục tiêu `/v1`, frontend proxy `/api/v1`; current client gọi `/api` qua proxy tới backend routes không prefix. Không đổi client trước khi migration/API v1 có thật.

**Phạm vi bắt buộc:** HM-01 tài khoản; HM-02 nguồn cung/media/moderation; HM-03 tìm kiếm/bản đồ/chi tiết; HM-04 AI/chi phí/HITL; HM-05 lưu/lịch sử/so sánh; HM-06 lịch/bàn giao/thông báo; HM-07 hợp đồng/thuê/bàn giao; HM-08 công tơ/hóa đơn/ghi nhận/đối chiếu tiền; HM-09 sửa chữa; HM-10 quản trị/vận hành/riêng tư/audit. Nền tảng video call riêng, voice/image AI, cổng thanh toán và legal e-sign là tích hợp tùy chọn. Tour/link/media, hồ sơ hợp đồng và consent, sổ ghi nhận tiền/đối chiếu vẫn là yêu cầu cốt lõi.

Truy vết từ nghiên cứu sang giao diện:

| Module | Nguồn nghiên cứu | Yêu cầu giao diện chính |
|---|---|---|
| HM-01 | HH-05/12 | Account, hồ sơ, security và quyền |
| HM-02 | HH-07/12 | Owner inventory/media, moderation và visibility |
| HM-03 | HH-01/04 | Landing, public search/map/detail |
| HM-04 | HH-02/03 | Hỏi rõ/confirm, AI projection/HITL và cost |
| HM-05 | HH-04/05 | Favorite, saved search, history và compare |
| HM-06 | HH-06 | Viewing/handoff/in-app + email giao dịch |
| HM-07 | HH-08 | Giữ phòng có hạn, contract/consent/tenancy/handover |
| HM-08 | HH-03/09/10 | Meter/invoice/payment evidence/reconciliation |
| HM-09 | HH-11 | Maintenance/timeline/accept/reopen |
| HM-10 | HH-07/12 | Admin/assignment/audit/privacy/support/ops |

HH là nguồn rút ra yêu cầu, không chứng minh HubHome hoặc HomeMatch đã chạy các flow này. Tên status/DTO dùng contract HomeMatch, không suy từ labels website tham chiếu.

## 2. Token và cấu trúc chung

Các giá trị đo là lịch sử tại 1280×720 ngày 02/10/2026, không khẳng định toàn site HubHome dùng cùng token.

| Token/vùng | Bằng chứng tham chiếu | Mục tiêu HomeMatch |
|---|---|---|
| Nền/surface | Nền `#f8fafc`, surface trắng | Page `#f8fafc`, surface `#ffffff` |
| Chữ/viền | `#0f172a`, `#334155`, `#64748b`, `#e2e8f0` | Heading/body/muted/border tương ứng |
| Accent | Send `#f97316`, text chọn `#ea580c`, border `#fdba74` | Accent `#f97316`, chữ nhỏ/hover `#c2410c`, nền nhấn `#fff7ed` |
| Font | Inter và fallback Arial | Inter local nếu có quyền sử dụng; fallback hệ thống/Arial hỗ trợ tiếng Việt |
| Chữ | Hero 38/45,6px weight 800; body 16/24px | Hero 38/46px desktop, 28–32px mobile; body 15–16/24px; input mobile ≥16px |
| Landing composer | Khoảng 720px, send tròn 44px | Max-width 720px, padding 16px, min-height khoảng 130px, radius 18px |
| Rail/assistant | Rail khoảng 60px, chat khoảng 430px ở viewport 1280px | Rail 60px, chat/preview 35/65 sau rail; chat min 360px khi dùng hai panel |
| Sidebar | Tổ chức có nhãn từ khảo sát đăng nhập; chưa đo lại dashboard | Khoảng 220px desktop, mobile drawer có nhãn |
| Spacing/control | Chưa đo toàn bộ | Scale 4/8/12/16/24/32/48/64; radius control 10–12px/card 16–18px; chip pill; vùng chạm ≥44×44px |

Accent sáng cần kiểm tra contrast; không mặc định chữ trắng nhỏ trên mọi nền cam. Mỗi status có nhãn và icon. Icon dùng wrapper SVG `Icon`, lưới 24px/stroke 1,6px/currentColor. `RoomIllustration` là tài sản gốc; không sao logo, mascot, ảnh, font hoặc kho tin HubHome. Source hiện vẫn là cam đỏ/nền ngà, khác hướng mục tiêu.

Motion 140–180ms ease-out, dịch tối đa 4px; `prefers-reduced-motion` bỏ chuyển động không cần thiết. Khi server xử lý lâu, thông báo trạng thái thật; không dựng câu trả lời/gợi ý bằng timer. Empty/loading giữ khung ổn định, không hiển thị số phòng/hóa đơn giả.

## 3. Vai trò, navigation và screen inventory

Các route trong bảng là **route UI mục tiêu**, chưa là route runtime. IDs không đưa nội dung chat, số điện thoại, ngân sách hoặc token vào URL. Filter công khai không nhạy cảm có thể đồng bộ query string; dữ liệu tài khoản phải đọc server theo quyền. Mỗi route có title, landmark, trạng thái auth, reload/back/deep link và fallback 403/404.

| Screen | Route mục tiêu | Người dùng / nội dung | Module / hiện trạng |
|---|---|---|---|
| S01 | `/` | Landing, composer, Tìm nhanh, lối owner, cẩm nang | HM-03/04; landing có source, layout target chưa có |
| S02 | `/dang-nhap`, `/dang-ky`, `/quen-mat-khau`, `/dat-lai-mat-khau` | Xác thực, xác minh và phục hồi tài khoản | HM-01; chỉ login hiện có |
| S03 | `/phong`, `/phong/:listingId` | Search/filter/map/list; gallery, giá/phí, vị trí, nguồn, liên hệ/lịch | HM-02/03; chưa có public catalog UI/API |
| S04 | `/tro-ly-ai`, `/tro-ly-ai/:sessionId` | Chat–preview, nhu cầu, confirm, tiến trình và gợi ý đã duyệt | HM-04; có core trong renter workspace, chưa có routes/layout target |
| S05 | `/nguoi-thue/tong-quan`, `/nguoi-thue/nhu-cau` | Việc cần làm, chế độ tìm/đang thuê; hồ sơ và scenario | HM-04/07; nhu cầu có component, overview target |
| S06 | `/nguoi-thue/tin-da-luu`, `/nguoi-thue/tim-kiem-da-luu`, `/nguoi-thue/phong-da-xem`, `/nguoi-thue/lich-su` | Tin lưu, bộ tiêu chí tìm đã lưu, đã xem/cân nhắc/loại, nhiều phiên và quản lý lịch sử | HM-05; chưa có |
| S07 | `/nguoi-thue/goi-y`, `/nguoi-thue/so-sanh` | Gợi ý AI hiện hành; compare 2–3 phòng theo cùng nguồn/ngữ cảnh | HM-04/05; có trong workspace, routes target |
| S08 | `/nguoi-thue/lich-xem`, `/nguoi-thue/lich-xem/:viewingId` | Requested/slot/confirmed/cancel/reschedule/completed/no-show; tại chỗ hoặc trực tuyến | HM-06; chỉ requested/confirmed/declined hiện có |
| S09 | `/nguoi-thue/giu-phong`, `/nguoi-thue/hop-dong`, `/nguoi-thue/hop-dong/:contractId` | Reservation có thỏa thuận/thời hạn; nháp được chia sẻ, review điều khoản, consent, tài liệu và revision | HM-07; chưa có |
| S10 | `/nguoi-thue/dang-thue/:tenancyId`, `/nguoi-thue/ban-giao/:handoverId` | Tình trạng thuê, bàn giao vào/ra, tài sản, công tơ, cọc | HM-07; chưa có |
| S11 | `/nguoi-thue/hoa-don`, `/nguoi-thue/hoa-don/:invoiceId`, `/nguoi-thue/chi-phi-su-dung` | Kỳ phí/công tơ/ảnh, hóa đơn, báo đã chuyển và trạng thái đối chiếu | HM-08; chưa có |
| S12 | `/nguoi-thue/sua-chua`, `/nguoi-thue/sua-chua/:ticketId` | Tạo yêu cầu, media, lịch hẹn, timeline và xác nhận kết quả | HM-09; chưa có |
| S13 | `/chu-nha/tong-quan`, `/chu-nha/nha`, `/chu-nha/phong`, `/chu-nha/phong/:listingId` | Nhà/phòng, CRUD, đơn giá, availability, gallery, gửi moderation | HM-02; owner chưa có |
| S14 | `/chu-nha/lich-xem`, `/chu-nha/khach-quan-tam` | Yêu cầu liên quan tin của owner, đề xuất slot, theo dõi bàn giao | HM-06; chưa có |
| S15 | `/chu-nha/giu-phong`, `/chu-nha/hop-dong`, `/chu-nha/dang-thue`, `/chu-nha/ban-giao` | Reservation, hợp đồng/tenancy, move-in/out, gia hạn/kết thúc | HM-07; chưa có |
| S16 | `/chu-nha/cong-to`, `/chu-nha/hoa-don`, `/chu-nha/doi-chieu`, `/chu-nha/sua-chua` | Chốt số, lập hóa đơn, xác nhận đã nhận tiền, xử lý bảo trì | HM-08/09; chưa có |
| S17 | `/quan-ly/duyet-tin`, `/quan-ly/duyet-goi-y`, `/quan-ly/kho` | Listing moderation và HITL là hai queue; kho/assignment/chi tiết | HM-02/04/10; review/catalog status có subset |
| S18 | `/quan-ly/lich-xem`, `/quan-ly/hop-dong`, `/quan-ly/van-hanh` | Công việc được phân công, lịch, hợp đồng và vận hành | HM-06/07/08/09; lịch có subset |
| S19 | `/quan-tri/don-vi`, `/quan-tri/tai-khoan`, `/quan-tri/phan-cong`, `/quan-tri/bao-cao`, `/quan-tri/audit`, `/quan-tri/van-hanh` | Role/scope, moderation báo cáo, audit và tình trạng dịch vụ | HM-01/10; admin chưa có |
| S20 | `/tai-khoan/ho-so`, `/tai-khoan/bao-mat`, `/tai-khoan/rieng-tu`, `/thong-bao` | Hồ sơ, phiên đăng nhập, tùy chọn thông báo, export/xóa dữ liệu | HM-01/06/10; chỉ logout hiện có |
| S21 | `/tro-giup`, `/cam-nang`, `/lien-he`, `/bao-cao-tin` | Hướng dẫn, support/report gắn bản ghi, policy | HM-10; chưa có flows sản phẩm |

Nếu một tài khoản có nhiều role đã được cấp, selector đổi ngữ cảnh và làm mới cache theo actor/scope. Không cho client tự cấp role. Owner chỉ thấy tài sản/thuê liên quan; manager chỉ công việc được giao; admin truy cập dữ liệu nhạy cảm theo scope và có audit. Tổng quan lấy số liệu thật, phân biệt 0 với chưa tải/chưa có quyền.

## 4. Đặc tả các nhóm màn

### 4.1. Landing, discovery và chi tiết

Landing: header/brand → minh họa gốc nhỏ → tiêu đề giữa → mô tả → composer → Tìm nhanh/4 câu mẫu → quy trình/tài chính/cẩm nang → CTA/footer. Gửi trước login giữ nhu cầu trong memory; câu mẫu chỉ điền, không tự gửi. Nội dung nói đúng chế độ demo hoặc sản phẩm vận hành; không lấy số nguồn cung hoặc claim HubHome.

Discovery cho phép tìm trực tiếp tin **đã qua listing moderation**, với filter city/area/type/price/amenity/availability và map. API sản phẩm quyết định lọc/sắp xếp/pagination; UI không đổi thứ tự gợi ý AI. Filter giữ giá trị khi reload/back, có xóa từng chip/reset, loại điều kiện cứng/mềm và đơn vị rõ. Dictionary loại phòng theo contract được duyệt; current chỉ room/studio, không coi mọi loại HubHome đã được hỗ trợ.

Phòng thực có `physical_room_id` ổn định, riêng với `listing_id` và revision tin; không tạo phòng mới chỉ vì đăng lại tin. Anti-overlap kiểm phòng thực, không kiểm mỗi mã tin. Map và danh sách dùng cùng public refs `listing_id + published_revision`, server resolve physical_room_id, không dùng draft revision của owner. AI refs dùng `run_id/profile_version/catalog_version + room_ids` đã published/current; comparison dùng `mode`, viewing dùng `source_mode`, enum `public_catalog/ai_recommendation` theo contract. Chọn marker làm nổi card; chọn card làm nổi marker. Vị trí gần đúng có nhãn và vùng sai số nếu API có; `area_only` không dựng ghim chính xác. Khoảng cách đường thẳng và đường đi ghi khác nhau, chưa có dữ liệu thì không hiện số. Map lỗi/cấm quyền vị trí vẫn dùng list/filter được. Không xin GPS trước hành động chủ động.

Chi tiết: gallery có alt/loading/error, title/địa chỉ theo quyền, diện tích/tiện ích/nội quy, availability/thời điểm xác minh, tiền thuê/phí/cọc, nguồn theo thuộc tính, owner/đầu mối được phép và CTA lưu/so sánh/lịch/báo cáo. Tin ẩn/hết phòng có trạng thái và chặn hành động mới theo server, vẫn thể hiện lịch sử được phép. Không tiếp tục dùng snapshot cũ để đặt lịch khi revision đổi.

### 4.2. Trợ lý, nhu cầu, gợi ý và chi phí

Desktop rail → chat → splitter → preview; chat và preview cuộn riêng, composer tiếp cận được ở đáy. Nhu cầu mở drawer, Tìm nhanh popover; mobile chuyển tab/sheet mà không mất draft, selection hoặc focus. Rail có accessible name; history/new session/favorites chỉ bật khi có API tương ứng.

Chat hiển thị trạng thái gửi, hỏi rõ và lịch sử server theo quyền. Enter gửi/Shift+Enter xuống dòng, không gửi giữa IME composition; disable rỗng/đang gửi. Draft có unknown/inferred/confirmed và căn cứ. Budget hint không thành ngân sách được xác nhận; sửa filter/form/chat phải đồng bộ cùng draft revision. Confirm tóm tắt hard/soft, tổng tháng, tiền ban đầu, người/xe/kWh/m³/chuyển/mua đồ và vị trí.

Kết quả AI chỉ có card/thumbnail/detail/compare/viewing khi `published` và còn hiệu lực; `reviewed` chưa là published. Current core tối đa 5 gợi ý và compare 2–3. Khi đổi profile/run/catalog, gỡ gợi ý/compare cũ, khóa hành động và đọc lại trạng thái. Không dựng skeleton có thông tin ứng viên nháp. Người thuê thấy lý do và đánh đổi; điểm/raw diagnostics dành đúng projection quản lý.

Cost breakdown tách monthly/initial, rent/deposit/advance/fee, known subtotal/full total, missing/included, nguồn và giả định. `null` hiển thị “Chưa rõ”, 0 hiển thị “0 ₫” hoặc “Đã bao gồm” đúng DTO; không cộng hai lần khoản included. UI không tính tiền hoặc cam kết khoản cọc đã mất. Hóa đơn thực tế về sau không thay cho ước tính scenario trước thuê.

### 4.3. Tin lưu, lịch sử, compare và lịch xem

Tin lưu/lịch sử đồng bộ tài khoản từ server, tách favorite listing, saved search criteria, viewed listing và session history. Saved search có tên/bộ filter/scenario/version và sửa/xóa/chạy lại theo quyền; chạy lại không sao approval của run cũ. Không lưu chat/hồ sơ/tài chính vào localStorage/sessionStorage. Tin thay giá/revision/hết phòng báo thay đổi; không giả tin đã lưu vẫn hợp lệ. Xóa lịch sử hoặc bỏ lưu có kết quả rõ, yêu cầu xóa dữ liệu tuân theo policy và trạng thái server.

Compare xác định `source=public_catalog` hoặc `source=ai_recommendation`, cùng scenario/đơn vị/ngữ cảnh phiên bản. Public compare dùng listing published hiện hành; AI compare chỉ dùng subset approved/current. Không trộn nguồn ngầm hoặc dùng lựa chọn cũ khi scope đổi. Có 2–3 cột, giới hạn chọn rõ, unknown không xếp như giá 0; mobile cho cuộn bảng trong container hoặc xem từng tiêu chí.

Viewing gắn nguồn public/AI, listing revision/run khi có, hình thức, timezone, slot và đầu mối. `requested` không giữ phòng và không phải confirmed. Owner đề xuất slot; manager được giao confirm/decline; renter có cancel/reschedule theo rule. Conflict nêu slot không còn hợp lệ và yêu cầu chọn lại. Màn detail có timeline, hướng dẫn tới phòng/tour link và bàn giao người thật; không hiển thị nhãn “Đã chuyển tới nhân viên” nếu chưa có receipt sự kiện. Thông báo in-app có deep link, read/unread, trạng thái tải/gửi; email giao dịch là kênh bắt buộc của v1 với outbox/delivery status và deep link yêu cầu đăng nhập; SMS/web push là kênh tùy chọn. Không gửi tài liệu/chat/chứng từ private trong email.

### 4.4. Owner inventory và hai cổng duyệt

Owner editor có nhà/phòng, vị trí/quyền công khai, quote/phí/đơn vị, amenities unknown/yes/no, media, availability và preview trước gửi. Upload báo tiến độ/loại/kích thước theo policy; media bị lỗi/reject có lý do. Lưu nháp không công bố. Listing moderation nêu lỗi cần sửa/approval/revision riêng; không tự approved vì owner đã lưu.

Manager có queue moderation tin và queue review gợi ý riêng. Review gợi ý hiển thị confirmed profile, scenario, catalog/profile version, phí/căn cứ/thiếu dữ liệu, subset và reason; approve/reject/needs_revision theo contract, CAS và key. Không optimistic published. Manager xem tin nguồn cung được phép nhưng ứng viên nháp không rò sang projection người thuê.

### 4.5. Hợp đồng, tenancy và bàn giao

Giữ phòng là thỏa thuận riêng có phòng/bên liên quan/thời hạn/điều kiện/actor/version; UI hiển thị active/released/expired theo contract và lịch sử. Requested viewing không tạo reservation. Hết hạn giải phóng theo policy server; không countdown local rồi tự thay availability. Reservation/deposit events không được ghi nhận từ chat hoặc giả owner đã nhận tiền.

Hợp đồng có bên tham gia, phòng, điều khoản, giá/phí/cọc/kỳ trả, thời hạn, tài liệu và version. Form nháp chia sẻ theo quyền; review nêu field thiếu và consent của từng bên. Sửa nội dung sau chấp thuận tạo version mới, hủy hiệu lực consent cũ theo rule. Activate chỉ khi renter và owner/manager được ủy quyền chấp thuận đúng version, transaction chặn allocation periods giao nhau trên cùng physical_room_id từ reservation hợp lệ và contract active/tenancy planned ngay trước move-in; không tự tạo chữ ký pháp lý. Export/download tài liệu có tên/version/ngày và quyền truy cập.

Tenancy chuyển active/availability occupied sau move-in checklist hoàn tất; contract active/tenancy planned đã giữ allocation period nhưng chưa đồng nghĩa renter vào ở. Contract expired không tự giải phóng phòng còn occupied trước move-out/policy. Bàn giao ghi tài sản/tình trạng/ảnh, khóa/chìa, số đầu công tơ và ghi nhận hai bên. Move-out có ngày, số cuối, kiểm tra tài sản, khoản cần quyết toán/cọc, kết quả và xác nhận. Khấu trừ cọc có `proposed/accepted/disputed`; khoản disputed được hold, không tự khấu trừ hoặc financial settlement settled như đã được chấp thuận. Hoàn cọc cần evidence/receipt và audit, không ghi refunded chỉ vì nhấn nút. Gia hạn/kết thúc/chuyển chỗ ở có flow theo rule; lịch sử không bị sửa mất. Không cho thuê trùng cùng phòng trong thời gian bị cấm.

### 4.6. Công tơ, hóa đơn, tiền và sửa chữa

Công tơ hiển thị kỳ, số đầu/cuối, ảnh/chủ thể/thời điểm, đơn giá và rule khoán/công tơ. Không biến thiếu số thành 0; số cuối nhỏ hơn số đầu yêu cầu xử lý thay/reset có căn cứ. Dữ liệu sửa sau chốt kỳ cần revision/audit, không đổi hóa đơn đã chốt ngầm.

Hóa đơn có kỳ thuê, line items/quantity/unit rate/tax nếu contract có, total/bù trừ, due date, version và trạng thái. Sổ cọc là phần riêng, không mặc định cộng cọc vào thuê hoặc invoice. Renter báo đã chuyển kèm amount/date/reference/chứng từ; owner/manager được phép xác nhận đã nhận và phân bổ/đối chiếu. UI tách evidence/receipt `submitted/verified/rejected`, invoice lifecycle `draft/issued/void` và `payment_status=unpaid/partially_paid/paid`; `overdue` là boolean tính từ `balance > 0` và `now > due_at`, vẫn có thể overdue khi đã trả một phần. Dispute có trạng thái riêng; chưa verify/allocate không gắn payment_status paid. Hỗ trợ trả thiếu/thừa/nhiều lần và dispute/correction có lý do. Phần đã chốt không chỉnh trực tiếp. Gateway nếu bật chỉ thêm kênh giao dịch, không thay sổ đối chiếu và audit.

Sửa chữa gắn tenancy active, mức ưu tiên, mô tả, media và thời gian có thể vào phòng. Timeline gồm tiếp nhận/phân công/hẹn/đang xử lý/hoàn tất/xác nhận hoặc mở lại theo rule; người xử lý đặt `resolved` khác renter xác nhận `closed`; reopen giữ timeline theo contract. Owner/manager xem đúng tài sản được phép, chi phí/sự cố riêng tư không phát tán qua notification. Repair charge phải có payer và chấp thuận của bên chịu tiền hoặc term snapshot đã xác minh; owner phê duyệt kỹ thuật không tự đủ để thu renter. Mỗi charge chuyển billing một lần có tham chiếu. Yêu cầu khẩn cấp hiển thị đầu mối liên hệ đã cấu hình; không hứa điều phối ngoài dữ liệu.

### 4.7. Quản trị, riêng tư và hỗ trợ

Admin quản lý account/role/scope/assignment, report/moderation và policy vận hành. Hành động nhạy cảm có tóm tắt tác động, lý do và ghi audit; server quyết định quyền. Audit có actor/time/action/entity/version/outcome, lọc và pagination, không đưa raw token/checkpoint/chat vào table. Người dùng xem/export/xóa dữ liệu theo policy và biết các bản ghi còn giữ theo căn cứ đã xác định. Support/report có loại vấn đề/entity/link/nội dung/media phù hợp; gửi thành công phải có mã tiếp nhận.

## 5. Ma trận trạng thái và phục hồi

Mọi screen có loading/empty/error/success; các screen có mutation/version thêm submitting/stale/conflict. Empty state có lý do/bước tiếp, không kêu gọi hành động ngoài quyền.

| Ngữ cảnh | Cách thể hiện | Hành động đúng |
|---|---|---|
| Boot/auth/loading | Skeleton trung tính/status; không hiện dữ liệu account trước | Kiểm tra server, cancel khi actor đổi |
| 401/403/404 | Hết phiên/không quyền/không tồn tại tách riêng | Login lại hoặc về danh sách được phép; không expose bản ghi |
| 422/validation | Lỗi cạnh field, giữ nội dung không nhạy cảm | Sửa field và gửi chủ động |
| 409/version/slot conflict | Thông báo dữ liệu thay đổi và bản server | Đọc lại, review nội dung mới; không tự ghi đè |
| 429/503/mất mạng | Lỗi dịch vụ hoặc giới hạn rõ, không giả no-match | Retry đọc thủ công; mutation theo endpoint contract |
| AI needs_clarification/awaiting_confirmation | Câu hỏi/summary/chưa confirmed | Bổ sung/xác nhận, không tạo kết quả giả |
| AI generating/pending_review/reviewed | Tiến trình, đầu mối/thông tin chờ | Không render ứng viên; polling có giới hạn/dừng đúng lúc |
| AI no_match/needs_verification/ai_unavailable | Nguyên nhân khác nhau, điều kiện hiện hành | Người thuê chủ động sửa điều kiện hoặc quản lý xác minh |
| AI invalidated/rejected/needs_revision | Gỡ cards/selection/hành động cũ | Đọc lại profile/reason và xác nhận/review mới |
| Listing stale/hidden/unavailable | Banner/revision hiện hành, ngừng CTA trái rule | Refresh hoặc tìm tin khác |
| Media/map lỗi | Placeholder có nhãn, error riêng của vùng | List/detail/text vẫn hoạt động, thử lại vùng lỗi |
| Save/mutation thành công | Receipt ID/version/status từ server | Đưa tới bản ghi/detail và bước kế tiếp |
| Contract/invoice/meter/ticket đã đổi | So sánh revision và thông báo tác động | Tải lại, chấp thuận/chỉnh sửa theo phiên bản mới |

Request cũ không được thay UI sau đổi actor/scope/session/filter/run. Cache key phải gồm actor/scope và entity/version. Khi không biết mutation đã thành công, đọc trạng thái; chỉ retry cùng key/payload tại endpoint có idempotency. Current review/viewing có key; message/confirm/draft/catalog không được tự resend. API v1 phải công bố semantics từng action trước triển khai; không giả tất cả POST đều retry được.

## 6. Responsive, bàn phím và accessibility

Kiểm tra desktop 1440×900/1280×720, tablet rộng 768px, mobile rộng 360px/390×844 và chiều rộng 320px, zoom 200%. Hai panel chuyển sang tab khi không còn đủ chỗ, không bóp form/chat dưới mức đọc được. Sidebar thành drawer có nhãn; danh sách/thẻ/CTA không tràn trang. Bảng/map được phép cuộn riêng nhưng còn phương án văn bản. Bàn phím điện thoại không che composer hoặc nút xác nhận.

Keyboard hoàn tất được các flow tìm/filter/chọn/compare/đặt lịch/consent/chốt công tơ/báo tiền/tạo ticket. Có skip link, heading/landmark, label/help/error gắn field, focus nhìn thấy, thứ tự Tab hợp lý; popover/modal không trap focus sai, Escape và trả focus hoạt động. Splitter có keyboard alternative; không bắt buộc kéo/thả để upload hoặc sắp ảnh. Trạng thái async quan trọng có thông báo `aria-live` phù hợp, không đọc lặp mỗi polling. Image alt phân biệt ảnh phòng và trang trí; không encode trạng thái bằng màu.

Mục tiêu contrast chữ thường ≥4,5:1, chữ lớn ≥3:1 theo [W3C Contrast Minimum](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html); kiểm tra keyboard/focus theo [W3C Keyboard](https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html) và [Focus Visible](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html). Đây là tiêu chí kiểm tra, chưa là chứng nhận toàn sản phẩm đạt WCAG. Product chọn vùng chạm ≥44×44px; không coi con số này là kết quả đo source.

## 7. Tiêu chí UI có thể kiểm tra

| ID | Điều kiện đạt | Bằng chứng |
|---|---|---|
| UI-V01 | Landing/header/composer và assistant rail/chat/preview đúng cấu trúc mục tiêu; khác biệt tham chiếu có giải thích | Ảnh baseline/candidate cùng viewport/state |
| UI-V02 | Token, type scale, spacing, icon và trạng thái dùng nhất quán trên bốn portal | Computed styles/component audit; không dùng phần trăm giống |
| UI-V03 | Mỗi S01…S21 có route/reload/back/auth/state và API tương ứng; không có CTA giả trong release | Screen coverage + browser/deep-link checks |
| UI-V04 | 320/360/390/768/1280/1440px không tràn trang; chat/form/CTA dùng được với keyboard mobile | Ảnh + thao tác trên browser/device đã ghi |
| UI-V05 | Các flow trọng yếu hoàn tất bằng keyboard, focus/modal/labels/contrast đạt tiêu chí mục 6 | Checklist keyboard + measurements |
| UI-V06 | Pending/reviewed/invalidated/error không lộ AI candidate; sai actor không đọc được detail/media/document | Fixture adversarial + API/browser negative tests |
| UI-V07 | Null/0/included/subtotal/total đúng; rent/estimate/invoice/payment status phân biệt | Fixtures có missing/zero + oracle API |
| UI-V08 | Mutation thất bại/response muộn/conflict không gây giả success hoặc ghi đè; retry đúng semantics | Controlled delay/loss/conflict evidence |
| UI-V09 | Map/list dùng cùng IDs; approximate/area-only giữ mức chính xác; lỗi map không khóa tìm kiếm | API dataset + map/list selection/failure browser |
| UI-V10 | Favorite/saved search/viewed/history đồng bộ tài khoản; stale listing có nhãn; public/AI compare giữ đúng nguồn | Hai phiên/browser + cross-account negative tests |
| UI-V11 | Lịch hiển thị đúng timezone/status/slot conflict; request không giữ phòng; bàn giao có receipt | Renter/owner/assigned manager timeline |
| UI-V12 | Reservation có expiry; consent đúng version; contract activate và tenancy active là hai bước; move-in/out không mất lịch sử | Full lifecycle API/browser evidence |
| UI-V13 | Công tơ/đơn giá/kỳ/ảnh và invoice revision đúng; reported transfer không thành payment_status paid | Meter/invoice lifecycle/payment_status/overdue/partial/dispute/correction scenario |
| UI-V14 | Ticket có media/assignment/timeline và renter acceptance/reopen theo quyền | Maintenance flow + role negative tests |
| UI-V15 | Notifications/report/privacy/audit có receipt/quyền và không lộ nội dung nhạy cảm | Events/outbox + access/export checks |
| UI-V16 | Build/browser release không chứa secrets; mọi HM module bắt buộc có kết quả nghiệm thu | Release evidence theo [PLAN](PLAN.md), [TEST_CHECKLIST](TEST_CHECKLIST.md) |

## 8. Ranh giới tích hợp và bằng chứng

Client giữ text chưa gửi/tab/drawer/focus/selection và cache phân vùng; server giữ account, permissions, listing/media revision, sessions/profile/runs, favorites/history, lịch, notification, contracts/tenancy, meters/invoices/payment records, tickets và audit. Agent logic, tài chính, ranking, CAS, idempotency và publication thuộc backend. Public catalog projection và renter AI projection là hai contract riêng.

Target comparison dùng `mode`, viewing dùng `source_mode`, enum `public_catalog|ai_recommendation`; public refs có listing_id/published_revision và server resolve physical_room_id, AI refs có run/profile/catalog versions. `source` của tin/candidate là provenance, không bị thay thành mode. Tenancy closed chỉ kết thúc việc ở; `settlement_status=pending/disputed/settled` riêng để khoản cọc tranh chấp không bị coi đã quyết toán.

Current token và session ID dùng sessionStorage; current chat/profile/tài chính không lưu bền vững trên browser. Khi phát triển v1, chọn cơ chế phiên theo threat model HM-01 và cập nhật tài liệu, không mặc nhiên coi sessionStorage là kiến trúc production đã chốt. Không đưa model/DB/storage private keys vào bundle/env public. Media/documents nhạy cảm cần URL quyền hạn/thời hạn từ server.

Đánh dấu screen/module hoàn tất chỉ sau API integration và browser evidence. [Bản preview lịch sử](design/hubhome-preview.html) dùng dữ liệu tổng hợp, không có map/owner/vận hành thuê; không thay source runtime hoặc chứng minh UI-V đã đạt. Checklist ngày 02/10 là baseline của giao diện cũ; không kế thừa nhãn đạt cho các screen mới.
