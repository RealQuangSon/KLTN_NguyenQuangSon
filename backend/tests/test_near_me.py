""""gần tôi": chỗ khách nhắc là của chính họ, không phải tên địa danh.

Luật dự phòng nhận ra current ("gần tôi", "gần đây", "quanh khu này") và
personal ("gần công ty tôi", "gần trường con tôi") → hệ thống hỏi lại điểm neo
(KIND_QUESTIONS + chip địa danh thật) thay vì bỏ ý khách hay tra "tôi" trong
places.json. Jev (input analyst) phân loại place_ref trong CÙNG một request;
quyết định của Jev (đủ xác suất) thắng luật khi ghi destination_kind. Mọi
model/provider là client giả kịch bản hóa; không gọi mạng.
"""
from types import SimpleNamespace

import pytest

from backend.app import input_analyst
from backend.app.agent_loop import build_tools
from backend.app.agents import ToolBox
from backend.app.clarify import KIND_QUESTIONS, blocking_field
from backend.app.interpreter import near_place_text, place_ref_hint
from backend.app.models import Actor, DraftPatch
from backend.app.service import HomeMatchService


@pytest.fixture
def demo(tmp_path, monkeypatch):
    """Service chế độ demo (luật) trên kho tổng hợp — cùng catalog các test dialog đang dùng."""
    monkeypatch.setenv("HOMEMATCH_CATALOG_PATH", "data/catalog/rooms.json")
    service = HomeMatchService(tmp_path / "near-me.sqlite")
    yield service
    service.close()


@pytest.fixture
def renter():
    return Actor(id="renter", role="renter")


class FakeJev:
    """Client giả cho analyst (theo test_multi_agent): ghi payload gửi đi, trả canned response."""

    def __init__(self, response):
        self.requests = []
        self.response = response

    def post(self, url, json=None):
        self.requests.append(json)
        return SimpleNamespace(status_code=200, json=lambda: self.response)


def jev_response(place_ref="none", place_ref_p=0.9, *, include_place_ref=True):
    """Decisions API response hợp lệ cho ba câu route + clarity + place_ref."""
    def probabilities(options, chosen, p):
        rest = round((1.0 - p) / (len(options) - 1), 4)
        return {option: (p if option == chosen else rest) for option in options}

    answers = {
        "route": {"choice": "needs",
                  "probabilities": probabilities(input_analyst.ROUTES, "needs", 0.9)},
        "clarity": {"choice": "clear",
                    "probabilities": probabilities(input_analyst.CLARITY_STATES, "clear", 0.9)}}
    if include_place_ref:
        answers["place_ref"] = {
            "choice": place_ref,
            "probabilities": probabilities(input_analyst.PLACE_REFS, place_ref, place_ref_p)}
    return {"answers": answers}


# --- 1. Luật dự phòng: place_ref_hint ---

@pytest.mark.parametrize("text, expected", [
    # current — vị trí hiện tại của khách
    ("Tìm phòng ở Hà Nội dưới 4 triệu gần tôi", "current"),
    ("Tìm phòng ở Hà Nội dưới 4 triệu gần đây", "current"),
    ("gần chỗ tôi đang ở", "current"),
    ("quanh khu này", "current"),
    ("gần nhà mình", "current"),
    ("gần chỗ này", "current"),
    ("gần vị trí của tôi", "current"),
    # personal — chỗ riêng của khách chưa nêu tên
    ("gần công ty tôi", "personal"),
    ("Tìm phòng dưới 4 triệu gần công ty tôi ở Cầu Giấy", "personal"),
    ("gần chỗ làm của em", "personal"),
    ("gần trường con tôi", "personal"),
    ("gần văn phòng của vợ tôi", "personal"),
    ("gần nhà bạn", "personal"),
    # không phải chỗ của khách
    ("dạo gần đây giá phòng tăng không", None),          # "gần đây" về thời gian
    ("thời gian gần đây tôi bận", None),
    ("mới gần đây chuyển nhà", None),
    ("gần ĐH Bách Khoa", None),                          # tên địa danh thật
    ("gần trường", None),                                # loại địa danh thật
    ("không cần gần chỗ tôi nữa", None),                 # khách tự bỏ ý "ở gần…"
    ("phòng 3 triệu ở Quận 7", None),                    # không nhắc chỗ gần
])
def test_place_ref_hint_table(text, expected):
    assert place_ref_hint(text) == expected


@pytest.mark.parametrize("text", ["gần tôi", "gần đây", "gần chỗ tôi đang ở", "gần công ty tôi"])
def test_near_place_text_pointer_is_not_a_place_name(text):
    """Từ chỉ trỏ không đẻ ra "địa danh" tra không ra chỗ."""
    assert near_place_text(text) is None


