"""Luồng thuê phòng end-to-end qua API thật (TestClient, offline).

Ba nhánh:
- **Chủ nhà**: chat → xác nhận hồ sơ → kết quả → chi tiết có kiểm chứng → đặt
  lịch (contact + consent) → đề xuất giờ khác → khách đồng ý → hoàn tất →
  phản hồi → hợp đồng từ lịch → gửi → chấp nhận → kích hoạt → số điện nước →
  hóa đơn → báo đã chuyển → xác nhận → phiếu thu.
- **Tin cào**: tin source Chợ Tốt → hàng đợi điều phối admin, owner2 không
  thấy gì → xác nhận → hoàn tất → phản hồi; xem SĐT có audit.
- **Lỗi**: phòng hết trong lúc chờ → stale_viewing; sai chuyển trạng thái →
  viewing_conflict; thiếu consent/contact → 422; lịch cũ hết hiệu lực khi hồ
  sơ đổi.

Không gọi mạng, không provider trả phí (conftest đặt demo).
"""
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.models import Quote, Room, Scenario

TOMORROW_8AM = (datetime.now(timezone.utc) + timedelta(days=2)).strftime(
    "%Y-%m-%dT08:00:00+07:00"
)


from contextlib import contextmanager


@contextmanager
def _client(service):
    """TestClient phải chạy lifespan (with) để app.state.auth_mode sẵn sàng."""
    with TestClient(create_app(lambda: service)) as client:
        yield client


# conftest đặt AUTH_MODE=demo: token bearer tĩnh per-user, không login mật khẩu.
def _login(client, user):
    response = client.get("/auth/me", headers={"Authorization": f"Bearer demo-{user}"})
    assert response.status_code == 200, response.text
    assert response.json()["id"] == user
    return f"demo-{user}"


def _crawled_room(room_id="chotot-e2e-1") -> Room:
    fees = [
        {"name": "electricity", "amount_vnd": 3500, "mode": "kwh",
         "included_in_rent": False, "source": "chotot://ad/9/body#electricity"},
        {"name": "water", "amount_vnd": 10000, "mode": "m3",
         "included_in_rent": False, "source": "chotot://ad/9/body#water"},
        {"name": "internet", "amount_vnd": 50000, "mode": "fixed",
         "included_in_rent": False, "source": "chotot://ad/9/body#internet"},
        {"name": "parking", "amount_vnd": 0, "mode": "fixed",
         "included_in_rent": True, "source": "chotot://ad/9/body#parking"},
        {"name": "service", "amount_vnd": 50000, "mode": "fixed",
         "included_in_rent": False, "source": "chotot://ad/9/body#service"},
    ]
    return Room.model_validate({
        "id": room_id, "revision": 1,
        "title": "Phòng trọ e2e Quận 7. Đang trống",
        "city": "TP.HCM", "area": "Quận 7", "room_type": "room",
        "bedrooms": None, "capacity": 2, "area_m2": 20.0,
        "published": True, "available": True, "amenities": {"kitchen": True},
        "latitude": None, "longitude": None, "location_accuracy": "area_only",
        "uncertainty_m": None,
        "quote": {"rent_vnd": 900_000, "deposit_vnd": 900_000, "fees": fees},
        "source": "https://www.chotot.com/999.htm", "synthetic": False,
        "poster_kind": "individual",
        "source_images": ["https://cdn.chotot.com/e2e/1.jpg"],
    })


def _book(client, token, room_id, key_suffix=""):
    return client.post(
        f"/listings/{room_id}/viewings",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "requested_at": TOMORROW_8AM,
            "idempotency_key": f"e2e-{room_id}-{key_suffix or uuid4().hex[:8]}",
            "mode": "offline",
            "contact_name": "Nguyễn Văn A",
            "contact_phone": "0901234567",
            "contact_consent": True,
            "time_slot": "morning",
            "note": "Gặp trước cổng.",
        },
    )


# --- Nhánh chủ nhà -------------------------------------------------------------


