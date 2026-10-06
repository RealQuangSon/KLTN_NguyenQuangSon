"""Offline business-invariant and grounding suites (EV-04).

Machine-verifiable functional checks against the hashed dataset; they are not
relevance judgments and never substitute the blind human labels of DATA-05.
"""
from __future__ import annotations

import json
import re
import tempfile
from collections import Counter
from pathlib import Path

from backend.app.catalog import Catalog, distance_m, normalize
from backend.app.catalog import BAND_TRADEOFFS
from backend.app.costs import assess_affordability, calculate_cost, estimate_loan
from backend.app.locations import canonical_area, canonical_city
from backend.app.models import Profile, Room

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


def invariants_report(data_dir: Path, split: str, output: Path, catalog: Catalog | None = None) -> dict:
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
            cost = calculate_cost(room.quote, profile.scenario)
            check("published", room.published is True, f"published={room.published}")
            check("available", room.available is True, f"available={room.available}")
            check("capacity", room.capacity is not None and room.capacity >= profile.scenario.people,
                  f"capacity={room.capacity}, people={profile.scenario.people}")
            check("city", normalize(canonical_city(room.city)) == normalize(canonical_city(profile.city)),
                  f"room={room.city}, profile={profile.city}")
            check("area", profile.area is None or normalize(canonical_area(room.area, room.city))
                  == normalize(canonical_area(profile.area, profile.city)),
                  f"room={room.area}, profile={profile.area}")
            check("room_type", room.room_type == profile.room_type, f"room_type={room.room_type}")
            check("bedrooms", profile.min_bedrooms is None
                  or (room.bedrooms is not None and room.bedrooms >= profile.min_bedrooms),
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
    counterfactual, flip_enforced = _counterfactual_checks(data_dir, split, reference, rows, violations)
    failed = sum(violations.values())
    summary = {"kind": "offline_hard_constraint_invariants", "stage": manifest["stage"], "split": split,
               "input_manifest_hash": content_hash(manifest), "code_hashes": code_hashes(),
               "catalog_hash": reference.version, "profile_count": len(rows),
               "eligible_candidate_checks": sum(row["eligible_count"] for row in rows),
               "violations": dict(violations), "failed": failed, "passed": failed == 0,
               "counterfactual": counterfactual, "availability_flip_enforced": flip_enforced,
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
                           violations: Counter) -> tuple[dict, bool | None]:
    """Commercial/marketing metadata must not move ranking; an availability flip must be enforced."""
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
        if not any(row["eligible_count"] for row in rows):
            return {"mutation": "title+source commercial text", "profiles_compared": 0,
                    "invariant_holds": True, "positive_control": "skipped_no_eligible_room"}, None
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
        counterfactual = {"mutation": "title+source commercial text (commission, days on market)", "profiles_compared": len(profiles),
                          "invariant_holds": violations["marketing_metadata_changed_ranking"] == 0,
                          "flipped_room_id": target_id,
                          "positive_control": "available=false removed from eligible set"
                          if enforced else "flip_not_enforced"}
        return counterfactual, enforced


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
                   and amount <= profile.max_monthly_cost_vnd,
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
