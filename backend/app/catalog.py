from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path

from .conversations import mask_pii
from .costs import assess_affordability, calculate_cost, estimate_loan
from .locations import canonical_area, canonical_city
from .models import Candidate, Destination, Profile, Room

DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / "data" / "demo_rooms.json"
# b1-p-v2 (12/11/2026, UX-01/03): điểm chi phí tối đa cho mọi căn trong khoảng tiền
# khách nêu (chỉ thưởng căn rẻ khi khách nói "rẻ nhất"); thêm thành phần diện tích
# (chỉ tính khi hồ sơ có diện tích mong muốn). 13/11/2026: hòa điểm thì tin ghi đủ
# thông tin hơn (phí, sức chứa, diện tích) đứng trước, rồi mới tới mã phòng.
RANKING_CONFIG = {"version": "b1-p-v2",
                  "weights": {"cost": 0.5, "preferences": 0.3, "location": 0.2, "area": 0.2},
                  "round_digits": 6, "tie_break": "missing_info,room_id", "top_limit": 5,
                  "semantic_normalization": "1-cosine_distance/2"}


BAND_TRADEOFFS = {
    "can_nhac": "Tỷ lệ chi phí nhà ở trên thu nhập ở mức cần cân nhắc.",
    "vuot": "Tỷ lệ chi phí nhà ở trên thu nhập vượt mức khuyến nghị.",
}


# Tài khoản chủ nhà demo cũ mà migration 24 đã xóa. Snapshot crawl trước 15/11
# vẫn ghi các mã này, nên tin của họ về chủ nhà dùng thử theo thành phố, cùng
# quy tắc với landlord_for của data.generate và data.crawl_chotot.
LEGACY_LANDLORDS = frozenset({"owner-a", "owner-b", "owner-c", "owner-d"})


def trial_landlord_for(city: str) -> str:
    return "owner1" if city == "Hà Nội" else "owner2"


def with_current_landlord(room: Room) -> Room:
    if room.landlord_id not in LEGACY_LANDLORDS:
        return room
    return room.model_copy(update={"landlord_id": trial_landlord_for(room.city)})


# Landlord free text that the public listing page shows; contact details are
# masked once at write time (FC-01/F4) so no read path can leak them.
LISTING_TEXT_FIELDS = ("features_text", "house_rules", "description")


def missing_info(item: "Candidate") -> int:
    """Số mục thông tin chính tin đăng không ghi: từng khoản phí phải tạm tính, sức chứa,
    diện tích. Chỉ dùng để PHÁ HÒA giữa các căn cùng điểm (13/11/2026) — không vào điểm,
    không đọc ngày đăng, loại người đăng hay thuộc tính thương mại."""
    count = 1 if item.area_m2 is None else 0
    for label in item.verification:
        if label == "capacity_unknown":
            count += 1
        elif str(label).startswith("fee_assumed:"):
            count += len(str(label).split(":", 1)[1].split(","))
    return count


def _rank_key(item: "Candidate"):
    # Điểm cao trước; hòa điểm thì tin ghi đủ thông tin hơn trước; cuối cùng theo mã để tất định.
    return (-item.score, missing_info(item), item.room_id)


def mask_listing_text(values: dict) -> dict:
    for field in LISTING_TEXT_FIELDS:
        if isinstance(values.get(field), str):
            values[field] = mask_pii(values[field])
    return values


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


# UX-04: nhãn đọc tất định từ tiêu đề/mô tả đã che PII; chỉ là nhãn và (với tin
# "tìm bạn ở ghép") điều kiện sức chứa — KHÔNG vào điểm xếp hạng.
_ROOMMATE_WANTED = re.compile(
    r"\btim\s*(?:\d+\s*)?(?:ban|nguoi)(?:\s*(?:nu|nam))?\s*o\s*ghep|\btim\s*o\s*ghep|\bcan\s*(?:\d+\s*)?(?:ban|nguoi)\s*o\s*ghep")
