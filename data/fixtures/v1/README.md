# Fixture packs v1 — HM-01/02/07/08/09

> **Ngoài đề tài (05/10/2026):** các fixture hợp đồng, hóa đơn, công tơ, sửa chữa thuộc phạm vi "toàn vòng đời thuê" đã được thu hẹp ([rà soát](../../../docs/ra-soat-tai-lieu.md)). Giữ để tham khảo, không dùng trong đánh giá.

**Phiên bản:** 05/10/2026. Bộ fixture vận hành cho [PLAN](../../PLAN.md) §2 (HM-01, HM-02, HM-07, HM-08, HM-09 stretch). Toàn bộ là dữ liệu **tổng hợp (synthetic=true ở mọi record)**: không phòng thật, không tin HubHome, không credential/PII/finance thật, không file ảnh thật (chỉ faux content ref + hash).

Không sửa các input đã freeze (`catalog/`, `profiles/`, `oracles/cost_cases.json`, `manifests/`, `generate.py`). Packs này là namespace ID mới, không tái sử dụng ID `synthetic-room-NNN`.

## Bố cục

| Thư mục | Nội dung | Ghi chú |
|---|---|---|
| `hm01_identity/` | organizations, users, sessions/recovery, memberships, assignments, access matrix | Ma trận allow/deny có actor/resource/org/as_of và expected |
| `hm02_catalog/` | properties, physical rooms, listings+versions, fee versions, media, evidence, expected public projection | draft→submitted→changes_requested→published→suspended→archived, stale revision, alias dedup |
| `hm07_contracts/` | agreements/reservations, contract versions+acceptances, tenancies+handovers, deposit ledger | expiry/overlap/occupied-sau-expiry là case âm có expected |
| `hm08_billing/` | meters/readings, tariffs, invoices+adjustments, payments, reconciliation cases, estimate tách actual, oracle expected | Oracle độc lập, VND nguyên, đơn giá Decimal string |
| `hm09_maintenance/` | tickets+events, cost events | Cost chưa confirmed không thành nợ |

`manifest.json` khai báo danh sách file và số record; `data/validate_fixtures.py` kiểm schema/ID/tham chiếu/tính toán lại oracle.

## Hợp đồng dữ liệu áp dụng

- Tiền nguyên VND (int); **đơn giá là Decimal string** (`"3000"`); `null` = chưa biết (khác `0` có nguồn).
- Timestamp ISO-8601 timezone-aware (`+07:00`), kỳ kiểu `[start, end)`.
- Mỗi record có `synthetic: true`, actor/organization/resource ID tường minh.
- Media tách `access_class: public|private|deleted`; `content_sha256 = sha256(content_ref)` (faux content, chỉ để kiểm toàn vẹn fixture).
- `document_hash` của contract version = `sha256(canonical JSON của `terms`)` với `json.dumps(terms, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`.
- Expected outcomes là hằng số soạn độc lập kèm `calculation_note`; oracle không import backend.

## Kiểm chứng

```bash
.venv/bin/python data/validate_fixtures.py
```

Lệnh trên không gọi provider, không import `backend/`; thoát khác 0 nếu thiếu file, sai schema, ID trùng, tham chiếu hỏng, hoặc oracle tính lại không khớp expected.