def test_near_place_text_keeps_real_landmark():
    assert near_place_text("gần ĐH Bách Khoa") == "ĐH Bách Khoa"


# --- Vòng 2 (QA): đại từ trần chỉ tính khi đứng cuối cụm; "chỗ/nơi + người" ---

@pytest.mark.parametrize("text, expected", [
    # Lỗi 1: tên riêng bắt đầu bằng đại từ → None
    ("Tìm phòng gần Minh Khai", None),      # phố Minh Khai, Hà Nội
    ("gần trường Minh Khai", None),
    ("gần chi nhánh Vietcombank", None),
    ("phòng gần Chi Lăng", None),
    ("gần Anh Đào hotel", None),
    # current: đại từ trần + từ nối/ngắn cuối cụm
    ("gần tôi nhất", "current"),
    ("gần tôi dưới 4 triệu", "current"),
    ("gần tôi, giá rẻ", "current"),
    ("gần mình thôi", "current"),
    ("gần chỗ tôi", "current"),
    # personal: chỗ/nơi + người + làm/làm việc/học; possession kéo dài
    ("gần chỗ tôi làm", "personal"),
    ("gần nơi em làm việc", "personal"),
    ("gần chỗ mình học", "personal"),
    ("gần trường em học", "personal"),
    ("gần nhà bạn tôi", "personal"),
    ("gần công ty mình ở Cầu Giấy", "personal"),
])
def test_place_ref_hint_round2_table(text, expected):
    assert place_ref_hint(text) == expected


def test_near_place_text_round2():
    assert near_place_text("gần Minh Khai") == "Minh Khai"  # tên riêng, không phải đại từ
    assert near_place_text("gần chỗ tôi làm") is None


# --- Vòng 2 (QA lỗi 3): báo thật khi chưa dùng được chỗ của khách ---

CITY_NOTICE = ("Mình chưa biết vị trí của bạn nên đang tìm trong cả Hà Nội; "
               "gõ tên trường, công ty hoặc địa chỉ để mình tìm quanh đó.")
AREA_NOTICE = ("Mình chưa biết chính xác chỗ đó nên đang tìm trong Quận Cầu Giấy; "
               "gõ tên trường, công ty hoặc địa chỉ để mình tìm quanh đó.")


def test_demo_published_without_chips_appends_city_notice(tmp_path, renter, monkeypatch):
    """Không dựng được chip điểm neo (kho không có địa danh quanh đó có căn) thì
    lượt vẫn tìm, nhưng phải NÓI THẬT là đang tìm trong cả thành phố. Dùng kho
    mặc định như lỗi gốc 22/11 (service không đặt HOMEMATCH_CATALOG_PATH).
    Vòng 3: lượt này vừa đổi kind vừa tạo run — câu báo xuất hiện đúng MỘT lần.
    đổi câu thành "gần chỗ tôi làm" (kind personal) — "gần tôi" giờ LUÔN
    hỏi lại điểm neo vì chip "Dùng vị trí hiện tại" luôn dựng được."""
    from backend.app import clarify as clarify_layer
    monkeypatch.delenv("HOMEMATCH_CATALOG_PATH", raising=False)
    monkeypatch.setattr(clarify_layer, "_destination_interpretations", lambda *args, **kwargs: [])
    service = HomeMatchService(tmp_path / "near-me-no-chips.sqlite")
    try:
        sid = service.create_session(renter)["session_id"]
        reply = service.message(sid, renter, "Tìm phòng ở Hà Nội dưới 4 triệu gần chỗ tôi làm")
        assert reply["status"] == "published"
        assert reply["message"].count("Mình chưa biết") == 1
        assert reply["message"].endswith(CITY_NOTICE)
    finally:
        service.close()


# --- Vòng 3 (QA): personal hai đại từ / "chỗ làm" trần; câu báo không lặp ---

@pytest.mark.parametrize("text", [
    "gần chỗ con tôi học", "gần chỗ vợ tôi làm", "gần nơi chồng em làm việc",
    "gần chỗ bạn tôi làm", "gần chỗ làm", "gần chỗ làm nhé", "gần nơi học",
])
def test_place_ref_hint_round3_personal(text):
    assert place_ref_hint(text) == "personal"
    assert near_place_text(text) is None


def test_place_ref_hint_round3_own_name_after_lam():
    """Sau "làm" không phải đuôi bare tail → vẫn là tên điểm mốc."""
    assert place_ref_hint("gần chỗ làm móng Hoa") is None
    assert near_place_text("gần chỗ làm móng Hoa") == "chỗ làm móng Hoa"


