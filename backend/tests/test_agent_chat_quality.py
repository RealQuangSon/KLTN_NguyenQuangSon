"""Lỗi chất lượng agent chat tìm thấy khi chạy thật 15/11/2026 (gpt-6-luna qua
OpenRouter, kho Chợ Tốt đa số thiếu phí). Mọi model là client giả — không gọi
mạng, không provider trả phí.

Lỗi 1 — công bố căn vượt mức tiền khách nêu khi cách hiểu chưa rõ.
Lỗi 2a/2b — bàn giao xếp hạng lộ câu chữ nội bộ / chép nguyên tiêu đề tin.
Lỗi 2c — đường tất định trả mã phòng chotot-… cho khách.
Lỗi 3a/3b/3c — hỏi "căn đầu tiên" khi chưa có kết quả; auto-confirm im lặng;
chip câu hỏi cũ gắn lại sau khi công bố.
Lỗi 4a/4b — "Quận 9" không nhận dạng được; điểm đến ngoài khu ghim; tiện ích
ngoài từ điển bị bỏ lặng lẽ.
"""
import json
from types import SimpleNamespace

import pytest

from backend.app.interpreter import OpenAIInterpreter
from backend.app.models import Room
from backend.app.service import HomeMatchService


def call(id_, name, **arguments):
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=name,
                                                            arguments=json.dumps(arguments, ensure_ascii=False)))


def message(content=None, tool_calls=None, tokens=7):
    usage = SimpleNamespace(total_tokens=tokens)
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=content, tool_calls=tool_calls))], usage=usage)


class FakeClient:
    def __init__(self, turns):
        self.turns = list(turns)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if not self.turns:
            raise AssertionError("FakeClient hết kịch bản phản hồi")
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


def _room(room_id: str, rent_vnd: int, service_fee: int, title: str, **extra) -> Room:
    """Căn Cầu Giấy có ĐỦ phí khai báo (tổng tháng = thuê + phí, không ước tính)."""
    fees = [
        {"name": "electricity", "amount_vnd": 1_000, "mode": "kwh",
         "included_in_rent": False, "source": "test://fee/electricity"},
        {"name": "water", "amount_vnd": 5_000, "mode": "m3",
         "included_in_rent": False, "source": "test://fee/water"},
        {"name": "internet", "amount_vnd": 45_000, "mode": "fixed",
         "included_in_rent": False, "source": "test://fee/internet"},
        {"name": "service", "amount_vnd": service_fee, "mode": "fixed",
         "included_in_rent": False, "source": "test://fee/service"},
    ]
    return Room.model_validate({
        "id": room_id, "revision": 1,
        "title": f"{title}. Còn trống",
        "city": "Hà Nội", "area": "Quận Cầu Giấy", "room_type": "room",
        "capacity": 1 if room_id.endswith("a") else 2, "area_m2": 20.0,
        "latitude": 21.045, "longitude": 105.797, "location_accuracy": "exact",
        "uncertainty_m": 0,
        "published": True, "available": True, "amenities": {"wifi": True},
        "quote": {"rent_vnd": rent_vnd, "deposit_vnd": rent_vnd, "fees": fees},
        "source": "synthetic://test", "synthetic": True,
        **extra,
    })


def _import_rooms(service) -> None:
    # Tổng tháng tính cả phí gửi xe giả định chuẩn 70k (1 xe): điện 140k + nước 15k
    # + internet 45k + gửi xe 70k = 270k ngoài tiền thuê và phí dịch vụ khai báo.
    # A: thuê 3,5 triệu → tổng 4,7 triệu (3,5 + 270k + 930k).
    # B: thuê 3,9 triệu → tổng 4,17 triệu — vượt 4 triệu theo cách hiểu TỔNG tháng.
    # C: thuê 3,4 triệu → tổng 3,97 triệu — dưới mức nêu theo cả hai cách hiểu.
    service.catalog.import_rooms([
        _room("qa-room-a", 3_500_000, 930_000, "Phòng trọ mới xây gần Đại học Quốc gia"),
        _room("qa-room-b", 3_900_000, 0, "Studio khép kín phố Cầu Giấy"),
        _room("qa-room-c", 3_400_000, 300_000, "Phòng trọ yên tĩnh gần Học viện Lục quân"),
    ])


@pytest.fixture
def service(tmp_path):
    """Service chế độ demo (đường tất định) với kho giả 3 căn Cầu Giấy."""
    agent = HomeMatchService(tmp_path / "chat-quality.sqlite")
    _import_rooms(agent)
    yield agent
    agent.close()


@pytest.fixture
def agent(tmp_path):
    """Service chế độ openai với model giả (không gọi mạng)."""
    agent = HomeMatchService(tmp_path / "chat-quality-loop.sqlite",
                             interpreter=OpenAIInterpreter(client=SimpleNamespace(), model="fixture-model"))
    _import_rooms(agent)
    yield agent
    agent.close()


RENT = 4_000_000
SENTENCE = "Tìm phòng trọ dưới 4 triệu ở Cầu Giấy, 1 người"


# --- Lỗi 1: mức trần chưa rõ cách hiểu thì không công bố căn vượt mức theo cả hai ---


def test_scope_unknown_stays_strict_in_profile_from_draft(service, renter):
    """Nháp chưa nêu cách hiểu (scope None) → hồ sơ tìm theo cách CHẶT hơn:
    cả trần tiền thuê lẫn trần tổng tháng đều bằng mức khách nêu."""
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, SENTENCE)
    profile = service._profile_from_draft(sid)
    assert profile is not None and profile.city == "Hà Nội"
    assert profile.max_rent_vnd == RENT, profile
    assert profile.max_monthly_cost_vnd == RENT, profile


def test_stated_cap_holds_under_both_readings_in_rank(service, renter):
    """Căn A (thuê 3,5tr/tổng 4,7tr) và B (thuê 3,9tr/tổng 4,1tr) đều vượt trần
    4 triệu theo cách hiểu TỔNG tháng — không được lọt vào kết quả khi scope
    chưa rõ; căn C (cả hai đều ≤ 4 triệu) vẫn được giữ."""
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, SENTENCE)
    profile = service._profile_from_draft(sid)
    items, _ = service.catalog.rank(profile, service.matching_method)
    ids = {item.room_id for item in items}
    assert "qa-room-a" not in ids and "qa-room-b" not in ids, ids
    assert "qa-room-c" in ids


