"""DA-03: hand-computed PMS invoice oracle executed on a throwaway service DB.

Expected totals and lines in `data/oracles/invoice_cases.json` are authored
arithmetic, independent of `backend/` code. The suite only builds the inputs the
billing engine consumes (quote snapshot, readings, occupants, vehicles) through
`HomeMatchService` on a temporary SQLite DB, then compares line by line. A
disagreement is recorded and fails the suite; the oracle is never adjusted to
match the code.
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from backend.app.models import Actor, DomainError, Room
from backend.app.service import HomeMatchService

from .common import content_hash, dataset_manifest, read_json, write_json
from .pipeline import code_hashes

OWNER = Actor(id="owner2", role="owner")
RENTER = Actor(id="renter-inv", role="renter")
# Labels are informational copy; the oracle asserts the money-bearing fields.
LINE_KEYS = ("name", "quantity", "unit_price", "amount_vnd")
AMENITIES = ("window", "quiet", "parking", "private_bathroom", "air_conditioning",
             "washing_machine", "balcony", "furniture", "pets_allowed")


def _case_room(index: int, case: dict) -> Room:
    case_id = case["case_id"]
    room_type = case["room_type"]
    value = {"id": f"inv-room-{index:02d}", "revision": 1, "title": f"Hóa đơn oracle {case_id}",
             "city": "TP.HCM", "area": "Quận 7", "room_type": room_type,
             "bedrooms": 2 if room_type == "apartment" else None, "capacity": 4,
             "area_m2": 70 if room_type == "apartment" else 20, "published": True, "available": True,
             "amenities": {name: True for name in AMENITIES}, "latitude": 10.735, "longitude": 106.721,
             "location_accuracy": "approximate", "uncertainty_m": 50, "quote": case["quote"],
             "source": f"synthetic://invoice-oracle/{case_id}", "synthetic": True,
             "landlord_id": OWNER.id}
    return Room.model_validate(value)


def _reading_input(service, lease_id: str, reading: dict):
    from backend.app import pms
    data = pms.ReadingInput(period=reading["period"])
    for key in ("electricity_start", "electricity_end", "water_start", "water_end"):
        if reading.get(key) is not None:
            setattr(data, key, Decimal(str(reading[key])))
    return service.record_reading(OWNER, lease_id, data)


def _active_lease(service, room_id: str, lease: dict) -> dict:
    from backend.app import pms
    start = date(2026, 10, 1)
    item = service.create_lease(OWNER, pms.LeaseInput(
        renter_id=RENTER.id, room_id=room_id, start_date=start, end_date=start + timedelta(days=180),
        rent_vnd=lease["rent_vnd"], deposit_vnd=lease["rent_vnd"],
        occupants=lease["occupants"], vehicles=lease["vehicles"]))
    service.send_lease(OWNER, item["id"])
    service.accept_lease(RENTER, item["id"], item["version"])
    return service.activate_lease(OWNER, item["id"])


def _comparable(lines: list[dict]) -> list[dict]:
    return [{key: line[key] for key in LINE_KEYS} for line in lines]


def invoice_oracle_report(data_dir: Path, output: Path) -> dict:
    manifest = dataset_manifest(data_dir)
    payload = read_json(data_dir / "oracles/invoice_cases.json")
    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="homematch-eval-invoices-") as directory:
        root = Path(directory)
        service = HomeMatchService(root / "invoices.sqlite")
        try:
            service.catalog.import_rooms([_case_room(index, case)
                                          for index, case in enumerate(payload["cases"], 1)])
            with service.repo.db:
                for user, role in ((RENTER.id, "renter"), (OWNER.id, "owner")):
                    service.repo.db.execute("INSERT INTO hm_users(id,role,password_hash) VALUES(?,?,?) "
                                            "ON CONFLICT(id) DO NOTHING", (user, role, "unused"))
            from backend.app import pms
            for index, case in enumerate(payload["cases"], 1):
                actual_error, invoice = None, None
                try:
                    item = _active_lease(service, f"inv-room-{index:02d}", case["lease"])
                    reading = case.get("reading")
                    if reading:
                        _reading_input(service, item["id"], reading)
                    if actual_error is None:
                        period = (reading or {}).get("period", "2026-10")
                        invoice = service.issue_invoice(OWNER, item["id"], pms.InvoiceInput(period=period))
                except DomainError as exc:
                    actual_error = exc.code
                differences: dict = {}
                expected_error = case["expected_error"]
                if expected_error or actual_error:
                    if expected_error != actual_error:
                        differences["error"] = {"expected": expected_error, "actual": actual_error}
                else:
                    actual_lines = _comparable(invoice["lines"])
                    expected_lines = _comparable(case["lines"])
                    if actual_lines != expected_lines:
                        differences["lines"] = {"expected": expected_lines, "actual": actual_lines}
                    if invoice["total_vnd"] != case["expected_total_vnd"]:
                        differences["total_vnd"] = {"expected": case["expected_total_vnd"],
                                                    "actual": invoice["total_vnd"]}
                rows.append({"case_id": case["case_id"], "passed": not differences,
                             "expected_error": expected_error, "actual_error": actual_error,
                             "expected_total_vnd": case["expected_total_vnd"],
                             "actual_total_vnd": invoice["total_vnd"] if invoice else None,
                             "expected_lines": case["lines"],
                             "actual_lines": invoice["lines"] if invoice else None,
                             "differences": differences,
                             "calculation_note": case["calculation_note"]})
        finally:
            service.close()
    summary = {"kind": "offline_pms_invoice_oracle", "case_count": len(rows),
               "input_manifest_hash": content_hash(manifest), "code_hashes": code_hashes(),
               "passed": sum(row["passed"] for row in rows), "failed": sum(not row["passed"] for row in rows),
               "exact_vnd_required": True, "line_labels_compared": False,
               "oracle_origin": "Authored hand calculations, independent of backend output; human cross-check pending.",
               "disagreement_policy": "oracle stays fixed; disagreements are reported for backend review",
               "cases": rows,
               "notice": "Invoice figures on synthetic fixtures; not a claim about real landlord billing."}
    write_json(output, summary)
    return summary
