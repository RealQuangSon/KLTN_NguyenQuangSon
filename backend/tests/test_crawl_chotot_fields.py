"""LF-02: crawler 2.2 maps the new listing fields from Chợ Tốt ads.

All mapping runs on synthetic ad dicts (to_room is pure) plus one crawl pass
over httpx.MockTransport — no network. Unknown values stay null; the raw
snapshot never contains seller or media fields (C1/F3).
"""
import json

import httpx
import pytest

from data.crawl_chotot import (CRAWLER_VERSION, KEYWORD_AMENITIES, RAW_ALLOWLIST, Target, REGION_HCM,
                               CATEGORY_ROOM, crawl, detect_amenities, extract_terms, strip_raw, to_room)

POSTED_AT = "2026-10-30T04:00:00Z"  # 11:00 Vietnam time, still 30/10
LIST_TIME_MS = 1793332800000  # = POSTED_AT, epoch milliseconds


def base_ad(**overrides):
    ad = {
        "ad_id": 123, "list_id": 87761600, "list_time": LIST_TIME_MS,
        "subject": "Phòng trọ Quận 7 có bếp",
        "body": "Phòng mới. Điện 3k5/số. Đóng 3 tháng 1 lần. Có bếp, không chung chủ. Trống từ 1/12.",
        "price": 3_000_000, "size": 20, "region_name": "TP Hồ Chí Minh", "area_name": "Quận 7",
        "ward_name": "Phường Tân Kiểng", "ward_name_v3": "Phường Tân Hưng", "street_name": "Đường Bà Cut",
        "company_ad": True, "furnishing_rent": None,
    }
    ad.update(overrides)
    return ad


def test_crawler_version_bumped_and_allowlist_extends_facts():
    assert CRAWLER_VERSION == "2.3"  # FC-02: quota crawl with poster source filter
    for key in ("ward_name_v3", "region_name_v3", "company_ad"):
        assert key in RAW_ALLOWLIST
    # Verified 2026-10-31 on real samples: no structured amenities → not allowlisted.
    for key in ("params", "ad_features", "pty_characteristics"):
        assert key not in RAW_ALLOWLIST


def test_to_room_maps_all_new_listing_fields():
    room, reason, _ = to_room(base_ad())
    assert reason is None
    assert room["posted_at"] == POSTED_AT
    assert room["poster_kind"] == "broker"
    assert room["ward"] == "Phường Tân Kiểng"
    assert room["ward_2025"] == "Phường Tân Hưng"
    assert room["street"] == "Đường Bà Cut"
    assert room["description"].startswith("Phòng mới.")
    assert room["available_from"] == "2026-12-01"
    assert room["quote"]["payment_cycle_months"] == 3
    # "Có bếp, không chung chủ" via keywords; furnishing not stated → furniture null.
    assert room["amenities"]["kitchen"] is True
    assert room["amenities"]["no_shared_landlord"] is True
    assert room["amenities"]["furniture"] is None


def test_company_ad_absent_or_false_stays_null():
    for company_ad in (None, False, "missing"):
        ad = base_ad()
        if company_ad != "missing":
            ad["company_ad"] = company_ad
        else:
            ad.pop("company_ad")
        room, _, _ = to_room(ad)
        assert room["poster_kind"] is None


def test_description_is_masked_then_truncated():
    long_body = "Liên hệ 0901234567 hoặc email abc@gmail.com. " + "Nội dung dài. " * 400
    room, _, _ = to_room(base_ad(body=long_body))
    assert "0901234567" not in room["description"] and "abc@gmail.com" not in room["description"]
    assert "[SĐT đã che]" in room["description"] and "[email đã che]" in room["description"]
    assert len(room["description"]) == 4000
    empty, _, _ = to_room(base_ad(body=""))
    assert empty["description"] is None


def test_furnishing_code_overrides_keywords_only_when_present():
    # Verified labels: 1 = "Nội thất cao cấp", 2 = "Nội thất đầy đủ", 3 = "Nhà trống".
    for code, expected in ((1, True), (2, True), (3, False)):
        room, _, _ = to_room(base_ad(furnishing_rent=code))
        assert room["amenities"]["furniture"] is expected
    room, _, _ = to_room(base_ad(furnishing_rent=3, body="Nội thất đầy đủ tiện nghi."))
    assert room["amenities"]["furniture"] is False  # structured code beats keywords
    room, _, _ = to_room(base_ad(body="Full nội thất."))
    assert room["amenities"]["furniture"] is True  # no code → keywords decide