def test_own_place_notice_only_on_reasonable_turns(demo, renter):
    """Lỗi 5: câu báo chỉ ở lượt có lý do (đổi kind / tạo run mới), không lặp ở
    mọi lượt sau trên cùng kết quả."""
    sid = demo.create_session(renter)["session_id"]
    reply = demo.message(sid, renter,
                         "Tìm phòng trọ gần công ty tôi ở Cầu Giấy, tổng tiền mỗi tháng dưới 4 triệu")
    assert reply["message"].count("Mình chưa biết") == 1
    # Bấm chip "Trần TỔNG THÁNG" → published (đường patch_draft, không qua message).
    revision = demo.session(sid, renter)["draft_revision"]
    after = demo.patch_draft(sid, renter, DraftPatch(expected_draft_revision=revision,
                                                     set={"budget_scope": "total"}, source="clarify"))
    assert after["status"] == "published"
    # Các lượt hỏi chuyện trên kết quả đã có: không lặp lại câu báo.
    for follow_up in ("phòng nào rẻ nhất?", "cảm ơn"):
        answer = demo.message(sid, renter, follow_up)
        assert "Mình chưa biết" not in (answer.get("message") or ""), follow_up


def test_demo_personal_no_money_appends_area_notice(demo, renter):
    """"công ty tôi ở Cầu Giấy" chưa nêu tiền: lượt hỏi chip tiền, message nói thật
    đang tìm trong Quận Cầu Giấy chứ chưa dùng được chỗ công ty."""
    sid = demo.create_session(renter)["session_id"]
    reply = demo.message(sid, renter, "Tìm phòng trọ gần công ty tôi ở Cầu Giấy")
    assert reply["draft"]["destination_kind"] == "personal"
    assert (reply.get("clarification") or {}).get("field") != "destination"
    assert reply["message"].endswith(AREA_NOTICE)


def test_demo_named_landmark_gets_no_own_place_notice(demo, renter):
    """Câu nhắc tên địa danh thật không có câu "chưa biết vị trí"."""
    sid = demo.create_session(renter)["session_id"]
    reply = demo.message(sid, renter, "Tìm phòng ở Hà Nội dưới 4 triệu gần ĐH Bách Khoa")
    assert "Mình chưa biết" not in (reply.get("message") or "")


# --- 2. Chế độ demo qua service.message: hỏi lại điểm neo ---

@pytest.mark.parametrize("text", ["Tìm phòng ở Hà Nội dưới 4 triệu gần tôi",
                                  "Tìm phòng ở Hà Nội dưới 4 triệu gần đây"])
def test_demo_near_me_asks_for_anchor(demo, renter, text):
    sid = demo.create_session(renter)["session_id"]
    reply = demo.message(sid, renter, text)
    assert reply["status"] != "published"
    assert not reply.get("active_run_id"), "chưa có điểm neo thì không chạy lượt tìm"
    dto = reply["clarification"]
    assert dto["field"] == "destination"
    assert dto["question"] == KIND_QUESTIONS["current"]
    assert dto["options"], "chip là địa danh thật trong danh mục, không lọc theo loại"
    assert reply["draft"]["destination_kind"] == "current"
    assert reply["draft"]["needs_destination"] is True
    assert reply["draft"]["destination"] is None


def test_demo_personal_with_district_is_not_blocked(demo, renter):
    """"công ty tôi ở Cầu Giấy" đã có quận → tìm trong quận đó, câu hỏi điểm neo không chặn."""
    sid = demo.create_session(renter)["session_id"]
    reply = demo.message(sid, renter, "Tìm phòng dưới 4 triệu gần công ty tôi ở Cầu Giấy")
    assert reply["draft"]["destination_kind"] == "personal"
    assert reply["draft"]["area"] == "Quận Cầu Giấy"
    assert (reply.get("clarification") or {}).get("field") != "destination"
    assert blocking_field(demo, sid) is None


def test_demo_anchor_set_and_search_runs_after_answer(demo, renter):
    """Sau câu hỏi, khách gõ tên địa danh có trong danh mục: điểm neo được đặt và lượt tìm chạy."""
    sid = demo.create_session(renter)["session_id"]
    demo.message(sid, renter, "Tìm phòng ở Hà Nội dưới 4 triệu gần tôi")
    reply = demo.message(sid, renter, "gần Đại học Bách Khoa Hà Nội")
    destination = reply["draft"]["destination"]
    assert destination and destination["label"] == "Đại học Bách Khoa Hà Nội"
    # Lượt đặt điểm mốc luôn kèm chip bán kính (luật AG-11 cũ); khách bấm chip → tìm.
    revision = demo.session(sid, renter)["draft_revision"]
    after = demo.patch_draft(sid, renter, DraftPatch(expected_draft_revision=revision,
                                                     set={"destination_radius_m": 2000},
                                                     source="clarify"))
    assert after["status"] == "published"
    assert demo.results(sid, renter)["status"] == "published"
    assert demo._draft(sid).destination is not None