def test_turn_asks_budget_scope_before_publishing(service, renter):
    """Đường tất định (demo): cách hiểu chưa rõ và hai cách hiểu cho kết quả
    khác nhau → hỏi budget_scope TRƯỚC, không công bố run nào trong lượt."""
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, SENTENCE)
    runs = service.repo.db.execute(
        "SELECT COUNT(*) AS c FROM hm_runs WHERE session_id=?", (sid,)).fetchone()["c"]
    assert runs == 0, reply.get("message")
    dto = reply.get("clarification") or {}
    assert dto.get("field") == "budget_scope", dto
    assert {option["patch"]["set"].get("budget_scope")
            for option in dto.get("options", [])} == {"total", "rent"}


def test_publish_after_scope_choice_keeps_relaxed_reading(service, renter):
    """Khách bấm chip "Chỉ trần tiền THUÊ" → scope=rent → tìm lại với trần thuê
    4 triệu (căn A, B vào được); trần tổng không còn là điều kiện cứng."""
    from backend.app.models import DraftPatch
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, SENTENCE)
    session = service.session(sid, renter)
    service.patch_draft(sid, renter, DraftPatch(
        expected_draft_revision=session["draft_revision"],
        set={"budget_scope": "rent"}, source="clarify"))
    results = service.results(sid, renter)
    assert results["status"] == "published"
    ids = {item["room_id"] for item in results["results"]}
    assert "qa-room-a" in ids and "qa-room-b" in ids, ids
    profile = service._confirmed_profile(sid)
    assert profile.max_rent_vnd == RENT and profile.max_monthly_cost_vnd is None


def test_loop_turn_never_publishes_over_cap_without_scope_choice(agent, renter):
    """Vòng lặp openai (model giả): confirm_and_search phải bị lớp hỏi lại chặn
    khi cách hiểu mức tiền chưa rõ — không run nào được công bố trong lượt."""
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs",
                                 patch={"city": "Hà Nội", "area": "Quận Cầu Giấy",
                                        "room_type": "room", "people": 1})]),
        message(tool_calls=[call("c2", "confirm_and_search")]),
        message(tool_calls=[call("c3", "ask_user", field="budget_scope")]),
    ])
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, SENTENCE)
    runs = agent.repo.db.execute(
        "SELECT COUNT(*) AS c FROM hm_runs WHERE session_id=?", (sid,)).fetchone()["c"]
    assert runs == 0, reply.get("message")
    dto = reply.get("clarification") or {}
    assert dto.get("field") == "budget_scope", dto


# --- Lỗi 2a: bàn giao xếp hạng không được lộ câu chữ nội bộ -------------------------


def test_guard_output_blocks_internal_wording():
    from backend.app.agent_loop import guard_output
    leaky = ("Mức tiền khách nêu không có trong dữ liệu gửi kèm nên chưa đối chiếu được.")
    text, violation = guard_output(leaky, [])
    assert violation == "internal_wording", (text, violation)
    assert text != leaky
    # JSON/tool/hậu kiểm cũng là cơ chế nội bộ.
    for phrase in ("JSON kèm dưới đây", "tôi đã chạy tool", "qua hậu kiểm số"):
        _, violation = guard_output(f"Dữ liệu cho bạn: {phrase}.", [])
        assert violation == "internal_wording", phrase


def test_rank_handover_leak_keeps_confirm_template(agent, renter):
    """Câu bàn giao lộ câu chữ nội bộ → rank_handover trả None để caller GIỮ câu
    mẫu confirm_template (như mọi lỗi bàn giao khác)."""
    import time

    from backend.app.agent_loop import rank_handover
    from backend.app.models import Profile, Scenario
    sid = agent.create_session(renter)["session_id"]
    agent.confirm(sid, renter, Profile(city="Hà Nội", area="Quận Cầu Giấy",
                                       max_monthly_cost_vnd=4_000_000,
                                       scenario=Scenario(people=1)),
                  agent.session(sid, renter)["draft_revision"])
    agent.interpreter.client = FakeClient([message(
        "Mức tiền khách nêu không có trong dữ liệu gửi kèm nên chưa đối chiếu được.")])
    info = rank_handover(agent, {"id": sid}, renter, "tìm phòng giúp mình",
                         fallback="CÂU MẪU", successful_tools=[], turn_started=time.monotonic())
    assert info is None


def test_rank_handover_grounding_carries_applied_cap(agent, renter):
    """Grounding bàn giao phải chứa mức trần ĐÃ ÁP (từ hồ sơ đã xác nhận, không
    thu nhập) để model không nói 'mức tiền không có trong dữ liệu'."""
    import json
    import time

    from backend.app.agent_loop import rank_handover
    from backend.app.models import Profile, Scenario
    sid = agent.create_session(renter)["session_id"]
    agent.confirm(sid, renter, Profile(city="Hà Nội", area="Quận Cầu Giấy",
                                       max_monthly_cost_vnd=4_000_000,
                                       scenario=Scenario(people=1)),
                  agent.session(sid, renter)["draft_revision"])
    agent.interpreter.client = FakeClient([message("Căn 1 hợp nhu cầu của bạn.")])
    info = rank_handover(agent, {"id": sid}, renter, "tìm phòng giúp mình",
                         fallback="", successful_tools=[], turn_started=time.monotonic())
    assert info and info["answer"]
    request = agent.interpreter.client.requests[0]
    user_content = request["messages"][1]["content"]
    assert "Ràng buộc tiền đã áp" in user_content
    assert "4.000.000" in user_content
    assert "monthly_income" not in user_content and "housing_ratio" not in user_content


# --- Lỗi 2b: nhãn ngắn ổn định cho từng căn trong bàn giao --------------------------


def test_rank_handover_uses_short_stable_labels(agent, renter):
    """JSON bàn giao cho model nhãn 'Căn 1 · phòng trọ · <khu>' — KHÔNG còn nguyên
    tiêu đề tin đăng để model chép."""
    import time

    from backend.app.agent_loop import rank_handover
    from backend.app.models import Profile, Scenario
    sid = agent.create_session(renter)["session_id"]
    agent.confirm(sid, renter, Profile(city="Hà Nội", area="Quận Cầu Giấy",
                                       max_monthly_cost_vnd=4_000_000,
                                       scenario=Scenario(people=1)),
                  agent.session(sid, renter)["draft_revision"])
    agent.interpreter.client = FakeClient([message("Căn 1 hợp nhu cầu của bạn.")])
    info = rank_handover(agent, {"id": sid}, renter, "tìm phòng giúp mình",
                         fallback="", successful_tools=[], turn_started=time.monotonic())
    assert info and info["answer"]
    user_content = agent.interpreter.client.requests[0]["messages"][1]["content"]
    assert "Căn 1" in user_content and "phòng trọ" in user_content
    assert "Quận Cầu Giấy" in user_content
    # Nguyên tiêu đề tin ("Phòng trọ qa-room-c") không còn trong dữ liệu cấp model.
    assert "qa-room-c" not in user_content


