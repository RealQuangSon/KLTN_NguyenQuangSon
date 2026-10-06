from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from pathlib import Path

from .costs import assess_affordability, calculate_cost, estimate_loan
from .locations import canonical_area, canonical_city
from .models import Candidate, Destination, Profile, Room

DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / "data" / "demo_rooms.json"
RANKING_CONFIG = {"version": "b1-p-v1", "weights": {"cost": 0.5, "preferences": 0.3, "location": 0.2},
                  "round_digits": 6, "tie_break": "room_id", "top_limit": 5,
                  "semantic_normalization": "1-cosine_distance/2"}


BAND_TRADEOFFS = {
    "can_nhac": "Tỷ lệ chi phí nhà ở trên thu nhập ở mức cần cân nhắc.",
    "vuot": "Tỷ lệ chi phí nhà ở trên thu nhập vượt mức khuyến nghị.",
}


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


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
            room = Room.model_validate(value)
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
                if room.bedrooms is None:
                    mark("verification", "bedrooms"); continue
                if room.bedrooms < profile.min_bedrooms:
                    mark("rejected", "bedrooms"); continue
            if room.available is None or room.capacity is None:
                mark("verification", "availability_or_capacity"); continue
            if not room.available or room.capacity < profile.scenario.people:
                mark("rejected", "availability_or_capacity"); continue
            required = [room.amenities.get(name) for name in profile.must_amenities]
            if any(value is False for value in required):
                mark("rejected", "required_amenity"); continue
            if any(value is None for value in required):
                mark("verification", "required_amenity"); continue

            distance = None
            if profile.destination:
                distance = distance_m(room, profile.destination)
                if distance is None:
                    mark("verification", "location"); continue
                error = room.uncertainty_m + profile.destination.uncertainty_m
                if max(0, distance - error) > profile.destination.max_distance_m:
                    mark("rejected", "distance"); continue
                if distance + error > profile.destination.max_distance_m:
                    mark("verification", "distance_boundary"); continue

            cost = calculate_cost(room.quote, profile.scenario)
            if profile.max_rent_vnd is not None and room.quote.rent_vnd > profile.max_rent_vnd:
                mark("rejected", "rent_budget"); continue
            if cost.monthly_total_vnd is None:
                mark("verification", "monthly_fees"); continue
            if cost.monthly_total_vnd > profile.max_monthly_cost_vnd:
                mark("rejected", "monthly_budget"); continue
            if profile.max_initial_cash_vnd is not None:
                if cost.initial_total_vnd is None:
                    mark("verification", "initial_fees"); continue
                shortfall = cost.initial_total_vnd - profile.max_initial_cash_vnd
                if shortfall > 0:
                    # Without a loan scenario cash is a hard limit; with one, the loan itself must fit.
                    if profile.loan is None:
                        mark("rejected", "initial_budget"); continue
                    loan = estimate_loan(shortfall, profile.loan)
                    if loan.exceeds_max_principal:
                        mark("rejected", "loan_principal"); continue
                    if cost.monthly_total_vnd + loan.installment_vnd > profile.max_monthly_cost_vnd:
                        mark("rejected", "loan_burden"); continue
            cost.affordability = assess_affordability(
                cost, people=profile.scenario.people, available_cash_vnd=profile.max_initial_cash_vnd,
                monthly_income_vnd=profile.monthly_income_vnd, cost_split=profile.cost_split, loan=profile.loan)

            components = {"cost": max(0, 1 - cost.monthly_total_vnd / profile.max_monthly_cost_vnd)}
            weights = {"cost": RANKING_CONFIG["weights"]["cost"]}
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
            if cost.initial_total_vnd is None:
                tradeoffs.append("Tiền ban đầu chưa đầy đủ: " + ", ".join(cost.missing_initial))
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
            verification += [f"fee_rate_unknown:{fee.name}" for fee in sorted(room.quote.fees, key=lambda f: f.name)
                             if fee.amount_vnd is None and fee.included_in_rent]
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
            ))
        candidates.sort(key=lambda item: (-item.score, item.room_id))
        return candidates, diagnostics

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
            candidates.sort(key=lambda item: (-item.score, item.room_id))
        elif method == "P":
            diagnostics["algorithm"] = "B1_structured_fallback" if not profile.soft_description else "P_empty"
        diagnostics.update(ranking_version=fingerprint(config), ranking_config=config,
                           profile_hash=fingerprint(profile.model_dump(mode="json")),
                           query_text_hash=fingerprint(profile.soft_description) if profile.soft_description else None)
        return candidates, diagnostics

    def match(self, profile: Profile, method: str = "B1") -> tuple[list[Candidate], dict]:
        candidates, diagnostics = self.rank(profile, method)
        return candidates[:RANKING_CONFIG["top_limit"]], diagnostics


class StoredCatalog(Catalog):
    """Versioned shared catalog; all mutations cooperate with the repository gate."""

    def __init__(self, repo, initial: Catalog | None = None):
        self.repo = repo
        with self.repo.guard():
            if not self.rooms():
                self.import_rooms((initial or Catalog()).rooms())

    def rooms(self) -> list[Room]:
        return [Room.model_validate_json(row["payload_json"]) for row in
                self.repo.db.execute("SELECT payload_json FROM hm_rooms ORDER BY id").fetchall()]

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
            values = [room.model_dump(mode="json") for room in self.rooms()]
            encoded = json.dumps(values, sort_keys=True, ensure_ascii=False).encode()
            version = hashlib.sha256(encoded).hexdigest()
            self.repo.db.execute("UPDATE hm_catalog_meta SET version=? WHERE id='catalog'", (version,))
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
        values = data.model_dump(mode="json")
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
            values = data.model_dump(mode="json", exclude={"expected_revision"})
            if values.get("occupancy"):
                values["available"] = values["occupancy"] == "vacant"
            changed = Room.model_validate({**room.model_dump(), **values, "revision": room.revision + 1})
            self.import_rooms([changed])
            return {"room": changed.model_dump(mode="json"), "catalog_version": self.version,
                    "previous": room.model_dump(mode="json")}