# --- 3. Input analyst: câu hỏi place_ref thứ ba, cùng một request ---

def test_analyze_jev_place_ref_in_same_payload(demo, renter):
    sid = demo.create_session(renter)["session_id"]
    fake = FakeJev(jev_response(place_ref="current"))
    analysis = input_analyst.analyze(demo, demo.repo.session(sid), "gần tôi",
                                     has_results=False, phase="interview",
                                     mode="jev", client=fake)
    assert analysis["place_ref"] == "current"
    assert analysis["decided_by"] == "jev"
    assert len(fake.requests) == 1, "không thêm lượt gọi Jev"
    assert "place_ref" in fake.requests[0]["questions"]


def test_analyze_jev_low_probability_place_ref_falls_back_to_rules(demo, renter):
    """Vòng 2 (QA lỗi 4): xác suất place_ref thấp chỉ lấy luật cho riêng place_ref,
    decided_by (nhãn quyết định route) vẫn là "jev"."""
    sid = demo.create_session(renter)["session_id"]
    analysis = input_analyst.analyze(demo, demo.repo.session(sid), "gần tôi",
                                     has_results=False, phase="interview",
                                     mode="jev", client=FakeJev(jev_response(place_ref="none",
                                                                             place_ref_p=0.4)))
    assert analysis["place_ref"] == "current"  # luật
    assert analysis["decided_by"] == "jev"


@pytest.mark.parametrize("response", [
    jev_response(include_place_ref=False),                       # thiếu place_ref
    {"answers": {"route": {"choice": "needs",
                           "probabilities": {r: 0.25 for r in input_analyst.ROUTES}},
                 "clarity": {"choice": "clear",
                             "probabilities": {s: 0.5 for s in input_analyst.CLARITY_STATES}},
                 "place_ref": {"choice": "current",             # tổng xác suất sai
                               "probabilities": {r: 0.9 for r in input_analyst.PLACE_REFS}}}},
], ids=["missing", "bad-probabilities"])
def test_analyze_invalid_place_ref_falls_back_to_rules(demo, renter, response):
    sid = demo.create_session(renter)["session_id"]
    analysis = input_analyst.analyze(demo, demo.repo.session(sid), "gần tôi",
                                     has_results=False, phase="interview",
                                     mode="jev", client=FakeJev(response))
    assert analysis["place_ref"] == "current"  # luật
    assert analysis["decided_by"] == "fallback"


def test_analyze_rules_mode_maps_law_values(demo, renter):
    sid = demo.create_session(renter)["session_id"]
    named = input_analyst.analyze(demo, demo.repo.session(sid), "gần ĐH Bách Khoa",
                                  has_results=False, phase="interview", mode="rules")
    assert named["place_ref"] == "named"
    none = input_analyst.analyze(demo, demo.repo.session(sid), "phòng 3 triệu ở Quận 7",
                                 has_results=False, phase="interview", mode="rules")
    assert none["place_ref"] == "none"


# --- 4. Jev thắng luật khi ghi destination_kind (gọi thẳng _apply_chat_extras) ---

def test_jev_place_ref_current_wins_when_law_misses(demo, renter):
    sid = demo.create_session(renter)["session_id"]
    assert place_ref_hint("tìm phòng đi bộ ra chỗ tôi được") is None  # luật không bắt được
    demo._apply_chat_extras(sid, "tìm phòng đi bộ ra chỗ tôi được", place_ref="current")
    draft = demo._draft(sid)
    assert draft.destination_kind == "current"
    assert draft.needs_destination is True


def test_jev_place_ref_named_drops_rules_current(demo, renter):
    sid = demo.create_session(renter)["session_id"]
    assert place_ref_hint("gần tôi") == "current"  # luật nói current
    demo._apply_chat_extras(sid, "gần tôi", place_ref="named")
    draft = demo._draft(sid)
    assert draft.destination_kind is None
    assert draft.needs_destination is False


def test_jev_place_ref_named_keeps_rules_school(demo, renter):
    """"named" chỉ bỏ current/personal của luật; school/hospital/transit giữ nguyên."""
    sid = demo.create_session(renter)["session_id"]
    demo._apply_chat_extras(sid, "gần trường", place_ref="named")
    assert demo._draft(sid).destination_kind == "school"


# --- 5. find_place không tra từ chỉ trỏ ---

def test_find_place_rejects_own_place_pointer(demo, renter):
    sid = demo.create_session(renter)["session_id"]
    tools = build_tools(demo, demo.repo.session(sid), renter, "gần tôi", ToolBox(),
                        demo._agent_phase(sid), "needs")
    result = tools["find_place"]["fn"]("tôi")
    assert result["found"] is False
    assert result["reason"] == "own_place"
    assert 'ask_user(field="destination")' in result["note"]
