"""AG-11: phỏng vấn nhu cầu 3 lớp — lựa chọn từ kho thật, ngưỡng luật, Jev giả
(không gọi mạng), chip có patch áp đúng trường + evidence clarify."""
from pathlib import Path
from types import SimpleNamespace
from collections import Counter
import json

import pytest

from backend.app import clarify, decisions
from backend.app.catalog import Catalog
from backend.app.locations import resolve_place
from backend.app.models import Actor, Destination, DraftPatch, DraftProfile, Profile, Scenario
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
    clarification = clarify.build_clarification(service, sid, field="destination_radius")
    assert clarification is not None and clarification["field"] == "destination_radius"
    radii = {option["interpretation"]["radius_m"] for option in clarification["options"]}
    # HN-13.2: mức ĐANG TẠM DÙNG (3 km mặc định) phải nằm trong chip.
    assert radii == {2000, 3000, 5000}
    # Bán kính 2 km là tập con của 5 km nhưng top-5 phải khác nhau (đáng hỏi).
    by_radius = {option["interpretation"]["radius_m"]: option for option in clarification["options"]}
    first, second = by_radius[2000], by_radius[5000]
    assert set(first["top"]) != set(second["top"])
    assert abs(sum(option["probability"] for option in clarification["options"]) - 1) < 0.01
    # Lượt chat tiếp theo gắn DTO lên đầu câu trả lời (chip có số căn thật).
    reply = service.message(sid, renter, "cho mình hỏi giá khu này luôn")
    dto = reply.get("clarification")
    # HN-13.2: alias "destination"→radius đã bỏ (destination là field riêng);
    # chip ở đây là destination_radius nên dùng question_for đúng field.
    assert dto and dto["question"] == clarify.question_for("destination_radius")
    assert dto["decided_by"] in {"rules", "jev", "fallback"}
    assert all("căn" in option["label"] for option in dto["options"])
    assert all(option["patch"]["set"].get("destination_radius_m") in {2000, 3000, 5000}
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
    clarification = clarify.build_clarification(service, sid, field="budget_scope")
    if clarification is None:
        pytest.skip("hai cách hiểu cho cùng top-5 trên kho này → không hỏi là đúng luật")
    assert clarification["field"] == "budget_scope"
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
        status_code=200, json=lambda: {"answers": {"clarify": {
            "type": "choice", "choice": "opt-1", "probabilities": {"opt-0": 0.1, "opt-1": 0.9},
            "confidence": 0.8}}}))
    decision, best, decided_by, _ = decisions.decide(clarification, {}, client=fake, mode="jev")
    assert decision == "accept" and best["id"] == "opt-1" and decided_by == "jev"
    # Chip xếp lại theo xác suất của Jev.
    assert [option["id"] for option in clarification["options"]] == ["opt-1", "opt-0"]

    unsure = SimpleNamespace(post=lambda url, json=None: SimpleNamespace(
        status_code=200, json=lambda: {"answers": {"clarify": {
            "type": "choice", "choice": "opt-0", "probabilities": {"opt-0": 0.6, "opt-1": 0.4}}}}))
    decision, best, decided_by, _ = decisions.decide(clarification, {}, client=unsure, mode="jev")
    assert decision == "ask" and best["id"] == "opt-0" and decided_by == "jev"

    broken = SimpleNamespace(post=lambda url, json=None: (_ for _ in ()).throw(RuntimeError("boom")))
    decision, best, decided_by, error = decisions.decide(clarification, {}, client=broken, mode="jev")
    assert decided_by == "fallback" and decision == "ask" and error == "RuntimeError"


def test_jev_payload_matches_decisions_api_shape():
    clarification = {"field": "destination", "options": [
        {"id": "opt-0", "label": "Trong 2 km"}, {"id": "opt-1", "label": "Trong 5 km"}]}
    body = decisions._jev_payload(clarification, {"draft": {"city": "Hà Nội"}})
    assert body["state"] == {"draft": {"city": "Hà Nội"}}
    question = body["questions"]["clarify"]
    assert question["type"] == "choice" and question["instructions"]
    assert question["criteria"] == {"opt-0": "Trong 2 km", "opt-1": "Trong 5 km"}


