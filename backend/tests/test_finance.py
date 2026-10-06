import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.app.catalog import DEFAULT_CATALOG, Catalog
from backend.app.costs import (affordability_band, assess_affordability, calculate_cost, estimate_loan,
                               loan_installment)
from backend.app.main import create_app
from backend.app.models import (Actor, DomainError, LoanTerms, Profile, Quote, Review, Scenario,
                                SimulationRequest)

DEMO = json.loads(DEFAULT_CATALOG.read_text(encoding="utf-8"))["rooms"]
DEMO_01 = next(room for room in DEMO if room["id"] == "demo-01")  # 3.250.000/month, 5.500.000 move-in


def catalog_with(tmp_path, *rooms) -> Catalog:
    path = tmp_path / "rooms.json"
    path.write_text(json.dumps({"rooms": list(rooms)}, ensure_ascii=False), encoding="utf-8")
    return Catalog(path)


def demo_profile(**changes) -> Profile:
    values = dict(city="TP.HCM", area="Quận 7", max_monthly_cost_vnd=3_500_000,
                  max_initial_cash_vnd=6_500_000, scenario=Scenario())
    return Profile(**{**values, **changes})


def test_worked_example_from_finance_spec():
    # docs/tai-chinh-thue.md §7, computed by hand.
    assert loan_installment(5_500_000, Decimal("0.12"), 6) == 949_016
    loan = estimate_loan(5_500_000, LoanTerms(annual_rate=Decimal("0.12"), term_months=6))
    assert loan.total_interest_vnd == 194_096 and not loan.exceeds_max_principal


def test_zero_rate_splits_evenly_and_no_shortfall_means_no_loan():
    assert loan_installment(1_200_000, Decimal("0"), 12) == 100_000
    cost = calculate_cost(Quote.model_validate(DEMO_01["quote"]), Scenario())
    result = assess_affordability(cost, people=1, available_cash_vnd=9_000_000, monthly_income_vnd=None,
                                  loan=LoanTerms(annual_rate=Decimal("0.1"), term_months=6))
    assert result.shortfall_vnd == 0 and result.loan is None
    assert result.burden_vnd == 3_250_000 and result.band == "chua_ro"


@pytest.mark.parametrize("ratio, band", [("0.3000", "phu_hop"), ("0.3001", "can_nhac"),
                                         ("0.4000", "can_nhac"), ("0.4001", "vuot"), (None, "chua_ro")])
def test_band_thresholds_are_inclusive_upper_bounds(ratio, band):
    assert affordability_band(Decimal(ratio) if ratio else None) == band


def test_equal_split_uses_renter_share_for_the_ratio():
    cost = calculate_cost(Quote.model_validate(DEMO_01["quote"]), Scenario(people=2))
    result = assess_affordability(cost, people=2, available_cash_vnd=None, monthly_income_vnd=10_000_000,
                                  cost_split="equal")
    assert result.renter_burden_vnd == round(result.burden_vnd / 2)
    assert result.housing_ratio == (Decimal(result.renter_burden_vnd) / 10_000_000).quantize(Decimal("0.0001"))


def test_unknown_initial_total_keeps_shortfall_unknown():
    quote = Quote.model_validate({**DEMO_01["quote"], "deposit_vnd": None})
    result = assess_affordability(calculate_cost(quote, Scenario()), people=1, available_cash_vnd=1,
                                  monthly_income_vnd=None)
    assert result.shortfall_vnd is None and result.loan is None


def test_cash_shortfall_is_hard_without_a_loan_and_fits_with_one(tmp_path):
    catalog = catalog_with(tmp_path, DEMO_01)
    no_loan, diagnostics = catalog.eligible_candidates(demo_profile(max_initial_cash_vnd=4_000_000))
    assert no_loan == [] and diagnostics["rejected"] == {"initial_budget": 1}
    with_loan, _ = catalog.eligible_candidates(demo_profile(
        max_initial_cash_vnd=4_000_000, max_monthly_cost_vnd=3_600_000,
        loan=LoanTerms(annual_rate=Decimal("0.12"), term_months=6)))
    [candidate] = with_loan
    loan = candidate.cost.affordability.loan
    assert loan.principal_vnd == 1_500_000 and loan.installment_vnd == loan_installment(1_500_000, Decimal("0.12"), 6)
    assert any(reason.startswith("Cần vay 1,500,000 VND") for reason in candidate.reasons)


def test_loan_principal_cap_and_burden_are_hard_limits(tmp_path):
    catalog = catalog_with(tmp_path, DEMO_01)
    capped, diagnostics = catalog.eligible_candidates(demo_profile(
        max_initial_cash_vnd=4_000_000,
        loan=LoanTerms(annual_rate=Decimal("0.12"), term_months=6, max_principal_vnd=1_000_000)))
    assert capped == [] and diagnostics["rejected"] == {"loan_principal": 1}
    # 3.250.000 + ~258.800 instalment exceeds a 3.400.000 ceiling while the loan runs.
    heavy, diagnostics = catalog.eligible_candidates(demo_profile(
        max_initial_cash_vnd=4_000_000, max_monthly_cost_vnd=3_400_000,
        loan=LoanTerms(annual_rate=Decimal("0.12"), term_months=6)))
    assert heavy == [] and diagnostics["rejected"] == {"loan_burden": 1}


