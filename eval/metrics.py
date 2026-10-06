from __future__ import annotations

import math
import random
import statistics
from collections import Counter

from .common import EvaluationError


def ranking_metrics(room_ids: list[str], judgments: dict[str, int], k: int = 5) -> dict:
    if len(room_ids) > k or len(room_ids) != len(set(room_ids)):
        raise EvaluationError("Ranking must contain at most k distinct canonical room IDs")
    if any(type(label) is not int or not 0 <= label <= 3 for label in judgments.values()):
        raise EvaluationError("Relevance labels must be integers 0–3")
    unjudged = [room_id for room_id in room_ids if room_id not in judgments]
    if unjudged:
        return {"status": "incomplete", "unjudged_ids": unjudged, "returned_count": len(room_ids),
                "precision_at_5": None, "actual_return_precision": None, "ndcg_at_5": None}
    relevant = sum(judgments[room_id] >= 2 for room_id in room_ids)
    dcg = sum((2 ** judgments[room_id] - 1) / math.log2(index + 2)
              for index, room_id in enumerate(room_ids))
    ideal = sorted(judgments.values(), reverse=True)[:k]
    idcg = sum((2 ** label - 1) / math.log2(index + 2) for index, label in enumerate(ideal))
    return {"status": "complete", "unjudged_ids": [], "returned_count": len(room_ids),
            "precision_at_5": relevant / k,
            "actual_return_precision": relevant / len(room_ids) if room_ids else None,
            "ndcg_at_5": dcg / idcg if idcg > 0 else None,
            "idcg": idcg, "idcg_zero": idcg == 0,
            "judgment_scope": "pooled_top5_not_full_catalog", "full_catalog_recall": "not_measured"}


def normalized_slot(value):
    if isinstance(value, str):
        return " ".join(value.casefold().split())
    return value


def extraction_metrics(rows: list[dict]) -> dict:
    """Micro slot/value F1; wrong scalar adds FP+FN, null is absence, bool=False is a value.

    Preferences are canonical amenity sets. No TN for two absent values; intent is separate.
    """
    fields = ("city", "area", "people", "preferences", "needs_destination")
    counts = {field: Counter(tp=0, fp=0, fn=0) for field in fields}
    intent_correct = 0
    failures = 0
    by_profile: dict[str, list[dict]] = {}
    for row in rows:
        expected, predicted = row["gold"], row.get("predicted")
        by_profile.setdefault(row["profile_id"], []).append(row)
        if predicted is None:
            failures += 1
            # Failure has no extracted slots; gold slots count as false negatives.
            predicted = {}
        else:
            intent_correct += predicted.get("intent") == expected["intent"]
        for field in fields:
            def slots(payload):
                value = payload.get(field)
                if field == "preferences":
                    return {normalized_slot(item) for item in (value or [])}
                return set() if value is None else {normalized_slot(value)}
            gold, actual = slots(expected), slots(predicted)
            counts[field]["tp"] += len(gold & actual)
            counts[field]["fp"] += len(actual - gold)
            counts[field]["fn"] += len(gold - actual)
    per_field = {}
    for field, count in counts.items():
        tp, fp, fn = (count[key] for key in ("tp", "fp", "fn"))
        denominator = 2 * tp + fp + fn
        per_field[field] = {**count, "precision": tp / (tp + fp) if tp + fp else None,
                           "recall": tp / (tp + fn) if tp + fn else None,
                           "f1": 2 * tp / denominator if denominator else None}
    tp, fp, fn = (sum(count[key] for count in counts.values()) for key in ("tp", "fp", "fn"))
    return {"field_mapping": list(fields), "per_field": per_field,
            "micro_f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "intent_accuracy": intent_correct / len(rows) if rows else None,
            "utterance_count": len(rows), "profile_count": len(by_profile), "failure_count": failures,
            "ambiguity_note": "Unsupported inferred fields are FP; question correctness needs conversation traces, not extraction alone.",
            "statistical_unit": "profile_group; utterance counts are descriptive, not independent participants"}


def paired_summary(per_profile: list[dict], metric: str, seed: int = 20261001, samples: int = 1000) -> dict:
    included, excluded = [], []
    for row in per_profile:
        left, right = row["methods"].get("B1"), row["methods"].get("P")
        if left and right and left["status"] == right["status"] == "complete" and left.get(metric) is not None and right.get(metric) is not None:
            included.append((row["profile_id"], left[metric], right[metric]))
        else:
            excluded.append({"profile_id": row["profile_id"], "reason": "missing_error_unjudged_or_undefined",
                             "B1_status": left.get("status") if left else "missing",
                             "P_status": right.get("status") if right else "missing"})
    if not included:
        return {"metric": metric, "status": "unavailable", "paired_count": 0,
                "included_profile_ids": [], "excluded": excluded, "whole_test_count": len(per_profile)}
    differences = [right - left for _, left, right in included]
    mean_b1 = statistics.mean(left for _, left, _ in included)
    effect = statistics.mean(differences)
    rng = random.Random(seed)
    bootstrap = sorted(statistics.mean(rng.choice(differences) for _ in differences) for _ in range(samples))
    return {"metric": metric, "status": "conditional_quality", "paired_count": len(included),
            "whole_test_count": len(per_profile), "included_profile_ids": [item[0] for item in included],
            "excluded": excluded, "B1_mean": mean_b1, "P_mean": statistics.mean(right for _, _, right in included),
            "absolute_effect": effect, "relative_effect": effect / mean_b1 if mean_b1 else None,
            "bootstrap_ci95": [bootstrap[int(samples * .025)], bootstrap[min(samples - 1, int(samples * .975))]],
            "bootstrap_seed": seed, "bootstrap_samples": samples,
            "statistical_unit": "profile_group", "notice": "Small synthetic sample; pooled judgments, conditional coverage; not population inference."}
