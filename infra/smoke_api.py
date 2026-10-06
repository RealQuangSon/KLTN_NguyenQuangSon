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


def run(base: str, test_client=None) -> dict:
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
        landlords = ("owner-a", "owner-b", "owner-c", "owner-d")
        for user in ("renter-a", "renter-b", *landlords):
            login = request("POST", "/auth/login", body={"username": user, "password": f"local-{user}-password"})
            assert login["actor"]["id"] == user
            tokens[user] = login["access_token"]
            assert request("GET", "/auth/me", user)["id"] == user
        checks.append("seed_login_and_identity")
        catalog = request("GET", "/landlord/rooms", "owner-a")
        assert catalog["rooms"] and all(room["landlord_id"] in (None, "owner-a") for room in catalog["rooms"])

        session = request("POST", "/sessions", "renter-a", expected=201)
        sid = session["session_id"]
        request("GET", f"/sessions/{sid}", "renter-b", expected=403)
        request("GET", "/landlord/rooms", "renter-a", expected=403)
        message = request("POST", f"/sessions/{sid}/messages", "renter-a", {
            "text": "Tìm phòng TP.HCM Quận 7 cho 1 người, tầm 3,5 triệu, có cửa sổ và yên tĩnh"})
        assert message["draft"]["monthly_budget_vnd"] is None
        assert len(message["questions"]) <= 2
        revision = message["draft_revision"]
        patch = request("PATCH", f"/sessions/{sid}/draft", "renter-a", {
            "expected_draft_revision": revision, "set": {"people": 2},
            "clear_fields": [], "remove_preferences": []})
        assert patch["draft"]["people"] == 2
        request("PATCH", f"/sessions/{sid}/draft", "renter-a", {
            "expected_draft_revision": revision, "set": {"people": 1}}, expected=409)
        checks.append("ownership_draft_patch_and_cas")

        profile = {"city": "TP.HCM", "area": "Quận 7", "room_type": "room",
            "max_monthly_cost_vnd": 5_000_000, "max_initial_cash_vnd": 12_000_000,
            "must_amenities": ["private_bathroom"], "preferences": ["window", "quiet"],
            "scenario": {"people": 2, "vehicles": 1, "electricity_kwh": "140", "water_m3": "3",
                         "moving_vnd": 300_000, "setup_vnd": 200_000}}
        confirmed = request("POST", f"/sessions/{sid}/confirm", "renter-a", {
            "expected_draft_revision": patch["draft_revision"], "profile": profile})
        run_id = confirmed["run_id"]
        results = request("GET", f"/sessions/{sid}/results", "renter-a")
        assert results["status"] == "pending_review" and results["results"] == []
        # Each landlord sees only their own rooms of the shortlist; uninvolved landlords get 403.
        drafts = {}
        for landlord in landlords:
            response = client.get(f"/landlord/recommendations/{run_id}",
                                  headers={"Authorization": f"Bearer {tokens[landlord]}"})
            assert response.status_code in (200, 403)
            if response.status_code == 200:
                drafts[landlord] = response.json()
                assert all(item["landlord_id"] == landlord for item in drafts[landlord]["items"])
        assert drafts and sum(len(draft["items"]) for draft in drafts.values()) >= 2
        request("POST", f"/sessions/{sid}/compare", "renter-a",
                {"room_ids": [item["room_id"] for draft in drafts.values() for item in draft["items"]][:2]}, expected=403)
        checks.append("pending_has_no_candidates_and_per_landlord_review_scope")

        expected_visible = []
        for landlord, draft in drafts.items():
            own = [item["room_id"] for item in draft["items"]]
            review = {"decision": "approve", "expected_profile_version": draft["profile_version"],
                      "keep_room_ids": list(reversed(own)), "reason": "Kiểm tra smoke với dữ liệu hoàn toàn giả lập.",
                      "override_reason": "Smoke kiểm tra đổi thứ tự có lý do." if len(own) > 1 else None,
                      "idempotency_key": f"smoke-review-{uuid4()}"}
            request("POST", f"/landlord/recommendations/{run_id}/review", landlord, review)
            request("POST", f"/landlord/recommendations/{run_id}/review", landlord, review)
            expected_visible += own
        results = request("GET", f"/sessions/{sid}/results", "renter-a")
        assert results["status"] == "published"
        ids = [item["room_id"] for item in results["results"]]
        assert sorted(ids) == sorted(expected_visible)
        comparison = request("POST", f"/sessions/{sid}/compare", "renter-a", {"room_ids": ids[:2]})
        assert len(comparison["items"]) == 2
        assert all(item["cost"]["monthly_total_vnd"] is not None for item in comparison["items"])
        checks.append("approval_subset_order_replay_and_comparison")

        first = results["results"][0]
        owner = first["landlord_id"]
        viewing_body = {"room_id": first["room_id"], "mode": "online",
                        "requested_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                        "idempotency_key": f"smoke-viewing-{uuid4()}"}
        viewing = request("POST", f"/sessions/{sid}/viewings", "renter-a", viewing_body, expected=201)
        repeat = request("POST", f"/sessions/{sid}/viewings", "renter-a", viewing_body, expected=201)
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
        stale = request("GET", f"/sessions/{sid}/results", "renter-a")
        assert stale["status"] == "invalidated" and stale["results"] == []
        request("POST", f"/sessions/{sid}/compare", "renter-a", {"room_ids": ids[:2]}, expected=403)
        current = request("GET", f"/landlord/rooms/{first['room_id']}", owner)["room"]
        request("PATCH", f"/landlord/rooms/{first['room_id']}/status", owner, {
            "expected_revision": current["revision"], "available": room["available"]})
        checks.append("catalog_cas_and_stale_visibility")

        request("POST", "/auth/logout", "renter-a")
        request("GET", "/auth/me", "renter-a", expected=401)
        checks.append("token_revocation")
        # Report safe IDs/counts only; access tokens and payloads never leave this process.
        return {"status": "passed", "storage": health["storage"], "checks": checks,
                "transport": "in_process_testclient" if test_client is not None else "real_local_http",
                "session_id": sid, "run_id": run_id, "viewing_id": viewing["id"],
                "note": "Synthetic local mutation smoke; catalog availability restored, revision remains incremented."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--in-process", action="store_true", help="Use isolated SQLite/TestClient without opening TCP ports.")
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
        for user in ("RENTER_A", "RENTER_B", "MANAGER_A", "MANAGER_B"):
            os.environ.pop("HOMEMATCH_PASSWORD_" + user, None)
        with tempfile.TemporaryDirectory(prefix="homematch-smoke-") as directory:
            app = create_app(lambda: HomeMatchService(Path(directory) / "smoke.sqlite"))
            with TestClient(app, base_url=args.base) as client:
                result = run(args.base, client)
    else:
        result = run(args.base)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
