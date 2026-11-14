"""AG-02: tiền tương đối trong chat — "nới thêm N" cộng vào mức cũ, "giảm …
xuống N" là mức mới; chưa có mức cũ thì hỏi lại; FE chỉ áp khi budget_explicit."""
import json
from pathlib import Path

import pytest

from backend.app.interpreter import relative_budget
from backend.app.models import DraftPatch


def oracle_cases():
    data = json.loads((Path(__file__).resolve().parents[2] / "data/oracles/relative_budget_cases.json")
                      .read_text(encoding="utf-8"))
    return data["cases"]


def test_relative_budget_matches_the_oracle():
    for case in oracle_cases():
        got = relative_budget(case["text"])
        if case["direction"] is None:
            assert got is None, case["case_id"]
        else:
            assert got and got["direction"] == case["direction"], case["case_id"]
            assert got["amount_vnd"] == case["amount_vnd"], case["case_id"]


def test_relative_budget_semantics_oracle_v2():
    """HN-13.3-A2: thêm/bớt = delta; lên/xuống/còn (không thêm) = ĐẶT mức."""
    data = json.loads((Path(__file__).resolve().parents[2]
                       / "data/oracles/relative_budget_semantics_cases.json").read_text())
    for case in data["cases"]:
        got = relative_budget(case["text"])
        assert got and got["direction"] == case["direction"], (case["case_id"], got)
        assert got["amount_vnd"] == case["amount_vnd"], case["case_id"]


def _message(service, renter, sid, text):
    reply = service.message(sid, renter, text)
    return reply, service.repo.session(sid)


def test_relative_up_adds_to_the_previous_hint(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply, session = _message(service, renter, sid, "Tìm phòng Quận 7 tổng tháng 3,5 triệu")
    assert session["draft_json"] and reply["budget_explicit"] is True
    revision = session["draft_revision"]
    reply, session = _message(service, renter, sid, "nới thêm 1 triệu")
    import json as jsonlib
    draft = jsonlib.loads(session["draft_json"])
    assert draft["budget_hint_vnd"] == 4_500_000
    assert draft["field_status"]["budget_hint"] == "inferred"
    assert reply["budget_explicit"] is True
    # Relative turn must NOT keep the old confirmation revision usable.
    # +1 cho nháp mới, +1 cho lần tự xác nhận lại trong cùng lượt (UX-02).
    assert session["draft_revision"] == revision + 2


def test_relative_without_a_baseline_asks_instead_of_guessing(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply, _ = _message(service, renter, sid, "nới thêm 1 triệu")
    assert reply["budget_explicit"] is None
    assert any("mức tổng tháng" in question for question in reply["questions"])
    draft = service.repo.session(sid)
    import json as jsonlib
    assert jsonlib.loads(draft["draft_json"])["budget_hint_vnd"] is None


def test_down_set_reads_the_new_level(service, renter):
    sid = service.create_session(renter)["session_id"]
    _message(service, renter, sid, "tổng tháng 4 triệu")
    _, session = _message(service, renter, sid, "giảm ngân sách xuống 3 triệu")
    import json as jsonlib
    assert jsonlib.loads(session["draft_json"])["budget_hint_vnd"] == 3_000_000


def test_plain_money_still_explicit_but_chip_bug_is_gone(service, renter):
    sid = service.create_session(renter)["session_id"]
    # Câu chip cũ ("nới... lên thêm 1 triệu") giờ đọc đúng là mức cũ + 1 triệu.
    _message(service, renter, sid, "tổng tháng 3,5 triệu")
    _, session = _message(service, renter, sid,
                          "Hãy nới ngân sách tổng tháng lên thêm 1 triệu và tìm lại.")
    import json as jsonlib
    assert jsonlib.loads(session["draft_json"])["budget_hint_vnd"] == 4_500_000


import pytest as _pytest


@_pytest.mark.parametrize("text,expected", [
    ("chấp nhận dữ liệu ước tính", True),
    ("đồng ý xem phí ước tính", True),
    ("bật dữ liệu ước tính", True),
    ("không chấp nhận dữ liệu ước tính", False),
    ("có nên chấp nhận dữ liệu ước tính không?", False),
    ("không đồng ý dữ liệu ước tính", False),
    ("chưa chấp nhận dữ liệu ước tính", False),
    ("đừng bật dữ liệu ước tính", False),
    ("dữ liệu ước tính là gì", False),
    ("tìm phòng quận 7", False),
])
def test_accept_estimated_intent_table(text, expected):
    from backend.app.interpreter import accept_estimated_intent
    assert accept_estimated_intent(text) is expected
