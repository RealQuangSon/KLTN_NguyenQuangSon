# Coding plan — Backend (BE)

Đọc [README.md](README.md) trước, đặc biệt các mục §2 phân quyền thư mục, §3 luật cứng và §7 hợp đồng API.

**Code mẫu cần đọc:**
- `backend/app/copilot.py` và `backend/tests/test_copilot.py`: một module nghiệp vụ và test của nó.
- `backend/app/pms.py`: mẫu chuyển trạng thái `TICKET_TRANSITIONS` (khoảng dòng 26 và 451).
- `backend/app/migrations.py`: tuple `MIGRATIONS` và hàm `migrate`.
- `backend/tests/test_pms.py`: test qua `TestClient`, kiểm quyền.

| ID | Task | Ưu tiên | Phụ thuộc |
|---|---|---|---|
| BE-01 | Chạy test PostgreSQL cho schema v9 | P0 | — |
| BE-02 | Dọn các chỗ còn sót ở backend và cấu hình deploy | P0 | — |
| BE-03 | Chủ nhà tự đăng ký, admin duyệt | P1 | — |
| BE-04 | Vòng đời ticket hỗ trợ | P1 | — |
| BE-05 | Chi phí vận hành quy ra VND | P1 | AG-03 (có thể làm trước với số liệu token hiện có) |
| BE-06 | Ảnh tin và ảnh sự cố | P2 | — |
| BE-07 | Ưu đãi của chủ nhà | P2 | — |
| BE-08 | Lệnh tạo dữ liệu demo cho PMS | P2 | — |
| BE-09 | Chuẩn bị deploy Railway (người dùng tự deploy) | P2 | BE-02, BE-06 |
| BE-10 | Tách `service.py` (tùy chọn) | P3 | Làm sau cùng, cần người dùng đồng ý |

---

## BE-01 — Chạy test PostgreSQL cho schema v9

**Mục tiêu:** chứng minh migration v1→v9 và toàn bộ test chạy trên PostgreSQL. Lần chạy gần nhất là 01/10, trước schema v5–v9.

**Các bước:**
1. `bash infra/local-pg.sh start`. Lệnh tạo cluster trong `.local/pgdata` ở `127.0.0.1:55432`, cùng hai DB `homematch_dev` và `homematch_test`.
   - Nếu thiếu `pg_config`, `initdb` hoặc extension `vector`: **dừng** và báo người dùng (`brew install postgresql@16 pgvector`). Không tự cài.
2. Chạy:
   ```bash
   HOMEMATCH_TEST_DATABASE_URL=postgresql://homematch@127.0.0.1:55432/homematch_test .venv/bin/python -m pytest -q
   ```
   Fixture `storage` chạy mỗi test trên cả SQLite và PostgreSQL, mỗi test một schema riêng.
3. Với mỗi test fail chỉ trên PostgreSQL, tìm nguyên nhân gốc rồi sửa code, không sửa test để né lỗi. Lỗi thường gặp:
   - `ON CONFLICT` thiếu cột;
   - `GROUP BY` thiếu cột;
   - so sánh `bool` với `INTEGER`;
   - `rowcount` của psycopg;
   - `executescript` có nhiều câu lệnh;
   - `ALTER TABLE` trong transaction.
4. Smoke trên PostgreSQL:
   ```bash
   export HOMEMATCH_DATABASE_URL=postgresql://homematch@127.0.0.1:55432/homematch_dev HOMEMATCH_CATALOG_PATH=data/catalog/rooms.json \
          HOMEMATCH_AUTH_MODE=seed HOMEMATCH_LLM_MODE=demo HOMEMATCH_MATCHING_METHOD=B1 HOMEMATCH_EMBEDDING_MODE=disabled
   .venv/bin/python -m backend.manage setup && .venv/bin/python -m infra.smoke_api --in-process
   ```
5. `bash infra/local-pg.sh stop`.

