import re

from backend.app import agent_loop
from backend.app.agent_loop import CONFIRM_TEMPLATES, RANK_HANDOVER_PROMPT, confirm_template
from backend.app.service import HomeMatchService

# UX-09: chữ gửi người thuê không dùng từ nội bộ.
BANNED = re.compile(r"kịch bản|công bố|xác nhận hồ sơ|giả định chuẩn|[a-z]+_[a-z_]+")


def test_confirm_templates_are_plain():
    for key, text in CONFIRM_TEMPLATES.items():
        assert not BANNED.search(text), (key, text)
    assert not BANNED.search(confirm_template({"status": "no_match", "count": 0, "budget_vnd": 3000000}))
    assert "6" in confirm_template({"status": "published", "count": 5, "total_matches": 6})


def test_handover_prompt_asks_for_best_match_and_one_question():
    assert "hợp nhất" in RANK_HANDOVER_PROMPT and "MỘT điểm" in RANK_HANDOVER_PROMPT
    # Cụm cấm chỉ xuất hiện trong danh sách "không dùng".
    assert "không dùng các từ" in RANK_HANDOVER_PROMPT
    assert agent_loop.guard_output and agent_loop.check_numbers


class _Draft:
    def __init__(self, text):
        self.soft_description = text

    def model_dump_json(self):
        return "{}"


def test_published_chips_follow_what_the_renter_asked(monkeypatch):
    from backend.app import service as service_module

    def fake(text):
        class D:
            soft_description = text
            budget_hint_vnd = None
        monkeypatch.setattr(service_module.DraftProfile, "model_validate_json", lambda raw: D())
        return HomeMatchService._next_prompts({"draft_json": "{}"}, "published")

    assert "Chỉ xem căn từ 20 m²" in fake("phòng rộng khoảng 20m2 có máy lạnh")
    chips = fake("phòng yên tĩnh")
    assert "Còn căn nào rẻ hơn khu này?" not in chips and "So sánh hai căn đầu" in chips
