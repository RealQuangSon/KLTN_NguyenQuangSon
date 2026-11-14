# Coding plan — Crawl toàn bộ dữ liệu tin Chợ Tốt (CA)

**Ngày lập:** 07/11/2026. Thay bản crawl.md ngày 31/10 (bản đó còn trong git, commit `43f3843`).

**Mục tiêu:** lấy **mọi tin** và **mọi trường** mà API danh sách công khai trả về, trong đó có URL ảnh. Tên hiển thị của người đăng được lưu (quyết định của người dùng, 07/11/2026); SĐT và các định danh khác ở luật C1 không lấy. Ảnh thật hiển thị được trên mọi thẻ phòng.

**Không làm trong plan này:** cập nhật định kỳ, diff giữa các snapshot, đồng bộ vào DB đang chạy, tải file ảnh về máy, đưa ảnh vào xếp hạng hoặc LLM.

## 1. Khảo sát API (07/11/2026)

Đo trên 200 tin từ `GET https://gateway.chotot.com/v1/public/ad-listing`, gồm 2 thành phố × 2 chuyên mục, với `st=u,h`. Crawler đang dùng `st=u`, nên số thật có thể thấp hơn.

| Nhóm | Cá nhân (`f=p`) | Môi giới (`f=c`) | Cộng |
|---|---|---|---|
| TP.HCM, phòng (`cg=1050`) | 3.528 | 7.771 | 11.299 |
| TP.HCM, căn hộ (`cg=1010`) | 1.522 | 9.994 | 11.516 |
| Hà Nội, phòng | 468 | 930 | 1.398 |
| Hà Nội, căn hộ | 263 | 1.167 | 1.430 |
| **Tổng** | | | **khoảng 25.600** |

- **Trần phân trang:** `total` không vượt 10.000. `o=10000` còn trả tin, `o=12000` trả rỗng. Nhóm gần trần phải chia nhỏ theo `area_v2` (lọc `area_v2=13113` trả 1.412 tin).
- **Ảnh:** `images` (cỡ `preset:view`), `image`, `thumbnail_image`, `webp_image`, `image_thumbnails`, `number_of_images`. Ở tin đối chiếu với trang chi tiết, API danh sách trả đủ 9/9 ảnh.
- **CDN:** `cdn.chotot.com` trả 200 khi không có Referer và khi Referer là `http://127.0.0.1:5173/`. Một ảnh mẫu 136 KB, `max-age=3600`.
- **Dung lượng:**
  - Mỗi tin khoảng 6 KB JSON, tức tối đa 150 MB cho 25.600 tin trước khi bỏ trường và nén. Hai database trên Neon hiện dùng 25 MB và 19 MB.
  - Tải file ảnh sẽ tốn cỡ 15 GB (ước tính), nên plan này chỉ lưu URL.
- **Trang chi tiết** `/ad-listing/{list_id}` trả **SĐT thật của người đăng** trong trường `ad.phone`, và không thêm ảnh nào so với danh sách. **Không gọi endpoint này** (C1).
- **Lỗi đang có:** `strip_raw` không làm tròn tọa độ. `raw/` có latitude tới 6 chữ số thập phân, trong khi manifest ghi `coordinates_rounded_decimals: 3` (chỉ `catalog.json` đúng). CA-01 sửa lỗi này.

## 2. Luật (vi phạm là task không đạt)

