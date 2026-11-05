"""data/llm_fees.py: LLM-proposed fees, terms and amenities are accepted only
after deterministic checks (LF-03).

No network: a fake extractor returns fixed proposals. Rejected values stay
absent (null, never 0/false), regex/API values already present are never
overwritten, and every acceptance quotes verbatim evidence from the post.
"""
import json
from datetime import datetime, timezone

import pytest

from data.llm_fees import (EXTRACTOR_VERSION, AmenityCandidate, FeeCandidate, FeeExtraction,
                           ListingExtraction, enrich, run, verify, verify_amenity, verify_date,
                           verify_term)

POST = ("Phòng trọ Gò Vấp\nĐiện 3k5/số, nước 100k/người. Wifi miễn phí.\n"
        "Phí dịch vụ 150.000đ/tháng, giữ xe 100k/chiếc.")

TERMS_POST = ("Phòng đủ tiện nghi.\nĐóng 3 tháng 1 lần. Hợp đồng tối thiểu 6 tháng. Hợp đồng 1 năm. "
              "Thuê ít nhất 6 tháng. Trống từ 1/12.\nWifi miễn phí. Có bếp. Không chung chủ. "
              "Ở chung chủ cùng gia đình. Không có wifi.")
POSTED_AT = datetime(2026, 10, 30, 4, 0, tzinfo=timezone.utc)


def fee(**fields):
    return FeeCandidate.model_validate({"included_in_rent": False, **fields})


@pytest.mark.parametrize("candidate", [
    fee(name="electricity", amount_vnd=3500, mode="kwh", evidence="Điện 3k5/số"),
    fee(name="water", amount_vnd=100000, mode="person", evidence="nước 100k/người"),
    fee(name="internet", amount_vnd=0, mode="fixed", included_in_rent=True, evidence="Wifi miễn phí"),
    fee(name="service", amount_vnd=150000, mode="fixed", evidence="Phí dịch vụ 150.000đ/tháng"),
    # Spacing and accents differ from the post: compared on the folded, space-normalized text.
    fee(name="parking", amount_vnd=100000, mode="vehicle", evidence="giu xe   100k/chiec"),
])
def test_grounded_fees_are_accepted(candidate):
    assert verify(candidate, POST) is None


@pytest.mark.parametrize("candidate, reason", [
    (fee(name="electricity", amount_vnd=4000, mode="kwh", evidence="Điện 4k/số"), "evidence_not_in_post"),
    (fee(name="water", amount_vnd=3500, mode="m3", evidence="Điện 3k5/số"), "evidence_wrong_fee"),
    (fee(name="electricity", amount_vnd=3000, mode="kwh", evidence="Điện 3k5/số"), "amount_not_in_evidence"),
    (fee(name="electricity", amount_vnd=3500, mode="fixed", evidence="Điện 3k5/số"), "mode_not_allowed"),
    (fee(name="water", amount_vnd=100000, mode="m3", evidence="nước 100k/người"), "amount_out_of_range"),
    (fee(name="parking", amount_vnd=0, mode="vehicle", included_in_rent=True, evidence="giữ xe 100k/chiếc"),
     "included_not_stated"),
    (fee(name="service", mode="fixed", evidence="Phí dịch vụ 150.000đ/tháng"), "amount_missing"),
])
def test_ungrounded_fees_are_rejected(candidate, reason):
    assert verify(candidate, POST) == reason


class FakeExtractor:
    model = "fake"

    def __init__(self, fees):
        self.fees, self.calls = fees, 0

    def extract(self, text):
        self.calls += 1
        return FeeExtraction(fees=self.fees), 120


def room(fees=()):
    return {"id": "chotot-1", "quote": {"fees": list(fees)}}


def test_enrich_fills_missing_fees_keeps_regex_fee_and_drops_bad_ones():
    regex_fee = {"name": "electricity", "amount_vnd": "3500", "mode": "kwh", "included_in_rent": False,
                 "source": "chotot://ad/1/body#electricity"}
    rooms = [room([regex_fee])]
    extractor = FakeExtractor([
        fee(name="electricity", amount_vnd=9999, mode="kwh", evidence="made up"),  # already known: ignored
        fee(name="water", amount_vnd=100000, mode="person", evidence="nước 100k/người"),
        fee(name="service", amount_vnd=200000, mode="fixed", evidence="Phí dịch vụ 200k"),  # not in post
    ])
    review, stats = enrich(rooms, {"chotot-1": POST}, extractor, cache={})
    fees = {item["name"]: item for item in rooms[0]["quote"]["fees"]}
    assert fees["electricity"] == regex_fee
    assert fees["water"]["source"] == "chotot://ad/1/body#water-llm"
    assert "service" not in fees  # rejected: stays unknown, never 0
    assert stats["accepted"] == {"water": 1} and stats["rejected"] == {"evidence_not_in_post": 1}
    assert [(row["kind"], row["key"]) for row in review] == [("fee", "water")]


