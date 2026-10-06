from decimal import Decimal, ROUND_HALF_UP

from .models import Affordability, CostLine, CostRequest, CostResult, LoanEstimate, LoanTerms, Quote, Scenario

REQUIRED_FEES = ("electricity", "water", "internet", "parking", "service")
# Housing-cost-to-income bands; a rule of thumb shown with the result, not a legal standard.
AFFORDABILITY_THRESHOLDS = {"phu_hop": Decimal("0.30"), "can_nhac": Decimal("0.40")}
RATIO_DIGITS = Decimal("0.0001")


def rounded_vnd(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_cost(quote: Quote, scenario: Scenario) -> CostResult:
    """Pure arithmetic. Missing charges remain unknown, including an absent fee."""
    lines = [CostLine(name="rent", period="monthly", amount_vnd=quote.rent_vnd,
                      source="quote.rent_vnd")]
    fees = {fee.name: fee for fee in quote.fees}
    quantities = {
        "fixed": Decimal(1), "person": Decimal(scenario.people),
        "vehicle": Decimal(scenario.vehicles), "kwh": scenario.electricity_kwh,
        "m3": scenario.water_m3,
    }
    for name in dict.fromkeys([*REQUIRED_FEES, *fees]):
        fee = fees.get(name)
        amount = None
        if fee is not None:
            if fee.included_in_rent:
                amount = 0
            elif fee.amount_vnd is not None:
                amount = rounded_vnd(fee.amount_vnd * quantities[fee.mode])
        lines.append(CostLine(name=name, period="monthly", amount_vnd=amount,
                              source=fee.source if fee else "missing",
                              included_in_rent=bool(fee and fee.included_in_rent)))

    initial = {
        "deposit": quote.deposit_vnd,
        "first_rent": (quote.rent_vnd * quote.advance_months
                       if quote.advance_months is not None else None),
        "one_time": quote.one_time_vnd,
        "moving": scenario.moving_vnd,
        "setup": scenario.setup_vnd,
    }
    for name, amount in initial.items():
        lines.append(CostLine(name=name, period="initial", amount_vnd=amount,
                              source="scenario" if name in {"moving", "setup"} else "quote"))
    monthly = [line for line in lines if line.period == "monthly"]
    upfront = [line for line in lines if line.period == "initial"]
    missing_monthly = [line.name for line in monthly if line.amount_vnd is None]
    missing_initial = [line.name for line in upfront if line.amount_vnd is None]
    month_sum = sum(line.amount_vnd for line in monthly if line.amount_vnd is not None)
    initial_sum = sum(line.amount_vnd for line in upfront if line.amount_vnd is not None)
    return CostResult(
        monthly_known_vnd=month_sum,
        monthly_total_vnd=None if missing_monthly else month_sum,
        initial_known_vnd=initial_sum,
        initial_total_vnd=None if missing_initial else initial_sum,
        missing_monthly=missing_monthly, missing_initial=missing_initial,
        lines=lines, assumptions=scenario.model_dump(mode="json"),
    )


def loan_installment(principal: int, annual_rate: Decimal, term_months: int) -> int:
    """Level (annuity) instalment on a declining balance at a fixed rate the renter entered."""
    if principal <= 0:
        return 0
    rate = annual_rate / 12
    if rate == 0:
        return rounded_vnd(Decimal(principal) / term_months)
    return rounded_vnd(Decimal(principal) * rate / (1 - (1 + rate) ** -term_months))


def estimate_loan(shortfall: int, terms: LoanTerms) -> LoanEstimate:
    installment = loan_installment(shortfall, terms.annual_rate, terms.term_months)
    return LoanEstimate(
        principal_vnd=shortfall, installment_vnd=installment,
        total_interest_vnd=installment * terms.term_months - shortfall,
        term_months=terms.term_months, annual_rate=terms.annual_rate,
        exceeds_max_principal=terms.max_principal_vnd is not None and shortfall > terms.max_principal_vnd)


def affordability_band(ratio: Decimal | None) -> str:
    if ratio is None:
        return "chua_ro"
    if ratio <= AFFORDABILITY_THRESHOLDS["phu_hop"]:
        return "phu_hop"
    if ratio <= AFFORDABILITY_THRESHOLDS["can_nhac"]:
        return "can_nhac"
    return "vuot"


def assess_affordability(cost: CostResult, *, people: int, available_cash_vnd: int | None,
                         monthly_income_vnd: int | None, cost_split: str = "none",
                         loan: LoanTerms | None = None) -> Affordability:
    """Shortfall, optional loan, monthly burden and income ratio; unknown inputs stay null."""
    shortfall = None
    if cost.initial_total_vnd is not None and available_cash_vnd is not None:
        shortfall = max(0, cost.initial_total_vnd - available_cash_vnd)
    estimate = estimate_loan(shortfall, loan) if loan is not None and shortfall else None
    installment = estimate.installment_vnd if estimate else 0
    burden = None if cost.monthly_total_vnd is None else cost.monthly_total_vnd + installment
    renter_burden = burden
    if burden is not None and cost_split == "equal" and people > 1:
        renter_burden = rounded_vnd(Decimal(burden) / people)
    ratio = None
    if renter_burden is not None and monthly_income_vnd:
        ratio = (Decimal(renter_burden) / Decimal(monthly_income_vnd)).quantize(RATIO_DIGITS, ROUND_HALF_UP)
    return Affordability(shortfall_vnd=shortfall, loan=estimate, burden_vnd=burden,
                         renter_burden_vnd=renter_burden, housing_ratio=ratio,
                         band=affordability_band(ratio), thresholds=AFFORDABILITY_THRESHOLDS)


def estimate_with_affordability(quote: Quote, scenario: Scenario, *, available_cash_vnd: int | None = None,
                                monthly_income_vnd: int | None = None, cost_split: str = "none",
                                loan: LoanTerms | None = None) -> CostResult:
    cost = calculate_cost(quote, scenario)
    cost.affordability = assess_affordability(
        cost, people=scenario.people, available_cash_vnd=available_cash_vnd,
        monthly_income_vnd=monthly_income_vnd, cost_split=cost_split, loan=loan)
    return cost


def estimate_cost(request: CostRequest) -> CostResult:
    """Cost estimate endpoint/chat tool: affordability only when the caller supplies its inputs."""
    if request.affordability is None:
        return calculate_cost(request.quote, request.scenario)
    inputs = request.affordability
    return estimate_with_affordability(request.quote, request.scenario,
                                       available_cash_vnd=inputs.available_cash_vnd,
                                       monthly_income_vnd=inputs.monthly_income_vnd,
                                       cost_split=inputs.cost_split, loan=inputs.loan)