# --- Lỗi 2c: đường tất định đặt lịch dùng tên phòng, không mã chotot- ---------------


def test_prepare_viewing_reply_uses_room_title(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, SENTENCE)  # hỏi chip scope, nháp đã có city+hint
    from backend.app.models import DraftPatch, Profile, Scenario
    session = service.session(sid, renter)
    service.patch_draft(sid, renter, DraftPatch(
        expected_draft_revision=session["draft_revision"],
        set={"budget_scope": "total"}, source="clarify"))
    reply = service.message(sid, renter, "Ok đặt lịch xem căn đầu giúp mình luôn sáng mai nhé")
    text = (reply.get("message") or "") + " ".join(reply.get("questions") or [])
    assert "chotot" not in text, text
    assert "qa-room-c" not in text, text
    assert "phiên bản hồ sơ" not in text and "có múi giờ" not in text, text
    assert "chưa tạo lịch xem" in text or "chưa được tạo" in text, text
    # Căn được focus sẵn trên workspace để khách bấm đặt lịch ngay.
    assert (reply.get("view_payload") or {}).get("room_id") == "qa-room-c"


# --- Lỗi 3a: hỏi về một căn cụ thể khi CHƯA có kết quả ------------------------------


def _draft_with_city_and_hint(service, sid: str) -> None:
    """Nháp đủ city + mức tiền (như sau một câu nêu nhu cầu), chưa xác nhận."""
    draft = service._draft(sid)
    draft.city = "Hà Nội"
    draft.area = "Quận Cầu Giấy"
    draft.room_type = "room"
    draft.budget_hint_vnd = 4_000_000
    for key in ("city", "area", "room_type", "budget_hint"):
        draft.field_status[key] = "inferred"
        draft.evidence_ref[key] = "chat:r1"
    session = service.repo.session(sid)
    service.repo.update_draft(sid, draft, session["draft_revision"])


def test_room_question_without_results_answers_deterministically(agent, renter):
    """"Căn đầu tiên tính ra mỗi tháng hết bao nhiêu?" khi phiên chưa có kết quả:
    trả lời tất định (0 lần gọi LLM), giữ chip câu hỏi đang treo, KHÔNG tự xác nhận
    hồ sơ và không công bố gì."""
    sid = agent.create_session(renter)["session_id"]
    _draft_with_city_and_hint(agent, sid)
    # Lượt 1: model hỏi lại bằng chip kho (câu hỏi đang treo).
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "ask_user", field="people")]),
    ])
    agent.message(sid, renter, "Mình muốn tìm chỗ ở yên tĩnh đi làm cho tiện")
    pending = agent._pending_clarification.get(sid)
    assert pending and pending.get("field"), agent._pending_clarification
    requests_before = len(agent.interpreter.client.requests)
    reply = agent.message(sid, renter,
                          "Căn đầu tiên tính ra mỗi tháng hết bao nhiêu, gồm những khoản gì?")
    assert len(agent.interpreter.client.requests) == requests_before, \
        "không được tốn lần gọi LLM cho câu này"
    runs = agent.repo.db.execute(
        "SELECT COUNT(*) AS c FROM hm_runs WHERE session_id=?", (sid,)).fetchone()["c"]
    assert runs == 0
    text = (reply.get("message") or "") + " ".join(reply.get("questions") or [])
    assert "chưa có danh sách" in text, text
    # Chip câu hỏi đang treo được giữ lại (cùng field, có lựa chọn từ kho).
    dto = reply.get("clarification") or {}
    assert dto.get("field") == pending["field"], (dto, pending)
    assert dto.get("options"), dto


# --- Lỗi 3b: auto-confirm là "tìm với giả định" — giả định phải hiện ----------------


def _draft_with_inferred_destination(service, sid: str) -> None:
    from backend.app.models import Destination
    draft = service._draft(sid)
    draft.destination = Destination(label="Đại học Quốc gia", latitude=21.045,
                                    longitude=105.797, uncertainty_m=0, max_distance_m=3000)
    draft.field_status["destination"] = "inferred"
    draft.evidence_ref["destination"] = "chat:r1"
    session = service.repo.session(sid)
    service.repo.update_draft(sid, draft, session["draft_revision"])