| # | Luật |
|---|---|
| C1 | **Từ người đăng chỉ lưu tên hiển thị (`full_name` cấp trên cùng).** Không thu thập SĐT, avatar, mã hay tên tài khoản. Không gọi `/ad-listing/{id}` hay endpoint "Hiện số". Bỏ các khóa trong `DROPPED_KEYS` (CA-01) ở mọi độ sâu. |
| C1b | **Tên người đăng chỉ hiện trong khối `contact` cho người đã đăng nhập.** Không có trong trang công khai cho khách ẩn danh, `/rooms`, thẻ danh sách, thẻ gợi ý, kết quả tool, prompt LLM, embedding, memory, lead CRM, hay Admin Console. Không ghi tên ra log. |
| C2 | **Vị trí giữ ở mức xấp xỉ.** Tọa độ làm tròn 3 chữ số thập phân cả trong raw; bỏ số nhà, số căn, block và các trường chứa tọa độ chính xác (`location`, `pty_map*`). |
| C3 | **Không ghi lên Neon và không chạy cào đầy đủ khi code.** Test dùng dữ liệu giả, không gọi mạng. Lượt chạy thật do người dùng tự chạy (mục 4). |
| C4 | **Lịch sự với Chợ Tốt.** Một luồng, tối thiểu 1,5 giây giữa các request, giữ backoff 429/5xx trong `fetch_page`. |
| C5 | **Chỉ lưu URL ảnh, không tải file.** Crawler chỉ nhận URL `https://cdn.chotot.com/`. |
| C6 | **Ảnh và trường mới không vào xếp hạng, LLM, embedding.** Ranking không đổi: `eval invariants` và `eval ranking --split dev` phải cho kết quả như trước. |
| C7 | **Snapshot bất biến và giữ vĩnh viễn.** Không sửa, không xóa snapshot cũ, không thêm lệnh dọn snapshot; snapshot cũ không có ảnh vẫn nạp được. |
| C8 | **Không commit dữ liệu cào, `.local/`, hay URL Neon.** Repo công khai. |
| C9 | **Không sửa dữ liệu giả lập** `data/catalog/rooms.json` và manifest đã đóng băng. Catalog giả lập có `source_images` rỗng. |
| C10 | Giữ các bất biến trong `CLAUDE.md`: phí chưa biết là `null`, `poster_kind` không vào ranking, và các bất biến khác. |

## 3. Các task

Làm theo thứ tự. Mỗi task xong phải chạy test liên quan rồi mới sang task sau.

| ID | Task | File chính | Phụ thuộc |
|---|---|---|---|
| CA-01 | Raw giữ mọi trường trừ danh sách cấm | `data/crawl_chotot.py` | — |
| CA-02 | Cào toàn bộ, vượt trần 10.000 | `data/crawl_chotot.py` | CA-01 |
| CA-03 | Lưu toàn bộ raw lên Postgres | `data/crawl_chotot.py` | CA-02 |
| CA-04 | `Room` có ảnh, nhà vệ sinh, tên dự án, tên người đăng | `backend/app/models.py`, `projection.py`, `data/crawl_chotot.py` | CA-01 |
| CA-05 | API trả ảnh cho mọi danh sách | `backend/app/service.py`, `schemas.py` | CA-04 |
| CA-06 | Giao diện hiện ảnh thật | `frontend/src/` | CA-05 |
| CA-07 | Cập nhật tài liệu | `docs/`, `data/PLAN.md` | tất cả |

### CA-01 — Raw giữ mọi trường trừ danh sách cấm

Bỏ `RAW_ALLOWLIST`; viết lại `strip_raw` như sau:

```python
DROPPED_KEYS = frozenset({
    # Định danh người đăng
    "account_id", "account_oid", "account_name", "avatar", "phone",
    "shop", "shop_alias", "facebook_id", "cta_buttons",
    # Vị trí chính xác
    "street_number", "streetnumber_display", "unitnumber", "unitnumber_display",
    "detail_address", "block", "location", "pty_map", "pty_map_modifier", "pty_map_v2",
})
```

1. Duyệt đệ quy dict và list, bỏ mọi khóa trong `DROPPED_KEYS` ở mọi độ sâu.
2. `seller_info` chỉ giữ `live_ads`, `sold_ads`. `full_name` chỉ giữ ở cấp trên cùng của tin; xuất hiện ở chỗ khác thì bỏ.
3. Làm tròn `latitude`, `longitude` về 3 chữ số thập phân.
4. Áp `mask_pii` lên mọi chuỗi không bắt đầu bằng `http`.
5. Khóa mới mà API trả thêm mặc định được giữ lại, rồi đi qua bước kiểm tra ở mục 6.
6. Thêm `audit_raw(ad) -> list[str]`, trả về vi phạm:
   - còn khóa cấm;
   - tọa độ quá 3 chữ số thập phân;
   - URL có dạng tọa độ `\d+x\d+_\d+x\d+`;
   - chuỗi không phải URL còn số điện thoại.
