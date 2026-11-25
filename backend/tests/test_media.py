"""BE-06: listing and maintenance photo media (hm_media + HOMEMATCH_MEDIA_DIR).

Type is decided by magic bytes, never the client content type; uploads over
5 MB or past the per-owner limit are rejected; files are content-addressed on
disk and only unlinked when the last ledger reference disappears. Visibility
follows the listing/ticket: public listing photos need no token, hidden
listing photos stay landlord-only, maintenance photos stay between the two
parties; anyone else gets the same 404 as a missing file.
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import pms
from backend.app.main import create_app
from backend.app.models import Actor

OWNER_2 = {"Authorization": "Bearer demo-owner2"}
# Người ngoài cuộc (không phải chủ tin/khách thuê trong ticket): mọi đường
# media đều trả 404 như file không tồn tại.
OWNER_B = {"Authorization": "Bearer demo-owner1"}
RENTER = {"Authorization": "Bearer demo-renter"}
RENTER_B = {"Authorization": "Bearer demo-owner1"}

# Tiny hard-coded 1x1 PNG: only the magic signature is ever parsed.
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
       b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00"
       b"\x00IEND\xaeB`\x82")
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 8


@pytest.fixture(autouse=True)
def media_dir(tmp_path, monkeypatch):
    target = tmp_path / "media"
    monkeypatch.setenv("HOMEMATCH_MEDIA_DIR", str(target))
    return target


@pytest.fixture
def client(service):
    with TestClient(create_app(lambda: service)) as test_client:
        yield test_client


def upload(client, room_id="demo-01", data=PNG, headers=OWNER_2, name="photo.png"):
    return client.post(f"/landlord/rooms/{room_id}/media", headers=headers,
                       files={"file": (name, data, "image/png")})


def upload_png(client, room_id="demo-01", index=0, headers=OWNER_2):
    return upload(client, room_id=room_id, data=PNG + bytes([index]), headers=headers)


def disk_path(media_dir, media_id, service):
    from backend.app.media import file_path
    return file_path(service.repo.db.execute("SELECT * FROM hm_media WHERE id=?", (media_id,)).fetchone())


def active_lease(service, renter_id="renter", room_id="demo-01"):
    owner = Actor(id="owner2", role="owner")
    start = date.today() - timedelta(days=30)
    lease = service.create_lease(owner, pms.LeaseInput(
        renter_id=renter_id, room_id=room_id, start_date=start,
        end_date=start + timedelta(days=180), occupants=1, vehicles=1))
    service.send_lease(owner, lease["id"])
    service.accept_lease(Actor(id=renter_id, role="renter"), lease["id"], lease["version"])
    service.activate_lease(owner, lease["id"])
    return lease


def test_upload_stores_file_and_metadata(client, service, media_dir):
    response = upload(client)
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["url"] == f"/media/{record['id']}"
    assert record["content_type"] == "image/png" and record["size_bytes"] == len(PNG)
    assert record["position"] == 0
    path = disk_path(media_dir, record["id"], service)
    assert path.exists() and path.read_bytes() == PNG
    # The filename never reaches disk: the path is content-addressed.
    assert record["id"].split("/")[-1] not in str(path)


def test_text_content_with_jpg_name_is_rejected(client):
    response = upload(client, data=b"khong phai anh", name="photo.jpg")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_media"


def test_oversized_upload_is_rejected(client):
    data = PNG + b"\x00" * (5 * 1024 * 1024 - len(PNG) + 1)
    response = upload(client, data=data)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "media_too_large"


def test_eleventh_photo_is_rejected(client):
    first = upload_png(client, index=0)
    assert first.status_code == 201
    for index in range(1, 10):
        assert upload_png(client, index=index).status_code == 201
    response = upload_png(client, index=10)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "media_limit"


def test_other_landlord_cannot_upload_delete_or_reorder(client):
    uploaded = upload(client)
    assert uploaded.status_code == 201
    media_id = uploaded.json()["id"]
    assert upload(client, headers=OWNER_B).status_code == 404
    assert upload(client, room_id="demo-09", headers=OWNER_B).status_code == 404
    delete = client.delete(f"/landlord/rooms/demo-01/media/{media_id}", headers=OWNER_B)
    assert delete.status_code == 404
    order = client.patch("/landlord/rooms/demo-01/media/order", headers=OWNER_B,
                         json={"media_ids": [media_id]})
    assert order.status_code == 404
    # A foreign media id is rejected even for the rightful room.
    wrong = client.patch("/landlord/rooms/demo-01/media/order", headers=OWNER_2,
                         json={"media_ids": ["no-such-media"]})
    assert wrong.status_code == 422


def test_hidden_listing_photo_needs_landlord(client):
    uploaded = upload(client, room_id="demo-09")  # demo-09 is not published
    assert uploaded.status_code == 201
    url = uploaded.json()["url"]
    assert client.get(url).status_code == 404
    assert client.get(url, headers=RENTER).status_code == 404
    ok = client.get(url, headers=OWNER_2)
    assert ok.status_code == 200 and ok.headers["cache-control"] == "private, max-age=300"


def test_public_listing_photo_is_anonymous_with_public_cache(client):
    uploaded = upload(client, room_id="demo-01")  # demo-01 is published
    assert uploaded.status_code == 201
    ok = client.get(uploaded.json()["url"])
    assert ok.status_code == 200
    assert ok.content == PNG and ok.headers["content-type"].startswith("image/png")
    assert ok.headers["cache-control"] == "public, max-age=300"


def test_maintenance_photos_stay_between_the_two_parties(client, service):
    active_lease(service)
    ticket = client.post("/maintenance", headers=RENTER, json={
        "room_id": "demo-01", "title": "Hỏng vòi nước", "description": "Vòi rò nước liên tục",
        "priority": "normal"}).json()
    assert client.post(f"/maintenance/{ticket['id']}/media", headers=RENTER_B,
                       files={"file": ("x.png", PNG, "image/png")}).status_code == 404
    uploaded = client.post(f"/maintenance/{ticket['id']}/media", headers=RENTER,
                           files={"file": ("x.png", PNG, "image/png")})
    assert uploaded.status_code == 201, uploaded.text
    url = uploaded.json()["url"]
    assert client.get(url, headers=RENTER_B).status_code == 404
    assert client.get(url, headers=OWNER_B).status_code == 404
    assert client.get(url).status_code == 404  # no token at all
    assert client.get(url, headers=RENTER).status_code == 200
    ok = client.get(url, headers=OWNER_2)
    assert ok.status_code == 200 and ok.headers["cache-control"] == "private, max-age=300"
    # The ticket DTO carries its photos.
    listed = client.get("/maintenance", headers=RENTER).json()
    assert next(item for item in listed if item["id"] == ticket["id"])["photos"] == [
        {"id": uploaded.json()["id"], "url": url}]


def test_duplicate_upload_returns_the_same_record(client, service, media_dir):
    first = upload(client)
    second = upload(client)
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    rows = service.repo.db.execute("SELECT COUNT(*) AS n FROM hm_media").fetchone()["n"]
    assert rows == 1
    assert len(list(media_dir.glob("*/*.png"))) == 1


def test_delete_removes_file_only_when_unused(client, service, media_dir):
    from backend.app.media import file_path
    first = upload(client).json()
    # The same content indexed for a second room keeps the file alive.
    second = upload(client, room_id="demo-02").json()
    path = file_path(service.repo.db.execute("SELECT * FROM hm_media WHERE id=?", (first["id"],)).fetchone())
    assert path.exists()
    assert client.delete(f"/landlord/rooms/demo-01/media/{first['id']}", headers=OWNER_2).status_code == 204
    assert path.exists() and client.get(first["url"], headers=OWNER_2).status_code == 404
    assert client.delete(f"/landlord/rooms/demo-02/media/{second['id']}", headers=OWNER_2).status_code == 204
    assert not path.exists()


def test_reorder_changes_photo_order_everywhere(client):
    ids = [upload_png(client, index=i).json()["id"] for i in range(3)]
    reversed_ids = list(reversed(ids))
    ordered = client.patch("/landlord/rooms/demo-01/media/order", headers=OWNER_2,
                           json={"media_ids": reversed_ids})
    assert ordered.status_code == 200, ordered.text
    assert [item["id"] for item in ordered.json()] == reversed_ids
    assert [item["position"] for item in ordered.json()] == [0, 1, 2]
    room = client.get("/landlord/rooms/demo-01", headers=OWNER_2).json()["room"]
    assert [photo["id"] for photo in room["photos"]] == reversed_ids
    detail = client.get("/listings/demo-01").json()
    assert [photo["id"] for photo in detail["photos"]] == reversed_ids
    assert all(photo["url"] == f"/media/{photo['id']}" for photo in detail["photos"])


def test_photos_are_in_listing_search_and_detail(client):
    upload(client, room_id="demo-01")
    detail = client.get("/listings/demo-01").json()
    assert len(detail["photos"]) == 1 and detail["photos"][0]["url"].startswith("/media/")
    search = client.get("/listings", params={"city": "TP.HCM", "area": "Quận 7"}).json()
    target = next(item for item in search["items"] if item["id"] == "demo-01")
    assert len(target["photos"]) == 1