**Xong khi:**
- pytest trên PostgreSQL có 0 fail;
- `docs/trang-thai-trien-khai.md` §1 có dòng "PostgreSQL <phiên bản>: N passed (ngày)";
- **không** sửa `docs/kiem-chung-backend.md`, vì đó là báo cáo lịch sử.

**Lặp lại:** sau BE-03, BE-04, BE-06, BE-07 (các task có migration), chạy lại bước 2.

---

## BE-02 — Dọn dẹp

| # | Việc | File | Cách làm |
|---|---|---|---|
| a | Phiên mới luôn gán `"manager-a"` | `service.py` `create_session` (~dòng 161) | Cột `hm_sessions.manager_id` là `NOT NULL` từ v1; không xóa cột. Thêm hằng module `LEGACY_ASSIGNEE = "manager-a"`, comment rằng cột cũ không dùng cho quyền. Chạy `grep -n "manager_id" backend/app/*.py` và kiểm không còn quyết định quyền nào dựa vào cột này. Nếu còn: báo lại, không tự đổi logic quyền. |
| b | Comment cũ nhắc "manager" như người duyệt | `models.py:20, :197, :234`; `agent_capability.py:23` | Sửa comment thành landlord. Không đổi tên định danh. |
| c | `support:list` vẫn cấp cho `owner`, nhưng chủ nhà không có ticket nào | `agent_capability.py:37` | Để BE-04 xử lý; ở đây chỉ ghi chú. |
| d | `infra/deploy-railway.md` ghi "bốn mật khẩu seed" | `infra/deploy-railway.md` | Liệt kê đủ tài khoản trong `auth.SEED_USERS`. Thêm `HOMEMATCH_PUBLIC_BASE_URL` (bắt buộc khi deploy), `HOMEMATCH_JOBS_INTERVAL_SECONDS`, `HOMEMATCH_CHAT_RETENTION_DAYS`, `HOMEMATCH_REENGAGE_AFTER_HOURS`. |
| e | `infra/compose.yaml` thiếu `HOMEMATCH_PUBLIC_BASE_URL` | `infra/compose.yaml` | Thêm biến, giá trị là cổng thật của frontend trong compose (xem service frontend trong file). |

**Xong khi:** check-local exit 0; `grep -rn "manager" backend/app/*.py` chỉ còn tên vai trò, cột DB và `LEGACY_ASSIGNEE`.

---

## BE-03 — Chủ nhà tự đăng ký, admin duyệt

**Hợp đồng:** README §7.1.

**Bối cảnh:** `auth.register_account` luôn chèn `role='renter'`. Chủ nhà chỉ có trong seed (`owner-a`…`owner-d`).

**Thiết kế đã chọn:**
- Chủ nhà mới phải xác minh email (stub), sau đó ở trạng thái `pending`:
  - đăng nhập được;
  - tạo và sửa tin được;
  - **không** công khai tin được.
- Admin duyệt thì chủ nhà thành `approved` và nhận membership `owner` trong `org-demo`.
- Tài khoản seed `owner-*` luôn được coi là `approved`.

Nếu người dùng muốn thiết kế khác: hỏi trước khi code.

**Các bước:**
1. Migration mới: `ALTER TABLE hm_account_profiles ADD COLUMN landlord_status TEXT`.
   - Giá trị: `NULL` cho người thuê; `pending`, `approved`, `rejected` cho chủ nhà.
   - Seed: cập nhật `seed_users` để profile của owner seed (nếu có) mang `approved`. Hàm kiểm tra coi "owner không có profile" là approved, vì seed có thể không tạo profile; kiểm lại trong `auth.py`.
2. `RegisterRequest` (`schemas.py`) thêm `account_type: Literal["renter","owner"] = "renter"`.
   - `register_account(..., account_type="renter")`: chèn `role` theo `account_type`; owner thì `landlord_status='pending'`.
   - Cập nhật docstring.
   - `Actor`, `Literal` của `role` trong `record_audit`: dùng role thật thay vì hard-code `"renter"` (dòng 136, 154, 188, 287 của `auth.py`).
