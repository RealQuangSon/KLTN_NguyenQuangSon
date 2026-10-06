"""Offline vertical slice. No external API, real listing, or actual viewing booking."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from .app.costs import calculate_cost
from .app.interpreter import DemoInterpreter
from .app.models import Actor, Profile, Review, Scenario
from .app.service import HomeMatchService


def main():
    with TemporaryDirectory(prefix="homematch-demo-") as directory:
        service = HomeMatchService(Path(directory) / "demo.sqlite", interpreter=DemoInterpreter())
        renter = Actor(id="renter-a", role="renter")
        landlord = Actor(id="owner-a", role="owner")  # demo rooms belong to owner-a
        session_id = service.create_session(renter)["session_id"]
        reply = service.message(session_id, renter, "Tìm phòng TP.HCM Quận 7 cho 1 người, khoảng 3,5 triệu, thoáng và yên tĩnh")
        print(json.dumps({"interview": reply}, ensure_ascii=False, indent=2))
        profile = Profile(city="TP.HCM", area="Quận 7", max_monthly_cost_vnd=3_500_000,
                          max_initial_cash_vnd=6_500_000, must_amenities=["private_bathroom"],
                          preferences=["window", "quiet"], scenario=Scenario())
        pending = service.confirm(session_id, renter, profile, reply["draft_revision"])
        print(json.dumps({"before_approval": pending}, ensure_ascii=False, indent=2))
        run_id = pending["run_id"]
        draft = service.draft(run_id, landlord)
        selected = [item["room_id"] for item in draft["items"]][:3]
        service.review(run_id, landlord, Review(decision="approve", expected_profile_version=1,
            keep_room_ids=selected, reason="Đã kiểm tra dữ liệu giả lập và chi phí.",
            override_reason="Chỉ giữ 3 phòng đầu để khách dễ so sánh.", idempotency_key="demo-approval"))
        result = service.results(session_id, renter)
        print(json.dumps({"after_approval": {"status": result["status"], "rooms": [
            {"id": item["room_id"], "monthly_vnd": item["cost"]["monthly_total_vnd"],
             "reasons": item["reasons"], "tradeoffs": item["tradeoffs"]} for item in result["results"]]}}, ensure_ascii=False, indent=2))
        print("Compared rooms:", len(service.compare(session_id, renter, selected[:2])["items"]))
        reference = next(room for room in service.catalog.rooms() if room.id == "demo-01")
        cost = calculate_cost(reference.quote, Scenario())
        print("Reference cost (VND): monthly =", cost.monthly_total_vnd, "; initial =", cost.initial_total_vnd)
        viewing = service.request_viewing(session_id, renter, selected[0], datetime.now(timezone.utc)+timedelta(days=1), "demo-viewing")
        print("Internal viewing:", viewing["status"], "→", service.respond_viewing(viewing["id"], landlord, "confirmed")["status"])
        service.close()


if __name__ == "__main__":
    main()
