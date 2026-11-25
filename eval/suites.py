"""Offline business-invariant and grounding suites (EV-04).

Machine-verifiable functional checks against the hashed dataset; they are not
relevance judgments and never substitute the blind human labels of DATA-05.
"""
from __future__ import annotations

import json
import re
import tempfile
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.catalog import Catalog, distance_m, normalize
from backend.app.catalog import BAND_TRADEOFFS
from backend.app.costs import assess_affordability, calculate_cost, estimate_loan
from backend.app.locations import canonical_area, canonical_city
from backend.app.models import Actor, Profile, PromotionInput, Room
from backend.app.promotions import today_vn
from backend.app.service import HomeMatchService

from .common import (ROOT, EvaluationError, confirmed_profile, content_hash, dataset_manifest,
                     load_profiles, read_json, read_jsonl, sha256_file, write_json)
from .pipeline import code_hashes, require_split_ready

MONTHLY_CLAIM = re.compile(r"^Tổng tháng ([\d.,]+) VND trong kịch bản đã xác nhận\.$")
MUST_CLAIM = re.compile(r"^Có (.+) theo nguồn tin\.$")
PREF_CLAIM = re.compile(r"^Đáp ứng sở thích (.+) theo nguồn tin\.$")
DISTANCE_CLAIM = "Đạt bán kính đường thẳng khi tính cả sai số vị trí đã khai báo."
PREF_MISSING = re.compile(r"^Sở thích (.+): thiếu bằng chứng hoặc không có\.$")
INITIAL_INCOMPLETE = "Tiền ban đầu chưa đầy đủ:"
LOAN_CLAIM = re.compile(r"^Cần vay ([\d,]+) VND, trả góp ([\d,]+) VND/tháng trong (\d+) tháng\.$")
BAND_CLAIMS = {text: band for band, text in BAND_TRADEOFFS.items()}


def _rooms_by_id(catalog: Catalog) -> dict[str, Room]:
    return {room.id: room for room in catalog.rooms()}


