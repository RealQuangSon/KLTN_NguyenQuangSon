"""HN-13.2 — đo hội thoại nhiều lượt (hỏi lại + chip) trước/sau khi sửa.

Chạy (backend không tự nạp .env — nạp trong shell; KHÔNG nạp .local/neon.env):

    set -a; source .env; set +a
    .venv/bin/python -m infra.measure_hn13_dialog --label before \
        --catalog data/catalog/rooms.json --out eval/runs/live-2026-11-07

Lượt "chip" mô phỏng đúng FE (RenterWorkspace.applyClarification + hiệu ứng tự
xác nhận): PATCH /sessions/{id}/draft (source=clarify) rồi POST /sessions/{id}/confirm
với profile dựng từ nháp khi đủ dữ liệu. Mọi lượt chữ đi qua
POST /sessions/{id}/messages (kiểm response_model thật).

Tiêu chí bằng code: hỏi lại điều đã biết, chip lệch field đang chờ, số căn chip
khớp kho (dựng hồ sơ tạm từ interpretation rồi rank lại — chip chưa được áp),
từ nội bộ, câu bị cắt (finish_reason=length), question_without_chip,
chạm question_limit, lượt bàn giao xếp hạng. Transcript markdown xuất để
NGƯỜI chấm định tính — script không tự chấm chất lượng.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

INTERNAL_TERMS = re.compile(
    r"hệ thống|he thong|danh mục|danh muc|\btool\b|công cụ|cong cu|\bfield\b"
    r"|lựa chọn cần xác nhận|lua chon can xac nhan|\bclarify\b|workspace"
    r"|điểm mốc|diem moc|xác thực|xac thuc|theo nháp|theo nhap"
    r"|không làm thay đổi đáng kể|khong lam thay doi dang ke"
    # HN-13.3.5: field snake_case và định dạng số kiểu Anh
    r"|[a-z][a-z_]*_vnd|area_m2|first_rent|one_time|deposit_vnd|room_id"
    r"|\d{1,3}(?:,\d{3})+|\d+\.\d+\s*m²|\bVND\b", re.I)
# HN-13.3.3: LIỆT KÊ TỪ CODE — mọi câu thay thế cố định phải được đếm là câu cụt.
# Nguồn: agent_loop.SAFE_REPLY, agent_loop.check_numbers, agent_loop.SAFE_OUTPUT_REPLY,
# service._limit_clarification_response (form), agent_guard.provider_fallback_reply,
# agent_guard.quarantine_reply, agent_guard.viewing_prep_missing_room_reply.
SAFE_MARKERS = (
    "Mình xử lý chưa trọn vẹn",
    "Mình vừa kiểm tra nhu cầu của bạn qua các bước bên dưới",
    "Mình vừa rà lại câu trả lời cho an toàn",
    "Bạn điền các mục còn thiếu",
    "Trợ lý AI tạm chưa xử lý được tin nhắn này",
    "Tin nhắn có dấu hiệu chứa chỉ đạo nhúng",
    "Chưa chuẩn bị được yêu cầu lịch xem",
)
# Câu KHÔNG có phòng: chỉ được phép khi cả count lẫn held bằng 0 (HN-13.3).
NO_ROOM_CLAIM = re.compile(r"chưa có phòng|không có phòng|chưa công bố|chưa tìm thấy căn", re.I)


class _Completions:
    def __init__(self, inner, sink: list):
        self._inner = inner
        self._sink = sink

    def create(self, **kwargs):
        completion = self._inner.create(**kwargs)
        self._record(completion)
        return completion

    def parse(self, **kwargs):
        completion = self._inner.parse(**kwargs)
        self._record(completion)
        return completion

    def _record(self, completion):
        try:
            self._sink.append(str(getattr(completion.choices[0], "finish_reason", None)))
        except Exception:
            self._sink.append("unreadable")

    def __getattr__(self, name):
        return getattr(self._inner, name)


class FinishReasonProbe:
    """Bọc client model để ghi finish_reason từng lần gọi (không đổi app code)."""

    def __init__(self, inner, sink: list):
        self._inner = inner
        self.chat = SimpleNamespace(completions=_Completions(inner.chat.completions, sink))

    def __getattr__(self, name):
        return getattr(self._inner, name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="before|after|<tên cấu hình>")
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--out", default="eval/runs/live-2026-11-07")
    parser.add_argument("--analyst", default="jev", choices=["off", "rules", "jev"])
    parser.add_argument("--reasoning", default=None, choices=["low", "medium"])
    parser.add_argument("--decision-mode", default=None, choices=["rules", "jev"])
    parser.add_argument("--catalog-name", default=None)
    args = parser.parse_args()

    catalog_name = args.catalog_name or Path(args.catalog).parent.name
    os.environ["HOMEMATCH_LLM_MODE"] = "openai"
    os.environ.setdefault("HOMEMATCH_LLM_API", "chat_completions")
    os.environ["HOMEMATCH_AUTH_MODE"] = "demo"
    os.environ["HOMEMATCH_MATCHING_METHOD"] = "B1"
    os.environ["HOMEMATCH_EMBEDDING_MODE"] = "disabled"
    os.environ["HOMEMATCH_JOBS_INTERVAL_SECONDS"] = "0"
    os.environ["HOMEMATCH_INPUT_ANALYST"] = args.analyst
    if args.reasoning:
        os.environ["HOMEMATCH_AGENT_REASONING"] = args.reasoning
    if args.decision_mode:
        os.environ["HOMEMATCH_DECISION_MODE"] = args.decision_mode
    tmp = tempfile.mkdtemp(prefix="hn13-dialog-")
    os.environ["HOMEMATCH_DB_PATH"] = os.path.join(tmp, "dialog.sqlite")
    os.environ.pop("HOMEMATCH_DATABASE_URL", None)  # cứng: DB tạm SQLite, không đụng Neon
    os.environ["HOMEMATCH_CATALOG_PATH"] = args.catalog

    script_hash = __import__("hashlib").sha256(Path(__file__).read_bytes()).hexdigest()[:16]
    fixture = json.loads(Path("eval/fixtures/hn13_dialogs.json").read_text(encoding="utf-8"))

    from fastapi.testclient import TestClient

    from backend.app.main import create_app
    from backend.app.models import Actor
    from backend.app.service import HomeMatchService

    service = HomeMatchService(os.environ["HOMEMATCH_DB_PATH"])
    finish_sink: list[str] = []
    service.interpreter.client = FinishReasonProbe(service.interpreter.client, finish_sink)
    app = create_app(lambda: service)
    renter = Actor(id="renter-a", role="renter")

    conversations = []
    counters: dict = {
        "turns": 0, "asked_fields": [], "asked_already_known": [], "chips": 0,
        "chip_field_mismatch": [], "chip_count_mismatch": [], "internal_terms": [],
        "truncated": [], "question_without_chip": [], "question_limit": [],
        "handover_turns": [], "chip_fallback_text": [], "errors": [], "confirmed_runs": 0,
        # HN-13.3: tiêu chí bổ sung theo yêu cầu người dùng (đóng băng TRƯỚC khi chạy).
        "safe_reply_turns": [], "no_room_while_held": [], "chip_click_errors": [],
        "money_chip_turns": [], "call_limit_turns": [], "latencies_ms": [],
        "claimed_vs_actual": [],
        # HN-13.3-A7: ba tiêu chí bổ sung (đóng băng TRƯỚC khi chạy).
        "reenter_known_turns": [], "verbatim_repeat_turns": [], "money_mismatch": [],
        # v2: checker claimed_vs_actual BẢN CŨ (không xét trần) để báo cạnh bản mới.
        "claimed_vs_actual_old": [], "loan_principal_mismatch": [],
        # B (D-12): câu mời/chữ "bị giữ" không được còn trong luồng người dùng.
        "estimate_invite_turns": [],
    }
    started = time.monotonic()
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer demo-renter-a"}
        for conversation in fixture["conversations"]:
            sid = client.post("/sessions", headers=headers).json()["session_id"]
            pending_field = None
            cost_prev = 0.0
            records: list[dict] = []
            for index, turn in enumerate(conversation["turns"], 1):
                record: dict = {"turn": index, "kind": "chip" if turn.get("chip") is not None else "text"}
                started_at = time.monotonic()
                turn_text = turn.get("text")
                if record["kind"] == "chip":
                    # Lượt bấm chip: phải có chip từ lượt trước; không thì lùi gõ chữ.
                    options = ((records[-1] if records else {}).get("clarification") or {}).get("options") or []
                    if not options:
                        counters["chip_fallback_text"].append(f"{conversation['id']}#{index}")
                        record["kind"] = "chip→text"
                        turn_text = "chốt luôn giúp mình"
                        response = client.post(f"/sessions/{sid}/messages", headers=headers,
                                               json={"text": turn_text})
                    else:
                        option = options[min(int(turn["chip"]), len(options) - 1)]
                        record["chip"] = option["label"]
                        session = client.get(f"/sessions/{sid}", headers=headers).json()
                        patch = client.patch(f"/sessions/{sid}/draft", headers=headers, json={
                            "expected_draft_revision": session["draft_revision"],
                            "set": (option.get("patch") or {}).get("set") or {},
                            "clear_fields": [], "remove_preferences": [], "source": "clarify"})
                        if patch.status_code != 200:
                            record["error"] = f"PATCH {patch.status_code}: {patch.text[:120]}"
                            counters["errors"].append(f"{conversation['id']}#{index}")
                            counters["chip_click_errors"].append(f"{conversation['id']}#{index}")
                            records.append(record)
                            continue
                        # Hiệu ứng tự xác nhận của FE: đủ dữ liệu tối thiểu thì POST confirm.
                        # HN-13.3 (sửa sau khi bắt 409): PATCH đã tăng revision — phải dùng
                        # revision MỚI từ phản hồi PATCH, không dùng revision cũ trước PATCH.
                        new_revision = patch.json().get("draft_revision", session["draft_revision"])
                        profile = service._profile_from_draft(sid)
                        if profile is not None:
                            confirm = client.post(f"/sessions/{sid}/confirm", headers=headers, json={
                                "expected_draft_revision": new_revision,
                                "profile": profile.model_dump(mode="json")})
                            record["confirm"] = confirm.json().get("status") \
                                if confirm.status_code == 200 else f"HTTP {confirm.status_code}"
                            if confirm.status_code != 200:
                                counters["chip_click_errors"].append(
                                    f"{conversation['id']}#{index}: confirm {confirm.status_code}")
                            if record["confirm"] in {"published", "no_match", "needs_verification"}:
                                counters["confirmed_runs"] += 1
                        record["message"] = "(khách bấm chip — không có câu trả lời mới)"
                        record["latency_ms"] = round((time.monotonic() - started_at) * 1000)
                        record["cost_usd"] = round(service.budget.spent_usd(sid) - cost_prev, 6)
                        cost_prev = service.budget.spent_usd(sid)
                        records.append(record)
                        counters["turns"] += 1
                        pending_field = None  # chip đã trả lời câu hỏi đang chờ
                        continue
                else:
                    response = client.post(f"/sessions/{sid}/messages", headers=headers,
                                           json={"text": turn_text})
                # --- lượt chữ: ghi số đo ---
                if response.status_code != 200:
                    record["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
                    counters["errors"].append(f"{conversation['id']}#{index}")
                    records.append(record)
                    continue
                counters["turns"] += 1
                body = response.json()
                clarification = body.get("clarification") or {}
                options = clarification.get("options") or []
                cost_now = service.budget.spent_usd(sid)
                record.update({
                    "text": turn_text,
                    "route": (body.get("input_analysis") or {}).get("route"),
                    "clarity": (body.get("input_analysis") or {}).get("clarity"),
                    "decided_by": (body.get("input_analysis") or {}).get("decided_by"),
                    "agents": body.get("agents"),
                    "agent_mode": body.get("agent_mode"),
                    "status": body.get("status"),
                    "message": body.get("message"),
                    "questions": body.get("questions"),
                    "clarification": clarification or None,
                    "field": clarification.get("field"),
                    "llm_calls": (body.get("usage") or {}).get("logical_calls"),
                    "handover_calls": (body.get("provenance") or {}).get("handover_calls"),
                    "cost_usd": round(cost_now - cost_prev, 6),
                    "latency_ms": round((time.monotonic() - started_at) * 1000),
                    "draft": body.get("draft"),
                    "pending_field_before": pending_field,
                })
                cost_prev = cost_now
                # --- tiêu chí bằng code ---
                draft = body.get("draft") or {}
                field = clarification.get("field")
                if field:
                    counters["asked_fields"].append(field)
                    tracked = "destination" if field == "destination_radius" else field
                    known = (draft.get("field_status", {}).get(tracked) == "confirmed"
                            or str(draft.get("evidence_ref", {}).get(tracked, "")).startswith("clarify:")
                            or (field == "budget_scope" and draft.get("budget_scope"))
                            or (field == "people" and draft.get("people"))
                            or (field == "room_type" and draft.get("room_type"))
                            or (field == "area" and draft.get("area")))
                    if known:
                        counters["asked_already_known"].append(f"{conversation['id']}#{index}:{field}")
                    if pending_field and field != pending_field:
                        # HN-13.2: không tính lệch nếu CÂU KHÁCH đã trả lời field
                        # đang chờ (giá trị đã vào nháp) — hỏi tiếp field mới là đúng.
                        tracked = {"city": "city", "budget_cap": "budget_hint_vnd",
                                   "budget_scope": "budget_scope", "area": "area",
                                   "room_type": "room_type", "people": "people"}
                        key = tracked.get(pending_field)
                        answered = bool(key) and (
                            draft.get("destination") is not None
                            if pending_field in {"destination", "destination_radius"}
                            else draft.get(key) is not None)
                        if not answered:
                            counters["chip_field_mismatch"].append(
                                f"{conversation['id']}#{index}: chờ {pending_field}, nhận {field}")
                    counters["chips"] += len(options)
                    confirmed_profile = body.get("confirmed_profile")
                    for option in options:
                        label = option.get("label") or ""
                        if INTERNAL_TERMS.search(label):
                            counters["internal_terms"].append(f"{conversation['id']}#{index}: chip '{label[:60]}'")
                        if option.get("count") is not None:
                            recount = _recount(service, draft, option,
                                               json.dumps(confirmed_profile) if confirmed_profile else None)
                            if recount is not None and recount != option["count"]:
                                counters["chip_count_mismatch"].append(
                                    f"{conversation['id']}#{index}: chip {option['count']} ≠ kho {recount}")
                question_text = " ".join(body.get("questions") or [])
                message = body.get("message") or ""
                if clarification.get("question"):
                    if INTERNAL_TERMS.search(clarification["question"]):
                        counters["internal_terms"].append(f"{conversation['id']}#{index}: câu hỏi chip")
                elif ("?" in message or "?" in question_text) and not re.search(
                        r"Có \d+ tin khớp|Chưa có căn nào khớp|Một số tin khớp|Chưa công bố",
                        message):
                    # Câu chốt template (đủ chip "Chấp nhận dữ liệu ước tính" ở
                    # suggested_prompts) không phải câu hỏi tự viết của model.
                    counters["question_without_chip"].append(f"{conversation['id']}#{index}")
                    if INTERNAL_TERMS.search(message + " " + question_text):
                        counters["internal_terms"].append(f"{conversation['id']}#{index}: câu hỏi tự do")
                if any("question_without_chip" in step for step in body.get("steps") or []
                       ) and f"{conversation['id']}#{index}" not in counters["question_without_chip"]:
                    counters["question_without_chip"].append(f"{conversation['id']}#{index}")
                if any("question_limit" in step for step in body.get("steps") or []):
                    counters["question_limit"].append(f"{conversation['id']}#{index}")
                # HN-13.3.6: lưu steps từng lượt để báo bước chậm nhất + tool lặp lại.
                try:
                    last_turn = service.repo.db.execute(
                        "SELECT id FROM hm_agent_turns WHERE session_id=? ORDER BY started_at DESC LIMIT 1",
                        (sid,)).fetchone()
                    if last_turn:
                        step_rows = service.repo.db.execute(
                            "SELECT kind, name, duration_ms, ok FROM hm_agent_steps "
                            "WHERE turn_row_id=? ORDER BY seq", (last_turn["id"],)).fetchall()
                        record["steps_detail"] = [
                            {"kind": s["kind"], "name": s["name"],
                             "duration_ms": s["duration_ms"], "ok": s["ok"]} for s in step_rows]
                except Exception:
                    pass
                if (body.get("provenance") or {}).get("handover_calls"):
                    counters["handover_turns"].append(f"{conversation['id']}#{index}")
                if finish_sink and finish_sink[-1] == "length":
                    counters["truncated"].append(f"{conversation['id']}#{index}")
                counters["latencies_ms"].append(record["latency_ms"])
                message_text = body.get("message") or ""
                # A7-i: số tiền trong câu (mức trần/gốc vay) phải khớp nháp.
                draft_now = body.get("draft") or {}
                hint_now = draft_now.get("budget_hint_vnd")
                if hint_now:
                    vn_hint = f"{hint_now:,}".replace(",", ".")
                    # Bản mới (v2): chỉ kiểm số đi kèm từ TRẦN/MỨC — giá từng căn
                    # liệt kê từ current_results không phải tuyên bố trần.
                    for money in re.findall(
                            r"(?:trần|ngân sách|tối đa)[^\d]{0,14}"
                            r"(\d{1,3}(?:[.]\d{3})+|\d+(?:[.,]\d+)?\s*(?:triệu|tr\b))",
                            message_text, re.I):
                        try:
                            if re.search(r"triệu|tr\b", money):
                                digits = int(round(float(re.sub(r"[^\d,.]", "", money).replace(",", ".")) * 1_000_000))
                            else:
                                digits = int(money.replace(".", ""))
                        except ValueError:
                            continue
                        if digits != hint_now:
                            counters["money_mismatch"].append(
                                f"{conversation['id']}#{index}: nói trần {money}, nháp {vn_hint}")
                # A7-i (gốc vay): câu khách nêu "vay N triệu" → thẻ phải có đúng gốc N.
                loan_match = re.search(r"vay\s+(\d+(?:[.,]\d+)?)\s*(?:triệu|tr\b)", turn_text or "", re.I)
                if loan_match and body.get("simulation"):
                    expected_principal = int(float(loan_match.group(1).replace(",", ".")) * 1_000_000)
                    if (body["simulation"].get("scenario") or {}).get("principal_vnd") != expected_principal:
                        counters["loan_principal_mismatch"].append(
                            f"{conversation['id']}#{index}: thẻ {(body['simulation'].get('scenario') or {}).get('principal_vnd')}, khách nêu {expected_principal}")
                # A7-ii: câu bảo khách nhập lại điều nháp đã có.
                draft_complete = draft_now.get("city") and draft_now.get("budget_hint_vnd")
                if draft_complete and re.search(r"điền|nhập (?:lại|vào)|gửi lại", message_text):
                    counters["reenter_known_turns"].append(f"{conversation['id']}#{index}")
                # A7-iii: câu trả lời trùng nguyên văn lượt trợ lý liền trước.
                prev = records[-1].get("message") if records else None
                if message_text and prev and message_text == prev:
                    counters["verbatim_repeat_turns"].append(f"{conversation['id']}#{index}")
                if re.search(r"Chấp nhận dữ liệu ước tính|bị giữ|đang chờ xác minh", message_text + " " + question_text) \
                        or any(re.search(r"Chấp nhận dữ liệu ước tính", (option.get("label") or ""))
                               for option in options):
                    counters["estimate_invite_turns"].append(f"{conversation['id']}#{index}")
                if any(marker in message_text for marker in SAFE_MARKERS):
                    counters["safe_reply_turns"].append(f"{conversation['id']}#{index}")
                if (record.get("llm_calls") or 0) >= 4:
                    counters["call_limit_turns"].append(f"{conversation['id']}#{index}")
                if any((option.get("text") or "").startswith(("Tổng tháng dưới ", "Tiền thuê dưới "))
                       for option in options) or any("Tổng tháng dưới " in (option.get("label") or "")
                                                     or "Tiền thuê dưới " in (option.get("label") or "")
                                                     for option in options):
                    counters["money_chip_turns"].append(f"{conversation['id']}#{index}")
                # HN-13.3.2: mọi số "N tin" trong câu trả lời đối chiếu rank thật.
                for claimed in re.findall(r"(\d+) (?:tin|căn) (?:khớp|phù hợp|xếp đầu)", message_text):
                    actual = _actual_counts(service, body.get("draft"), body.get("confirmed_profile"))
                    n = int(claimed)
                    valid = {actual["eligible"], actual["estimate_only"], actual["held"],
                             actual.get("shown"), actual.get("exact"),
                             actual.get("capped_eligible"), actual.get("capped_estimate_only"),
                             actual.get("capped_shown")}
                    if n not in {actual["eligible"], actual["estimate_only"], actual["held"]}:
                        counters["claimed_vs_actual_old"].append(
                            f"{conversation['id']}#{index}: nói {n}, thật {actual}")
                    if n not in valid:
                        counters["claimed_vs_actual"].append(
                            f"{conversation['id']}#{index}: nói {n}, thật {actual}")
                no_room_hit = (NO_ROOM_CLAIM.search(message_text) or
                               any(NO_ROOM_CLAIM.search(question or "")
                                   for question in body.get("questions") or []))
                # HN-13.3 (tinh chỉnh tiêu chí, KHÔNG đóng băng sau khi thấy kết quả —
                # báo cả hai phiên bản trong báo cáo): câu chốt template khi còn tin
                # bị giữ NÓI ĐÚNG SỐ ("Có N tin khớp...") — chỉ tính là sai khi câu
                # KHÔNG nêu số tin bị giữ nào.
                if no_room_hit and not re.search(r"\d+ tin (?:khớp|phù hợp)", message_text):
                    # HN-13.3-A7 (v3): held theo TRẦN của nháp — "còn N tin" chỉ sai
                    # khi pool ước tính CÓ trần vẫn > 0.
                    actual = _actual_counts(service, body.get("draft"),
                                            body.get("confirmed_profile"))
                    held_now = actual.get("capped_estimate_only", actual.get("held", 0))
                    if held_now > 0:
                        counters["no_room_while_held"].append(
                            f"{conversation['id']}#{index}: held={held_now}")
                pending_field = field if (clarification.get("question") and options) else None
                records.append(record)
            conversations.append({"id": conversation["id"], "name": conversation["name"],
                                  "turns": records})
    elapsed = time.monotonic() - started
    service.close()

    measured_cost = sum((record.get("cost_usd") or 0)
                        for conversation in conversations for record in conversation["turns"]
                        if isinstance(record.get("cost_usd"), (int, float)))
    payload = {
        "kind": "hn13_dialog_measure", "label": args.label, "catalog": str(args.catalog),
        "catalog_name": catalog_name, "analyst": args.analyst,
        "reasoning": args.reasoning or os.getenv("HOMEMATCH_AGENT_REASONING", "low"),
        "decision_mode": args.decision_mode or os.getenv("HOMEMATCH_DECISION_MODE", "rules"),
        "model": os.getenv("OPENAI_MODEL"), "runs": 1, "script_sha256_16": script_hash,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(elapsed, 1), "turns": counters["turns"],
        "total_cost_usd": round(measured_cost, 4),
        "criteria": {
            "asked_already_known": counters["asked_already_known"],
            "chip_field_mismatch": counters["chip_field_mismatch"],
            "chip_count_mismatch": counters["chip_count_mismatch"],
            "internal_terms": counters["internal_terms"],
            "truncated_finish_reason_length": counters["truncated"],
            "question_without_chip": counters["question_without_chip"],
            "question_limit_hits": counters["question_limit"],
            "handover_turns": counters["handover_turns"],
                "chip_fallback_text": counters["chip_fallback_text"],
            "confirmed_runs": counters["confirmed_runs"],
            "safe_reply_turns": counters["safe_reply_turns"],
            "claimed_vs_actual": counters["claimed_vs_actual"],
            "reenter_known_turns": counters["reenter_known_turns"],
            "verbatim_repeat_turns": counters["verbatim_repeat_turns"],
            "money_mismatch": counters["money_mismatch"],
            "claimed_vs_actual_old": counters["claimed_vs_actual_old"],
            "estimate_invite_turns": counters["estimate_invite_turns"],
            "loan_principal_mismatch": counters["loan_principal_mismatch"],
            "no_room_while_held": counters["no_room_while_held"],
            "chip_click_errors": counters["chip_click_errors"],
            "money_chip_turns": counters["money_chip_turns"],
            "call_limit_turns": counters["call_limit_turns"],
            "latency_p50_ms": (sorted(counters["latencies_ms"])[len(counters["latencies_ms"]) // 2]
                               if counters["latencies_ms"] else None),
            "latency_p95_ms": (sorted(counters["latencies_ms"])[min(len(counters["latencies_ms"]) - 1, int(len(counters["latencies_ms"]) * 0.95))]
                               if counters["latencies_ms"] else None),
            "errors": counters["errors"],
            "asked_fields": counters["asked_fields"],
        },
        "conversations": conversations,
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"hn13-dialog-{catalog_name}-{args.label}.json"
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _export_transcript(payload, out_dir / f"hn13-dialog-{catalog_name}-{args.label}-transcript.md")
    print(f"[{catalog_name}/{args.label}] {counters['turns']} lượt · "
          f"{measured_cost:.4f} USD · {elapsed:.1f}s · {out_file.name}")
    for key, value in payload["criteria"].items():
        if key == "asked_fields":
            print(f"  asked_fields: {value}")
            continue
        if isinstance(value, list) and value:
            print(f"  {key}: {len(value)} → {value[:6]}")
        elif isinstance(value, list):
            print(f"  {key}: 0")


def _actual_counts(service, draft_dict: dict | None, confirmed_profile) -> dict:
    """Số thật bằng code theo nháp TẠI LƯỢT (HN-13.3.2). HN-13.3-A7: khi draft có
    mức tiền (budget_hint_vnd), trả thêm các số CÓ TRẦN (capped) — chip/model nói
    "≤ X triệu" phải khớp số có trần; held không trần vẫn hợp lệ cho câu template."""
    try:
        from backend.app.clarify import _moneyless_profile
        from backend.app.models import DraftProfile, Profile as P
        out = {"eligible": 0, "estimate_only": 0, "held": 0}
        if not draft_dict:
            return out
        draft = DraftProfile.model_validate(draft_dict)
        if confirmed_profile:
            profile = P.model_validate_json(json.dumps(confirmed_profile))
        else:
            profile = _moneyless_profile(service, draft, None)
        if profile is None:
            return out
        # D-12: không còn "held"; estimate_pool_counts = (tổng căn khớp, trong đó ước tính).
        total, estimated = service.estimate_pool_counts(profile)
        out.update(eligible=total, estimate_only=estimated, held=0,
                   shown=min(total, 5), exact=total - estimated)
        hint = draft.budget_hint_vnd
        if hint:
            capped = profile.model_copy(update={"max_monthly_cost_vnd": hint})
            total_c, estimated_c = service.estimate_pool_counts(capped)
            out["capped_eligible"] = total_c
            out["capped_estimate_only"] = estimated_c
            out["capped_shown"] = min(total_c, 5)
        return out
    except Exception:
        return {"eligible": -1, "estimate_only": -1, "held": -1}


def _held_from_draft(service, draft_dict: dict | None, confirmed_profile) -> int:
    """Đếm bằng code: số tin bị GIỮ (thiếu phí/sức chứa) theo nháp TẠI LƯỢT —
    dùng để xét câu 'không có phòng' có sai không (HN-13.3)."""
    try:
        from backend.app.clarify import _moneyless_profile
        from backend.app.models import DraftProfile, Profile as P
        if not draft_dict:
            return 0
        draft = DraftProfile.model_validate(draft_dict)
        confirmed = P.model_validate_json(json.dumps(confirmed_profile)) if confirmed_profile else None
        if confirmed:
            profile = confirmed
        else:
            profile = _moneyless_profile(service, draft, None)
        if profile is None:
            return 0
        if not profile.accept_estimated_data:
            # tin bị giữ chỉ tồn tại khi CHƯA chấp nhận ước tính
            items, diagnostics = service.catalog.rank(profile, service.matching_method)
            return sum((diagnostics.get("verification") or {}).values())
        return 0
    except Exception:
        return 0


def _recount(service, draft_dict: dict, option: dict, profile_json: str | None) -> int | None:
    """Số căn của chip: dựng hồ sơ tạm = nháp hiện tại + interpretation rồi rank.
    Chip CHƯA được áp tại lúc trả nên đếm được độc lập (không ghi gì)."""
    try:
        from backend.app.clarify import _DraftSession, _temp_profile
        from backend.app.models import DraftProfile
        draft = DraftProfile.model_validate(draft_dict)
        interpretation = option.get("interpretation") or {}
        if not interpretation:
            return None
        temporary = _temp_profile(service, draft, interpretation, profile_json)
        if temporary is None:
            return None
        items, _ = service.catalog.rank(temporary, service.matching_method)
        return len(items)
    except Exception:
        return None


def _export_transcript(payload: dict, path: Path) -> None:
    """Transcript markdown cho NGƯỜI chấm — không chấm thay."""
    lines = [f"# Transcript HN-13.2 — {payload['catalog_name']} / {payload['label']}",
             f"Model: `{payload['model']}` · analyst: {payload['analyst']} · "
             f"reasoning: {payload['reasoning']} · decision: {payload['decision_mode']} · "
             f"measured_at: {payload['measured_at']} · mỗi cấu hình chạy {payload['runs']} lần", ""]
    for conversation in payload["conversations"]:
        lines.append(f"## {conversation['id']} — {conversation.get('name', '')}")
        for record in conversation["turns"]:
            if record.get("kind", "text").startswith("chip"):
                lines.append(f"- **Lượt {record['turn']} (chip)**: khách bấm “{record.get('chip')}”"
                             + (f" → confirm {record.get('confirm')}" if record.get("confirm") else ""))
                continue
            lines.append(f"- **Khách (lượt {record['turn']})**: {record.get('text')}")
            meta = (f"route={record.get('route')}/{record.get('clarity')}({record.get('decided_by')}) "
                    f"agents={record.get('agents')} mode={record.get('agent_mode')} "
                    f"calls={record.get('llm_calls')} {record.get('latency_ms')}ms")
            lines.append(f"  - `{meta}`")
            if record.get("message"):
                lines.append(f"  - **Trợ lý**: {record['message']}")
            clarification = record.get("clarification") or {}
            if clarification.get("question"):
                lines.append(f"  - **Chip** [{clarification.get('field')}]: {clarification['question']}")
                for option in clarification.get("options") or []:
                    lines.append(f"    - “{option.get('label')}” (count={option.get('count')}, "
                                 f"decided_by={option.get('decided_by')})")
            elif record.get("questions"):
                lines.append(f"  - **Câu hỏi (không chip)**: {record['questions']}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