def test_landlord_branch_full_flow(service):
        with _client(service) as client:
                renter = _login(client, "renter")
                owner = _login(client, "owner2")

                session = client.post("/sessions", headers={"Authorization": f"Bearer {renter}"})
                assert session.status_code == 201
                sid = session.json()["session_id"]
                message = client.post(
                f"/sessions/{sid}/messages",
                headers={"Authorization": f"Bearer {renter}"},
                json={"text": "Tìm phòng TP.HCM Quận 7 cho 1 người tầm 3 triệu"},
                )
                draft_revision = message.json()["draft_revision"]
                profile = {"city": "TP.HCM", "area": "Quận 7", "room_type": "room",
                       "max_monthly_cost_vnd": 4_000_000,
                       "scenario": {"people": 1}, "accept_estimated_data": True}
                confirmed = client.post(
                f"/sessions/{sid}/confirm",
                headers={"Authorization": f"Bearer {renter}"},
                json={"profile": profile, "expected_draft_revision": draft_revision},
                )
                assert confirmed.status_code == 200, confirmed.text
                results = confirmed.json()["results"]
                assert results, "catalog must yield rooms for the profile"
                first = results[0]
                assert first["source_images"] is not None

                # Chi tiết có kiểm chứng + giá mỗi m² + chỗ ở tương tự (E-04/E-06).
                detail = client.get(
                f"/listings/{first['room_id']}",
                headers={"Authorization": f"Bearer {renter}"},
                ).json()
                assert set(detail["trust"]) >= {"completeness", "price_vs_area", "freshness",
                                            "ownership", "reports"}
                assert detail["trust"]["notice"]
                assert detail["trust"]["ownership"]["status"] == "unknown"

                # Đặt lịch thiếu consent → 422; thiếu contact → 422 (E-01/R3).
                base = {"requested_at": TOMORROW_8AM,
                    "idempotency_key": f"e2e-neg-{uuid4().hex[:8]}", "mode": "offline"}
                no_consent = client.post(
                f"/listings/{first['room_id']}/viewings",
                headers={"Authorization": f"Bearer {renter}"},
                json={**base, "contact_name": "A", "contact_phone": "0901234567"},
                )
                assert no_consent.status_code == 422
                no_contact = client.post(
                f"/listings/{first['room_id']}/viewings",
                headers={"Authorization": f"Bearer {renter}"},
                json={**base, "contact_consent": True},
                )
                assert no_contact.status_code == 422

                # Đặt lịch đúng: created, liên hệ đã chia sẻ với người thuê.
                booked = _book(client, renter, first["room_id"], key_suffix="main")
                assert booked.status_code == 201, booked.text
                viewing = booked.json()
                assert viewing["status"] == "requested"
                assert viewing["handler"] == "landlord"
                assert viewing["contact_shared"] and viewing["contact_phone"] == "0901234567"
                # Idempotency: cùng key → cùng lịch.
                repeat = _book(client, renter, first["room_id"], key_suffix="main")
                assert repeat.status_code == 201 and repeat.json()["id"] == viewing["id"]

                # Trước xác nhận: chủ nhà KHÔNG thấy SĐT (R3/E-01.7).
                before = client.get(
                f"/viewings/{viewing['id']}",
                headers={"Authorization": f"Bearer {owner}"},
                ).json()
                assert before["contact_phone"] is None and before["contact_shared"] is False

                # Chủ nhà đề xuất giờ khác → khách đồng ý (stale check vẫn chạy).
                proposed = client.post(
                f"/viewings/{viewing['id']}/actions",
                headers={"Authorization": f"Bearer {owner}"},
                json={"action": "propose",
                      "proposed_at": (datetime.now(timezone.utc) + timedelta(days=3))
                      .isoformat()},
                )
                assert proposed.status_code == 200, proposed.text
                assert proposed.json()["status"] == "reschedule_proposed"
                accepted = client.post(
                f"/viewings/{viewing['id']}/actions",
                headers={"Authorization": f"Bearer {renter}"},
                json={"action": "accept"},
                )
                assert accepted.status_code == 200, accepted.text
                assert accepted.json()["status"] == "confirmed"
                # Sau xác nhận: chủ nhà thấy liên hệ (E-01.7).
                after = client.get(
                f"/viewings/{viewing['id']}",
                headers={"Authorization": f"Bearer {owner}"},
                ).json()
                assert after["contact_phone"] == "0901234567"

                # Hoàn tất → phản hồi 1–5 (chỉ completed mới gửi được).
                completed = client.post(
                f"/viewings/{viewing['id']}/actions",
                headers={"Authorization": f"Bearer {owner}"},
                json={"action": "complete"},
                )
                assert completed.status_code == 200
                early = client.post(
                f"/viewings/{first['room_id']}/feedback",
                headers={"Authorization": f"Bearer {renter}"}, json={"rating": 5},
                )
                assert early.status_code in (404, 409)  # phòng khác chưa completed
                feedback = client.post(
                f"/viewings/{viewing['id']}/feedback",
                headers={"Authorization": f"Bearer {renter}"},
                json={"rating": 5, "note": "Phòng ổn, nhận nhà."},
                )
                assert feedback.status_code == 200, feedback.text
                assert feedback.json()["feedback_rating"] == 5

                # Hợp đồng từ lịch (E-08): renter_id lấy từ lịch, không gõ mã tài khoản.
                from datetime import date
                # Giao diện không gửi renter_id: máy chủ lấy khách của lịch xem.
                lease_body = {
                "room_id": first["room_id"],
                "viewing_id": viewing["id"],
                "start_date": (date.today() + timedelta(days=1)).isoformat(),
                "end_date": (date.today() + timedelta(days=181)).isoformat(),
                }
                # Sai người thuê → 422 (renter phải là khách của lịch).
                wrong = dict(lease_body, renter_id="renter-b")
                created_wrong = client.post(
                "/landlord/leases",
                headers={"Authorization": f"Bearer {owner}"}, json=wrong,
                )
                assert created_wrong.status_code in (403, 404, 422)
                # Không có người thuê và không có lịch xem → 422, không tạo hợp đồng mồ côi.
                no_renter = {k: v for k, v in lease_body.items() if k != "viewing_id"}
                assert client.post(
                "/landlord/leases",
                headers={"Authorization": f"Bearer {owner}"}, json=no_renter,
                ).status_code == 422
                created = client.post(
                "/landlord/leases",
                headers={"Authorization": f"Bearer {owner}"}, json=lease_body,
                )
                assert created.status_code in (200, 201), created.text
                lease = created.json().get("lease", created.json())
                lease_id = lease["id"]
                sent = client.post(
                f"/landlord/leases/{lease_id}/send",
                headers={"Authorization": f"Bearer {owner}"},
                )
                assert sent.status_code in (200, 201), sent.text
                lease_version = (sent.json().get("lease") or sent.json()).get("version") or 2
                accepted_lease = client.post(
                f"/leases/{lease_id}/accept",
                headers={"Authorization": f"Bearer {renter}"},
                json={"expected_version": lease_version},
                )
                assert accepted_lease.status_code in (200, 201), accepted_lease.text
                activated = client.post(
                f"/landlord/leases/{lease_id}/activate",
                headers={"Authorization": f"Bearer {owner}"},
                )
                assert activated.status_code in (200, 201), activated.text
                # Lịch xem giờ trỏ hợp đồng; hợp đồng đã kích hoạt không còn draft → hiện link.
                viewing_after = client.get(
                f"/viewings/{viewing['id']}",
                headers={"Authorization": f"Bearer {renter}"},
                ).json()
                assert viewing_after["lease_id"] == lease_id
                assert viewing_after["lease_visible"] is True

                # Số điện nước → hóa đơn → khách báo đã chuyển → chủ nhà xác nhận → phiếu thu.
                from datetime import date as _date
                period = _date.today().strftime("%Y-%m")
                reading = client.post(
                f"/landlord/leases/{lease_id}/readings",
                headers={"Authorization": f"Bearer {owner}"},
                json={"period": period, "electricity_start": 0, "electricity_end": 120,
                      "water_start": 0, "water_end": 4},
                )
                assert reading.status_code in (200, 201), reading.text
                invoice = client.post(
                f"/landlord/leases/{lease_id}/invoices",
                headers={"Authorization": f"Bearer {owner}"},
                json={"period": period},
                )
                assert invoice.status_code in (200, 201), invoice.text
                invoice_id = (invoice.json().get("invoice") or invoice.json())["id"]
                claim = client.post(
                f"/invoices/{invoice_id}/claims",
                headers={"Authorization": f"Bearer {renter}"},
                json={"amount_vnd": 1, "reference": "Đã chuyển tháng đầu"},
                )
                assert claim.status_code in (200, 201), claim.text
                claim_id = (claim.json().get("claim") or claim.json())["id"]
                receipt_note = client.post(
                f"/landlord/payment-claims/{claim_id}/confirm",
                headers={"Authorization": f"Bearer {owner}"},
                )
                assert receipt_note.status_code in (200, 201), receipt_note.text
                receipt = client.get(
                f"/invoices/{invoice_id}", headers={"Authorization": f"Bearer {renter}"}
                )
                assert receipt.status_code == 200


