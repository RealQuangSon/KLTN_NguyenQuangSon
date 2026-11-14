"""Intent Literal sync between the public MessageResult and the interpreter schema.

Extraction is the structured output schema of OpenAIInterpreter; if a MessageResult
intent value is missing there, openai mode can never return it. get_args keeps the
test catching future drift on both sides automatically.
"""
from types import SimpleNamespace
from typing import get_args

import pytest

from backend.app.interpreter import DemoInterpreter, OpenAIInterpreter, SYSTEM_PROMPT
from backend.app.models import Extraction
from backend.app.schemas import MessageResult

MESSAGE_INTENTS = get_args(MessageResult.model_fields["intent"].annotation)

# Required nullable fields mirror Extraction; only intent varies across cases.
BASE_EXTRACTION = {"city": None, "area": None, "people": None,
                   "preferences": [], "needs_destination": False}


def test_message_result_has_intents_to_sync():
    # Guards against the Literal silently disappearing (get_args returning ()).
    assert set(MESSAGE_INTENTS) >= {"find_room", "calculate_cost", "human_support", "handbook", "unknown"}


def test_every_message_intent_is_accepted_by_extraction_schema():
    for intent in MESSAGE_INTENTS:
        extraction = Extraction.model_validate({"intent": intent, **BASE_EXTRACTION})
        assert extraction.intent == intent


def test_system_prompt_describes_every_message_intent():
    for intent in MESSAGE_INTENTS:
        assert intent in SYSTEM_PROMPT


def test_demo_interpreter_maps_house_rules_to_handbook():
    assert DemoInterpreter().extract("Nội quy cho thuê ở đây thế nào?").intent == "handbook"


def test_openai_interpreter_accepts_handbook_without_live_call():
    captured = {}

    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(status="completed", output_parsed={"intent": "handbook", **BASE_EXTRACTION},
                               usage=SimpleNamespace(total_tokens=12))

    adapter = OpenAIInterpreter(client=SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    result = adapter.extract("Nội quy về hoàn cọc là gì?")
    assert result.intent == "handbook"
    assert captured["store"] is False
    assert captured["text_format"] is Extraction


# --- LF-04: the ten new amenity keys are understood with and without accents ---

NEW_AMENITY_PREFERENCES = [
    ("kitchen", "cần có bếp để nấu ăn", "can bep khong"),
    ("wifi", "phòng cần wifi mạnh", "phong can wifi manh"),
    ("elevator", "nhà phải có thang máy", "nha phai co thang may"),
    ("security_24h", "cần khu có an ninh 24/24", "can khu co bao ve 24/24"),
    ("camera", "muốn có camera cho an toàn", "muon co camera cho an toan"),
    ("loft", "thích phòng có gác lửng", "thich phong co gac lung"),
    ("flexible_hours", "cần giờ giấc tự do", "can gio giac tu do"),
    ("no_shared_landlord", "tìm phòng không chung chủ", "tim phong ko chung chu"),
    ("water_heater", "cần có nóng lạnh", "can co nong lanh"),
    ("fridge", "phòng nên có tủ lạnh", "phong nen co tu lanh"),
]


@pytest.mark.parametrize("key, accented, plain", NEW_AMENITY_PREFERENCES)
def test_new_amenity_preferences_extracted_with_and_without_accents(key, accented, plain):
    assert DemoInterpreter().extract(accented).preferences == [key]
    assert DemoInterpreter().extract(plain).preferences == [key]


def test_new_amenity_preferences_removed_by_rejection_phrase():
    extraction = DemoInterpreter().extract("bỏ nhà bếp không cần bếp nữa, thích yên tĩnh")
    assert "kitchen" in extraction.remove_preferences
    assert "kitchen" not in extraction.preferences


def test_openai_prompt_lists_every_amenity_key():
    from backend.app.interpreter import SYSTEM_PROMPT
    from backend.app.models import AMENITY_KEYS
    for key in AMENITY_KEYS:
        assert key in SYSTEM_PROMPT


# AG-02: trích tiền tất định phải hiểu các kiểu viết phổ biến của người thuê
# (đo 06/11 trên 10 câu khó: "3 triệu5", "5 triệu rưỡi", "4 củ" bị mất hoặc đọc thiếu).
def test_budget_hint_reads_tail_decimal_and_half():
    from backend.app.interpreter import budget_hint
    # "3 triệu5" / "3tr5" dính liền đơn vị = 3,5 triệu.
    assert budget_hint("phòng trọ 3 triệu5 gần HUST") == 3_500_000
    assert budget_hint("tìm studio 3tr5 quận 7") == 3_500_000
    # "5 triệu rưỡi" = 5,5 triệu.
    assert budget_hint("tầm 5 triệu rưỡi có thang máy") == 5_500_000
    # Slang triệu: "4 củ", "5 cây".
    assert budget_hint("dưới 4 củ gần bến xe") == 4_000_000
    assert budget_hint("5 cây một tháng") == 5_000_000
    # Có khoảng trắng thì đuôi số KHÔNG phải phần lẻ: "3 triệu 2 người" là 3 triệu.
    assert budget_hint("phòng 3 triệu 2 người ở") == 3_000_000
    # Các dạng cũ không đổi.
    assert budget_hint("tầm 3,5 triệu") == 3_500_000
    assert budget_hint("800k một tháng") is None or budget_hint("800k một tháng") == 800_000
    assert budget_hint("không nói tiền") is None