@pytest.mark.parametrize("bad", ["invalid", float("nan"), float("inf"), -0.1, 1.1])
def test_jev_invalid_probabilities_keep_rules_unchanged(bad):
    clarification = {"options": [
        {"id": "a", "label": "A", "probability": 0.5},
        {"id": "b", "label": "B", "probability": 0.5}]}
    fake = SimpleNamespace(post=lambda *args, **kwargs: SimpleNamespace(
        status_code=200, json=lambda: {"answers": {"clarify": {
            "choice": "a", "probabilities": {"a": 0.99, "b": bad}}}}))
    decision, _, decided_by, error = decisions.decide(clarification, {}, client=fake, mode="jev")
    assert (decision, decided_by, error) == ("ask", "fallback", "ValueError")
    assert [option["probability"] for option in clarification["options"]] == [0.5, 0.5]


def test_jev_payload_never_carries_money_or_pii():
    context = {"draft": {"budget_hint_vnd": 3500000, "city": "TP.HCM"},
               "confirmed_profile": {"monthly_income_vnd": 20000000, "max_monthly_cost_vnd": 3500000},
               "nested": {"scenario": {"moving_vnd": 300000}, "loan": {"principal_vnd": 3000000}},
               "recent_chat": ["user: gọi 0901234567, son@example.com, phòng 3,5 triệu", "thu nhập 20000000",
                               "thu nhập 20.000.000"],
               "count": 12}
    body = decisions._jev_payload({"options": [{"id": "a", "label": "4.000.000 ₫, son@example.com"}]}, context)
    blob = json.dumps(body, ensure_ascii=False)
    for forbidden in ("monthly_income_vnd", "20000000", "3500000", "300000", "0901234567",
                      "son@example.com", "3,5 triệu", "4.000.000", "20.000.000", "principal_vnd", '"loan"'):
        assert forbidden not in blob
    assert body["state"]["count"] == 12
    assert context["confirmed_profile"]["monthly_income_vnd"] == 20000000


def test_auto_accept_records_assumption_in_draft(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "Tìm phòng TP.HCM gần Phú Mỹ Hưng")
    # Chưa xác nhận trần bán kính: tự diễn giải không được nới hồ sơ đã chốt.
    revision = service.session(sid, renter)["draft_revision"]
    service._apply_chat_budget_hint(sid, 6_000_000, revision)
    clarification = clarify.build_clarification(service, sid)
    assert clarification is not None
    best = max(clarification["options"], key=lambda option: option["count"])
    label = service._apply_clarification_choice(sid, best)
    assert label
    draft = service.session(sid, renter)["draft"]
    assert draft["destination"]["max_distance_m"] == best["interpretation"]["radius_m"]
    assert draft["field_status"]["destination"] == "inferred"
    assert draft["evidence_ref"]["destination"].startswith("clarify:auto-")


def _draft_for_field(service, renter, field):
    sid = service.create_session(renter)["session_id"]
    draft = DraftProfile(city="TP.HCM", budget_hint_vnd=10_000_000, budget_scope="total",
                         room_type=None if field == "room_type" else "room",
                         people=None if field == "people" else 1)
    if field == "destination_radius":
        place = resolve_place("Phú Mỹ Hưng", "TP.HCM")
        draft.destination = Destination(label=place["label"], latitude=place["latitude"],
                                        longitude=place["longitude"], uncertainty_m=place["uncertainty_m"],
                                        max_distance_m=3000)
    service.repo.update_draft(sid, draft, 0)
    return sid, draft