def invariants_report(data_dir: Path, split: str, output: Path, catalog: Catalog | None = None,
                      promotion_service_factory: Callable[[Path], HomeMatchService] | None = None) -> dict:
    """Re-verify hard constraints on every eligible room, dedup and counterfactual fairness (AC15)."""
    manifest = require_split_ready(data_dir, split)
    reference = catalog or Catalog(data_dir / "catalog/rooms.json")
    rooms = _rooms_by_id(reference)
    violations: Counter[str] = Counter()
    rows: list[dict] = []
    for profile_row in load_profiles(data_dir, split):
        profile = confirmed_profile(profile_row)
        eligible, _ = reference.eligible_candidates(profile)
        profile_violations = []
        for candidate in eligible:
            room = rooms.get(candidate.room_id)

            def check(name: str, ok: bool, detail: str):
                if not ok:
                    violations[name] += 1
                    profile_violations.append({"room_id": candidate.room_id, "check": name, "detail": detail})

            if room is None:
                check("room_resolves", False, "eligible room missing from hashed catalog")
                continue
            # D-12 (08/11): thiếu dữ liệu (available/capacity/bedrooms None) KHÔNG còn
            # loại căn — hiện kèm nhãn "chưa rõ"; chỉ known-false mới là vi phạm.
            cost = calculate_cost(room.quote, profile.scenario, accept_estimated_fees=True)
            check("published", room.published is True, f"published={room.published}")
            check("available", room.available is not False, f"available={room.available}")
            check("capacity", room.capacity is None or room.capacity >= profile.scenario.people,
                  f"capacity={room.capacity}, people={profile.scenario.people}")
            check("city", normalize(canonical_city(room.city)) == normalize(canonical_city(profile.city)),
                  f"room={room.city}, profile={profile.city}")
            check("area", profile.area is None or normalize(canonical_area(room.area, room.city))
                  == normalize(canonical_area(profile.area, profile.city)),
                  f"room={room.area}, profile={profile.area}")
            check("room_type", room.room_type == profile.room_type, f"room_type={room.room_type}")
            check("bedrooms", profile.min_bedrooms is None
                  or room.bedrooms is None or room.bedrooms >= profile.min_bedrooms,
                  f"bedrooms={room.bedrooms}, min={profile.min_bedrooms}")
            check("monthly_budget", cost.monthly_total_vnd is not None
                  and cost.monthly_total_vnd <= profile.max_monthly_cost_vnd,
                  f"monthly={cost.monthly_total_vnd}, budget={profile.max_monthly_cost_vnd}")
            shortfall = (None if profile.max_initial_cash_vnd is None or cost.initial_total_vnd is None
                         else cost.initial_total_vnd - profile.max_initial_cash_vnd)
            loan = estimate_loan(shortfall, profile.loan) if profile.loan and shortfall and shortfall > 0 else None
            check("initial_budget", profile.max_initial_cash_vnd is None
                  or (shortfall is not None and (shortfall <= 0 or loan is not None)),
                  f"initial={cost.initial_total_vnd}, cash={profile.max_initial_cash_vnd}, loan={profile.loan}")
            if loan is not None:
                check("loan_principal", not loan.exceeds_max_principal,
                      f"principal={loan.principal_vnd}, cap={profile.loan.max_principal_vnd}")
                check("loan_burden", cost.monthly_total_vnd is not None
                      and cost.monthly_total_vnd + loan.installment_vnd <= profile.max_monthly_cost_vnd,
                      f"monthly={cost.monthly_total_vnd}, installment={loan.installment_vnd}")
            check("must_amenities", all(room.amenities.get(name) is True for name in profile.must_amenities),
                  f"must={profile.must_amenities}, room={ {k: room.amenities.get(k) for k in profile.must_amenities} }")
            if profile.destination:
                value = distance_m(room, profile.destination)
                upper = None if value is None else value + room.uncertainty_m + profile.destination.uncertainty_m
                check("distance", upper is not None and upper <= profile.destination.max_distance_m,
                      f"upper={upper}, max={profile.destination.max_distance_m}")
        if len({candidate.room_id for candidate in eligible}) != len(eligible):
            violations["canonical_dedup"] += 1
            profile_violations.append({"room_id": "*", "check": "canonical_dedup", "detail": "duplicate canonical id"})
        rows.append({"profile_id": profile_row["profile_id"], "eligible_count": len(eligible),
                     "violations": profile_violations})
    counterfactual, flip_enforced = _counterfactual_checks(data_dir, split, reference, rows, violations,
                                                            promotion_service_factory)
    failed = sum(violations.values())
    summary = {"kind": "offline_hard_constraint_invariants", "stage": manifest["stage"], "split": split,
               "input_manifest_hash": content_hash(manifest), "code_hashes": code_hashes(),
               "catalog_hash": reference.version, "profile_count": len(rows),
               "eligible_candidate_checks": sum(row["eligible_count"] for row in rows),
               "violations": dict(violations), "failed": failed, "passed": failed == 0,
               "counterfactual": counterfactual, "availability_flip_enforced": flip_enforced,
               "promotion_rank_changes": counterfactual["promotion"]["changed"],
               "rows": rows,
               "notice": "Functional re-verification of engine behavior on synthetic fixtures; "
                         "not market evidence and not relevance labels."}
    write_json(output, summary)
    return summary


