# Rà soát và căn chỉnh tài liệu theo đề tài

**Ngày:** 05/10/2026.

## 1. Vấn đề

Bộ docs ngày 04/10 đã trôi khỏi đề tài:

| Đề tài | Docs 04/10 |
|---|---|
| Trợ lý AI gợi ý căn theo nhu cầu và **năng lực tài chính**, có ước tính vay | Nền tảng quản lý **toàn vòng đời thuê**: 10 module HM-01…HM-10, 30 yêu cầu, gồm hợp đồng, công tơ, hóa đơn, đối soát tiền, sửa chữa, cổng chủ nhà, bản đồ công khai |
| Hai vai trò: sale và khách | Bốn vai trò, cách ly theo đơn vị |
| Ước tính vay | README ghi rõ "không có vay mua căn hộ" |
| Nâng cao: multi-agent, memory, mô phỏng vay, đánh giá hài lòng | Không có multi-agent; memory chỉ là consent; không có mô phỏng vay |

Ngoài ra, `trang-thai-trien-khai.md` mô tả code 0.3.0, trong khi code đã ở 0.4.0. Docs ghi thiếu đăng ký, xác minh, đặt lại mật khẩu, đơn vị, dù code đã có. Số test ghi trong docs cũng cũ.

## 2. Quyết định của người dùng (05/10/2026)

1. Giữ thị trường **cho thuê** vì thị trường mua quá phức tạp → D-01, D-02 trong [đề cương](ke-hoach-kltn-homematch.md#7-quyết-định-điều-chỉnh-so-với-đề-bài).
2. Viết docs trước, đổi code sau. Lần này chỉ sửa các lỗi đang có.
3. Hà Nội cùng phòng và căn hộ được gộp vào **kho chính** (kho v2, manifest mới).

## 3. Thay đổi

| Hạng mục | Trước (04/10) | Sau (05/10) |
|---|---|---|
| Phạm vi | HM-01…HM-10, toàn vòng đời thuê | Phỏng vấn → tài chính → xếp hạng → sale duyệt → khách so sánh/đặt lịch; nâng cao theo đề bài |
| Yêu cầu | 30 HM-R, 8 NFR | 25 FR (mức CB/NC, hiện trạng từng mục), 9 NFR gắn ràng buộc đề bài |
| Tài chính | Ước tính thuê + billing sau thuê | [Engine tài chính thuê](tai-chinh-thue.md): khả năng chi trả, băng tỷ lệ, vay annuity, mô phỏng |
| Agent | Hai graph, multi-agent là "tùy chọn" | Supervisor + 3 agent với danh sách tool, memory có đồng ý, tối ưu chi phí semantic |
| Khu vực | TP.HCM | TP.HCM + Hà Nội, từ điển alias |
| Nghiệm thu | P0–P5 theo 10 module | AC-01…AC-14, cổng G1–G4 |
| Kế hoạch | W-01…W-18 | GĐ1…GĐ5 |
| File | 4 file kế hoạch trùng nhau ở `docs/` + 6 file `DETAILED_PLAN` | Gộp vào `ke-hoach-trien-khai.md` và các `PLAN.md` ngắn; bản cũ chuyển vào `luu-tru/` |

Các file được giữ nguyên nội dung vì là bằng chứng lịch sử: `kiem-chung-*.md`, `release-manifest.json`, `khao-sat-hubhome-da-dang-nhap.md`. `nghien-cuu-hubhome.md` chỉ được thêm ghi chú phạm vi ở đầu.

## 4. Còn mở

| Mã | Việc | Người quyết |
|---|---|---|
| T1.4 | Xác nhận D-01/D-02 | Xong: người dùng xác nhận 05/10 |
| — | `data/crawl_chotot.py` lấy tin từ API công khai của Chợ Tốt nhưng chưa được dùng. Chưa có xác nhận quyền sử dụng dữ liệu. Kho chính vẫn hoàn toàn tổng hợp. Không chạy crawler này để nạp kho khi chưa có quyền. | Người dùng |
| — | `data/fixtures/v1` (hợp đồng, hóa đơn, công tơ) thuộc phạm vi cũ. Giữ lại nhưng không dùng. | — |
