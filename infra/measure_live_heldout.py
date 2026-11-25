"""Đo agent trên LLM THẬT bằng bộ câu GIỮ RIÊNG (eval/fixtures/live_heldout_1118.json).

Bộ câu này không dùng để chỉnh code: sửa lỗi theo nó thì phải viết bộ mới để đo.
Mọi lượt đi qua POST /sessions/{id}/messages của app thật (TestClient, DB SQLite tạm,
không đụng Neon); model, analyst và các tuỳ chọn agent lấy từ .env như khi chạy app.

    set -a; source .env; set +a
    .venv/bin/python -m infra.measure_live_heldout --label K-1118 --run 1 \
        --catalog .local/chotot/chotot-2026-11-07-5k-r2/catalog.json
    .venv/bin/python -m infra.measure_live_heldout --summarize eval/runs/live-2026-11-18/heldout-K-1118-run*.json

Tiêu chí bằng code (đóng băng theo hash script + hash bộ câu ghi trong output):
- mỗi lượt: HTTP 200; không bị thay bằng câu mẫu an toàn/câu lỗi provider; câu hỏi
  có nút thì phải có ít nhất một nút; không lộ từ nội bộ hay mã phòng;
- theo kỳ vọng của từng lượt: thành phố/khu/số người/mức tiền/cách hiểu mức tiền/loại
  phòng/điểm đến agent ghi nhận, đặt lịch đúng căn, số tiền vào ở và trả góp khớp
  engine, trạng thái và các cụm phải có/không được có.
Script không chấm chất lượng câu chữ — transcript xuất ra để NGƯỜI chấm.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import tempfile
import time
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

# 18/11 (sau lần đo K): thêm "chotot-[" — mask_pii đổi mã căn lọt ra câu trả lời
# thành "chotot-[số đã che]", bản cũ không bắt được dạng này.
CODE_LEAK = re.compile(r"chotot-\d|chotot-\[|synthetic-room|demo-\d|\bcăn 0\d\d|\bphòng 0\d\d|giả lập", re.I)
PROVIDER_FALLBACK = "Trợ lý AI tạm chưa xử lý"


def fold(value: str | None) -> str:
    text = unicodedata.normalize("NFD", (value or "").lower()).replace("đ", "d")
    return "".join(char for char in text if not unicodedata.combining(char))


def vnd(amount: int) -> str:
    return f"{amount:,}".replace(",", ".")


def understood(body: dict) -> dict:
    """Giá trị agent đang ghi nhận: nháp trước, hồ sơ đã xác nhận nếu nháp trống."""
    draft = body.get("draft") or {}
    profile = body.get("confirmed_profile") or {}

    def pick(draft_value, profile_value):
        return draft_value if draft_value not in (None, "", []) else profile_value

    destination = pick((draft.get("destination") or {}).get("label"),
                       (profile.get("destination") or {}).get("label"))
    budget = pick(draft.get("budget_hint_vnd") or draft.get("monthly_budget_vnd"),
                  profile.get("max_monthly_cost_vnd") or profile.get("max_rent_vnd"))
    scope = draft.get("budget_scope")
    if scope is None and profile:
        scope = "rent" if profile.get("max_rent_vnd") else ("total" if profile.get("max_monthly_cost_vnd") else None)
    return {"city": pick(draft.get("city"), profile.get("city")),
            "area": pick(draft.get("area"), profile.get("area")),
            "people": pick(draft.get("people"), (profile.get("scenario") or {}).get("people")),
            "budget": budget, "budget_scope": scope,
            "room_type": pick(draft.get("room_type"), profile.get("room_type")),
            "destination": destination}


def check_turn(body: dict, expect: dict, results_before: list[dict], safe_templates: tuple[str, ...],
               internal_terms) -> dict:
    """{tên tiêu chí: "ok" | "skip: …" | "FAIL: …"} cho một lượt."""
    checks: dict[str, str] = {}
    message = body.get("message") or ""
    text = message + " " + " ".join(body.get("questions") or [])
    # 18/11 (sau lần đo K): câu trả lời cẩm nang nằm ở thẻ `answers`, không ở message —
    # bản cũ chỉ đọc message/questions nên chấm trượt nhầm câu cẩm nang đúng.
    for card in body.get("answers") or []:
        if isinstance(card, dict):
            text += " " + " ".join(str(value) for value in card.values() if isinstance(value, str))
    clarification = body.get("clarification") or {}
    # --- chung cho mọi lượt ---
    if message.startswith(PROVIDER_FALLBACK) or text.lstrip().startswith(PROVIDER_FALLBACK):
        checks["no_provider_fallback"] = "FAIL: câu lỗi provider"
    else:
        checks["no_provider_fallback"] = "ok"
    if any(message.startswith(template) for template in safe_templates):
        checks["not_safe_template"] = "ok" if expect.get("allow_safe") else "FAIL: câu trả lời bị thay bằng câu mẫu"
    else:
        checks["not_safe_template"] = "ok"
    if clarification.get("question") and not (clarification.get("options") or []):
        checks["no_empty_chip"] = f"FAIL: câu hỏi [{clarification.get('field')}] không kèm nút nào"
    else:
        checks["no_empty_chip"] = "ok"
    found = internal_terms.search(text)
    checks["no_internal_terms"] = f"FAIL: '{found.group(0)}'" if found else "ok"
    leak = CODE_LEAK.search(text)
    checks["no_code_leak"] = f"FAIL: '{leak.group(0)}'" if leak else "ok"
    # --- theo kỳ vọng ---
    seen = understood(body)
    for key in ("city", "people", "budget", "budget_scope", "room_type"):
        if key in expect:
            checks[key] = "ok" if seen[key] == expect[key] else f"FAIL: ghi nhận {seen[key]!r}, cần {expect[key]!r}"
    if "area" in expect:
        checks["area"] = ("ok" if seen["area"] and fold(seen["area"]).endswith(fold(expect["area"]))
                          else f"FAIL: ghi nhận {seen['area']!r}, cần …{expect['area']!r}")
    if "destination" in expect:
        checks["destination"] = ("ok" if seen["destination"] and fold(expect["destination"]) in fold(seen["destination"])
                                 else f"FAIL: ghi nhận {seen['destination']!r}, cần chứa {expect['destination']!r}")
    if expect.get("budget_none"):
        checks["budget_none"] = "ok" if seen["budget"] is None else f"FAIL: ghi trần {seen['budget']!r}"
    if "budget_not" in expect:
        checks["budget_not"] = "ok" if seen["budget"] != expect["budget_not"] else f"FAIL: ghi trần {seen['budget']!r}"
    if "city_not" in expect:
        checks["city_not"] = "ok" if seen["city"] != expect["city_not"] else f"FAIL: ghi thành phố {seen['city']!r}"
    status = body.get("status")
    if "status_in" in expect:
        checks["status_in"] = "ok" if status in expect["status_in"] else f"FAIL: status {status}"
    if "status_not" in expect:
        checks["status_not"] = "ok" if status not in expect["status_not"] else f"FAIL: status {status}"
    for pattern in expect.get("msg_has", []):
        checks[f"has:{pattern}"] = "ok" if re.search(pattern, text) else "FAIL: thiếu"
    for pattern in expect.get("msg_not", []):
        hit = re.search(pattern, text)
        checks[f"not:{pattern}"] = f"FAIL: '{hit.group(0)}'" if hit else "ok"
    if expect.get("keeps_results"):
        checks["keeps_results"] = "ok" if status == "published" else f"FAIL: status {status}"
    if "viewing_index" in expect:
        index = expect["viewing_index"]
        if len(results_before) < index:
            checks["viewing_index"] = f"skip: chỉ có {len(results_before)} căn"
        else:
            wanted = results_before[index - 1]["room_id"]
            got = (body.get("view_payload") or {}).get("room_id")
            outcome = (body.get("provenance") or {}).get("outcome")
            checks["viewing_index"] = ("ok" if got == wanted and outcome == "prepared"
                                       else f"FAIL: mở {got!r} (outcome {outcome}), cần căn {index}")
    if "move_in_of" in expect:
        index = expect["move_in_of"]
        if len(results_before) < index:
            checks["move_in"] = f"skip: chỉ có {len(results_before)} căn"
        else:
            total = ((results_before[index - 1].get("cost") or {}).get("initial_total_vnd"))
            if total is None:
                checks["move_in"] = "skip: engine không có tổng tiền vào ở"
            else:
                checks["move_in"] = "ok" if vnd(total) in text else f"FAIL: thiếu {vnd(total)} ₫"
    if "loan" in expect:
        from backend.app.costs import loan_installment
        loan = expect["loan"]
        installment = loan_installment(loan["principal"], Decimal(loan["annual_rate"]), loan["months"])
        checks["loan"] = "ok" if vnd(installment) in text else f"FAIL: thiếu {vnd(installment)} ₫"
    return checks


def run(args) -> None:
    if os.environ.get("HOMEMATCH_LLM_MODE") != "openai":
        sys.exit("Cần LLM thật: set -a; source .env; set +a")
    os.environ.setdefault("HOMEMATCH_LLM_API", "chat_completions")
    os.environ["HOMEMATCH_AUTH_MODE"] = "demo"
    os.environ["HOMEMATCH_MATCHING_METHOD"] = "B1"
    os.environ["HOMEMATCH_EMBEDDING_MODE"] = "disabled"
    os.environ["HOMEMATCH_JOBS_INTERVAL_SECONDS"] = "0"
    tmp = tempfile.mkdtemp(prefix="live-heldout-")
    os.environ["HOMEMATCH_DB_PATH"] = os.path.join(tmp, "heldout.sqlite")
    os.environ.pop("HOMEMATCH_DATABASE_URL", None)  # DB tạm SQLite, không đụng Neon
    os.environ["HOMEMATCH_CATALOG_PATH"] = args.catalog

    fixture_bytes = Path(args.fixture).read_bytes()
    fixture = json.loads(fixture_bytes)
    meta = {"kind": "live_heldout", "label": args.label, "run": args.run, "catalog": args.catalog,
            "fixture": args.fixture,
            "fixture_sha256_16": hashlib.sha256(fixture_bytes).hexdigest()[:16],
            "script_sha256_16": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16],
            "model": os.environ.get("OPENAI_MODEL"),
            "analyst": os.environ.get("HOMEMATCH_INPUT_ANALYST"),
            "measured_at": datetime.now(timezone.utc).isoformat()}

    from fastapi.testclient import TestClient

    from backend.app.agent_loop import SAFE_OUTPUT_REPLY, SAFE_REPLY
    from backend.app.main import create_app
    from backend.app.service import HomeMatchService
    from infra.measure_hn13_dialog import INTERNAL_TERMS

    safe_templates = (SAFE_REPLY[:40], SAFE_OUTPUT_REPLY[:40],
                      "Mình vừa kiểm tra nhu cầu của bạn qua các bước bên dưới")
    service = HomeMatchService(os.environ["HOMEMATCH_DB_PATH"])
    app = create_app(lambda: service)
    only = set(args.only.split(",")) if args.only else None
    conversations = []
    started = time.monotonic()
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer demo-renter"}
        for conversation in fixture["conversations"]:
            if only and conversation["id"] not in only:
                continue
            sid = client.post("/sessions", headers=headers).json()["session_id"]
            turns = list(conversation["turns"])
            if conversation.get("setup"):
                turns = [{"text": fixture["setups"][conversation["setup"]],
                          "expect": {"status_in": ["published"]}, "setup": True}] + turns
            records = []
            for index, turn in enumerate(turns, 1):
                results_before = client.get(f"/sessions/{sid}/results", headers=headers).json().get("results") or []
                cost_before = service.budget.spent_usd(sid)
                t0 = time.monotonic()
                response = client.post(f"/sessions/{sid}/messages", headers=headers, json={"text": turn["text"]})
                latency = round((time.monotonic() - t0) * 1000)
                record = {"turn": index, "text": turn["text"], "setup": bool(turn.get("setup")),
                          "latency_ms": latency}
                if response.status_code != 200:
                    record.update({"http": response.status_code, "error": response.text[:300],
                                   "checks": {"http": f"FAIL: HTTP {response.status_code}"}})
                    records.append(record)
                    continue
                body = response.json()
                clarification = body.get("clarification") or {}
                record.update({
                    "status": body.get("status"), "agent_mode": body.get("agent_mode"),
                    "agents": body.get("agents"),
                    "route": (body.get("input_analysis") or {}).get("route"),
                    "llm_calls": (body.get("usage") or {}).get("logical_calls"),
                    "cost_usd": round(service.budget.spent_usd(sid) - cost_before, 6),
                    "message": body.get("message"), "questions": body.get("questions"),
                    "chip_field": clarification.get("field"),
                    "chips": [option.get("label") for option in clarification.get("options") or []],
                    "understood": understood(body),
                    "view_room": (body.get("view_payload") or {}).get("room_id"),
                    "checks": {"http": "ok", **check_turn(body, turn.get("expect") or {}, results_before,
                                                           safe_templates, INTERNAL_TERMS)},
                })
                records.append(record)
            failed = [f"#{record['turn']} {name}" for record in records
                      for name, verdict in record["checks"].items() if verdict.startswith("FAIL")]
            conversations.append({"id": conversation["id"], "group": conversation["group"],
                                  "passed": not failed, "failed": failed, "turns": records})
            print(f"{conversation['id']:12} {'ok' if not failed else 'FAIL ' + '; '.join(failed)}", flush=True)
    meta["elapsed_s"] = round(time.monotonic() - started, 1)
    meta["total_cost_usd"] = round(sum(record.get("cost_usd") or 0 for conversation in conversations
                                       for record in conversation["turns"]), 4)
    payload = {**meta, "conversations": conversations}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"heldout-{args.label}-run{args.run}"
    (out / f"{stem}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    export_transcript(payload, out / f"{stem}-transcript.md")
    passed = sum(1 for conversation in conversations if conversation["passed"])
    print(f"[{stem}] {passed}/{len(conversations)} hội thoại đạt · {meta['total_cost_usd']} USD · {meta['elapsed_s']}s")


def export_transcript(payload: dict, path: Path) -> None:
    lines = [f"# Đo live bộ giữ riêng — {payload['label']} lần {payload['run']}",
             f"Model `{payload['model']}` · analyst {payload['analyst']} · kho `{payload['catalog']}` · "
             f"bộ câu {payload['fixture_sha256_16']} · script {payload['script_sha256_16']} · "
             f"{payload['total_cost_usd']} USD · {payload['elapsed_s']} s", ""]
    for conversation in payload["conversations"]:
        mark = "ĐẠT" if conversation["passed"] else "KHÔNG ĐẠT"
        lines.append(f"## {conversation['id']} ({conversation['group']}) — {mark}")
        for record in conversation["turns"]:
            prefix = "Khách (dựng kết quả)" if record["setup"] else "Khách"
            lines.append(f"- **{prefix} {record['turn']}**: {record['text']}")
            if record.get("error"):
                lines.append(f"  - LỖI: {record['error']}")
            else:
                lines.append(f"  - `status={record['status']} mode={record['agent_mode']} route={record['route']} "
                             f"calls={record['llm_calls']} {record['latency_ms']}ms`")
                lines.append(f"  - **Trợ lý**: {record['message']}")
                if record.get("chips") or record.get("chip_field"):
                    lines.append(f"  - Nút [{record['chip_field']}]: " + " | ".join(record.get("chips") or []))
                lines.append(f"  - Ghi nhận: `{json.dumps(record['understood'], ensure_ascii=False)}`")
            bad = {name: verdict for name, verdict in record["checks"].items() if not verdict.startswith("ok")}
            if bad:
                lines.append("  - Tiêu chí: " + "; ".join(f"{name} → {verdict}" for name, verdict in bad.items()))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def summarize(paths: list[str]) -> None:
    runs = [json.loads(Path(path).read_text(encoding="utf-8")) for path in paths]
    print(f"{len(runs)} lần chạy · bộ câu {sorted({run['fixture_sha256_16'] for run in runs})} · "
          f"script {sorted({run['script_sha256_16'] for run in runs})} · "
          f"{round(sum(run['total_cost_usd'] for run in runs), 4)} USD")
    by_id: dict[str, list[dict]] = {}
    for run_payload in runs:
        for conversation in run_payload["conversations"]:
            by_id.setdefault(conversation["id"], []).append(conversation)
    total = sum(len(items) for items in by_id.values())
    passed = sum(1 for items in by_id.values() for item in items if item["passed"])
    print(f"Hội thoại đạt: {passed}/{total} ({passed / total:.0%})")
    groups: dict[str, list[bool]] = {}
    for items in by_id.values():
        for item in items:
            groups.setdefault(item["group"], []).append(item["passed"])
    for group, values in groups.items():
        print(f"  {group:28} {sum(values)}/{len(values)}")
    checks: dict[str, list[int]] = {}
    for items in by_id.values():
        for item in items:
            for record in item["turns"]:
                for name, verdict in record["checks"].items():
                    key = name.split(":")[0]
                    bucket = checks.setdefault(key, [0, 0, 0])
                    bucket[0 if verdict == "ok" else (1 if verdict.startswith("FAIL") else 2)] += 1
    print("Tiêu chí (đạt / không đạt / bỏ qua):")
    for name, (ok, fail, skip) in sorted(checks.items(), key=lambda kv: -kv[1][1]):
        print(f"  {name:22} {ok:4} {fail:4} {skip:4}")
    print("Hội thoại không đạt (số lần / tổng lần — lỗi):")
    for conversation_id, items in by_id.items():
        fails = [item for item in items if not item["passed"]]
        if fails:
            reasons = sorted({reason for item in fails for reason in item["failed"]})
            print(f"  {conversation_id:12} {len(fails)}/{len(items)} — {'; '.join(reasons)[:300]}")
    latencies = [record["latency_ms"] for run_payload in runs for conversation in run_payload["conversations"]
                 for record in conversation["turns"] if not record["setup"]]
    if latencies:
        latencies.sort()
        print(f"Độ trễ (bỏ lượt dựng kết quả): p50 {statistics.median(latencies)} ms · "
              f"p95 {latencies[int(len(latencies) * 0.95) - 1]} ms")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label")
    parser.add_argument("--run", type=int, default=1)
    parser.add_argument("--catalog")
    parser.add_argument("--fixture", default="eval/fixtures/live_heldout_1118.json")
    parser.add_argument("--out", default="eval/runs/live-2026-11-18")
    parser.add_argument("--only", default=None, help="chỉ chạy các id (phẩy ngăn cách) — chạy thử script")
    parser.add_argument("--summarize", nargs="+", default=None)
    args = parser.parse_args()
    if args.summarize:
        summarize(args.summarize)
        return
    if not args.label or not args.catalog:
        parser.error("--label và --catalog là bắt buộc khi đo")
    run(args)


if __name__ == "__main__":
    main()
