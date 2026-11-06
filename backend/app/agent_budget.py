"""Per-session budget for AI turns (HN-06).

The unit is a CHAT TURN that needs the AI (agent loop or interview extraction),
not an LLM call — a turn with several model calls spends one turn. Deterministic
routes (explicit cost/support keywords, viewing preparation, fast path) never
consume or check the budget, so users keep an escape hatch after exhaustion.
A cumulative session cost cap (USD, from provider-reported usage) also trips the
budget: the next AI turn answers HTTP 429 with a friendly message pointing at
the form; the turn that crossed the cap still finishes normally.
"""
from __future__ import annotations

from .models import DomainError


class SessionTurnBudget:
    def __init__(self, turn_limit: int, cost_cap_usd: float = 0.05):
        if not isinstance(turn_limit, int) or turn_limit < 1:
            raise ValueError("Session turn budget must be a positive integer")
        if cost_cap_usd < 0:
            raise ValueError("Session cost cap must not be negative")
        self.turn_limit = turn_limit
        self.cost_cap_usd = cost_cap_usd
        self._turns: dict[str, int] = {}
        self._costs: dict[str, float] = {}

    def ensure_turn(self, session_id: str) -> int:
        """Charge one AI chat turn; raise budget_exceeded (HTTP 429) when the
        turn budget is exhausted or the session cost cap is already over."""
        turns = self._turns.get(session_id, 0)
        if turns >= self.turn_limit:
            raise DomainError("budget_exceeded",
                              "Phiên đã đạt giới hạn lượt trợ lý AI. Bạn vẫn dùng được biểu mẫu "
                              "nhu cầu, tìm kiếm, lọc và các mục khác nhé.", 429)
        if self._costs.get(session_id, 0.0) > self.cost_cap_usd:
            raise DomainError("budget_exceeded",
                              "Phiên đã vượt trần chi phí trợ lý AI. Bạn vẫn dùng được biểu mẫu "
                              "nhu cầu, tìm kiếm, lọc và các mục khác nhé.", 429)
        self._turns[session_id] = turns + 1
        return self._turns[session_id]

    def record_cost(self, session_id: str, cost_usd: float | None) -> None:
        """Accumulate provider-reported cost (OpenRouter `usage.cost`, Jev
        `usage.cost`). Unknown/absent cost is never estimated."""
        if not cost_usd:
            return
        try:
            self._costs[session_id] = self._costs.get(session_id, 0.0) + float(cost_usd)
        except (TypeError, ValueError):
            return  # dữ liệu provider hỏng không được làm lệch bộ đếm

    def used(self, session_id: str) -> int:
        return self._turns.get(session_id, 0)

    def spent_usd(self, session_id: str) -> float:
        return round(self._costs.get(session_id, 0.0), 6)
