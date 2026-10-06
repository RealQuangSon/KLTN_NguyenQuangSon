from decimal import Decimal

from backend.app.catalog import Catalog
from backend.app.costs import calculate_cost
from backend.app.models import Destination, Scenario


def reference():
    return next(room for room in Catalog().rooms() if room.id == "demo-01")


def test_known_monthly_and_initial_cash():
    cost = calculate_cost(reference().quote, Scenario())
    assert cost.monthly_total_vnd == 3_250_000
    assert cost.initial_total_vnd == 5_500_000


def test_per_person_and_usage_scenario():
    cost = calculate_cost(reference().quote, Scenario(people=2, vehicles=0, electricity_kwh=Decimal("100")))
    assert cost.monthly_total_vnd == 3_110_000


def test_missing_fee_is_unknown_not_zero():
    quote = reference().quote.model_copy(deep=True)
    quote.fees = [fee for fee in quote.fees if fee.name != "water"]
    quote.deposit_vnd = None
    cost = calculate_cost(quote, Scenario())
    assert cost.monthly_total_vnd is None and cost.monthly_known_vnd == 3_170_000
    assert cost.missing_monthly == ["water"]
    assert cost.initial_total_vnd is None and "deposit" in cost.missing_initial


def test_included_fee_is_zero_without_invented_unit_price():
    quote = reference().quote.model_copy(deep=True)
    quote.fees[0].included_in_rent = True
    quote.fees[0].amount_vnd = None
    assert calculate_cost(quote, Scenario()).monthly_total_vnd == 2_830_000


def test_full_cost_filters_cheap_rent_and_unknowns(profile):
    items, diagnostics = Catalog().match(profile)
    ids = {item.room_id for item in items}
    assert "demo-06" not in ids  # 2.8m rent but 3.97m total.
    assert "demo-07" not in ids  # Unknown water charge.
    assert "demo-12" not in ids  # Unknown mandatory amenity.
    assert diagnostics["rejected"]["monthly_budget"] == 1
    assert diagnostics["verification"]["monthly_fees"] == 1


def test_zero_initial_budget_does_not_disable_filter(profile):
    profile.max_initial_cash_vnd = 0
    items, _ = Catalog().match(profile)
    assert items == []


def test_location_boundary_requires_verification(profile):
    # Synthetic rooms are close to this point, but have 100m location uncertainty.
    profile.destination = Destination(label="Điểm giả lập", latitude=10.735, longitude=106.721,
                                      uncertainty_m=0, max_distance_m=50)
    items, diagnostics = Catalog().match(profile)
    assert items == []
    assert diagnostics["verification"]["distance_boundary"] > 0


def test_tie_break_is_stable_and_explanations_have_sources(profile):
    first, _ = Catalog().match(profile)
    second, _ = Catalog().match(profile)
    assert [item.room_id for item in first] == [item.room_id for item in second]
    assert all(item.source.startswith("demo://") and item.reasons for item in first)


def test_candidates_carry_listing_verification_flags(profile):
    items, _ = Catalog().match(profile)
    assert items
    rooms = {room.id: room for room in Catalog().rooms()}
    for item in items:
        room = rooms[item.room_id]
        unknown = {f"amenity_unknown:{name}" for name, value in room.amenities.items() if value is None}
        assert unknown <= set(item.verification)
        included_unknown_rate = {f"fee_rate_unknown:{fee.name}" for fee in room.quote.fees
                                 if fee.amount_vnd is None and fee.included_in_rent}
        assert included_unknown_rate <= set(item.verification)
        if room.location_accuracy == "approximate":
            assert "location_approximate" in item.verification
        elif room.location_accuracy == "area_only":
            assert "location_area_only" in item.verification
