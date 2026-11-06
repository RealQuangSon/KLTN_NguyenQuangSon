"""HN-09 — cassette ghi/phát lại lượt live để tái lập bằng chứng trong luận văn.

`HOMEMATCH_AGENT_RECORD=path`: mỗi lần gọi model (chat completions của vòng lặp)
hoặc Jev (Decisions API) được ghi một dòng vào cassette JSON. Request gửi provider
LÀ bản đã redact (model/Jev không bao giờ thấy văn bản chưa che) nên cassette
không chứa PII/thu nhập. `HOMEMATCH_AGENT_REPLAY=path`: các lần gọi được phát
lại theo thứ tự từ cassette, KHÔNG gọi mạng — chạy lại miễn phí, kết quả giống
lượt gốc vì cả usage (token/cost) cũng được phát lại.

Chỉ một trong hai env nên đặt cùng lúc; ghi ưu tiên hơn phát lại khi cả hai đều có.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace

_lock = threading.Lock()
# Trạng thái phát lại khóa theo đường dẫn: đổi cassette (run/test khác) thì
# phát lại từ đầu, trong cùng cassette thì con trỏ chạy tiếp qua các lượt.
_state = {"path": None, "entries": None, "cursor": 0}


def _record_path() -> str | None:
    return os.getenv("HOMEMATCH_AGENT_RECORD") or None


def _replay_path() -> str | None:
    if _record_path():
        return None
    return os.getenv("HOMEMATCH_AGENT_REPLAY") or None


def _replay_entries(path: str) -> list[dict]:
    with _lock:
        if _state["path"] != path or _state["entries"] is None:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            entries = payload.get("entries") if isinstance(payload, dict) else payload
            if not isinstance(entries, list):
                raise ValueError("cassette phải là JSON object có 'entries' (hoặc mảng)")
            _state.update(path=path, entries=entries, cursor=0)
        return _state["entries"]


def _next_replay(kind: str, path: str) -> dict:
    entries = _replay_entries(path)
    with _lock:
        index = _state["cursor"]
        _state["cursor"] = index + 1
    if index >= len(entries):
        raise RuntimeError(f"cassette_exhausted:{kind}:{index}")
    entry = entries[index]
    if entry.get("kind") != kind:
        raise RuntimeError(f"cassette_kind_mismatch:{kind}:{entry.get('kind')}")
    return entry.get("response")


def _append_record(path: str, kind: str, request, response) -> None:
    with _lock:
        payload = {"kind": "agent_cassette", "version": 1, "entries": []}
        file = Path(path)
        if file.exists():
            payload = json.loads(file.read_text(encoding="utf-8"))
            payload.setdefault("entries", [])
        payload["entries"].append({"kind": kind, "request": request, "response": response})
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _serialize_completion(completion) -> dict:
    message = completion.choices[0].message
    usage = getattr(completion, "usage", None)
    return {
        "content": message.content,
        "tool_calls": [{"id": call.id, "name": call.function.name,
                        "arguments": call.function.arguments}
                       for call in (getattr(message, "tool_calls", None) or [])],
        "usage": {key: getattr(usage, key, None) for key in
                  ("total_tokens", "prompt_tokens", "completion_tokens", "cost")},
    }


def _deserialize_completion(data: dict):
    message = SimpleNamespace(
        content=data.get("content"),
        tool_calls=[SimpleNamespace(id=item["id"],
                                    function=SimpleNamespace(name=item["name"],
                                                             arguments=item["arguments"]))
                    for item in data.get("tool_calls") or []])
    usage_data = {key: value for key, value in (data.get("usage") or {}).items()}
    return SimpleNamespace(choices=[SimpleNamespace(message=message)],
                           usage=SimpleNamespace(**usage_data))


def model_call(params: dict, live):
    """Gọi provider qua cassette: record ghi request/response; replay trả bản ghi.

    Request là messages/redacted mà vòng lặp chuẩn bị để gửi thật — không sao
    chép thêm dữ liệu nhạy cảm nào khác."""
    replay = _replay_path()
    if replay:
        return _deserialize_completion(_next_replay("model", replay))
    completion = live()
    record = _record_path()
    if record:
        request = {"messages": [dict(message, tool_calls=message.get("tool_calls"))
                                for message in params.get("messages", [])]}
        _append_record(record, "model", request, _serialize_completion(completion))
    return completion


def jev_call(payload: dict, live):
    """Gọi Jev qua cassette (payload đã qua decision_context/redact)."""
    replay = _replay_path()
    if replay:
        return _next_replay("jev", replay)
    response = live(payload)
    record = _record_path()
    if record:
        _append_record(record, "jev", payload, response)
    return response
