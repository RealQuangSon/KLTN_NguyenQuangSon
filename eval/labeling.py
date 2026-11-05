"""DA-05: research-evaluation tooling — blind sheets, label reports, survey reports.

The agent never invents labels or survey answers: `label-sheet` only builds a
shuffled, method-blinded template; `label-report` and `survey-report` only
aggregate human-filled files. Synthetic fixtures for tests live in tmp_path;
`eval/labels/` is git-ignored because real labels stay under the user's control.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path
from statistics import mean, stdev

from .common import EvaluationError, read_json, read_jsonl, write_json
from .metrics import ranking_metrics

SHEET_FIELDS = ("profile_id", "room_id", "need", "room_info", "label", "annotator", "note")
KEY_FIELDS = ("profile_id", "room_id", "rank", "method")
ALIAS_POOL = ("goi-m", "goi-n", "goi-p", "goi-q", "goi-r", "goi-s")
# Renter money never leaves the confirmed profile into an annotation artifact.
MASKED_PROFILE_KEYS = ("max_monthly_cost_vnd", "max_initial_cash_vnd", "monthly_income_vnd",
                       "loan", "cost_split")
SURVEY_NUMERIC = ("sus1", "sus2", "sus3", "sus4", "sus5", "sus6",
                  "trust_explanation", "satisfaction_suggestions", "privacy_financial")


def _need_text(profile: dict) -> str:
    parts = []
    for key, prefix in (("city", ""), ("area", ""), ("room_type", "loại: ")):
        if profile.get(key):
            parts.append(f"{prefix}{profile[key]}")
    if profile.get("bedrooms"):
        parts.append(f"{profile['bedrooms']} phòng ngủ")
    scenario = profile.get("scenario") or {}
    if scenario.get("people"):
        parts.append(f"{scenario['people']} người ở")
    if profile.get("must_amenities"):
        parts.append("bắt buộc: " + ", ".join(profile["must_amenities"]))
    if profile.get("preferences"):
        parts.append("sở thích: " + ", ".join(profile["preferences"]))
    if profile.get("min_bedrooms"):
        parts.append(f"tối thiểu {profile['min_bedrooms']} phòng ngủ")
    if profile.get("needs_destination"):
        parts.append("cần gần trường/nơi làm")
    if profile.get("soft_description"):
        parts.append(profile["soft_description"])
    return "; ".join(parts)


def _room_info(room: dict, item: dict) -> str:
    amenities = ", ".join(name for name, value in room["amenities"].items() if value is True)
    parts = [room["title"].split(". ")[0], f"{room['city']} · {room['area']}",
             f"loại {room['room_type']}", f"{room['area_m2']} m²", f"sức chứa {room['capacity']}",
             f"tiện ích: {amenities or '—'}",
             f"thuê {room['quote']['rent_vnd']:,} VND/tháng",
             f"tổng tháng theo engine: {item['cost']['monthly_total_vnd']:,} VND"]
    return "; ".join(parts)


def label_sheet(data_dir: Path, split: str, method: str, run_dir: Path, labels_dir: Path) -> dict:
    """Build one shuffled, method-blinded CSV template; the mapping goes to *.key.csv."""
    run = read_json(run_dir / "run_manifest.json")
    if run["split"] != split:
        raise EvaluationError(f"Run directory holds split {run['split']}, not {split}")
    rooms = {room["id"]: room for room in read_json(data_dir / "catalog/rooms.json")["rooms"]}
    rows = []
    for row in read_jsonl(run_dir / "rankings.jsonl"):
        ranking = row["methods"].get(method)
        if not ranking or not ranking.get("items"):
            continue
        for position, item in enumerate(ranking["items"][:5], 1):
            room = rooms[item["room_id"]]
            rows.append({"profile_id": row["profile_id"], "room_id": item["room_id"],
                         "need": _need_text(row["confirmed_profile"]),
                         "room_info": _room_info(room, item), "label": "", "annotator": "",
                         "note": "", "rank": position})
    if not rows:
        raise EvaluationError(f"Method {method} has no ranked items to label in this run")
    existing = {path.name for path in labels_dir.glob("*.key.csv")}
    rng = random.Random(20261001)
    alias = next((name for name in sorted(ALIAS_POOL) if f"sheet-{name}.key.csv" not in existing), None)
    if alias is None:
        raise EvaluationError("All blind aliases are used; archive the labeled round first")
    rng.shuffle(rows)
    labels_dir.mkdir(parents=True, exist_ok=True)
    sheet_path = labels_dir / f"sheet-{alias}.csv"
    with sheet_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SHEET_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    key_path = labels_dir / f"sheet-{alias}.key.csv"
    with key_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=KEY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({"profile_id": item["profile_id"], "room_id": item["room_id"],
                          "rank": item["rank"], "method": method} for item in rows)
    return {"kind": "blind_label_sheet", "split": split, "method": method, "alias": alias,
            "sheet_path": str(sheet_path), "key_path": str(key_path), "rows": len(rows),
            "notice": "Method name appears only in the key file; annotators never see it. "
                      "Labels are filled by humans; the agent never pre-fills them."}


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def cohens_kappa(labels_a: list[int], labels_b: list[int]) -> float | None:
    """Unweighted Cohen's kappa over paired labels (equal length, same items)."""
    if not labels_a:
        return None
    categories = sorted(set(labels_a) | set(labels_b))
    n = len(labels_a)
    po = sum(a == b for a, b in zip(labels_a, labels_b)) / n
    pe = sum(labels_a.count(c) * labels_b.count(c) for c in categories) / n ** 2
    return None if pe == 1 else (po - pe) / (1 - pe)


