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
    assert session["draft_revision"] == revision + 1


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
