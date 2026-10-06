from __future__ import annotations

import csv
import html
import inspect
import json
import random
import statistics
import time
from pathlib import Path

from backend.app.catalog import Catalog
from backend.app.costs import estimate_cost
from backend.app.interpreter import DemoInterpreter, OpenAIInterpreter, budget_hint, redact
from backend.app.models import CostRequest, DomainError

from .common import (ROOT, EvaluationError, confirmed_profile, content_hash, dataset_manifest,
                     load_profiles, read_json, read_jsonl, sha256_file, write_json, write_jsonl)
from .metrics import extraction_metrics, paired_summary, ranking_metrics


def code_hashes() -> dict[str, str]:
    paths = [ROOT / "requirements.txt", ROOT / "requirements.lock", ROOT / "data/generate.py", ROOT / "eval/config/protocol.json"]
    paths += sorted((ROOT / "backend/app").rglob("*.py"))
    paths += sorted((ROOT / "eval").glob("*.py"))
    return {str(path.relative_to(ROOT)): sha256_file(path) for path in paths if path.is_file()}


def verify_code(manifest: dict) -> None:
    for name, expected in manifest.get("code_hashes", {}).items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or sha256_file(path) != expected:
            raise EvaluationError(f"Frozen code/config mismatch: {name}")


def require_split_ready(data_dir: Path, split: str) -> dict:
    manifest = dataset_manifest(data_dir)
    if split == "test" and not manifest.get("frozen"):
        raise EvaluationError("Test quality/output run requires frozen input manifest; use development split first")
    if manifest.get("frozen"):
        verify_code(manifest)
    return manifest


def freeze_inputs(data_dir: Path, config: Path, ack_g4: bool = False) -> dict:
    if not ack_g4:
        raise EvaluationError("Freeze requires explicit --ack-g4 after root declares integration/MVP ready")
    manifest = dataset_manifest(data_dir)
    if manifest.get("frozen"):
        raise EvaluationError("Input already frozen; create a new version instead of replacing it")
    config_value = read_json(config)
    if config_value.get("ranking_k") != 5:
        raise EvaluationError("This runner implements ranking_k=5; change/version the implementation before freezing another k")
    result = {**manifest, "stage": "frozen_test_input", "frozen": True,
              "g4_declaration": "operator_explicit_acknowledgement",
              "protocol": config_value, "protocol_hash": content_hash(config_value),
              "protocol_path": str(config.resolve()), "code_hashes": code_hashes(),
              "labels_status": "pending_human_judgments"}
    write_json(data_dir / "manifests/input_manifest.json", result)
    return result


def _affordability_view(value: dict) -> dict:
    loan = value["loan"] or {}
    return {"shortfall_vnd": value["shortfall_vnd"], "burden_vnd": value["burden_vnd"],
            "housing_ratio": value["housing_ratio"], "band": value["band"],
            "installment_vnd": loan.get("installment_vnd"), "total_interest_vnd": loan.get("total_interest_vnd"),
            "exceeds_max_principal": loan.get("exceeds_max_principal", False)}


