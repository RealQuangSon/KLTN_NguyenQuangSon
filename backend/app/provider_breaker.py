"""HN-07 — circuit breaker cho provider ngoài.

5 lỗi liên tiếp trong cửa sổ 60 s → bỏ qua provider đó 120 s (mở). Gọi khi breaker
đang mở sẽ bị từ chối ngay mà không chạm mạng; một lần thành công đóng lại và đếm
từ đầu. Dùng chung cho model chat (khóa `chat:<model>`) và Jev (khóa `jev`).
"""
from __future__ import annotations

import threading
import time

THRESHOLD = 5
WINDOW_S = 60.0
OPEN_S = 120.0

_lock = threading.Lock()
_state: dict[str, dict] = {}


def _now() -> float:
    return time.monotonic()


def open_(key: str) -> bool:
    """True khi provider đang bị bỏ qua (breaker mở, chưa hết 120 s)."""
    with _lock:
        state = _state.get(key)
        if not state:
            return False
        until = state.get("open_until")
        if until and _now() < until:
            return True
        if until:
            # Hết hạn mở: đóng breaker, đếm lỗi lại từ đầu.
            _state[key] = {"consecutive": 0, "last_at": None, "open_until": None}
        return False


def record(key: str, ok: bool) -> None:
    """Ghi một kết quả gọi provider; thành công đóng breaker, lỗi cộng chuỗi."""
    with _lock:
        state = _state.setdefault(key, {"consecutive": 0, "last_at": None, "open_until": None})
        now = _now()
        if ok:
            state.update(consecutive=0, last_at=None, open_until=None)
            return
        consecutive = state["consecutive"] + 1
        last_at = state.get("last_at")
        if last_at is not None and now - last_at > WINDOW_S:
            consecutive = 1  # lỗi rải rác ngoài cửa sổ không tính là liên tiếp
        state.update(consecutive=consecutive, last_at=now)
        if consecutive >= THRESHOLD:
            state["open_until"] = now + OPEN_S


def reset(key: str | None = None) -> None:
    """Dọn trạng thái (test; không dùng ở runtime)."""
    with _lock:
        if key is None:
            _state.clear()
        else:
            _state.pop(key, None)