_SHARED = re.compile(r"\bo\s*ghep\b|\bshare\s*phong|\bghep\s*phong|\broommate")
_FEMALE_ONLY = re.compile(r"\bcho\s*nu\s*thue|\bchi\s*(?:nhan|cho)\s*nu\b|\bdanh\s*cho\s*nu\b|\bnu\s*thue\b")
_MALE_ONLY = re.compile(r"\bcho\s*nam\s*thue|\bchi\s*(?:nhan|cho)\s*nam\b|\bdanh\s*cho\s*nam\b")


def listing_flags(room: Room) -> set[str]:
    text = normalize(" ".join(filter(None, [room.title, room.description])))
    text = "".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch)).replace("đ", "d")
    flags: set[str] = set()
    if _ROOMMATE_WANTED.search(text):
        flags |= {"roommate_wanted", "shared_listing"}
    elif _SHARED.search(text):
        flags.add("shared_listing")
    if _FEMALE_ONLY.search(text):
        flags.add("gender_female_only")
    if _MALE_ONLY.search(text):
        flags.add("gender_male_only")
    return flags


def distance_m(room: Room, target: Destination) -> float | None:
    if (room.location_accuracy == "area_only" or room.latitude is None
            or room.longitude is None or room.uncertainty_m is None):
        return None
    lat1, lat2 = math.radians(room.latitude), math.radians(target.latitude)
    dlat = lat2 - lat1
    dlon = math.radians(target.longitude - room.longitude)
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_000 * 2 * math.asin(min(1.0, math.sqrt(value)))