3. `service.py`: thêm `_require_landlord_approved(actor)`. Gọi trong `create_room`, `update_room` và `change_status` khi kết quả cuối có `published=True` → `DomainError("landlord_not_approved", "Tài khoản chủ nhà đang chờ quản trị viên duyệt; chưa công khai tin được.", 403)`.
   - Kiểm `RoomInput` có trường `published` không (`grep -n "class RoomInput" -A20 backend/app/models.py`). Nếu tạo tin mặc định `published=True`, đổi mặc định cho chủ nhà chưa duyệt thành `False` thay vì báo lỗi, và ghi lại quyết định này.
4. `/auth/me` trả thêm `landlord_status`.
5. API admin theo §7.1:
   - `require` một capability mới `account:review_landlord` cho `admin`, thêm vào `agent_capability.py`;
   - approve: cập nhật status, tạo membership (dùng hàm trong `organizations.py`, xem `ensure_default_organization` ~dòng 40), `record_audit`, `notify(kind="landlord_review", dedup_key=f"landlord:{user_id}:{status}")`;
   - reject: cần `reason`, 1–500 ký tự.
6. Sinh lại OpenAPI; cập nhật `api-contract.md`.

**Test** (`backend/tests/test_landlord_signup.py`):
- Đăng ký owner → verify → login → tạo tin không công khai → 201.
- Công khai khi đang pending → 403 `landlord_not_approved`.
- Admin approve → công khai OK; có membership `owner`; có audit `account.landlord_approved`; chủ nhà có thông báo.
- Owner hoặc renter gọi approve → 403.
- `account_type="admin"` → 422.
- Không có `account_type` → renter, như cũ.
- Reject thiếu reason → 422.
- Owner seed (`owner-a`) vẫn công khai được, nên không phá test cũ.

**Docs:**
- thêm FR-49 vào `yeu-cau-san-pham.md` §4 ("Chủ nhà tự đăng ký; admin duyệt trước khi công khai tin");
- AC-22 thêm ca kiểm;
- `quy-trinh-nghiep-vu.md` §1;
- `status-dictionary.md` thêm `landlord_not_approved`.

---

## BE-04 — Vòng đời ticket hỗ trợ

**Hợp đồng:** README §7.2.

**Bối cảnh:**
- Chat graph (node `support`) gọi `repo.request_support(session)` và ghi `hm_support(status='requested')`.
- `repo.support_tickets(manager_id)` lọc theo cột cũ.
- `SupportResult.status` chỉ có `Literal["requested"]`.

**Các bước:**
1. Migration mới: thêm các cột `assignee TEXT`, `note TEXT`, `updated_at TEXT`, `resolved_at TEXT` vào `hm_support`.
2. `SUPPORT_TRANSITIONS = {"requested": {"in_progress","resolved"}, "in_progress": {"resolved"}, "resolved": {"in_progress"}}`, theo mẫu `TICKET_TRANSITIONS` trong `pms.py`.
   - Sai chuyển trạng thái → 409 `ticket_state`.
   - `resolved` mà thiếu `note` → 422 `note_required`.
   - Gửi lại đúng trạng thái hiện tại → trả bản hiện tại, không ghi gì thêm.
3. `repository.py`: `update_support(...)`, và `support_tickets(status=None)` cho admin.
4. `schemas.py`: mở rộng `SupportResult` (`status` thêm 2 giá trị; thêm các trường mới, nullable); thêm `SupportUpdate`.
5. API:
   - `GET /admin/support-tickets` và `PATCH /admin/support-tickets/{id}`, capability `support:manage` (chỉ admin);
   - `support:list` bỏ `owner`;
   - `GET /support-tickets` giữ cho admin.
6. Thông báo cho khách (chủ phiên): `notify(kind="support_update", dedup_key=f"support:{id}:{status}", link="/tro-ly-ai")`.
7. `assignee` lấy từ `actor.id` khi chuyển sang `in_progress`.

**Test** (`backend/tests/test_support_tickets.py`):
- Tạo ticket qua chat "tôi muốn gặp người thật".
- Admin chuyển `in_progress` → `resolved` (có note) → khách có 2 thông báo.
- PATCH lặp lại → không thêm thông báo.
- Thiếu note → 422.
- Owner gọi → 403.
- Chuyển trạng thái sai → 409.

