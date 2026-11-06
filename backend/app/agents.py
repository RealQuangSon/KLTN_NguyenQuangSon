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

from threading import Lock
from typing import Callable

from pydantic import ValidationError

from .agent_tools import TOOL_REGISTRY, public_result, tools_by_agent
from .models import DomainError

AGENT_TOOLS: dict[str, frozenset[str]] = tools_by_agent()
MAX_STEPS = 4


class ToolBox:
    """One instance per turn/run; records which agent called which tool."""

    def __init__(self, max_steps: int = MAX_STEPS):
        self.max_steps = max_steps
        self.calls: list[dict] = []
        self.denied: list[dict] = []
        self._lock = Lock()

    def call(self, agent: str, tool: str, function: Callable, *args, **kwargs):
        # Chỉ giữ khóa khi dành bước; tool chỉ đọc được chạy song song ở executor.
        with self._lock:
            if tool not in AGENT_TOOLS.get(agent, frozenset()):
                self.denied.append({"agent": agent, "tool": tool})
                raise DomainError("tool_not_allowed", f"Agent {agent} không được dùng công cụ {tool}.", 403)
            if len(self.calls) >= self.max_steps:
                raise DomainError("agent_step_limit", "Lượt xử lý vượt số bước cho phép.", 429)
            self.calls.append({"agent": agent, "tool": tool})
        return function(*args, **kwargs)

    def invoke(self, name: str, function: Callable, arguments: dict) -> dict:
        """Biên model: kiểm schema rồi gọi qua allowlist và chuẩn hóa kết quả.

        Graph cũ tiếp tục dùng call() để nhận object nghiệp vụ nguyên bản.
        Không ghi tham số lỗi hay nội dung exception vào phản hồi của provider.
        """
        definition = TOOL_REGISTRY.get(name)
        if definition is None:
            return {"ok": False, "error": "tool_unavailable", "message": "Công cụ không có trong registry.",
                    "hint": "Chọn một công cụ trong danh sách được cấp."}
        try:
            parsed = definition.Args.model_validate(arguments)
            result = self.call(definition.agent, name, function,
                               **parsed.model_dump(mode="json", exclude_unset=True))
            return {"ok": True, "data": public_result(result)}
        except ValidationError:
            return {"ok": False, "error": "invalid_patch" if name == "update_needs" else "invalid_arguments",
                    "message": "Tham số chưa đúng hợp đồng công cụ.",
                    "hint": "Dùng đúng tên trường và kiểu dữ liệu trong schema; không gửi trường tiền hay quyền."}
        except DomainError as error:
            if error.code == "needs_clarification":
                field = getattr(error, "field", "other")
                if field not in {"destination_radius", "budget_scope", "area", "room_type", "people"}:
                    field = "other"
                return {"ok": False, "error": error.code, "field": field,
                        "message": "Cần làm rõ nhu cầu trước khi tìm.",
                        "hint": f"Gọi ask_user(field='{field}') để lấy lựa chọn từ kho."}
            return {"ok": False, "error": error.code, "message": definition.redact(str(error)),
                    "hint": {"unknown_place": "Gọi find_place để kiểm chứng điểm mốc trước.",
                             "needs_more_info": "Hỏi thành phố và mức tiền trước khi tìm.",
                             "not_visible": "Chọn căn trong kết quả hiện tại hoặc workspace.",
                             "stale_profile": "Đọc lại hồ sơ và xác nhận revision hiện tại."}.get(
                                 error.code, "Kiểm tra thông tin từ khách và sửa tham số trước khi thử lại.")}
        except Exception:
            return {"ok": False, "error": "tool_failed", "message": "Công cụ tạm chưa xử lý được yêu cầu.",
                    "hint": "Thử lại hoặc đề nghị khách dùng biểu mẫu."}

    def summary(self, agent: str) -> dict:
        with self._lock:
            return {"agent": agent, "tools": [item["tool"] for item in self.calls], "steps": len(self.calls)}
