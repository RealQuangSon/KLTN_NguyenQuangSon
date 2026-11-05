"""AG-11: gold data/gold/clarify_cases.json — kiểm cơ chế phần đo được offline
(mơ hồ bán kính điểm đến) và thống kêprecision/recall của quyết định hỏi."""
import json
import re
from pathlib import Path

from backend.app.locations import resolve_place

GOLD = json.loads((Path(__file__).resolve().parents[2] / "data/gold/clarify_cases.json")
                  .read_text(encoding="utf-8"))["cases"]
RADIUS_KEYWORDS = re.compile(r"\b(?:bán kính|km|cách|trong vòng)\b", re.I)


def test_gold_has_at_least_40_labelled_cases():
    assert len(GOLD) >= 40
    assert all(case.get("case_id") and "should_ask" in case for case in GOLD)


def test_destination_radius_ask_decision_matches_gold():
    """Nhãn gold cho nhóm bán kính: hỏi khi có điểm mốc trong danh mục và chưa
    nói bán kính; không hỏi khi đã nói bán kính hoặc không có điểm mốc."""
    hits = misses = 0
    for case in GOLD:
        if case["ambiguity"] != "destination_radius":
            continue
        has_place = resolve_place(case["text"]) is not None
        radius_given = bool(RADIUS_KEYWORDS.search(case["text"]))
        predicted_ask = has_place and not radius_given
        expected_ask = case["should_ask"] == "yes"
        if predicted_ask == expected_ask:
            hits += 1
        else:
            misses += 1
    total = hits + misses
    precision = hits / total if total else 0.0
    assert precision >= 0.9, f"gold destination-radius ask-decision: {hits}/{total}"
