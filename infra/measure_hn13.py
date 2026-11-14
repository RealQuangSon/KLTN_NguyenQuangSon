"""HN-13 — đo 10 câu tiếng Việt khó trước/sau khi tách multi-agent (chạy live, trả phí).

Chạy (backend không tự nạp .env — nạp trong shell, KHÔNG nạp .local/neon.env):

    set -a; source .env; set +a
    .venv/bin/python -m infra.measure_hn13 --analyst off --out eval/runs/live-2026-11-07/hn13-baseline-off.json
    .venv/bin/python -m infra.measure_hn13 --analyst jev --out eval/runs/live-2026-11-07/hn13-after-jev.json

--analyst bắt buộc: `off` = baseline (code hiện tại, đường một vòng lặp cũ —
không Jev, không bàn giao); `jev` = analyst + bàn giao xếp hạng bật.
DB tạm SQLite trong /tmp; HOMEMATCH_DATABASE_URL bị gỡ trong tiến trình này —
không thể ghi lên Neon. Mỗi câu một phiên riêng (trần chi phí phiên vẫn hiệu lực);
câu cần kết quả được seed hồ sơ đã xác nhận bằng đường tất định (không tốn lượt
gọi model) và dừng nếu seed không ra run published có căn.

Số liệu: llm_calls/tokens KHÔNG gồm lần gọi bàn giao (báo riêng handover_calls
và handover_tokens; tổng lần gọi model thực tế = llm_calls + handover_calls).
Provider không báo usage.cost → chi phí ghi "không đo được" (không ghi 0) và
cảnh báo trần phiên 0,05 USD mất tác dụng.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone

# (câu, cần kết quả đã published trước khi hỏi)
SENTENCES = [
    ("gần trường, thoáng, tầm 3 triệu, ở với bạn", False),
    ("phòng nào đáng tiền hơn", True),
    ("vay 20 triệu lãi 10% thì sao", True),
    ("tìm phòng Quận 7 dưới 4 triệu cho 2 người có máy lạnh", False),
    ("phòng gần HUST đi", False),
    ("so sánh căn đầu và căn thứ hai giúp mình", True),
    ("tính giúp mình tổng chi phí căn đầu tiên", True),
    ("còn căn nào rẻ hơn khu này không?", True),
    ("mình muốn ở Hà Nội, gần Hồ Gươm, tầm 5 triệu", False),
    ("mình nên chuẩn bị giấy tờ gì khi thuê phòng?", False),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analyst", required=True, choices=["off", "jev"])
    parser.add_argument("--out", required=True)
    parser.add_argument("--catalog")
    args = parser.parse_args()

    os.environ["HOMEMATCH_LLM_MODE"] = "openai"
    os.environ.setdefault("HOMEMATCH_LLM_API", "chat_completions")
    os.environ["HOMEMATCH_AUTH_MODE"] = "seed"
    os.environ["HOMEMATCH_MATCHING_METHOD"] = "B1"
    os.environ["HOMEMATCH_EMBEDDING_MODE"] = "disabled"
    os.environ["HOMEMATCH_JOBS_INTERVAL_SECONDS"] = "0"
    os.environ["HOMEMATCH_INPUT_ANALYST"] = args.analyst
    tmp = tempfile.mkdtemp(prefix="hn13-measure-")
    os.environ["HOMEMATCH_DB_PATH"] = os.path.join(tmp, "measure.sqlite")
    os.environ.pop("HOMEMATCH_DATABASE_URL", None)  # cứng: DB tạm SQLite, không đụng Neon
    # Backend không tự load .env: catalog phải đặt tường minh (mặc định repo hiện tại).
    os.environ.setdefault("HOMEMATCH_CATALOG_PATH", "data/catalog/rooms.json")
    if args.catalog:
        os.environ["HOMEMATCH_CATALOG_PATH"] = args.catalog

    from backend.app.models import Actor, Profile, Scenario
    from backend.app.service import HomeMatchService

    service = HomeMatchService(os.environ["HOMEMATCH_DB_PATH"])
    renter = Actor(id="renter-a", role="renter")

    # Đếm xem provider có báo usage.cost nào không — không báo thì chi phí
    # "không đo được" và trần phiên 0,05 USD mất tác dụng (báo người chạy).
    cost_state = {"reports": 0}
    original_record_cost = service.budget.record_cost

    def counted_record_cost(session_id, cost_usd):
        if cost_usd:
            cost_state["reports"] += 1
        return original_record_cost(session_id, cost_usd)

    service.budget.record_cost = counted_record_cost  # type: ignore[method-assign]

    rows = []
    for index, (text, needs_results) in enumerate(SENTENCES, 1):
        sid = service.create_session(renter)["session_id"]
        if needs_results:
            service.confirm(sid, renter, Profile(city="TP.HCM", area="Quận 7",
                max_monthly_cost_vnd=6_000_000, max_initial_cash_vnd=8_000_000,
                scenario=Scenario(people=2)),
                service.repo.session(sid)["draft_revision"])
            results = service.results(sid, renter)
            if results["status"] != "published" or not results["results"]:
                print(f"DỪNG: seed câu {index} không ra run published có căn "
                      f"(status={results['status']}). Không tính tiếp.", file=sys.stderr)
                service.close()
                sys.exit(2)
        cost_state["reports"] = 0
        started = time.monotonic()
        reply = service.message(sid, renter, text)
        latency_ms = round((time.monotonic() - started) * 1000)
        usage = reply.get("usage") or {}
        provenance = reply.get("provenance") or {}
        handover_calls = provenance.get("handover_calls") or 0
        if cost_state["reports"] > 0:
            cost_usd: float | str = service.budget.spent_usd(sid)
        else:
            cost_usd = "không đo được"  # provider không báo usage.cost — không ghi 0
        rows.append({
            "index": index,
            "text": text,
            "seeded_results": needs_results,
            "route": (reply.get("input_analysis") or {}).get("route"),
            "clarity": (reply.get("input_analysis") or {}).get("clarity"),
            "decided_by": (reply.get("input_analysis") or {}).get("decided_by"),
            "agents": reply.get("agents"),
            "agent_mode": reply.get("agent_mode"),
            "status": reply.get("status"),
            "llm_calls": usage.get("logical_calls"),          # không gồm bàn giao
            "handover_calls": handover_calls,                  # báo riêng (HN-13)
            "model_calls_total": (usage.get("logical_calls") or 0) + handover_calls,
            "tokens": usage.get("tokens"),                     # không gồm token bàn giao
            "handover_tokens": provenance.get("handover_tokens"),
            "cost_usd": cost_usd,
            "latency_ms": latency_ms,
            "message": (reply.get("message") or "")[:400],
            "questions": reply.get("questions"),
        })
        print(f"[{index:02d}] mode={rows[-1]['agent_mode']} route={rows[-1]['route']} "
              f"agents={rows[-1]['agents']} calls={rows[-1]['model_calls_total']} "
              f"cost={rows[-1]['cost_usd']} {latency_ms} ms")
    service.close()
    measured = [row["cost_usd"] for row in rows if isinstance(row["cost_usd"], (int, float))]
    unmeasured = sum(1 for row in rows if not isinstance(row["cost_usd"], (int, float)))
    payload = {
        "kind": "hn13_measure",
        "model": os.getenv("OPENAI_MODEL"),
        "analyst_mode": args.analyst,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "llm_api": os.getenv("HOMEMATCH_LLM_API"),
        "note_cost": ("provider báo usage.cost" if cost_state["reports"] > 0 or measured
                      else "provider KHÔNG báo usage.cost — chi phí không đo được, "
                           "trần phiên 0,05 USD không có tác dụng"),
        "unmeasured_rows": unmeasured,
        "rows": rows,
    }
    if measured:
        payload["total_cost_usd_measured_rows"] = round(sum(measured), 4)  # type: ignore[arg-type]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    total_calls = sum(row["model_calls_total"] for row in rows)
    print(f"TỔNG: {total_calls} lần gọi model (gồm bàn giao) · "
          f"{unmeasured} câu không đo được chi phí · ghi {args.out}")
    if cost_state["reports"] == 0 and not measured:
        print("CẢNH BÁO: không có usage.cost nào được báo — trần phiên 0,05 USD "
              "không có tác dụng trong lần chạy này.", file=sys.stderr)


if __name__ == "__main__":
    main()
