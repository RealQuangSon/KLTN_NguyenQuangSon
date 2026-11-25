"""Offline vertical slice. No external API, real listing, or actual viewing booking."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from .app.costs import calculate_cost
from .app.interpreter import DemoInterpreter
from .app.models import Actor, Profile, Scenario
from .app.service import HomeMatchService


def main():
    with TemporaryDirectory(prefix="homematch-demo-") as directory:
        service = HomeMatchService(Path(directory) / "demo.sqlite", interpreter=DemoInterpreter())
        renter = Actor(id="renter", role="renter")
        landlord = Actor(id="owner2", role="owner")  # demo rooms belong to owner2
        session_id = service.create_session(renter)["session_id"]
        reply = service.message(session_id, renter, "Tìm phòng TP.HCM Quận 7 cho 1 người, khoảng 3,5 triệu, thoáng và yên tĩnh")
        print(json.dumps({"interview": reply}, ensure_ascii=False, indent=2))
        profile = Profile(city="TP.HCM", area="Quận 7", max_monthly_cost_vnd=3_500_000,
                          max_initial_cash_vnd=6_500_000, must_amenities=["private_bathroom"],
                          preferences=["window", "quiet"], scenario=Scenario())
        confirmed = service.confirm(session_id, renter, profile, reply["draft_revision"])
        run_id = confirmed["run_id"]
        selected = [item["room_id"] for item in confirmed["results"]][:3]
        # Quyết định 05/11/2026: kết quả công bố ngay, không còn bước chủ nhà duyệt.
        result = service.results(session_id, renter)
        print(json.dumps({"published": {"status": result["status"], "rooms": [
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
