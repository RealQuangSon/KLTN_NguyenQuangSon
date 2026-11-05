"""DA-03: hand-computed invoice oracle — schema, independent re-arithmetic, suite run."""
from decimal import ROUND_HALF_UP, Decimal

from backend.app.models import Quote

from data.generate import generate
from eval.common import read_json
from eval.invoices import invoice_oracle_report


def test_invoice_oracle_schema_and_hand_arithmetic(tmp_path):
    dataset = tmp_path / "data"
    generate(dataset)
    payload = read_json(dataset / "oracles/invoice_cases.json")
    cases = payload["cases"]
    assert len(cases) >= 10 and len({case["case_id"] for case in cases}) == len(cases)
    covered = set()
    for case in cases:
        Quote.model_validate(case["quote"])
        assert set(case["lease"]) == {"rent_vnd", "occupants", "vehicles"}
        assert case["expected_total_vnd"] is None or case["expected_error"] is None
        assert case["origin"] == "authored_independent_arithmetic_constants"
        if case["expected_error"]:
            assert case["lines"] is None and case["expected_total_vnd"] is None
            covered.add(case["expected_error"])
            continue
        # Independent re-arithmetic (formula rewritten here, never imported from backend):
        # each line is quantity × unit_price rounded HALF_UP to whole VND.
        total = 0
        for line in case["lines"]:
            amount = (Decimal(line["quantity"]) * Decimal(line["unit_price"])).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP)
            assert int(amount) == line["amount_vnd"]
            total += line["amount_vnd"]
        assert total == case["expected_total_vnd"]
    assert {"reading_decreased", "invoice_incomplete"} <= covered


def test_invoice_suite_matches_hand_calculations_on_temp_db(tmp_path):
    dataset, output = tmp_path / "data", tmp_path / "invoices.json"
    generate(dataset)
    report = invoice_oracle_report(dataset, output)
    assert report["case_count"] == report["passed"] == 12 and report["failed"] == 0
    assert output.is_file()
    assert all(case["differences"] == {} for case in report["cases"])
    reference = next(case for case in report["cases"] if case["case_id"] == "INV-01-reference")
    assert reference["actual_total_vnd"] == 3_360_000
