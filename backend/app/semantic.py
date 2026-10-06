from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone

from .interpreter import redact
from .models import DomainError


def semantic_text(room) -> str:
    features = [f"{name}: {'có' if value else 'không có'}"
                for name, value in sorted(room.amenities.items()) if value is not None]
    text = "; ".join([room.room_type, room.title, *features, *([room.features_text] if room.features_text else [])])
    if redact(text) != text:
        raise DomainError("private_semantic_text", "Văn bản semantic chứa tiền hoặc liên hệ cần loại bỏ.", 422)
    return text


class OpenAIEmbeddings:
    def __init__(self, client=None, model: str | None = None, dimensions: int = 1536):
        from openai import OpenAI
        self.client = client or OpenAI(timeout=20, max_retries=1)
        self.model = model or os.getenv("HOMEMATCH_EMBEDDING_MODEL", "text-embedding-3-small")
        self.dimensions = dimensions
        self.cache: dict[str, list[float]] = {}
        self.calls = 0
        self.tokens = 0
        self.usage_missing_calls = 0

    def embed(self, text: str) -> list[float]:
        if redact(text) != text:
            raise DomainError("private_semantic_text", "Không embedding tiền hoặc thông tin liên hệ.", 422)
        key = hashlib.sha256((self.model + str(self.dimensions) + text).encode()).hexdigest()
        if key not in self.cache:
            self.calls += 1  # Logical SDK invocations; HTTP retries are not separately observed.
            try:
                response = self.client.embeddings.create(model=self.model, dimensions=self.dimensions, input=text)
                values = response.data[0].embedding
                if (len(values) != self.dimensions or not all(math.isfinite(value) for value in values)
                        or not any(value != 0 for value in values)):
                    raise ValueError("invalid vector")
                self.cache[key] = values
                tokens = getattr(getattr(response, "usage", None), "total_tokens", None)
                if tokens is None:
                    self.usage_missing_calls += 1
                else:
                    self.tokens += tokens
            except Exception:
                self.usage_missing_calls += 1
                raise DomainError("semantic_unavailable", "Dịch vụ embedding chưa sẵn sàng.", 503) from None
        return self.cache[key]


class QueryEmbeddingCache:
    """Persistent cache of query vectors (ledger table `hm_query_embeddings`, migration v4).

    Room vectors are re-embedded only when their semantic-text hash changes; the same
    confirmed soft description across runs, retries and restarts costs one provider call.
    """

    def __init__(self, repo, provider, on_lookup=None):
        self.repo, self.provider, self.on_lookup = repo, provider, on_lookup
        self.hits = 0
        self.misses = 0

    def key(self, text: str) -> str:
        return hashlib.sha256(f"{self.provider.model}|{self.provider.dimensions}|{text}".encode()).hexdigest()

    def embed(self, text: str) -> list[float]:
        key = self.key(text)
        row = self.repo.db.execute("SELECT embedding_json FROM hm_query_embeddings WHERE cache_key=?", (key,)).fetchone()
        if row is not None:
            self.hits += 1
            if self.on_lookup:
                self.on_lookup(hit=True)
            return json.loads(row["embedding_json"])
        vector = self.provider.embed(text)
        self.misses += 1
        if self.on_lookup:
            self.on_lookup(hit=False)
        with self.repo.db:
            self.repo.db.execute("INSERT INTO hm_query_embeddings(cache_key,model,dimensions,embedding_json,created_at) "
                                 "VALUES(?,?,?,?,?) ON CONFLICT(cache_key) DO NOTHING",
                                 (key, self.provider.model, self.provider.dimensions, json.dumps(vector),
                                  datetime.now(timezone.utc).isoformat()))
        return vector


class PostgresSemantic:
    def __init__(self, repo, catalog, provider, on_lookup=None):
        self.repo, self.catalog, self.provider = repo, catalog, provider
        self.query_cache = QueryEmbeddingCache(repo, provider, on_lookup)
        if not repo.db.postgres:
            raise ValueError("pgvector requires PostgreSQL")
        with repo.guard():
            repo.db.execute("CREATE EXTENSION IF NOT EXISTS vector")
            repo.db.execute("CREATE TABLE IF NOT EXISTS hm_embeddings (room_id TEXT PRIMARY KEY REFERENCES hm_rooms(id), "
                            "text_hash TEXT NOT NULL, model TEXT NOT NULL, dimensions INTEGER NOT NULL, embedding VECTOR NOT NULL)")

    def index(self) -> dict:
        count = 0
        for room in self.catalog.rooms():
            text = semantic_text(room)
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            old = self.repo.db.execute("SELECT text_hash,model,dimensions FROM hm_embeddings WHERE room_id=?", (room.id,)).fetchone()
            if old and (old["text_hash"], old["model"], old["dimensions"]) == (text_hash, self.provider.model, self.provider.dimensions):
                continue
            vector = self.provider.embed(text)
            with self.repo.guard():
                self.repo.db.execute("INSERT INTO hm_embeddings VALUES(?,?,?,?,?::vector) "
                                    "ON CONFLICT(room_id) DO UPDATE SET text_hash=excluded.text_hash,model=excluded.model, "
                                    "dimensions=excluded.dimensions,embedding=excluded.embedding",
                                    (room.id, text_hash, self.provider.model, self.provider.dimensions, json.dumps(vector)))
            count += 1
        return {"indexed": count, "model": self.provider.model, "dimensions": self.provider.dimensions}

    def similarities(self, query: str, room_ids: list[str]) -> dict[str, float]:
        current = {room.id: hashlib.sha256(semantic_text(room).encode()).hexdigest() for room in self.catalog.rooms()}
        rows = self.repo.db.execute("SELECT room_id,text_hash FROM hm_embeddings WHERE room_id=ANY(?) AND model=? AND dimensions=?",
                                    (room_ids, self.provider.model, self.provider.dimensions)).fetchall()
        if len(rows) != len(room_ids) or any(row["text_hash"] != current.get(row["room_id"]) for row in rows):
            raise DomainError("semantic_unavailable", "Cần index vector cho toàn bộ tập phòng đủ điều kiện.", 503)
        vector = self.query_cache.embed(query)
        # Exact search scores every eligible ID; no approximate index or semantic shortlist.
        values = self.repo.db.execute("SELECT room_id,embedding <=> ?::vector AS distance FROM hm_embeddings "
                                     "WHERE room_id=ANY(?) AND model=? AND dimensions=?",
                                     (json.dumps(vector), room_ids, self.provider.model, self.provider.dimensions)).fetchall()
        if any(row["distance"] is None or not math.isfinite(row["distance"]) for row in values):
            raise DomainError("semantic_unavailable", "Vector không đủ điều kiện tính độ tương đồng.", 503)
        return {row["room_id"]: max(0.0, min(1.0, 1 - row["distance"] / 2)) for row in values}