def test_enrich_reuses_cache_and_respects_limit():
    extractor = FakeExtractor([])
    cache = {"chotot-1": {"fees": [], "tokens": 50}}
    rooms = [room(), {"id": "chotot-2", "quote": {"fees": []}}, {"id": "chotot-3", "quote": {"fees": []}}]
    texts = {r["id"]: POST for r in rooms}
    _, stats = enrich(rooms, texts, extractor, cache, limit=1)
    assert extractor.calls == 1 and stats["cached"] == 1 and stats["llm_calls"] == 1
    assert "chotot-3" not in cache
    assert stats["budget_exhausted"] is True


# --- FC-05: LLM budget — interleave cities, token ceiling, gated live calls ---

def test_input_estimate_and_yes_gate():
    from data.llm_fees import input_token_estimate, live_call_allowed
    texts = {"a": "x" * 3000, "b": "y" * 300}
    assert input_token_estimate(texts) == 1100  # chars / 3
    assert live_call_allowed(500_000, confirmed=False) is True
    assert live_call_allowed(1_500_000, confirmed=False) is False
    assert live_call_allowed(1_500_000, confirmed=True) is True


def test_budget_order_interleaves_cities_individual_first_newest_first():
    from data.llm_fees import budget_order
    def entry(room_id, city, poster, day):
        return {"id": room_id, "city": city, "quote": {"fees": []},
                "poster_kind": poster, "posted_at": f"2026-10-{day:02d}T00:00:00Z"}
    rooms = [entry(f"hn-{i}", "Hà Nội", "individual", 10 + i) for i in range(2)]
    rooms += [entry(f"sg-{i}", "TP.HCM", "individual", 20 + i) for i in range(3)]
    rooms += [entry("sg-broker", "TP.HCM", "broker", 29)]
    order = budget_order(rooms)
    # Round-robin across the two cities; inside a city individual first (newest
    # first), broker last. Hà Nội sorts before TP.HCM alphabetically.
    assert [item["id"] for item in order] == ["hn-1", "sg-2", "hn-0", "sg-1", "sg-0", "sg-broker"]


def test_enrich_stops_at_token_budget_and_reports_exhaustion():
    class SpendingExtractor(FakeExtractor):
        def extract(self, text):
            _, tokens = super().extract(text)
            return _, 400

    extractor = SpendingExtractor([])
    rooms = [{"id": f"chotot-{i}", "quote": {"fees": []}} for i in range(1, 5)]
    texts = {r["id"]: POST for r in rooms}
    _, stats = enrich(rooms, texts, extractor, cache={}, max_tokens=800)
    # Tokens are only known after a call: the budget stops before the call that
    # would run past it (800 reached → call 3 never happens), the rest wait.
    assert stats["llm_calls"] == 2 and stats["new_tokens"] == 800
    assert stats["budget_exhausted"] is True
    assert stats["tokens"] == 800  # only new-call tokens: nothing else was cached


def test_enrich_within_budget_is_not_flagged():
    extractor = FakeExtractor([])
    rooms = [{"id": "chotot-1", "quote": {"fees": []}}]
    _, stats = enrich(rooms, {"chotot-1": POST}, extractor, cache={}, limit=10, max_tokens=1000)
    assert stats["llm_calls"] == 1 and stats["budget_exhausted"] is False


def test_run_writes_derived_snapshot_and_leaves_source_untouched(tmp_path):
    source = tmp_path / "src"
    (source / "raw").mkdir(parents=True)
    (source / "raw" / "page-0.json").write_text(json.dumps([{"ad_id": 1, "subject": "Phòng", "body": POST}]))
    catalog = {"snapshot_id": "src", "rooms": [room()]}
    (source / "catalog.json").write_text(json.dumps(catalog))
    (source / "manifest.json").write_text(json.dumps({"snapshot_id": "src", "catalog_sha256": "x",
                                                      "summary": {"with_all_required_fees": 0}}))
    extractor = FakeExtractor([fee(name="water", amount_vnd=100000, mode="person", evidence="nước 100k/người")])
    result = run(source, tmp_path / "dst", "dst", extractor, log=lambda *_: None)
    assert result["accepted"] == {"water": 1}
    manifest = json.loads((tmp_path / "dst" / "manifest.json").read_text())
    assert manifest["derived_from"]["snapshot_id"] == "src" and manifest["llm_fees"]["model"] == "fake"
    assert json.loads((source / "catalog.json").read_text()) == catalog
    # A rerun reads the cache instead of calling the model again.
    run(source, tmp_path / "dst", "dst", extractor, log=lambda *_: None)
    assert extractor.calls == 1


# --- LF-03: terms, available_from and amenities, all deterministically verified ---