def test_auto_confirm_publishing_states_its_assumptions(agent, renter, monkeypatch):
    """Hết quyền hỏi mà vẫn auto-confirm → lượt công bố phải nêu giả định đang dùng
    (bán kính mặc định, cách hiểu chặt hơn) qua MessageResult.assumptions."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    _draft_with_inferred_destination(agent, sid)
    _draft_with_city_and_hint(agent, sid)
    # Hết giới hạn câu hỏi (2 câu trước kết quả đầu).
    agent.repo.db.execute("UPDATE hm_sessions SET clarification_questions=2 WHERE id=?", (sid,))
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs", patch={"preferences": ["wifi"]})]),
        message(content="Đã ghi nhận nhu cầu của bạn."),
    ])
    reply = agent.message(sid, renter, "ghi nhận giúp mình nhu cầu vừa rồi nhé")
    assert reply["status"] == "published", reply.get("message")
    assumptions = " ".join(reply.get("assumptions") or [])
    assert "bán kính 3 km" in assumptions, reply.get("assumptions")
    assert "chặt hơn" in assumptions, reply.get("assumptions")


# --- Lỗi 3c: guard thay câu trả lời thì không gắn lại chip câu hỏi cũ ---------------


def test_guard_replaced_turn_does_not_reattach_stale_chip(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    _draft_with_inferred_destination(agent, sid)
    _draft_with_city_and_hint(agent, sid)
    agent.repo.db.execute("UPDATE hm_sessions SET clarification_questions=2 WHERE id=?", (sid,))
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs", patch={"preferences": ["wifi"]})]),
        message(content="Đã ghi nhận nhu cầu của bạn."),
    ])
    agent.message(sid, renter, "ghi nhận giúp mình nhu cầu vừa rồi nhé")
    # Lượt sau: câu ngoài luồng bị guard thay (tuyên bố "đã đặt lịch" không có tool).
    agent.interpreter.client = FakeClient([message(content="Ok, mình đã đặt lịch cho bạn rồi nhé!")])
    reply = agent.message(sid, renter, "ừ bạn chuẩn bị giúp mình nhé")
    assert reply["message"].startswith("Mình vừa rà lại"), reply["message"]
    dto = reply.get("clarification") or {}
    assert not dto.get("question"), dto
    assert not reply.get("questions"), reply.get("questions")


# --- Lỗi 3d: lượt giải thích trên kết quả đang công bố phải trả status đúng nghĩa --


def test_explanation_turn_over_published_results_reports_published(agent, renter):
    from backend.app.models import Profile, Scenario
    sid = agent.create_session(renter)["session_id"]
    agent.confirm(sid, renter, Profile(city="Hà Nội", area="Quận Cầu Giấy",
                                       max_monthly_cost_vnd=3_970_000,
                                       scenario=Scenario(people=1)),
                  agent.session(sid, renter)["draft_revision"])
    assert agent.results(sid, renter)["status"] == "published"
    agent.interpreter.client = FakeClient([
        message(content="Căn 1 đang đứng đầu vì tổng tháng thấp nhất trong danh sách nhé.")])
    reply = agent.message(sid, renter, "sao căn 1 đứng đầu vậy?")
    assert reply["status"] == "published", reply.get("status")


# --- Lỗi 4a: "Quận 9" phải được nhận dạng và ghim thành phố --------------------------


def test_quan_nine_resolves_to_thu_duc_with_city_pin():
    from backend.app.locations import city_for_area, find_area
    assert find_area("khu công nghệ cao Quận 9") == "TP. Thủ Đức"
    assert city_for_area("Quận 9") == "TP.HCM"
    from backend.app.interpreter import DemoInterpreter
    extraction = DemoInterpreter().extract("Mình làm ở khu công nghệ cao Quận 9, cần studio")
    assert extraction.area == "TP. Thủ Đức"
    assert extraction.city is None  # thành phố do ghim tất định, không mặc định


def test_fast_path_pins_city_from_area_for_quan_nine(agent, renter, monkeypatch):
    """Câu đầu phiên có "Quận 9" nhưng không nêu thành phố: luật trích được khu →
    ghim thành phố bằng city_for_area → fast path chạy, không hỏi lại thành phố."""
    monkeypatch.setattr(__import__("backend.app.clarify", fromlist=["build_clarification"]),
                        "build_clarification", lambda *a, **k: None)
    agent.interpreter.client = FakeClient([])
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(
        sid, renter,
        "Mình làm ở khu công nghệ cao Quận 9, cần studio có máy lạnh cho 2 người, tổng tháng 5 triệu")
    draft = agent.session(sid, renter)["draft"]
    assert draft["area"] == "TP. Thủ Đức", draft
    assert draft["city"] == "TP.HCM", draft
    assert reply["status"] in {"published", "no_match"}, reply.get("message")


def test_update_needs_pins_city_when_area_names_district(agent, renter):
    """Model ghi area="Quận 9" khi nháp chưa có thành phố → tool tự ghim TP.HCM
    (alias tất định, như node interview của graph), không hỏi lại thành phố."""
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs",
                                 patch={"area": "Quận 9", "room_type": "studio"})]),
        message(content="Đã ghi nhận khu vực của bạn."),
    ])
    reply = agent.message(sid, renter, "Mình làm ở khu công nghệ cao Quận 9, cần studio")
    draft = agent.session(sid, renter)["draft"]
    assert draft["area"] == "TP. Thủ Đức", draft
    assert draft["city"] == "TP.HCM", draft
    assert reply.get("agents") in (None, ["needs"])


def test_city_question_cannot_carry_area_wording(agent, renter):
    """Model hỏi "quận nào" nhưng field là city (chip thành phố) → giữ câu mẫu của
    kho để câu hỏi và chip khớp nhau."""
    sid = agent.create_session(renter)["session_id"]
    _draft_with_city_and_hint(agent, sid)
    draft = agent._draft(sid)
    draft.city = None
    draft.field_status["city"] = "unknown"
    draft.evidence_ref.pop("city", None)
    agent.repo.update_draft(sid, draft, agent.repo.session(sid)["draft_revision"])
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "ask_user", field="city",
                                 question="Mình chưa xác định được khu vực để khoanh vùng phòng. "
                                          "Bạn muốn tìm ở quận hoặc khu vực nào?")]),
    ])
    reply = agent.message(sid, renter, "Mình cần studio có máy lạnh cho 2 người")
    dto = reply.get("clarification") or {}
    assert dto.get("field") == "city", dto
    assert "quận" not in (dto.get("question") or "").lower(), dto.get("question")
    assert "thành phố" in (dto.get("question") or "").lower()


# --- Lỗi 4b: điểm đến ngoài khu ghim; no_match nới cụ thể; tiện ích ngoài từ điển ----


def test_destination_outside_pinned_area_asks_renter(agent, renter):
    """Bách Khoa (Hai Bà Trưng) ngoài khu đang ghim Cầu Giấy: tool phải TỪ CHỐI ghi
    điểm đến và chỉ dẫn model hỏi khách giữ khu cũ hay chuyển khu — không tự giữ,
    không tự bỏ."""
    from backend.app.models import DraftPatch
    sid = agent.create_session(renter)["session_id"]
    _draft_with_city_and_hint(agent, sid)
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs",
                                 patch={"destination_text": "Đại học Bách Khoa Hà Nội"})]),
        message(content="Bạn muốn giữ khu Cầu Giấy hay chuyển sang ở quanh Bách Khoa?"),
    ])
    reply = agent.message(sid, renter, "Mình học ở Bách Khoa, có chỗ nào gần trường không?")
    draft = agent.session(sid, renter)["draft"]
    assert draft["destination"] is None, "điểm đến chưa được khách chọn thì không ghi"
    # Vòng sửa 2: lượt kết thúc ngay bằng hai nút của hệ thống (không chờ model hỏi).
    assert len(agent.interpreter.client.requests) == 1
    assert any("destination_area_conflict" in step for step in reply["steps"])
    assert (reply.get("clarification") or {}).get("field") == "conflict"


def test_same_area_destination_still_saved(agent, renter):
    """Điểm đến CÓ căn của khu ghim trong bán kính → ghi bình thường (không hỏi)."""
    sid = agent.create_session(renter)["session_id"]
    _draft_with_city_and_hint(agent, sid)
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs",
                                 patch={"destination_text": "Đại học Thương mại"})]),
        message(content="Đã ghi nhận điểm đến của bạn."),
    ])
    agent.message(sid, renter, "Mình học ở Đại học Thương mại, tìm phòng gần trường")
    draft = agent.session(sid, renter)["draft"]
    assert draft["destination"] and draft["destination"]["label"] == "Đại học Thương mại"


def test_unknown_amenity_told_to_renter(agent, renter):
    """"hồ bơi" không có trong AMENITY_KEYS: tool từ chối ghi và chỉ dẫn model nói
    với khách rằng hệ thống chưa lọc được tiêu chí đó — không bỏ lặng lẽ."""
    sid = agent.create_session(renter)["session_id"]
    _draft_with_city_and_hint(agent, sid)
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs", patch={"preferences": ["pool"]})]),
        message(content="Mình chưa lọc được tiêu chí hồ bơi, bạn chọn tiện ích khác nhé."),
    ])
    agent.message(sid, renter, "Mình cần căn hộ 2 phòng ngủ có hồ bơi ở Cầu Giấy, gần trường học cho tiện")
    tool_message = next(item for item in agent.interpreter.client.requests[1]["messages"]
                        if item.get("role") == "tool")
    assert "chưa lọc được" in tool_message["content"].lower(), tool_message["content"][:400]


def test_no_match_offers_specific_relax_chips_from_catalog(agent, renter):
    """no_match: chip nới CỤ THỂ dựng từ kho (ràng buộc nào chặn, nới ra còn bao
    nhiêu căn) — khách bấm mới áp; không phụ thuộc giới hạn câu hỏi."""
    sid = agent.create_session(renter)["session_id"]
    _draft_with_city_and_hint(agent, sid)
    # Trần 2,5 triệu: cả 3 căn đều bị chặn bởi tiền thuê → no_match.
    draft = agent._draft(sid)
    draft.budget_hint_vnd = 2_500_000
    agent.repo.update_draft(sid, draft, agent.repo.session(sid)["draft_revision"])
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "confirm_and_search")]),
    ])
    reply = agent.message(sid, renter, "Tìm phòng trọ dưới 2,5 triệu ở Cầu Giấy cho 1 người")
    assert reply["status"] == "no_match", reply.get("message")
    dto = reply.get("clarification") or {}
    assert dto.get("options"), reply.get("clarification")
    labels = " | ".join(option["label"] for option in dto["options"])
    assert "căn" in labels, labels
    # Ít nhất một chip có patch thật (bấm là áp) hoặc chip chữ về tiền.
    assert any(option.get("patch", {}).get("set") for option in dto["options"]) \
        or any(option.get("action") == "text" for option in dto["options"])


# --- Lỗi 5: câu luật hiểu trọn vẹn phải đi đường tắt dù analyst đoán clarity=reason ---


def test_fast_path_taken_even_when_analyst_says_reason(agent, renter, monkeypatch):
    """Jev đoán sai clarity=reason cho câu luật hiểu trọn vẹn: vòng lặp không được
    nuốt câu này (đo live 15/11: 27,7 s thay vì đường tắt 0 LLM)."""
    from backend.app import input_analyst
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    monkeypatch.setattr(input_analyst, "analyze",
                        lambda *a, **k: {"route": "needs", "clarity": "reason",
                                         "decided_by": "jev"})
    agent.interpreter.client = FakeClient([])
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, SENTENCE)
    assert reply["agent_mode"] == "fast_path", reply.get("agent_mode")
    assert agent.interpreter.client.requests == []


# --- Việc nhỏ: tin ở ghép phải được nêu rõ điều kiện trong lời giải thích ------------


def test_handover_notes_roommate_condition(agent, renter, monkeypatch):
    """Tin "tìm bạn nữ ở ghép" gợi ý cho người ở một mình: lời giải thích (dữ liệu
    bàn giao) phải nêu đây là tin ở ghép có điều kiện của người đăng — không đưa
    giới tính vào xếp hạng."""
    import time

    from backend.app.agent_loop import rank_handover
    from backend.app.models import Profile, Room, Scenario
    roommate = Room.model_validate({
        "id": "qa-room-share", "revision": 1,
        "title": "Tìm bạn nữ ở ghép (phòng đã có 2 ng). Còn trống",
        "city": "Hà Nội", "area": "Quận Cầu Giấy", "room_type": "room",
        "capacity": 3, "area_m2": 30.0, "latitude": 21.045, "longitude": 105.797,
        "published": True, "available": True, "amenities": {},
        "quote": {"rent_vnd": 2_000_000, "deposit_vnd": 2_000_000, "fees": []},
        "source": "synthetic://test", "synthetic": True,
    })
    agent.catalog.import_rooms([roommate])
    sid = agent.create_session(renter)["session_id"]
    agent.confirm(sid, renter, Profile(city="Hà Nội", area="Quận Cầu Giấy",
                                       max_monthly_cost_vnd=4_000_000,
                                       scenario=Scenario(people=1)),
                  agent.session(sid, renter)["draft_revision"])
    agent.interpreter.client = FakeClient([message("Căn 1 là tin ở ghép.")])
    info = rank_handover(agent, {"id": sid}, renter, "tìm phòng giúp mình",
                         fallback="", successful_tools=[], turn_started=time.monotonic())
    assert info and info["answer"]
    user_content = agent.interpreter.client.requests[0]["messages"][1]["content"]
    assert "ở ghép" in user_content, user_content[:400]
    assert "điều kiện của người đăng" in user_content


# --- Việc nhỏ: nhãn chip tiền phải khớp cách đếm (thiếu phí → "Tiền thuê dưới X") ----


def test_budget_cap_label_matches_counting_basis(tmp_path):
    """Kho thiếu phí (tổng tháng là ước tính) → chip phải là "Tiền thuê dưới X";
    kho đủ phí (≥5 căn tổng biết chắc) → "Tổng tháng dưới X"."""
    from backend.app.models import Room
    from backend.app.service import HomeMatchService

    def _room(room_id: str, rent_vnd: int, fees: list) -> Room:
        return Room.model_validate({
            "id": room_id, "revision": 1, "title": f"Phòng {room_id}. Còn trống",
            "city": "Hà Nội", "area": "Quận Cầu Giấy", "room_type": "room",
            "capacity": 2, "area_m2": 20.0,
            "published": True, "available": True, "amenities": {"wifi": True},
            "quote": {"rent_vnd": rent_vnd, "deposit_vnd": rent_vnd, "fees": fees},
            "source": "synthetic://test", "synthetic": True,
        })

    def _service(path, rooms):
        svc = HomeMatchService(path)
        svc.catalog.import_rooms(rooms)
        return svc

    from backend.app.models import Actor
    renter = Actor(id="renter", role="renter")
    # Kho THIẾU phí: tổng tháng đều là ước tính → nhãn "Tiền thuê dưới X".
    svc_missing = _service(tmp_path / "missing.sqlite", [
        _room(f"cap-miss-{i}", 2_000_000 + i * 300_000, []) for i in range(8)])
    try:
        sid = svc_missing.create_session(renter)["session_id"]
        draft = svc_missing._draft(sid)
        draft.city = "Hà Nội"
        draft.field_status["city"] = "inferred"
        draft.evidence_ref["city"] = "chat:r1"
        svc_missing.repo.update_draft(sid, draft, svc_missing.repo.session(sid)["draft_revision"])
        chips = __import__("backend.app.clarify", fromlist=["state_chips"]).state_chips(svc_missing, sid)
        assert chips and all(chip.startswith("Tiền thuê dưới") for chip in chips), chips
    finally:
        svc_missing.close()
    # Kho ĐỦ phí: tổng tháng biết chắc → nhãn "Tổng tháng dưới X".
    full_fees = [{"name": "electricity", "amount_vnd": 1_000, "mode": "kwh",
                  "included_in_rent": False, "source": "t://e"},
                 {"name": "water", "amount_vnd": 5_000, "mode": "m3",
                  "included_in_rent": False, "source": "t://w"},
                 {"name": "internet", "amount_vnd": 45_000, "mode": "fixed",
                  "included_in_rent": False, "source": "t://i"},
                 {"name": "parking", "amount_vnd": 0, "mode": "fixed",
                  "included_in_rent": True, "source": "t://p"},
                 {"name": "service", "amount_vnd": 100_000, "mode": "fixed",
                  "included_in_rent": False, "source": "t://s"}]
    svc_full = _service(tmp_path / "full.sqlite", [
        _room(f"cap-full-{i}", 2_000_000 + i * 300_000, full_fees) for i in range(8)])
    try:
        sid = svc_full.create_session(renter)["session_id"]
        draft = svc_full._draft(sid)
        draft.city = "Hà Nội"
        draft.field_status["city"] = "inferred"
        draft.evidence_ref["city"] = "chat:r1"
        svc_full.repo.update_draft(sid, draft, svc_full.repo.session(sid)["draft_revision"])
        chips = __import__("backend.app.clarify", fromlist=["state_chips"]).state_chips(svc_full, sid)
        money_chips = [chip for chip in chips if "dưới" in chip]
        assert money_chips and all(chip.startswith("Tổng tháng dưới") for chip in money_chips), chips
    finally:
        svc_full.close()


# === Vòng sửa 2 (15/11): lỗi còn lại sau lần chạy thật thứ hai ====================


def _http(service):
    from contextlib import contextmanager
    from fastapi.testclient import TestClient
    from backend.app.main import create_app

    @contextmanager
    def manager():
        with TestClient(create_app(lambda: service)) as client:
            yield client
    return manager()


AUTH = {"Authorization": "Bearer demo-renter"}


def test_clarify_chip_patch_returns_run_status_over_http(service):
    """Bấm chip cách hiểu mức tiền = PATCH draft (source=clarify) → backend tự xác nhận
    và xếp hạng. Trước đây thân trả về vi phạm DraftResult → HTTP 500."""
    with _http(service) as client:
        sid = client.post("/sessions", headers=AUTH).json()["session_id"]
        turn = client.post(f"/sessions/{sid}/messages", headers=AUTH, json={"text": SENTENCE})
        assert turn.status_code == 200, turn.text
        chip = turn.json()["clarification"]
        assert chip["field"] == "budget_scope", chip
        option = next(item for item in chip["options"] if item["patch"]["set"].get("budget_scope") == "total")
        response = client.patch(f"/sessions/{sid}/draft", headers=AUTH, json={
            "expected_draft_revision": turn.json()["draft_revision"],
            "set": option["patch"]["set"], "clear_fields": [], "remove_preferences": [],
            "source": "clarify"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "published" and body["questions"] == []
        results = client.get(f"/sessions/{sid}/results", headers=AUTH).json()
        assert results["status"] == "published" and results["results"]


def test_room_question_after_question_limit_does_not_auto_confirm(agent, renter):
    """Đã hỏi đủ 2 câu, chưa có kết quả, khách hỏi "căn đầu tiên…": vẫn trả lời "chưa có
    danh sách" — giới hạn câu hỏi không được biến lượt này thành một lượt tìm."""
    sid = agent.create_session(renter)["session_id"]
    _draft_with_city_and_hint(agent, sid)
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "ask_user", field="people")]),
    ])
    agent.message(sid, renter, "Mình muốn tìm chỗ ở yên tĩnh đi làm cho tiện")
    agent.repo.db.execute("UPDATE hm_sessions SET clarification_questions=2 WHERE id=?", (sid,))
    assert not agent._can_ask_clarification(sid)
    reply = agent.message(sid, renter,
                          "Căn đầu tiên tính ra mỗi tháng hết bao nhiêu, gồm những khoản gì?")
    assert reply["status"] == "needs_clarification", reply
    assert "chưa có danh sách" in reply["message"]
    runs = agent.repo.db.execute(
        "SELECT COUNT(*) AS c FROM hm_runs WHERE session_id=?", (sid,)).fetchone()["c"]
    assert runs == 0
    assert agent.repo.session(sid)["clarification_questions"] == 2