def oracle_report(data_dir: Path, output: Path) -> dict:
    manifest = dataset_manifest(data_dir)
    rows = []
    for case in read_json(data_dir / "oracles/cost_cases.json")["cases"]:
        start = time.perf_counter()
        actual = estimate_cost(CostRequest.model_validate({key: case[key] for key in ("quote", "scenario", "affordability")
                                                          if key in case})).model_dump(mode="json")
        differences = {key: {"expected": expected, "actual": actual[key]}
                       for key, expected in case["expected"].items() if actual[key] != expected}
        if "expected_affordability" in case:
            observed = _affordability_view(actual["affordability"])
            differences.update({f"affordability.{key}": {"expected": expected, "actual": observed.get(key)}
                                for key, expected in case["expected_affordability"].items()
                                if observed.get(key) != expected})
        budget_rows = []
        for check in case.get("budget_checks", []):
            if "monthly_limit_vnd" in check:
                value = actual["monthly_total_vnd"]
                actual_pass = value is not None and value <= check["monthly_limit_vnd"]
                expected_pass = check["expected_monthly_pass"]
            else:
                value = actual["initial_total_vnd"]
                actual_pass = value is not None and value <= check["initial_limit_vnd"]
                expected_pass = check["expected_initial_pass"]
            budget_rows.append({**check, "actual_pass": actual_pass, "passed": actual_pass == expected_pass})
        rows.append({"case_id": case["case_id"], "passed": not differences and all(row["passed"] for row in budget_rows),
                     "differences": differences, "budget_checks": budget_rows,
                     "actual": actual, "expected": case["expected"],
                     "machine_latency_ms": round((time.perf_counter() - start) * 1000, 4)})
    summary = {"kind": "offline_finance_component", "case_count": len(rows),
               "input_manifest_hash": content_hash(manifest), "code_hashes": code_hashes(),
               "passed": sum(row["passed"] for row in rows), "failed": sum(not row["passed"] for row in rows),
               "exact_vnd_required": True, "model_calls": 0,
               "oracle_origin": "Authored arithmetic constants, independent of engine output; human cross-check pending.",
               "cases": rows}
    write_json(output, summary)
    return summary


def extraction_report(data_dir: Path, split: str, output: Path, live: bool = False,
                      allow_live: bool = False, api_budget_vnd: int | None = None) -> dict:
    manifest = require_split_ready(data_dir, split)
    if live and (not allow_live or not api_budget_vnd or api_budget_vnd <= 0):
        raise EvaluationError("Live extraction needs explicit --allow-live and positive --api-budget-vnd; default is offline")
    if live:
        # A single Responses call/utterance with SDK retries disabled; cap output and row count.
        import os
        from openai import OpenAI
        if not os.getenv("OPENAI_API_KEY"):
            raise EvaluationError("Live extraction unavailable: API key not configured (never printed)")
        interpreter = OpenAIInterpreter(client=OpenAI(timeout=20, max_retries=0))
        if manifest.get("frozen") and interpreter.model != manifest.get("protocol", {}).get("extraction_model"):
            raise EvaluationError("Extraction model differs from frozen protocol")
    else:
        interpreter = DemoInterpreter()
    rows = []
    for profile in load_profiles(data_dir, split):
        for utterance in profile["utterances"]:
            start = time.perf_counter()
            error, predicted = None, None
            try:
                predicted = interpreter.extract(redact(utterance["text"])).model_dump(mode="json")
            except DomainError as exc:
                error = exc.code
            usage = getattr(interpreter, "last_usage", {}) if live else {}
            rows.append({"profile_id": profile["profile_id"], "group_id": profile["group_id"],
                         "utterance_id": utterance["utterance_id"], "gold": utterance["gold"],
                         "predicted": predicted, "error": error, "mode": "live" if live else "demo_rules",
                         "budget_hint_local_vnd": budget_hint(utterance["text"]),
                         "financial_hint_not_model_f1": True,
                         "machine_latency_ms": round((time.perf_counter() - start) * 1000, 4),
                         "api_attempts": usage.get("logical_calls", 0),
                         "provider_usage": usage if live else "not_applicable"})
    report = {"kind": "synthetic_gold_extraction_component", "stage": manifest["stage"], "split": split,
              "input_manifest_hash": content_hash(manifest), "code_hashes": code_hashes(),
              "model": getattr(interpreter, "model", None),
              "mode": "live" if live else "demo_rules", "model_calls": sum(row["api_attempts"] for row in rows),
              "model_quality_measured": live, "gold_origin": "authored_synthetic_cases_not_real_customer_judgments",
              "metrics": extraction_metrics(rows), "rows": rows,
              "question_correctness": "not_measured_without_conversation_trace",
              "api_budget_vnd": api_budget_vnd if live else None,
              "cost_vnd": "unavailable_no_provider_usage" if live else 0,
              "notice": "F1 is descriptive on authored synthetic fields; not satisfaction or room relevance."}
    write_json(output, report)
    return report