def test_raw_never_keeps_seller_or_media_fields():
    ad = base_ad(account_name="nguoi_dang", account_id=999, full_name="Nguyễn Văn A",
                 seller_info={"rating": 5}, shop_info={"name": "shop"}, streetnumber_display="12/3",
                 image={"url": "x"}, video={"url": "y"})
    raw = strip_raw(ad)
    assert all(key not in raw for key in ("account_name", "account_id", "full_name", "seller_info",
                                          "shop_info", "streetnumber_display", "image", "video"))
    assert raw["ward_name_v3"] == "Phường Tân Hưng" and raw["company_ad"] is True


@pytest.mark.parametrize("text, amenity, expected", [
    ("Cho nau an nhanh gon, bep ro rieng", "kitchen", True),
    ("Khong cho nau an", "kitchen", False),
    ("Wifi mien phi, mang dut doi", "wifi", True),
    ("Khong co wifi", "wifi", False),
    ("Co thang may gan moi", "elevator", True),
    ("Khong co thang may", "elevator", False),
    ("Bao ve 24/24, khu an ninh 24/7", "security_24h", True),
    ("Khong bao ve 24", "security_24h", False),
    ("Co camera an ninh", "camera", True),
    ("Khong camera", "camera", False),
    ("Nha co gac lung thoang", "loft", True),
    ("Khong co gac lung", "loft", False),
    ("Gio giac tu do, ra vao ban dem", "flexible_hours", True),
    ("Khong o chung chu, tu do ra vao", "no_shared_landlord", True),
    ("Ko chung chu", "no_shared_landlord", True),
    ("Khong o chung chu", "no_shared_landlord", True),
    ("Chung chu cung gia dinh chu nha", "no_shared_landlord", False),
    ("Co nong lanh ca nam", "water_heater", True),
    ("Khong co nong lanh", "water_heater", False),
    ("Co tu lanh rong", "fridge", True),
    ("Khong co tu lanh", "fridge", False),
])
def test_new_amenity_keywords_positive_and_negative(text, amenity, expected):
    assert detect_amenities(text)[amenity] is expected


def test_unmentioned_amenities_stay_null():
    detected = detect_amenities("Phòng sạch đẹp, giá tốt gần chợ.")
    for key in ("kitchen", "wifi", "elevator", "security_24h", "camera", "loft",
                "flexible_hours", "no_shared_landlord", "water_heater", "fridge"):
        assert detected[key] is None


@pytest.mark.parametrize("text, months", [
    ("Dong tien 3 thang 1 lan", 3),
    ("Thanh toan 3 thang/lan", 3),
    ("Tra 6 thang mot lan", 6),
    ("3 thang dong 1 lan", 3),
    ("Dong 3 thang", None),          # thiếu "lần" → mơ hồ → null
    ("Tra 13 thang 1 lan", None),    # outside 1-12 → null
])
def test_payment_cycle_regex(text, months):
    assert extract_terms(text, None)["payment_cycle_months"] == months


@pytest.mark.parametrize("text, months", [
    ("Hop dong toi thieu 6 thang", 6),
    ("HD it nhat 6 thang", 6),
    ("Hop dong 1 nam", 12),
    ("hop dong 2 nam", 24),
    ("Thue toi thieu 6 thang", None),   # không nhắc hợp đồng → null
    ("Hop dong 100 thang", None),       # outside 1-60 → null
])
def test_min_lease_regex(text, months):
    assert extract_terms(text, None)["min_lease_months"] == months


def test_available_from_variants():
    from datetime import datetime, timezone
    posted = datetime.fromisoformat(POSTED_AT)
    assert extract_terms("Trong tu 1/12 nhan phong", posted)["available_from"] == "2026-12-01"
    # A vacancy date more than six months before the posting day means next year.
    assert extract_terms("Trong tu 1/3", posted)["available_from"] == "2027-03-01"
    assert extract_terms("Trong ngay", posted)["available_from"] == "2026-10-30"
    assert extract_terms("Vao o ngay", posted)["available_from"] == "2026-10-30"
    assert extract_terms("Trong 32/13", posted)["available_from"] is None
    assert extract_terms("Trong tu 1/12", None)["available_from"] is None