def test_fast_path_names_amenity_it_cannot_filter(agent, renter):
    """Đường tắt (0 LLM) gặp "hồ bơi": tìm như thường nhưng câu trả lời nói thẳng tiêu
    chí này chưa lọc được."""
    sid = agent.create_session(renter)["session_id"]
    draft = agent._draft(sid)
    draft.budget_scope = "rent"
    agent.repo.update_draft(sid, draft, agent.repo.session(sid)["draft_revision"])
    agent.interpreter.client = FakeClient([])
    reply = agent.message(sid, renter, "Tìm phòng trọ có hồ bơi tiền thuê dưới 4 triệu ở Cầu Giấy, 1 người")
    assert reply["agent_mode"] == "fast_path", reply
    assert "chưa lọc được theo “hồ bơi”" in reply["message"], reply["message"]


def test_ask_budget_without_any_amount_asks_for_the_amount(agent, renter):
    """Model gọi ask_user(field="budget_scope") khi khách CHƯA nêu mức tiền: phải thành câu
    hỏi mức tiền kết thúc lượt (1 lần gọi model), không phải "không cần hỏi"."""
    sid = agent.create_session(renter)["session_id"]
    draft = agent._draft(sid)
    draft.city = "Hà Nội"
    draft.field_status["city"] = "inferred"
    draft.evidence_ref["city"] = "chat:r1"
    agent.repo.update_draft(sid, draft, agent.repo.session(sid)["draft_revision"])
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "ask_user", field="budget_scope")]),
    ])
    reply = agent.message(sid, renter, "Mình cần chỗ ở yên tĩnh để đi làm cho tiện")
    assert len(agent.interpreter.client.requests) == 1
    dto = reply.get("clarification") or {}
    assert dto.get("field") == "budget_cap", reply
    assert reply["questions"] == [dto["question"]]