def _status(items: list, diagnostics: dict) -> str:
    return "successful" if items else "needs_verification" if diagnostics.get("verification") else "no_match"


def ranking_run(data_dir: Path, split: str, run_dir: Path, semantic_catalog=None) -> dict:
    manifest = require_split_ready(data_dir, split)
    reference = Catalog(data_dir / "catalog/rooms.json")
    catalog = semantic_catalog or reference
    if catalog.version != reference.version:
        raise EvaluationError("Semantic database catalog differs from the hashed JSON input; use a separate matching dataset DB")
    provider = getattr(getattr(catalog, "semantic_scorer", None), "provider", None)
    if manifest.get("frozen") and provider is not None:
        expected = manifest.get("protocol", {}).get("methods", {}).get("P", {})
        actual = (getattr(catalog, "alpha", .3), getattr(provider, "model", None), getattr(provider, "dimensions", None))
        if actual != (expected.get("alpha"), expected.get("embedding_model"), expected.get("dimensions")):
            raise EvaluationError("Semantic model/dimensions/alpha differ from frozen protocol")
    if not hasattr(catalog, "eligible_candidates") or not hasattr(catalog, "rank"):
        raise EvaluationError("Backend all-eligible rank interface not ready; cannot substitute top5-only match")
    rows = []
    room_metadata = read_json(data_dir / "catalog/metadata.json")
    for profile_row in load_profiles(data_dir, split):
        profile = confirmed_profile(profile_row)
        eligible, filter_diagnostics = catalog.eligible_candidates(profile)
        eligible_ids = sorted(item.room_id for item in eligible)
        methods = {}
        for method in ("B1", "P"):
            start = time.perf_counter()
            calls_before = getattr(provider, "calls", 0)
            tokens_before = getattr(provider, "tokens", 0)
            missing_usage_before = getattr(provider, "usage_missing_calls", 0)
            try:
                ranked, diagnostics = catalog.rank(profile, method=method)
                algorithm = diagnostics.get("algorithm", "structured_baseline_v1")
                if method == "P" and ("fallback" in algorithm.casefold() or "structured" in algorithm.casefold()):
                    methods[method] = {"status": "unavailable", "error": "structured_fallback_is_not_hybrid_P",
                                       "items": [], "diagnostics": diagnostics}
                else:
                    if sorted(item.room_id for item in ranked) != eligible_ids:
                        raise EvaluationError("B1/P ranking candidate set differs from common eligible set")
                    methods[method] = {"status": _status(ranked, diagnostics),
                                       "items": [item.model_dump(mode="json") for item in ranked[:5]],
                                       "diagnostics": diagnostics, "algorithm": algorithm}
            except DomainError as exc:
                methods[method] = {"status": "unavailable", "error": exc.code, "items": []}
            methods[method]["machine_latency_ms"] = round((time.perf_counter() - start) * 1000, 4)
            methods[method]["model_calls"] = getattr(provider, "calls", 0) - calls_before
            missing_usage = getattr(provider, "usage_missing_calls", 0) - missing_usage_before
            methods[method]["embedding_tokens"] = None if missing_usage else getattr(provider, "tokens", 0) - tokens_before
            methods[method]["usage_missing_calls"] = missing_usage
            methods[method]["mode"] = "live_pgvector_embedding" if provider is not None else "offline_json_no_embedding_provider"
        rows.append({"profile_id": profile_row["profile_id"], "group_id": profile_row["group_id"],
                     "confirmed_profile": profile.model_dump(mode="json"),
                     "eligible_ids": eligible_ids, "eligible_hash": content_hash(eligible_ids),
                     "eligible_count": len(eligible), "filter_diagnostics": filter_diagnostics, "methods": methods})
    write_jsonl(run_dir / "rankings.jsonl", rows)
    run_manifest = {"stage": manifest["stage"], "frozen": manifest["frozen"], "split": split,
                    "input_manifest_hash": content_hash(manifest), "code_hashes": code_hashes(),
                    "catalog_hash": catalog.version, "rankings_hash": sha256_file(run_dir / "rankings.jsonl"),
                    "methods_requested": ["B1", "P"], "method_status_counts": {
                        method: {status: sum(row["methods"][method]["status"] == status for row in rows)
                                 for status in ("successful", "no_match", "needs_verification", "unavailable")}
                        for method in ("B1", "P")},
                    "model_calls": sum(value["model_calls"] for row in rows for value in row["methods"].values()),
                    "labels_status": "pending_human_judgments", "privacy": "synthetic_only_no_real_customer_data",
                    "protocol_hash": manifest.get("protocol_hash"),
                    "semantic_provider": "live" if provider is not None else "unavailable",
                    "semantic_alpha": getattr(catalog, "alpha", .3),
                    "embedding_model": getattr(provider, "model", None),
                    "embedding_dimensions": getattr(provider, "dimensions", None),
                    "call_unit": "logical_SDK_invocation; HTTP retries not separately observed",
                    "notice": "B1 outputs are recommendations, never gold judgments; offline P may be unavailable. Provider cost not calculated without verified price/usage evidence."}
    write_json(run_dir / "run_manifest.json", run_manifest)
    build_annotation(rows, room_metadata, catalog.rooms(), run_dir)
    return run_manifest


