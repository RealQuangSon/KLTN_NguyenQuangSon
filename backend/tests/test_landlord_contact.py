"""Landlord contact phone (schema v14) and the listing `contact` block.

The phone is entered by the landlord on their own profile, never crawled. It is
shown on their listings to signed-in users only; crawled listings point to the
original post instead, because their landlord_id is a demo account. Since
CA-04/C1b (crawler 2.4) the crawled poster's display name (`poster_name`) also
lives only in this contact block for signed-in users; anonymous visitors get
null and no other surface carries it.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app

OWNER_2 = {"Authorization": "Bearer demo-owner2"}
RENTER = {"Authorization": "Bearer demo-renter"}


@pytest.fixture
def client(service):
    with TestClient(create_app(lambda: service)) as test_client:
        yield test_client


def owner_a_room(service):
    return next(room for room in service.catalog.rooms() if room.published and room.landlord == "owner2")


def test_owner_sets_normalized_phone_and_clears_it(client):
    saved = client.patch("/me/profile", headers=OWNER_2, json={"contact_phone": "+84 901 234 567"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["contact_phone"] == "0901234567"
    assert client.get("/me/profile", headers=OWNER_2).json()["contact_phone"] == "0901234567"
    cleared = client.patch("/me/profile", headers=OWNER_2, json={"contact_phone": ""})
    assert cleared.json()["contact_phone"] is None


@pytest.mark.parametrize("value", ["12345", "0901-234-56", "abc0901234567"])
def test_invalid_phone_is_rejected(client, value):
    response = client.patch("/me/profile", headers=OWNER_2, json={"contact_phone": value})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_phone"


def test_renter_cannot_set_contact_phone(client):
    response = client.patch("/me/profile", headers=RENTER, json={"contact_phone": "0901234567"})
    assert response.status_code == 422


def test_phone_shown_to_signed_in_users_only(client, service):
    room = owner_a_room(service)
    client.patch("/me/profile", headers=OWNER_2, json={"contact_phone": "0901234567"})
    signed_in = client.get(f"/listings/{room.id}", headers=RENTER).json()["contact"]
    assert signed_in == {"kind": "landlord", "original_url": None, "phone": "0901234567",
                         "phone_requires_login": False, "poster_name": None}
    anonymous = client.get(f"/listings/{room.id}").json()["contact"]
    assert anonymous["phone"] is None and anonymous["phone_requires_login"] is True
    assert anonymous["poster_name"] is None


def test_no_phone_means_nothing_to_reveal(client, service):
    room = owner_a_room(service)
    contact = client.get(f"/listings/{room.id}").json()["contact"]
    assert contact["phone"] is None and contact["phone_requires_login"] is False


@pytest.mark.parametrize("source, url", [
    ("https://www.chotot.com/87761600.htm", "https://www.chotot.com/87761600.htm"),
    ("chotot://ad/123", None),
])
def test_crawled_listing_links_original_and_hides_demo_phone(client, service, renter, source, url):
    client.patch("/me/profile", headers=OWNER_2, json={"contact_phone": "0901234567"})
    crawled = owner_a_room(service).model_copy(update={"source": source})
    assert service._listing_contact(crawled, renter) == {
        "kind": "external", "original_url": url, "phone": None, "phone_requires_login": False,
        "poster_name": None}
    # CA-04/C1b: a real poster name reaches signed-in renters through contact only.
    named = crawled.model_copy(update={"poster_name": "Người đăng mẫu"})
    assert service._listing_contact(named, renter)["poster_name"] == "Người đăng mẫu"
    assert service._listing_contact(named, None)["poster_name"] is None