def test_destination_conflict_gets_system_chips_even_past_question_limit(agent, renter):
    """Điểm đến ngoài khu đang ghim: hai nút giữ khu / chuyển khu do hệ thống dựng, có
    cả khi đã hết lượt hỏi; không đẩy khách sang biểu mẫu, không tự tìm."""
    sid = agent.create_session(renter)["session_id"]
    _draft_with_city_and_hint(agent, sid)
    agent.repo.db.execute("UPDATE hm_sessions SET clarification_questions=2 WHERE id=?", (sid,))
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs",
                                 patch={"destination_text": "Đại học Bách Khoa Hà Nội"})]),
        message(content="Bạn hãy chọn trong biểu mẫu nhu cầu: giữ Cầu Giấy hay chuyển khu."),
    ])
    reply = agent.message(sid, renter, "Mình học ở Bách Khoa, có chỗ nào gần trường không?")
    dto = reply.get("clarification") or {}
    assert dto.get("field") == "conflict", reply
    assert [option["id"] for option in dto["options"]] == ["conflict-move", "conflict-keep"]
    assert "biểu mẫu" not in reply["message"], reply["message"]
    assert reply["status"] == "needs_clarification"
    assert agent.repo.session(sid)["clarification_questions"] == 2
    # Bấm "tìm quanh Bách Khoa": khu cũ được bỏ, điểm đến được ghi.
    move = dto["options"][0]["patch"]["set"]
    from backend.app.models import DraftPatch
    agent.patch_draft(sid, renter, DraftPatch(
        expected_draft_revision=agent.repo.session(sid)["draft_revision"],
        set=move, clear_fields=[], remove_preferences=[], source="clarify"))
    draft = agent.session(sid, renter)["draft"]
    assert draft["area"] is None and draft["destination"]["label"] == "Đại học Bách Khoa Hà Nội"