def build_annotation(rankings: list[dict], metadata: dict, rooms: list, run_dir: Path) -> dict:
    by_id = {room.id: room.model_dump(mode="json") for room in rooms}
    packets, templates = [], []
    rng = random.Random(20261001)
    for row in rankings:
        items = {}
        for method in row["methods"].values():
            if method["status"] in ("successful", "no_match", "needs_verification"):
                for item in method["items"]:
                    items[item["room_id"]] = item
        candidates = []
        for room_id, item in items.items():
            # Intentionally omit algorithm, component scores, method identity and machine order.
            candidates.append({"room_id": room_id, "room_revision": item["room_revision"],
                               "room": by_id[room_id], "cost": item["cost"],
                               "semantic_text": metadata[room_id]["semantic_text"]})
            templates.append({"profile_id": row["profile_id"], "room_id": room_id,
                              "room_revision": item["room_revision"], "relevance": "",
                              "reason": "", "evidence": "", "judge_id": ""})
        rng.shuffle(candidates)
        packets.append({"profile_id": row["profile_id"], "confirmed_profile": row["confirmed_profile"],
                        "candidates": candidates, "judgment_status": "pending_human_judgments"})
    write_json(run_dir / "blind_packets.json", {"notice": "Blind synthetic annotation inputs. Blank relevance must be judged by a human; not machine gold.",
                                               "packets": packets})
    with (run_dir / "judgments_template.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["profile_id", "room_id", "room_revision", "relevance", "reason", "evidence", "judge_id"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(templates)
    blocks = []
    for packet in packets:
        blocks.append(f"<section><h2>{html.escape(packet['profile_id'])}</h2><pre>{html.escape(json.dumps(packet['confirmed_profile'],ensure_ascii=False,indent=2))}</pre>")
        for candidate in packet["candidates"]:
            key = f"{packet['profile_id']}|{candidate['room_id']}"
            evidence = {"room": candidate["room"], "cost": candidate["cost"]}
            blocks.append(f'<article data-key="{html.escape(key,quote=True)}"><h3>{html.escape(candidate["room_id"])}</h3>'
                          f'<pre>{html.escape(json.dumps(evidence,ensure_ascii=False,indent=2))}</pre>'
                          '<label>Nhãn <select class="relevance"><option value="">Chưa chấm</option>'
                          '<option value="0">0</option><option value="1">1</option><option value="2">2</option><option value="3">3</option></select></label>'
                          '<label>Lý do <textarea class="reason"></textarea></label><label>Bằng chứng/field <input class="evidence"></label></article>')
        blocks.append("</section>")
    template_json = json.dumps(templates, ensure_ascii=False).replace("<", "\\u003c")
    page = '''<!doctype html><html lang="vi"><meta charset="utf-8"><title>HomeMatch — chấm nhãn giả lập</title>
<style>body{font:16px system-ui;max-width:1000px;margin:30px auto;padding:20px;background:#f7f8fa}article,section{background:white;border:1px solid #dde1e5;border-radius:12px;padding:18px;margin:15px 0}pre{white-space:pre-wrap;font-size:13px}label{display:block;margin:12px 0}input,textarea,select{padding:8px;max-width:90%;width:400px}button{padding:12px}strong{color:#923900}</style>
<h1>Chấm mức phù hợp — dữ liệu giả lập</h1><p>Không phải tin HubHome hoặc phòng thật. <strong>Các nhãn đang để trống; người chấm đọc hồ sơ và bằng chứng rồi quyết định.</strong></p>
<p>0: vi phạm hard/không đủ bằng chứng hard (ghi reason). 1: đủ hard nhưng đáp ứng ít sở thích. 2: đáp ứng đáng kể, có đánh đổi. 3: đáp ứng tốt theo hồ sơ. Điểm không phải thứ hạng máy.</p>
<label>Judge ID giả danh <input id="judge"></label><button onclick="save()">Tải judgments.json</button>''' + "".join(blocks) + '''<script>
const rows=TEMPLATE;
function save(){const judge=document.getElementById('judge').value.trim();if(!judge){alert('Nhập judge ID giả danh');return;}
const annotations=[];for(const a of document.querySelectorAll('article')){const value=a.querySelector('.relevance').value;const base=rows.find(r=>r.profile_id+'|'+r.room_id===a.dataset.key);annotations.push({...base,relevance:value===''?null:Number(value),reason:a.querySelector('.reason').value.trim(),evidence:a.querySelector('.evidence').value.trim(),judge_id:judge});}
const body={origin:'human_declared_local_annotation',judgments:annotations};const blob=new Blob([JSON.stringify(body,null,2)],{type:'application/json'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='judgments.json';link.click();URL.revokeObjectURL(link.href);}
</script></html>'''.replace("TEMPLATE", template_json)
    (run_dir / "annotation.html").write_text(page, encoding="utf-8")
    coverage = {"profile_count": len(packets), "candidate_pairs": len(templates),
                "completed_judgments": 0, "status": "pending_human_judgments",
                "pool_scope": "available_methods_only; final B1/P research requires both methods available and frozen input"}
    write_json(run_dir / "annotation_status.json", coverage)
    return coverage


def load_judgments(path: Path) -> dict[tuple[str, str], dict]:
    if path.suffix.casefold() == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            values = list(csv.DictReader(handle))
    else:
        payload = read_json(path)
        if payload.get("origin") != "human_declared_local_annotation":
            raise EvaluationError("Research judgment JSON must explicitly declare human annotation origin")
        values = payload["judgments"]
    result = {}
    for value in values:
        key = (value["profile_id"], value["room_id"])
        if key in result:
            raise EvaluationError(f"Duplicate judgment: {key}")
        label = value.get("relevance")
        if label in (None, ""):
            continue
        if isinstance(label, bool) or str(label) not in ("0", "1", "2", "3"):
            raise EvaluationError(f"Relevance must be integer0–3: {key}")
        if not all(str(value.get(field, "")).strip() for field in ("reason", "evidence", "judge_id")):
            raise EvaluationError(f"Judgment needs reason/evidence/judge_id: {key}")
        result[key] = {**value, "relevance": int(label), "room_revision": int(value["room_revision"])}
    return result


def evaluate_rankings(data_dir: Path, run_dir: Path, judgments_path: Path | None,
                      human_declared: bool = False, allow_development: bool = False) -> dict:
    manifest = dataset_manifest(data_dir)
    run = read_json(run_dir / "run_manifest.json")
    if sha256_file(run_dir / "rankings.jsonl") != run["rankings_hash"]:
        raise EvaluationError("Rankings hash mismatch")
    if run["input_manifest_hash"] != content_hash(manifest):
        raise EvaluationError("Ranking run and dataset manifest differ")
    if not judgments_path:
        summary = {"status": "pending_human_judgments", "quality_metrics": None,
                   "method_status_counts": run["method_status_counts"],
                   "notice": "Machine recommendations cannot substitute human relevance labels."}
        write_json(run_dir / "evaluation_summary.json", summary)
        return summary
    if not human_declared:
        raise EvaluationError("Explicit --human-declared required; never auto-label recommendations as gold")
    if not manifest.get("frozen") and not allow_development:
        raise EvaluationError("Research metrics require frozen input; --allow-development labels exploratory output")
    if manifest.get("frozen"):
        verify_code(manifest)
    judgments = load_judgments(judgments_path)
    packets = read_json(run_dir / "blind_packets.json")["packets"]
    expected = {(packet["profile_id"], item["room_id"]): item["room_revision"]
                for packet in packets for item in packet["candidates"]}
    if any(key not in expected or expected[key] != value["room_revision"] for key, value in judgments.items()):
        raise EvaluationError("Judgment references unknown pool candidate or wrong room revision")
    missing = [list(key) for key in expected if key not in judgments]
    rows = []
    for row in read_jsonl(run_dir / "rankings.jsonl"):
        labels = {room_id: value["relevance"] for (profile_id, room_id), value in judgments.items()
                  if profile_id == row["profile_id"]}
        methods = {}
        for name, value in row["methods"].items():
            if value["status"] in ("successful", "no_match", "needs_verification"):
                methods[name] = ranking_metrics([item["room_id"] for item in value["items"]], labels)
            else:
                methods[name] = {"status": value["status"], "error": value.get("error")}
        rows.append({"profile_id": row["profile_id"], "methods": methods})
    summary = {"status": "incomplete_judgments" if missing else "conditional_quality",
               "stage": "exploratory_development" if not manifest.get("frozen") else "frozen_test",
               "pool_candidate_pairs": len(expected), "judged_pairs": len(judgments), "missing_pairs": missing,
               "judgments_hash": sha256_file(judgments_path), "whole_profile_count": len(rows),
               "method_status_counts": run["method_status_counts"],
               "paired": {metric: paired_summary(rows, metric) for metric in
                          ("ndcg_at_5", "precision_at_5", "actual_return_precision")},
               "full_catalog_recall": "not_measured", "relevance_origin": "operator_declared_human_judgments",
               "notice": "Small synthetic pooled judgments; conditional coverage, not market quality or satisfaction."}
    # Labels are locked before metrics only for research, and only if every packet is judged.
    if manifest.get("frozen") and not missing:
        label_manifest = {"input_manifest_hash": content_hash(manifest), "rankings_hash": run["rankings_hash"],
                          "judgments_hash": summary["judgments_hash"], "label_origin": "human_declared",
                          "judged_pairs": len(judgments), "frozen": True}
        lock_path = data_dir / "manifests/evaluation_manifest.json"
        if lock_path.exists() and read_json(lock_path) != label_manifest:
            raise EvaluationError("Label manifest already locked to different judgments; use a new research version")
        write_json(lock_path, label_manifest)
    write_jsonl(run_dir / "per_profile_metrics.jsonl", rows)
    write_json(run_dir / "evaluation_summary.json", summary)
    return summary
