"""DA-01: gold intent cases, determinism, schema and the offline routing suite."""
from typing import get_args

from backend.app.interpreter import DemoInterpreter, fixed_intent
from backend.app.schemas import MessageResult

from data.generate import generate
from eval.common import read_json, sha256_file
from eval.intents import decide_intent, intents_report


def _allowed_intents() -> set[str]:
    # simulate_finance joins the MessageResult Literal when AG-02 lands; the union
    # keeps this schema check stable before and after that change.
    return set(get_args(MessageResult.model_fields["intent"].annotation)) | {"simulate_finance"}


def test_intent_cases_generate_deterministically_with_expected_mix(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    generate(first)
    generate(second)
    assert sha256_file(first / "profiles/intent_cases.json") == \
        sha256_file(second / "profiles/intent_cases.json")
    payload = read_json(first / "profiles/intent_cases.json")
    assert payload["counts"]["by_intent"] == {"calculate_cost": 6, "find_room": 6, "handbook": 8,
                                              "human_support": 6, "simulate_finance": 8, "unknown": 4}
    share = payload["counts"]["by_split"]["dev"] / sum(payload["counts"]["by_intent"].values())
    assert 0.35 <= share <= 0.45  # plan asks for roughly 40% dev / 60% test
    ids = [case["case_id"] for case in payload["cases"]]
    assert len(ids) == len(set(ids)) == 38
    for case in payload["cases"]:
        assert case["intent"] in _allowed_intents()
        assert case["split"] in ("dev", "test") and case["text"].strip()


def test_decide_intent_mirrors_chat_graph_route_rule():
    # Explicit fixed_intent wins before any extraction, exactly like node `route`.
    assert decide_intent("Tính chi phí vào ở giúp mình") == "calculate_cost"
    assert decide_intent("Cho gặp nhân viên tư vấn") == "human_support"
    assert decide_intent("Nội quy gửi xe thế nào?") == "handbook"
    # Without a fixed rule the demo extraction intent decides.
    assert decide_intent("tim phong q7 1 nguoi") == DemoInterpreter().extract("tim phong q7 1 nguoi").intent
    assert decide_intent("hello") == "unknown"


def test_intents_suite_runs_on_dev_and_records_errors_without_gating(tmp_path):
    dataset, output = tmp_path / "data", tmp_path / "intents.json"
    generate(dataset)
    report = intents_report(dataset, "dev", output)
    assert report["case_count"] == 15 and output.is_file()
    assert report["gate"] == "measurement_only_no_accuracy_threshold" and report["failed"] == 0
    # Wrong predictions are recorded, never hidden or relabelled.
    assert report["errors"] and all(row["gold"] != row["predicted"] for row in report["errors"])
    assert sum(row["total"] for row in report["per_intent"].values()) == 15
    assert set(report["confusion_matrix"]) <= set(report["per_intent"])


def test_intents_suite_respects_split_partition(tmp_path):
    dataset = tmp_path / "data"
    generate(dataset)
    payload = read_json(dataset / "profiles/intent_cases.json")
    dev = {case["case_id"] for case in payload["cases"] if case["split"] == "dev"}
    test_ids = {case["case_id"] for case in payload["cases"] if case["split"] == "test"}
    assert not dev & test_ids
    report = intents_report(dataset, "dev", tmp_path / "dev.json")
    assert report["case_count"] == len(dev) == 15
