"""Chip trả lời bám theo điều agent đang chờ, và mỗi chip là câu hệ thống hiểu được."""
from __future__ import annotations

import pytest

from backend.app.interpreter import relative_budget
from backend.app.models import Profile, Scenario


def _prompts(service, sid, renter):
    return service.results(sid, renter)["suggested_prompts"]


def test_prompts_answer_what_the_interview_still_needs(service, renter):
    # HN-13.2: chip chờ xác nhận là chip ĐỘNG từ kho (điểm mốc thật + mức tiền từ
    # phân bố, "Tiền thuê" khi thiếu phí) — hết bộ 3/5/8 và chip thành phố tĩnh.
    sid = service.create_session(renter)["session_id"]
    prompts = _prompts(service, sid, renter)
    assert prompts and len(prompts) <= 4
    # Thiếu thành phố → chip thành phố trước (hết chip tĩnh 3/5/8 ở lượt này).
    assert all(prompt.startswith("Thuê ở ") for prompt in prompts)
    service.message(sid, renter, prompts[0])
    assert service.session(sid, renter)["draft"]["city"]
    prompts = _prompts(service, sid, renter)
    budget_chip = next((p for p in prompts if p.startswith(("Tổng tháng dưới ", "Tiền thuê dưới "))), None)
    assert budget_chip, "phải có chip mức tiền đọc được từ kho"
    service.message(sid, renter, budget_chip)
    draft = service.session(sid, renter)["draft"]
    assert draft["budget_hint_vnd"] and draft["budget_hint_vnd"] > 0  # đọc tất định từ câu chip
    if budget_chip.startswith("Tiền thuê dưới "):
        assert draft["budget_scope"] == "rent"


def test_published_prompts_are_about_the_listed_rooms(service, renter, profile):
    sid = service.create_session(renter)["session_id"]
    service.confirm(sid, renter, profile, 0)
    prompts = _prompts(service, sid, renter)
    assert "Tính tổng chi phí căn đầu tiên" in prompts
    assert not {"Thuê ở TP.HCM", "Chấp nhận dữ liệu ước tính"} & set(prompts)
    for prompt in prompts:
        assert service.message(sid, renter, prompt)["status"]


def test_empty_result_prompts_match_why_it_is_empty(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "phòng trọ Quận 7 TP.HCM dưới 2 triệu")
    service.confirm(sid, renter, Profile(city="TP.HCM", area="Quận 7", max_monthly_cost_vnd=1,
                                         max_initial_cash_vnd=1, scenario=Scenario()),
                    service.session(sid, renter)["draft_revision"])
    result = service.results(sid, renter)
    assert result["status"] in ("no_match", "needs_verification")
    prompts = result["suggested_prompts"]
    assert "Đổi khu vực khác" in prompts and "Nới ngân sách thêm 1 triệu" in prompts
    before = service.session(sid, renter)["draft"]["budget_hint_vnd"]
    service.message(sid, renter, "Nới ngân sách thêm 1 triệu")
    assert service.session(sid, renter)["draft"]["budget_hint_vnd"] == before + 1_000_000


@pytest.mark.parametrize("text", ["Nới ngân sách thêm 1 triệu", "tăng trần thêm 1 triệu", "nới thêm 1 triệu"])
def test_raising_the_budget_by_name_is_relative_not_a_new_ceiling(text):
    # Trước đây "Nới ngân sách thêm 1 triệu" bị đọc thành trần mới 1 triệu.
    assert relative_budget(text) == {"direction": "up", "amount_vnd": 1_000_000}