def _write_catalog_file(path: Path, rooms: list[Room]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"rooms": [room.model_dump(mode="json") for room in rooms]}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _counterfactual_checks(data_dir: Path, split: str, reference: Catalog, rows: list[dict],
                           violations: Counter,
                           promotion_service_factory: Callable[[Path], HomeMatchService] | None = None
                           ) -> tuple[dict, bool | None]:
    """Commercial/marketing metadata and landlord promotions must not move ranking;
    an availability flip must be enforced."""
    profiles = [(row["profile_id"], confirmed_profile(profile_row))
                for row, profile_row in zip(rows, load_profiles(data_dir, split))]
    base: dict[str, list] = {}
    for profile_id, profile in profiles:
        ranked, _ = reference.rank(profile, method="B1")
        base[profile_id] = [(item.room_id, item.score, item.components) for item in ranked]
    with tempfile.TemporaryDirectory(prefix="homematch-eval-cf-") as directory:
        root = Path(directory)
        # Commission and time-on-market ("căn tồn") are commercial facts the ranking must ignore.
        promo_rooms = [room.model_copy(update={"title": room.title + " | Hoa hồng giới thiệu 30% | Tồn kho 120 ngày",
                                               "source": f"synthetic://promo/{room.id}"})
                       for room in reference.rooms()]
        promo_path = root / "promo.json"
        _write_catalog_file(promo_path, promo_rooms)
        promo = Catalog(promo_path)
        for profile_id, profile in profiles:
            ranked, _ = promo.rank(profile, method="B1")
            mutated = [(item.room_id, item.score, item.components) for item in ranked]
            if mutated != base[profile_id]:
                violations["marketing_metadata_changed_ranking"] += 1
        # LF-01/F2: posting time and poster kind must never move the AI ranking.
        # The fixed anchor keeps the pass deterministic; every room is mutated.
        listing_meta = _listing_meta_counterfactual(reference, profiles, base, violations, root)
        if not any(row["eligible_count"] for row in rows):
            return {"mutation": "title+source commercial text", "profiles_compared": 0,
                    "invariant_holds": True, "positive_control": "skipped_no_eligible_room",
                    "listing_meta": {"mutation": "posted_at (-1 year, +1 day), poster_kind (broker<->null), "
                                                 "source_images and poster_name on every room",
                                     "profiles_compared": 0, "posted_at_past_changed": 0,
                                     "posted_at_future_changed": 0, "poster_kind_changed": 0,
                                     "source_images_changed": 0, "poster_name_changed": 0,
                                     "invariant_holds": True,
                                     "positive_control": "skipped_no_eligible_room"},
                    "promotion": {"mutation": "hm_promotions row via HomeMatchService.set_promotion",
                                  "promoted_room_id": None, "profiles_compared": 0, "changed": 0,
                                  "invariant_holds": True,
                                  "positive_control": "skipped_no_eligible_room"}}, None
        target_id = None
        for _, profile in profiles:
            ranked, _ = reference.rank(profile, method="B1")
            if ranked:
                target_id = ranked[0].room_id
                break
        flipped_rooms = [room.model_copy(update={"available": False}) if room.id == target_id else room
                         for room in reference.rooms()]
        flipped_path = root / "flipped.json"
        _write_catalog_file(flipped_path, flipped_rooms)
        flipped = Catalog(flipped_path)
        enforced = None
        for profile_id, profile in profiles:
            base_ids = [item[0] for item in base[profile_id]]
            if target_id in base_ids:
                eligible_now, _ = flipped.eligible_candidates(profile)
                ids_now = {candidate.room_id for candidate in eligible_now}
                removed = target_id not in ids_now
                enforced = removed if enforced is None else (enforced and removed)
                if not removed:
                    violations["availability_flip_not_enforced"] += 1
        promotion = _promotion_counterfactual(reference, profiles, target_id, violations, root,
                                              promotion_service_factory or HomeMatchService)
        counterfactual = {"mutation": "title+source commercial text (commission, days on market)", "profiles_compared": len(profiles),
                          "invariant_holds": violations["marketing_metadata_changed_ranking"] == 0,
                          "flipped_room_id": target_id,
                          "positive_control": "available=false removed from eligible set"
                          if enforced else "flip_not_enforced",
                          "listing_meta": listing_meta,
                          "promotion": promotion}
        return counterfactual, enforced


_LISTING_META_ANCHOR = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _listing_meta_counterfactual(reference: Catalog, profiles: list[tuple[str, Profile]],
                                 base: dict[str, list], violations: Counter, root: Path) -> dict:
    """LF-01/F2: the AI ranking must not read posted_at or poster_kind. Every room
    gets its posting time shifted back a year, then forward a day, then its poster
    kind swapped (broker<->null); the ranked (room_id, score, components) tuples
    must stay identical to the unmutated baseline in all three passes. CA-04: the
    same holds for display-only crawl fields (source_images, poster_name)."""
    rooms = reference.rooms()
    mutations = {
        "posted_at_past": [{"posted_at": (room.posted_at or _LISTING_META_ANCHOR) - timedelta(days=365)}
                           for room in rooms],
        "posted_at_future": [{"posted_at": (room.posted_at or _LISTING_META_ANCHOR) + timedelta(days=1)}
                             for room in rooms],
        "poster_kind": [{"poster_kind": None if room.poster_kind == "broker" else "broker"}
                        for room in rooms],
        "source_images": [{"source_images": [f"https://cdn.chotot.com/{room.id}/1.jpg",
                                             f"https://cdn.chotot.com/{room.id}/2.jpg"]}
                          for room in rooms],
        "poster_name": [{"poster_name": f"Người đăng {room.id}"} for room in rooms],
        # Media và thông số hiển thị từ tin cào không đổi thứ hạng.
        "source_videos": [{"source_videos": [{"url": f"https://{index}.videodelivery.net/x/manifest/video.m3u8",
                                              "thumbnail": None}]}
                          for index, room in enumerate(rooms)],
        "listing_specs": [{"floor": str(index % 6), "direction": "Đông",
                           "balcony_direction": "Nam", "property_subtype": "Phòng trọ"}
                          for index, room in enumerate(rooms)],
        # Kiểm chứng tin (prepay, ảnh dùng chung) không vào xếp hạng.
        "trust_signals": [{"description": "Đặt cọc trước khi xem để giữ chỗ. " + (room.description or ""),
                           "source_images": [f"https://cdn.chotot.com/shared/{room.id}.jpg"]}
                          for room in rooms],
    }
    changed = {name: 0 for name in mutations}
    for name, updates in mutations.items():
        path = root / f"{name}.json"
        _write_catalog_file(path, [room.model_copy(update=update)
                                   for room, update in zip(rooms, updates)])
        mutated_catalog = Catalog(path)
        for profile_id, profile in profiles:
            ranked, _ = mutated_catalog.rank(profile, method="B1")
            if [(item.room_id, item.score, item.components) for item in ranked] != base[profile_id]:
                changed[name] += 1
                violations[f"{name}_changed_ranking"] += 1
    total = sum(changed.values())
    return {"mutation": "posted_at (-1 year, +1 day), poster_kind (broker<->null), "
                        "source_images, poster_name, source_videos, listing specs and "
                        "trust signals (prepay phrase, shared image) on every room",
            "profiles_compared": len(profiles),
            "posted_at_past_changed": changed["posted_at_past"],
            "posted_at_future_changed": changed["posted_at_future"],
            "poster_kind_changed": changed["poster_kind"],
            "source_images_changed": changed["source_images"],
            "poster_name_changed": changed["poster_name"],
            "source_videos_changed": changed["source_videos"],
            "listing_specs_changed": changed["listing_specs"],
            "trust_signals_changed": changed["trust_signals"],
            "invariant_holds": total == 0,
            "positive_control": "ranked tuples compared against unmutated baseline"}