# --- Nhánh tin cào (concierge) --------------------------------------------------


def test_crawled_branch_concierge_queue(service):
    service.catalog.import_rooms([_crawled_room()])
    with _client(service) as client:
            renter = _login(client, "renter")
            owner = _login(client, "owner2")
            admin = _login(client, "admin")

            booked = _book(client, renter, "chotot-e2e-1", key_suffix="concierge")
            assert booked.status_code == 201, booked.text
            viewing = booked.json()
            # E-02: handler concierge, không landlord.
            assert viewing["handler"] == "concierge" and viewing["landlord_id"] is None
            # owner2 không thấy lịch đó và không có thông báo mới về nó.
            owner_views = client.get(
                "/viewings", headers={"Authorization": f"Bearer {owner}"}
            ).json()
            assert viewing["id"] not in {item["id"] for item in owner_views}
            owner_notifications = client.get(
                "/notifications", headers={"Authorization": f"Bearer {owner}"}
            ).json()
            items = owner_notifications.get("items", owner_notifications)
            assert all(item.get("room_id") != "chotot-e2e-1" for item in items)

            # Hàng đợi admin: có lịch, KHÔNG trả tên/SĐT (R3).
            queue = client.get(
                "/admin/viewings", headers={"Authorization": f"Bearer {admin}"}
            )
            assert queue.status_code == 200, queue.text
            queue_item = next(row for row in queue.json() if row["id"] == viewing["id"])
            # R3: hàng đợi không trả khóa liên hệ (khác với trả null).
            assert "contact_phone" not in queue_item and "contact_name" not in queue_item

            # Xem SĐT riêng: admin được, renter/owner không; mỗi lần admin xem có audit.
            reveal = client.get(
                f"/admin/viewings/{viewing['id']}/contact",
                headers={"Authorization": f"Bearer {admin}"},
            )
            assert reveal.status_code == 200
            assert reveal.json()["contact_phone"] == "0901234567"
            for role in (renter, owner):
                denied = client.get(
                    f"/admin/viewings/{viewing['id']}/contact",
                    headers={"Authorization": f"Bearer {role}"},
                )
                assert denied.status_code in (401, 403)
            # Admin route confirm + complete + feedback của khách.
            confirmed = client.post(
                f"/viewings/{viewing['id']}/actions",
                headers={"Authorization": f"Bearer {admin}"},
                json={"action": "confirm"},
            )
            assert confirmed.status_code == 200, confirmed.text
            completed = client.post(
                f"/viewings/{viewing['id']}/actions",
                headers={"Authorization": f"Bearer {admin}"},
                json={"action": "complete"},
            )
            assert completed.status_code == 200
            feedback = client.post(
                f"/viewings/{viewing['id']}/feedback",
                headers={"Authorization": f"Bearer {renter}"},
                json={"rating": 4},
            )
            assert feedback.status_code == 200
            # Tin cào không có nút hợp đồng: create lease với viewing concierge → lỗi.
            from datetime import date
            lease_body = {"room_id": "chotot-e2e-1", "renter_id": "renter",
                          "viewing_id": viewing["id"],
                          "start_date": (date.today() + timedelta(days=1)).isoformat(),
                          "end_date": (date.today() + timedelta(days=30)).isoformat()}
            lease = client.post(
                "/landlord/leases", headers={"Authorization": f"Bearer {owner}"},
                json=lease_body,
            )
            assert lease.status_code in (403, 404)  # concierge: không thuộc owner nào


