"""Offline latency/call measurement aggregation (EV-07).

Aggregates machine timings recorded by real runs of the offline pipeline.
Review-waiting time is never included; these are machine phases only.
"""
from __future__ import annotations

import math
from pathlib import Path

from .common import EvaluationError, read_json, read_jsonl, write_json


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile; deterministic and hand-checkable."""
    if not values or not 0 < fraction <= 1:
        raise EvaluationError("Percentile needs a non-empty sample and fraction in (0, 1]")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def _phase(values: list[float], **extra) -> dict:
    return {"samples": len(values), "unit": "ms",
            "p50": percentile(values, 0.5), "p95": percentile(values, 0.95), **extra}


def measurement_report(run_dir: Path, output: Path) -> dict:
    """Summarize machine latency and logical model calls from existing run artifacts."""
    extraction = read_json(run_dir / "extraction.json")
    oracle = read_json(run_dir / "oracle.json")
    rankings = read_jsonl(run_dir / "rankings.jsonl")
    run = read_json(run_dir / "run_manifest.json")
    phases: dict[str, dict] = {}
    phases["extraction"] = _phase([row["machine_latency_ms"] for row in extraction["rows"]],
                                  mode=extraction["mode"],
                                  model_calls=sum(row["api_attempts"] for row in extraction["rows"]))
    for method in ("B1", "P"):
        values = [row["methods"][method]["machine_latency_ms"] for row in rankings]
        calls = sum(row["methods"][method]["model_calls"] for row in rankings)
        statuses = {}
        for row in rankings:
            status = row["methods"][method]["status"]
            statuses[status] = statuses.get(status, 0) + 1
        phases[f"ranking_{method}"] = _phase(values, statuses=statuses, model_calls=calls,
                                             provider=run.get("semantic_provider"))
    phases["finance_oracle"] = _phase([case["machine_latency_ms"] for case in oracle["cases"]],
                                      mode="offline_cost_engine", model_calls=0)
    total_calls = sum(phase["model_calls"] for phase in phases.values())
    summary = {"kind": "offline_machine_measurement", "stage": run["stage"], "split": run["split"],
               "rankings_hash": run["rankings_hash"], "phases": phases,
               "total_logical_model_calls": total_calls,
               "review_waiting_time": "excluded_machine_phases_only",
               "cache_state": "not_applicable_offline_json_catalog",
               "environment": "single local process, offline synthetic dataset; not provider latency",
               "live_measurements": False,
               "notice": "Timings describe the offline rule/B1 pipeline on this machine only; "
                         "they are not GPT/embedding quality or provider latency evidence."}
    write_json(output, summary)
    return summary