@pytest.mark.parametrize("field", ["area", "room_type", "people"])
def test_new_field_options_have_real_counts_costs_and_patches(service, renter, field):
    sid, draft = _draft_for_field(service, renter, field)
    clarification = clarify.build_clarification(service, sid, field=field)
    assert clarification is not None and clarification["field"] == field
    assert 2 <= len(clarification["options"]) <= 3
    for option in clarification["options"]:
        profile = clarify._temp_profile(service, draft, option["interpretation"], None)
        candidates, _ = service.catalog.rank(profile, service.matching_method)
        monthly = [item.cost.monthly_total_vnd for item in candidates if item.cost.monthly_total_vnd is not None]
        assert option["count"] == len(candidates)
        assert option["top"] == [item.room_id for item in candidates[:5]]
        assert option["min_monthly_total_vnd"] == (min(monthly) if monthly else None)
        assert clarify.option_patch(option) == {"set": {field: option["interpretation"]["value"]}}
    dto = clarify.to_dto(clarification, "jev")
    assert dto["decided_by"] == "jev"
    assert all(option["decided_by"] == "jev" and option["count"] > 0 and option["patch"]
               for option in dto["options"])
    assert all(set(clarify.CHIP_KEYS).issubset(option) for option in dto["options"])


def test_counts_cover_full_eligible_set_instead_of_only_top_five(service, renter):
    sid, draft = _draft_for_field(service, renter, "area")
    profile = service._profile_from_draft(sid)
    top, count, minimum, held = clarify._match_top(service, profile)
    candidates, _ = service.catalog.rank(profile, service.matching_method)
    assert count == len(candidates) > 5 and len(top) == 5
    assert minimum == min(item.cost.monthly_total_vnd for item in candidates
                          if item.cost.monthly_total_vnd is not None)
    area_counts = Counter(item.area for item in candidates)
    options = clarify._interpretations(draft, service, profile=profile, field="area")
    assert [option["value"] for option in options] == sorted(
        area_counts, key=lambda area: (-area_counts[area], area))[:3]


def test_impact_compares_every_pair_and_treats_empty_sets_as_equal():
    assert clarify._impact([{"top": []}, {"top": []}]) == 0
    assert clarify._impact([{"top": ["a"]}, {"top": ["a"]}, {"top": ["b"]}]) == 1
    assert clarify._impact([{"top": ["a", "b"]}, {"top": ["a", "b"]}]) == 0


def test_distinct_ambiguity_fields_are_never_mixed(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "Tìm phòng TP.HCM gần Phú Mỹ Hưng")
    revision = service.session(sid, renter)["draft_revision"]
    service._apply_chat_budget_hint(sid, 6_000_000, revision)
    clarification = clarify.build_clarification(service, sid)
    assert clarification is not None and clarification["field"] == "destination_radius"
    assert {option["field"] for option in clarification["options"]} == {"destination_radius"}
    assert all(option["kind"] == "radius" for option in clarification["options"])
    # HN-13.2: "destination" giờ là field RIÊNG (chip điểm mốc thật) — destination
    # đã đặt nên nhóm này rỗng; alias cũ budget → budget_scope giữ nguyên.
    assert clarify.canonical_field("budget") == "budget_scope"
    assert clarify.build_clarification(service, sid, field="destination") is None
    assert clarify.question_for("budget") == clarify.question_for("budget_scope")


@pytest.mark.parametrize("field, tracked", [
    ("destination_radius", "destination"), ("budget_scope", "budget_scope"),
    ("area", "area"), ("room_type", "room_type"), ("people", "people"),
])
@pytest.mark.parametrize("resolved_by", ["confirmed", "clarify:auto-r2", "clarify:r2"])
def test_resolved_fields_do_not_generate_another_question(service, renter, field, tracked, resolved_by):
    sid, draft = _draft_for_field(service, renter, field)
    draft.budget_scope = None
    if resolved_by == "confirmed":
        draft.field_status[tracked] = "confirmed"
    else:
        draft.evidence_ref[tracked] = resolved_by
    session = service.session(sid, renter)
    service.repo.update_draft(sid, draft, session["draft_revision"])
    assert clarify.build_clarification(service, sid, field=field) is None


