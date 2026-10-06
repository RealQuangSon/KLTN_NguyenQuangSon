"""Bounded process metrics; no identifiers, request bodies or credentials."""
from collections import Counter
from threading import Lock


class Metrics:
    def __init__(self):
        self.lock = Lock()
        self.requests = {}
        self.generations = {}
        self.usage = Counter()
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

    def provider_usage(self, usage: dict):
        with self.lock:
            calls = usage.get("logical_calls", 0)
            self.usage["logical_calls"] += calls
            tokens = usage.get("tokens")
            if tokens is None:
                self.usage["calls_without_token_usage"] += calls
            else:
                self.usage["reported_tokens"] += tokens

    def snapshot(self) -> dict:
        with self.lock:
            return {"scope": "current_process", "requests": [
                {"method": method, "route": route, "status": status, **values}
                for (method, route, status), values in sorted(self.requests.items())
            ], "generations": [
                {"status": status, "algorithm": algorithm, **values}
                for (status, algorithm), values in sorted(self.generations.items())
            ], "provider_usage": {
                key: self.usage[key] for key in ("logical_calls", "reported_tokens", "calls_without_token_usage")
            }, "semantic_usage": {"query_embedding_calls": self.semantic.get("query_embedding_calls", 0),
                                  "query_cache_hits": self.semantic.get("query_cache_hits", 0)}}
