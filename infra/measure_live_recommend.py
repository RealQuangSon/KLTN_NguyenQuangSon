"""Đo chất lượng ĐỀ XUẤT của agent trên LLM THẬT (eval/fixtures/live_recommend_1118.json).

Khách nói nhu cầu bằng lời; mọi lượt đi qua POST /sessions/{id}/messages của app thật
(TestClient, SQLite tạm, không đụng Neon; model/analyst lấy từ .env). Khi agent hỏi lại
sau lượt cuối, script trả lời bằng chữ như khách (đúng điều khách đã định nói).

    set -a; source .env; set +a
    .venv/bin/python -m infra.measure_live_recommend --label R-1118 --run 1 \
        --catalog .local/chotot/chotot-2026-11-07-5k-r2/catalog.json
    .venv/bin/python -m infra.measure_live_recommend --summarize eval/runs/live-2026-11-18/recommend-R-1118-run*.json

Kiểm bằng code, ĐỘC LẬP với bộ lọc của engine (script tự đọc kho thô theo điều khách
nói; chỉ dùng chung costs.calculate_cost — nguồn tiền duy nhất — và listing_flags):
- reached: kho có căn khớp thì phải ra kết quả; kho không có thì không được công bố căn sai;
- profile: hồ sơ agent xác nhận đúng điều khách nói (thành phố, khu, loại, số người, mức
  tiền và cách hiểu, điểm đến, tiện ích bắt buộc, diện tích, "rẻ nhất");
- rooms_valid: TỪNG căn đề xuất thỏa điều khách nói (khu, loại, mức tiền, sức chứa, tiện
  ích bắt buộc, bán kính, diện tích);
- recall: số căn khớp agent báo (total_matches) = số căn script tự lọc được (chỉ chấm khi
  hồ sơ đúng — hồ sơ sai thì đã trượt ở profile);
- cheapest: khách đòi rẻ nhất thì top là các căn rẻ nhất trong tập khớp;
- cost_consistent: tổng tháng hiển thị = costs.calculate_cost trên tin gốc;
- numbers: số tiền/diện tích agent nói sau "Căn N" là số của chính căn N (hoặc mức trần
  của CHÍNH lượt đó, hiệu số với mức trần/căn khác); câu "N căn khớp" đúng số. Sửa 19/11:
  trước đây mọi lượt bị kiểm theo trần cuối, nên khách hạ mức tiền ở lượt sau thì câu
  "dưới mức 5 triệu" đúng của lượt trước bị chấm sai (chỉ ảnh hưởng kịch bản đổi trần
  giữa các lượt đã công bố — trong bộ này là r12);
- mỗi lượt: không câu lỗi provider, không câu mẫu an toàn, không lộ mã căn/từ nội bộ.
Thông tin (không chấm): số căn khớp rẻ hơn căn rẻ nhất được đề xuất, tỉ lệ có tiện ích
ưu tiên. Script không chấm chất lượng câu chữ — transcript để NGƯỜI chấm.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from infra.measure_live_heldout import CODE_LEAK, PROVIDER_FALLBACK, fold, vnd

AREA_PREFIX = re.compile(r"^(?:quan|huyen|thi xa|tp\.?|thanh pho)\s+")
VND_EXACT = re.compile(r"(\d{1,3}(?:\.\d{3})+)\s*(?:₫|đồng|đ\b|VND)")
VND_TRIEU = re.compile(r"(\d+(?:,\d+)?)\s*(?:triệu|tr\b)", re.I)
AREA_M2 = re.compile(r"(\d+(?:[.,]\d+)?)\s*m(?:²|2)\b")
COUNT_CLAIM = re.compile(r"(\d+)\s*căn\s*(?:khớp|phù hợp|hợp)", re.I)
TYPE_TEXT = {"room": "phòng trọ", "studio": "studio", "apartment": "căn hộ"}


def area_key(value: str | None) -> str:
    return AREA_PREFIX.sub("", fold(value or "").strip())


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    value = (math.sin((p2 - p1) / 2) ** 2
             + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6_371_000 * 2 * math.asin(min(1.0, math.sqrt(value)))


def triệu(amount: int) -> str:
    return f"{amount / 1_000_000:g}".replace(".", ",") + " triệu"


def answer_for(field: str | None, expect: dict, defaults: dict) -> str:
    total = expect.get("scope") == "total"
    if field == "budget_scope":
        return "tính tổng tháng gồm cả điện nước" if total else "chỉ tính tiền thuê phòng"
    if field == "people":
        return f"{expect['people']} người"
    if field == "city":
        return expect["city"]
    if field == "budget_cap":
        return f"{'tổng tháng' if total else 'tiền thuê'} dưới {triệu(expect['budget'])}"
    if field == "room_type":
        return TYPE_TEXT[expect["room_type"]]
    return defaults.get(field or "go") or defaults["go"]


class Checker:
    def __init__(self, catalog_path: str):
        from backend.app.models import Room
        raw = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
        self.rooms = {item["id"]: Room.model_validate(item) for item in raw["rooms"]}
        self.places = {place["id"]: place for place in
                       json.loads(Path("data/places.json").read_text(encoding="utf-8"))["places"]}

    def monthly_total(self, room, scenario) -> int | None:
        from backend.app.costs import calculate_cost
        return calculate_cost(room.quote, scenario, accept_estimated_fees=True).monthly_total_vnd

    def violations(self, room, expect: dict, scenario, radius_m: float | None) -> list[str]:
        """Điều khách nói mà căn không thỏa ([] = thỏa). Đọc tin gốc, không đọc Candidate."""
        from backend.app.catalog import listing_flags
        bad: list[str] = []
        if not room.published or room.available is False:
            bad.append("không còn cho thuê")
        if room.city != expect["city"]:
            bad.append(f"thành phố {room.city}")
        if expect.get("area") and area_key(room.area) != area_key(expect["area"]):
            bad.append(f"khu {room.area}")
        if room.room_type != expect["room_type"]:
            bad.append(f"loại {room.room_type}")
        if expect.get("bedrooms") and room.bedrooms is not None and room.bedrooms < expect["bedrooms"]:
            bad.append(f"{room.bedrooms} phòng ngủ")
        people = expect["people"]
        if room.capacity is not None and room.capacity < people:
            bad.append(f"sức chứa {room.capacity}")
        if people >= 2 and "roommate_wanted" in listing_flags(room):
            bad.append("tin tìm người ở ghép")
        for name in expect.get("must", []):
            if room.amenities.get(name) is not True:
                bad.append(f"thiếu {name}")
        if expect.get("min_area") and room.area_m2 is not None and room.area_m2 < expect["min_area"]:
            bad.append(f"{room.area_m2:g} m²")
        if expect["scope"] == "rent":
            if room.quote.rent_vnd > expect["budget"]:
                bad.append(f"tiền thuê {vnd(room.quote.rent_vnd)}")
        else:
            total = self.monthly_total(room, scenario)
            if total is None or total > expect["budget"]:
                bad.append(f"tổng tháng {vnd(total) if total else 'chưa rõ'}")
        if expect.get("destination"):
            place = self.places[expect["destination"]]
            if room.location_accuracy == "area_only" or room.latitude is None:
                bad.append("không có tọa độ")
            else:
                upper = (haversine(room.latitude, room.longitude, place["latitude"], place["longitude"])
                         + (room.uncertainty_m or 0) + place["uncertainty_m"])
                if radius_m is None or upper > radius_m + 1:
                    bad.append(f"cách {upper / 1000:.1f} km")
        return bad

    def matching(self, expect: dict, scenario, radius_m: float | None) -> list:
        return [room for room in self.rooms.values()
                if room.city == expect["city"]
                and not self.violations(room, expect, scenario, radius_m)]


def check_profile(profile: dict, expect: dict, places: dict) -> dict:
    checks: dict[str, str] = {}

    def verdict(name, ok, got):
        checks[name] = "ok" if ok else f"FAIL: ghi nhận {got!r}"
    verdict("city", profile.get("city") == expect["city"], profile.get("city"))
    if expect.get("area"):
        verdict("area", area_key(profile.get("area")) == area_key(expect["area"]), profile.get("area"))
    verdict("room_type", profile.get("room_type") == expect["room_type"], profile.get("room_type"))
    people = (profile.get("scenario") or {}).get("people")
    verdict("people", people == expect["people"], people)
    cap_field = "max_monthly_cost_vnd" if expect["scope"] == "total" else "max_rent_vnd"
    other = "max_rent_vnd" if expect["scope"] == "total" else "max_monthly_cost_vnd"
    verdict("budget", profile.get(cap_field) == expect["budget"],
            {cap_field: profile.get(cap_field), other: profile.get(other)})
    if expect.get("destination"):
        place = places[expect["destination"]]
        destination = profile.get("destination") or {}
        near = (destination.get("latitude") is not None and haversine(
            destination["latitude"], destination["longitude"], place["latitude"], place["longitude"]) < 500)
        verdict("destination", near, destination.get("label"))
    if expect.get("must"):
        must = set(profile.get("must_amenities") or [])
        verdict("must", set(expect["must"]) <= must, sorted(must))
    if expect.get("prefer"):
        wanted = set(profile.get("preferences") or []) | set(profile.get("must_amenities") or [])
        verdict("prefer", set(expect["prefer"]) <= wanted, sorted(wanted))
    if expect.get("min_area"):
        verdict("min_area", profile.get("min_area_m2") == expect["min_area"], profile.get("min_area_m2"))
    if expect.get("bedrooms"):
        verdict("bedrooms", profile.get("min_bedrooms") == expect["bedrooms"], profile.get("min_bedrooms"))
    if expect.get("cheapest"):
        verdict("cheapest_flag", bool(profile.get("prefer_cheapest")), profile.get("prefer_cheapest"))
    return checks


def room_numbers(item: dict, cap: int | None, others: list[int]) -> set[int]:
    cost = item.get("cost") or {}
    values = {line["amount_vnd"] for line in cost.get("lines") or [] if line.get("amount_vnd")}
    values |= {cost.get(key) for key in ("monthly_total_vnd", "monthly_known_vnd",
                                         "initial_known_vnd", "initial_total_vnd") if cost.get(key)}
    total = cost.get("monthly_total_vnd")
    if cap:
        values.add(cap)
        if total:
            values.add(abs(cap - total))
    if total:
        values |= {abs(total - other) for other in others if other and other != total}
    return {value for value in values if value}


def check_numbers_per_room(message: str, results: list[dict], cap: int | None,
                           total_matches: int | None) -> list[str]:
    """Số sau "Căn N" (tới "Căn" kế tiếp) phải là số của căn N."""
    from backend.app.agent_guard import ROOM_ORDINAL_NUMBER
    problems: list[str] = []
    marks = list(ROOM_ORDINAL_NUMBER.finditer(message))
    totals = [(item.get("cost") or {}).get("monthly_total_vnd") for item in results]
    for index, mark in enumerate(marks):
        position = int(mark.group(1))
        if not 1 <= position <= len(results):
            problems.append(f"nhắc Căn {position} ngoài danh sách {len(results)} căn")
            continue
        segment = message[mark.end(): marks[index + 1].start() if index + 1 < len(marks) else len(message)]
        item = results[position - 1]
        allowed = room_numbers(item, cap, totals)
        for found in VND_EXACT.finditer(segment):
            amount = int(found.group(1).replace(".", ""))
            if amount >= 10_000 and amount not in allowed:
                problems.append(f"Căn {position}: {found.group(0)} không phải số của căn này")
        for found in VND_TRIEU.finditer(segment):
            amount = int(float(found.group(1).replace(",", ".")) * 1_000_000)
            if not any(abs(amount - value) <= 50_000 for value in allowed):
                problems.append(f"Căn {position}: {found.group(0)} không phải số của căn này")
        for found in AREA_M2.finditer(segment):
            size = float(found.group(1).replace(",", "."))
            if item.get("area_m2") is None or abs(size - float(item["area_m2"])) > 0.05:
                problems.append(f"Căn {position}: {found.group(0)} khác diện tích {item.get('area_m2')}")
    for found in COUNT_CLAIM.finditer(message):
        claimed = int(found.group(1))
        if claimed not in {len(results), total_matches}:
            problems.append(f"nói {claimed} căn khớp, thật là {total_matches}")
    return problems


def run(args) -> None:
    if os.environ.get("HOMEMATCH_LLM_MODE") != "openai":
        sys.exit("Cần LLM thật: set -a; source .env; set +a")
    os.environ.setdefault("HOMEMATCH_LLM_API", "chat_completions")
    os.environ["HOMEMATCH_AUTH_MODE"] = "demo"
    os.environ["HOMEMATCH_MATCHING_METHOD"] = "B1"
    os.environ["HOMEMATCH_EMBEDDING_MODE"] = "disabled"
    os.environ["HOMEMATCH_JOBS_INTERVAL_SECONDS"] = "0"
    tmp = tempfile.mkdtemp(prefix="live-recommend-")
    os.environ["HOMEMATCH_DB_PATH"] = os.path.join(tmp, "recommend.sqlite")
    os.environ.pop("HOMEMATCH_DATABASE_URL", None)  # DB tạm SQLite, không đụng Neon
    os.environ["HOMEMATCH_CATALOG_PATH"] = args.catalog

    fixture_bytes = Path(args.fixture).read_bytes()
    fixture = json.loads(fixture_bytes)
    meta = {"kind": "live_recommend", "label": args.label, "run": args.run, "catalog": args.catalog,
            "fixture": args.fixture,
            "fixture_sha256_16": hashlib.sha256(fixture_bytes).hexdigest()[:16],
            "script_sha256_16": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16],
            "model": os.environ.get("OPENAI_MODEL"), "analyst": os.environ.get("HOMEMATCH_INPUT_ANALYST"),
            "measured_at": datetime.now(timezone.utc).isoformat()}

    from fastapi.testclient import TestClient

    from backend.app.agent_loop import SAFE_OUTPUT_REPLY, SAFE_REPLY
    from backend.app.main import create_app
    from backend.app.models import Scenario
    from backend.app.service import HomeMatchService
    from infra.measure_hn13_dialog import INTERNAL_TERMS

    safe_templates = (SAFE_REPLY[:40], SAFE_OUTPUT_REPLY[:40])
    checker = Checker(args.catalog)
    service = HomeMatchService(os.environ["HOMEMATCH_DB_PATH"])
    app = create_app(lambda: service)
    only = set(args.only.split(",")) if args.only else None
    scenarios = []
    started = time.monotonic()
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer demo-renter"}
        for scenario in fixture["scenarios"]:
            if only and scenario["id"] not in only:
                continue
            expect = scenario["expect"]
            sid = client.post("/sessions", headers=headers).json()["session_id"]
            turns: list[dict] = []
            profile: dict = {}

            def send(text: str, scripted: bool) -> dict:
                cost_before = service.budget.spent_usd(sid)
                t0 = time.monotonic()
                response = client.post(f"/sessions/{sid}/messages", headers=headers, json={"text": text})
                latency = round((time.monotonic() - t0) * 1000)
                body = response.json() if response.status_code == 200 else {}
                results = client.get(f"/sessions/{sid}/results", headers=headers).json()
                message = body.get("message") or ""
                text_all = message + " " + " ".join(body.get("questions") or [])
                checks = {"http": "ok" if response.status_code == 200 else f"FAIL: HTTP {response.status_code}",
                          "no_provider_fallback": "FAIL" if PROVIDER_FALLBACK in text_all else "ok",
                          "not_safe_template": ("FAIL: câu mẫu an toàn"
                                                if any(message.startswith(t) for t in safe_templates) else "ok")}
                leak = CODE_LEAK.search(text_all)
                checks["no_code_leak"] = f"FAIL: '{leak.group(0)}'" if leak else "ok"
                internal = INTERNAL_TERMS.search(text_all)
                checks["no_internal_terms"] = f"FAIL: '{internal.group(0)}'" if internal else "ok"
                record = {"text": text, "scripted": scripted, "latency_ms": latency,
                          "status": body.get("status"), "agent_mode": body.get("agent_mode"),
                          "llm_calls": (body.get("usage") or {}).get("logical_calls"),
                          "cost_usd": round(service.budget.spent_usd(sid) - cost_before, 6),
                          "message": message, "questions": body.get("questions"),
                          "chip_field": (body.get("clarification") or {}).get("field"),
                          "chips": [o.get("label") for o in (body.get("clarification") or {}).get("options") or []],
                          "results_status": results.get("status"), "run_id": results.get("run_id"),
                          "result_ids": [item["room_id"] for item in results.get("results") or []],
                          "total_matches": results.get("total_matches"), "checks": checks}
                if body.get("confirmed_profile"):
                    profile.clear()
                    profile.update(body["confirmed_profile"])
                record["_results"] = results.get("results") or []
                # Sửa 19/11: trần của CHÍNH lượt này (khách đổi mức tiền giữa chừng thì câu
                # lượt trước nói "dưới mức 5 triệu" vẫn đúng với lượt đó).
                record["_cap"] = profile.get("max_monthly_cost_vnd") or profile.get("max_rent_vnd")
                turns.append(record)
                return record

            last = None
            for index, text in enumerate(scenario["turns"]):
                last = send(text, True)
                is_last = index == len(scenario["turns"]) - 1
                extra = 0
                while (is_last or scenario.get("settle_each")) and extra < 3 \
                        and last["status"] not in {"published", "no_match"}:
                    last = send(answer_for(last["chip_field"], expect, fixture["default_answers"]), False)
                    extra += 1

            final = client.get(f"/sessions/{sid}/results", headers=headers).json()
            results = final.get("results") or []
            checks: dict[str, str] = {}
            radius = ((profile.get("destination") or {}).get("max_distance_m")) if expect.get("destination") else None
            people_scenario = Scenario.model_validate({**(profile.get("scenario") or {}), "people": expect["people"]})
            matches = checker.matching(expect, people_scenario, radius)
            if results:
                checks["reached"] = "ok"
            else:
                checks["reached"] = ("ok" if not matches else
                                     f"FAIL: không ra kết quả dù kho có {len(matches)} căn khớp")
            profile_checks = check_profile(profile, expect, checker.places) if profile else {
                "profile": "FAIL: chưa xác nhận hồ sơ"}
            checks.update({f"profile.{name}": verdict for name, verdict in profile_checks.items()})
            shown = []
            for position, item in enumerate(results, 1):
                room = checker.rooms.get(item["room_id"])
                bad = (checker.violations(room, expect, people_scenario, radius) if room is not None
                       else ["không có trong kho"])
                engine_total = (item.get("cost") or {}).get("monthly_total_vnd")
                own_total = checker.monthly_total(room, Scenario.model_validate(profile.get("scenario") or {})) \
                    if room is not None and profile else None
                distance = None
                if expect.get("destination") and room is not None and room.latitude is not None:
                    place = checker.places[expect["destination"]]
                    distance = round(haversine(room.latitude, room.longitude, place["latitude"], place["longitude"]))
                shown.append({"position": position, "room_id": item["room_id"], "title": item.get("title"),
                              "area": item.get("area"), "room_type": item.get("room_type"),
                              "rent_vnd": room.quote.rent_vnd if room else None,
                              "monthly_total_vnd": engine_total, "own_total_vnd": own_total,
                              "estimated": any(str(v).startswith("fee_assumed") for v in item.get("verification") or []),
                              "area_m2": item.get("area_m2"), "capacity": room.capacity if room else None,
                              "distance_m": distance, "score": item.get("score"),
                              "components": item.get("components"), "violations": bad})
            invalid = [f"Căn {row['position']}: {', '.join(row['violations'])}" for row in shown if row["violations"]]
            checks["rooms_valid"] = "ok" if not invalid else "FAIL: " + "; ".join(invalid)
            mismatch = [f"Căn {row['position']}: {row['monthly_total_vnd']} ≠ {row['own_total_vnd']}"
                        for row in shown if row["own_total_vnd"] != row["monthly_total_vnd"]]
            checks["cost_consistent"] = "ok" if not mismatch else "FAIL: " + "; ".join(mismatch)
            profile_ok = all(verdict == "ok" for verdict in profile_checks.values())
            total_matches = final.get("total_matches")
            if not results:
                checks["recall"] = "skip: không có kết quả"
            elif not profile_ok:
                checks["recall"] = "skip: hồ sơ khác điều khách nói"
            else:
                checks["recall"] = ("ok" if total_matches == len(matches)
                                    else f"FAIL: agent báo {total_matches} căn, kho có {len(matches)} căn khớp")

            def key_total(room):
                if expect["scope"] == "rent":
                    return room.quote.rent_vnd
                return checker.monthly_total(room, people_scenario)
            match_totals = sorted(key_total(room) for room in matches)
            shown_totals = [row["rent_vnd"] if expect["scope"] == "rent" else row["own_total_vnd"] for row in shown]
            if expect.get("cheapest") and results:
                wanted = match_totals[:len(shown_totals)]
                checks["cheapest"] = ("ok" if sorted(shown_totals) == wanted
                                      else f"FAIL: đề xuất {sorted(shown_totals)}, rẻ nhất trong kho {wanted}")
            number_problems = []
            for record in turns:
                if record["status"] == "published" and record["_results"]:
                    number_problems += check_numbers_per_room(record["message"] or "", record["_results"],
                                                              record["_cap"],
                                                              record["total_matches"])
            checks["numbers"] = "ok" if not number_problems else "FAIL: " + "; ".join(number_problems)
            for record in turns:
                for name, verdict in record["checks"].items():
                    if verdict != "ok":
                        checks.setdefault(f"turn.{name}", verdict)
                record.pop("_results", None)
                record.pop("_cap", None)
            cheapest_shown = min((value for value in shown_totals if value is not None), default=None)
            info = {"matches_in_catalog": len(matches), "total_matches": total_matches,
                    "cheaper_hidden": (sum(1 for value in match_totals if value < cheapest_shown)
                                       if cheapest_shown is not None else None),
                    "radius_m": radius}
            if expect.get("prefer"):
                info["prefer_shown"] = sum(1 for row in results
                                           if all(checker.rooms[row["room_id"]].amenities.get(n) is True
                                                  for n in expect["prefer"]))
                info["prefer_in_matches"] = sum(1 for room in matches
                                                if all(room.amenities.get(n) is True for n in expect["prefer"]))
            failed = [name for name, verdict in checks.items() if verdict.startswith("FAIL")]
            scenarios.append({"id": scenario["id"], "expect": expect, "passed": not failed, "failed": failed,
                              "checks": checks, "info": info, "profile": profile, "shown": shown, "turns": turns})
            print(f"{scenario['id']:5} {'ok' if not failed else 'FAIL ' + ', '.join(failed)}", flush=True)
    meta["elapsed_s"] = round(time.monotonic() - started, 1)
    meta["total_cost_usd"] = round(sum(record.get("cost_usd") or 0 for item in scenarios
                                       for record in item["turns"]), 4)
    payload = {**meta, "scenarios": scenarios}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"recommend-{args.label}-run{args.run}"
    (out / f"{stem}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    export_transcript(payload, out / f"{stem}-transcript.md")
    passed = sum(1 for item in scenarios if item["passed"])
    print(f"[{stem}] {passed}/{len(scenarios)} kịch bản đạt · {meta['total_cost_usd']} USD · {meta['elapsed_s']}s")


def export_transcript(payload: dict, path: Path) -> None:
    lines = [f"# Đo đề xuất trên LLM thật — {payload['label']} lần {payload['run']}",
             f"Model `{payload['model']}` · analyst {payload['analyst']} · kho `{payload['catalog']}` · "
             f"bộ kịch bản {payload['fixture_sha256_16']} · script {payload['script_sha256_16']} · "
             f"{payload['total_cost_usd']} USD · {payload['elapsed_s']} s", ""]
    for item in payload["scenarios"]:
        lines.append(f"## {item['id']} — {'ĐẠT' if item['passed'] else 'KHÔNG ĐẠT'}")
        lines.append(f"Khách muốn: `{json.dumps(item['expect'], ensure_ascii=False)}`")
        for record in item["turns"]:
            who = "Khách" if record["scripted"] else "Khách (trả lời câu hỏi)"
            lines.append(f"- **{who}**: {record['text']}")
            lines.append(f"  - `status={record['status']} mode={record['agent_mode']} calls={record['llm_calls']} "
                         f"{record['latency_ms']}ms`")
            lines.append(f"  - **Trợ lý**: {record['message']}")
            if record.get("chips"):
                lines.append(f"  - Nút [{record['chip_field']}]: " + " | ".join(record["chips"]))
        profile = item["profile"]
        if profile:
            keys = ("city", "area", "room_type", "max_monthly_cost_vnd", "max_rent_vnd", "min_rent_vnd",
                    "must_amenities", "preferences", "min_area_m2", "min_bedrooms", "prefer_cheapest",
                    "budget_approx")
            summary = {key: profile.get(key) for key in keys if profile.get(key) not in (None, [], False)}
            summary["people"] = (profile.get("scenario") or {}).get("people")
            if profile.get("destination"):
                summary["destination"] = (f"{profile['destination'].get('label')} · "
                                          f"{profile['destination'].get('max_distance_m')} m")
            lines.append(f"- Hồ sơ đã xác nhận: `{json.dumps(summary, ensure_ascii=False)}`")
        info = item["info"]
        lines.append(f"- Kho có **{info['matches_in_catalog']}** căn khớp điều khách nói; agent báo "
                     f"{info['total_matches']}; căn khớp rẻ hơn căn rẻ nhất được đề xuất: {info['cheaper_hidden']}"
                     + (f"; có tiện ích ưu tiên: {info['prefer_shown']}/{len(item['shown'])} đề xuất, "
                        f"{info['prefer_in_matches']}/{info['matches_in_catalog']} trong kho" if "prefer_shown" in info else ""))
        if item["shown"]:
            lines.append("")
            lines.append("| Căn | Tin | Khu | Thuê | Tổng tháng | m² | Sức chứa | Cách | Điểm | Vi phạm |")
            lines.append("|---|---|---|---|---|---|---|---|---|---|")
            for row in item["shown"]:
                total = (vnd(row["monthly_total_vnd"]) + (" (ước tính)" if row["estimated"] else "")
                         if row["monthly_total_vnd"] else "chưa rõ")
                title = (row["title"] or "").replace("|", "/")[:60]
                lines.append(f"| {row['position']} | {title} | {row['area']} | "
                             f"{vnd(row['rent_vnd']) if row['rent_vnd'] else '?'} | {total} | "
                             f"{row['area_m2'] if row['area_m2'] is not None else 'chưa rõ'} | "
                             f"{row['capacity'] if row['capacity'] is not None else 'chưa rõ'} | "
                             f"{(str(round(row['distance_m'] / 1000, 2)) + ' km') if row['distance_m'] is not None else ''} | "
                             f"{row['score']} | {', '.join(row['violations']) or '—'} |")
            lines.append("")
        bad = {name: verdict for name, verdict in item["checks"].items() if not verdict.startswith("ok")}
        if bad:
            lines.append("- Tiêu chí: " + "; ".join(f"{name} → {verdict}" for name, verdict in bad.items()))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def summarize(paths: list[str]) -> None:
    runs = [json.loads(Path(path).read_text(encoding="utf-8")) for path in paths]
    print(f"{len(runs)} lần · bộ kịch bản {sorted({r['fixture_sha256_16'] for r in runs})} · "
          f"script {sorted({r['script_sha256_16'] for r in runs})} · "
          f"{round(sum(r['total_cost_usd'] for r in runs), 4)} USD")
    items = [item for run_payload in runs for item in run_payload["scenarios"]]
    print(f"Kịch bản đạt: {sum(i['passed'] for i in items)}/{len(items)}")
    counts: dict[str, list[int]] = {}
    for item in items:
        for name, verdict in item["checks"].items():
            bucket = counts.setdefault(name, [0, 0, 0])
            bucket[0 if verdict == "ok" else (1 if verdict.startswith("FAIL") else 2)] += 1
    print("Tiêu chí (đạt / không đạt / bỏ qua):")
    for name, (ok, fail, skip) in sorted(counts.items(), key=lambda kv: (-kv[1][1], kv[0])):
        print(f"  {name:26} {ok:4} {fail:4} {skip:4}")
    shown = [row for item in items for row in item["shown"]]
    print(f"Căn được đề xuất: {len(shown)}, vi phạm điều khách nói: {sum(1 for r in shown if r['violations'])}")
    by_id: dict[str, list[dict]] = {}
    for item in items:
        by_id.setdefault(item["id"], []).append(item)
    print("Kịch bản không đạt (số lần / tổng — tiêu chí):")
    for scenario_id, group in by_id.items():
        fails = [item for item in group if not item["passed"]]
        if fails:
            print(f"  {scenario_id:5} {len(fails)}/{len(group)} — "
                  f"{'; '.join(sorted({name for item in fails for name in item['failed']}))}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label")
    parser.add_argument("--run", type=int, default=1)
    parser.add_argument("--catalog")
    parser.add_argument("--fixture", default="eval/fixtures/live_recommend_1118.json")
    parser.add_argument("--out", default="eval/runs/live-2026-11-18")
    parser.add_argument("--only", default=None, help="chỉ chạy các id (phẩy ngăn cách)")
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
