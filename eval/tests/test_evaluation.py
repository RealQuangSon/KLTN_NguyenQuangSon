import math
from types import SimpleNamespace

import pytest

from data.generate import generate
from eval.common import ROOT, EvaluationError, read_json, validate_dataset
from backend.app.catalog import Catalog
from eval.metrics import extraction_metrics, paired_summary, ranking_metrics
from eval.pipeline import evaluate_rankings, freeze_inputs, oracle_report, ranking_run


def test_precision_and_pool_ndcg_use_hand_calculated_values():
    result = ranking_metrics(["b", "a"], {"a": 3, "b": 2})
    assert result["precision_at_5"] == 2 / 5
    assert result["actual_return_precision"] == 1
    assert result["ndcg_at_5"] == pytest.approx((3 + 7 / math.log2(3)) / (7 + 3 / math.log2(3)))
    assert result["full_catalog_recall"] == "not_measured"


def test_unjudged_is_missing_and_zero_idcg_is_undefined():
    missing = ranking_metrics(["a", "b"], {"a": 3})
    assert missing["status"] == "incomplete" and missing["ndcg_at_5"] is None
    assert missing["unjudged_ids"] == ["b"]
    zero = ranking_metrics(["a"], {"a": 0})
    assert zero["idcg_zero"] and zero["ndcg_at_5"] is None
    with pytest.raises(EvaluationError):
        ranking_metrics(["a", "a"], {"a": 3})


def test_paired_summary_uses_same_profiles_for_both_means():
    rows = [
        {"profile_id": "paired", "methods": {"B1": {"status": "complete", "ndcg_at_5": .2}, "P": {"status": "complete", "ndcg_at_5": .8}}},
        {"profile_id": "excluded", "methods": {"B1": {"status": "complete", "ndcg_at_5": 1}, "P": {"status": "unavailable"}}},
    ]
    result = paired_summary(rows, "ndcg_at_5")
    assert result["included_profile_ids"] == ["paired"] and result["paired_count"] == 1
    assert result["B1_mean"] == .2 and result["P_mean"] == .8
    assert result["absolute_effect"] == pytest.approx(.6)
    assert result["bootstrap_ci95"] == pytest.approx([.6, .6])
    assert result["excluded"][0]["profile_id"] == "excluded"


def test_slot_metrics_count_false_as_value_and_keep_money_out():
    gold = {"intent": "find_room", "city": "TP.HCM", "area": None, "people": 2,
            "preferences": ["quiet"], "needs_destination": False}
    predicted = {**gold, "people": 1, "preferences": ["quiet", "window"], "budget_hint_vnd": 9_000_000}
    result = extraction_metrics([{"profile_id": "p", "gold": gold, "predicted": predicted}])
    assert result["per_field"]["needs_destination"]["tp"] == 1
    assert result["per_field"]["people"]["fp"] == result["per_field"]["people"]["fn"] == 1
    assert "budget_hint_vnd" not in result["field_mapping"]
    assert result["intent_accuracy"] == 1


def test_synthetic_dataset_is_deterministic_valid_and_grouped(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    a, b = generate(first), generate(second)
    assert a == b
    report = validate_dataset(first)
    assert report["canonical_rooms"] == 220 and report["profiles"] == {"dev": 15, "test": 30}
    assert report["cities"] == {"TP.HCM": 120, "Hà Nội": 100}
    assert set(report["room_types"]) == {"room", "studio", "apartment"}
    assert report["synthetic_ratio"] == 1 and not report["frozen"]
    split = read_json(first / "profiles/split_manifest.json")
    assert not set(split["profile_ids"]["dev"]) & set(split["profile_ids"]["test"])
    (first / "catalog/rooms.json").write_text("{}")
    with pytest.raises(EvaluationError, match="hash mismatch"):
        validate_dataset(first)


def test_independent_oracles_include_unknown_rounding_and_boundary(tmp_path):
    dataset = tmp_path / "data"
    generate(dataset)
    report = oracle_report(dataset, tmp_path / "oracle.json")
    assert report["case_count"] == report["passed"] == 22 and report["failed"] == 0
    loan = next(row for row in report["cases"] if row["case_id"] == "L01-worked-example")
    assert loan["actual"]["affordability"]["loan"]["installment_vnd"] == 949_016
    unknown = next(row for row in report["cases"] if row["case_id"] == "C06-unknown-water")
    assert unknown["actual"]["monthly_total_vnd"] is None
    boundary = report["cases"][0]["budget_checks"]
    assert [row["actual_pass"] for row in boundary] == [True, False, True, False]


def test_dev_ranking_has_blank_blind_labels_and_no_fake_p(tmp_path):
    dataset, runs = tmp_path / "data", tmp_path / "runs"
    generate(dataset)
    manifest = ranking_run(dataset, "dev", runs)
    assert manifest["model_calls"] == 0 and manifest["semantic_provider"] == "unavailable"
    assert manifest["method_status_counts"]["P"]["unavailable"] > 0
    packets = read_json(runs / "blind_packets.json")["packets"]
    assert len(packets) == 15
    assert all("score" not in item and "algorithm" not in item for packet in packets for item in packet["candidates"])
    summary = evaluate_rankings(dataset, runs, None)
    assert summary["quality_metrics"] is None and summary["status"] == "pending_human_judgments"


def test_test_split_and_freeze_require_explicit_gate(tmp_path):
    dataset = tmp_path / "data"
    generate(dataset)
    with pytest.raises(EvaluationError, match="frozen"):
        ranking_run(dataset, "test", tmp_path / "runs")
    with pytest.raises(EvaluationError, match="ack-g4"):
        freeze_inputs(dataset, tmp_path / "config.json")


def test_frozen_semantic_config_rejects_changed_model_before_provider_call(tmp_path):
    dataset = tmp_path / "data"
    generate(dataset)
    frozen = freeze_inputs(dataset, ROOT / "eval/config/protocol.json", ack_g4=True)
    assert frozen["frozen"] and frozen["labels_status"] == "pending_human_judgments"
    catalog = Catalog(dataset / "catalog/rooms.json")
    catalog.alpha = .3
    catalog.semantic_scorer = SimpleNamespace(provider=SimpleNamespace(model="different-fixture-model", dimensions=1536))
    with pytest.raises(EvaluationError, match="differ from frozen protocol"):
        ranking_run(dataset, "test", tmp_path / "runs", semantic_catalog=catalog)
