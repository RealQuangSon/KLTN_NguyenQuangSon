#!/usr/bin/env python
"""Validator độc lập cho fixture packs v1 (data/fixtures/v1).

Kiểm tra: JSON parse, schema tối thiểu, timezone-aware timestamps, kiểu tiền VND
nguyên + đơn giá Decimal string, ID duy nhất, tham chiếu chéo pack, lifecycle
status_at(as_of), chống overlap kỳ thuê, deposit balance, oracle billing tính
lại bằng Decimal/ROUND_HALF_UP riêng và so khớp expected, đối soát payments,
estimate tách actual, media/document hash, số lượng record khớp manifest.

Không import backend; chỉ stdlib. Không gọi network.

Dùng:
    .venv/bin/python data/validate_fixtures.py                # kiểm tra
    .venv/bin/python data/validate_fixtures.py --write-manifest  # cập nhật manifest.json từ dữ liệu hiện có

Thoát mã 0 khi mọi kiểm tra đạt; khác 0 khi có failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "fixtures" / "v1"

FAILURES: list[str] = []
CHECKS = 0


def check(cond: bool, msg: str) -> bool:
    global CHECKS
    CHECKS += 1
    if not cond:
        FAILURES.append(msg)
    return bool(cond)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def vnd(x: Decimal) -> int:
    return int(x.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


ISO_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T")


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def walk_values(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key, value
            yield from walk_values(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_values(item)


def line_amount(unit_price: str, quantity: str) -> int:
    if "/" in quantity:
        days, month_days = quantity.split("/")
        return vnd(Decimal(unit_price) * int(days) / int(month_days))
    return vnd(Decimal(unit_price) * Decimal(quantity))


def status_at(item: dict, at: datetime) -> str | None:
    best = None
    best_key = None
    for entry in item.get("status_history", []):
        key = parse_dt(entry["effective_from"])
        if key <= at and (best_key is None or key >= best_key):
            best, best_key = entry, key
    return best["status"] if best else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-manifest", action="store_true",
                        help="Tái tạo manifest.json từ dữ liệu hiện có thay vì kiểm tra")
    args = parser.parse_args()

    files = sorted(p for p in BASE.rglob("*.json") if p.name != "manifest.json")

    data: dict[str, dict] = {}
    for path in files:
        rel = path.relative_to(BASE).as_posix()
        try:
            data[rel] = load(path)
        except json.JSONDecodeError as exc:
            FAILURES.append(f"JSON parse lỗi: {rel}: {exc}")

    if args.write_manifest:
        manifest = {"version": "v1", "synthetic": True, "files": {}}
        for rel, payload in sorted(data.items()):
            best = 0
            if isinstance(payload, dict):
                for value in payload.values():
                    if isinstance(value, list) and value and isinstance(value[0], dict):
                        best = max(best, len(value))
            manifest["files"][rel] = {"records": best}
        manifest_path = BASE / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        print(f"Đã ghi {manifest_path} ({len(data)} file)")
        return 0

    # ---- manifest count check -------------------------------------------------
    manifest_path = BASE / "manifest.json"
    if not check(manifest_path.is_file(), "Thiếu data/fixtures/v1/manifest.json — chạy --write-manifest trước"):
        print("\n".join(FAILURES))
        return 1
    manifest = load(manifest_path)
    check(set(manifest["files"]) == set(data),
          "manifest.json và tập file dữ liệu không khớp")

    # ---- generic checks -------------------------------------------------------
    for rel, payload in data.items():
        check(payload.get("synthetic") is True, f"{rel}: synthetic phải true ở cấp file")
        for key, value in walk_values(payload):
            if isinstance(value, str) and ISO_PREFIX.match(value):
                try:
                    parsed = parse_dt(value)
                except ValueError:
                    continue
                check(parsed.tzinfo is not None and parsed.utcoffset() is not None,
                      f"{rel}: timestamp không timezone-aware: {key}={value}")
            if key.endswith("_vnd") and value is not None:
                if isinstance(value, bool) or isinstance(value, float):
                    check(False, f"{rel}: tiền phải nguyên VND (int) hoặc Decimal string, {key}={value!r}")
                elif isinstance(value, str) and key != "unit_price":
                    # Quy ước: amount_vnd dạng string là đơn giá (unit price) — phải parse Decimal được.
                    try:
                        Decimal(value)
                    except Exception:
                        check(False, f"{rel}: amount_vnd string phải là Decimal: {key}={value!r}")
                elif isinstance(value, str):
                    try:
                        Decimal(value)
                    except Exception:
                        check(False, f"{rel}: unit_price không parse được Decimal: {value!r}")
            if key == "unit_price":
                check(isinstance(value, str), f"{rel}: unit_price phải Decimal string: {value!r}")
                if isinstance(value, str):
                    try:
                        Decimal(value)
                    except Exception:
                        check(False, f"{rel}: unit_price không parse được Decimal: {value!r}")
        check("PLACEHOLDER" not in json.dumps(payload),
              f"{rel}: còn PLACEHOLDER chưa băm")

    for rel, payload in data.items():
        if isinstance(payload, dict):
            for key, value in payload.items():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and "synthetic" in item:
                            check(item["synthetic"] is True, f"{rel}: record {item.get('id')} thiếu synthetic=true")

    # ---- ID registry ----------------------------------------------------------
    def collect(rel: str, list_key: str, kind: str, id_key: str = "id") -> list[dict]:
        items = data.get(rel, {}).get(list_key, [])
        ids[kind] = {item[id_key] for item in items}
        for item in items:
            if item.get(id_key) in seen_ids:
                check(False, f"{rel}: ID trùng toàn cục: {item[id_key]}")
            seen_ids.add(item.get(id_key))
        return items

    ids: dict[str, set] = {}
    seen_ids: set = set()
    orgs = collect("hm01_identity/organizations.json", "organizations", "org")
    users = collect("hm01_identity/users.json", "users", "user")
    sessions = collect("hm01_identity/sessions_recovery.json", "sessions", "session")
    recoveries = collect("hm01_identity/sessions_recovery.json", "password_recovery_cases", "recovery")
    memberships = collect("hm01_identity/memberships.json", "memberships", "membership")
    assignments = collect("hm01_identity/assignments.json", "assignments", "assignment")
    access_cases = collect("hm01_identity/access_cases.json", "access_cases", "acx")

    props = collect("hm02_catalog/properties.json", "properties", "prop")
    rooms = collect("hm02_catalog/physical_rooms.json", "physical_rooms", "room")
    listings = collect("hm02_catalog/listings.json", "listings", "lst")
    ids["lstver"] = {v["id"] for lst in listings for v in lst["versions"]}
    for version_id in ids["lstver"]:
        check(version_id not in seen_ids, f"hm02: lstver ID trùng toàn cục: {version_id}")
        seen_ids.add(version_id)
    fee_versions = collect("hm02_catalog/fees.json", "fee_versions", "feev")
    media = collect("hm02_catalog/media.json", "media_objects", "med")
    evidence = collect("hm02_catalog/evidence.json", "evidence_records", "evd")

    agreements = collect("hm07_contracts/agreements_reservations.json", "agreements", "agr")
    reservations = collect("hm07_contracts/agreements_reservations.json", "reservations", "rsv")
    contracts = collect("hm07_contracts/contract_versions.json", "contracts", "ctr")
    contract_versions = collect("hm07_contracts/contract_versions.json", "contract_versions", "ctrv")
    acceptances = collect("hm07_contracts/contract_versions.json", "acceptances", "acc")
    tenancies = collect("hm07_contracts/tenancies_handovers.json", "tenancies", "ten")
    handovers = collect("hm07_contracts/tenancies_handovers.json", "handovers", "hnd")
    deposits = collect("hm07_contracts/deposit_ledger.json", "ledger_entries", "dep")

    meters = collect("hm08_billing/meters_readings.json", "meters", "mtr")
    readings = collect("hm08_billing/meters_readings.json", "readings", "rdg")
    tariffs = collect("hm08_billing/tariffs.json", "tariffs", "trf")
    invoices = collect("hm08_billing/invoices.json", "invoices", "inv")
    adjustments = collect("hm08_billing/invoices.json", "adjustments", "adj")
    disputes = collect("hm08_billing/invoices.json", "disputes", "dsp")
    pevs = collect("hm08_billing/payments.json", "payment_evidence", "pev")
    receipts = collect("hm08_billing/payments.json", "receipts", "rcp")
    allocations = collect("hm08_billing/payments.json", "allocations", "alc")
    refunds = collect("hm08_billing/payments.json", "refunds", "rfnd")
    recons = collect("hm08_billing/reconciliation_cases.json", "reconciliation_cases", "recon")
    estimates = collect("hm08_billing/estimate_vs_actual.json", "estimates", "est")
    oracle_cases = collect("hm08_billing/oracle_expected.json", "cases", "bill", id_key="case_id")

    tickets = collect("hm09_maintenance/tickets.json", "tickets", "tkt")
    cost_events = collect("hm09_maintenance/cost_events.json", "cost_events", "cst")

    def has(kind: str, rid) -> bool:
        return rid in ids.get(kind, set())

    def ref(kind: str, rid, ctx: str) -> bool:
        return check(has(kind, rid), f"{ctx}: tham chiếu {kind} không tồn tại: {rid!r}")

    def ref_list(kind: str, rids, ctx: str) -> None:
        for rid in rids or []:
            ref(kind, rid, ctx)

    by_id = lambda items: {item["id"]: item for item in items}
    user_by = by_id(users)
    member_by = by_id(memberships)
    assign_by = by_id(assignments)
    room_by = by_id(rooms)
    listing_by = by_id(listings)
    fee_by = by_id(fee_versions)
    med_by = by_id(media)
    ctr_by = by_id(contracts)
    ctrv_by = by_id(contract_versions)
    ten_by = by_id(tenancies)
    meter_by = by_id(meters)
    rdg_by = by_id(readings)
    trf_by = by_id(tariffs)
    inv_by = by_id(invoices)
    rcp_by = by_id(receipts)
    cst_by = by_id(cost_events)

    # ---- hm01 -----------------------------------------------------------------
    for user in users:
        check(user["role_primary"] in {"renter", "owner", "manager", "admin"},
              f"hm01 users: role không hợp lệ {user['id']}")
        check(user["status"] == "active", f"hm01 users: trạng thái account không hợp lệ {user['id']}")
    for member in memberships:
        check(member["role"] in {"renter", "owner", "manager", "admin"},
              f"hm01 memberships: role không hợp lệ {member['id']}")
        check(member["status"] in {"invited", "active", "suspended", "revoked"},
              f"hm01 memberships: trạng thái không hợp lệ {member['id']}")
        ref("user", member["user_id"], f"hm01 {member['id']}")
        ref("org", member["organization_id"], f"hm01 {member['id']}")
    for assignment in assignments:
        check(assignment["status"] in {"proposed", "active", "ended"},
              f"hm01 assignments: trạng thái không hợp lệ {assignment['id']}")
        ref("user", assignment["user_id"], f"hm01 {assignment['id']}")
        ref("prop", assignment["resource_id"], f"hm01 {assignment['id']}")

    expected1 = load(BASE / "hm01_identity/expected_outcomes.json")
    allow_set = set(expected1["case_summary"]["allow"]) | set(expected1["case_summary"]["allow_audited"])
    deny_set = set(expected1["case_summary"]["deny"])
    for case in access_cases:
        cid = case["id"]
        expected = case["expected_outcome"]
        check(expected in {"allow", "allow_audited", "deny"}, f"hm01 {cid}: expected không hợp lệ")
        if expected == "deny":
            check(cid in deny_set and cid not in allow_set, f"hm01 {cid}: deny phải nằm trong deny list")
            check(bool(case.get("expected_reason")), f"hm01 {cid}: deny thiếu expected_reason")
        else:
            check(cid in allow_set and cid not in deny_set, f"hm01 {cid}: allow phải nằm trong allow list")
        ref("user", case["actor_id"], f"hm01 {cid}") if case.get("actor_id") else None
        if case.get("session_ref"):
            ref("session", case["session_ref"], f"hm01 {cid}")
        as_of = parse_dt(case["as_of"])
        reason = case.get("expected_reason") or ""
        status_map = {
            "membership_suspended": "suspended",
            "membership_revoked": "revoked",
            "membership_invited_not_accepted": "invited",
            "assignment_ended": "ended",
            "assignment_only_proposed": "proposed",
        }
        allow_map = {
            "org_owner_active": ("membership", "active"),
            "org_owner_active_second_org": ("membership", "active"),
            "assignment_active": ("assignment", "active"),
        }
        if case.get("ref_membership_id") and reason in status_map:
            actual = status_at(member_by[case["ref_membership_id"]], as_of)
            check(actual == status_map[reason],
                  f"hm01 {cid}: membership status tại as_of là {actual}, reason đòi {status_map[reason]}")
        if case.get("ref_assignment_id") and reason in status_map:
            actual = status_at(assign_by[case["ref_assignment_id"]], as_of)
            check(actual == status_map[reason],
                  f"hm01 {cid}: assignment status tại as_of là {actual}, reason đòi {status_map[reason]}")
        if case.get("ref_membership_id") and reason in allow_map:
            kind, want = allow_map[reason]
            actual = status_at(member_by[case["ref_membership_id"]], as_of)
            check(actual == want, f"hm01 {cid}: {kind} status tại as_of là {actual}, cần {want}")
        if case.get("ref_assignment_id") and reason in allow_map:
            kind, want = allow_map[reason]
            actual = status_at(assign_by[case["ref_assignment_id"]], as_of)
            check(actual == want, f"hm01 {cid}: {kind} status tại as_of là {actual}, cần {want}")

    lifecycle = expected1["lifecycle_expectations"]
    for entity, points in lifecycle.get("membership_status_at_as_of", {}).items():
        for point in points:
            actual = status_at(member_by[entity], parse_dt(point["as_of"]))
            check(actual == point["expected_status"],
                  f"hm01 lifecycle {entity}@{point['as_of']}: {actual} != {point['expected_status']}")
    for entity, points in lifecycle.get("assignment_status_at_as_of", {}).items():
        for point in points:
            actual = status_at(assign_by[entity], parse_dt(point["as_of"]))
            check(actual == point["expected_status"],
                  f"hm01 lifecycle {entity}@{point['as_of']}: {actual} != {point['expected_status']}")

    for session in sessions:
        if session["status"] == "revoked":
            check(session["revoked_at"] is not None, f"hm01 {session['id']}: revoked thiếu revoked_at")
        if session["status"] == "expired":
            check(parse_dt(session["expires_at"]) < parse_dt("2026-09-05T00:00:00+07:00"),
                  f"hm01 {session['id']}: expired session phải hết hạn trong quá khứ")
        check(session["token_ref"].startswith("synth-"),
              f"hm01 {session['id']}: token_ref phải là chuỗi faux")

    # ---- hm02 -----------------------------------------------------------------
    seen_triples = set()
    for room in rooms:
        triple = (room["organization_id"], room["building_code"], room["room_code"])
        check(triple not in seen_triples, f"hm02: trùng (org,building,room_code): {triple}")
        seen_triples.add(triple)
        ref("prop", room["property_id"], f"hm02 {room['id']}")
        ref("org", room["organization_id"], f"hm02 {room['id']}")
        check(set(room["amenities"]) == set(load(BASE / "hm02_catalog/physical_rooms.json")["amenity_codes"]),
              f"hm02 {room['id']}: amenities phải đủ từ điển 9 mã")

    fee_by_version: dict[str, list[dict]] = {}
    for fee in fee_versions:
        ref("lstver", fee["listing_version_id"], f"hm02 {fee['id']}")
        check(fee["mode"] in {"fixed", "person", "vehicle", "kwh", "m3"},
              f"hm02 {fee['id']}: fee mode không hợp lệ")
        if fee["amount_vnd"] is None:
            check(fee["needs_verification"] is True,
                  f"hm02 {fee['id']}: fee null phải needs_verification (null khác 0)")
        else:
            check(isinstance(fee["amount_vnd"], str), f"hm02 {fee['id']}: đơn giá phải string")
            check(fee["needs_verification"] is False, f"hm02 {fee['id']}: fee có giá thì không needs_verification")
        if fee["included_in_rent"]:
            check(Decimal(fee["amount_vnd"]) == 0 and bool(fee["source"]),
                  f"hm02 {fee['id']}: included phải amount 0 có nguồn")
        fee_by_version.setdefault(fee["listing_version_id"], []).append(fee)

    for m in media:
        digest = hashlib.sha256(m["content_ref"].encode("utf-8")).hexdigest()
        check(m["content_sha256"] == digest, f"hm02 media {m['id']}: content_sha256 sai")
        check(m["access_class"] in {"public", "private", "deleted"}, f"hm02 media {m['id']}: access_class không hợp lệ")
        if m["listing_version_id"]:
            ref("lstver", m["listing_version_id"], f"hm02 media {m['id']}")

    for lst in listings:
        ref("room", lst["physical_room_id"], f"hm02 {lst['id']}")
        ref("org", lst["organization_id"], f"hm02 {lst['id']}")
        revisions = [v["revision"] for v in lst["versions"]]
        check(revisions == sorted(revisions) and len(revisions) == len(set(revisions)),
              f"hm02 {lst['id']}: revision phải đơn điệu tăng và duy nhất")
        version_ids = {v["id"] for v in lst["versions"]}
        for version in lst["versions"]:
            ref_list("feev", version["snapshot"]["fee_version_ids"], f"hm02 {version['id']}")
            ref_list("med", version["media_ids"], f"hm02 {version['id']}")
            for fee_id in version["snapshot"]["fee_version_ids"]:
                check(fee_by[fee_id]["listing_version_id"] == version["id"],
                      f"hm02 {version['id']}: fee {fee_id} không thuộc version này")
            if version["status"] == "published":
                check(version["published_at"] is not None and version["effective_from"] is not None,
                      f"hm02 {version['id']}: published version thiếu thời điểm hiệu lực")
        if lst["status"] == "published":
            published = [v for v in lst["versions"] if v["status"] == "published"]
            check(published and max(v["revision"] for v in published) == lst["current_published_revision"],
                  f"hm02 {lst['id']}: published listing phải có current_published_revision đúng")
        if lst["status"] == "draft":
            check(all(v["status"] != "published" for v in lst["versions"]),
                  f"hm02 {lst['id']}: draft listing không được có bản published")

    # media listing_version refs
    for m in media:
        if m["listing_version_id"]:
            check(any(m["listing_version_id"] in {v["id"] for v in l["versions"]} for l in listings),
                  f"hm02 media {m['id']}: listing_version ref hỏng")

    expected2 = load(BASE / "hm02_catalog/expected_outcomes.json")
    published = [l for l in listings if l["status"] == "published"]
    published_ids = sorted(l["id"] for l in published)
    check(published_ids == sorted(expected2["public_catalog_snapshot"]["expected_published_listing_ids"]),
          "hm02: tập listing published không khớp expected public catalog")
    hidden_ids = sorted(l["id"] for l in listings if l["status"] != "published")
    check(hidden_ids == sorted(expected2["public_catalog_snapshot"]["expected_hidden_listing_ids"]),
          "hm02: tập listing hidden không khớp expected")
    distinct_rooms = {l["physical_room_id"] for l in published}
    check(len(distinct_rooms) == expected2["public_catalog_snapshot"]["expected_distinct_physical_room_count"],
          "hm02: số phòng thực distinct trong public catalog sai (alias không được tăng lựa chọn)")
    rooms_with_multi = [rid for rid in {l["physical_room_id"] for l in published}
                        if sum(1 for l in published if l["physical_room_id"] == rid) > 1]
    check(len(rooms_with_multi) == expected2["quality_report_expectations"]["alias_listing_pairs"],
          "hm02: số alias pair sai")

    quantity_map = {"kwh": "electricity_kwh", "m3": "water_m3", "person": "people", "vehicle": "vehicles"}
    for case in expected2["monthly_total_cases"]:
        version = next(v for l in listings for v in l["versions"] if v["id"] == case["listing_version_id"])
        scenario = case["scenario"]
        known = version["snapshot"]["rent_vnd"]
        missing = []
        for fee_id in version["snapshot"]["fee_version_ids"]:
            fee = fee_by[fee_id]
            if fee["included_in_rent"]:
                continue
            if fee["amount_vnd"] is None:
                missing.append(fee["name"])
                continue
            quantity = Decimal("1") if fee["mode"] == "fixed" else Decimal(str(scenario[quantity_map[fee["mode"]]]))
            known += vnd(Decimal(fee["amount_vnd"]) * quantity)
        exp = case["expected"]
        check(known == exp["known_subtotal_vnd"],
              f"hm02 {case['case_id']}: known subtotal {known} != {exp['known_subtotal_vnd']}")
        full = None if missing else known
        check(full == exp["full_monthly_total_vnd"],
              f"hm02 {case['case_id']}: full total {full} != {exp['full_monthly_total_vnd']}")
        check(sorted(missing) == sorted(exp["missing_fees"]),
              f"hm02 {case['case_id']}: missing fees {missing} != {exp['missing_fees']}")

    qr = expected2["quality_report_expectations"]
    check(len(props) == qr["properties"], "hm02 quality: số property")
    check(len(rooms) == qr["physical_rooms"], "hm02 quality: số phòng thực")
    check(len(listings) == qr["listings"], "hm02 quality: số listing")
    check(len(published) == qr["published_listings"], "hm02 quality: số published")
    missing_fees = [f["id"] for f in fee_versions if f["amount_vnd"] is None]
    check(sorted(missing_fees) == sorted(qr["missing_fee_ids"]), "hm02 quality: danh sách fee missing")
    check(sum(1 for m in media if m["access_class"] == "private") == qr["private_media_count"],
          "hm02 quality: số media private")
    check(sum(1 for m in media if m["access_class"] == "deleted") == qr["deleted_media_count"],
          "hm02 quality: số media deleted")
    check(len(media) == qr["media_registry_total"], "hm02 quality: tổng media registry")

    # ---- hm07 -----------------------------------------------------------------
    for agreement in agreements:
        ref("room", agreement["physical_room_id"], f"hm07 {agreement['id']}")
        ref("user", agreement["renter_id"], f"hm07 {agreement['id']}")
        if agreement["concluded_contract_id"]:
            ref("ctr", agreement["concluded_contract_id"], f"hm07 {agreement['id']}")
    for rsv in reservations:
        ref("agr", rsv["agreement_id"], f"hm07 {rsv['id']}")
        ref("room", rsv["physical_room_id"], f"hm07 {rsv['id']}")
        if rsv["converted_to_contract_id"]:
            ref("ctr", rsv["converted_to_contract_id"], f"hm07 {rsv['id']}")

    acc_by_version: dict[str, list[dict]] = {}
    for acceptance in acceptances:
        ref("ctrv", acceptance["contract_version_id"], f"hm07 {acceptance['id']}")
        ref("user", acceptance["actor_id"], f"hm07 {acceptance['id']}")
        check(acceptance["actor_role"] in {"renter", "owner", "manager"},
              f"hm07 {acceptance['id']}: vai trò chấp thuận không hợp lệ")
        check(bool(acceptance["legal_note"]), f"hm07 {acceptance['id']}: thiếu legal_note e-sign")
        acc_by_version.setdefault(acceptance["contract_version_id"], []).append(acceptance)
        if acceptance["status"] == "invalidated":
            ref("ctrv", acceptance["invalidated_by"], f"hm07 {acceptance['id']}")

    for version in contract_versions:
        ref("ctr", version["contract_id"], f"hm07 {version['id']}")
        canonical = json.dumps(version["terms"], ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        check(version["document_hash"] == digest,
              f"hm07 {version['id']}: document_hash không khớp canonical terms")

    for contract in contracts:
        ref("room", contract["physical_room_id"], f"hm07 {contract['id']}")
        ref("user", contract["renter_id"], f"hm07 {contract['id']}")
        if contract["agreement_id"]:
            ref("agr", contract["agreement_id"], f"hm07 {contract['id']}")
        if contract["active_version_id"]:
            ref("ctrv", contract["active_version_id"], f"hm07 {contract['id']}")
        if contract["tenancy_id"]:
            ref("ten", contract["tenancy_id"], f"hm07 {contract['id']}")
        if contract["activated_at"]:
            version = ctrv_by[contract["active_version_id"]]
            accs = acc_by_version.get(version["id"], [])
            renters = [a for a in accs if a["actor_role"] == "renter" and a["status"] == "active"]
            owners = [a for a in accs if a["actor_role"] == "owner" and a["status"] == "active"]
            managers = [a for a in accs if a["actor_role"] == "manager" and a["status"] == "active"
                        and a.get("delegated_by")]
            check(renters and (owners or managers),
                  f"hm07 {contract['id']}: contract active phải có acceptance renter + owner/manager ủy quyền cùng version")

    # no activatable version exists for mismatch contracts
    for contract in contracts:
        if contract["activated_at"] is None and contract["expected_outcome"] == "blocked_version_mismatch_acceptance":
            ok_versions = []
            for version in [v for v in contract_versions if v["contract_id"] == contract["id"]]:
                accs = acc_by_version.get(version["id"], [])
                roles = {a["actor_role"] for a in accs if a["status"] == "active"}
                if "renter" in roles and ("owner" in roles or "manager" in roles):
                    ok_versions.append(version["id"])
            check(not ok_versions,
                  f"hm07 {contract['id']}: không được có version nào đủ hai bên khi blocked_version_mismatch")

    # allocation overlap
    allocations_room: dict[str, list[dict]] = {}
    for contract in contracts:
        if not contract["activated_at"] or not contract["active_version_id"]:
            continue
        terms = ctrv_by[contract["active_version_id"]]["terms"]
        allocations_room.setdefault(contract["physical_room_id"], []).append(
            {"contract": contract["id"],
             "start": parse_dt(terms["period"]["start"]),
             "end": parse_dt(terms["period"]["end"])})
    for room_id, intervals in allocations_room.items():
        intervals.sort(key=lambda item: item["start"])
        for a, b in zip(intervals, intervals[1:]):
            check(a["end"] <= b["start"],
                  f"hm07: allocation chồng lấn trên {room_id}: {a['contract']} và {b['contract']}")

    for attempt in load(BASE / "hm07_contracts/contract_versions.json")["negative_activation_attempts"]:
        target = ctr_by[attempt["contract_id"]]
        check(attempt["attempted_version_id"] != target.get("active_version_id"),
              f"hm07 {attempt['id']}: attempted version không được là bản đang active")
        if attempt["case"] in {"overlap_active_contract", "overlap_planned_allocation"}:
            terms = ctrv_by[attempt["attempted_version_id"]]["terms"]
            start, end = parse_dt(terms["period"]["start"]), parse_dt(terms["period"]["end"])
            overlaps = [item for item in allocations_room.get(target["physical_room_id"], [])
                        if start < item["end"] and item["start"] < end]
            check(bool(overlaps) and overlaps[0]["contract"] == attempt["overlapping_contract_id"],
                  f"hm07 {attempt['id']}: case overlap phải giao thật với {attempt['overlapping_contract_id']}")

    for tenancy in tenancies:
        ref("ctr", tenancy["contract_id"], f"hm07 {tenancy['id']}")
        ref("room", tenancy["physical_room_id"], f"hm07 {tenancy['id']}")
        ref("user", tenancy["renter_id"], f"hm07 {tenancy['id']}")
        check(tenancy["status"] in {"planned", "active", "ending", "closed"},
              f"hm07 {tenancy['id']}: tenancy status không hợp lệ")
        if tenancy["status"] == "planned":
            check(tenancy["move_in_at"] is None, f"hm07 {tenancy['id']}: planned chưa được move-in")
    for handover in handovers:
        ref("ten", handover["tenancy_id"], f"hm07 {handover['id']}")
        for item in handover["checklist"]:
            ref_list("med", item.get("media_ids"), f"hm07 {handover['id']}")
            if item.get("reading_id"):
                ref("rdg", item["reading_id"], f"hm07 {handover['id']}")
                check(rdg_by[item["reading_id"]]["value"] == item["reading_value"],
                      f"hm07 {handover['id']}: reading value không khớp handover")
            if item.get("meter_id"):
                ref("mtr", item["meter_id"], f"hm07 {handover['id']}")
            if item.get("deposit_ledger_id"):
                ref("dep", item["deposit_ledger_id"], f"hm07 {handover['id']}")

    entries_by_tenancy: dict[str, list[dict]] = {}
    for entry in deposits:
        ref("ten", entry["tenancy_id"], f"hm07 {entry['id']}")
        check(entry["entry_type"] in {"deposit_received", "deduction_proposed", "deduction_accepted",
                                      "deduction_disputed", "refund_issued"},
              f"hm07 {entry['id']}: entry_type không hợp lệ")
        ref_list("med", entry.get("media_ids"), f"hm07 {entry['id']}")
        entries_by_tenancy.setdefault(entry["tenancy_id"], []).append(entry)
    for expected in load(BASE / "hm07_contracts/deposit_ledger.json")["expected_balances"]:
        entries = entries_by_tenancy.get(expected["tenancy_id"], [])
        received = sum(e["amount_vnd"] for e in entries if e["entry_type"] == "deposit_received")
        deducted = sum(e["amount_vnd"] for e in entries if e["entry_type"] == "deduction_accepted")
        refunded = sum(e["amount_vnd"] for e in entries if e["entry_type"] == "refund_issued")
        balance = received - deducted - refunded
        check(received == expected["expected_received_vnd"]
              and deducted == expected["expected_accepted_deductions_vnd"]
              and refunded == expected["expected_refunds_vnd"]
              and balance == expected["expected_balance_vnd"],
              f"hm07 deposit {expected['tenancy_id']}: balance tính lại {balance} != expected {expected['expected_balance_vnd']}")

    # ---- hm08 -----------------------------------------------------------------
    for reading in readings:
        ref("mtr", reading["meter_id"], f"hm08 {reading['id']}")
        check(isinstance(reading["value"], int), f"hm08 {reading['id']}: reading phải nguyên")
    for tariff in tariffs:
        ref("mtr", tariff["meter_id"], f"hm08 {tariff['id']}")
    for invoice in invoices:
        ref("ten", invoice["tenancy_id"], f"hm08 {invoice['id']}")
        ref("org", invoice["organization_id"], f"hm08 {invoice['id']}")
        computed_total = 0
        for line in invoice["lines"]:
            expected_amount = line_amount(line["unit_price"], line["quantity"])
            check(expected_amount == line["amount_vnd"],
                  f"hm08 {invoice['id']}/{line['line_id']}: amount tính lại {expected_amount} != {line['amount_vnd']}")
            computed_total += line["amount_vnd"]
            for rid in re.findall(r"rdg-[a-z0-9-]+", line.get("source", "")):
                ref("rdg", rid, f"hm08 {invoice['id']} line {line['line_id']}")
            for rid in re.findall(r"trf-[a-z0-9-]+", line.get("source", "")):
                ref("trf", rid, f"hm08 {invoice['id']} line {line['line_id']}")
            for rid in re.findall(r"ctrv-[a-z0-9-]+", line.get("source", "")):
                ref("ctrv", rid, f"hm08 {invoice['id']} line {line['line_id']}")
            for rid in re.findall(r"cst-[a-z0-9-]+", line.get("source", "")):
                ref("cst", rid, f"hm08 {invoice['id']} line {line['line_id']}")
            for rid in re.findall(r"tkt-[a-z0-9-]+", line.get("source", "")):
                ref("tkt", rid, f"hm08 {invoice['id']} line {line['line_id']}")
        if invoice["status"] == "issued":
            check(computed_total == invoice["issued_total_vnd"],
                  f"hm08 {invoice['id']}: tổng line {computed_total} != issued_total {invoice['issued_total_vnd']}")

    def allocated_at(invoice_id: str, at: datetime) -> int:
        return sum(a["amount_vnd"] for a in allocations
                   if a["invoice_id"] == invoice_id and parse_dt(a["allocated_at"]) <= at)

    def adjustment_at(invoice_id: str, at: datetime) -> int:
        return sum(a["amount_vnd"] for a in adjustments
                   if a["invoice_id"] == invoice_id and parse_dt(a["at"]) <= at)

    def effective_total(invoice: dict) -> int:
        adj = sum(a["amount_vnd"] for a in adjustments if a["invoice_id"] == invoice["id"])
        return invoice["issued_total_vnd"] + adj

    for invoice in invoices:
        iid = invoice["id"]
        if invoice["status"] == "issued":
            effective = effective_total(invoice)
            check(effective == invoice["effective_total_vnd"],
                  f"hm08 {iid}: effective_total tính lại {effective} != {invoice['effective_total_vnd']}")
            allocated = sum(a["amount_vnd"] for a in allocations if a["invoice_id"] == iid)
            balance = effective - allocated
            check(allocated == invoice["allocated_vnd"], f"hm08 {iid}: allocated sai")
            check(balance == invoice["balance_vnd"], f"hm08 {iid}: balance {balance} != {invoice['balance_vnd']}")
            status = "paid" if balance == 0 else ("partially_paid" if allocated > 0 else "unpaid")
            check(status == invoice["payment_status"], f"hm08 {iid}: payment_status {status} != {invoice['payment_status']}")
            if invoice["overdue_as_of"]:
                as_of = parse_dt(invoice["overdue_as_of"])
                bal = effective_total(invoice) - allocated_at(iid, as_of)
                check(bal > 0 and as_of > parse_dt(invoice["due_at"]),
                      f"hm08 {iid}: overdue flag phải đúng balance>0 và quá hạn")
        if invoice["status"] == "draft":
            check(invoice["issued_at"] is None and invoice["due_at"] is None,
                  f"hm08 {iid}: draft không có issued/due")
        if invoice["status"] == "void":
            check(bool(invoice.get("void_reason")), f"hm08 {iid}: void phải có lý do")

    for adjustment in adjustments:
        ref("inv", adjustment["invoice_id"], f"hm08 {adjustment['id']}")
        check(adjustment["amount_vnd"] != 0, f"hm08 {adjustment['id']}: adjustment 0 vô nghĩa")
    for dispute in disputes:
        ref("inv", dispute["invoice_id"], f"hm08 {dispute['id']}")
        target = inv_by[dispute["invoice_id"]]
        check(any(line["line_id"] == dispute["line_id"] for line in target["lines"]),
              f"hm08 {dispute['id']}: line bị tranh chấp không tồn tại")
        check(target["balance_vnd"] == target["effective_total_vnd"] - target["allocated_vnd"],
              f"hm08 {dispute['id']}: tranh chấp không được xóa nợ")

    # payments
    pev_by = by_id(pevs)
    for receipt in receipts:
        ref("inv", receipt["invoice_id"], f"hm08 {receipt['id']}")
        ref("pev", receipt["evidence_id"], f"hm08 {receipt['id']}")
        evidence = pev_by[receipt["evidence_id"]]
        check(evidence["bank_ref"] and receipt["amount_vnd"] > 0, f"hm08 {receipt['id']}: receipt thiếu dữ liệu")
    for allocation in allocations:
        ref("rcp", allocation["receipt_id"], f"hm08 {allocation['id']}")
        ref("inv", allocation["invoice_id"], f"hm08 {allocation['id']}")
        receipt = rcp_by[allocation["receipt_id"]]
        check(allocation["invoice_id"] == receipt["invoice_id"],
              f"hm08 {allocation['id']}: allocation sai invoice so với receipt")
    for refund in refunds:
        ref("rcp", refund["receipt_id"], f"hm08 {refund['id']}")

    # duplicate bank_ref protection
    refs = {}
    for receipt in receipts:
        evidence = pev_by[receipt["evidence_id"]]
        refs.setdefault(evidence["bank_ref"], []).append(receipt["id"])
    for bank_ref, receipt_ids in refs.items():
        check(len(receipt_ids) == 1,
              f"hm08: bank_ref {bank_ref} có nhiều receipt verified: {receipt_ids}")

    expected_pay = load(BASE / "hm08_billing/payments.json")["receipt_identity_expected"]
    for receipt in receipts:
        exp = expected_pay[receipt["id"]]
        allocated = sum(a["amount_vnd"] for a in allocations if a["receipt_id"] == receipt["id"])
        refunded = sum(r["amount_vnd"] for r in refunds if r["receipt_id"] == receipt["id"])
        check(allocated + refunded + exp["unallocated_vnd"] == receipt["amount_vnd"],
              f"hm08 {receipt['id']}: verified = allocated + unallocated + refunded vi phạm "
              f"({allocated}+{exp['unallocated_vnd']}+{refunded} != {receipt['amount_vnd']})")
        check(allocated == exp["allocated_vnd"] and refunded == exp["refunded_vnd"],
              f"hm08 {receipt['id']}: allocated/refunded không khớp expected identity")

    # duplicate evidence expectations
    dup_refs = {}
    for evidence in pevs:
        dup_refs.setdefault(evidence["bank_ref"], []).append(evidence["id"])
    for evidence in pevs:
        if evidence["status"] == "flagged_duplicate":
            check(len(dup_refs[evidence["bank_ref"]]) > 1,
                  f"hm08 {evidence['id']}: flagged_duplicate nhưng bank_ref chỉ có một record")

    # reconciliation cases
    for case in recons:
        if not case.get("invoice_id"):
            continue
        invoice = inv_by[case["invoice_id"]]
        iid = case["invoice_id"]
        if case["case"] == "declared_not_paid_then_partial_then_paid":
            for step in case["steps"]:
                at = parse_dt(step["at"])
                eff = invoice["issued_total_vnd"] + adjustment_at(iid, at)
                bal = eff - allocated_at(iid, at)
                alloc = allocated_at(iid, at)
                status = "paid" if bal == 0 else ("partially_paid" if alloc > 0 else "unpaid")
                overdue = bal > 0 and at > parse_dt(invoice["due_at"])
                check(status == step["expected_payment_status"] and bal == step["expected_balance_vnd"]
                      and overdue == step["expected_overdue"],
                      f"hm08 {case['id']} step@{step['at']}: tính lại status={status} bal={bal} overdue={overdue}")
        elif case["case"] == "partial_and_overdue_and_dispute_and_adjustment":
            as_of = parse_dt(case["as_of"])
            bal = invoice["issued_total_vnd"] + adjustment_at(iid, as_of) - allocated_at(iid, as_of)
            exp = case["expected_final"]
            check(bal == exp["balance_vnd"], f"hm08 {case['id']}: balance {bal} != {exp['balance_vnd']}")
            check(invoice["issued_total_vnd"] == exp["issued_total_vnd"],
                  f"hm08 {case['id']}: issued_total snapshot phải giữ nguyên sau adjustment")
            check(exp["overdue"] is True and as_of > parse_dt(invoice["due_at"]),
                  f"hm08 {case['id']}: overdue expectation sai")
        elif case["case"] == "overpayment_refund":
            exp = case["expected_final"]
            receipt = next(r for r in receipts if r["invoice_id"] == iid)
            check(receipt["amount_vnd"] - exp["allocated_vnd"] == exp["refunded_vnd"],
                  f"hm08 {case['id']}: overpayment/refund không khớp")
            check(exp["balance_vnd"] == 0, f"hm08 {case['id']}: balance phải 0 sau khi allocate đủ")
        elif case["case"] == "open_receivables_snapshot":
            as_of = parse_dt(case["as_of"])
            total = 0
            for inv in invoices:
                if inv["status"] == "issued" and parse_dt(inv["issued_at"]) <= as_of:
                    total += inv["issued_total_vnd"] + adjustment_at(inv["id"], as_of) - allocated_at(inv["id"], as_of)
            check(total == case["expected_open_receivables_vnd"],
                  f"hm08 {case['id']}: open receivables tính lại {total} != {case['expected_open_receivables_vnd']}")
        elif case["case"] == "duplicate_evidence_not_double_counted":
            evidences = dup_refs[case["bank_ref"]]
            check(len(evidences) == case["expected"]["evidence_records_for_bank_ref"],
                  f"hm08 {case['id']}: số evidence cho bank_ref sai")
            receipt_ids = refs.get(case["bank_ref"], [])
            check(len(receipt_ids) == case["expected"]["verified_receipts_for_bank_ref"],
                  f"hm08 {case['id']}: bank_ref trùng chỉ được một receipt verified")
        elif case["case"] in {"void_excluded_from_receivables", "blocked_draft_not_in_receivables",
                              "missing_tariff_draft_blocked"}:
            check(invoice["status"] in {"void", "draft"},
                  f"hm08 {case['id']}: invoice phải void/draft")

    # missing tariff recheck for BILL-09 invoice
    inv009 = inv_by["inv-009"]
    check(inv009["known_subtotal_vnd"] == 3600000 and inv009["issued_total_vnd"] is None,
          "hm08 inv-009: known subtotal phải 3600000 và full total null")

    # estimates
    for estimate in estimates:
        ref("ten", estimate["tenancy_id"], f"hm08 {estimate['id']}")
        total = 0
        for line in estimate["expected_lines"]:
            if line["name"] == "rent":
                amount = line["amount_vnd"]
            elif line["name"] == "electricity":
                amount = vnd(Decimal(str(estimate["scenario_usage"]["electricity_kwh"]))
                             * Decimal(trf_by[estimate["tariff_refs"]["electricity"]]["unit_price"]))
            elif line["name"] == "water":
                amount = vnd(Decimal(str(estimate["scenario_usage"]["water_m3"]))
                             * Decimal(trf_by[estimate["tariff_refs"]["water"]]["unit_price"]))
            else:
                amount = line["amount_vnd"]
            check(amount == line["amount_vnd"],
                  f"hm08 {estimate['id']}: estimate line {line['name']} tính lại {amount} != {line['amount_vnd']}")
            total += line["amount_vnd"]
        check(total == estimate["expected_estimate_total_vnd"],
              f"hm08 {estimate['id']}: estimate total {total} != {estimate['expected_estimate_total_vnd']}")
        check(not any("est-" in line.get("source", "") for invoice in invoices for line in invoice["lines"]),
              f"hm08 {estimate['id']}: estimate không được làm nguồn của invoice actual")

    # ---- oracle recompute (independent) ---------------------------------------
    def reading_value(rid):
        return rdg_by[rid]["value"] if rid else None

    def meter_for_reading(rid):
        return rdg_by[rid]["meter_id"]

    for case in oracle_cases:
        cid = case["case_id"]
        inputs = case
        # electricity
        el = inputs.get("electricity") or {}
        expected = case["expected"]
        computed: dict[str, int] = {}
        quantities: dict[str, str] = {}
        if "electricity_segments" in inputs:
            total_el = 0
            for index, segment in enumerate(inputs["electricity_segments"], start=1):
                usage_kwh = reading_value(segment["end_reading_id"]) - reading_value(segment["start_reading_id"])
                price = trf_by[segment["tariff_id"]]["unit_price"]
                amount = vnd(Decimal(price) * usage_kwh)
                computed[f"electricity_segment_{index}"] = amount
                quantities[f"electricity_segment_{index}"] = str(usage_kwh)
                total_el += amount
            check(total_el == expected.get("electricity_total_vnd"),
                  f"oracle {cid}: electricity total {total_el} != {expected.get('electricity_total_vnd')}")
        elif el.get("old_meter_id"):
            old_seg = reading_value(el["old_last_reading_id"]) - reading_value(el["old_start_reading_id"])
            new_first = reading_value(el["new_first_reading_id"])
            new_end = reading_value(el["new_end_reading_id"])
            if new_first is None:
                check(expected.get("outcome") == "blocked_unknown_segment",
                      f"oracle {cid}: new_first null phải blocked_unknown_segment")
                check(expected.get("full_total_vnd") is None,
                      f"oracle {cid}: unknown segment phải full_total null")
                continue
            usage_kwh = old_seg + (new_end - new_first)
            price = trf_by[el["tariff_id"]]["unit_price"]
            computed["electricity"] = vnd(Decimal(price) * usage_kwh)
            quantities["electricity"] = str(usage_kwh)
        elif el:
            start_value, end_value = reading_value(el["start_reading_id"]), reading_value(el["end_reading_id"])
            if end_value < start_value:
                check(expected.get("outcome") == "blocked_reading_regression",
                      f"oracle {cid}: end<start phải blocked_reading_regression")
                check(expected.get("full_total_vnd") is None,
                      f"oracle {cid}: regression phải full_total null")
                continue
            usage_kwh = end_value - start_value
            price = trf_by[el["tariff_id"]]["unit_price"]
            computed["electricity"] = vnd(Decimal(price) * usage_kwh)
            quantities["electricity"] = str(usage_kwh)
        # water
        wt = inputs.get("water") or {}
        if wt and wt.get("start_reading_id"):
            usage_m3 = reading_value(wt["end_reading_id"]) - reading_value(wt["start_reading_id"])
            if wt.get("tariff_id"):
                price = trf_by[wt["tariff_id"]]["unit_price"]
                computed["water"] = vnd(Decimal(price) * usage_m3)
                quantities["water"] = str(usage_m3)
            else:
                check(expected.get("missing") == ["water"] and expected.get("full_total_vnd") is None,
                      f"oracle {cid}: thiếu tariff nước phải missing water + full_total null")
        # flat lines
        for flat in inputs.get("flat_lines", []):
            computed[flat["name"]] = line_amount(flat["unit_price"], flat["quantity"])
        # cost event lines
        for cost_line in inputs.get("cost_event_lines", []):
            event = cst_by[cost_line["cost_event_id"]]
            check(event["status"] == "confirmed",
                  f"oracle {cid}: cost event {event['id']} phải confirmed mới charge")
            computed[cost_line["name"]] = event["amount_vnd"]
            check(Decimal(cost_line["unit_price"]) == Decimal(str(event["amount_vnd"])),
                  f"oracle {cid}: cost line unit_price không khớp cost event")
        if "total_vnd" in expected:
            got = sum(computed.values())
            check(got == expected["total_vnd"],
                  f"oracle {cid}: total tính lại {got} != expected {expected['total_vnd']} "
                  f"(computed={computed})")
            for name, amount in computed.items():
                match = next((line for line in expected["lines"] if line["name"] == name), None)
                check(match is not None, f"oracle {cid}: computed line {name} không có trong expected")
                if match:
                    check(amount == match["amount_vnd"],
                          f"oracle {cid}: line {name} {amount} != {match['amount_vnd']}")
                    if "quantity" in match:
                        check(quantities.get(name) == match["quantity"],
                              f"oracle {cid}: quantity {name} {quantities.get(name)} != {match['quantity']}")
            for line in expected["lines"]:
                check(line["name"] in computed,
                      f"oracle {cid}: expected line {line['name']} không được tính lại")
        # rate-at-period-start policy verification
        if inputs.get("policy") == "rate_at_period_start" and el.get("start_reading_id"):
            period_start = parse_dt(inputs["period"]["start"])
            candidates = [t for t in tariffs
                          if t["meter_id"] == meter_for_reading(el["start_reading_id"])
                          and parse_dt(t["effective_from"]) <= period_start
                          and (t["superseded_at"] is None or parse_dt(t["superseded_at"]) > period_start)]
            latest = max(candidates, key=lambda t: parse_dt(t["effective_from"]))
            check(latest["id"] == el["tariff_id"],
                  f"oracle {cid}: tariff đầu kỳ phải là {latest['id']}, case dùng {el['tariff_id']}")
        if inputs.get("policy") == "rate_change_at_period_boundary" and el.get("start_reading_id"):
            period_start = parse_dt(inputs["period"]["start"])
            latest = trf_by[el["tariff_id"]]
            check(parse_dt(latest["effective_from"]) == period_start,
                  f"oracle {cid}: rate boundary phải effective đúng đầu kỳ")
        if case.get("type") == "scenario_variant":
            check(case.get("invoice_id") is None and expected.get("total_vnd") is not None,
                  f"oracle {cid}: variant phải có expected nhưng không gắn invoice")
        if case.get("type") == "actual_invoice":
            ref("inv", case["invoice_id"], f"oracle {cid}")
            check(inv_by[case["invoice_id"]]["status"] == "issued",
                  f"oracle {cid}: invoice của case actual phải issued")
            # snapshot consistency: invoice lines match oracle expected lines
            inv_lines = {line["name"]: line["amount_vnd"] for line in inv_by[case["invoice_id"]]["lines"]}
            for line in expected["lines"]:
                if line["name"] in inv_lines:
                    check(inv_lines[line["name"]] == line["amount_vnd"],
                          f"oracle {cid}: invoice snapshot {line['name']} {inv_lines[line['name']]} != oracle {line['amount_vnd']}")

    # BILL-03 amendment must require accepted amendment + boundary measured reading
    for case in oracle_cases:
        if case.get("policy") == "amendment_boundary_split":
            amendment = case["amendment"]
            check(amendment["accepted"] is True and len(amendment["accepted_by"]) >= 2,
                  f"oracle {case['case_id']}: amendment variant phải accepted hai bên")
            boundary = rdg_by[amendment["boundary_reading_id"]]
            check(boundary["kind"] == "measured", f"oracle {case['case_id']}: boundary phải measured")

    # ---- hm09 -----------------------------------------------------------------
    allowed_basic = {"submitted": {"triaged", "cancelled"},
                     "triaged": {"scheduled", "cancelled"},
                     "scheduled": {"in_progress", "cancelled"},
                     "in_progress": {"resolved"},
                     "resolved": {"renter_confirmed", "reopened"},
                     "reopened": {"triaged"},
                     "renter_confirmed": {"closed"},
                     "closed": set(),
                     "cancelled": set()}
    event_count = 0
    appointment_count = 0
    for ticket in tickets:
        ref("ten", ticket["tenancy_id"], f"hm09 {ticket['id']}")
        ref("user", ticket["created_by"], f"hm09 {ticket['id']}")
        ref_list("med", ticket["media_ids"], f"hm09 {ticket['id']}")
        check(ticket["urgency"] in {"low", "normal", "high", "urgent"},
              f"hm09 {ticket['id']}: urgency không hợp lệ")
        previous = None
        last_at = None
        for event in ticket["events"]:
            event_count += 1
            ref("user", event["actor_id"], f"hm09 {event['id']}")
            at = parse_dt(event["at"])
            if last_at is not None:
                check(at >= last_at, f"hm09 {ticket['id']}: event {event['id']} lệch thứ tự thời gian")
            last_at = at
            if event["action"] == "reopened":
                check(bool(event.get("reason")), f"hm09 {event['id']}: reopen phải có lý do")
                previous = "triaged"
                continue
            if previous is not None:
                check(event["action"] in allowed_basic.get(previous, set()),
                      f"hm09 {ticket['id']}: chuyển {previous}→{event['action']} không hợp lệ")
            if event["action"] == "resolved":
                check(bool(event.get("completion_evidence_media_ids")) and bool(event.get("work_summary")),
                      f"hm09 {event['id']}: resolved phải có bằng chứng + mô tả công việc")
                ref_list("med", event.get("completion_evidence_media_ids"), f"hm09 {event['id']}")
            previous = event["action"]
        check(previous == ticket["status"], f"hm09 {ticket['id']}: trạng thái cuối khác status record")
        for appointment in ticket["appointments"]:
            appointment_count += 1
            check(appointment["status"] in {"proposed", "confirmed", "completed", "cancelled"},
                  f"hm09 {appointment['id']}: appointment status không hợp lệ")
            if appointment["status"] in {"confirmed", "completed"}:
                check(appointment["confirmed_at"] is not None,
                      f"hm09 {appointment['id']}: confirmed phải có thời điểm xác nhận")

    charged_refs = []
    for invoice in invoices:
        for line in invoice["lines"]:
            match = re.search(r"cost_event:(cst-[a-z0-9-]+)", line.get("source", ""))
            if match:
                charged_refs.append((match.group(1), line["line_id"]))
    check(sorted(charged_refs) == [("cst-002", "lin-005-8")],
          f"hm09: chỉ cst-002 được charge đúng một lần trên lin-005-8, thực tế {charged_refs}")
    for event in cost_events:
        ref("tkt", event["ticket_id"], f"hm09 {event['id']}")
        check(event["status"] in {"proposed", "superseded", "disputed", "confirmed"},
              f"hm09 {event['id']}: cost status không hợp lệ")
        if event["status"] == "confirmed" and event["payer"] == "renter":
            check(event.get("payer_accepted_at") is not None and event.get("basis"),
                  f"hm09 {event['id']}: charge renter phải có acceptance + căn cứ terms")
            check(parse_dt(event["payer_accepted_at"]) <= parse_dt(event["confirmed_at"]),
                  f"hm09 {event['id']}: acceptance phải trước khi confirmed")
        if event["status"] == "disputed":
            check(event.get("invoice_line_refs", []) == [],
                  f"hm09 {event['id']}: disputed cost không được vào invoice")
        if event["status"] in {"proposed", "superseded"}:
            check(event.get("invoice_line_refs", []) == [],
                  f"hm09 {event['id']}: quote/proposed không được vào invoice")
    charged_event_ids = {ref_[0] for ref_ in charged_refs}
    for event in cost_events:
        if event["status"] == "confirmed":
            if event["id"] in charged_event_ids:
                check(len([r for r in charged_refs if r[0] == event["id"]]) == 1,
                      f"hm09 {event['id']}: confirmed cost chỉ được charge một lần")
            else:
                check(event.get("invoice_line_refs", []) == [],
                      f"hm09 {event['id']}: declared refs nhưng chưa thấy line — kiểm khớp fixture state")

    expected9 = load(BASE / "hm09_maintenance/expected_outcomes.json")["expected_counts"]
    check(len(tickets) == expected9["tickets"], "hm09 counts: tickets")
    check(event_count == expected9["ticket_events"], "hm09 counts: ticket_events")
    check(appointment_count == expected9["appointments"], "hm09 counts: appointments")
    check(len(cost_events) == expected9["cost_events"], "hm09 counts: cost_events")
    check(sum(1 for c in cost_events if c["status"] == "confirmed") == expected9["confirmed_cost_events"],
          "hm09 counts: confirmed cost events")
    check(len(charged_refs) == expected9["charged_cost_events"], "hm09 counts: charged cost events")
    check(sum(1 for c in cost_events if c["status"] == "disputed") == expected9["disputed_cost_events"],
          "hm09 counts: disputed cost events")

    # ---- cross-pack sanity -----------------------------------------------------
    for tenancy in tenancies:
        contract = ctr_by[tenancy["contract_id"]]
        check(contract["physical_room_id"] == tenancy["physical_room_id"],
              f"hm07/hm02: tenancy {tenancy['id']} và contract không cùng phòng thực")
    for handover in handovers:
        tenancy = ten_by[handover["tenancy_id"]]
        if handover["kind"] == "move_in" and handover["status"] == "completed":
            check(tenancy["move_in_at"] is not None,
                  f"hm07 {handover['id']}: move-in handover nhưng tenancy chưa move-in")

    # ---- report ----------------------------------------------------------------
    print(f"Kiểm tra: {CHECKS} assertions trên {len(data)} file fixture.")
    if FAILURES:
        print(f"THẤT BẠI: {len(FAILURES)} lỗi")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("OK: mọi fixture packs v1 hợp lệ; oracle billing tính lại khớp expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