def label_report(labels_dir: Path, output: Path) -> dict:
    """Aggregate filled blind sheets: nDCG@5/P@5 per method and annotator agreement."""
    keys = {path.name.removesuffix(".key.csv"): _read_csv(path)
            for path in labels_dir.glob("*.key.csv")}
    if not keys:
        raise EvaluationError("No *.key.csv found; build sheets with label-sheet first")
    filled = [path for path in labels_dir.glob("sheet-*.csv") if not path.name.endswith(".key.csv")]
    judgments: dict[str, dict[str, dict[tuple[str, str], int]]] = {}
    for path in filled:
        # Key names are stems like "sheet-<alias>"; annotator copies add a suffix.
        alias = next((name for name in keys if path.name == f"{name}.csv"
                      or path.name.startswith(f"{name}-")), None)
        if alias is None:
            raise EvaluationError(f"Sheet {path.name} has no matching key file; blinded files must stay paired")
        for row in _read_csv(path):
            annotator = (row.get("annotator") or "").strip() or path.stem
            label = (row.get("label") or "").strip()
            if not label:
                continue
            if label not in ("0", "1", "2", "3"):
                raise EvaluationError(f"Label must be 0–3: {path.name} {row.get('profile_id')}/{row.get('room_id')}")
            target = judgments.setdefault(annotator, {}).setdefault(alias, {})
            key = (row["profile_id"], row["room_id"])
            if key in target:
                raise EvaluationError(f"Duplicate label by {annotator}: {key}")
            target[key] = int(label)
    per_method: dict[str, dict] = {}
    method_of = {}
    for alias, mapping in keys.items():
        for entry in mapping:
            method = entry["method"]
            if method_of.setdefault(method, alias) != alias:
                raise EvaluationError(f"Alias mapping conflicts for method {method}")
    for method, alias in method_of.items():
        ranked: dict[str, list[str]] = {}
        for entry in keys[alias]:
            ranked.setdefault(entry["profile_id"], []).append(entry["room_id"])
        annotator_rows = {}
        for annotator, per_alias in sorted(judgments.items()):
            labels = per_alias.get(alias, {})
            if not labels:
                continue
            metrics = [ranking_metrics(rooms, {room_id: labels[(profile_id, room_id)]
                                               for room_id in rooms if (profile_id, room_id) in labels})
                       for profile_id, rooms in sorted(ranked.items())]
            complete = [item for item in metrics if item["status"] == "complete"]
            scored = [item for item in complete if item["ndcg_at_5"] is not None]
            annotator_rows[annotator] = {
                "judged_pairs": len(labels),
                "complete_profiles": len(complete),
                "ndcg_at_5": mean(item["ndcg_at_5"] for item in scored) if scored else None,
                "precision_at_5": mean(item["precision_at_5"] for item in complete) if complete else None}
        values = [row for row in annotator_rows.values() if row["ndcg_at_5"] is not None]
        per_method[method] = {"alias": alias, "annotators": annotator_rows,
                              "ndcg_at_5_mean": mean(row["ndcg_at_5"] for row in values) if values else None,
                              "precision_at_5_mean": mean(row["precision_at_5"] for row in values) if values else None,
                              "notice": "Pool-based top-5 only; incomplete annotators are excluded from means."}
    kappa_rows = []
    annotators = sorted(judgments)
    for i, left in enumerate(annotators):
        for right in annotators[i + 1:]:
            shared_aliases = set(judgments[left]) & set(judgments[right])
            pairs = [(a_label, judgments[right][alias][key])
                     for alias in shared_aliases
                     for key, a_label in judgments[left][alias].items()
                     if key in judgments[right][alias]]
            kappa_rows.append({"annotator_a": left, "annotator_b": right, "shared_pairs": len(pairs),
                               "agreement_rate": sum(a == b for a, b in pairs) / len(pairs) if pairs else None,
                               "cohens_kappa": cohens_kappa([a for a, _ in pairs], [b for _, b in pairs])
                               if pairs else None})
    summary = {"kind": "human_label_report", "labels_dir": str(labels_dir),
               "filled_sheets": len(filled), "annotators": annotators,
               "methods": per_method,
               "agreement": {"pairwise": kappa_rows,
                             "status": "ok" if len(annotators) >= 2 else "needs_2_annotators"},
               "notice": "Metrics only over human-declared labels; no machine labels substituted."}
    write_json(output, summary)
    return summary


