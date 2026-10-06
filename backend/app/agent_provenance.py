"""Provenance stamps for assistant turns and result payloads.

Every chat turn and every renter-visible result payload records where its
content came from (user intent, deterministic engine or interpreter) and which
graph node produced it. The stamps are service-layer data (`HomeMatchService.agent_trace`);
exposing them in HTTP payloads needs an optional schema field owned by the
backend agent.
"""
from __future__ import annotations

SOURCES = frozenset({"user", "deterministic-engine", "interpreter"})


def stamp(source: str, node: str, **details) -> dict:
    if source not in SOURCES:
        raise ValueError(f"Unknown provenance source: {source}")
    return {"source": source, "node": node, **details}