def test_extractor_version_bumped_for_new_prompt():
    assert EXTRACTOR_VERSION == "2.0"


def test_listing_extraction_keeps_old_alias_and_defaults():
    assert FeeExtraction is ListingExtraction
    extraction = FeeExtraction.model_validate({"fees": []})
    assert extraction.payment_cycle_months is None and extraction.amenities == []


@pytest.mark.parametrize("name, value, evidence", [
    ("payment_cycle_months", 3, "Đóng 3 tháng 1 lần"),
    ("min_lease_months", 6, "Hợp đồng tối thiểu 6 tháng"),
    ("min_lease_months", 12, "hợp đồng 1 năm"),
])
def test_grounded_terms_are_accepted(name, value, evidence):
    assert verify_term(name, value, evidence, TERMS_POST) is None


@pytest.mark.parametrize("name, value, evidence, reason", [
    ("payment_cycle_months", 3, "không có trong tin", "evidence_not_in_post"),
    ("payment_cycle_months", 6, "Đóng 3 tháng 1 lần", "months_not_in_evidence"),
    ("min_lease_months", 6, "Đóng 3 tháng 1 lần", "months_not_in_evidence"),
    # no contract keyword in the evidence → the crawler regex cannot re-read it
    ("min_lease_months", 6, "thuê ít nhất 6 tháng", "months_not_in_evidence"),
])
def test_ungrounded_terms_are_rejected(name, value, evidence, reason):
    assert verify_term(name, value, evidence, TERMS_POST) == reason


def test_grounded_available_from_is_accepted_and_reads_back_iso():
    assert verify_date("1/12", "Trống từ 1/12", TERMS_POST, POSTED_AT) is None
    assert verify_date("1/12/2026", "trống từ ngày 1/12/2026", "tin mới: trống từ ngày 1/12/2026",
                       datetime(2026, 1, 1, tzinfo=timezone.utc)) is None


@pytest.mark.parametrize("candidate, evidence, posted_at, reason", [
    ("1/12", "không có trong tin", POSTED_AT, "evidence_not_in_post"),
    ("1/12", "Trống từ 1/12", None, "posted_time_unknown"),
    ("1/12", "Trống từ 1/12", POSTED_AT, None),
    ("5/12", "Trống từ 1/12", POSTED_AT, "date_not_in_evidence"),
    ("1/12", "Phòng đủ tiện nghi", POSTED_AT, "date_not_in_evidence"),
])
def test_available_from_variants(candidate, evidence, posted_at, reason):
    assert verify_date(candidate, evidence, TERMS_POST, posted_at) == reason


def test_available_from_rejects_invalid_calendar_date():
    # "Trong 32/13" appears verbatim in the post but never forms a valid date → null.
    assert verify_date("32/13", "Trong 32/13", "tin lạ Trong 32/13",
                       POSTED_AT) == "date_not_in_evidence"


def test_available_from_reads_vacant_on_day_evidence_with_crawler_regex():
    # FC-01: verify_date re-reads evidence through AVAILABLE_FROM of the crawler
    # (no hand-copied pattern), so "trống ngày D/M" wording verifies and the
    # stored ISO date comes from the same parser the crawl used.
    from data.crawl_chotot import fold, parse_available_from
    text = "Phòng mới. Trống ngày 5/11, còn 2 phòng."
    assert verify_date("5/11", "Trống ngày 5/11", text, POSTED_AT) is None
    assert parse_available_from(fold(text), POSTED_AT) == "2026-11-05"


@pytest.mark.parametrize("key, value, evidence", [
    ("kitchen", True, "Có bếp"),
    ("wifi", True, "Wifi miễn phí"),
    ("wifi", False, "Không có wifi"),
    # the keyword itself contains the negation: must not fall into the NEGATION trap
    ("no_shared_landlord", True, "Không chung chủ"),
    ("no_shared_landlord", False, "Ở chung chủ cùng gia đình"),
])
def test_grounded_amenities_are_accepted(key, value, evidence):
    assert verify_amenity(key, value, evidence, TERMS_POST) is None


@pytest.mark.parametrize("key, value, evidence, reason", [
    ("kitchen", True, "không có trong tin", "evidence_not_in_post"),
    ("kitchen", False, "Có bếp", "value_not_in_evidence"),
    ("kitchen", True, "Phòng đủ tiện nghi", "value_not_in_evidence"),
    ("elevator", True, "Phòng đủ tiện nghi", "value_not_in_evidence"),
    ("wifi", True, "Không có wifi", "value_not_in_evidence"),
])
def test_ungrounded_amenities_are_rejected(key, value, evidence, reason):
    assert verify_amenity(key, value, evidence, TERMS_POST) == reason


