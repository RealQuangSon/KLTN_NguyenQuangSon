"""HN-03: nguồn duy nhất cho hợp đồng và quyền gọi công cụ của harness.

Công cụ nội bộ của graph vẫn có hợp đồng nhưng không gửi cho model. Hàm
nghiệp vụ được gắn vào phiên ở executor; registry không giữ repo hay dữ liệu
khách, và không tự cấp quyền trên bản ghi.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Annotated, Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import WithJsonSchema

from .agent_guard import redact
from .conversations import mask_pii
from .copilot import AMENITY_TEXT
from .models import AMENITY_KEYS


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EmptyArgs(ToolArgs):
    pass


class FindPlaceArgs(ToolArgs):
    query: str = Field(min_length=1, max_length=200)
    city_hint: Literal["TP.HCM", "Hà Nội"] | None = None


# Sửa luồng UX (14/11): model gọi sai update_needs hai lần mỗi lượt — gửi trường
# tiền bị cấm (invalid_patch) rồi tên tiện ích bằng lời thay vì khóa từ điển
# (invalid_amenity). Schema là hợp đồng model đọc: enum tiện ích sinh từ
# AMENITY_KEYS kèm nghĩa tiếng Việt (nhãn có sẵn trong copilot.AMENITY_TEXT cho
# 9 khóa cũ). Kiểm tra runtime GIỮ list[str] — hàng rào invalid_amenity trong
# agent_loop.update_needs vẫn từ chối có cấu trúc để model sửa trong cùng lượt;
# WithJsonSchema chỉ đổi JSON schema gửi model, không đổi kiểm tra.
AMENITY_LABELS = {**AMENITY_TEXT,
                  "kitchen": "bếp nấu được", "wifi": "wifi/internet", "elevator": "thang máy",
                  "security_24h": "an ninh 24 giờ", "camera": "camera an ninh", "loft": "gác lửng",
                  "flexible_hours": "giờ giấc tự do", "no_shared_landlord": "không ở chung với chủ",
                  "water_heater": "máy nước nóng", "fridge": "tủ lạnh"}
AMENITY_ENUM_DESCRIPTION = ("Nghĩa từng khóa: "
                            + ", ".join(f"{key} = {AMENITY_LABELS.get(key, key)}" for key in AMENITY_KEYS))
_PREFERENCES_JSON = WithJsonSchema({
    "type": "array",
    "items": {"type": "string", "enum": list(AMENITY_KEYS),
              "description": AMENITY_ENUM_DESCRIPTION},
    "maxItems": 30,
    "description": "Mỗi phần tử PHẢI là một khóa trong enum — KHÔNG viết tên tiện ích bằng lời "
                   "(\"máy lạnh\") hay từ viết tắt (\"ac\").",
})


class NeedsPatch(ToolArgs):
    city: Literal["TP.HCM", "Hà Nội"] | None = None
    area: str | None = Field(default=None, max_length=120)
    people: int | None = Field(default=None, ge=1, le=20)
    room_type: Literal["room", "studio", "apartment"] | None = None
    bedrooms: int | None = Field(default=None, ge=0, le=20)
    preferences: Annotated[list[str] | None, _PREFERENCES_JSON] = Field(default=None, max_length=30)
    needs_destination: bool | None = None
    soft_description: str | None = Field(default=None, max_length=2000)
    destination_text: str | None = Field(default=None, max_length=200)


class UpdateNeedsArgs(ToolArgs):
    patch: NeedsPatch


class AskUserArgs(ToolArgs):
    field: Literal["destination", "budget_cap", "destination_radius", "budget_scope",
                   "city", "area", "room_type", "people", "other"]
    question: str | None = Field(default=None, min_length=1, max_length=300)
    # HN-13.2: một câu ngắn vì sao câu trả lời làm đổi kết quả — đi vào DTO kèm
    # câu hỏi (FE hiển thị dưới câu hỏi); qua hậu kiểm như question.
    reason: str | None = Field(default=None, min_length=1, max_length=300)
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


class CompareRoomsArgs(ToolArgs):
    room_refs: list[str] = Field(min_length=2, max_length=3)


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
                           "phone", "phone_number", "email", "contact_phone",
                           # C1b/CA-04/crawl.md B-2,C-1: dữ liệu hiển thị từ tin cào
                           # (ảnh, video, tầng, hướng, loại hình) và tên người đăng
                           # không đi vào kết quả tool gửi model, prompt hay embedding.
                           "poster_name", "source_images", "source_videos", "toilets",
                           "project_name", "floor", "direction", "balcony_direction",
                           "property_subtype",
                           # crawl.md E-01/R3: liên hệ của lịch xem chỉ ở projection
                           # lịch cho đúng người đọc — không cho model/prompt/log.
                           "contact_name", "contact_phone", "contact_consent_at"})
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


PHASES = ("interview", "results", "transaction")


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
    # HN-11: các pha agent được phép dùng tool (mặc định: cả ba pha).
    phases: tuple[str, ...] = PHASES

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
                summary: str = "Đã xử lý công cụ.", handler: Callable | None = None,
                phases: tuple[str, ...] = PHASES) -> ToolDefinition:
    return ToolDefinition(name, agent, description, Args, writes, 8.0, view, capability,
                          sample_args or {}, exposed, summary, handler=handler, phases=phases)


_DEFINITIONS = (
    _definition("find_place", "needs", "Tra điểm mốc theo tên; kiểm chứng thành phố và tọa độ.",
                FindPlaceArgs, sample_args={"query": "HUST", "city_hint": "Hà Nội"},
                summary="Đã tra điểm mốc trong danh mục."),
    _definition("update_needs", "needs", "Ghi nhu cầu đã kiểm chứng vào nháp; cấm thu nhập và quyền hạn. "
                "KHÔNG gửi bất kỳ trường tiền nào (budget_hint_vnd, monthly_budget_vnd, budget_min_vnd…): "
                "mức tiền, khoảng tiền và diện tích mong muốn hệ thống tự đọc tất định từ câu của khách. "
                "preferences chỉ gửi khóa tiện ích đúng trong enum của schema, không viết bằng lời.",
                UpdateNeedsArgs, writes=True, capability="draft:patch",
                sample_args={"patch": {"city": "Hà Nội", "preferences": ["air_conditioning"]}},
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
                summary="Đã lấy thông tin căn đang xem.", phases=("results", "transaction")),
    _definition("estimate_cost", "finance", "Tính chi phí và khả năng chi trả bằng công cụ tất định.",
                EstimateCostArgs, view="cost", capability="results:read", sample_args={"room_id": "demo-01"},
                summary="Đã tính chi phí từ dữ liệu hiện có.", phases=("results", "transaction")),
    _definition("simulate_loan", "finance",
                "Chạy lại mô phỏng vay bằng chính câu của khách qua engine tài chính; không nhận tham số tiền. "
                "Trả thẻ mô phỏng với số từ costs.py để diễn giải.",
                EmptyArgs, writes=True, capability="results:read",
                summary="Đã chạy mô phỏng vay bằng engine tài chính.", phases=("results", "transaction")),
    _definition("compare_rooms", "ranking",
                "So sánh 2–3 căn trong kết quả hiện tại bằng advisor tất định (chỉ đọc, không đổi thứ hạng).",
                CompareRoomsArgs, capability="results:read", sample_args={"room_refs": ["căn số 1", "căn số 2"]},
                summary="Đã so sánh các căn theo dữ liệu tất định.", phases=("results", "transaction")),
    _definition("search_handbook", "handbook", "Tra cẩm nang quyền lợi, tiền cọc và nội quy người thuê.",
                HandbookArgs, sample_args={"question": "Thủ tục tạm trú?"},
                summary="Đã tra cẩm nang người thuê."),
    _definition("open_landlord_chat", "support", "Mở hội thoại với chủ nhà của căn trong kết quả hiện tại.",
                RoomReferenceArgs, writes=True, capability="support:handoff", sample_args={"room_ref": "demo-01"},
                summary="Đã mở hội thoại với chủ nhà.", phases=("transaction",)),
    _definition("prepare_viewing", "needs", "Chuẩn bị lịch xem; khách chọn giờ và xác nhận trên giao diện mới tạo lịch.",
                RoomReferenceArgs, writes=True, capability="viewing:prepare", sample_args={"room_ref": "demo-01"},
                summary="Đã chuẩn bị thông tin; lịch xem chưa được tạo.", phases=("transaction",)),
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

# Multi-agent (HN-13): roster khai báo MỘT CHỖ — mỗi role một system prompt và
# một bộ tool. Phase vẫn lọc thêm (room_details không có ở interview…), nên bộ
# tool thực tế của lượt = roster[role] ∩ phases[phase].
# NEEDS prompt giữ NGUYÊN VĂN prompt một vòng lặp cũ (AGENT_SYSTEM_PROMPT) để
# HOMEMATCH_INPUT_ANALYST=off đúng hành vi cũ tới từng byte (test cũ, cassette).
NEEDS_SYSTEM_PROMPT = """Bạn là trợ lý tìm phòng trọ HomeMatch cho khách tại TP.HCM và Hà Nội.
Dùng hiểu biết chung để hiểu địa danh, khu vực và nhu cầu ngầm ("gần HUST", "phòng 2 người", "nới thêm tiền").
Khi suy ra điều khách chưa nói rõ, gọi tool để kiểm chứng rồi nói lại giả định cho khách sửa ("Mình hiểu HUST ở Đại Cồ Việt, Hai Bà Trưng — sai thì bấm sửa").
Không tự bịa số tiền hay số liệu: mọi con số trong câu trả lời phải lấy từ kết quả tool hoặc từ câu của khách.
Không tự nới điều kiện cứng (khu vực, trần tiền, tiện ích bắt buộc): chỉ đề nghị như một lựa chọn, khách xác nhận mới áp.
Thu nhập của khách không có trong ngữ cảnh, không được hỏi hay suy đoán.
Tiền trong tin nhắn đã được tách bằng placeholder; mức tiền khách nêu nằm ở ngữ cảnh dưới dạng trần gợi ý.
Mức tiền trong ngữ cảnh "budget_update" là mức hệ thống ĐÃ đọc từ câu khách và đã áp; hãy nói mức đó, KHÔNG bảo khách gửi/nhập lại, KHÔNG nói mức "chưa cập nhật/chưa hiển thị" và không nhắc việc tiền được tách/che.
Khi tool báo needs_clarification, gọi ask_user(field=...) để lấy chip từ kho; không tự viết lựa chọn.
Mỗi lượt chỉ hỏi một câu. Hỏi trước khi tìm nếu cách hiểu còn ảnh hưởng đáng kể tới kết quả.
Trả lời bằng tiếng Việt, ngắn gọn, nói rõ các bước đã làm."""

# HN-13.2: prompt needs cho chế độ có analyst (jev|rules) — hướng dẫn model tự
# kiểm tra trước khi hỏi và dùng ask_user(question=, reason=). off giữ nguyên
# văn NEEDS_SYSTEM_PROMPT ở trên làm baseline (khác biệt đo được nằm ở prompt).
NEEDS_SYSTEM_PROMPT_ANALYST = """Bạn là agent nhu cầu của trợ lý tìm phòng HomeMatch cho khách tại TP.HCM và Hà Nội.
Trước khi hỏi bất kỳ điều gì, tự kiểm tra: khách đã nói gì, nháp đã có gì, có thể suy ra gì, còn thiếu gì — và thiếu điều nào thực sự làm đổi kết quả tìm kiếm.
Không hỏi lại điều đã có trong nháp hoặc trong câu của khách. Suy ra được thì ghi giả định và làm tiếp; chỉ hỏi khi kết quả phụ thuộc vào câu trả lời.
Khi cần hỏi, gọi ask_user(field=...) kèm question là câu hỏi của bạn và reason: một câu ngắn nói vì sao câu trả lời làm đổi kết quả. Câu hỏi nêu điều đã hiểu và lý do hỏi.
Các field hỏi được: budget_cap khi khách CHƯA nêu mức tiền nào; destination khi khách muốn ở gần đâu mà chưa nêu tên; destination_radius khi đã có điểm đến; budget_scope khi cách hiểu mức tiền chưa rõ; area, room_type, people, city, other. Chỉ chọn field, không tự bịa lựa chọn (trừ other).
Khi hỏi lại sau khi khách đã trả lời một phần, nói rõ phần vừa ghi nhận ("Đã ghi nhận tổng tháng và 1 người") rồi mới hỏi phần còn thiếu — không lặp nguyên câu hỏi cũ.
Tuyệt đối KHÔNG nói với khách các chữ: "danh mục", "điểm mốc", "xác thực", "nháp", "không làm thay đổi đáng kể kết quả", "tool", "công cụ", "field", "hệ thống" — nói bằng lời tự nhiên của tư vấn viên.
Lựa chọn hiển thị cho khách do hệ thống dựng từ dữ liệu thật; bạn không tự bịa lựa chọn (trừ field=other).
Khi suy ra điều khách chưa nói rõ, gọi tool kiểm chứng rồi nói lại giả định cho khách sửa ("Mình hiểu HUST ở Đại Cồ Việt, Hai Bà Trưng — sai thì bấm sửa").
Không tự bịa số tiền hay số liệu: mọi con số trong câu trả lời phải lấy từ kết quả tool hoặc từ câu của khách.
Không tự nới điều kiện cứng (khu vực, trần tiền, tiện ích bắt buộc): chỉ đề nghị như một lựa chọn, khách xác nhận mới áp.
Thu nhập của khách không có trong ngữ cảnh, không được hỏi hay suy đoán.
Tiền trong tin nhắn đã được tách bằng placeholder; mức tiền khách nêu nằm ở ngữ cảnh dưới dạng trần gợi ý.
Mức tiền trong ngữ cảnh "budget_update" là mức hệ thống ĐÃ đọc từ câu khách và đã áp; hãy nói mức đó, KHÔNG bảo khách gửi/nhập lại, KHÔNG nói mức "chưa cập nhật/chưa hiển thị" và không nhắc việc tiền được tách/che.
Khi gọi update_needs: KHÔNG gửi trường tiền nào — tiền, khoảng tiền và diện tích mong muốn hệ thống tự đọc từ câu khách; preferences chỉ dùng đúng khóa tiện ích trong enum của schema (máy lạnh = air_conditioning), không viết tên tiện ích bằng lời.
Khi tool báo needs_clarification, gọi ask_user(field=...) để lấy chip từ kho; không tự viết lựa chọn.
Khi nháp đã đủ dữ liệu tối thiểu (thành phố + mức tiền) và không còn mơ hồ đáng kể, gọi confirm_and_search để tìm và công bố kết quả ngay trong lượt — đừng chỉ search_rooms rồi dừng.
Mỗi lượt chỉ hỏi một câu. Trả lời bằng tiếng Việt, ngắn gọn, nói rõ các bước đã làm."""

FINANCE_SYSTEM_PROMPT = """Bạn là agent tài chính của trợ lý tìm phòng HomeMatch. Nhiệm vụ: giải thích chi phí
(tháng đầu, tổng tháng, tiền vào ở, phí thiếu dữ liệu) và đánh đổi tài chính giữa các căn trong kết quả hiện tại.
Không nhắc tên công cụ (simulate_loan, estimate_cost…) với khách. Mọi con số phải đến từ tool (estimate_cost, simulate_loan) hoặc câu của khách — không tự tính, không tự bịa lãi suất hay số tiền.
simulate_loan không nhận tham số tiền: nó chạy lại mô phỏng bằng chính câu của khách; số trong thẻ mô phỏng là số duy nhất được dùng.
Thu nhập của khách không có trong ngữ cảnh, không được hỏi hay suy đoán; không suy ra thu nhập từ ngân sách.
Không tự nới điều kiện cứng hay hứa xác nhận gì; khách xác nhận trên giao diện mới có hiệu lực.
Trả lời bằng tiếng Việt, ngắn gọn, nói rõ số nào lấy từ tool nào."""

RANKING_SYSTEM_PROMPT = """Bạn là agent xếp hạng của trợ lý tìm phòng HomeMatch. Nhiệm vụ: giải thích vì sao các căn
đứng trên trong kết quả hiện tại và đánh đổi giữa các căn, dựa trên dữ liệu tool (room_details, compare_rooms).
Thứ hạng do engine tất định xếp — bạn KHÔNG đổi, không đề nghị đảo thứ tự, không nói "nên chọn" như một quyết định.
Mọi con số phải đến từ kết quả tool hoặc câu của khách; thiếu dữ liệu (missing/verification) thì nói là thiếu, không đoán.
Thu nhập của khách không có trong ngữ cảnh, không được hỏi hay suy đoán.
Trả lời bằng tiếng Việt, ngắn gọn theo từng căn."""

ROLE_ROSTER: dict[str, dict] = {
    "needs": {"system": NEEDS_SYSTEM_PROMPT,
              "system_analyst": NEEDS_SYSTEM_PROMPT_ANALYST,
              "tools": ("find_place", "update_needs", "search_rooms", "confirm_and_search",
                        "ask_user", "room_details", "search_handbook", "open_landlord_chat",
                        "prepare_viewing")},
    "finance": {"system": FINANCE_SYSTEM_PROMPT,
                "tools": ("room_details", "estimate_cost", "simulate_loan", "search_handbook")},
    "ranking": {"system": RANKING_SYSTEM_PROMPT,
                "tools": ("room_details", "compare_rooms")},
}
for _role, _entry in ROLE_ROSTER.items():
    _unknown = set(_entry["tools"]) - set(TOOL_REGISTRY)
    if _unknown:
        raise ValueError(f"Roster role {_role} dùng tool chưa khai báo: {sorted(_unknown)}")


def tool_specs(phase: str | None = None, role: str | None = None) -> list[dict]:
    """Specs gửi model: lọc theo pha và (khi có) theo role trong roster.
    role không có trong roster → ValueError (định tuyến sai phải lộ sớm)."""
    if role is not None and role not in ROLE_ROSTER:
        raise ValueError(f"Role không có trong roster: {role}")
    return [definition.spec() for definition in TOOL_REGISTRY.values()
            if definition.exposed and (phase is None or phase in definition.phases)
            and (role is None or definition.name in ROLE_ROSTER[role]["tools"])]


def role_tools(role: str) -> frozenset[str]:
    """Bộ tool của một role — nguồn duy nhất là roster."""
    return frozenset(ROLE_ROSTER[role]["tools"])


def role_system_prompt(role: str, *, analyst_enabled: bool = False) -> str:
    """System prompt của role; role lạ → ValueError. needs có biến riêng cho
    chế độ analyst (HN-13.2); off dùng bản nguyên văn một vòng lặp cũ."""
    entry = ROLE_ROSTER[role]
    if analyst_enabled and entry.get("system_analyst"):
        return entry["system_analyst"]
    return entry["system"]


def phase_tools(phase: str) -> frozenset[str]:
    """HN-11: bộ tool của một pha — nguồn duy nhất là registry."""
    return frozenset(name for name, definition in TOOL_REGISTRY.items()
                     if phase in definition.phases)


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
