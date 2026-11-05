"""AG-02: the simulate_finance chat intent.

The finance agent answers a loan what-if from chat with numbers produced only by
the deterministic finance tool — the same calculation as POST /sessions/{id}/simulate.
Utterance parsing is validated against the independent oracle
data/oracles/loan_parse_cases.json (DA-02). All providers stay offline fakes.
"""
import json
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.interpreter import OpenAIInterpreter, fixed_intent, parse_loan_terms
from backend.app.models import (DomainError, DraftProfile, LoanTerms, Profile, Review, Scenario,
                                SimulationRequest)
from backend.app.schemas import MessageResult
from backend.app.service import HomeMatchService

ROOT = Path(__file__).parents[2]
LOAN_CASES = json.loads((ROOT / "data" / "oracles" / "loan_parse_cases.json").read_text(encoding="utf-8"))
QUESTION = "nếu vay 12 tháng lãi 12% thì sao"


def chat_profile(**changes) -> Profile:
    # Confirmed loan 12%/6 months; the chat question overrides the term to 12.
    values = dict(city="TP.HCM", area="Quận 7", max_monthly_cost_vnd=3_700_000,
                  max_initial_cash_vnd=4_000_000, monthly_income_vnd=12_000_000,
                  loan=LoanTerms(annual_rate=Decimal("0.12"), term_months=6), scenario=Scenario())
    return Profile(**{**values, **changes})


def approved(service, renter, landlord, profile) -> str:
    """Published shortlist built like test_landlord.py/test_finance.py."""
    session_id = service.create_session(renter)["session_id"]
    run_id = service.confirm(session_id, renter, profile, 0)["run_id"]
    service.review(run_id, landlord, Review(decision="approve", expected_profile_version=1,
                                            reason="Đã kiểm tra.", idempotency_key="k"))
    return session_id


def test_loan_question_matches_the_simulate_endpoint(service, renter, landlord):
    session_id = approved(service, renter, landlord, chat_profile())
    visible = service.results(session_id, renter)["results"]
    reply = service.message(session_id, renter, QUESTION)
    assert reply["intent"] == "simulate_finance" and reply["status"] == "simulation"
    simulation = reply["simulation"]
    # No room named in the question: the first approved room is simulated.
    assert simulation["room_id"] == visible[0]["room_id"]
    assert simulation["room_title"] == visible[0]["title"]
    assert simulation["scenario"]["annual_rate"] == 12.0 and simulation["scenario"]["term_months"] == 12
    # Exact parity with the simulate endpoint for the same scenario.
    expected = service.simulate(session_id, renter, SimulationRequest.model_validate({
        "room_id": simulation["room_id"],
        "scenarios": [{"label": simulation["result"]["label"],
                       "loan": {"annual_rate": "0.12", "term_months": 12}}]}))
    assert simulation["result"] == expected["items"][0]
    loan = simulation["result"]["cost"]["affordability"]["loan"]
    assert simulation["scenario"]["principal_vnd"] == loan["principal_vnd"]
    # The templated reply carries the tool's numbers and never the income.
    assert "trả góp" in reply["message"] and "12 tháng" in reply["message"]
    assert "12.000.000" not in reply["message"]


def test_loan_simulation_leaves_profile_and_run_untouched(service, renter, landlord):
    session_id = approved(service, renter, landlord, chat_profile())
    run_id = service.session(session_id, renter)["active_run_id"]
    before_session, before_run = service.session(session_id, renter), service.repo.run(run_id)
    service.message(session_id, renter, QUESTION)
    assert service.session(session_id, renter) == before_session
    assert service.repo.run(run_id) == before_run


def test_named_room_inside_the_shortlist_is_simulated(service, renter, landlord):
    session_id = approved(service, renter, landlord, chat_profile())
    target = service.results(session_id, renter)["results"][-1]["room_id"]
    reply = service.message(session_id, renter, f"phòng {target} nếu vay 12 tháng lãi 12% thì sao")
    assert reply["status"] == "simulation" and reply["simulation"]["room_id"] == target


def test_named_room_outside_the_shortlist_is_refused(service, renter, landlord):
    session_id = service.create_session(renter)["session_id"]
    run_id = service.confirm(session_id, renter, chat_profile(), 0)["run_id"]
    ids = [item["room_id"] for item in service.draft(run_id, landlord)["items"]]
    service.review(run_id, landlord, Review(decision="approve", expected_profile_version=1, reason="Đã kiểm tra.",
                                            idempotency_key="k", keep_room_ids=ids[:1],
                                            override_reason="Chỉ duyệt một phòng cho ca kiểm tra."))
    with pytest.raises(DomainError) as hidden:
        service.message(session_id, renter, f"phòng {ids[-1]} nếu vay 12 tháng lãi 12% thì sao")
    assert hidden.value.code == "not_visible"