class FakeListingExtractor:
    model = "fake"

    def __init__(self, extraction):
        self.extraction, self.calls = extraction, 0

    def extract(self, text):
        self.calls += 1
        return ListingExtraction.model_validate(self.extraction), 150


def terms_room():
    return {"id": "chotot-9", "posted_at": "2026-10-30T04:00:00Z", "available_from": None,
            "amenities": {"kitchen": True},
            "quote": {"rent_vnd": 3000000, "fees": [], "payment_cycle_months": 3,
                      "min_lease_months": None}}


def test_enrich_fills_only_null_terms_amenities_and_never_overwrites():
    room = terms_room()
    extractor = FakeListingExtractor({
        "fees": [],
        # payment_cycle already 3: a valid proposal is ignored and not counted.
        "payment_cycle_months": 3, "payment_cycle_evidence": "Đóng 3 tháng 1 lần",
        "min_lease_months": 6, "min_lease_evidence": "Hợp đồng tối thiểu 6 tháng",
        "available_from": "1/12", "available_from_evidence": "Trống từ 1/12",
        "amenities": [
            {"key": "wifi", "value": True, "evidence": "Wifi miễn phí"},
            {"key": "kitchen", "value": True, "evidence": "Có bếp"},  # already true: skipped
            {"key": "elevator", "value": True, "evidence": "Có bếp"},  # evidence lacks the keyword
        ]})
    review, stats = enrich([room], {"chotot-9": TERMS_POST}, extractor, cache={})
    assert room["quote"]["payment_cycle_months"] == 3  # regex value stays untouched
    assert room["quote"]["min_lease_months"] == 6
    assert room["available_from"] == "2026-12-01"
    assert room["amenities"]["wifi"] is True and room["amenities"]["kitchen"] is True
    assert "elevator" not in room["amenities"] or room["amenities"]["elevator"] is None
    assert stats["accepted"] == {"term:min_lease_months": 1, "term:available_from": 1, "amenity:wifi": 1}
    assert stats["rejected"] == {"value_not_in_evidence": 1}
    assert stats["rooms_missing_fees"] == 1 and stats["rooms_missing_terms_or_amenities"] == 1
    assert {(row["kind"], row["key"]) for row in review} == {
        ("term", "min_lease_months"), ("term", "available_from"), ("amenity", "wifi")}


def test_enrich_targets_rooms_that_only_need_terms_or_amenities():
    # All fees known but terms/amenities still null: the room must still be processed.
    room = terms_room()
    full_fees = [{"name": name, "amount_vnd": "100000", "mode": "fixed", "included_in_rent": False,
                  "source": f"chotot://ad/9/body#{name}"} for name in
                 ("electricity", "water", "internet", "parking", "service")]
    room["quote"]["fees"] = full_fees
    extractor = FakeListingExtractor({"fees": [], "amenities": [
        {"key": "fridge", "value": True, "evidence": "Có bếp."}]})  # wrong keyword: rejected
    _, stats = enrich([room], {"chotot-9": TERMS_POST}, extractor, cache={})
    assert stats["rooms_missing_fees"] == 0
    assert stats["rooms_missing_terms_or_amenities"] == 1 and stats["llm_calls"] == 1
    assert stats["accepted"] == {} and stats["rejected"] == {"value_not_in_evidence": 1}


def test_run_ignores_cache_from_old_extractor_version(tmp_path):
    source = tmp_path / "src"
    (source / "raw").mkdir(parents=True)
    (source / "raw" / "page-0.json").write_text(json.dumps([{"ad_id": 9, "subject": "Phòng", "body": TERMS_POST}]))
    catalog = {"snapshot_id": "src", "rooms": [terms_room()]}
    (source / "catalog.json").write_text(json.dumps(catalog))
    (source / "manifest.json").write_text(json.dumps({"snapshot_id": "src", "catalog_sha256": "x",
                                                      "summary": {"with_all_required_fees": 0}}))
    target = tmp_path / "dst"
    target.mkdir()
    # A 1.0-format cache entry (no extractor_version): ignored entirely.
    (target / "llm_cache.jsonl").write_text(json.dumps({"room_id": "chotot-9", "fees": [], "tokens": 10}) + "\n")
    extractor = FakeListingExtractor({"fees": [], "min_lease_months": 6,
                                      "min_lease_evidence": "Hợp đồng tối thiểu 6 tháng"})
    result = run(source, target, "dst", extractor, log=lambda *_: None)
    assert extractor.calls == 1  # old cache invalidated: the model is called again
    assert result["cached"] == 0 and result["extractor_version"] == "2.0"
    lines = (target / "llm_cache.jsonl").read_text().splitlines()
    assert json.loads(lines[1])["extractor_version"] == "2.0"
    # A rerun honors the 2.0 cache: no extra call.
    run(source, target, "dst", extractor, log=lambda *_: None)
    assert extractor.calls == 1
