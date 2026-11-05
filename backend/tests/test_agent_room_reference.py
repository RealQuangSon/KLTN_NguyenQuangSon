"""AG-05: agent tham chiếu được căn trong kết quả — id Chợ Tốt/synthetic/demo,
thứ tự danh sách, tiêu đề rút gọn; chỉ id nằm trong visible_items."""
from backend.app.agent_guard import mention_room_id, resolve_room_reference

VISIBLE = [
    {"room_id": "chotot-101", "title": "Phòng Q7. Gần chợ"},
    {"room_id": "chotot-102", "title": "Studio Bình Thạnh. Có cửa sổ"},
    {"room_id": "synthetic-room-003", "title": "Phòng Hà Đông. Yên tĩnh"},
    {"room_id": "demo-04", "title": "Căn hộ Cầu Giấy. 2PN"},
    {"room_id": "room-abc123def0", "title": "Phòng Thủ Đức. Giờ giấc tự do"},
]


def test_ids_of_every_source_including_chotot():
    assert resolve_room_reference("đặt lịch chotot-102", VISIBLE) == "chotot-102"
    assert resolve_room_reference("synthetic-room-003 có giữ xe không", VISIBLE) == "synthetic-room-003"
    assert resolve_room_reference("demo-04 rộng lắm hả", VISIBLE) == "demo-04"
    assert resolve_room_reference("room-abc123def0 giờ giấc sao", VISIBLE) == "room-abc123def0"


def test_ordinals_map_to_list_order():
    assert resolve_room_reference("đặt lịch căn số 2", VISIBLE) == "chotot-102"
    assert resolve_room_reference("căn thứ hai có wc riêng không", VISIBLE) == "chotot-102"
    assert resolve_room_reference("nội quy căn đầu tiên", VISIBLE) == "chotot-101"
    assert resolve_room_reference("nếu vay 12 tháng cho căn cuối", VISIBLE) == "room-abc123def0"
    # Ngoài phạm vi danh sách (căn số 6) → None, không wrap về đầu.
    assert resolve_room_reference("căn số 6", VISIBLE) is None


def test_unique_short_title_match():
    assert resolve_room_reference("phòng Q7. Gần chợ có giặt máy không", VISIBLE) == "chotot-101"
    # Tiêu đề mơ hồ/được nhắc chung chung → None.
    assert resolve_room_reference("phòng ở đâu cũng được", VISIBLE) is None


def test_ids_outside_the_visible_list_never_resolve():
    assert resolve_room_reference("chotot-999 có còn không", VISIBLE) is None
    assert resolve_room_reference("demo-99 ra sao", []) is None


def test_sentences_without_a_room_reference_return_none():
    assert resolve_room_reference("cho mình hỏi nội quy chung", VISIBLE) is None
    assert resolve_room_reference("khu này có ngập không", VISIBLE) is None


def test_mention_room_id_distinguishes_named_but_hidden():
    assert mention_room_id("chotot-999 có còn không") == "chotot-999"
    assert mention_room_id("cho mình hỏi nội quy chung") is None