def _promotion_counterfactual(reference: Catalog, profiles: list[tuple[str, Profile]],
                              target_id: str, violations: Counter, root: Path,
                              service_factory: Callable[[Path], HomeMatchService]) -> dict:
    """DA-04: a promotion written through the BE-07 service API onto hm_promotions
    (throwaway SQLite DB, same pattern as the invoices suite) must leave the ranked
    room_id order identical; the listing DTO must surface it as a positive control.
    The baseline is the same service catalog ranked before the write, so the
    promotion row is the only variable between the two passes."""
    landlord = next(room.landlord for room in reference.rooms() if room.id == target_id)
    service = service_factory(root / "promotion.sqlite")
    changed, visible = 0, False
    try:
        service.catalog.import_rooms(reference.rooms())
        without = {}
        for profile_id, profile in profiles:
            ranked, _ = service.catalog.rank(profile, method="B1")
            without[profile_id] = [item.room_id for item in ranked]
        service.set_promotion(Actor(id=landlord, role="owner"), target_id,
                              PromotionInput(text="Ưu đãi synthetic kiểm công bằng xếp hạng",
                                             valid_until=today_vn() + timedelta(days=30)))
        visible = service.listing(target_id)["promotion"] is not None
        for profile_id, profile in profiles:
            ranked, _ = service.catalog.rank(profile, method="B1")
            if [item.room_id for item in ranked] != without[profile_id]:
                changed += 1
    finally:
        service.close()
    if changed:
        violations["promotion_changed_ranking"] += changed
    if not visible:
        violations["promotion_not_visible"] += 1
    return {"mutation": "hm_promotions row via HomeMatchService.set_promotion",
            "promoted_room_id": target_id, "profiles_compared": len(profiles), "changed": changed,
            "invariant_holds": changed == 0,
            "positive_control": "promotion visible on listing DTO" if visible else "promotion_not_visible"}


def grounding_report(data_dir: Path, run_dir: Path, output: Path) -> dict:
    """Check every explanation claim against room evidence at the ranked revision."""
    manifest = dataset_manifest(data_dir)
    run = read_json(run_dir / "run_manifest.json")
    if sha256_file(run_dir / "rankings.jsonl") != run["rankings_hash"]:
        raise EvaluationError("Rankings hash mismatch")
    if run["input_manifest_hash"] != content_hash(manifest):
        raise EvaluationError("Ranking run and dataset manifest differ")
    rooms = _rooms_by_id(Catalog(data_dir / "catalog/rooms.json"))
    claim_counts: Counter[str] = Counter()
    unsupported: Counter[str] = Counter()
    rows = []
    for row in read_jsonl(run_dir / "rankings.jsonl"):
        profile = confirmed_profile(row)
        for method, value in row["methods"].items():
            for item in value["items"]:
                findings = _check_item(profile, item, rooms, claim_counts, unsupported)
                rows.append({"profile_id": row["profile_id"], "method": method,
                             "room_id": item["room_id"], "findings": findings})
    total_claims = sum(claim_counts.values())
    failed = sum(unsupported.values())
    summary = {"kind": "offline_explanation_grounding", "stage": run["stage"], "split": run["split"],
               "input_manifest_hash": content_hash(manifest), "code_hashes": code_hashes(),
               "rankings_hash": run["rankings_hash"], "items_checked": len(rows),
               "claim_counts": dict(claim_counts), "total_claims": total_claims,
               "unsupported": dict(unsupported), "failed": failed, "passed": failed == 0,
               "evidence_recompute": "finance engine on the hashed room quote at the ranked revision; "
                                     "oracle independence stays with the 15-case cost oracle",
               "rows": rows,
               "notice": "Template-claim verification on synthetic fixtures; not human judgment of usefulness."}
    write_json(output, summary)
    return summary