def survey_report(csv_path: Path, output: Path) -> dict:
    """Aggregate human survey CSV rows; per-question mean/stdev and the short SUS score."""
    rows = _read_csv(csv_path)
    if not rows:
        raise EvaluationError("Survey CSV has no rows")
    missing = [column for column in ("respondent_id", *SURVEY_NUMERIC) if column not in rows[0]]
    if missing:
        raise EvaluationError(f"Survey CSV misses columns: {', '.join(missing)}")
    columns: dict[str, dict] = {}
    for column in SURVEY_NUMERIC:
        values = [int(row[column]) for row in rows if (row[column] or "").strip()]
        columns[column] = {"n": len(values),
                           "mean": round(mean(values), 4) if values else None,
                           "stdev": round(stdev(values), 4) if len(values) > 1 else None}
    sus = []
    for row in rows:
        values = [row[name] for name in ("sus1", "sus2", "sus3", "sus4", "sus5", "sus6")]
        if not all(value.strip() for value in values):
            continue
        adjusted = [int(value) - 1 if index % 2 == 0 else 5 - int(value)
                    for index, value in enumerate(values)]
        sus.append(2.5 * sum(adjusted))
    summary = {"kind": "human_survey_report", "respondents": len(rows),
               "per_question": columns,
               "sus_score": {"n": len(sus), "mean": round(mean(sus), 2) if sus else None,
                             "stdev": round(stdev(sus), 2) if len(sus) > 1 else None,
                             "scale": "0–100, shortened 6-item SUS, alternating polarity"},
               "notice": "Aggregates human-entered answers only; the agent never fabricates responses."}
    write_json(output, summary)
    return summary