**Docs:** FR-38, AC-22, `api-contract.md` (bảng Admin), `status-dictionary.md` (thêm trạng thái ticket).

---

## BE-05 — Chi phí vận hành quy ra VND

**Hợp đồng:** README §7.3. **Spec:** `docs/api-san-pham-v1.md` §1.

**Các bước:**
1. Tạo `infra/provider-prices.example.json`, **không có giá thật**:
   ```json
   {"effective_date": null, "vnd_per_usd": null,
    "models": {"gpt-4o": {"input_usd_per_1m": null, "output_usd_per_1m": null},
               "text-embedding-3-small": {"input_usd_per_1m": null}}}
   ```
   Thêm biến `HOMEMATCH_PROVIDER_PRICES_PATH` vào `env-inventory.md`. Người dùng tự điền giá từ trang giá chính thức và ghi ngày.
2. Tạo module `backend/app/cost_metrics.py` với hàm thuần `estimate_cost_vnd(usage: dict, prices: dict|None) -> dict`:
   - tính bằng `Decimal`, làm tròn tới đồng (`ROUND_HALF_UP`);
   - thiếu bất kỳ giá hay tỷ giá nào cần dùng → `estimated_cost_vnd: None`, kèm `missing` liệt kê khóa còn thiếu;
   - `basis` ghi số token dùng để tính.
3. Đọc usage từ `operations.py`. **Phụ thuộc AG-03:** nếu đã có `input_tokens`/`output_tokens`/`embedding_tokens` thì dùng. Nếu chưa, chỉ có `reported_tokens` (tổng) → trả `None` với `missing: ["input_output_split"]`. Không chia đôi để đoán.
4. Gắn `cost` vào DTO của `/admin/metrics` (`grep -n "semantic_usage" backend/app/schemas.py` để tìm DTO).

**Test** (`backend/tests/test_cost_metrics.py`):
- Không có file giá → `null`.
- File giá giả trong `tmp_path` cùng usage giả → số khớp với phép tính tay viết trong test.
- Thiếu tỷ giá → `null` và `missing` chứa `vnd_per_usd`.
- `/admin/metrics` có trường `cost`.

**Docs:** xóa §1 của `api-san-pham-v1.md`; cập nhật `api-contract.md`, NFR-05.

---

## BE-06 — Ảnh tin và ảnh sự cố

**Hợp đồng:** README §7.5.

**Quyết định kỹ thuật:**
- Lưu file trong `HOMEMATCH_MEDIA_DIR` (mặc định `.local/media`; trên Railway là volume).
- Metadata lưu trong DB.
- Không dùng object storage, không thêm Pillow.

**Các bước:**
1. **Dependency:** `UploadFile` cần `python-multipart`, hiện chưa cài. Thêm vào `requirements.txt` và `requirements.lock`: đọc đầu `requirements.lock` để biết cách lock, nếu không rõ thì ghi phiên bản cố định đã cài. Nêu trong báo cáo.
2. **Migration mới:** bảng `hm_media`:
   - cột `id TEXT PK`, `owner_kind TEXT` (`room`|`maintenance`), `owner_id`, `uploader_id`, `content_type`, `size_bytes INTEGER`, `sha256`, `position INTEGER`, `created_at`;
   - `UNIQUE(owner_kind, owner_id, sha256)`.
3. **Module `backend/app/media.py`:**
   - kiểm magic bytes: JPEG `FF D8 FF`, PNG `89 50 4E 47 0D 0A 1A 0A`, WebP `RIFF????WEBP`; không tin `content_type` của client;
   - giới hạn: 5 MB mỗi ảnh (đọc tối đa 5 MB + 1 byte rồi dừng); 10 ảnh mỗi tin, 5 ảnh mỗi sự cố;
   - đường dẫn file: `{MEDIA_DIR}/{sha256[:2]}/{sha256}.{ext}`. **Không bao giờ dùng tên file người dùng gửi**;
   - xóa: xóa bản ghi; nếu không còn bản ghi nào dùng `sha256` đó thì xóa file;
   - tải trùng (cùng owner và sha256) → trả bản ghi cũ, status 200.