7. Crawl gọi `audit_raw` cho mọi tin và **dừng, không ghi snapshot** nếu có vi phạm. Lỗi chỉ ghi tên khóa, không ghi giá trị.

**Test** (sửa `test_raw_never_keeps_seller_or_media_fields` trong `backend/tests/test_crawl_chotot_fields.py`):

- Khóa cấm mất ở mọi độ sâu, kể cả lồng trong dict/list.
- `images`, `videos`, `image`, `floornumber`, một khóa lạ `new_field` được giữ.
- `seller_info` chỉ còn hai khóa; URL ảnh không bị `mask_pii` làm đổi.
- `full_name` cấp trên cùng được giữ, còn số điện thoại nằm trong tên thì bị che.
- `audit_raw` bắt được từng loại vi phạm.

### CA-02 — Cào toàn bộ, vượt trần 10.000

1. Thêm `--all`: mỗi tổ hợp thành phố × chuyên mục × `f=p`, `f=c` được cào hết, không giới hạn `max_ads`. Giữ `st=u` như hiện tại.
2. Nhóm có `total >= 9500`: sau khi hết trang, lấy các `area_v2` đã thấy rồi cào lại từng quận với `area_v2=<mã>`. Quận vẫn `>= 9500` thì ghi cảnh báo vào stats, không chia tiếp.
3. Khử trùng theo `ad_id`. Tin có ở cả `f=p` và `f=c` lấy `f=p` trước, giữ cách tính `poster_kind` hiện tại.
4. `--max-minutes` mặc định 60 khi có `--all`. Ước tính khoảng 25 phút cho 25.600 tin.
5. **Raw giữ mọi tin**, kể cả tin bị `to_room` từ chối hoặc bị ba lớp lọc loại.
6. `catalog.json` vẫn chọn theo `--per-city` (mặc định 2.500). Thêm `--per-city 0` = không giới hạn, giữ mọi tin qua được lọc.
7. Stats ghi thêm: `raw_ads`, số tin theo nhóm, `total` API báo, số tin có `number_of_images != len(images)`, danh sách quận chạm trần.

**Test** (fetch giả): không giới hạn `max_ads`; chia quận chỉ khi đạt ngưỡng; khử trùng đúng; raw có tin bị loại; `--per-city 0` không cắt.

### CA-03 — Lưu toàn bộ raw lên Postgres

1. Thêm bảng vào `SCHEMA_SQL`:

```sql
CREATE TABLE IF NOT EXISTS chotot_raw_ads (
    snapshot_id text NOT NULL REFERENCES chotot_snapshots(snapshot_id) ON DELETE CASCADE,
    ad_id bigint NOT NULL,
    list_id bigint,
    raw jsonb NOT NULL,
    PRIMARY KEY (snapshot_id, ad_id)
);
```

2. `push_snapshot` ghi mọi tin trong `raw/` vào bảng này theo lô, không ghi từng dòng. Với snapshot mới, `chotot_listings.raw` để `NULL` (cột cho phép NULL) để không lưu trùng.
3. Trước khi đẩy, in dung lượng raw dự kiến và `pg_database_size`. Dùng `--max-raw-mb` (mặc định 300): vượt thì dừng, không đẩy dở.
4. Manifest: `crawler_version` `2.4`, thêm `raw_ads`, `raw_sha256` (SHA-256 trên các file raw theo thứ tự tên), và:

```json
"privacy": {"seller_identifiers_dropped": true, "poster_name_kept": true, "images_dropped": false, "image_urls_only": true,
            "detail_endpoint_used": false, "phone_email_masked_in_raw": true,
            "coordinates_rounded_decimals": 3}
```

5. `pull_snapshot` với snapshot cũ phải chạy như trước.

**Test:** chỉ dùng PG local qua `HOMEMATCH_TEST_DATABASE_URL`, không có thì skip. Không bao giờ dùng Neon.

### CA-04 — `Room` có ảnh, nhà vệ sinh, tên dự án

1. Thêm vào `Room`:

```python
# URL ảnh trên CDN Chợ Tốt theo thứ tự của tin. Chỉ để hiển thị, không vào ranking/LLM/embedding.
source_images: list[str] = Field(default_factory=list, max_length=30)
toilets: int | None = Field(default=None, ge=0)
project_name: str | None = None
# Tên hiển thị trên tin gốc, chỉ trả qua khối contact cho người đã đăng nhập (C1b).
poster_name: str | None = Field(default=None, max_length=120)
```

