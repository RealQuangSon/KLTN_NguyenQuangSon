"""Per-session budget for interpreter/provider calls.

One logical assistant turn that needs extraction spends one unit, whether the
interpreter is the offline rule demo or a live provider. Exceeding the budget is
an explicit DomainError (HTTP 429) — the service never retries silently and
never spins a retry storm. Deterministic routes (explicit cost/support keywords,
viewing preparation) do not consume budget so users keep an escape hatch after
exhaustion.
"""
from __future__ import annotations

from .models import DomainError


class SessionCallBudget:
    def __init__(self, limit: int):
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("Session call budget must be a positive integer")
        self.limit = limit
        self._counts: dict[str, int] = {}

    def spend(self, session_id: str) -> int:
        """Charge one logical call; raise budget_exceeded once the cap is hit."""
        used = self._counts.get(session_id, 0)
        if used >= self.limit:
            raise DomainError("budget_exceeded",
                              "Phiên đã đạt giới hạn lượt gọi trợ lý AI; vui lòng dùng biểu mẫu nhập nhu cầu.", 429)
        self._counts[session_id] = used + 1
        return self._counts[session_id]

    def used(self, session_id: str) -> int:
        return self._counts.get(session_id, 0)
