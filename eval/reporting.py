"""Development evidence report assembly (EV-08).

Builds a deterministic markdown report and a CSV evidence index; every table row
traces back to a hashed artifact. Development output is exploratory, never
research results: human relevance labels and live GPT/P runs remain pending.
"""
from __future__ import annotations

import csv
from pathlib import Path
from statistics import median

from .common import (EvaluationError, read_json, read_jsonl, sha256_file, validate_dataset, write_json)

REQUIRED = ("oracle.json", "extraction.json", "rankings.jsonl", "run_manifest.json",
            "evaluation_summary.json", "invariants.json", "grounding.json", "measurements.json")


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(_fmt(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def development_report(data_dir: Path, run_dir: Path, split: str = "dev") -> dict:
    missing = [name for name in REQUIRED if not (run_dir / name).is_file()]
    if missing:
        raise EvaluationError(f"Missing run artifacts; run the suites first: {', '.join(missing)}")
    dataset = validate_dataset(data_dir)
    oracle = read_json(run_dir / "oracle.json")
    extraction = read_json(run_dir / "extraction.json")
    rankings = read_jsonl(run_dir / "rankings.jsonl")
    run = read_json(run_dir / "run_manifest.json")
    if sha256_file(run_dir / "rankings.jsonl") != run["rankings_hash"]:
        raise EvaluationError("Rankings hash mismatch")
    metrics = read_json(run_dir / "evaluation_summary.json")
    invariants = read_json(run_dir / "invariants.json")
    grounding = read_json(run_dir / "grounding.json")
    measurements = read_json(run_dir / "measurements.json")

    sections = [_dataset_section(dataset), _oracle_section(oracle), _extraction_section(extraction),
                _ranking_section(rankings, run), _metrics_section(metrics),
                _invariants_section(invariants), _grounding_section(grounding),
                _measurement_section(measurements), _limits_section(run)]
    report = "\n\n".join([_header(run, split)] + sections) + "\n"
    (run_dir / "report.md").write_text(report, encoding="utf-8")

    artifacts = [(name, sha256_file(run_dir / name)) for name in REQUIRED]
    annotations = run_dir / "annotation_status.json"
    if annotations.is_file():
        artifacts.append(("annotation_status.json", sha256_file(annotations)))
    with (run_dir / "evidence_index.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["artifact", "sha256", "kind"])
        writer.writerows([name, digest, _artifact_kind(name)] for name, digest in artifacts)
    summary = {"kind": "development_evidence_report", "stage": run["stage"], "split": split,
               "report_path": str((run_dir / "report.md").resolve()),
               "evidence_index_path": str((run_dir / "evidence_index.csv").resolve()),
               "artifact_count": len(artifacts),
               "labels_status": metrics.get("status", "pending_human_judgments"),
               "notice": "Exploratory development evidence; research metrics require freeze, "
                         "blind human labels and both B1/P available."}
    write_json(run_dir / "report_summary.json", summary)
    return summary


def _header(run: dict, split: str) -> str:
    return (f"# Bằng chứng đánh giá phát triển HomeMatch — split `{split}`\n\n"
            f"Stage: `{run['stage']}` · rankings hash: `{run['rankings_hash'][:16]}…` · "
            f"catalog hash: `{run['catalog_hash'][:16]}…`\n\n"
            "Mọi bảng dưới đây truy được về artifact trong `evidence_index.csv`. "
            "Đây là kết quả phát triển/khám phá, **không phải kết quả nghiên cứu**: nhãn relevance "
            "người chấm và phép đo GPT/P thật còn thiếu.")


def _dataset_section(dataset: dict) -> str:
    rows = [["Phòng canonical", dataset["canonical_rooms"]],
            ["Hồ sơ dev/test", f"{dataset['profiles']['dev']}/{dataset['profiles']['test']}"],
            ["Câu phát biểu gold", dataset["utterances"]],
            ["Capacity chưa biết", dataset["unknown_capacity"]],
            ["Availability chưa biết", dataset["unknown_availability"]],
            ["Phí theo đơn giá chưa biết", dataset["unknown_fee_rates"]],
            ["Tiện ích chưa biết", dataset["unknown_amenities"]],
            ["Độ chính xác vị trí", ", ".join(f"{k}: {v}" for k, v in sorted(dataset["location_precision"].items()))],
            ["Tỷ lệ synthetic", dataset["synthetic_ratio"]]]
    return "## Dữ liệu\n\n" + _table(["Đặc tính", "Giá trị"], rows)


def _oracle_section(oracle: dict) -> str:
    rows = [[case["case_id"], "đạt" if case["passed"] else "lệch",
             case["actual"]["monthly_total_vnd"], case["actual"]["initial_total_vnd"],
             ", ".join(case["actual"]["missing_monthly"] + case["actual"]["missing_initial"]) or "—"]
            for case in oracle["cases"]]
    return (f"## Oracle tài chính ({oracle['passed']}/{oracle['case_count']} đạt)\n\n"
            + _table(["Ca", "Kết quả", "Tổng tháng (VND)", "Tiền ban đầu (VND)", "Thiếu"], rows))


def _extraction_section(extraction: dict) -> str:
    metrics = extraction["metrics"]
    rows = [[field, values["tp"], values["fp"], values["fn"], values["f1"]]
            for field, values in metrics["per_field"].items()]
    return (f"## Trích xuất nhu cầu (mode `{extraction['mode']}`)\n\n"
            f"Micro-F1: **{_fmt(metrics['micro_f1'])}** · Intent accuracy: **{_fmt(metrics['intent_accuracy'])}** · "
            f"lỗi/tổng câu: {metrics['failure_count']}/{metrics['utterance_count']}\n\n"
            + _table(["Trường", "TP", "FP", "FN", "F1"], rows)
            + "\n\nTiền nhắc trong chat chỉ là hint cục bộ, không nằm trong F1 model.")


def _ranking_section(rankings: list[dict], run: dict) -> str:
    counts = run["method_status_counts"]
    eligible = [row["eligible_count"] for row in rankings]
    rows = [[method, counts[method].get("successful", 0), counts[method].get("no_match", 0),
             counts[method].get("needs_verification", 0), counts[method].get("unavailable", 0)]
            for method in ("B1", "P")]
    return ("## Xếp hạng trên tập eligible đầy đủ\n\n"
            f"Elite set/profile: min {min(eligible)}, median {median(eligible)}, max {max(eligible)}\n\n"
            + _table(["Phương pháp", "successful", "no_match", "needs_verification", "unavailable"], rows)
            + f"\n\nProvider semantic: `{run['semantic_provider']}`; P offline ghi `unavailable`, "
              "không tự thay bằng B1.")


def _metrics_section(metrics: dict) -> str:
    rows = [["Trạng thái nhãn", metrics.get("status")],
            ["Chỉ số chất lượng", "chưa tính" if metrics.get("quality_metrics") is None else "đã có"]]
    return "## Chỉ số relevance\n\n" + _table(["Mục", "Giá trị"], rows) + \
        "\n\nNhãn người chấm còn trống; đầu ra máy không tự thành gold."


def _invariants_section(invariants: dict) -> str:
    rows = [["Hồ sơ kiểm tra", invariants["profile_count"]],
            ["Ứng viên eligible đã kiểm", invariants["eligible_candidate_checks"]],
            ["Vi phạm", invariants["failed"]],
            ["Phản thực tế hoa hồng giữ rank", "đạt" if invariants["counterfactual"]["invariant_holds"] else "lệch"],
            ["Đối chứng available=false loại phòng", _fmt(invariants["availability_flip_enforced"])]]
    return (f"## Bất biến điều kiện cứng ({'đạt' if invariants['passed'] else 'lệch'})\n\n"
            + _table(["Kiểm tra", "Kết quả"], rows))


def _grounding_section(grounding: dict) -> str:
    rows = [[claim, count, grounding["unsupported"].get(claim, 0)]
            for claim, count in sorted(grounding["claim_counts"].items())]
    return (f"## Grounding lời giải thích ({'đạt' if grounding['passed'] else 'lệch'})\n\n"
            f"Items kiểm tra: {grounding['items_checked']} · claims: {grounding['total_claims']} · "
            f"không hỗ trợ: {grounding['failed']}\n\n"
            + _table(["Loại claim", "Số lượng", "Không hỗ trợ"], rows))


def _measurement_section(measurements: dict) -> str:
    rows = [[phase, values["samples"], values["p50"], values["p95"], values["model_calls"]]
            for phase, values in measurements["phases"].items()]
    return ("## Đo máy (ms, offline)\n\n"
            + _table(["Pha", "Số mẫu", "p50", "p95", "Model calls"], rows)
            + f"\n\nTổng logical model calls: {measurements['total_logical_model_calls']} · "
              f"thời gian chờ duyệt: `{measurements['review_waiting_time']}`. "
              "Không suy ra latency provider thật từ các số này.")


def _limits_section(run: dict) -> str:
    return ("## Giới hạn bằng chứng\n\n"
            "- Dữ liệu 80 phòng/30 hồ sơ hoàn toàn tổng hợp, một thành phố; không đại diện thị trường.\n"
            "- Nhãn relevance độc lập chưa có; mọi chỉ số ranking đang `pending_human_judgments`.\n"
            "- P cần vector thật (PostgreSQL + embedding live); bản offline ghi `unavailable`, "
            "fallback cấu trúc không được tính là P.\n"
            "- Chưa chạy GPT-4o/embedding thật; F1 extraction ở đây là của rule demo.\n"
            "- Latency đo trên một process local, không phải tải production.\n"
            "- Đúng thứ tự nghiên cứu: freeze → pool → nhãn blind → khóa hash nhãn → metric; "
            "xem `eval/REPRODUCE.md`.")


def _artifact_kind(name: str) -> str:
    return {"oracle.json": "finance_oracle", "extraction.json": "extraction_component",
            "rankings.jsonl": "ranking_run", "run_manifest.json": "run_manifest",
            "evaluation_summary.json": "metrics_summary", "invariants.json": "hard_constraint_invariants",
            "grounding.json": "explanation_grounding", "measurements.json": "machine_measurement",
            "annotation_status.json": "blind_annotation_status"}.get(name, "other")