2. `to_room` đổ `images` (chỉ URL `https://cdn.chotot.com/`, tối đa 30), `toilets`, `pty_project_name` qua `clean_text`, `full_name` qua `clean_text` và `mask_pii` thành `poster_name`. Không có thì rỗng/`null`.
3. Thêm `source_images`, `toilets`, `project_name` vào `PUBLIC_ROOM_FIELDS` (`backend/app/projection.py`). **Không thêm `poster_name`.**
4. Các trường khác (`floornumber`, `balconydirection`, `direction`, ...) **chỉ ở raw**, vì chưa xác minh ý nghĩa mã.
5. **Kiểm tra `catalog_version`:** version là SHA-256 của `model_dump` nên thêm trường sẽ đổi version của mọi catalog. Chạy `eval validate` và `eval invariants`, ghi rõ kết quả; nếu có hash đóng băng bị vỡ thì dừng và báo, không tự sửa manifest (C9).
6. Kiểm tra `agent_tools.py`, `semantic.py`, `interpreter.py` và phần chiếu phòng cho LLM: bốn trường mới không được lọt vào prompt hoặc văn bản embedding. Thêm `poster_name` vào `_PRIVATE_KEYS` trong `agent_tools.py`.

**Test:**

- `to_room` lọc URL ngoài CDN và cắt ở 30 ảnh.
- Thiếu trường → rỗng/`null`.
- Đổi `source_images` hoặc `poster_name` không làm đổi thứ hạng; thêm hai phép đột biến này vào `eval invariants`.
- Kết quả tool gửi cho model không chứa `cdn.chotot.com` và tên người đăng.

### CA-05 — API trả ảnh cho mọi danh sách

1. `/listings`, `/rooms`, trang công khai `/tin/:id`: `source_images` có sẵn qua `model_dump`/projection; kiểm tra test.
2. Thẻ gợi ý: tìm DTO của `RoomCard`/`RoomMini` (`frontend/src/types.ts`, nguồn dữ liệu trong `service.py`). Gắn `source_images` theo `room_id` **lúc trả response**, giống cách gắn `photos`. Không lưu vào payload run đã xếp hạng và không thêm vào `eval/runs`.
3. `photos` giữ nguyên nghĩa: chỉ ảnh chủ nhà tải lên. Không đổi API quản lý ảnh của chủ nhà.
4. `_listing_contact` (`backend/app/service.py`): với tin cào, thêm `poster_name` khi `actor` đã đăng nhập; khách ẩn danh nhận `null`.
5. `poster_name` phải bị bỏ khỏi mọi đầu ra dùng `model_dump` của `Room`, nhất là `GET /rooms` trong `service.rooms`. Không dùng `Field(exclude=True)`, vì `model_dump_json` còn dùng để lưu `hm_rooms` và tính `catalog_version`.
6. **Test:** gọi `/rooms`, `/listings`, trang công khai, kết quả gợi ý, lead CRM và admin, rồi khẳng định tên mẫu không xuất hiện trong body; chỉ `contact` của người đã đăng nhập có tên.
7. Cập nhật `docs/openapi.json` bằng cách sinh lại theo cách repo đang làm, và `docs/api-contract.md`.

### CA-06 — Giao diện hiện ảnh thật

1. Thêm helper `displayPhotos(item)`: ảnh chủ nhà (`photos`) trước, sau đó `source_images`. Trả về danh sách có `url` và `external`. Ảnh ngoài dùng URL nguyên bản, không qua `mediaSrc`.
2. `CoverPhoto` và `PhotoGallery` dùng helper này, thêm `referrerPolicy="no-referrer"` và `onError`:
   - ảnh lỗi trong gallery thì bỏ khỏi danh sách;
   - hết ảnh thì về `RoomIllustration`;
   - không hiện biểu tượng ảnh hỏng.
