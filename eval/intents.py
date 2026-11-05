"""DA-01: offline gold-intent routing measurement for the chat graph route node.

The suite replays the routing decision the same way `_build_chat_graph` node
`route` decides with the offline interpreter: explicit `fixed_intent` wins,
otherwise the extraction intent of `DemoInterpreter`. It is a measurement only:
no accuracy threshold, errors are recorded, `simulate_finance` is expected to
misroute until AG-02 lands.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from backend.app.interpreter import DemoInterpreter, fixed_intent

from .common import content_hash, read_json, write_json
from .pipeline import code_hashes, require_split_ready


def decide_intent(text: str) -> str:
    """Mirror the demo routing decision of the chat graph (no model call, no draft)."""
    return fixed_intent(text) or DemoInterpreter().extract(text).intent


def intents_report(data_dir: Path, split: str, output: Path) -> dict:
    manifest = require_split_ready(data_dir, split)
    payload = read_json(data_dir / "profiles/intent_cases.json")
    cases = [dict(case) for case in payload["cases"] if case["split"] == split]
    confusion: Counter[str] = Counter()
    per_intent: dict[str, dict] = {}
    errors: list[dict] = []
    for case in cases:
        predicted = decide_intent(case["text"])
        confusion[f"{case['intent']}->{predicted}"] += 1
        stats = per_intent.setdefault(case["intent"], {"total": 0, "correct": 0})
        stats["total"] += 1
        stats["correct"] += predicted == case["intent"]
        if predicted != case["intent"]:
            errors.append({"case_id": case["case_id"], "gold": case["intent"],
                           "predicted": predicted, "text": case["text"]})
    intents = sorted(per_intent)
    predicted_labels = sorted({case.split("->", 1)[1] for case in confusion})
    matrix = {gold: {predicted: confusion.get(f"{gold}->{predicted}", 0)
                     for predicted in predicted_labels} for gold in intents}
    correct = sum(stats["correct"] for stats in per_intent.values())
    summary = {"kind": "offline_intent_routing_measurement", "split": split,
               "input_manifest_hash": content_hash(manifest), "code_hashes": code_hashes(),
               "decision_rule": payload["decision"], "case_count": len(cases),
               "correct": correct, "accuracy": correct / len(cases) if cases else None,
               "per_intent": {intent: {**stats, "accuracy": stats["correct"] / stats["total"]}
                              for intent, stats in sorted(per_intent.items())},
               "confusion_matrix": matrix, "errors": errors,
               "error_policy": "errors are recorded, never relabelled",
               "gate": "measurement_only_no_accuracy_threshold", "failed": 0,
               "notice": "Authored synthetic utterances; descriptive accuracy on gold intents, not live user traffic."}
    write_json(output, summary)
    return summary