# --- A1 (15/11): link tin gốc của hàng đợi điều phối lấy từ `source` của phòng ---


def test_admin_viewings_carry_crawled_source_url(service):
    service.catalog.import_rooms([_crawled_room()])
    # Tin "cào" nhưng source là scheme nội bộ chotot:// → KHÔNG trả URL http.
    non_http = _crawled_room("chotot-e2e-src2").model_copy(
        update={"source": "chotot://ad/99"})
    service.catalog.import_rooms([non_http])
    with _client(service) as client:
        renter = _login(client, "renter")
        admin = _login(client, "admin")
        first = _book(client, renter, "chotot-e2e-1", key_suffix="src1")
        assert first.status_code == 201, first.text
        second = _book(client, renter, "chotot-e2e-src2", key_suffix="src2")
        assert second.status_code == 201, second.text
        queue = client.get(
            "/admin/viewings", headers={"Authorization": f"Bearer {admin}"}
        )
        assert queue.status_code == 200, queue.text
        rows = {row["id"]: row for row in queue.json()}
        row1 = rows[first.json()["id"]]
        row2 = rows[second.json()["id"]]
        # Link tin gốc là đúng trường source của phòng (không dựng từ mã phòng).
        assert row1["source_url"] == "https://www.chotot.com/999.htm", row1
        assert row1["room_id"] == "chotot-e2e-1"
        # Source không phải http(s) → không có link.
        assert row2["source_url"] is None, row2
        # Hàng đợi vẫn không trả liên hệ (R3).
        assert "contact_phone" not in row1 and "contact_name" not in row1


def test_admin_viewing_source_url_not_leaked_to_other_roles(service):
    service.catalog.import_rooms([_crawled_room()])
    with _client(service) as client:
        renter = _login(client, "renter")
        owner = _login(client, "owner2")
        booked = _book(client, renter, "chotot-e2e-1", key_suffix="leak")
        assert booked.status_code == 201, booked.text
        vid = booked.json()["id"]
        for token in (renter, owner):
            items = client.get(
                "/viewings", headers={"Authorization": f"Bearer {token}"}
            ).json()
            mine = next((item for item in items if item["id"] == vid), None)
            if mine is not None:
                assert "source_url" not in mine, mine
        detail = client.get(
            f"/viewings/{vid}", headers={"Authorization": f"Bearer {renter}"}
        ).json()
        assert "source_url" not in detail, detail


# --- B1 (15/11): tên phòng trong danh sách lịch, đi qua mask_address --------------


def test_viewings_and_admin_queue_carry_masked_room_title(service):
    room = _crawled_room("chotot-e2e-title").model_copy(update={
        "title": "Phòng 25 đường Bà Cut Q7. Còn trống",
        "street": "Đường Bà Cut",
    })
    service.catalog.import_rooms([room])
    with _client(service) as client:
        renter = _login(client, "renter")
        admin = _login(client, "admin")
        booked = _book(client, renter, "chotot-e2e-title", key_suffix="title")
        assert booked.status_code == 201, booked.text
        vid = booked.json()["id"]
        # Danh sách lịch của người thuê trả tên phòng đã che số nhà.
        mine = client.get(
            "/viewings", headers={"Authorization": f"Bearer {renter}"}
        ).json()
        row = next(item for item in mine if item["id"] == vid)
        assert "[Địa chỉ đã che]" in row["room_title"], row
        assert "25 đường Bà Cut" not in row["room_title"]
        # Hàng đợi điều phối cũng trả tên phòng (không trả liên hệ).
        queue = client.get(
            "/admin/viewings", headers={"Authorization": f"Bearer {admin}"}
        ).json()
        queue_row = next(item for item in queue if item["id"] == vid)
        assert "[Địa chỉ đã che]" in queue_row["room_title"], queue_row
        assert "contact_name" not in queue_row and "contact_phone" not in queue_row


# --- B4 (15/11): mục kiểm chứng dùng nhãn phí tiếng Việt, không lộ khóa nội bộ ----