def test_relax_area_chip_really_drops_area_from_confirmed_profile(agent, renter):
    """Nút "Nới khu vực" trên hồ sơ ĐÃ xác nhận: khu vực phải rời khỏi hồ sơ (trước đây
    nháp xóa khu nhưng hồ sơ giữ nguyên nên bấm không đổi gì)."""
    from backend.app.models import DraftPatch
    sid = agent.create_session(renter)["session_id"]
    _draft_with_city_and_hint(agent, sid)
    draft = agent._draft(sid)
    draft.budget_scope = "rent"
    agent.repo.update_draft(sid, draft, agent.repo.session(sid)["draft_revision"])
    profile = agent._profile_from_draft(sid)
    agent.confirm(sid, renter, profile, agent.repo.session(sid)["draft_revision"])
    assert agent._confirmed_profile(sid).area == "Quận Cầu Giấy"
    result = agent.patch_draft(sid, renter, DraftPatch(
        expected_draft_revision=agent.repo.session(sid)["draft_revision"],
        set={"area": None}, clear_fields=[], remove_preferences=[], source="clarify"))
    assert agent._confirmed_profile(sid).area is None
    assert result["status"] in {"published", "no_match"}


def test_relax_chip_does_not_spend_question_budget(agent, renter):
    """Nút nới điều kiện sau no_match không tính vào giới hạn 2 câu hỏi."""
    sid = agent.create_session(renter)["session_id"]
    _draft_with_city_and_hint(agent, sid)
    draft = agent._draft(sid)
    draft.budget_hint_vnd = 2_500_000
    agent.repo.update_draft(sid, draft, agent.repo.session(sid)["draft_revision"])
    agent.interpreter.client = FakeClient([message(tool_calls=[call("c1", "confirm_and_search")])])
    reply = agent.message(sid, renter, "Tìm phòng trọ dưới 2,5 triệu ở Cầu Giấy cho 1 người")
    assert (reply.get("clarification") or {}).get("field") == "relax", reply
    assert agent.repo.session(sid)["clarification_questions"] == 0


def test_booking_reply_opens_the_room_it_says_it_opened(service, renter):
    """Câu đặt lịch nói "đã mở sẵn căn đó" thì view phải là detail kèm room_id."""
    sid = service.create_session(renter)["session_id"]
    _draft_with_city_and_hint(service, sid)
    draft = service._draft(sid)
    draft.budget_scope = "rent"
    service.repo.update_draft(sid, draft, service.repo.session(sid)["draft_revision"])
    service.confirm(sid, renter, service._profile_from_draft(sid),
                    service.repo.session(sid)["draft_revision"])
    reply = service.message(sid, renter, "Đặt lịch xem căn đầu tiên")
    assert reply["view"] == "detail" and reply["view_payload"]["room_id"], reply


def test_turn_that_cannot_search_yet_asks_for_the_missing_amount(agent, renter):
    """Model ghi nhận nhu cầu rồi dừng khi chưa có mức tiền: hệ thống tự hỏi mức tiền,
    giữ nguyên câu ghi nhận của model."""
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs", patch={"city": "Hà Nội", "room_type": "studio"})]),
        message(content="Mình đã ghi nhận studio ở Hà Nội."),
    ])
    reply = agent.message(sid, renter, "Mình cần một studio yên tĩnh để đi làm cho tiện")
    dto = reply.get("clarification") or {}
    assert dto.get("field") == "budget_cap", reply
    assert reply["message"].startswith("Mình đã ghi nhận studio ở Hà Nội.")
    assert dto["question"] in reply["message"]