4. **Route:** theo §7.5.
   - Quyền upload, xóa, đổi thứ tự ảnh tin: chủ nhà của phòng.
   - Quyền ảnh sự cố: khách của hợp đồng đang hiệu lực, hoặc chủ nhà của phòng.
   - `GET /media/{id}`:
     - ảnh tin công khai: không cần token;
     - ảnh tin không công khai: chỉ chủ nhà;
     - ảnh sự cố: chỉ hai bên;
     - người khác: **404**.

     Trả `FileResponse` kèm `Cache-Control: private, max-age=300` (ảnh công khai dùng `public`).
5. **DTO:** thêm `photos: [{id, url}]` (theo `position`) vào `listings.listing_card`, chi tiết tin, `/landlord/rooms/{id}` và DTO sự cố.
6. **Hạ tầng:**
   - `env-inventory.md`: `HOMEMATCH_MEDIA_DIR`;
   - `compose.yaml`: volume cho thư mục media;
   - `deploy-railway.md`: mount volume.

**Test** (`backend/tests/test_media.py`). Tạo bytes ảnh nhỏ ngay trong test, ví dụ PNG 1×1 hard-code. Các ca:
- upload → 201, file tồn tại trên đĩa;
- `.jpg` nhưng nội dung là text → 422 `invalid_media`;
- 5 MB + 1 byte → 422 `media_too_large`;
- ảnh thứ 11 → 422 `media_limit`;
- chủ nhà khác upload → 404;
- tin ẩn: người ẩn danh GET → 404, chủ nhà → 200;
- ảnh sự cố: người ngoài → 404;
- tải trùng → cùng `id`;
- xóa → file biến mất khi không còn ai dùng;
- `photos` có trong `/listings/{id}`.

**Docs:** FR-40, FR-43, AC-23, AC-25; xóa §3 của `api-san-pham-v1.md`.

---

## BE-07 — Ưu đãi của chủ nhà

**Hợp đồng:** README §7.6. **Spec:** `docs/api-san-pham-v1.md` §4.

**Các bước:**
1. **Migration mới:** bảng `hm_promotions`, cột `room_id TEXT PRIMARY KEY`, `landlord_id`, `text`, `valid_until`, `updated_at`.
2. **Route PUT/DELETE:**
   - chỉ chủ nhà của phòng; người khác → 404;
   - `valid_until` phải ≥ hôm nay (UTC+7) và ≤ hôm nay + 90 ngày, nếu sai → 422 `invalid_promotion`;
   - `text` dài 1–200 ký tự, chạy qua `conversations.mask_pii` để không chứa số điện thoại hay email.
3. **Ưu đãi không đổi giá và không vào xếp hạng.** Không đọc `hm_promotions` trong `catalog.py`, `costs.py`, `semantic.py`. DA-04 kiểm phần này.
4. **DTO:** thêm `promotion` (chỉ khi còn hạn) vào `listing_card`, chi tiết tin và `/landlord/rooms/{id}`.
5. **`automation.lead_reengagement`:** với mỗi căn gợi ý có ưu đãi còn hạn, nối thêm `" — Ưu đãi: {text} (đến {dd/mm})"`. Dedup key giữ nguyên.

**Test** (`backend/tests/test_promotions.py`):
- PUT rồi `run_due` → thông báo có ưu đãi.
- Ưu đãi hết hạn → không có trong thông báo và không có trong DTO.
- Chủ khác → 404.
- `valid_until` ở quá khứ → 422.
- `text` chứa số điện thoại → đã bị che.
- Thứ hạng gợi ý (danh sách `room_id` của run) giống hệt khi có và không có ưu đãi.

**Docs:** FR-33 → "Đã có"; xóa §4 của `api-san-pham-v1.md`.

---

## BE-08 — Lệnh tạo dữ liệu demo cho PMS

