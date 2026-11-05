"""Bounded process metrics; no identifiers, request bodies or credentials."""
from collections import Counter
from threading import Lock


class Metrics:
    def __init__(self):
        self.lock = Lock()
        self.requests = {}
        self.generations = {}
        self.usage = Counter()
        self.by_model = {}
        self.semantic = {}

    def request(self, method: str, route: str, status: int, seconds: float):
        with self.lock:
            key = (method, route, status)
            values = self.requests.setdefault(key, {"count": 0, "duration_seconds": 0.0})
            values["count"] += 1
            values["duration_seconds"] += seconds

    def generation(self, status: str, algorithm: str, seconds: float):
        with self.lock:
            key = (status, algorithm)
            values = self.generations.setdefault(key, {"count": 0, "duration_seconds": 0.0})
            values["count"] += 1
            values["duration_seconds"] += seconds

    def semantic_query(self, hit: bool):
        with self.lock:
            key = "query_cache_hits" if hit else "query_embedding_calls"
            self.semantic[key] = self.semantic.get(key, 0) + 1

    def _account(self, stats: Counter, calls: int, tokens, split: dict):
        stats["logical_calls"] += calls
        if tokens is None:
            stats["calls_without_token_usage"] += calls
        else:
            stats["reported_tokens"] += tokens
        # Input/output split stays absent (not zero) when the provider did not report it.
        for key in ("input_tokens", "output_tokens"):
            value = split.get(key)
            if value is not None:
                stats[key] += value

    def provider_usage(self, usage: dict):
        with self.lock:
            calls = usage.get("logical_calls", 0)
            tokens = usage.get("tokens")
            split = {"input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens")}
            self._account(self.usage, calls, tokens, split)
            model = usage.get("model")
            if model and calls:
                # Prices differ per model, so the split is kept per model for cost conversion.
                self._account(self.by_model.setdefault(str(model), Counter()), calls, tokens, split)

    def embedding_usage(self, usage: dict):
        """Embedding provider report; embedding_tokens None means usage was not reported."""
        with self.lock:
            model = str(usage.get("model") or "unknown")
            tokens = usage.get("embedding_tokens")
            stats = self.by_model.setdefault(model, Counter())
            stats["embedding_calls"] += 1
            if tokens is None:
                self.usage["embedding_calls_without_usage"] += 1
                stats["embedding_calls_without_usage"] += 1
            else:
                self.usage["embedding_tokens"] += tokens
                stats["embedding_tokens"] += tokens

    def snapshot(self) -> dict:
        with self.lock:
            provider_usage = {"logical_calls": self.usage["logical_calls"],
                              "reported_tokens": self.usage["reported_tokens"],
                              "calls_without_token_usage": self.usage["calls_without_token_usage"]}
            # New split counters only appear once non-zero so legacy consumers of the
            # three-key payload are unaffected.
            for key in ("input_tokens", "output_tokens", "embedding_tokens", "embedding_calls_without_usage"):
                if self.usage[key]:
                    provider_usage[key] = self.usage[key]
            by_model = {model: {key: value for key, value in sorted(stats.items()) if value}
                        for model, stats in sorted(self.by_model.items())}
            by_model = {model: values for model, values in by_model.items() if values}
            if by_model:
                provider_usage["by_model"] = by_model
            return {"scope": "current_process", "requests": [
                {"method": method, "route": route, "status": status, **values}
                for (method, route, status), values in sorted(self.requests.items())
            ], "generations": [
                {"status": status, "algorithm": algorithm, **values}
                for (status, algorithm), values in sorted(self.generations.items())
            ], "provider_usage": provider_usage,
               "semantic_usage": {"query_embedding_calls": self.semantic.get("query_embedding_calls", 0),
                                  "query_cache_hits": self.semantic.get("query_cache_hits", 0)}}