# --- Đo live 17/11: câu no_match lặp nguyên văn qua các lượt (verbatim_repeat 3/30) ---


def _no_match_draft(service, sid: str) -> None:
    """Nháp Cầu Giấy trần 2,5 triệu: cả 3 căn giả đều vượt → no_match."""
    _draft_with_city_and_hint(service, sid)
    draft = service._draft(sid)
    draft.budget_hint_vnd = 2_500_000
    service.repo.update_draft(sid, draft, service.repo.session(sid)["draft_revision"])


def test_no_match_reply_names_search_scope_and_real_relax_chips(agent, renter):
    """Câu no_match nói ĐÃ tìm theo điều kiện gì (khu, trần đã áp) và chỉ hứa cách
    nới khi lượt thực sự kèm chip nới — số cách nới khớp số chip."""
    sid = agent.create_session(renter)["session_id"]
    _no_match_draft(agent, sid)
    agent.interpreter.client = FakeClient([message(tool_calls=[call("c1", "confirm_and_search")])])
    reply = agent.message(sid, renter, "Tìm phòng trọ dưới 2,5 triệu ở Cầu Giấy")
    assert reply["status"] == "no_match", reply.get("message")
    text = reply["message"]
    options = (reply.get("clarification") or {}).get("options") or []
    assert options, reply.get("clarification")
    assert "ở Quận Cầu Giấy, Hà Nội" in text and "trần 2,5 triệu mỗi tháng" in text, text
    assert f"Bên dưới có {len(options)} cách nới" in text, text
    # Khách chưa nêu số người → không bịa "cho 1 người" từ mặc định Scenario.
    assert "người" not in text, text
    assert "Điều kiện tìm vẫn" not in text, text


def test_no_match_repeat_with_same_conditions_is_not_verbatim(agent, renter):
    """Lượt sau tìm lại với đúng điều kiện cũ: nói rõ điều kiện chưa đổi thay vì trả
    lại nguyên văn câu trước (đo live 17/11: landmark-ho-guom#2/#3, no-match#2)."""
    sid = agent.create_session(renter)["session_id"]
    _no_match_draft(agent, sid)
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "confirm_and_search")]),
        message(tool_calls=[call("c2", "confirm_and_search")]),
    ])
    first = agent.message(sid, renter, "Tìm phòng trọ dưới 2,5 triệu ở Cầu Giấy")
    second = agent.message(sid, renter, "tìm lại giúp mình")
    assert first["status"] == second["status"] == "no_match"
    assert second["message"] != first["message"], second["message"]
    assert second["message"].startswith("Điều kiện tìm vẫn như lần tìm trước"), second["message"]


def test_no_match_after_estimate_phrase_explains_labels_already_shown(agent, renter):
    """"chấp nhận dữ liệu ước tính" không đổi điều kiện (D-12: tin thiếu dữ liệu đã
    hiện kèm nhãn) → câu chốt nói đúng điều đó, không lặp câu no_match trước."""
    sid = agent.create_session(renter)["session_id"]
    _no_match_draft(agent, sid)
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "confirm_and_search")]),
        message(tool_calls=[call("c2", "confirm_and_search")]),
    ])
    first = agent.message(sid, renter, "Tìm phòng trọ dưới 2,5 triệu ở Cầu Giấy")
    second = agent.message(sid, renter, "chấp nhận dữ liệu ước tính")
    assert second["status"] == "no_match", second.get("message")
    assert second["message"] != first["message"]
    assert "nhãn ước tính" in second["message"] and "không đổi" in second["message"], second["message"]


def test_no_match_reply_mentions_people_only_when_stated(agent, renter):
    from backend.app.agent_loop import no_match_reply, no_match_scope
    sid = agent.create_session(renter)["session_id"]
    _no_match_draft(agent, sid)
    profile = agent._profile_from_draft(sid)
    assert no_match_scope(agent, sid, profile, None)["people"] is None
    draft = agent._draft(sid)
    draft.people = 2
    agent.repo.update_draft(sid, draft, agent.repo.session(sid)["draft_revision"])
    profile = agent._profile_from_draft(sid)
    scope = no_match_scope(agent, sid, profile, None)
    text = no_match_reply({"scope": scope, "budget_vnd": profile.max_monthly_cost_vnd,
                           "relax_options": 0})
    assert "cho 2 người" in text, text
    # Không có chip nới đi kèm → hỏi, không hứa "gợi ý".
    assert text.endswith("Bạn muốn nới khu vực hoặc mức tiền không?"), text


def test_no_match_scope_ignores_legacy_estimate_flag(agent, renter):
    """D-12: accept_estimated_data là cờ lịch sử — bật cờ không tính là đổi điều kiện."""
    from backend.app.agent_loop import no_match_scope
    sid = agent.create_session(renter)["session_id"]
    _no_match_draft(agent, sid)
    profile = agent._profile_from_draft(sid)
    before = profile.model_copy(update={"accept_estimated_data": not profile.accept_estimated_data})
    assert no_match_scope(agent, sid, profile, before.model_dump_json())["unchanged"] is True
    wider = profile.model_copy(update={"area": None})
    assert no_match_scope(agent, sid, profile, wider.model_dump_json())["unchanged"] is False


def test_auto_confirm_no_match_attaches_relax_chips(agent, renter, monkeypatch):
    """Đo live 17/11 (landmark-ho-guom#1): nhánh tự tìm lại sau update_needs ra no_match
    mà không kèm chip nới → câu chốt hứa gợi ý nhưng không có nút nào."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    _no_match_draft(agent, sid)
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs", patch={"preferences": ["wifi"]})]),
        message(content="Đã ghi nhận nhu cầu của bạn."),
    ])
    reply = agent.message(sid, renter, "ghi nhận giúp mình nhu cầu vừa rồi nhé")
    assert reply["status"] == "no_match", reply.get("message")
    dto = reply.get("clarification") or {}
    assert dto.get("field") == "relax" and dto.get("options"), reply
    assert f"Bên dưới có {len(dto['options'])} cách nới" in reply["message"], reply["message"]