def test_no_question_for_empty_catalog_or_unknown_field(service, renter, monkeypatch):
    sid, _ = _draft_for_field(service, renter, "people")
    monkeypatch.setattr(service.catalog, "rank", lambda *args: ([], {}))
    assert clarify.build_clarification(service, sid) is None
    assert clarify.build_clarification(service, sid, field="other") is None


@pytest.mark.parametrize("response, code", [
    ({"choice": "missing", "probabilities": {"a": 0.5, "b": 0.5}}, "RuntimeError"),
    ({"choice": "a", "probabilities": {"a": 0.9}}, "ValueError"),
    ({"choice": "a", "probabilities": {"a": 0.9, "b": 0.9}}, "ValueError"),
    ({"choice": "a", "probabilities": {"a": 0.1, "b": 0.1}}, "ValueError"),
    ({"choice": "a", "probabilities": {"a": True, "b": False}}, "ValueError"),
])
def test_jev_malformed_distribution_uses_original_rules(response, code):
    clarification = {"field": "budget_scope", "options": [
        {"id": "a", "label": "Tổng", "probability": 0.5},
        {"id": "b", "label": "Thuê", "probability": 0.5}]}
    fake = SimpleNamespace(post=lambda *args, **kwargs: SimpleNamespace(
        status_code=200, json=lambda: {"answers": {"clarify": response}}))
    decision, _, decided_by, error = decisions.decide(clarification, {}, client=fake, mode="jev")
    assert (decision, decided_by, error) == ("ask", "fallback", code)
    assert [option["probability"] for option in clarification["options"]] == [0.5, 0.5]


@pytest.mark.parametrize("failure", ["timeout", "http_error", "invalid_json", "success"])
def test_jev_owned_client_is_closed_on_provider_failures(monkeypatch, failure):
    import httpx
    closed = []

    def post(*args, **kwargs):
        if failure == "timeout":
            raise TimeoutError("Không được gửi nội dung lỗi cho model")
        if failure == "success":
            return SimpleNamespace(status_code=200, json=lambda: {"answers": {"clarify": {
                "choice": "a", "probabilities": {"a": 0.9, "b": 0.1}}}})
        return SimpleNamespace(status_code=503 if failure == "http_error" else 200,
                               json=lambda: (_ for _ in ()).throw(ValueError("bad JSON")))

    fake = SimpleNamespace(post=post, close=lambda: closed.append(True))
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: fake)
    clarification = {"field": "budget_scope", "options": [
        {"id": "a", "label": "Tổng", "probability": 0.5},
        {"id": "b", "label": "Thuê", "probability": 0.5}]}
    decision, _, decided_by, _ = decisions.decide(clarification, {}, mode="jev")
    assert (decision, decided_by) == (("accept", "jev") if failure == "success" else ("ask", "fallback"))
    assert closed == [True]


def test_jev_does_not_close_a_client_owned_by_the_caller():
    closed = []
    fake = SimpleNamespace(
        post=lambda *args, **kwargs: SimpleNamespace(status_code=200, json=lambda: {"answers": {"clarify": {
            "choice": "a", "probabilities": {"a": 0.9, "b": 0.1}}}}),
        close=lambda: closed.append(True))
    clarification = {"field": "budget_scope", "options": [
        {"id": "a", "label": "Tổng", "probability": 0.5},
        {"id": "b", "label": "Thuê", "probability": 0.5}]}
    assert decisions.decide(clarification, {}, client=fake, mode="jev")[2] == "jev"
    assert closed == []


def test_jev_empty_options_fall_back_without_crashing():
    assert decisions.decide({"options": []}, {}, mode="rules") == ("ask", None, "rules", None)
    fake = SimpleNamespace(post=lambda *args, **kwargs: pytest.fail("Không gọi provider khi thiếu lựa chọn"))
    decision, best, decided_by, error = decisions.decide({"options": []}, {}, client=fake, mode="jev")
    assert (decision, best, decided_by, error) == ("ask", None, "fallback", "ValueError")
