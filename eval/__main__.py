"""Command-line entry point; offline by default, research outputs require freeze/labels."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .common import DEFAULT_DATA, ROOT, EvaluationError, validate_dataset
from .intents import intents_report
from .invoices import invoice_oracle_report
from .labeling import label_report, label_sheet, survey_report
from .measurement import measurement_report
from .pipeline import evaluate_rankings, extraction_report, freeze_inputs, oracle_report, ranking_run
from .reporting import development_report
from .suites import grounding_report, invariants_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    oracle = sub.add_parser("oracle")
    oracle.add_argument("--output", type=Path, default=ROOT / "eval/runs/development/oracle.json")
    extraction = sub.add_parser("extraction")
    extraction.add_argument("--split", choices=("dev", "test"), default="dev")
    extraction.add_argument("--output", type=Path, default=ROOT / "eval/runs/development/extraction.json")
    extraction.add_argument("--live", action="store_true")
    extraction.add_argument("--allow-live", action="store_true")
    extraction.add_argument("--api-budget-vnd", type=int)
    ranking = sub.add_parser("ranking")
    ranking.add_argument("--split", choices=("dev", "test"), default="dev")
    ranking.add_argument("--run-dir", type=Path, default=ROOT / "eval/runs/development")
    ranking.add_argument("--live-semantic", action="store_true")
    ranking.add_argument("--allow-live", action="store_true")
    ranking.add_argument("--api-budget-vnd", type=int)
    metrics = sub.add_parser("metrics")
    metrics.add_argument("--run-dir", type=Path, default=ROOT / "eval/runs/development")
    metrics.add_argument("--judgments", type=Path)
    metrics.add_argument("--human-declared", action="store_true")
    metrics.add_argument("--allow-development", action="store_true")
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--config", type=Path, default=ROOT / "eval/config/protocol.json")
    freeze.add_argument("--ack-g4", action="store_true")
    invariants = sub.add_parser("invariants")
    invariants.add_argument("--split", choices=("dev", "test"), default="dev")
    invariants.add_argument("--output", type=Path, default=ROOT / "eval/runs/development/invariants.json")
    intents = sub.add_parser("intents")
    intents.add_argument("--split", choices=("dev", "test"), default="dev")
    intents.add_argument("--output", type=Path, default=ROOT / "eval/runs/development/intents.json")
    invoices = sub.add_parser("invoices")
    invoices.add_argument("--output", type=Path, default=ROOT / "eval/runs/development/invoices.json")
    grounding = sub.add_parser("grounding")
    grounding.add_argument("--run-dir", type=Path, default=ROOT / "eval/runs/development")
    grounding.add_argument("--output", type=Path, default=ROOT / "eval/runs/development/grounding.json")
    measure = sub.add_parser("measure")
    measure.add_argument("--run-dir", type=Path, default=ROOT / "eval/runs/development")
    measure.add_argument("--output", type=Path, default=ROOT / "eval/runs/development/measurements.json")
    report = sub.add_parser("report")
    report.add_argument("--run-dir", type=Path, default=ROOT / "eval/runs/development")
    sheet = sub.add_parser("label-sheet")
    sheet.add_argument("--split", choices=("dev", "test"), default="test")
    sheet.add_argument("--method", choices=("B1", "P"), required=True)
    sheet.add_argument("--run-dir", type=Path, default=ROOT / "eval/runs/development")
    sheet.add_argument("--labels-dir", type=Path, default=ROOT / "eval/labels")
    labeling = sub.add_parser("label-report")
    labeling.add_argument("--labels-dir", type=Path, default=ROOT / "eval/labels")
    labeling.add_argument("--output", type=Path, default=ROOT / "eval/runs/development/label_report.json")
    survey = sub.add_parser("survey-report")
    survey.add_argument("--csv", type=Path, required=True)
    survey.add_argument("--output", type=Path, default=ROOT / "eval/runs/development/survey_report.json")
    args = parser.parse_args()
    try:
        if args.command == "validate":
            report = validate_dataset(args.data_dir)
        elif args.command == "oracle":
            report = oracle_report(args.data_dir, args.output)
        elif args.command == "extraction":
            report = extraction_report(args.data_dir, args.split, args.output, args.live,
                                       args.allow_live, args.api_budget_vnd)
        elif args.command == "ranking":
            if not args.live_semantic:
                report = ranking_run(args.data_dir, args.split, args.run_dir)
            else:
                if not args.allow_live or not args.api_budget_vnd or args.api_budget_vnd <= 0:
                    raise EvaluationError("Live P requires --allow-live and a declared positive --api-budget-vnd")
                dsn = os.getenv("HOMEMATCH_DATABASE_URL", "")
                if not dsn.startswith(("postgresql://", "postgres://")) or not os.getenv("OPENAI_API_KEY"):
                    raise EvaluationError("Live P requires a matching PostgreSQL catalog, configured API key and prebuilt vectors")
                from backend.app.service import HomeMatchService
                os.environ["HOMEMATCH_EMBEDDING_MODE"] = "openai"
                os.environ["HOMEMATCH_LLM_MODE"] = "demo"
                service = HomeMatchService(dsn)
                try:
                    report = ranking_run(args.data_dir, args.split, args.run_dir, service.catalog)
                finally:
                    service.close()
                report["declared_api_budget_vnd"] = args.api_budget_vnd
                report["budget_policy"] = "declaration_only_not_an_enforced_spend_limit"
        elif args.command == "metrics":
            report = evaluate_rankings(args.data_dir, args.run_dir, args.judgments,
                                        args.human_declared, args.allow_development)
        elif args.command == "invariants":
            report = invariants_report(args.data_dir, args.split, args.output)
        elif args.command == "intents":
            report = intents_report(args.data_dir, args.split, args.output)
        elif args.command == "invoices":
            report = invoice_oracle_report(args.data_dir, args.output)
        elif args.command == "grounding":
            report = grounding_report(args.data_dir, args.run_dir, args.output)
        elif args.command == "measure":
            report = measurement_report(args.run_dir, args.output)
        elif args.command == "report":
            report = development_report(args.data_dir, args.run_dir)
        elif args.command == "label-sheet":
            report = label_sheet(args.data_dir, args.split, args.method, args.run_dir, args.labels_dir)
        elif args.command == "label-report":
            report = label_report(args.labels_dir, args.output)
        elif args.command == "survey-report":
            report = survey_report(args.csv, args.output)
        else:
            report = freeze_inputs(args.data_dir, args.config, args.ack_g4)
    except (EvaluationError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"Evaluation stopped: {exc}", file=sys.stderr)
        return 2
    summary = {key: value for key, value in report.items() if key not in ("cases", "rows", "artifacts", "code_hashes")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if report.get("failed", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
