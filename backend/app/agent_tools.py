"""HN-03: nguồn duy nhất cho hợp đồng và quyền gọi công cụ của harness.

Công cụ nội bộ của graph vẫn có hợp đồng nhưng không gửi cho model. Hàm
nghiệp vụ được gắn vào phiên ở executor; registry không giữ repo hay dữ liệu
khách, và không tự cấp quyền trên bản ghi.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .agent_guard import redact
from .conversations import mask_pii


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EmptyArgs(ToolArgs):
    pass


class FindPlaceArgs(ToolArgs):
    query: str = Field(min_length=1, max_length=200)
    city_hint: Literal["TP.HCM", "Hà Nội"] | None = None


class NeedsPatch(ToolArgs):
    city: Literal["TP.HCM", "Hà Nội"] | None = None
    area: str | None = Field(default=None, max_length=120)
    people: int | None = Field(default=None, ge=1, le=20)
    room_type: Literal["room", "studio", "apartment"] | None = None
    bedrooms: int | None = Field(default=None, ge=0, le=20)
    preferences: list[str] | None = Field(default=None, max_length=30)
    needs_destination: bool | None = None
    accept_estimated_data: bool | None = None
    soft_description: str | None = Field(default=None, max_length=2000)
    destination_text: str | None = Field(default=None, max_length=200)


class UpdateNeedsArgs(ToolArgs):
    patch: NeedsPatch


class AskUserArgs(ToolArgs):
    field: Literal["destination_radius", "budget_scope", "area", "room_type", "people", "other"]
    question: str | None = Field(default=None, min_length=1, max_length=300)
    options: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def options_only_for_other(self):
        if self.field != "other" and self.options:
            raise ValueError("Lựa chọn phải do lớp hỏi lại dựng từ kho; model chỉ chọn field")
        if self.field == "other" and self.question is None:
            raise ValueError("Câu hỏi khác cần nội dung question")
        return self


class RoomReferenceArgs(ToolArgs):
    room_ref: str = Field(min_length=1, max_length=200)


class EstimateCostArgs(ToolArgs):
    room_id: str = Field(min_length=1, max_length=200)


class HandbookArgs(ToolArgs):
    question: str = Field(min_length=1, max_length=2000)


class ExtractNeedsArgs(ToolArgs):
    text: str = Field(min_length=1, max_length=2000)
    draft: dict[str, Any] | None = None


class UpdateDraftArgs(ToolArgs):
    session_id: str
    draft: dict[str, Any]
    expected_revision: int | None = Field(default=None, ge=0)


class ReadMemoryArgs(ToolArgs):
    user_id: str


class FinanceArgs(ToolArgs):
    request: dict[str, Any]


class MatchCatalogArgs(ToolArgs):
    profile: dict[str, Any]
    method: Literal["B1", "P"] = "B1"


class SemanticArgs(ToolArgs):
    query: str
    room_ids: list[str]


class ExplainCandidateArgs(ToolArgs):
    room_id: str
    profile: dict[str, Any]


class RequestSupportArgs(ToolArgs):
    session_id: str


class OpenConversationArgs(ToolArgs):
    room_id: str
    session_id: str


_PRIVATE_KEYS = frozenset({"monthly_income_vnd", "housing_ratio", "income",
                           "phone", "phone_number", "email", "contact_phone"})
_ROOM_IDENTIFIER = re.compile(r"(?:chotot-\d+|synthetic-room-\d+|demo-\d+|room-[0-9a-fA-F]{10})")
_UUID_IDENTIFIER = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


def _identifier_field(name: str | None) -> bool:
    return name == "id" or bool(name and name.endswith(("_id", "_ids")))


def _valid_identifier(name: str | None, value: str) -> bool:
    if not _identifier_field(name):
        return False
    return bool(_UUID_IDENTIFIER.fullmatch(value) or _ROOM_IDENTIFIER.fullmatch(value))


def _project_result(value: Any, mask: Callable[[str], str], name: str | None = None,
                    private_keys: frozenset[str] = _PRIVATE_KEYS) -> Any:
    """Mã bản ghi đã đúng định dạng không phải văn bản liên hệ để che PII."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {mask(str(key)): _project_result(item, mask, str(key), private_keys) for key, item in value.items()
                if str(key).lower() not in private_keys and "income" not in str(key).lower()}
    if isinstance(value, (list, tuple)):
        return [_project_result(item, mask, name, private_keys) for item in value]
    if isinstance(value, str):
        return value if _valid_identifier(name, value) else mask(value)
    if value is not None and _identifier_field(name):
        return mask(str(value))
    return value


