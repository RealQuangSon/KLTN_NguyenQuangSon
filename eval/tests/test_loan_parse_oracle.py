"""DA-02: schema-only checks on the hand-authored loan parse oracle (used by AG-02)."""
from data.generate import generate
from eval.common import read_json


def _valid_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def test_loan_parse_oracle_schema_types_and_documented_ranges(tmp_path):
    dataset = tmp_path / "data"
    generate(dataset)
    payload = read_json(dataset / "oracles/loan_parse_cases.json")
    for key in ("term_months", "annual_rate", "principal_vnd"):
        assert key in payload["rules"], f"rules must document {key}"
    cases = payload["cases"]
    assert len(cases) >= 15 and len({case["case_id"] for case in cases}) == len(cases)
    for case in cases:
        assert case["text"].strip()
        expected = case["expected"]
        assert set(expected) == {"term_months", "annual_rate", "principal_vnd"}
        term, rate, principal = expected["term_months"], expected["annual_rate"], expected["principal_vnd"]
        # Values are the documented type or null (unknown), and stay inside the documented ranges.
        assert term is None or (type(term) is int and 1 <= term <= 60)
        assert rate is None or (_valid_number(rate) and 0 <= rate <= 50)
        assert principal is None or (type(principal) is int and principal > 0)


def test_loan_parse_oracle_covers_readme_cases_and_edge_cases(tmp_path):
    dataset = tmp_path / "data"
    generate(dataset)
    cases = {case["case_id"]: case for case in
             read_json(dataset / "oracles/loan_parse_cases.json")["cases"]}
    # The three README §7.4 examples.
    assert cases["LP01"]["expected"] == {"term_months": 12, "annual_rate": None, "principal_vnd": None}
    assert cases["LP02"]["expected"] == {"term_months": 6, "annual_rate": 10.0, "principal_vnd": 20_000_000}
    assert cases["LP03"]["expected"] == {"term_months": 24, "annual_rate": 12.5, "principal_vnd": None}
    # Out-of-range inputs must expect null, never a clamped number.
    assert cases["LP07"]["expected"]["term_months"] is None  # 100 tháng
    assert cases["LP08"]["expected"]["annual_rate"] is None  # 60%
    assert cases["LP19"]["expected"]["term_months"] is None  # 61 tháng, boundary +1
    # Boundaries stay valid and zero rate is a value, not absence.
    assert cases["LP17"]["expected"]["term_months"] == 60
    assert cases["LP18"]["expected"]["annual_rate"] == 50.0
    assert cases["LP05"]["expected"]["annual_rate"] == 0.0
    # Two month numbers: the first one wins; unit-less or unsupported units stay null.
    assert cases["LP09"]["expected"]["term_months"] == 6
    assert cases["LP15"]["expected"]["principal_vnd"] is None
    assert cases["LP04"]["expected"]["principal_vnd"] == 1_500_000  # dấu phẩy thập phân
    assert cases["LP11"]["expected"]["principal_vnd"] == 20_000_000  # đơn vị "tr"