def test_completeness_check_uses_vietnamese_fee_labels():
    from backend.app.trust import _completeness
    room = _crawled_room("chotot-e2e-fees").model_copy(update={
        "quote": Quote(rent_vnd=900_000, deposit_vnd=900_000, fees=[]),
    })
    detail = _completeness(room)
    assert detail["status"] == "warn"
    assert "điện" in detail["detail"] and "nước" in detail["detail"], detail
    assert "electricity" not in detail["detail"], detail
    assert "water" not in detail["detail"], detail
    # Tin đủ dữ liệu vẫn báo ok như cũ.
    full = _crawled_room("chotot-e2e-fees-full")
    assert _completeness(full)["status"] == "ok"


# --- B5 (15/11): /me/profile phải còn hoạt động khi tài khoản có dữ liệu hồ sơ ----
# (Trước đây profile.get() trên sqlite3.Row gây 500 → form đặt lịch không điền
# sẵn được họ tên vì effect gọi /me/profile luôn lỗi.)


def test_me_profile_returns_data_when_account_profile_exists(service):
    with _client(service) as client:
        renter = _login(client, "renter")
        patched = client.patch(
            "/me/profile",
            headers={"Authorization": f"Bearer {renter}"},
            json={"display_name": "Nguyễn Văn A"},
        )
        assert patched.status_code == 200, patched.text
        got = client.get("/me/profile", headers={"Authorization": f"Bearer {renter}"})
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["display_name"] == "Nguyễn Văn A"
        assert body["contact_phone"] is None  # người thuê không khai SĐT tài khoản (v14)
        # PATCH lần nữa vẫn hoạt động (hồ sơ đã tồn tại).
        patched_again = client.patch(
            "/me/profile",
            headers={"Authorization": f"Bearer {renter}"},
            json={"display_name": "Nguyễn Văn B"},
        )
        assert patched_again.status_code == 200, patched_again.text


# --- Nhánh lỗi ------------------------------------------------------------------


