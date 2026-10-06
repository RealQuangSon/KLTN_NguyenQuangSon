import json

import pytest
from fastapi.testclient import TestClient

from backend.app.catalog import Catalog
from backend.app.copilot import marketing_post, price_advice
from backend.app.main import create_app
from backend.app.models import Actor, DomainError

OWNER = Actor(id="owner-a", role="owner")


def test_marketing_posts_use_only_listing_facts_per_channel(service):
    rooms = service.catalog.rooms()
    room = next(room for room in rooms if room.id == "demo-01")
    posts = {channel: marketing_post(rooms, room, channel, "https://x/tin/demo-01")
             for channel in ("facebook", "zalo", "forum")}
    assert "#" in posts["facebook"]["text"] and "🏠" in posts["facebook"]["text"]
    assert len(posts["zalo"]["text"]) < len(posts["forum"]["text"])
    assert posts["facebook"]["share_url"].startswith("https://www.facebook.com/sharer/")
    unknown = [name for name, value in room.amenities.items() if value is not True]
    for post in posts.values():
        assert "https://x/tin/demo-01" in post["text"] and "không tự đăng" in post["notice"]
        assert "2,5 triệu" in post["text"]
    assert "máy lạnh" not in posts["forum"]["text"] or room.amenities.get("air_conditioning") is True
    assert unknown  # demo-01 has amenities that are false/unknown and are not advertised


def test_price_advice_uses_comparables_and_refuses_thin_samples():
    rooms = Catalog("data/catalog/rooms.json").rooms()
    room = next(room for room in rooms if room.city == "TP.HCM" and room.room_type == "room")
    advice = price_advice(rooms, room)
    assert advice["sample"] >= 3 and advice["suggested_min"] <= advice["median"] <= advice["suggested_max"]
    lonely = next(room for room in rooms if room.room_type == "apartment" and room.bedrooms == 2)
    lonely = lonely.model_copy(update={"area_m2": 500})
    assert price_advice(rooms, lonely)["suggested_min"] is None


def test_assistant_routes_questions_and_stays_within_own_rooms(service):
    vacancy = service.landlord_assistant(OWNER, "Vì sao phòng trống lâu vậy?")
    assert vacancy["intent"] == "vacancy" and vacancy["data"]
    assert all(item["reasons"] for item in vacancy["data"])
    price = service.landlord_assistant(OWNER, "Phòng demo-01 nên cho thuê giá bao nhiêu?")
    assert price["intent"] == "price_advice" and price["data"][0]["room_id"] == "demo-01"
    assert service.landlord_assistant(OWNER, "Doanh thu tháng này?")["intent"] == "finance"
    assert service.landlord_assistant(OWNER, "Tỷ lệ lấp đầy?")["intent"] == "occupancy"
    assert service.landlord_assistant(OWNER, "xin chào")["intent"] == "help"
    with pytest.raises(DomainError):
        service.marketing_post(Actor(id="owner-b", role="owner"), "demo-01", "facebook")
    with pytest.raises(DomainError):
        service.landlord_assistant(Actor(id="renter-a", role="renter"), "giá?")


def test_copilot_routes(service):
    with TestClient(create_app(lambda: service)) as client:
        owner = {"Authorization": "Bearer demo-owner-a"}
        post = client.post("/landlord/rooms/demo-01/marketing", headers=owner, json={"channel": "zalo"})
        assert post.status_code == 200 and post.json()["channel"] == "zalo"
        assert client.post("/landlord/rooms/demo-01/marketing", headers=owner,
                           json={"channel": "tiktok"}).status_code == 422
        answer = client.post("/landlord/assistant", headers=owner, json={"question": "phòng trống vì sao?"})
        assert answer.json()["intent"] == "vacancy"