def public_result(value: Any, *, for_renter: bool = False) -> Any:
    """DTO cho khách và cache retry: che liên hệ, bỏ thu nhập, giữ giá từ tool."""
    # Khách được xem tỷ lệ tài chính của chính mình; tool/model/trace thì không.
    private_keys = _PRIVATE_KEYS - {"housing_ratio"} if for_renter else _PRIVATE_KEYS
    return _project_result(value, mask_pii, private_keys=private_keys)


def redact_result(value: Any) -> Any:
    """Bỏ trường suy ra thu nhập và che văn bản trước khi trả về model.

    Giá số do tool tài chính trả về được giữ; tiền trong văn bản được tách
    trước model. Thu nhập và tỷ lệ suy ra thu nhập luôn bị bỏ, kể cả trong
    object Pydantic lồng nhau. DTO cho khách dùng public_result riêng.
    """
    return _project_result(value, redact)


def _search_view(draft) -> tuple[str, dict]:
    destination = draft.get("destination") if isinstance(draft, dict) else getattr(draft, "destination", None)
    return ("map" if destination else "list"), {"sorted_by": "distance" if destination else "match"}


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    agent: str
    description: str
    Args: type[ToolArgs]
    writes: bool
    timeout_s: float
    view: str | Callable | None
    capability: str
    sample_args: dict = field(default_factory=dict)
    exposed: bool = True
    success_summary: str = "Đã xử lý công cụ."
    redact: Callable[[Any], Any] = redact_result
    # Tool mới có thể đặt nghiệp vụ ngay cạnh khai báo; executor gắn ngữ cảnh
    # (service, session, actor, toolbox) trước khi truyền tham số đã kiểm.
    handler: Callable | None = None

    def spec(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": self.Args.model_json_schema()}}

    def summarize(self, result: Any) -> str:
        # Chỉ dùng câu đã khai báo; không đưa note/exception/model text vào trace.
        if isinstance(result, dict) and (result.get("ok") is False or result.get("error")):
            code = result.get("error")
            if isinstance(code, str) and re.fullmatch(r"[a-z_]{1,60}", code):
                return f"Lỗi {code}; cần kiểm tra thông tin đầu vào."
            return "Công cụ chưa hoàn tất; cần kiểm tra thông tin đầu vào."
        return self.success_summary


def _definition(name: str, agent: str, description: str, Args: type[ToolArgs], *,
                writes: bool = False, view=None, capability: str = "chat:message",
                sample_args: dict | None = None, exposed: bool = True,
                summary: str = "Đã xử lý công cụ.", handler: Callable | None = None) -> ToolDefinition:
    return ToolDefinition(name, agent, description, Args, writes, 8.0, view, capability,
                          sample_args or {}, exposed, summary, handler=handler)


_DEFINITIONS = (
    _definition("find_place", "needs", "Tra điểm mốc theo tên; kiểm chứng thành phố và tọa độ.",
                FindPlaceArgs, sample_args={"query": "HUST", "city_hint": "Hà Nội"},
                summary="Đã tra điểm mốc trong danh mục."),
    _definition("update_needs", "needs", "Ghi nhu cầu đã kiểm chứng vào nháp; cấm tiền, thu nhập và quyền hạn.",
                UpdateNeedsArgs, writes=True, capability="draft:patch", sample_args={"patch": {"city": "Hà Nội"}},
                summary="Đã ghi nhu cầu vào hồ sơ nháp."),
    _definition("search_rooms", "needs", "Đếm căn khớp nhu cầu nháp và trả giá từ kho; không ghi dữ liệu.",
                EmptyArgs, summary="Đã kiểm tra số căn khớp nhu cầu."),
    _definition("confirm_and_search", "needs", "Xác nhận hồ sơ từ nháp rồi xếp hạng và công bố kết quả hiện tại.",
                EmptyArgs, writes=True, view=_search_view, capability="profile:confirm",
                summary="Đã xác nhận nhu cầu và chạy tìm phòng."),
    _definition("ask_user", "needs", "Chọn field cần làm rõ; hệ thống dựng lựa chọn có số căn từ kho và Jev. "
                "Chỉ field=other mới nhận câu hỏi và tối đa bốn lựa chọn chữ của model.",
                AskUserArgs, writes=True,
                sample_args={"field": "other", "question": "Bạn muốn tìm tại thành phố nào?", "options": ["Hà Nội", "TP.HCM"]},
                summary="Đã chuẩn bị câu hỏi làm rõ nhu cầu."),
    _definition("room_details", "needs", "Xem căn trong kết quả hiện tại bằng mã hoặc thứ tự trong workspace.",
                RoomReferenceArgs, view="detail", capability="results:read", sample_args={"room_ref": "căn số 2"},
                summary="Đã lấy thông tin căn đang xem."),
    _definition("estimate_cost", "finance", "Tính chi phí và khả năng chi trả bằng công cụ tất định.",
                EstimateCostArgs, view="cost", capability="results:read", sample_args={"room_id": "demo-01"},
                summary="Đã tính chi phí từ dữ liệu hiện có."),
    _definition("search_handbook", "handbook", "Tra cẩm nang quyền lợi, tiền cọc và nội quy người thuê.",
                HandbookArgs, sample_args={"question": "Thủ tục tạm trú?"},
                summary="Đã tra cẩm nang người thuê."),
    _definition("open_landlord_chat", "support", "Mở hội thoại với chủ nhà của căn trong kết quả hiện tại.",
                RoomReferenceArgs, writes=True, capability="support:handoff", sample_args={"room_ref": "demo-01"},
                summary="Đã mở hội thoại với chủ nhà."),
    _definition("prepare_viewing", "needs", "Chuẩn bị lịch xem; khách chọn giờ và xác nhận trên giao diện mới tạo lịch.",
                RoomReferenceArgs, writes=True, capability="viewing:prepare", sample_args={"room_ref": "demo-01"},
                summary="Đã chuẩn bị thông tin; lịch xem chưa được tạo."),
    _definition("extract_needs", "needs", "Trích nhu cầu cho graph nội bộ.", ExtractNeedsArgs,
                sample_args={"text": "Phòng ở Hà Nội"}, exposed=False),
    _definition("update_draft", "needs", "Ghi hồ sơ nháp có revision cho graph nội bộ.", UpdateDraftArgs,
                writes=True, capability="draft:patch", sample_args={"session_id": "fixture", "draft": {}}, exposed=False),
    _definition("read_memory", "needs", "Đọc sở thích đã được đồng ý lưu.", ReadMemoryArgs,
                sample_args={"user_id": "renter-a"}, exposed=False),
    _definition("calculate_cost", "finance", "Tính chi phí từ bảng giá đã kiểm tra.", FinanceArgs,
                sample_args={"request": {}}, exposed=False),
    _definition("assess_affordability", "finance", "Đánh giá khả năng chi trả bằng công thức tất định.", FinanceArgs,
                sample_args={"request": {}}, exposed=False),
    _definition("estimate_loan", "finance", "Tính khoản vay bằng engine tài chính.", FinanceArgs,
                sample_args={"request": {}}, exposed=False),
    _definition("simulate_scenarios", "finance", "Mô phỏng kịch bản tài chính bằng engine.", FinanceArgs,
                sample_args={"request": {}}, exposed=False),
    _definition("match_catalog", "ranking", "Lọc cứng và xếp hạng kho hiện tại.", MatchCatalogArgs,
                sample_args={"profile": {}}, exposed=False),
    _definition("semantic_scores", "ranking", "Đọc điểm tương đồng ngữ nghĩa khi được cấu hình.", SemanticArgs,
                sample_args={"query": "yên tĩnh", "room_ids": ["demo-01"]}, exposed=False),
    _definition("explain_candidate", "ranking", "Giải thích ứng viên từ các điểm tất định.", ExplainCandidateArgs,
                sample_args={"room_id": "demo-01", "profile": {}}, exposed=False),
    _definition("request_support", "support", "Lưu phiếu hỗ trợ để quản trị viên tiếp nhận.", RequestSupportArgs,
                writes=True, capability="support:handoff", sample_args={"session_id": "fixture"}, exposed=False),
    _definition("open_conversation", "support", "Mở hội thoại chủ nhà từ graph nội bộ.", OpenConversationArgs,
                writes=True, capability="support:handoff", sample_args={"room_id": "demo-01", "session_id": "fixture"}, exposed=False),
)

TOOL_REGISTRY = {definition.name: definition for definition in _DEFINITIONS}
if len(TOOL_REGISTRY) != len(_DEFINITIONS):
    raise ValueError("Registry có tên công cụ trùng nhau")


def tool_specs() -> list[dict]:
    return [definition.spec() for definition in TOOL_REGISTRY.values() if definition.exposed]


def tools_by_agent() -> dict[str, frozenset[str]]:
    agents = {definition.agent for definition in TOOL_REGISTRY.values()}
    return {agent: frozenset(definition.name for definition in TOOL_REGISTRY.values()
                             if definition.agent == agent) for agent in agents}


def tool_capabilities() -> dict[str, str]:
    return {name: definition.capability for name, definition in TOOL_REGISTRY.items()}


def workspace_view(successful_tools: list[str], draft) -> tuple[str, dict | None]:
    """Chỉ công cụ thành công mới được mở view; tool không có view giữ nguyên."""
    for name in reversed(successful_tools):
        definition = TOOL_REGISTRY.get(name)
        if definition is None or definition.view is None:
            continue
        return definition.view(draft) if callable(definition.view) else (definition.view, None)
    return "keep", None