3. `RoomCard` và `RoomMini` (`components/Shared.tsx`) đang luôn vẽ `RoomIllustration` với nhãn cứng "Hình minh họa": dùng `CoverPhoto`. Nhãn "Hình minh họa" chỉ hiện khi không có ảnh thật. Bỏ `aria-hidden` ở khối có ảnh thật.
4. `ContactInfo`: tin cào hiện "Người đăng: {tên} (theo tin gốc Chợ Tốt)" kèm link tin gốc. Không dùng tên này cho tài khoản `landlord_id` demo, chat hay lịch xem.
5. Ảnh từ Chợ Tốt có chú thích "Ảnh từ tin gốc Chợ Tốt" kèm link `source`.
6. `RoomEditor` chỉ quản lý `photos`; không hiện nút xóa/sắp xếp cho `source_images`.
7. Thẻ dùng `loading="lazy"`, ảnh giữ đúng tỉ lệ khung, không làm xô lệch bố cục. Kiểm tra cả mobile.

**Test Vitest:** ảnh chủ nhà ưu tiên; ảnh ngoài không bị thêm `/api`; `onError` về hình minh họa; nhãn đúng cho cả hai trường hợp; `RoomMini`, `RoomCard` hiện ảnh; `RoomEditor` không có nút xóa cho ảnh ngoài.

### CA-07 — Cập nhật tài liệu

- `data/crawl_chotot.py`: docstring đầu file đang ghi "Không thu thập ... ảnh".
- `data/PLAN.md` dòng 16 và `docs/trang-thai-trien-khai.md`: chỉ ghi "đã kiểm chứng" với việc thực sự đã chạy.
- `docs/ke-hoach-kltn-homematch.md`, phần giới hạn:
  - ảnh thuộc người đăng, chỉ hiển thị qua liên kết cho demo KLTN, không phân phối lại;
  - tên người đăng là dữ liệu cá nhân lấy từ tin công khai, chưa có sự đồng ý riêng của người đăng; chỉ phục vụ demo và cần giảng viên hướng dẫn xác nhận;
  - ảnh có thể tự chứa SĐT hoặc mặt người mà bước che văn bản không xử lý;
  - link ảnh có thể chết khi tin hết hạn;
  - `robots.txt` ghi `ai-train=no`, nên dữ liệu không dùng để huấn luyện mô hình.
- `CLAUDE.md`: một dòng về `source_images`, `poster_name` và bảng `chotot_raw_ads`.
- `backend/tests/test_landlord_contact.py`: cập nhật docstring nếu nội dung thay đổi.

## 4. Lượt chạy thật (người dùng tự chạy)

Chạy thử 2%:

```bash
.venv/bin/python -m data.crawl_chotot --all --scale 0.02 --snapshot-id chotot-test-2.4
```

Kiểm tra `.local/chotot/chotot-test-2.4/manifest.json`, rồi chạy đầy đủ:

```bash
.venv/bin/python -m data.crawl_chotot --all --snapshot-id chotot-2026-11-07
```

Đẩy lên Neon (cần `HOMEMATCH_CRAWL_DATABASE_URL`):

```bash
.venv/bin/python -m data.crawl_chotot --push-only --snapshot-id chotot-2026-11-07
```

Nạp vào app: catalog chỉ nạp vào DB rỗng, nên phải dùng DB mới và đặt `HOMEMATCH_CHOTOT_SNAPSHOT=chotot-2026-11-07`.

## 5. Định nghĩa "xong"

```bash
.venv/bin/python -m pytest
```

```bash
npm --prefix frontend test
```

```bash
npm --prefix frontend run typecheck
```

```bash
npm --prefix frontend run build
```

```bash
.venv/bin/python -m eval validate
```

```bash
.venv/bin/python -m eval invariants --split dev
```

Tất cả phải xanh. Thêm vào đó, `git status` không có dữ liệu cào hoặc secret, và thứ hạng trong `eval ranking --split dev` không đổi.

## 6. Mẫu báo cáo cho mỗi task

- **Đã đổi:** file và việc đã làm.
- **Đã chạy:** lệnh và kết quả thật, gồm số test pass/fail.
- **Chưa chạy hoặc chưa kiểm chứng:** ghi rõ. Không được ghi "đã kiểm chứng" với cào thật, Neon, hay trình duyệt nếu chưa chạy.
- **Lệch khỏi plan:** nếu có, nêu lý do.