def test_error_branch_conflicts_and_stale(service):
    service.catalog.import_rooms([_crawled_room("chotot-e2e-err")])
    with _client(service) as client:
            renter = _login(client, "renter")
            admin = _login(client, "admin")

            booked = _book(client, renter, "chotot-e2e-err", key_suffix="err")
            assert booked.status_code == 201
            viewing = booked.json()
            # Sai chuyển trạng thái: renter không thể complete (chỉ handler).
            wrong_role = client.post(
                f"/viewings/{viewing['id']}/actions",
                headers={"Authorization": f"Bearer {renter}"},
                json={"action": "complete"},
            )
            assert wrong_role.status_code == 403
            # Chuyển không có trong bảng: confirmed → requested không hợp lệ trực tiếp.
            confirm = client.post(
                f"/viewings/{viewing['id']}/actions",
                headers={"Authorization": f"Bearer {admin}"},
                json={"action": "confirm"},
            )
            assert confirm.status_code == 200
            invalid = client.post(
                f"/viewings/{viewing['id']}/actions",
                headers={"Authorization": f"Bearer {admin}"},
                json={"action": "confirm"},
            )
            # Lặp cùng trạng thái đích → trả kết quả cũ, không lỗi.
            assert invalid.status_code == 200 and invalid.json()["status"] == "confirmed"
            events = client.get(
                f"/viewings/{viewing['id']}/events",
                headers={"Authorization": f"Bearer {renter}"},
            ).json()
            confirmed_events = [e for e in events if e["to_status"] == "confirmed"]
            assert len(confirmed_events) == 1, "replay must not add a second event"

            # Phòng hết trong lúc chờ → confirm lại trả stale_viewing (E-01.6).
            from backend.app.models import CatalogStatus
            room = service.catalog.room("chotot-e2e-err")
            service.catalog.change_status(
                "chotot-e2e-err",
                CatalogStatus(expected_revision=room.revision, available=False),
            )
            second = _book(client, renter, "chotot-e2e-err", key_suffix="err2")
            if second.status_code == 409:
                # Phòng đã hết: đặt mới bị chặn đúng luật not_available.
                return
            second_viewing = second.json()
            stale = client.post(
                f"/viewings/{second_viewing['id']}/actions",
                headers={"Authorization": f"Bearer {admin}"},
                json={"action": "confirm"},
            )
            assert stale.status_code == 409
            assert stale.json()["error"]["code"] == "stale_viewing"

            # Hủy và vắng mặt trên lịch confirmed đầu.
            cancelled = client.post(
                f"/viewings/{viewing['id']}/actions",
                headers={"Authorization": f"Bearer {renter}"},
                json={"action": "cancel"},
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"
            # Lịch đã hủy không chuyển tiếp được.
            after_cancel = client.post(
                f"/viewings/{viewing['id']}/actions",
                headers={"Authorization": f"Bearer {admin}"},
                json={"action": "complete"},
            )
            assert after_cancel.status_code == 409
            assert after_cancel.json()["error"]["code"] == "viewing_conflict"


# --- SĐT không vào prompt/handover/log (R3/E-01) --------------------------------


def test_contact_phone_never_reaches_model_or_handover(service):
    service.catalog.import_rooms([_crawled_room("chotot-e2e-pii")])
    with _client(service) as client:
            renter = _login(client, "renter")
            booked = _book(client, renter, "chotot-e2e-pii", key_suffix="pii")
            assert booked.status_code == 201
            viewing = booked.json()
            # public_result strip: redact_result bỏ contact_phone khỏi kết quả tool.
            from backend.app.agent_tools import redact_result
            sent_to_model = redact_result({"viewing": dict(viewing)})
            assert "contact_phone" not in json.dumps(sent_to_model)
            assert "0901234567" not in json.dumps(sent_to_model, ensure_ascii=False)
            # Handover context gửi model phải đi qua redact (viewing_row từ repo có
            # contact_phone, nhưng kết quả gửi model thì không).
            from backend.app.agent_tools import redact_result as redact_row
            viewing_row = service.repo.viewing(viewing["id"])
            sent_to_model_2 = redact_row({"viewing": dict(viewing_row)})
            assert "contact_phone" not in json.dumps(sent_to_model_2)
            assert "0901234567" not in json.dumps(sent_to_model_2, ensure_ascii=False)


# --- E-06.1: phí nhất quán (lỗi 1) -----------------------------------------------


def test_extract_fees_consistency_samples():
    from data.crawl_chotot import extract_fees
    samples = {
        "Dịch vụ 200k/phòng": ("service", "200000", "fixed"),
        "Xe 100k/chiếc": ("parking", "100000", "vehicle"),
        "Nước 120k/người": ("water", "120000", "person"),
        "Điện 4k/kWh": ("electricity", "4000", "kwh"),
    }
    for text, (name, amount, mode) in samples.items():
        fees, _ = extract_fees(text, 1)
        assert fees, f"phí không đọc được từ: {text}"
        assert fees[0]["name"] == name and fees[0]["amount_vnd"] == amount \
            and fees[0]["mode"] == mode


# --- E-03: che địa chỉ ------------------------------------------------------------


def test_mask_address_context_rules():
    from backend.app.listings import mask_address
    masked = mask_address("Nhà 25/12 đường Bà Cut gần chợ", "Đường Bà Cut")
    assert "25/12" not in masked and "[Địa chỉ đã che]" in masked
    # Không che nhầm: 24/7, ngày, tiền, số người.
    keep = mask_address(
        "Mở 24/7, nộp ngày 12/11, giá 3tr5, xe 200k/phòng, đủ 2 người, 5 triệu.",
        "Đường Bà Cut",
    )
    assert keep == "Mở 24/7, nộp ngày 12/11, giá 3tr5, xe 200k/phòng, đủ 2 người, đủ 5 triệu." \
        or "24/7" in keep and "12/11" in keep and "3tr5" in keep and "200k/phòng" in keep
    numbered = mask_address("Nhà số 25/3 gần đó", None)
    assert "25/3" not in numbered
    numbered_a = mask_address("Nhà số 25/3A gần đó", None)
    assert "25/3A" not in numbered_a, numbered_a

    # Sửa 15/11: số đứng liền sau chữ cái/chữ số không phải số nhà —
    # "40m2 <tên đường>" phải giữ nguyên "40m2".
    area = mask_address("Studio 2 Ban Công Full Nội Thất 40m2 Trần Xuân Soạn Q7",
                        "Đường Trần Xuân Soạn")
    assert "40m2 Trần Xuân Soạn" in area, area
    assert "40m[Địa chỉ đã che]" not in area
    area2 = mask_address("Phòng 30m² Trần Xuân Soạn gần chợ", "Đường Trần Xuân Soạn")
    assert "30m² Trần Xuân Soạn" in area2, area2
    area3 = mask_address("Căn hộ Q7 Bà Cut giá tốt", "Đường Bà Cut")
    assert "Q7 Bà Cut" in area3, area3
    # Các trường hợp đúng vẫn che như cũ.
    still = mask_address("Nhà 25/12 đường Bà Cut", "Đường Bà Cut")
    assert "25/12" not in still
    still2 = mask_address("Liên hệ trước khi tới 25 Đường Bà Cut", "Đường Bà Cut")
    assert "25 Đường Bà Cut" not in still2 and "[Địa chỉ đã che] Đường Bà Cut" in still2
    # 24/7, ngày, tiền không bị che (không kề ngay tên đường).
    keep2 = mask_address("Cửa hàng mở 24/7 gần đó, nộp tiền ngày 12/11, giá 3tr5",
                         "Đường Bà Cut")
    assert "24/7" in keep2 and "12/11" in keep2 and "3tr5" in keep2


# --- Sửa 4 lỗi + E-03 còn thiếu (08/11) -----------------------------------------


def _landlord_viewing(service, client, owner_token, renter_token, room_id="chotot-e2e-fix"):
    service.catalog.import_rooms([_crawled_room().__class__.model_validate({
        **{k: v for k, v in _crawled_room().model_dump(mode="json").items()},
        "id": room_id,
        "source": "synthetic://fix",  # handler=landlord, gán cho owner2 qua landlord_for
    })])
    room = service.catalog.room(room_id)
    # _crawled_room đặt landlord_id=owner2 (landlord_for); ép rõ ràng:
    if room.landlord != "owner2":
        fixed = room.model_copy(update={"landlord_id": "owner2"})
        service.catalog.import_rooms([fixed])
    booked = _book(client, renter_token, room_id, key_suffix="fix")
    assert booked.status_code == 201, booked.text
    return booked.json()


def test_owner1_cannot_touch_owner2_viewing(service):
    """Lỗi 1: owner1 decline/confirm/propose/complete/no_show lịch của owner2
    phải 403, trạng thái không đổi, không event mới."""
    with _client(service) as client:
        renter = _login(client, "renter")
        owner_b = _login(client, "owner1")
        viewing = _landlord_viewing(service, client, renter, renter)
        vid = viewing["id"]
        before = client.get(f"/viewings/{vid}", headers={"Authorization": f"Bearer {renter}"}).json()
        assert before["landlord_id"] == "owner2"
        for action in ("decline", "confirm", "complete", "no_show"):
            response = client.post(
                f"/viewings/{vid}/actions",
                headers={"Authorization": f"Bearer {owner_b}"},
                json={"action": action},
            )
            assert response.status_code == 403, f"{action}: {response.status_code} {response.text}"
        proposed = client.post(
            f"/viewings/{vid}/actions",
            headers={"Authorization": f"Bearer {owner_b}"},
            json={"action": "propose",
                  "proposed_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()},
        )
        assert proposed.status_code == 403
        after = client.get(f"/viewings/{vid}", headers={"Authorization": f"Bearer {renter}"}).json()
        assert after["status"] == "requested" == before["status"]
        events = client.get(f"/viewings/{vid}/events", headers={"Authorization": f"Bearer {renter}"}).json()
        assert len(events) == 1  # chỉ event created→requested


def test_concierge_admin_never_gets_contact_without_audit(service):
    """Lỗi 2/R3: admin confirm → response, chi tiết, hàng đợi, events đều KHÔNG
    chứa SĐT; hm_audit_log không tăng khi không xem SĐT; route xem SĐT 2 lần
    tạo đúng 2 dòng audit mới."""
    with _client(service) as client:
        renter = _login(client, "renter")
        admin = _login(client, "admin")
        service.catalog.import_rooms([_crawled_room("chotot-e2e-audit")])
        booked = _book(client, renter, "chotot-e2e-audit", key_suffix="audit")
        assert booked.status_code == 201
        vid = booked.json()["id"]
        row = service.repo.db.execute(
            "SELECT COUNT(*) AS n FROM hm_audit_log WHERE resource_id=?", (vid,)
        ).fetchone()["n"]
        confirmed = client.post(
            f"/viewings/{vid}/actions",
            headers={"Authorization": f"Bearer {admin}"},
            json={"action": "confirm"},
        )
        assert confirmed.status_code == 200
        assert "0901234567" not in confirmed.text
        detail = client.get(f"/viewings/{vid}", headers={"Authorization": f"Bearer {admin}"})
        assert "0901234567" not in detail.text
        queue = client.get("/admin/viewings", headers={"Authorization": f"Bearer {admin}"})
        assert "0901234567" not in queue.text
        events = client.get(f"/viewings/{vid}/events", headers={"Authorization": f"Bearer {admin}"})
        assert "0901234567" not in events.text
        after = service.repo.db.execute(
            "SELECT COUNT(*) AS n FROM hm_audit_log WHERE resource_id=?", (vid,)
        ).fetchone()["n"]
        assert after == row, f"audit không được ghi tự động: {row} → {after}"
        for _ in range(2):
            reveal = client.get(
                f"/admin/viewings/{vid}/contact",
                headers={"Authorization": f"Bearer {admin}"},
            )
            assert reveal.status_code == 200
            assert reveal.json()["contact_phone"] == "0901234567"
        final = service.repo.db.execute(
            "SELECT COUNT(*) AS n FROM hm_audit_log WHERE resource_id=?", (vid,)
        ).fetchone()["n"]
        assert final == after + 2, f"2 lần xem SĐT phải tạo 2 audit: {after} → {final}"


def test_reschedule_flow_requires_handler_then_renter_accept(service):
    """Lỗi 3: renter propose trên confirmed → 403 (chọn 403 vì sai VAI TRỊ —
    bảng chuyển trạng thái cấm vai); handler propose → 200; renter accept →
    confirmed và requested_at bằng giờ đề xuất (lỗi 4)."""
    with _client(service) as client:
        renter = _login(client, "renter")
        owner = _login(client, "owner2")
        viewing = _landlord_viewing(service, client, renter, renter)
        vid = viewing["id"]
        confirmed = client.post(
            f"/viewings/{vid}/actions",
            headers={"Authorization": f"Bearer {owner}"},
            json={"action": "confirm"},
        )
        assert confirmed.status_code == 200
        # Người thuê tự propose trên lịch confirmed → bị cấm.
        renter_propose = client.post(
            f"/viewings/{vid}/actions",
            headers={"Authorization": f"Bearer {renter}"},
            json={"action": "propose",
                  "proposed_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()},
        )
        assert renter_propose.status_code == 403, renter_propose.text
        # Handler propose → 200, proposed_at được ghi.
        # 18:00 giờ Việt Nam (11:00 UTC) ba ngày tới: khung giờ phải thành "evening".
        proposed_at = (datetime.now(timezone.utc) + timedelta(days=3)).replace(
            hour=11, minute=0, second=0, microsecond=0).isoformat()
        proposed = client.post(
            f"/viewings/{vid}/actions",
            headers={"Authorization": f"Bearer {owner}"},
            json={"action": "propose", "proposed_at": proposed_at},
        )
        assert proposed.status_code == 200, proposed.text
        assert proposed.json()["proposed_at"] is not None
        # Renter accept → confirmed và requested_at = giờ đề xuất; proposed_at rỗng.
        accepted = client.post(
            f"/viewings/{vid}/actions",
            headers={"Authorization": f"Bearer {renter}"},
            json={"action": "accept"},
        )
        assert accepted.status_code == 200, accepted.text
        body = accepted.json()
        assert body["status"] == "confirmed"
        assert body["requested_at"].startswith(proposed_at[:16]), \
            f"requested_at phải bằng giờ đề xuất: {body['requested_at']} vs {proposed_at}"
        assert body.get("proposed_at") is None
        # Nhãn khung giờ đi theo giờ đã đồng ý, không giữ khung giờ lúc đặt.
        assert body["time_slot"] == "evening"


def test_choose_time_updates_requested_at(service):
    """Lỗi 4: choose_time từ reschedule_proposed → requested, requested_at =
    giờ mới, proposed_at rỗng, event ghi giờ cũ → mới."""
    with _client(service) as client:
        renter = _login(client, "renter")
        owner = _login(client, "owner2")
        viewing = _landlord_viewing(service, client, renter, renter)
        vid = viewing["id"]
        old_at = viewing["requested_at"]
        proposed = client.post(
            f"/viewings/{vid}/actions",
            headers={"Authorization": f"Bearer {owner}"},
            json={"action": "propose",
                  "proposed_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()},
        )
        assert proposed.status_code == 200
        new_at = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        chosen = client.post(
            f"/viewings/{vid}/actions",
            headers={"Authorization": f"Bearer {renter}"},
            json={"action": "choose_time", "requested_at": new_at, "time_slot": "evening"},
        )
        assert chosen.status_code == 200, chosen.text
        body = chosen.json()
        assert body["status"] == "requested"
        assert body["requested_at"].startswith(new_at[:16]), body["requested_at"]
        assert body.get("proposed_at") is None
        assert body.get("time_slot") == "evening"
        events = client.get(f"/viewings/{vid}/events", headers={"Authorization": f"Bearer {renter}"}).json()
        move_events = [e for e in events if e["to_status"] == "requested"]
        assert move_events and old_at in json.dumps(move_events) and "2026-11" in json.dumps(move_events)


def test_model_never_sees_street_number_in_title(service):
    """E-03: tiêu đề có số nhà không đi nguyên văn vào dữ liệu gửi model."""
    from backend.app.agent_loop import _mask_title_for_model
    masked = _mask_title_for_model("Phòng 25/12 Lê Văn Sỹ. Đẹp", None)
    assert "25/12" not in masked
    assert "[Địa chỉ đã che]" in masked


def test_viewing_booked_from_assistant_results_carries_contact_to_landlord(service):
    """Luồng tìm phòng: đặt lịch NGAY từ kết quả gợi ý (/sessions/{id}/viewings) phải
    mang tên, SĐT và khung giờ như đặt từ tin đăng — chủ nhà thấy sau khi xác nhận."""
    with _client(service) as client:
        renter = _login(client, "renter")
        owner = _login(client, "owner2")
        auth = {"Authorization": f"Bearer {renter}"}
        sid = client.post("/sessions", headers=auth).json()["session_id"]
        message = client.post(f"/sessions/{sid}/messages", headers=auth,
                              json={"text": "Tìm phòng TP.HCM Quận 7 cho 1 người tầm 3 triệu"})
        profile = {"city": "TP.HCM", "area": "Quận 7", "room_type": "room",
                   "max_monthly_cost_vnd": 4_000_000, "scenario": {"people": 1}}
        confirmed = client.post(f"/sessions/{sid}/confirm", headers=auth,
                                json={"profile": profile,
                                      "expected_draft_revision": message.json()["draft_revision"]})
        assert confirmed.status_code == 200, confirmed.text
        room_id = confirmed.json()["results"][0]["room_id"]
        when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        body = {"room_id": room_id, "requested_at": when, "idempotency_key": "from-results-1",
                "contact_name": "Nguyễn Văn A", "contact_phone": "0912345678",
                "time_slot": "morning"}
        # Có liên hệ mà thiếu đồng ý chia sẻ → 422.
        assert client.post(f"/sessions/{sid}/viewings", headers=auth, json=body).status_code == 422
        created = client.post(f"/sessions/{sid}/viewings", headers=auth,
                              json={**body, "contact_consent": True})
        assert created.status_code == 201, created.text
        viewing = created.json()
        assert viewing["time_slot"] == "morning"
        owner_auth = {"Authorization": f"Bearer {owner}"}
        confirm = client.post(f"/viewings/{viewing['id']}/actions", headers=owner_auth,
                              json={"action": "confirm"})
        assert confirm.status_code == 200, confirm.text
        seen = next(item for item in client.get("/viewings", headers=owner_auth).json()
                    if item["id"] == viewing["id"])
        assert seen["contact_name"] == "Nguyễn Văn A" and seen["contact_phone"]