def test_available_from_reads_vacant_on_day_phrasing():
    # FC-01 bug: "trống" folds to "trong", so "trống ngày D/M" is a vacancy date;
    # it must not fall through to available-now (the posting day).
    from datetime import datetime, timezone
    posted = datetime.fromisoformat(POSTED_AT)
    assert extract_terms("Trống ngày 5/11", posted)["available_from"] == "2026-11-05"
    assert extract_terms("Trống từ ngày 5/11", posted)["available_from"] == "2026-11-05"
    assert extract_terms("Trống ngay", posted)["available_from"] == "2026-10-30"
    assert extract_terms("Vào ở ngay", posted)["available_from"] == "2026-10-30"
    # Available-now must not swallow a concrete day or an unresolvable "mai".
    assert extract_terms("Trống ngay 5/11", posted)["available_from"] == "2026-11-05"
    assert extract_terms("Trống ngày mai", posted)["available_from"] is None
    assert extract_terms("Vào ở ngay mai", posted)["available_from"] is None


def test_available_from_past_dates_follow_90day_sixmonth_rule():
    # FC-01 bug: "trống từ 15/10" on a 31/10 post is vacant-now, not 15/10/2027.
    from datetime import datetime, timezone
    posted = datetime.fromisoformat(POSTED_AT)  # 2026-10-30
    # ≤ 90 days back: the room is already vacant → the posting day.
    assert extract_terms("Trống từ 15/10", posted)["available_from"] == "2026-10-30"
    assert extract_terms("Trống từ 1/8", posted)["available_from"] == "2026-10-30"  # exactly 90 days
    # Between 90 days and six months back: ambiguous → null, never guessed.
    assert extract_terms("Trống từ 31/7", posted)["available_from"] is None
    assert extract_terms("Trống từ 30/4", posted)["available_from"] is None  # exactly six months
    # More than six months back: the poster means next year.
    assert extract_terms("Trống từ 29/4", posted)["available_from"] == "2027-04-29"
    # An explicit year in the text is always honored as written.
    assert extract_terms("Trống từ 15/10/2027", posted)["available_from"] == "2027-10-15"
    # Cross-year: a 20/12 post advertising 5/1 means the coming January.
    posted_dec = datetime(2026, 12, 20, 4, 0, tzinfo=timezone.utc)
    assert extract_terms("Trống từ 5/1", posted_dec)["available_from"] == "2027-01-05"


@pytest.mark.parametrize("keyword", KEYWORD_AMENITIES["loft"])
def test_demo_interpreter_loft_keywords_match_crawler(keyword):
    # FC-01: "cần phòng có gác" must map to the loft preference. Two keyword
    # tables on purpose (backend/app must not import data/ tooling); this pins
    # the interpreter's loft definition to the crawler's KEYWORD_AMENITIES.
    from backend.app.interpreter import DemoInterpreter
    extraction = DemoInterpreter().extract(f"Tôi cần phòng {keyword} gần trường")
    assert "loft" in extraction.preferences
    assert "loft" not in extraction.remove_preferences


def test_crawl_pass_through_mock_transport_keeps_new_fields(tmp_path, monkeypatch):
    ads = [base_ad(), base_ad(ad_id=456, list_id=87761700, subject="Phòng trọ Quận 7 ban cong",
                              body="Co ban cong, wifi mien phi. Hop dong toi thieu 6 thang.",
                              company_ad=False)]
    seen_urls = []

    def handler(request):
        seen_urls.append(str(request.url))
        return httpx.Response(200, json={"total": 2, "ads": [strip_raw(ad) for ad in ads]})

    real_client = httpx.Client

    def fake_client(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("data.crawl_chotot.httpx.Client", staticmethod(fake_client))
    rooms, stats = crawl((Target(REGION_HCM, CATEGORY_ROOM, 2),), 0.0, tmp_path / "raw", log=lambda *_: None)
    assert stats["kept"] == 2 and len(seen_urls) == 1
    assert all(room["id"].startswith("chotot-") for room in rooms)
    by_id = {room["id"]: room for room in rooms}
    assert by_id["chotot-123"]["posted_at"] == POSTED_AT
    # G1 (FC-02): poster_kind comes from the source filter (f=p here), never from
    # the ad content, so company_ad no longer decides it.
    assert by_id["chotot-123"]["poster_kind"] == "individual"
    assert by_id["chotot-456"]["poster_kind"] == "individual"
    assert by_id["chotot-456"]["quote"]["min_lease_months"] == 6
    assert by_id["chotot-456"]["amenities"]["balcony"] is True
    raw_page = json.loads((tmp_path / "raw" / "page-13000-1050-p-000.json").read_text(encoding="utf-8"))
    assert raw_page[0]["ward_name_v3"] == "Phường Tân Hưng"
    assert all("account_id" not in ad and "full_name" not in ad for ad in raw_page)
