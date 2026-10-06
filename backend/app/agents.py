"""Multi-agent tool boundary (FR-21).

The chat graph is a supervisor that routes each turn to one specialised agent:
needs (interview), finance (cost/affordability) or support. Ranking runs in
the recommendation graph as the ranking agent. Agents only reach business
logic through `ToolBox.call`, which enforces a static per-agent allowlist and
a per-turn step limit. Model output never adds a tool or an agent.

Several agents do not mean several LLM calls: only the needs agent's
extraction may call a provider, and routing is deterministic whenever the
intent is explicit.
"""
from __future__ import annotations

from typing import Callable

from .models import DomainError

AGENT_TOOLS: dict[str, frozenset[str]] = {
    "needs": frozenset({"extract_needs", "update_draft", "read_memory"}),
    "finance": frozenset({"calculate_cost", "assess_affordability", "estimate_loan", "simulate_scenarios"}),
    "ranking": frozenset({"match_catalog", "semantic_scores", "explain_candidate"}),
    "support": frozenset({"request_support"}),
    "handbook": frozenset({"search_handbook"}),
}
MAX_STEPS = 4


class ToolBox:
    """One instance per turn/run; records which agent called which tool."""

    def __init__(self, max_steps: int = MAX_STEPS):
        self.max_steps = max_steps
        self.calls: list[dict] = []
        self.denied: list[dict] = []

    def call(self, agent: str, tool: str, function: Callable, *args, **kwargs):
        if tool not in AGENT_TOOLS.get(agent, frozenset()):
            self.denied.append({"agent": agent, "tool": tool})
            raise DomainError("tool_not_allowed", f"Agent {agent} không được dùng công cụ {tool}.", 403)
        if len(self.calls) >= self.max_steps:
            raise DomainError("agent_step_limit", "Lượt xử lý vượt số bước cho phép.", 429)
        self.calls.append({"agent": agent, "tool": tool})
        return function(*args, **kwargs)

    def summary(self, agent: str) -> dict:
        return {"agent": agent, "tools": [item["tool"] for item in self.calls], "steps": len(self.calls)}
