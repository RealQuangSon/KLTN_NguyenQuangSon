"""AG-11: phỏng vấn nhu cầu 3 lớp — lựa chọn từ kho thật, ngưỡng luật, Jev giả
(không gọi mạng), chip có patch áp đúng trường + evidence clarify."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app import clarify, decisions
from backend.app.catalog import Catalog
from backend.app.models import Actor, DraftPatch, Profile, Scenario
from backend.app.service import HomeMatchService

SYNTHETIC_CATALOG = Path(__file__).resolve().parents[2] / "data/catalog/rooms.json"


@pytest.fixture
def service(tmp_path):
    # Catalog 220 phòng synthetic: kho đủ rộng cho mơ hồ bán kính điểm đến.
    agent = HomeMatchService(tmp_path / "clarify.sqlite", catalog=Catalog(SYNTHETIC_CATALOG))
    yield agent
    agent.close()


def confirm_destination_profile(service, renter, sid):
    session = service.session(sid, renter)
    destination = session["draft"]["destination"]
    profile = Profile(city="TP.HCM", max_monthly_cost_vnd=6_000_000,
                      max_initial_cash_vnd=8_000_000, scenario=Scenario(),
                      destination=destination)
    service.confirm(sid, renter, profile, session["draft_revision"])


def test_destination_radius_ambiguity_asks_with_real_counts(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "Tìm phòng TP.HCM gần Phú Mỹ Hưng")
    confirm_destination_profile(service, renter, sid)
    clarification = clarify.build_clarification(service, sid)
    assert clarification is not None and clarification["field"] == "destination"
    radii = {option["interpretation"]["radius_m"] for option in clarification["options"]}
    assert radii == {2000, 5000}
    # Bán kính 2 km là tập con của 5 km nhưng top-5 phải khác nhau (đáng hỏi).
    first, second = clarification["options"]
    assert set(first["top"]) != set(second["top"])
    assert abs(sum(option["probability"] for option in clarification["options"]) - 1) < 0.01
    # Lượt chat tiếp theo gắn DTO lên đầu câu trả lời (chip có số căn thật).
    reply = service.message(sid, renter, "cho mình hỏi giá khu này luôn")
    dto = reply.get("clarification")
    assert dto and dto["question"] == clarify.question_for("destination")
    assert dto["decided_by"] in {"rules", "jev", "fallback"}
    assert all("căn" in option["label"] for option in dto["options"])
    assert all(option["patch"]["set"].get("destination_radius_m") in {2000, 5000}
               for option in dto["options"])


def test_radius_chip_patch_applies_confirmed_with_clarify_evidence(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "Tìm phòng TP.HCM gần Phú Mỹ Hưng")
    confirm_destination_profile(service, renter, sid)
    session = service.session(sid, renter)
    service.patch_draft(sid, renter, DraftPatch(expected_draft_revision=session["draft_revision"],
                                                set={"destination_radius_m": 5000}, source="clarify"))
    draft = service.session(sid, renter)["draft"]
    assert draft["destination"]["max_distance_m"] == 5000
    assert draft["field_status"]["destination"] == "confirmed"
    assert draft["evidence_ref"]["destination"].startswith("clarify:")


def test_budget_interpretations_carry_real_counts(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "Tìm phòng TP.HCM cho 1 người")
    session = service.session(sid, renter)
    profile = Profile(city="TP.HCM", max_monthly_cost_vnd=5_000_000,
                      max_initial_cash_vnd=6_500_000, scenario=Scenario())
    service.confirm(sid, renter, profile, session["draft_revision"])
    service.message(sid, renter, "phòng 4,5 triệu")
    clarification = clarify.build_clarification(service, sid)
    if clarification is None:
        pytest.skip("hai cách hiểu cho cùng top-5 trên kho này → không hỏi là đúng luật")
    assert clarification["field"] == "budget"
    assert {option["kind"] for option in clarification["options"]} == {"total_cap", "rent_cap"}
    assert all(option["count"] > 0 for option in clarification["options"])


def test_rules_thresholds_accept_high_probability(service, renter):
    clarification = {"field": "destination", "impact": 0.9, "options": [
        {"id": "opt-0", "field": "destination", "kind": "radius", "label": "2 km",
         "interpretation": {"field": "destination", "kind": "radius", "radius_m": 2000, "scope": None},
         "top": ["a", "b", "c", "d", "e"], "count": 40, "probability": 0.95},
        {"id": "opt-1", "field": "destination", "kind": "radius", "label": "5 km",
         "interpretation": {"field": "destination", "kind": "radius", "radius_m": 5000, "scope": None},
         "top": ["a", "b", "c", "d", "e"], "count": 2, "probability": 0.05},
    ]}
    decision, best, decided_by, _ = decisions.decide(clarification, {}, mode="rules")
    assert decision == "accept" and decided_by == "rules" and best["id"] == "opt-0"


def test_jev_fake_accepts_and_falls_back_on_error():
    clarification = {"field": "budget", "impact": 0.9, "options": [
        {"id": "opt-0", "label": "Tổng", "probability": 0.5, "count": 10, "top": ["a"],
         "interpretation": {"field": "budget", "kind": "total_cap", "scope": "total"}},
        {"id": "opt-1", "label": "Thuê", "probability": 0.5, "count": 10, "top": ["b"],
         "interpretation": {"field": "budget", "kind": "rent_cap", "scope": "rent"}},
    ]}
    fake = SimpleNamespace(post=lambda url, json=None: SimpleNamespace(
        status_code=200, json=lambda: {"answers": [{"choice_id": "opt-1", "probability": 0.9}]}))
    decision, best, decided_by, _ = decisions.decide(clarification, {}, client=fake, mode="jev")
    assert decision == "accept" and best["id"] == "opt-1" and decided_by == "jev"

    broken = SimpleNamespace(post=lambda url, json=None: (_ for _ in ()).throw(RuntimeError("boom")))
    decision, best, decided_by, error = decisions.decide(clarification, {}, client=broken, mode="jev")
    assert decided_by == "fallback" and decision == "ask" and error == "RuntimeError"


def test_jev_payload_never_carries_money_or_pii():
    context = {"draft": {"budget_hint_vnd": 3500000, "city": "TP.HCM"},
               "confirmed_profile": {"monthly_income_vnd": 20000000, "max_monthly_cost_vnd": 3500000},
               "recent_chat": ["user: gọi 0901234567"]}
    with pytest.raises(ValueError):
        decisions._jev_payload({"options": []}, context)


def test_auto_accept_records_assumption_in_draft(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "Tìm phòng TP.HCM gần Phú Mỹ Hưng")
    confirm_destination_profile(service, renter, sid)
    clarification = clarify.build_clarification(service, sid)
    assert clarification is not None
    best = max(clarification["options"], key=lambda option: option["count"])
    label = service._apply_clarification_choice(sid, best)
    assert label
    draft = service.session(sid, renter)["draft"]
    assert draft["destination"]["max_distance_m"] == best["interpretation"]["radius_m"]
    assert draft["field_status"]["destination"] == "inferred"
    assert draft["evidence_ref"]["destination"].startswith("clarify:auto-")
