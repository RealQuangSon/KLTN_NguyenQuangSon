"""Exercise a running local API with synthetic data; no provider calls or secret output."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx


def run(base: str, test_client=None, service=None) -> dict:
    """`service` (in-process only) cho phép nháp cào: import một tin source Chợ Tốt
    để chạy nhánh điều phối. Real HTTP mode bỏ qua nhánh này."""
    if not base.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise ValueError("This mutation smoke is restricted to a local synthetic-data API.")
    tokens = {}
    checks = []
    with (nullcontext(test_client) if test_client is not None else httpx.Client(base_url=base, timeout=30)) as client:
        def request(method, path, user=None, body=None, expected=200):
            response = client.request(method, path, json=body,
                headers={"Authorization": f"Bearer {tokens[user]}"} if user else {})
            assert response.status_code == expected, f"{method} {path}: expected {expected}, got {response.status_code}"
            assert response.headers.get("X-Request-ID"), f"Missing request ID: {path}"
            return response.json()

        health = request("GET", "/health")
        assert health["matching_method"] == "B1", "Offline smoke expects B1."
        landlords = ("owner2", "owner1")
        for user in ("renter", *landlords):
            login = request("POST", "/auth/login", body={"username": user, "password": "123456"})
            assert login["actor"]["id"] == user
            tokens[user] = login["access_token"]
            assert request("GET", "/auth/me", user)["id"] == user
        checks.append("seed_login_and_identity")
        catalog = request("GET", "/landlord/rooms", "owner2")
        assert catalog["rooms"] and all(room["landlord_id"] in (None, "owner2") for room in catalog["rooms"])

        session = request("POST", "/sessions", "renter", expected=201)
        sid = session["session_id"]
        request("GET", f"/sessions/{sid}", "owner2", expected=403)
        request("GET", "/landlord/rooms", "renter", expected=403)
        message = request("POST", f"/sessions/{sid}/messages", "renter", {
            "text": "Tìm phòng TP.HCM Quận 7 cho 1 người, tầm 3,5 triệu, có cửa sổ và yên tĩnh"})
        assert message["draft"]["monthly_budget_vnd"] is None
        # UX-02: đủ thành phố + mức tiền thì backend tự xác nhận và xếp hạng ngay trong lượt.
        assert len(message.get("questions") or []) <= 2
        assert message["status"] in {"published", "no_match", "needs_clarification"}
        revision = message["draft_revision"]
        patch = request("PATCH", f"/sessions/{sid}/draft", "renter", {
            "expected_draft_revision": revision, "set": {"people": 2},
            "clear_fields": [], "remove_preferences": []})
        assert patch["draft"]["people"] == 2
        request("PATCH", f"/sessions/{sid}/draft", "renter", {
            "expected_draft_revision": revision, "set": {"people": 1}}, expected=409)
        checks.append("ownership_draft_patch_and_cas")

        profile = {"city": "TP.HCM", "area": "Quận 7", "room_type": "room",
            "max_monthly_cost_vnd": 5_000_000, "max_initial_cash_vnd": 12_000_000,
            "must_amenities": ["private_bathroom"], "preferences": ["window", "quiet"],
            "scenario": {"people": 2, "vehicles": 1, "electricity_kwh": "140", "water_m3": "3",
                         "moving_vnd": 300_000, "setup_vnd": 200_000}}
        confirmed = request("POST", f"/sessions/{sid}/confirm", "renter", {
            "expected_draft_revision": patch["draft_revision"], "profile": profile})
        run_id = confirmed["run_id"]
        # Quyết định 05/11/2026: kết quả công bố ngay sau khi xếp hạng, không chờ duyệt.
        results = request("GET", f"/sessions/{sid}/results", "renter")
        assert results["status"] == "published" and results["results"]
        # Endpoint duyệt gợi ý đã bị xóa: mọi vai trò đều 404, người thuê khác vẫn 403.
        request("GET", "/landlord/recommendations", "owner2", expected=404)
        request("GET", f"/landlord/recommendations/{run_id}", "owner2", expected=404)
        request("GET", f"/sessions/{sid}/results", "owner1", expected=403)
        checks.append("published_in_one_turn_and_review_endpoints_removed")

        ids = [item["room_id"] for item in results["results"]]
        assert len(ids) >= 2
        comparison = request("POST", f"/sessions/{sid}/compare", "renter", {"room_ids": ids[:2]})
        assert len(comparison["items"]) == 2
        assert all(item["cost"]["monthly_total_vnd"] is not None for item in comparison["items"])
        checks.append("published_order_and_comparison")

        first = results["results"][0]
        owner = first["landlord_id"]
        viewing_body = {"room_id": first["room_id"], "mode": "online",
                        "requested_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                        "idempotency_key": f"smoke-viewing-{uuid4()}"}
        viewing = request("POST", f"/sessions/{sid}/viewings", "renter", viewing_body, expected=201)
        repeat = request("POST", f"/sessions/{sid}/viewings", "renter", viewing_body, expected=201)
        assert repeat["id"] == viewing["id"] and viewing["status"] == "requested"
        assert viewing["meeting_url"] and viewing["landlord_id"] == owner
        reply = request("POST", f"/landlord/viewings/{viewing['id']}/respond", owner, {"status": "confirmed"})
        assert reply["status"] == "confirmed"
        checks.append("viewing_idempotency_online_and_confirmation")

        room = request("GET", f"/landlord/rooms/{first['room_id']}", owner)["room"]
        request("PATCH", f"/landlord/rooms/{first['room_id']}/status", owner, {
            "expected_revision": room["revision"], "available": False})
        request("PATCH", f"/landlord/rooms/{first['room_id']}/status", owner, {
            "expected_revision": room["revision"], "available": True}, expected=409)
        stale = request("GET", f"/sessions/{sid}/results", "renter")
        assert stale["status"] == "invalidated" and stale["results"] == []
        request("POST", f"/sessions/{sid}/compare", "renter", {"room_ids": ids[:2]}, expected=403)
        current = request("GET", f"/landlord/rooms/{first['room_id']}", owner)["room"]
        request("PATCH", f"/landlord/rooms/{first['room_id']}/status", owner, {
            "expected_revision": current["revision"], "available": room["available"]})
        checks.append("catalog_cas_and_stale_visibility")

        request("POST", "/auth/logout", "renter")
        request("GET", "/auth/me", "renter", expected=401)
        checks.append("token_revocation")

        # --- Nhánh 1: vòng đời lịch xem + hợp đồng từ lịch ---
        second_owner = results["results"][1]["landlord_id"]
        for user in dict.fromkeys(("renter", second_owner)):
            login = request("POST", "/auth/login", body={"username": user, "password": "123456"})
            tokens[user] = login["access_token"]
        handler = second_owner
        from datetime import date as _date
        viewing_body = {"mode": "offline",
                        "requested_at": (datetime.now(timezone.utc) + timedelta(days=2))
                        .strftime("%Y-%m-%dT08:00:00+07:00"),
                        "idempotency_key": f"smoke-lifecycle-{uuid4()}",
                        "contact_name": "Nguyễn Văn A", "contact_phone": "0901234567",
                        "contact_consent": True, "time_slot": "morning"}
        lifecycle = request("POST", f"/listings/{ids[1]}/viewings", "renter", viewing_body, expected=201)
        vid = lifecycle["id"]
        assert lifecycle["contact_shared"] and lifecycle["contact_phone"] == "0901234567"
        hidden = request("GET", f"/viewings/{vid}", handler)
        assert hidden["contact_phone"] is None, "phone must stay hidden before confirmed"
        propose = request("POST", f"/viewings/{vid}/actions", handler,
                          {"action": "propose", "proposed_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()})
        assert propose["status"] == "reschedule_proposed"
        accepted = request("POST", f"/viewings/{vid}/actions", "renter", {"action": "accept"})
        assert accepted["status"] == "confirmed" and accepted["contact_phone"] == "0901234567"
        completed = request("POST", f"/viewings/{vid}/actions", handler, {"action": "complete"})
        assert completed["status"] == "completed"
        feedback = request("POST", f"/viewings/{vid}/feedback", "renter", {"rating": 5, "note": "Đã xem phòng."})
        assert feedback["feedback_rating"] == 5
        period = _date.today().strftime("%Y-%m")
        lease_created = request("POST", "/landlord/leases", handler, {
            "room_id": ids[1], "renter_id": "renter", "viewing_id": vid,
            "start_date": (_date.today() + timedelta(days=1)).isoformat(),
            "end_date": (_date.today() + timedelta(days=181)).isoformat()}, expected=201)
        lease_id = (lease_created.get("lease") or lease_created)["id"]
        sent = request("POST", f"/landlord/leases/{lease_id}/send", handler)
        version = (sent.get("lease") or sent).get("version") or 2
        request("POST", f"/leases/{lease_id}/accept", "renter", {"expected_version": version})
        request("POST", f"/landlord/leases/{lease_id}/activate", handler)
        request("POST", f"/landlord/leases/{lease_id}/readings", handler,
                {"period": period, "electricity_start": 0, "electricity_end": 120,
                 "water_start": 0, "water_end": 4}, expected=201)
        invoice = request("POST", f"/landlord/leases/{lease_id}/invoices", handler,
                          {"period": period}, expected=201)
        invoice_id = (invoice.get("invoice") or invoice)["id"]
        claim = request("POST", f"/invoices/{invoice_id}/claims", "renter",
                        {"amount_vnd": 1, "reference": "Đã chuyển"}, expected=201)
        claim_id = (claim.get("claim") or claim)["id"]
        request("POST", f"/landlord/payment-claims/{claim_id}/confirm", handler)
        checks.append("viewing_lifecycle_and_lease_from_viewing")

        # --- Nhánh 2: tin cào → điều phối (chỉ in-process) ---
        if service is not None:
            from backend.app.models import Room as RoomModel
            crawled = RoomModel.model_validate({
                "id": "chotot-smoke-1", "revision": 1, "title": "Phòng trọ smoke Quận 7. Còn trống",
                "city": "TP.HCM", "area": "Quận 7", "room_type": "room", "capacity": 2,
                "area_m2": 20.0, "published": True, "available": True, "amenities": {},
                "quote": {"rent_vnd": 900_000, "deposit_vnd": 900_000, "fees": []},
                "source": "https://www.chotot.com/99999.htm", "synthetic": False,
                "poster_kind": "individual",
                "source_images": ["https://cdn.chotot.com/smoke/1.jpg"]})
            service.catalog.import_rooms([crawled])
            concierge_body = {"mode": "offline",
                              "requested_at": (datetime.now(timezone.utc) + timedelta(days=2))
                              .strftime("%Y-%m-%dT14:00:00+07:00"),
                              "idempotency_key": f"smoke-concierge-{uuid4()}",
                              "contact_name": "Trần Thị B", "contact_phone": "0987654321",
                              "contact_consent": True, "time_slot": "afternoon"}
            concierge = request("POST", "/listings/chotot-smoke-1/viewings", "renter",
                                concierge_body, expected=201)
            assert concierge["handler"] == "concierge" and concierge["landlord_id"] is None
            # owner2 không thấy lịch đó.
            owner_rows = request("GET", "/viewings", owner)
            assert concierge["id"] not in {row["id"] for row in owner_rows}
            admin_login = request("POST", "/auth/login", body={"username": "admin", "password": "123456"})
            tokens["admin"] = admin_login["access_token"]
            queue = request("GET", "/admin/viewings", "admin")
            row = next(item for item in queue if item["id"] == concierge["id"])
            assert "contact_phone" not in row, "admin queue must not carry contact"
            reveal = request("GET", f"/admin/viewings/{concierge['id']}/contact", "admin")
            assert reveal["contact_phone"] == "0987654321"
            request("GET", f"/admin/viewings/{concierge['id']}/contact", "renter", expected=403)
            confirmed_c = request("POST", f"/viewings/{concierge['id']}/actions", "admin",
                                  {"action": "confirm"})
            assert confirmed_c["status"] == "confirmed"
            completed_c = request("POST", f"/viewings/{concierge['id']}/actions", "admin",
                                  {"action": "complete"})
            assert completed_c["status"] == "completed"
            checks.append("concierge_queue_and_audit_reveal")
        # Report safe IDs/counts only; access tokens and payloads never leave this process.
        return {"status": "passed", "storage": health["storage"], "checks": checks,
                "transport": "in_process_testclient" if test_client is not None else "real_local_http",
                "session_id": sid, "run_id": run_id, "viewing_id": viewing["id"],
                "note": "Synthetic local mutation smoke; catalog availability restored, revision remains incremented."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--in-process", action="store_true",
                        help="TestClient without TCP ports; uses HOMEMATCH_DATABASE_URL when set, else isolated SQLite.")
    args = parser.parse_args()
    if args.in_process:
        from fastapi.testclient import TestClient
        from backend.app.main import create_app
        from backend.app.service import HomeMatchService
        for name, value in {"HOMEMATCH_PUBLIC": "false", "HOMEMATCH_AUTH_MODE": "seed",
                            "HOMEMATCH_LLM_MODE": "demo", "HOMEMATCH_MATCHING_METHOD": "B1",
                            "HOMEMATCH_EMBEDDING_MODE": "disabled", "HOMEMATCH_TOKEN_TTL_SECONDS": "3600",
                            "HOMEMATCH_CATALOG_PATH": str(Path(__file__).resolve().parents[1] / "data/catalog/rooms.json")}.items():
            os.environ[name] = value
        for user in ("RENTER", "RENTER_B", "MANAGER_A", "MANAGER_B"):
            os.environ.pop("HOMEMATCH_PASSWORD_" + user, None)
        # Smoke PostgreSQL in place when HOMEMATCH_DATABASE_URL points at it (e.g. the
        # local pg cluster); otherwise run against a throwaway isolated SQLite file.
        database_url = os.getenv("HOMEMATCH_DATABASE_URL")
        tempdir = None if database_url else tempfile.TemporaryDirectory(prefix="homematch-smoke-")
        try:
            target = database_url or str(Path(tempdir.name) / "smoke.sqlite")
            service_instance = HomeMatchService(target)
            app = create_app(lambda: service_instance)
            with TestClient(app, base_url=args.base) as client:
                result = run(args.base, client, service=service_instance)
        finally:
            if tempdir is not None:
                tempdir.cleanup()
    else:
        result = run(args.base)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
