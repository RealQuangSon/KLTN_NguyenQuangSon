"""HN-08 — bộ kịch bản nhiều lượt cho agent (agent_e2e) và suite `eval clarify`.

Kịch bản chạy qua `HomeMatchService.message` (cùng đường với FE), chấm tất định
theo kỳ vọng trong `eval/scenarios/agent_e2e.json`: trường nháp, chip hỏi lại,
view, cấm tool, câu không được chứa thu nhập/số bịa. Chế độ demo là offline;
chế độ live chỉ chạy khi có `--allow-live` và ngân sách — mặc định in ước lượng
rồi dừng. Suite `eval clarify` chạy lớp 2+3 (kho + Jev/luật) trên 40 ca gold
`data/gold/clarify_cases.json`, báo cáo theo `decided_by`.

Đây là đầu vào đo cho EV-01; không thay nhãn người độc lập (DATA-05).
"""
from __future__ import annotations

import os
import re
import statistics
import tempfile
import time
from collections import Counter
from pathlib import Path

from backend.app.catalog import Catalog
from backend.app.interpreter import DemoInterpreter, OpenAIInterpreter
from backend.app.models import Actor
from backend.app.service import HomeMatchService

from .common import ROOT, EvaluationError, read_json, write_json

SCENARIOS_PATH = ROOT / "eval/scenarios/agent_e2e.json"
GOLD_CLARIFY_PATH = ROOT / "data/gold/clarify_cases.json"
MONEY_TEXT = re.compile(r"\b\d[\d.,]*\s*(?:triệu|đồng|vnd|đ)\b", re.I)


def _make_service(mode: str, model: str | None, root: Path) -> HomeMatchService:
    """Service cho một run; demo dùng luật, live dùng OpenAIInterpreter thật.
    Bắt buộc Catalog đầy đủ (220 căn) — Catalog mặc định chỉ 12 phòng demo."""
    if mode == "demo":
        interpreter = DemoInterpreter()
    else:
        if model:
            os.environ["OPENAI_MODEL"] = model
        interpreter = OpenAIInterpreter()
    return HomeMatchService(root / "agent-eval.sqlite", catalog=Catalog(
        ROOT / "data/catalog/rooms.json"), interpreter=interpreter)


def _draft_matches(draft: dict, expected: dict) -> tuple[bool, list[str]]:
    """So trường nháp: giá trị thật so sánh bằng; true nghĩa 'có giá trị khác null'."""
    problems = []
    for key, value in expected.items():
        actual = draft.get(key)
        if value is True:
            if actual in (None, [], {}, False):
                problems.append(f"{key}: mong có giá trị, thực tế {actual!r}")
        elif value is False:
            if actual not in (None, [], {}, False):
                problems.append(f"{key}: mong trống, thực tế {actual!r}")
        elif isinstance(value, list) and isinstance(actual, list):
            # preferences là tập hợp ngữ nghĩa: so không thứ tự.
            if sorted(actual) != sorted(value):
                problems.append(f"{key}: mong {value!r}, thực tế {actual!r}")
        elif actual != value:
            problems.append(f"{key}: mong {value!r}, thực tế {actual!r}")
    return not problems, problems


def _check_turn(turn: dict, reply: dict, mode: str) -> dict:
    """Chấm một lượt theo kỳ vọng khai báo; kỳ vọng tool chỉ chấm ở chế độ live."""
    message_blob = " ".join([reply.get("message") or "",
                             *(reply.get("questions") or [])])
    problems: list[str] = []
    checked: list[str] = []
    skipped: list[str] = []
    if "draft" in turn:
        ok, issues = _draft_matches(reply.get("draft") or {}, turn["draft"])
        checked.append("draft")
        problems += issues
    if "clarification_field" in turn:
        checked.append("clarification_field")
        dto = reply.get("clarification") or {}
        actual_field = dto.get("field")
        expected = turn["clarification_field"]
        if expected is None:
            if dto.get("question"):
                problems.append(f"mong không hỏi, thực tế chip field={actual_field}")
        elif actual_field != expected:
            problems.append(f"mong chip field={expected}, thực tế {actual_field}")
    if "view" in turn and turn["view"] is not None:
        checked.append("view")
        if reply.get("view") != turn["view"]:
            problems.append(f"mong view={turn['view']}, thực tế {reply.get('view')}")
    if "must_not_contain" in turn:
        checked.append("must_not_contain")
        for banned in turn["must_not_contain"]:
            if banned.lower() in message_blob.lower():
                problems.append(f"câu trả lời chứa cấm '{banned}'")
    if "tools_called" in turn:
        if mode == "live":
            checked.append("tools_called")
            actual_tools = set((reply.get("provenance") or {}).get("tools") or [])
            missing = set(turn["tools_called"]) - actual_tools
            if missing:
                problems.append(f"thiếu tool {sorted(missing)}")
        else:
            skipped.append("tools_called")
    if "tools_forbidden" in turn:
        checked.append("tools_forbidden")
        actual_tools = set((reply.get("provenance") or {}).get("tools") or [])
        used = set(turn["tools_forbidden"]) & actual_tools
        if used:
            problems.append(f"dùng tool cấm {sorted(used)}")
    if "questions_max" in turn:
        checked.append("questions_max")
        count = len(reply.get("questions") or [])
        if count > turn["questions_max"]:
            problems.append(f"mong ≤{turn['questions_max']} câu hỏi, thực tế {count}")
    return {"checked": checked, "skipped": skipped, "problems": problems}