class Catalog:
    def __init__(self, path: Path = DEFAULT_CATALOG):
        self.path = Path(path)

    def rooms(self) -> list[Room]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        by_id: dict[str, Room] = {}
        for value in payload["rooms"]:
            room = with_current_landlord(Room.model_validate(value))
            previous = by_id.get(room.id)
            if previous and previous.revision == room.revision and previous != room:
                raise ValueError("Conflicting room records with the same ID and revision")
            if not previous or room.revision > previous.revision:
                by_id[room.id] = room
        return sorted(by_id.values(), key=lambda room: room.id)

    @property
    def version(self) -> str:
        values = [room.model_dump(mode="json") for room in self.rooms()]
        encoded = json.dumps(values, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(encoded).hexdigest()

    def eligible_candidates(self, profile: Profile) -> tuple[list[Candidate], dict]:
        candidates: list[Candidate] = []
        diagnostics = {"rejected": {}, "verification": {}}

        def mark(bucket: str, reason: str):
            counts = diagnostics[bucket]
            counts[reason] = counts.get(reason, 0) + 1

        # Aliases ("Sài Gòn", "Q7", "Bình Thạnh") compare equal to the canonical catalog names.
        city = normalize(canonical_city(profile.city))
        area = normalize(canonical_area(profile.area, profile.city)) if profile.area else None
        for room in self.rooms():
            if not room.published:
                continue
            if normalize(canonical_city(room.city)) != city:
                mark("rejected", "city"); continue
            if area and normalize(canonical_area(room.area, room.city)) != area:
                mark("rejected", "area"); continue
            if room.room_type != profile.room_type:
                mark("rejected", "room_type"); continue
            if profile.min_bedrooms is not None:
                if room.bedrooms is not None and room.bedrooms < profile.min_bedrooms:
                    mark("rejected", "bedrooms"); continue
            # D-12: tin thiếu sức chứa/phí KHÔNG bị giữ — hiện ngay kèm nhãn.
            # available False hoặc sức chứa rõ mà ít hơn số người vẫn là điều kiện cứng.
            if room.available is False or (room.capacity is not None and room.capacity < profile.scenario.people):
                mark("rejected", "availability_or_capacity"); continue
            flags = listing_flags(room)
            # UX-04: tin "tìm bạn ở ghép" chỉ còn 1 chỗ — loại như sức chứa không đủ khi từ 2 người.
            if "roommate_wanted" in flags and profile.scenario.people >= 2:
                mark("rejected", "availability_or_capacity"); continue
            if profile.min_area_hard and profile.min_area_m2 and room.area_m2 is not None \
                    and room.area_m2 < profile.min_area_m2:
                mark("rejected", "min_area"); continue
            required = [room.amenities.get(name) for name in profile.must_amenities]
            if any(value is False for value in required):
                mark("rejected", "required_amenity"); continue
            if any(value is None for value in required):
                mark("rejected", "required_amenity"); continue

            distance = None
            if profile.destination:
                distance = distance_m(room, profile.destination)
                if distance is None:
                    mark("rejected", "location"); continue
                error = room.uncertainty_m + profile.destination.uncertainty_m
                if max(0, distance - error) > profile.destination.max_distance_m:
                    mark("rejected", "distance"); continue
                if distance + error > profile.destination.max_distance_m:
                    mark("rejected", "distance"); continue

            # D-12: tổng tháng luôn tính được — phí thiếu theo giả định chuẩn có ghi
            # nguồn (Candidate.verification nhãn "estimated_total"); điều kiện cứng
            # (trần tiền) lọc trên tổng ước tính như tổng thường.
            cost = calculate_cost(room.quote, profile.scenario, accept_estimated_fees=True)
            if profile.max_rent_vnd is not None and room.quote.rent_vnd > profile.max_rent_vnd:
                mark("rejected", "rent_budget"); continue
            if cost.monthly_total_vnd is None:
                mark("rejected", "monthly_fees"); continue
            if profile.max_monthly_cost_vnd is not None and cost.monthly_total_vnd > profile.max_monthly_cost_vnd:
                mark("rejected", "monthly_budget"); continue
            if profile.max_initial_cash_vnd is not None:
                if cost.initial_total_vnd is None:
                    mark("rejected", "initial_fees"); continue
                shortfall = cost.initial_total_vnd - profile.max_initial_cash_vnd
                if shortfall > 0:
                    # Without a loan scenario cash is a hard limit; with one, the loan itself must fit.
                    if profile.loan is None:
                        mark("rejected", "initial_budget"); continue
                    loan = estimate_loan(shortfall, profile.loan)
                    if loan.exceeds_max_principal:
                        mark("rejected", "loan_principal"); continue
                    if profile.max_monthly_cost_vnd is not None \
                            and cost.monthly_total_vnd + loan.installment_vnd > profile.max_monthly_cost_vnd:
                        mark("rejected", "loan_burden"); continue
            cost.affordability = assess_affordability(
                cost, people=profile.scenario.people, available_cash_vnd=profile.max_initial_cash_vnd,
                monthly_income_vnd=profile.monthly_income_vnd, cost_split=profile.cost_split, loan=profile.loan)

            components = {"cost": self._cost_score(profile, room.quote.rent_vnd, cost.monthly_total_vnd)}
            weights = {"cost": RANKING_CONFIG["weights"]["cost"]}
            if profile.min_area_m2 and room.area_m2 is not None:
                # Diện tích chưa rõ thì không cộng, không trừ (không có thành phần này).
                components["area"] = min(1.0, room.area_m2 / profile.min_area_m2)
                weights["area"] = RANKING_CONFIG["weights"]["area"]
            if profile.preferences:
                components["preferences"] = sum(room.amenities.get(name) is True
                                                 for name in profile.preferences) / len(profile.preferences)
                weights["preferences"] = RANKING_CONFIG["weights"]["preferences"]
            if profile.destination:
                # Use the conservative upper distance for both acceptance and scoring.
                upper = distance + room.uncertainty_m + profile.destination.uncertainty_m
                components["location"] = max(0, 1 - upper / profile.destination.max_distance_m)
                weights["location"] = RANKING_CONFIG["weights"]["location"]
            score = sum(weights[key] * value for key, value in components.items()) / sum(weights.values())
            reasons = [f"Tổng tháng {cost.monthly_total_vnd:,} VND trong kịch bản đã xác nhận."]
            reasons += [f"Có {name} theo nguồn tin." for name in profile.must_amenities]
            reasons += [f"Đáp ứng sở thích {name} theo nguồn tin."
                        for name in profile.preferences if room.amenities.get(name) is True]
            tradeoffs = [f"Sở thích {name}: thiếu bằng chứng hoặc không có."
                        for name in profile.preferences if room.amenities.get(name) is not True]
            if profile.min_area_m2 and room.area_m2 is not None and room.area_m2 < profile.min_area_m2:
                tradeoffs.append(f"Nhỏ hơn mong muốn {profile.min_area_m2} m².")
            if profile.min_rent_vnd and room.quote.rent_vnd < profile.min_rent_vnd:
                tradeoffs.append("Tiền thuê thấp hơn khoảng bạn nêu.")
            if cost.initial_total_vnd is None:
                tradeoffs.append("Tiền ban đầu chưa đầy đủ: " + ", ".join(cost.missing_initial))
            if cost.assumed_fees:
                tradeoffs.append("Phí " + ", ".join(cost.assumed_fees)
                                 + " đang theo giả định chuẩn vì tin không ghi — cần xác minh lại khi xem.")
            if profile.destination:
                reasons.append("Đạt bán kính đường thẳng khi tính cả sai số vị trí đã khai báo.")
            if loan_estimate := cost.affordability.loan:
                reasons.append(f"Cần vay {loan_estimate.principal_vnd:,} VND, trả góp "
                               f"{loan_estimate.installment_vnd:,} VND/tháng trong {loan_estimate.term_months} tháng.")
            if cost.affordability.band in BAND_TRADEOFFS:
                tradeoffs.append(BAND_TRADEOFFS[cost.affordability.band])
            # Listing-level data-quality flags: unknown evidence and location precision.
            verification = [f"amenity_unknown:{name}" for name, value in sorted(room.amenities.items())
                            if value is None]
            if profile.min_bedrooms is not None and room.bedrooms is None:
                verification.append("bedrooms_unknown")
            if room.capacity is None:
                # D-12: sức chứa chưa ghi — hiển thị "chưa rõ", không chặn.
                verification.append("capacity_unknown")
            if cost.assumed_fees:
                verification.append("fee_assumed:" + ",".join(cost.assumed_fees))
            verification += [f"fee_rate_unknown:{fee.name}" for fee in sorted(room.quote.fees, key=lambda f: f.name)
                             if fee.amount_vnd is None and fee.included_in_rent]
            if profile.min_area_m2 and room.area_m2 is None:
                verification.append("area_unknown")
            verification += sorted(flag for flag in listing_flags(room) if flag != "roommate_wanted")
            if "roommate_wanted" in listing_flags(room):
                verification.append("roommate_wanted")
            if room.location_accuracy == "area_only":
                verification.append("location_area_only")
            elif room.location_accuracy == "approximate":
                verification.append("location_approximate")
            if room.uncertainty_m is not None and room.uncertainty_m >= 200:
                verification.append(f"location_uncertainty_{int(room.uncertainty_m)}m")
            candidates.append(Candidate(
                room_id=room.id, room_revision=room.revision, title=room.title,
                city=room.city, area=room.area, area_m2=room.area_m2,
                room_type=room.room_type, bedrooms=room.bedrooms, landlord_id=room.landlord, cost=cost,
                score=round(score, RANKING_CONFIG["round_digits"]), components=components, reasons=reasons,
                tradeoffs=tradeoffs, source=room.source, synthetic=room.synthetic,
                verification=verification,
                latitude=room.latitude, longitude=room.longitude,
                location_accuracy=room.location_accuracy, uncertainty_m=room.uncertainty_m,
            ))
        candidates.sort(key=_rank_key)
        # D-12: tổng khớp + chất lượng dữ liệu để nói thật ("N căn khớp, M căn có
        # tổng tháng ước tính").
        diagnostics["total_matches"] = len(candidates)
        diagnostics["exact_cost_matches"] = sum(1 for item in candidates if not item.verification)
        diagnostics["estimated_matches"] = sum(
            1 for item in candidates if any(str(label).startswith("fee_assumed")
                                            for label in item.verification))
        return candidates, diagnostics

    @staticmethod
    def _cost_score(profile: Profile, rent_vnd: int, monthly_total_vnd: int) -> float:
        """Q2 (12/11): trong khoảng tiền khách nêu thì điểm chi phí bằng nhau (tối đa);
        dưới cận dưới giảm dần; chỉ thưởng căn rẻ khi khách nói "rẻ nhất"; khách nói
        "tầm X" (budget_approx) thì căn gần mức X hơn điểm cao hơn."""
        if profile.prefer_cheapest:
            if profile.max_monthly_cost_vnd is not None:
                return max(0.0, 1 - monthly_total_vnd / profile.max_monthly_cost_vnd)
            if profile.max_rent_vnd is not None:
                return max(0.0, 1 - rent_vnd / profile.max_rent_vnd)
        if profile.min_rent_vnd and rent_vnd < profile.min_rent_vnd:
            return max(0.0, rent_vnd / profile.min_rent_vnd)
        if profile.budget_approx and not profile.min_rent_vnd:
            # 13/11: "tầm X" — căn có giá càng gần mức X càng điểm cao (X vẫn là trần cứng).
            if profile.max_rent_vnd is not None:
                return min(1.0, rent_vnd / profile.max_rent_vnd)
            if profile.max_monthly_cost_vnd is not None:
                return min(1.0, monthly_total_vnd / profile.max_monthly_cost_vnd)
        return 1.0

    def rank(self, profile: Profile, method: str = "B1") -> tuple[list[Candidate], dict]:
        from .models import DomainError
        if method not in {"B1", "P"}:
            raise DomainError("invalid_method", "Phương pháp xếp hạng không được hỗ trợ.", 422)
        candidates, diagnostics = self.eligible_candidates(profile)
        diagnostics["algorithm"] = "B1"
        config = {**RANKING_CONFIG, "method": method}
        if method == "P" and candidates and profile.soft_description:
            scorer = getattr(self, "semantic_scorer", None)
            if scorer is None:
                raise DomainError("semantic_unavailable", "Chưa có embedding/vector để chạy P.", 503)
            scores = scorer.similarities(profile.soft_description, [item.room_id for item in candidates])
            if set(scores) != {item.room_id for item in candidates}:
                raise DomainError("semantic_unavailable", "Vector chưa phủ toàn bộ tập phòng đủ điều kiện.", 503)
            alpha = getattr(self, "alpha", 0.3)
            provider = getattr(scorer, "provider", None)
            config.update(alpha=alpha, embedding_model=getattr(provider, "model", None),
                          embedding_dimensions=getattr(provider, "dimensions", None))
            for item in candidates:
                semantic = float(scores[item.room_id])
                if not math.isfinite(semantic) or not 0 <= semantic <= 1:
                    raise DomainError("semantic_unavailable", "Điểm semantic không hợp lệ.", 503)
                item.components["semantic"] = semantic
                item.score = round((1 - alpha) * item.score + alpha * semantic, RANKING_CONFIG["round_digits"])
                item.algorithm = "hybrid_p_v1"
            diagnostics["algorithm"] = "P"
            candidates.sort(key=_rank_key)
        elif method == "P":
            diagnostics["algorithm"] = "B1_structured_fallback" if not profile.soft_description else "P_empty"
        diagnostics.update(ranking_version=fingerprint(config), ranking_config=config,
                           profile_hash=fingerprint(profile.model_dump(mode="json")),
                           query_text_hash=fingerprint(profile.soft_description) if profile.soft_description else None)
        return candidates, diagnostics

    def match(self, profile: Profile, method: str = "B1") -> tuple[list[Candidate], dict]:
        # D-12: diagnostics (total_matches/exact/estimated) đã có từ rank trên TOÀN
        # tập — cắt top 5 sau khi đếm, không đếm lại trên tập đã cắt.
        candidates, diagnostics = self.rank(profile, method)
        return candidates[:RANKING_CONFIG["top_limit"]], diagnostics


class StoredCatalog(Catalog):
    """Versioned shared catalog; all mutations cooperate with the repository gate."""

    def __init__(self, repo, initial: Catalog | None = None):
        self.repo = repo
        # (catalog version, raw payloads). Every write goes through import_rooms, which
        # bumps the version, so a matching version means the rows are unchanged. Only
        # JSON is cached; each call builds fresh Room objects, so callers never share state.
        self._payloads: tuple[str, list[str]] | None = None
        # Lỗi 5 (15/11): một lượt chat đọc rooms() ~6 lần (ngữ cảnh, lớp hỏi lại,
        # xếp hạng, criteria…) — parse lại toàn kho mỗi lần tốn CPU thuần (kho cào
        # ~4k tin). Cache bản Room đã parse THEO VERSION; import_rooms vô hiệu hóa.
        # Trả bản sao LIST mới mỗi lần nên caller vẫn không chia sẻ list mutable
        # (các Room bên trong được codebase coi là bất biến — không ai ghi tại chỗ).
        self._parsed: tuple[str, list[Room]] | None = None
        with self.repo.guard():
            stored = self._load_rooms()
            if not stored:
                self.import_rooms((initial or Catalog()).rooms())
            else:
                self._release_legacy_landlords(stored)

    def _release_legacy_landlords(self, rooms: list[Room]) -> None:
        """Move rooms of the retired demo landlords to the trial landlord of their city.

        A normalization, not an edit: the revision stays, so re-importing the same old
        snapshot (remapped by Catalog.rooms) stays a no-op. One bulk UPDATE per target
        keeps it to a few round trips on hosted PostgreSQL."""
        targets: dict[str, list[str]] = {}
        for room in rooms:
            if room.landlord_id in LEGACY_LANDLORDS:
                targets.setdefault(trial_landlord_for(room.city), []).append(room.id)
        if not targets:
            return
        payload = ("jsonb_set(payload_json::jsonb,'{landlord_id}',to_jsonb(?::text))::text"
                   if self.repo.db.postgres else "json_set(payload_json,'$.landlord_id',?)")
        # Runs inside the caller's guard() transaction.
        for landlord_id, room_ids in targets.items():
            for start in range(0, len(room_ids), 500):
                chunk = room_ids[start:start + 500]
                self.repo.db.execute(
                    f"UPDATE hm_rooms SET payload_json={payload} "
                    f"WHERE id IN ({','.join('?' * len(chunk))})", (landlord_id, *chunk))
        self._store_version()

    def _store_version(self) -> None:
        # Uncached: the rows just changed but the stored version has not been bumped yet.
        self._payloads = None
        self._parsed = None
        values = [room.model_dump(mode="json") for room in self._load_rooms()]
        encoded = json.dumps(values, sort_keys=True, ensure_ascii=False).encode()
        version = hashlib.sha256(encoded).hexdigest()
        self.repo.db.execute("UPDATE hm_catalog_meta SET version=? WHERE id='catalog'", (version,))

    def _load_payloads(self) -> list[str]:
        return [row["payload_json"] for row in
                self.repo.db.execute("SELECT payload_json FROM hm_rooms ORDER BY id").fetchall()]

    def _load_rooms(self) -> list[Room]:
        return [Room.model_validate_json(payload) for payload in self._load_payloads()]

    def rooms(self) -> list[Room]:
        # Hosted PostgreSQL makes the full read costly (2.5 MB per call for ~2,800 rooms);
        # the version probe is one small row.
        version = self.version
        if self._parsed is not None and self._parsed[0] == version:
            return list(self._parsed[1])
        if self._payloads is None or self._payloads[0] != version:
            self._payloads = (version, self._load_payloads())
        parsed = [Room.model_validate_json(payload) for payload in self._payloads[1]]
        self._parsed = (version, parsed)
        return list(parsed)

    @property
    def version(self) -> str:
        return self.repo.db.execute("SELECT version FROM hm_catalog_meta WHERE id='catalog'").fetchone()["version"]

    def import_rooms(self, rooms: list[Room]):
        from .models import DomainError
        valid = [Room.model_validate(room.model_dump()) for room in rooms]
        if len({room.id for room in valid}) != len(valid):
            raise DomainError("invalid_catalog", "Canonical room ID không được lặp trong lô nhập.", 422)
        with self.repo.guard():
            current = {room.id: room for room in self.rooms()}
            for room in valid:
                old = current.get(room.id)
                if old and (room.revision < old.revision or
                            (room.revision == old.revision and room != old)):
                    raise DomainError("catalog_conflict", "Dữ liệu không khớp phiên bản kho hiện tại.")
                self.repo.db.execute("INSERT INTO hm_rooms(id,revision,payload_json) VALUES(?,?,?) "
                                     "ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload_json=excluded.payload_json",
                                     (room.id, room.revision, room.model_dump_json()))
            self._store_version()
        return self.version

    def room(self, room_id: str) -> Room:
        from .models import DomainError
        row = self.repo.db.execute("SELECT payload_json FROM hm_rooms WHERE id=?", (room_id,)).fetchone()
        if row is None:
            raise DomainError("not_found", "Không tìm thấy phòng.", 404)
        return Room.model_validate_json(row["payload_json"])

    def change_status(self, room_id: str, request, landlord_id: str | None = None):
        """Publish/availability/occupancy change with CAS; a landlord may only touch own rooms."""
        from .models import DomainError
        with self.repo.guard():
            room = next((room for room in self.rooms() if room.id == room_id), None)
            if room is None or (landlord_id is not None and room.landlord != landlord_id):
                raise DomainError("not_found", "Không tìm thấy phòng.", 404)
            if room.revision != request.expected_revision:
                raise DomainError("catalog_conflict", "Kho phòng đã đổi; hãy tải lại.")
            update = request.model_dump(exclude_unset=True, exclude={"expected_revision"})
            if not update or ("published" in update and update["published"] is None):
                raise DomainError("invalid_catalog", "Cần trạng thái published/available hợp lệ.", 422)
            if update.get("occupancy"):
                # Deposited or rented rooms leave the eligible set; vacant ones become available again.
                update["available"] = update["occupancy"] == "vacant"
            changed = Room.model_validate({**room.model_dump(), **update, "revision": room.revision + 1})
            self.import_rooms([changed])
            return {"room": changed.model_dump(mode="json"), "catalog_version": self.version,
                    "previous": room.model_dump(mode="json")}

    def create_room(self, landlord_id: str, data) -> dict:
        from uuid import uuid4
        room_id = f"room-{uuid4().hex[:10]}"
        values = mask_listing_text(data.model_dump(mode="json"))
        if values.get("occupancy"):
            values["available"] = values["occupancy"] == "vacant"
        room = Room.model_validate({**values, "id": room_id, "revision": 1, "landlord_id": landlord_id,
                                    "source": f"landlord://{landlord_id}/{room_id}", "synthetic": False})
        self.import_rooms([room])
        return {"room": room.model_dump(mode="json"), "catalog_version": self.version}

    def update_room(self, room_id: str, landlord_id: str, data) -> dict:
        from .models import DomainError
        with self.repo.guard():
            room = self.room(room_id)
            if room.landlord != landlord_id:
                raise DomainError("not_found", "Không tìm thấy phòng.", 404)
            if room.revision != data.expected_revision:
                raise DomainError("catalog_conflict", "Tin đã đổi; hãy tải lại trước khi sửa.")
            values = mask_listing_text(data.model_dump(mode="json", exclude={"expected_revision"}))
            if values.get("occupancy"):
                values["available"] = values["occupancy"] == "vacant"
            changed = Room.model_validate({**room.model_dump(), **values, "revision": room.revision + 1})
            self.import_rooms([changed])
            return {"room": changed.model_dump(mode="json"), "catalog_version": self.version,
                    "previous": room.model_dump(mode="json")}
