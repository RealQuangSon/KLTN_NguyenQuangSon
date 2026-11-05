"""DA-05: blind label sheets, label aggregation, survey aggregation.

All fixtures are synthetic and live in tmp_path; nothing is written to the
git-ignored eval/labels/ directory from tests and no fake labels are committed.
"""
import csv

import pytest

from data.generate import generate
from eval.common import EvaluationError, read_jsonl
from eval.labeling import cohens_kappa, label_report, label_sheet, survey_report
from eval.pipeline import ranking_run


def _write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_label_sheet_shuffles_and_hides_method(tmp_path):
    dataset, runs, labels = tmp_path / "data", tmp_path / "runs", tmp_path / "labels"
    generate(dataset)
    ranking_run(dataset, "dev", runs)
    result = label_sheet(dataset, "dev", "B1", runs, labels)
    rankings = read_jsonl(runs / "rankings.jsonl")
    expected_rows = sum(len(row["methods"]["B1"]["items"][:5]) for row in rankings)
    assert 0 < result["rows"] == expected_rows <= 75  # top-5 per dev profile, sparse eligible sets allowed
    sheet_text = (labels / "sheet-goi-m.csv").read_text(encoding="utf-8")
    assert "B1" not in sheet_text and "P," not in sheet_text
    assert "need" in sheet_text and "label" in sheet_text
    key_rows = list(csv.DictReader((labels / "sheet-goi-m.key.csv").open(encoding="utf-8")))
    assert {row["method"] for row in key_rows} == {"B1"}
    assert {row["rank"] for row in key_rows} == {"1", "2", "3", "4", "5"}
    # Renter money fields stay out of the blinded need description.
    assert "max_monthly_cost_vnd" not in sheet_text and "monthly_income" not in sheet_text
    with pytest.raises(EvaluationError, match="split"):
        label_sheet(dataset, "test", "B1", runs, labels)


def test_label_report_metrics_and_kappa_on_synthetic_sheets(tmp_path):
    labels, output = tmp_path / "labels", tmp_path / "label_report.json"
    labels.mkdir()
    pairs = [(f"p1", f"r{index}") for index in range(1, 6)]
    _write_csv(labels / "sheet-goi-m.key.csv", ["profile_id", "room_id", "rank", "method"],
               [{"profile_id": "p1", "room_id": room, "rank": str(rank), "method": "B1"}
                for rank, room in enumerate((room for _, room in pairs), 1)])
    _write_csv(labels / "sheet-goi-m.csv", ["profile_id", "room_id", "need", "room_info",
                                            "label", "annotator", "note"],
               [{"profile_id": "p1", "room_id": room, "need": "n", "room_info": "r",
                 "label": "", "annotator": "", "note": ""} for _, room in pairs])
    # Two human annotators on the same blind sheet: fixed labels only for the check.
    _write_csv(labels / "sheet-goi-m-ann-a.csv", ["profile_id", "room_id", "label", "annotator"],
               [{"profile_id": "p1", "room_id": room, "label": "3", "annotator": "ann-a"}
                for _, room in pairs])
    _write_csv(labels / "sheet-goi-m-ann-b.csv", ["profile_id", "room_id", "label", "annotator"],
               [{"profile_id": "p1", "room_id": room, "label": label, "annotator": "ann-b"}
                for (_, room), label in zip(pairs, ("0", "3", "0", "0", "0"))])
    report = label_report(labels, output)
    method = report["methods"]["B1"]
    assert method["annotators"]["ann-a"]["ndcg_at_5"] == 1.0
    assert method["annotators"]["ann-a"]["precision_at_5"] == 1.0
    assert method["annotators"]["ann-b"]["precision_at_5"] == 0.2
    # ann-b: single graded-relevant item at rank 2 → nDCG = 7/log2(3) / 7.
    assert method["annotators"]["ann-b"]["ndcg_at_5"] == pytest.approx(1 / 1.5849625007211562)
    assert method["ndcg_at_5_mean"] == pytest.approx((1.0 + 1 / 1.5849625007211562) / 2)
    agreement = report["agreement"]
    assert agreement["status"] == "ok"
    row = agreement["pairwise"][0]
    assert row["shared_pairs"] == 5 and row["agreement_rate"] == pytest.approx(0.2)
    assert row["cohens_kappa"] == pytest.approx(0.0)
    assert output.is_file()


def test_cohens_kappa_matches_hand_calculation():
    assert cohens_kappa([3, 3, 3, 3, 3], [3, 0, 0, 0, 0]) == pytest.approx(0.0)
    assert cohens_kappa([1, 2, 3], [1, 2, 3]) == 1.0
    # Disjoint categories: po = 0 and pe = 0 → kappa 0, not undefined.
    assert cohens_kappa([0, 0], [1, 1]) == 0.0
    # pe = 1 (both raters use one constant category) leaves kappa undefined.
    assert cohens_kappa([2, 2], [2, 2]) is None
    assert cohens_kappa([], []) is None


def test_label_report_requires_paired_key(tmp_path):
    labels = tmp_path / "labels"
    labels.mkdir()
    _write_csv(labels / "sheet-orphan.csv", ["profile_id", "room_id", "label", "annotator"],
               [{"profile_id": "p", "room_id": "r", "label": "3", "annotator": "a"}])
    with pytest.raises(EvaluationError, match="key"):
        label_report(labels, tmp_path / "out.json")


def test_survey_report_scores_short_sus_and_spread(tmp_path):
    csv_path, output = tmp_path / "survey.csv", tmp_path / "survey.json"
    fields = ["respondent_id", "sus1", "sus2", "sus3", "sus4", "sus5", "sus6",
              "trust_explanation", "satisfaction_suggestions", "privacy_financial"]
    rows = [{"respondent_id": "S01", "sus1": "5", "sus2": "1", "sus3": "5", "sus4": "1",
             "sus5": "5", "sus6": "1", "trust_explanation": "4",
             "satisfaction_suggestions": "5", "privacy_financial": "5"},
            {"respondent_id": "S02", "sus1": "4", "sus2": "2", "sus3": "4", "sus4": "2",
             "sus5": "4", "sus6": "2", "trust_explanation": "2",
             "satisfaction_suggestions": "3", "privacy_financial": "4"}]
    _write_csv(csv_path, fields, rows)
    report = survey_report(csv_path, output)
    # S01: adjusted all 4 → SUS 60; S02: adjusted all 3 → SUS 45.
    assert report["sus_score"]["mean"] == 52.5 and report["sus_score"]["n"] == 2
    assert report["sus_score"]["stdev"] == pytest.approx(10.61, abs=0.01)
    assert report["per_question"]["trust_explanation"]["mean"] == 3.0
    assert report["per_question"]["trust_explanation"]["stdev"] == pytest.approx(1.4142, abs=1e-3)
    assert report["respondents"] == 2