def test_without_an_approved_shortlist_the_agent_asks_for_results(service, renter):
    session_id = service.create_session(renter)["session_id"]
    reply = service.message(session_id, renter, QUESTION)
    assert reply["intent"] == "simulate_finance" and reply["status"] == "needs_results"
    assert reply["message"] == "Bạn cần có danh sách phòng đã được chủ nhà duyệt trước khi mô phỏng vay."
    assert "simulation" not in reply


def test_missing_rate_without_a_profile_loan_asks_and_never_invents_numbers(service, renter, landlord):
    # Enough cash to be approved without a loan, so the profile carries no rate either.
    session_id = approved(service, renter, landlord,
                          chat_profile(loan=None, max_initial_cash_vnd=9_000_000, max_monthly_cost_vnd=3_500_000))
    reply = service.message(session_id, renter, "nếu vay 12 tháng thì sao")
    assert reply["status"] == "needs_clarification" and reply["intent"] == "simulate_finance"
    text = " ".join(reply["questions"]) + (reply.get("message") or "")
    assert "lãi suất" in text
    # No instalment or money figure is fabricated while asking.
    assert "trả góp" not in text
    assert not re.search(r"\d[\d.,]*\s*(?:triệu|đ)\b", text)


def test_term_above_the_loan_bound_asks_instead_of_clamping(service, renter, landlord):
    session_id = approved(service, renter, landlord, chat_profile())
    reply = service.message(session_id, renter, "nếu vay 48 tháng thì sao")
    assert reply["status"] == "needs_clarification" and "36 tháng" in " ".join(reply["questions"])


def test_no_shortfall_reports_that_no_loan_is_needed(service, renter, landlord):
    session_id = approved(service, renter, landlord,
                          chat_profile(loan=None, max_initial_cash_vnd=9_000_000, max_monthly_cost_vnd=3_500_000))
    reply = service.message(session_id, renter, QUESTION)
    assert reply["status"] == "simulation"
    assert reply["simulation"]["result"]["cost"]["affordability"]["loan"] is None
    assert "không phát sinh khoản vay" in reply["message"]
    assert reply["simulation"]["scenario"]["principal_vnd"] is None


def test_openai_mode_never_calls_the_model_for_the_loan_question(tmp_path, renter, landlord, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_LLM_MODE", "openai")
    calls = []

    def parse(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status="completed",
                               output_parsed={"intent": "find_room", "city": None, "area": None, "people": None,
                                              "preferences": [], "needs_destination": False},
                               usage=SimpleNamespace(total_tokens=7))

    service = HomeMatchService(tmp_path / "ledger.sqlite", interpreter=OpenAIInterpreter(
        client=SimpleNamespace(responses=SimpleNamespace(parse=parse)), model="gpt-4o"))
    try:
        session_id = approved(service, renter, landlord, chat_profile())
        reply = service.message(session_id, renter, QUESTION)
        assert calls == [] and reply["intent"] == "simulate_finance" and reply["status"] == "simulation"
        assert reply["usage"]["logical_calls"] == 0
    finally:
        service.close()


def test_message_result_schema_accepts_the_simulation_payload():
    payload = {"session_id": "s", "draft_revision": 0, "draft": DraftProfile().model_dump(),
               "profile_version": 1, "confirmed_profile": None, "active_run_id": None,
               "usage": {"logical_calls": 0, "tokens": None, "mode": "demo_rules"}}
    simulated = MessageResult.model_validate({**payload, "intent": "simulate_finance", "status": "simulation",
        "simulation": {"room_id": "demo-01", "room_title": "Phòng Quận 7",
                       "scenario": {"annual_rate": 12.0, "term_months": 12, "principal_vnd": 1_500_000},
                       "result": {}}})
    assert simulated.simulation["scenario"]["term_months"] == 12
    assert MessageResult.model_validate({**payload, "intent": "simulate_finance",
                                         "status": "needs_results"}).simulation is None


def test_parse_loan_terms_matches_every_oracle_case():
    for case in LOAN_CASES["cases"]:
        assert parse_loan_terms(case["text"]) == case["expected"], case["case_id"]


def test_cost_wording_stays_calculate_cost():
    assert fixed_intent("mô phỏng chi phí thuê giúp mình") == "calculate_cost"
    assert fixed_intent("tính chi phí cho 2 người") == "calculate_cost"


def test_loan_question_wordings_route_to_simulate_finance():
    for text in ("Nếu vay 12 tháng thì sao nhỉ?", "vay 20 triệu lãi 10% trong 6 tháng thì trả bao nhiêu?",
                 "trả góp 24 tháng lãi suất 12,5% được không?", "mô phỏng vay giúp mình",
                 "lai suat 9.5% vay 18 thang duoc khong?"):
        assert fixed_intent(text) == "simulate_finance"
