"""Gọi tool qua hợp đồng chung, giữ mutation và khóa retry trong cùng transaction."""
from __future__ import annotations

import hashlib
import json

from .agent_tools import TOOL_REGISTRY, public_result
from .agent_capability import Resource, require
from .repository import utc_now


class _RollbackTool(Exception):
    pass


def execute_tool(service, toolbox, session_id: str, turn_id: str,
                 name: str, function, arguments: dict, *, actor) -> dict:
    definition = TOOL_REGISTRY[name]
    session = service.repo.session(session_id)
    require(definition.capability, actor, Resource.for_session(session))
    if not definition.writes:
        return toolbox.invoke(name, function, arguments)
    args_hash = hashlib.sha256(json.dumps(arguments, sort_keys=True,
                                         ensure_ascii=False).encode()).hexdigest()
    result: dict = {}
    previous_assumptions = list(getattr(toolbox, "assumptions", []))
    previous_question = getattr(toolbox, "question_asked", False)
    try:
        with service.repo.db:
            cached = service.repo.db.execute(
                "SELECT result_json FROM hm_agent_tool_calls "
                "WHERE session_id=? AND turn_id=? AND tool=? AND args_hash=?",
                (session_id, turn_id, name, args_hash)).fetchone()
            if cached:
                return toolbox.call(definition.agent, name, lambda: json.loads(cached["result_json"]))
            result = toolbox.invoke(name, function, arguments)
            if not result["ok"]:
                if name == "confirm_and_search" and result.get("error") == "needs_clarification":
                    # Preflight chỉ đã ghi diễn giải an toàn; chưa tạo run. Giữ
                    # nháp này để chip và giả định khách thấy cùng một phiên bản.
                    return result
                raise _RollbackTool()
            service.repo.db.execute("INSERT INTO hm_agent_tool_calls VALUES(?,?,?,?,?,?,?)",
                (session_id, turn_id, name, args_hash, f"{turn_id}:{name}:{args_hash}",
                 json.dumps(public_result(result), ensure_ascii=False, default=str), utc_now()))
    except _RollbackTool:
        toolbox.assumptions = previous_assumptions
        toolbox.question_asked = previous_question
    return result
