"""Estimate provider spend in VND from reported token usage.

Pure module (no I/O beyond the optional price-file reader): the operator keeps
a price table (see infra/provider-prices.example.json) outside the repository.
Any missing price or fx rate means the estimate stays None — unknown money is
never guessed as 0. Math is Decimal with ROUND_HALF_UP to whole VND, matching
costs.py.
"""
import json
from decimal import Decimal, ROUND_HALF_UP

WHOLE_VND = Decimal("1")
MILLION = Decimal(1_000_000)


def load_prices(path: str | None) -> dict | None:
    """Read the operator price file; None when unset, absent or invalid JSON.

    An invalid file is treated as "not configured" so the metrics endpoint
    keeps working; it just reports a null cost instead of a wrong number.
    """
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            prices = json.load(handle)
    except (OSError, ValueError):
        return None
    return prices if isinstance(prices, dict) else None


def estimate_cost_vnd(usage: dict | None, prices: dict | None) -> dict:
    """Convert per-model token usage into VND; missing inputs keep it None.

    usage is the provider_usage object from operations.Metrics.snapshot():
    cost needs the by_model split (input_tokens/output_tokens for chat models,
    embedding_tokens for embeddings). Aggregate-only reported_tokens cannot be
    split honestly, so it yields missing ["input_output_split"].
    """
    usage = usage or {}
    prices = prices or {}
    missing: list[str] = []
    basis: dict[str, dict[str, int]] = {}
    total = Decimal(0)
    tables = prices.get("models") if isinstance(prices.get("models"), dict) else {}
    by_model = usage.get("by_model") if isinstance(usage.get("by_model"), dict) else {}
    for model, stats in sorted(by_model.items()):
        stats = stats if isinstance(stats, dict) else {}
        tokens = {key: stats[key] for key in ("input_tokens", "output_tokens", "embedding_tokens") if stats.get(key)}
        if not tokens:
            continue
        basis[model] = tokens
        table = tables.get(model) if isinstance(tables.get(model), dict) else {}
        for key, count in tokens.items():
            price_key = "output_usd_per_1m" if key == "output_tokens" else "input_usd_per_1m"
            price = table.get(price_key)
            if price is None:
                missing.append(f"models.{model}.{price_key}")
                continue
            total += Decimal(str(count)) * Decimal(str(price)) / MILLION
    if basis:
        fx = prices.get("vnd_per_usd")
        if fx is None:
            missing.append("vnd_per_usd")
        else:
            total *= Decimal(str(fx))
    if not by_model and usage.get("reported_tokens"):
        # Only the aggregate total was reported; the input/output split is unknown.
        missing.append("input_output_split")
    if usage.get("calls_without_token_usage"):
        # The provider did not report usage for some calls; any total would understate.
        missing.append("calls_without_token_usage")
    return {"estimated_cost_vnd": None if missing else int(total.quantize(WHOLE_VND, rounding=ROUND_HALF_UP)),
            "price_effective_date": prices.get("effective_date"),
            "missing": missing, "basis": basis}