def test_band_tradeoff_is_shown_but_never_filters(tmp_path):
    catalog = catalog_with(tmp_path, DEMO_01)
    [candidate], _ = catalog.eligible_candidates(demo_profile(monthly_income_vnd=7_000_000))
    assert candidate.cost.affordability.band == "vuot"
    assert "Tỷ lệ chi phí nhà ở trên thu nhập vượt mức khuyến nghị." in candidate.tradeoffs


def test_apartment_bedrooms_filter_and_unknown_needs_verification(tmp_path):
    apartment = {**DEMO_01, "id": "apt-2pn", "room_type": "apartment", "bedrooms": 2}
    unknown = {**DEMO_01, "id": "apt-unknown", "room_type": "apartment", "bedrooms": None}
    small = {**DEMO_01, "id": "apt-1pn", "room_type": "apartment", "bedrooms": 1}
    catalog = catalog_with(tmp_path, apartment, unknown, small, DEMO_01)
    found, diagnostics = catalog.eligible_candidates(demo_profile(room_type="apartment", min_bedrooms=2))
    assert [item.room_id for item in found] == ["apt-2pn"]
    assert found[0].room_type == "apartment" and found[0].bedrooms == 2
    assert diagnostics["rejected"] == {"bedrooms": 1, "room_type": 1}
    assert diagnostics["verification"] == {"bedrooms": 1}


def published(service, renter, landlord, profile):
    session_id = service.create_session(renter)["session_id"]
    run_id = service.confirm(session_id, renter, profile, 0)["run_id"]
    ids = [item["room_id"] for item in service.draft(run_id, landlord)["items"]]
    service.review(run_id, landlord, Review(decision="approve", expected_profile_version=1,
                                           reason="Đã kiểm tra.", idempotency_key="k"))
    return session_id, run_id, ids


def test_sale_projection_hides_income_and_exact_ratio(service, renter, landlord):
    profile = demo_profile(monthly_income_vnd=12_000_000)
    session_id, run_id, _ = published(service, renter, landlord, profile)
    sale = service._admin_projection(service.repo.run(run_id))
    assert "monthly_income_vnd" not in sale["profile"]
    assert all(item["cost"]["affordability"]["housing_ratio"] is None for item in sale["items"])
    assert all(item["cost"]["affordability"]["band"] != "chua_ro" for item in sale["items"])
    mine = service.results(session_id, renter)["results"]
    assert all(item["cost"]["affordability"]["housing_ratio"] is not None for item in mine)


def test_simulation_is_read_only_and_limited_to_approved_rooms(service, renter, landlord):
    profile = demo_profile(max_initial_cash_vnd=4_000_000, max_monthly_cost_vnd=3_700_000,
                           monthly_income_vnd=12_000_000,
                           loan=LoanTerms(annual_rate=Decimal("0.12"), term_months=6))
    session_id, run_id, ids = published(service, renter, landlord, profile)
    before = service.session(session_id, renter)
    request = SimulationRequest.model_validate({"room_id": ids[0], "scenarios": [
        {"label": "Vay 6 tháng"},
        {"label": "Vay 12 tháng", "loan": {"annual_rate": "0.12", "term_months": 12}},
        {"label": "Không vay", "loan": None}]})
    result = service.simulate(session_id, renter, request)
    six, twelve, none = (item["cost"]["affordability"] for item in result["items"])
    assert six["loan"]["term_months"] == 6 and twelve["loan"]["term_months"] == 12
    assert twelve["loan"]["installment_vnd"] < six["loan"]["installment_vnd"] and none["loan"] is None
    assert service.session(session_id, renter) == before
    with pytest.raises(DomainError) as hidden:
        service.simulate(session_id, renter, SimulationRequest(room_id="demo-06", scenarios=[{"label": "x"}]))
    assert hidden.value.code == "not_visible"
    with pytest.raises(DomainError):
        service.simulate(session_id, Actor(id="renter-b", role="renter"), request)


def test_locations_endpoint_and_cost_estimate_with_affordability(service):
    with TestClient(create_app(lambda: service)) as client:
        cities = client.get("/locations").json()["cities"]
        assert [city["name"] for city in cities] == ["TP.HCM", "Hà Nội"]
        hanoi = next(city for city in cities if city["name"] == "Hà Nội")
        assert "Quận Cầu Giấy" in [area["name"] for area in hanoi["areas"]]
        headers = {"Authorization": "Bearer demo-renter-a"}
        plain = client.post("/costs/estimate", headers=headers,
                            json={"quote": DEMO_01["quote"], "scenario": {}}).json()
        assert plain["affordability"] is None and plain["monthly_total_vnd"] == 3_250_000
        rich = client.post("/costs/estimate", headers=headers, json={
            "quote": DEMO_01["quote"], "scenario": {},
            "affordability": {"available_cash_vnd": 4_000_000, "monthly_income_vnd": 10_000_000,
                              "loan": {"annual_rate": "0.12", "term_months": 6}}}).json()
        assert rich["affordability"]["shortfall_vnd"] == 1_500_000
        assert rich["affordability"]["loan"]["principal_vnd"] == 1_500_000
