import pytest

from data.generate import generate
from backend.app.catalog import Catalog
from backend.app.models import Candidate
from eval.common import EvaluationError, read_json, read_jsonl, sha256_file, write_json, write_jsonl
from eval.measurement import measurement_report, percentile
from eval.pipeline import extraction_report, oracle_report, ranking_run
from eval.reporting import development_report
from eval.suites import grounding_report, invariants_report


def test_percentile_is_nearest_rank_and_hand_calculated():
    assert percentile([1, 2, 3, 4], 0.5) == 2
    assert percentile(list(range(1, 101)), 0.95) == 95
    assert percentile([7], 0.95) == 7
    with pytest.raises(EvaluationError):
        percentile([], 0.5)


def test_invariants_pass_on_generated_dataset(tmp_path):
    dataset, runs = tmp_path / "data", tmp_path / "runs"
    generate(dataset)
    report = invariants_report(dataset, "dev", runs / "invariants.json")
    assert report["passed"] and report["failed"] == 0
    assert report["profile_count"] == 15 and report["eligible_candidate_checks"] > 0
    assert report["counterfactual"]["invariant_holds"]
    assert report["availability_flip_enforced"] is True
    assert report["violations"] == {}


def test_invariants_detect_leaky_eligible_set(tmp_path):
    dataset, runs = tmp_path / "data", tmp_path / "runs"
    generate(dataset)

    class LeakyCatalog(Catalog):
        def eligible_candidates(self, profile):
            candidates, diagnostics = super().eligible_candidates(profile)
            if candidates:
                room = next(item for item in self.rooms() if not item.published)
                payload = candidates[0].model_dump()
                payload.update(room_id=room.id, room_revision=room.revision)
                candidates.append(Candidate.model_validate(payload))
            return candidates, diagnostics

    report = invariants_report(dataset, "dev", runs / "invariants.json", catalog=LeakyCatalog(dataset / "catalog/rooms.json"))
    assert not report["passed"]
    assert report["violations"]["published"] >= 1
    assert any(row["violations"] for row in report["rows"])


def test_grounding_supports_template_claims_and_flags_tampered_amount(tmp_path):
    dataset, runs = tmp_path / "data", tmp_path / "runs"
    generate(dataset)
    ranking_run(dataset, "dev", runs)
    clean = grounding_report(dataset, runs, runs / "grounding.json")
    assert clean["passed"] and clean["failed"] == 0
    assert clean["claim_counts"]["monthly_total"] == clean["items_checked"]
    assert clean["claim_counts"]["preference_satisfied"] + clean["claim_counts"]["preference_missing"] > 0

    rows = read_jsonl(runs / "rankings.jsonl")
    item = next(value["items"][0] for row in rows for value in row["methods"].values() if value["items"])
    amount = item["cost"]["monthly_total_vnd"]
    item["reasons"][0] = f"Tổng tháng {amount + 1:,} VND trong kịch bản đã xác nhận."
    write_jsonl(runs / "rankings.jsonl", rows)
    manifest = read_json(runs / "run_manifest.json")
    manifest["rankings_hash"] = sha256_file(runs / "rankings.jsonl")
    write_json(runs / "run_manifest.json", manifest)
    tampered = grounding_report(dataset, runs, runs / "grounding.json")
    assert not tampered["passed"] and tampered["unsupported"]["monthly_total"] >= 1


def test_grounding_rejects_hash_mismatch(tmp_path):
    dataset, runs = tmp_path / "data", tmp_path / "runs"
    generate(dataset)
    ranking_run(dataset, "dev", runs)
    (runs / "rankings.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(EvaluationError, match="hash mismatch"):
        grounding_report(dataset, runs, runs / "grounding.json")


def test_measurement_aggregates_offline_runs_with_zero_model_calls(tmp_path):
    dataset, runs = tmp_path / "data", tmp_path / "runs"
    generate(dataset)
    oracle_report(dataset, runs / "oracle.json")
    extraction_report(dataset, "dev", runs / "extraction.json")
    ranking_run(dataset, "dev", runs)
    report = measurement_report(runs, runs / "measurements.json")
    assert report["total_logical_model_calls"] == 0 and report["live_measurements"] is False
    for phase in ("extraction", "ranking_B1", "ranking_P", "finance_oracle"):
        values = report["phases"][phase]
        assert values["samples"] > 0 and values["p95"] >= values["p50"] >= 0
    b1, p = report["phases"]["ranking_B1"]["statuses"], report["phases"]["ranking_P"]["statuses"]
    assert sum(b1.values()) == 15 and b1["successful"] >= 12
    # Without vectors P is reported unavailable wherever B1 had candidates, never relabelled as P.
    assert p["unavailable"] == b1["successful"] and p.get("successful", 0) == 0


def test_development_report_tables_and_evidence_index(tmp_path):
    dataset, runs = tmp_path / "data", tmp_path / "runs"
    generate(dataset)
    oracle_report(dataset, runs / "oracle.json")
    extraction_report(dataset, "dev", runs / "extraction.json")
    ranking_run(dataset, "dev", runs)
    invariants_report(dataset, "dev", runs / "invariants.json")
    grounding_report(dataset, runs, runs / "grounding.json")
    measurement_report(runs, runs / "measurements.json")
    with pytest.raises(EvaluationError, match="Missing run artifacts"):
        development_report(dataset, runs)
    from eval.pipeline import evaluate_rankings
    evaluate_rankings(dataset, runs, None)
    summary = development_report(dataset, runs)
    assert summary["labels_status"] == "pending_human_judgments" and summary["artifact_count"] == 9
    markdown = (runs / "report.md").read_text(encoding="utf-8")
    assert "pending_human_judgments" in markdown or "chưa tính" in markdown
    for section in ("## Dữ liệu", "## Oracle tài chính", "## Trích xuất nhu cầu", "## Xếp hạng",
                    "## Bất biến điều kiện cứng", "## Grounding lời giải thích", "## Đo máy",
                    "## Giới hạn bằng chứng"):
        assert section in markdown
    index = [line.split(",") for line in (runs / "evidence_index.csv").read_text(encoding="utf-8").splitlines()[1:]]
    assert len(index) == summary["artifact_count"]
    for name, digest in (row[:2] for row in index):
        assert sha256_file(runs / name) == digest


def test_cli_report_command_dispatches_and_exits_zero(tmp_path, monkeypatch, capsys):
    dataset, runs = tmp_path / "data", tmp_path / "runs"
    generate(dataset)
    oracle_report(dataset, runs / "oracle.json")
    extraction_report(dataset, "dev", runs / "extraction.json")
    ranking_run(dataset, "dev", runs)
    invariants_report(dataset, "dev", runs / "invariants.json")
    grounding_report(dataset, runs, runs / "grounding.json")
    measurement_report(runs, runs / "measurements.json")
    from eval.__main__ import main
    from eval.pipeline import evaluate_rankings
    evaluate_rankings(dataset, runs, None)
    monkeypatch.setattr("sys.argv", ["eval", "--data-dir", str(dataset), "report", "--run-dir", str(runs)])
    assert main() == 0
    assert "development_evidence_report" in capsys.readouterr().out