def _check_item(profile: Profile, item: dict, rooms: dict[str, Room],
                claim_counts: Counter, unsupported: Counter) -> list[dict]:
    findings = []

    def record(claim: str, supported: bool, detail: str):
        claim_counts[claim] += 1
        if not supported:
            unsupported[claim] += 1
            findings.append({"claim": claim, "detail": detail})

    room = rooms.get(item["room_id"])
    if room is None or room.revision != item["room_revision"]:
        record("room_revision", False, f"room={item['room_id']} revision={item['room_revision']}")
        return findings
    cost = calculate_cost(room.quote, profile.scenario)
    affordability = assess_affordability(
        cost, people=profile.scenario.people, available_cash_vnd=profile.max_initial_cash_vnd,
        monthly_income_vnd=profile.monthly_income_vnd, cost_split=profile.cost_split, loan=profile.loan)
    cited_preferences: set[str] = set()
    monthly_cited = False
    must_cited: set[str] = set()
    for reason in item["reasons"]:
        if match := MONTHLY_CLAIM.match(reason):
            amount = int(match[1].replace(",", ""))
            monthly_cited = True
            record("monthly_total", amount == cost.monthly_total_vnd
                   and (profile.max_monthly_cost_vnd is None or amount <= profile.max_monthly_cost_vnd),
                   f"claim={amount}, computed={cost.monthly_total_vnd}, budget={profile.max_monthly_cost_vnd}")
        elif match := MUST_CLAIM.match(reason):
            name = match[1]
            must_cited.add(name)
            record("required_amenity", name in profile.must_amenities
                   and room.amenities.get(name) is True, f"amenity={name}, value={room.amenities.get(name)}")
        elif match := PREF_CLAIM.match(reason):
            name = match[1]
            cited_preferences.add(name)
            record("preference_satisfied", name in profile.preferences
                   and room.amenities.get(name) is True, f"amenity={name}, value={room.amenities.get(name)}")
        elif match := LOAN_CLAIM.match(reason):
            claimed = (int(match[1].replace(",", "")), int(match[2].replace(",", "")), int(match[3]))
            loan = affordability.loan
            actual = (loan.principal_vnd, loan.installment_vnd, loan.term_months) if loan else None
            record("loan_estimate", claimed == actual, f"claim={claimed}, computed={actual}")
        elif reason == DISTANCE_CLAIM:
            value = distance_m(room, profile.destination) if profile.destination else None
            upper = None if value is None else value + room.uncertainty_m + profile.destination.uncertainty_m
            record("distance_radius", upper is not None and upper <= profile.destination.max_distance_m,
                  f"upper={upper}, max={profile.destination.max_distance_m if profile.destination else None}")
        else:
            record("unparsed_reason", False, reason[:120])
    for tradeoff in item["tradeoffs"]:
        if match := PREF_MISSING.match(tradeoff):
            name = match[1]
            cited_preferences.add(name)
            record("preference_missing", name in profile.preferences
                   and room.amenities.get(name) is not True, f"amenity={name}, value={room.amenities.get(name)}")
        elif tradeoff in BAND_CLAIMS:
            record("affordability_band", BAND_CLAIMS[tradeoff] == affordability.band,
                   f"claim={BAND_CLAIMS[tradeoff]}, computed={affordability.band}")
        elif tradeoff.startswith(INITIAL_INCOMPLETE):
            record("initial_incomplete", cost.initial_total_vnd is None and bool(cost.missing_initial),
                  f"initial={cost.initial_total_vnd}, missing={cost.missing_initial}")
        else:
            record("unparsed_tradeoff", False, tradeoff[:120])
    if not monthly_cited:
        record("missing_monthly_claim", False, "no monthly total citation in reasons")
    for name in profile.must_amenities:
        if name not in must_cited:
            record("missing_must_citation", False, f"must amenity {name} not cited")
    for name in profile.preferences:
        if name not in cited_preferences:
            record("missing_preference_citation", False, f"preference {name} not cited either way")
    return findings