def run_agent_scenarios(scenarios_path: Path = SCENARIOS_PATH, mode: str = "demo",
                        model: str | None = None, output: Path | None = None,
                        allow_live: bool = False, api_budget_vnd: int | None = None) -> dict:
    """Chạy toàn bộ kịch bản; demo offline, live phải có --allow-live + ngân sách."""
    payload = read_json(scenarios_path)
    scenarios = payload["scenarios"]
    if len(scenarios) < 40:
        raise EvaluationError(f"agent_e2e cần ≥ 40 kịch bản, thấy {len(scenarios)}")
    if mode == "live" and (not allow_live or not api_budget_vnd or api_budget_vnd <= 0):
        # Không tự gọi mạng: in ước lượng rồi dừng, chờ người dùng tự chạy lại.
        calls = sum(len(scenario["turns"]) for scenario in scenarios) * 4
        raise EvaluationError(
            "Chế độ live cần --allow-live và --api-budget-vnd > 0. Ước tính cho "
            f"{len(scenarios)} kịch bản/{sum(len(s['turns']) for s in scenarios)} lượt: "
            f"~{calls} lần gọi LLM + ~{len(scenarios)} lần Jev "
            "(đơn giá xem bảng giá OpenRouter trước khi chạy).")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="agent-eval-") as tmp:
        service = _make_service(mode, model, Path(tmp))
        renter = Actor(id="renter-a", role="renter")
        rows: list[dict] = []
        durations: list[float] = []
        try:
            for scenario in scenarios:
                sid = service.create_session(renter)["session_id"]
                scenario_rows = []
                for index, turn in enumerate(scenario["turns"]):
                    t0 = time.monotonic()
                    reply = service.message(sid, renter, turn["user"])
                    durations.append((time.monotonic() - t0) * 1000)
                    verdict = _check_turn(turn, reply, mode)
                    entry = {"turn_index": index, "user": turn["user"],
                             "duration_ms": round(durations[-1], 1),
                             "intent": reply.get("intent"), "status": reply.get("status"),
                             "agent_mode": reply.get("agent_mode"),
                             "questions": len(reply.get("questions") or []),
                             "clarification_field": (reply.get("clarification") or {}).get("field"),
                             "checked": verdict["checked"], "skipped": verdict["skipped"],
                             "problems": verdict["problems"],
                             "passed": not verdict["problems"]}
                    if mode == "live":
                        entry["tools"] = sorted((reply.get("provenance") or {}).get("tools") or [])
                    scenario_rows.append(entry)
                draft = service.session(sid, renter)["draft"]
                final = scenario.get("final") or {}
                final_problems: list[str] = []
                if final.get("draft"):
                    ok, issues = _draft_matches(draft, final["draft"])
                    final_problems += issues
                published = None
                if final.get("published"):
                    profile = service._profile_from_draft(sid)
                    if profile is None:
                        final_problems.append("final.published: hồ sơ chưa đủ để xác nhận")
                    else:
                        fresh = service.repo.session(sid)
                        result = service.confirm(sid, renter, profile, fresh["draft_revision"])
                        published = result["status"]
                        if result["status"] != "published":
                            final_problems.append(f"final.published: run {result['status']}")
                rows.append({"id": scenario["id"], "city": scenario.get("city"),
                             "turns": scenario_rows,
                             "published": published,
                             "final_problems": final_problems,
                             "passed": all(row["passed"] for row in scenario_rows)
                             and not final_problems})
        finally:
            service.close()
    turn_rows = [row for scenario in rows for row in scenario["turns"]]
    checked_rows = [row for row in turn_rows if row["checked"]]
    durations_sorted = sorted(durations)
    report = {
        "kind": "agent_scenarios", "version": 1, "mode": mode, "model": model,
        "scenarios_file": str(scenarios_path),
        "scenario_count": len(scenarios),
        "turn_count": len(turn_rows),
        "completed_scenarios": sum(1 for row in rows if row["passed"]),
        "completion_rate": round(sum(1 for row in rows if row["passed"]) / len(rows), 4),
        "turn_pass_rate": round(sum(1 for row in checked_rows if row["passed"])
                                / len(checked_rows), 4) if checked_rows else None,
        "questions_before_first_result": round(
            statistics.mean(row["questions"] for scenario in rows
                            for row in scenario["turns"][:1]), 2) if rows else None,
        "p50_ms": round(durations_sorted[len(durations_sorted) // 2], 1) if durations_sorted else None,
        "p95_ms": round(durations_sorted[min(len(durations_sorted) - 1,
                                             int(len(durations_sorted) * 0.95))], 1) if durations_sorted else None,
        "cost_usd": None if mode == "demo" else None,  # live: cộng usage.cost khi chạy thật
        "wall_seconds": round(time.monotonic() - started, 1),
        "results": rows,
    }
    if output is not None:
        write_json(output, report)
    return report


# --- Suite `eval clarify`: lớp 2+3 trên gold -------------------------------

def _preferred_rank(options: list[dict], preferred: str | None) -> int | None:
    """Vị trí (0-based) của lựa chọn khớp nhãn `preferred` trong danh sách đã xếp.
    Đọc từ DTO chip (patch có cấu trúc), không cần interpretation nội bộ."""
    if not preferred:
        return None
    for index, option in enumerate(options):
        patch_set = (option.get("patch") or {}).get("set") or {}
        if "destination_radius_m" in patch_set and \
                preferred == f"radius_{patch_set['destination_radius_m']}":
            return index
        if patch_set.get("budget_scope") == preferred:
            return index
    return None


def run_clarify_suite(gold_path: Path = GOLD_CLARIFY_PATH, output: Path | None = None,
                      model: str | None = None) -> dict:
    """Chạy lớp 2 (lựa chọn từ kho) + lớp 3 (Jev/luật) trên từng ca gold.

    Lớp 1 dựng nháp bằng luật demo (không qua `message` để lớp hỏi lại của graph
    không tiêu thụ quyết định trước). Nhãn: should_ask=yes → mong một câu hỏi có
    chip; no → mong không hỏi (None hoặc tự áp giả định); low_impact → tính như
    'no' ở precision/recall."""
    from backend.app.interpreter import rent_budget_hint
    from backend.app.locations import resolve_place
    from backend.app.models import Destination, DraftPatch

    gold = read_json(gold_path)["cases"]
    # Lớp 1 mô phỏng cho marker tường minh mà model live tự đọc qua update_needs:
    # bán kính ("2 km") và phạm vi tiền ("tổng tháng", "tiền thuê/rent").
    radius_given = re.compile(r"(\d+(?:[.,]\d+)?)\s*km", re.I)
    scope_total = re.compile(r"tổng tháng|tổng chi phí tháng", re.I)
    scope_rent = re.compile(r"tiền thuê|rent\b|chỉ tính tiền thuê", re.I)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="clarify-eval-") as tmp:
        os.environ.setdefault("HOMEMATCH_MATCHING_METHOD", "B1")
        service = _make_service("demo", model, Path(tmp))
        renter = Actor(id="renter-a", role="renter")
        rows: list[dict] = []
        try:
            for case in gold:
                sid = service.create_session(renter)["session_id"]
                # Lớp 1: luật demo trích nhu cầu vào nháp (inferred), như update_needs.
                extraction = DemoInterpreter().extract(case["text"])
                patch = {key: value for key in ("city", "area", "room_type", "bedrooms",
                                                "people", "preferences", "needs_destination",
                                                "accept_estimated_data")
                         for value in [getattr(extraction, key, None)] if value}
                if patch:
                    service._apply_agent_patch(sid, patch)
                if extraction.destination_text:
                    draft = service._draft(sid)
                    place = resolve_place(extraction.destination_text, draft.city)
                    if place:
                        service._apply_agent_patch(sid, {"destination": Destination(
                            label=place["label"], latitude=place["latitude"],
                            longitude=place["longitude"], uncertainty_m=place["uncertainty_m"],
                            max_distance_m=3000)})
                        if not service._draft(sid).city and place.get("city"):
                            # Như vòng lặp live: model ghi city inferred sau find_place.
                            service._apply_agent_patch(sid, {"city": place["city"]})
                markers = case["text"]
                radius = radius_given.search(markers)
                if radius and service._draft(sid).destination:
                    meters = int(float(radius.group(1).replace(",", ".")) * 1000)
                    service.patch_draft(sid, renter, DraftPatch(
                        expected_draft_revision=service.repo.session(sid)["draft_revision"],
                        set={"destination_radius_m": meters}, source="clarify"))
                scope = "total" if scope_total.search(markers) else \
                    ("rent" if scope_rent.search(markers) else None)
                if scope:
                    service.patch_draft(sid, renter, DraftPatch(
                        expected_draft_revision=service.repo.session(sid)["draft_revision"],
                        set={"budget_scope": scope}, source="clarify"))
                hint = rent_budget_hint(case["text"])
                if hint is None:
                    # Ca không nêu tiền: cấp trần gợi ý mặc định như phiên thật đã
                    # có ngân sách từ lượt trước — lớp 2 cần tiền để xếp hạng đếm.
                    hint = 6_000_000
                service._apply_chat_budget_hint(sid, hint, service.repo.session(sid)["draft_revision"])
                # Lớp 2+3: lựa chọn từ kho + quyết định luật (decided_by="rules").
                payload = service._clarification_payload(sid)
                asked = bool((payload or {}).get("question"))
                decided_by = (payload or {}).get("decided_by") or \
                    ("auto" if (payload or {}).get("assumed") else "none")
                expect_ask = case["should_ask"] == "yes"
                treated_negative = case["should_ask"] in ("no", "low_impact")
                correct = asked == expect_ask
                top1 = None
                if asked:
                    options = payload.get("options") or []
                    rank = _preferred_rank(options, case.get("preferred"))
                    top1 = (rank == 0) if rank is not None else None
                rows.append({"case_id": case["case_id"], "ambiguity": case["ambiguity"],
                             "should_ask": case["should_ask"], "asked": asked,
                             "asked_field": (payload or {}).get("field"),
                             "correct": correct, "decided_by": decided_by,
                             "top1_matches_preferred": top1,
                             "options": [(option.get("id"),
                                          _preferred_rank([option], case.get("preferred")) == 0)
                                         for option in (payload or {}).get("options") or []]
                             if asked else []})
        finally:
            service.close()
    positives = [row for row in rows if row["should_ask"] == "yes"]
    negatives = [row for row in rows if row["should_ask"] in ("no", "low_impact")]
    true_positive = sum(1 for row in positives if row["asked"])
    false_positive = sum(1 for row in negatives if row["asked"])
    false_negative = sum(1 for row in positives if not row["asked"])
    asked_rows = [row for row in rows if row["asked"]]
    top1_known = [row for row in asked_rows if row["top1_matches_preferred"] is not None]
    decided = Counter(row["decided_by"] for row in rows)
    report = {
        "kind": "clarify_suite", "version": 1,
        "gold_file": str(gold_path), "case_count": len(gold),
        "precision": round(true_positive / (true_positive + false_positive), 4)
        if true_positive + false_positive else None,
        "recall": round(true_positive / (true_positive + false_negative), 4)
        if true_positive + false_negative else None,
        "accuracy": round(sum(1 for row in rows if row["correct"]) / len(rows), 4) if rows else None,
        "top1_accuracy": round(sum(1 for row in top1_known if row["top1_matches_preferred"])
                               / len(top1_known), 4) if top1_known else None,
        "decided_by": dict(decided),
        "confusion": {"tp": true_positive, "fp": false_positive,
                      "fn": false_negative, "tn": len(negatives) - false_positive},
        "results": rows,
        "note": "Nhãn do tác giả đặt (chưa có nhãn người độc lập); decided_by là "
                "'rules' ở chế độ demo — Jev chỉ chạy khi HOMEMATCH_DECISION_MODE=jev. "
                "Ca không nêu tiền được cấp trần gợi ý 6.000.000 (giả định phiên thật "
                "đã có ngân sách) vì lớp 2 cần trần để xếp hạng đếm.",
        "wall_seconds": round(time.monotonic() - started, 1),
    }
    if output is not None:
        write_json(output, report)
    return report
