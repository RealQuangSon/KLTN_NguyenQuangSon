"""BE-05: operating cost estimate in VND from reported provider tokens."""
import json

from fastapi.testclient import TestClient

from backend.app.cost_metrics import estimate_cost_vnd, load_prices
from backend.app.main import create_app

FAKE_PRICES = {"effective_date": "2026-10-01", "vnd_per_usd": 26000,
               "models": {"gpt-4o": {"input_usd_per_1m": 1.5, "output_usd_per_1m": 6},
                          "text-embedding-3-small": {"input_usd_per_1m": 0.4}}}

FAKE_USAGE = {"logical_calls": 3, "reported_tokens": 3_500_000, "calls_without_token_usage": 0,
              "input_tokens": 2_000_000, "output_tokens": 500_000, "embedding_tokens": 1_000_000,
              "by_model": {"gpt-4o": {"logical_calls": 2, "reported_tokens": 2_500_000,
                                      "input_tokens": 2_000_000, "output_tokens": 500_000},
                           "text-embedding-3-small": {"embedding_calls": 1, "embedding_tokens": 1_000_000}}}


def test_missing_price_file_yields_null_cost_on_metrics(service, monkeypatch):
    monkeypatch.delenv("HOMEMATCH_PROVIDER_PRICES_PATH", raising=False)
    with TestClient(create_app(lambda: service)) as client:
        admin = {"Authorization": "Bearer demo-admin"}
        response = client.get("/admin/metrics", headers=admin)
        assert response.status_code == 200
        assert response.json()["cost"] is None


def test_estimate_matches_hand_computation(tmp_path):
    path = tmp_path / "prices.json"
    path.write_text(json.dumps(FAKE_PRICES), encoding="utf-8")
    assert load_prices(str(path)) == FAKE_PRICES
    # Hand computation: gpt-4o (2M*1.5 + 0.5M*6)/1e6 = 6 USD; embeddings 1M*0.4/1e6
    # = 0.4 USD; 6.4 USD * 26,000 = 166,400 VND exactly.
    result = estimate_cost_vnd(FAKE_USAGE, FAKE_PRICES)
    assert result["estimated_cost_vnd"] == 166_400
    assert result["price_effective_date"] == "2026-10-01"
    assert result["missing"] == []
    assert result["basis"] == {"gpt-4o": {"input_tokens": 2_000_000, "output_tokens": 500_000},
                               "text-embedding-3-small": {"embedding_tokens": 1_000_000}}


def test_rounding_is_half_up_to_whole_vnd():
    prices = {"effective_date": None, "vnd_per_usd": 25000,
              "models": {"gpt-4o": {"input_usd_per_1m": 1, "output_usd_per_1m": 1}}}
    usage = {"by_model": {"gpt-4o": {"input_tokens": 100}}}
    # 100/1e6 USD * 25,000 = 2.5 VND -> ROUND_HALF_UP -> 3.
    assert estimate_cost_vnd(usage, prices)["estimated_cost_vnd"] == 3


def test_missing_fx_rate_keeps_estimate_null_and_lists_the_key():
    prices = {"effective_date": "2026-10-01", "models": FAKE_PRICES["models"]}
    result = estimate_cost_vnd(FAKE_USAGE, prices)
    assert result["estimated_cost_vnd"] is None
    assert "vnd_per_usd" in result["missing"]
    assert result["price_effective_date"] == "2026-10-01"


def test_missing_model_price_and_unknown_split_stay_null():
    priced = estimate_cost_vnd(FAKE_USAGE, {"effective_date": None, "vnd_per_usd": 26000, "models": {}})
    assert priced["estimated_cost_vnd"] is None
    assert "models.gpt-4o.input_usd_per_1m" in priced["missing"]
    assert "models.text-embedding-3-small.input_usd_per_1m" in priced["missing"]
    aggregate = estimate_cost_vnd({"reported_tokens": 150, "logical_calls": 1}, FAKE_PRICES)
    assert aggregate["estimated_cost_vnd"] is None and aggregate["missing"] == ["input_output_split"]
    unreported = estimate_cost_vnd({"logical_calls": 1, "reported_tokens": 0, "calls_without_token_usage": 1},
                                   FAKE_PRICES)
    assert unreported["estimated_cost_vnd"] is None
    assert "calls_without_token_usage" in unreported["missing"]


def test_unreadable_price_file_is_treated_as_not_configured(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_prices(str(path)) is None
    assert load_prices(str(tmp_path / "absent.json")) is None
    assert load_prices(None) is None


def test_metrics_exposes_cost_with_real_usage(service, tmp_path, monkeypatch):
    prices_path = tmp_path / "prices.json"
    prices_path.write_text(json.dumps(FAKE_PRICES), encoding="utf-8")
    monkeypatch.setenv("HOMEMATCH_PROVIDER_PRICES_PATH", str(prices_path))
    # Same shape operations.Metrics records after a live provider turn.
    service.metrics.provider_usage({"logical_calls": 1, "tokens": 2_500_000, "model": "gpt-4o",
                                    "input_tokens": 2_000_000, "output_tokens": 500_000})
    service.metrics.embedding_usage({"model": "text-embedding-3-small", "embedding_tokens": 1_000_000})
    with TestClient(create_app(lambda: service)) as client:
        admin = {"Authorization": "Bearer demo-admin"}
        renter = {"Authorization": "Bearer demo-renter"}
        assert client.get("/admin/metrics", headers=renter).status_code == 403
        payload = client.get("/admin/metrics", headers=admin).json()
        assert payload["cost"]["estimated_cost_vnd"] == 166_400
        assert payload["cost"]["price_effective_date"] == "2026-10-01"
        assert payload["cost"]["missing"] == []
        assert payload["cost"]["basis"]["gpt-4o"]["input_tokens"] == 2_000_000
