from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from backend.app.locations import CITY_ALIASES
from backend.app.models import AffordabilityInput, Extraction, Profile, Quote, Room, Scenario

SUPPORTED_CITIES = frozenset(CITY_ALIASES)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data"


class EvaluationError(ValueError):
    pass


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def content_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def contained_path(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise EvaluationError("Artifact path escapes dataset directory")
    return path


def verify_manifest(data_dir: Path, manifest: dict) -> None:
    for name, expected in manifest["artifacts"].items():
        path = contained_path(data_dir, name)
        if not path.is_file() or sha256_file(path) != expected:
            raise EvaluationError(f"Dataset artifact hash mismatch: {name}")


def dataset_manifest(data_dir: Path) -> dict:
    frozen = data_dir / "manifests/input_manifest.json"
    path = frozen if frozen.exists() else data_dir / "manifests/development_manifest.json"
    value = read_json(path)
    verify_manifest(data_dir, value)
    return value


def load_profiles(data_dir: Path, split: str) -> list[dict]:
    if split not in ("dev", "test"):
        raise EvaluationError("Split must be dev or test")
    return read_jsonl(data_dir / f"profiles/{split}/profiles.jsonl")


def confirmed_profile(row: dict) -> Profile:
    payload = dict(row["confirmed_profile"])
    if "soft_description" in Profile.model_fields:
        payload["soft_description"] = row.get("confirmed_soft_description")
    return Profile.model_validate(payload)


def validate_dataset(data_dir: Path = DEFAULT_DATA) -> dict:
    manifest = dataset_manifest(data_dir)
    payload = read_json(data_dir / "catalog/rooms.json")
    rooms = [Room.model_validate(item) for item in payload["rooms"]]
    ids = [room.id for room in rooms]
    if len(ids) != len(set(ids)):
        raise EvaluationError("Canonical room IDs must be unique")
    if len(rooms) != manifest["canonical_rooms"]:
        raise EvaluationError("Catalog count disagrees with manifest")
    if any(not room.synthetic or room.city not in SUPPORTED_CITIES
           or not room.source.startswith("synthetic://") for room in rooms):
        raise EvaluationError("Core dataset must be explicit synthetic rooms in TP.HCM or Hà Nội")
    profile_ids, groups = set(), {"dev": set(), "test": set()}
    all_utterances, counts = set(), {}
    for split in ("dev", "test"):
        rows = load_profiles(data_dir, split)
        counts[split] = len(rows)
        for row in rows:
            if row["profile_id"] in profile_ids or row["split"] != split or not row["synthetic"]:
                raise EvaluationError("Duplicate profile ID or inconsistent split/synthetic flag")
            profile_ids.add(row["profile_id"])
            groups[split].add(row["group_id"])
            confirmed_profile(row)
            if not row["utterances"]:
                raise EvaluationError("Profile requires at least one utterance")
            for utterance in row["utterances"]:
                if utterance["utterance_id"] in all_utterances:
                    raise EvaluationError("Duplicate utterance ID")
                all_utterances.add(utterance["utterance_id"])
                Extraction.model_validate(utterance["gold"])
    if groups["dev"] & groups["test"]:
        raise EvaluationError("Paraphrase/profile group crosses dev/test split")
    expected_counts = {45: {"dev": 15, "test": 30}, 30: {"dev": 10, "test": 20}, 20: {"dev": 8, "test": 12}}
    if counts != expected_counts.get(manifest["gold_profiles"]):
        raise EvaluationError("Profile counts do not match accepted prototype split")
    for case in read_json(data_dir / "oracles/cost_cases.json")["cases"]:
        Quote.model_validate(case["quote"])
        Scenario.model_validate(case["scenario"])
        if "affordability" in case:
            AffordabilityInput.model_validate(case["affordability"])
        if case["origin"] != "authored_independent_arithmetic_constants":
            raise EvaluationError("Oracle origin must disclose independent authored calculations")
    aliases = read_json(data_dir / "catalog/alias_fixtures.json")["aliases"]
    if any(alias["canonical_room_id"] not in set(ids) for alias in aliases):
        raise EvaluationError("Alias references an unknown canonical room")
    metadata = read_json(data_dir / "catalog/metadata.json")
    if set(metadata) != set(ids):
        raise EvaluationError("Room metadata coverage is incomplete")
    report = {"status": "valid", "stage": manifest["stage"], "frozen": manifest["frozen"],
              "canonical_rooms": len(rooms), "profiles": counts, "utterances": len(all_utterances),
              "aliases_are_extra_rooms": False, "synthetic_ratio": 1.0,
              "unknown_capacity": sum(room.capacity is None for room in rooms),
              "unknown_availability": sum(room.available is None for room in rooms),
              "unpublished": sum(not room.published for room in rooms),
              "unavailable": sum(room.available is False for room in rooms),
              "unknown_fee_rates": sum(fee.amount_vnd is None and not fee.included_in_rent
                                       for room in rooms for fee in room.quote.fees),
              "unknown_amenities": sum(value is None for room in rooms for value in room.amenities.values()),
              "location_precision": dict(Counter(room.location_accuracy for room in rooms)),
              "cities": dict(Counter(room.city for room in rooms)),
              "room_types": dict(Counter(room.room_type for room in rooms)),
              "labels_status": "pending_human_judgments", "pii_exclusions": 0,
              "notice": "Validation of synthetic fixtures, not quality on the rental market."}
    return report
