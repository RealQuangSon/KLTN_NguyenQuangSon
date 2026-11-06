"""HN-08: runner kịch bản agent và suite clarify — offline, không gọi mạng."""
import json
from pathlib import Path

import pytest

from eval.agent_eval import run_agent_scenarios, run_clarify_suite
from eval.common import EvaluationError, ROOT


def test_scenario_file_has_at_least_40_multi_turn_scenarios():
    payload = json.loads((ROOT / "eval/scenarios/agent_e2e.json").read_text(encoding="utf-8"))
    assert len(payload["scenarios"]) >= 40
    cities = {scenario.get("city") for scenario in payload["scenarios"]}
    assert {"Hà Nội", "TP.HCM"} <= cities
    for scenario in payload["scenarios"]:
        assert scenario["turns"], scenario["id"]
        for turn in scenario["turns"]:
            assert turn["user"].strip()
            assert "monthly_income" in turn.get("must_not_contain", ["monthly_income"])


def test_demo_run_scores_all_scenarios(tmp_path):
    report = run_agent_scenarios(output=tmp_path / "agent.json")
    assert report["mode"] == "demo"
    assert report["scenario_count"] >= 40
    assert report["completion_rate"] == 1.0, [
        (row["id"], [t["problems"] for t in row["turns"] if t["problems"]], row["final_problems"])
        for row in report["results"] if not row["passed"]]
    assert report["p50_ms"] is not None and report["p95_ms"] is not None
    assert report["cost_usd"] is None  # demo không có chi phí thật
    assert (tmp_path / "agent.json").exists()


def test_live_mode_refuses_without_explicit_budget():
    with pytest.raises(EvaluationError) as error:
        run_agent_scenarios(mode="live")
    assert "allow-live" in str(error.value) and "Ước tính" in str(error.value)


def test_clarify_suite_reports_calibration_against_gold(tmp_path):
    report = run_clarify_suite(output=tmp_path / "clarify.json")
    assert report["case_count"] >= 40
    # Nhãn là của tác giả: precision phải tuyệt đối (không hỏi sai), recall/accuracy
    # báo cáo trung thực — các ca còn thiếu là giới hạn kho (sân bay/KCN không có
    # căn, kho không bảng phí) đã ghi trong review HN-08.
    assert report["precision"] == 1.0
    assert report["recall"] is not None and report["top1_accuracy"] == 1.0
    assert set(report["decided_by"]) <= {"rules", "none", "auto", "jev"}
    assert (tmp_path / "clarify.json").exists()


def test_clarify_suite_explains_known_catalog_gaps(tmp_path):
    report = run_clarify_suite(output=None)
    misses = {row["case_id"] for row in report["results"] if not row["correct"]}
    # CL08/09 (sân bay/KCN không có căn trong kho synthetic) và CL15-20 (kho
    # không bảng phí nên total/rent trùng nhau) là giới hạn dữ liệu đã biết.
    assert {"CL08", "CL09", "CL15", "CL16"} <= misses
    asked = [row for row in report["results"] if row["asked"]]
    assert asked and all(row["decided_by"] == "rules" for row in asked)