**Mục tiêu:** DB mới có dashboard, hợp đồng, hóa đơn, sự cố mẫu để demo trên trình duyệt (FE-09). Hiện tại các màn này trống cho tới khi người dùng tự thao tác hết luồng.

**Các bước:**
1. Thêm lệnh `seed-demo` vào `backend/manage.py`.
   - Từ chối chạy khi `HOMEMATCH_PUBLIC=true`.
   - Idempotent: kiểm dấu hiệu đã seed, ví dụ hợp đồng có `terms` chứa `[DEMO]`, rồi bỏ qua.
2. **Chỉ gọi method của `HomeMatchService`/`pms.py`, không chèn SQL trực tiếp**, để các bất biến (phiên bản hợp đồng, hóa đơn bất biến) vẫn được kiểm. Kịch bản cho `owner-a` và `renter-a` trên một phòng TP.HCM của owner-a đang trống:
   1. tạo hợp đồng → gửi → khách chấp thuận → kích hoạt (bắt đầu 2 tháng trước);
   2. chốt chỉ số và lập hóa đơn 2 kỳ; kỳ 1 ghi thu đủ, kỳ 2 để quá hạn;
   3. khách báo chuyển một phần cho kỳ 2 (chưa xác nhận);
   4. một sự cố `in_progress`;
   5. một cuộc trò chuyện có 2 tin nhắn.
3. Mọi văn bản demo có tiền tố `[DEMO]`.
4. Nếu `pms.py` không cho đặt ngày trong quá khứ: thêm tham số `now` (đã có ở `automation`), **không** nới validation cho API.

**Test:**
- Chạy `seed-demo` 2 lần trên DB tạm → không lỗi, không nhân đôi.
- Dashboard của owner-a có `overdue_invoices >= 1`.
- `HOMEMATCH_PUBLIC=true` → exit khác 0.

**Docs:** `README.md` (gốc) phần Demo thêm bước `python -m backend.manage seed-demo`; `CLAUDE.md` phần Commands.

---

## BE-09 — Chuẩn bị deploy Railway (người dùng tự deploy)

**Không deploy.** Chỉ làm cho cấu hình đúng và hướng dẫn đầy đủ.

1. Đọc `infra/railway.toml`, `Dockerfile.api`, `Dockerfile.frontend`, `nginx.conf`, `deploy-railway.md`.
2. Kiểm:
   - API chạy `--workers 1` (đã có);
   - nginx proxy `/api/` → API và bỏ tiền tố `/api` như Vite đang làm;
   - SPA fallback `try_files ... /index.html`, cần cho deep link `/tin/:id`;
   - `client_max_body_size 6m` (cho BE-06).
3. `deploy-railway.md` cần có:
   - PostgreSQL có `vector`;
   - một replica API;
   - volume media;
   - `HOMEMATCH_PUBLIC=true`, mật khẩu seed mạnh cho **mọi** tài khoản trong `SEED_USERS`;
   - `HOMEMATCH_PUBLIC_BASE_URL` là domain frontend thật;
   - CORS đúng domain;
   - `setup` chạy một lần;
   - cách xem `/ready`.
4. Nếu máy có Docker: `docker build -f infra/Dockerfile.api .` và `docker build -f infra/Dockerfile.frontend .`. Ghi kết quả; nếu không có Docker thì ghi "chưa build".

**Xong khi:** hướng dẫn đủ để người dùng làm theo, và `trang-thai-trien-khai.md` vẫn ghi "chưa deploy".

---

## BE-10 — Tách `service.py` (tùy chọn, cần người dùng đồng ý)

- Chỉ di chuyển code, không đổi hành vi.
- Tách các wrapper PMS, copilot, admin sang `service_pms.py`, `service_admin.py` (mixin hoặc hàm nhận `self`).
- **Không** đụng `_build_chat_graph`/`_build_recommendation_graph` và tên node, vì checkpoint đang chờ phụ thuộc vào tên node.
- Số test trước và sau phải bằng nhau. Chạy check-local sau mỗi lần tách.
