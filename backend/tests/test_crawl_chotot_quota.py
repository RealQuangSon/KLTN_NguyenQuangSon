"""FC-02/FC-03: quota crawl (individual first, broker top-up) and the three
filter layers with balanced per-city selection.

All HTTP runs on httpx.MockTransport; filter/selection tests are pure. No
network, no real crawl (G5): the real run belongs to the user.
"""
import json
import time

import httpx
import pytest

from data.crawl_chotot import (CRAWLER_VERSION, CrawlTimeout, REGION_HANOI, REGION_HCM,
                               CATEGORY_APARTMENT, CATEGORY_ROOM, Target, crawl, crawl_catalog,
                               filter_rooms, multi_unit_reason, select_catalog, targets_for)


# Six genuinely different default titles: near-identical or merely re-templated
# titles would legitimately collapse in filter layer 2 (ratio ≥ 0.8).
_TITLES = ("Phòng trọ Quận 7 giá rẻ mới xây",
           "Cho thuê studio nội thất đầy đủ Bình Thạnh",
           "Phòng có gác rộng thoáng mát Gò Vấp",
           "Phòng riêng WC riêng lầu 2 Thủ Đức",
           "Căn hộ mini cửa sổ lớn gần chợ Quận 12",
           "Phòng trọ mặt tiền yên tĩnh Tân Bình")


def make_room(ad_id, city="TP.HCM", room_type="room", poster="individual",
              title=None,  # distinct by default: identical titles would hit filter layer 2
              price=3_000_000, size=20, coords=(10.750, 106.700), posted="2026-10-30T04:00:00+00:00",
              description=None):
    latitude, longitude = coords
    return {
        "id": f"chotot-{ad_id}", "revision": 1,
        "title": title or _TITLES[ad_id % 6],
        "city": city, "area": "Quận 7",
        "room_type": room_type, "bedrooms": None, "capacity": None, "area_m2": float(size),
        "published": True, "available": True, "amenities": {},
        "latitude": latitude, "longitude": longitude, "location_accuracy": "approximate",
        "uncertainty_m": 300.0,
        "quote": {"rent_vnd": price, "deposit_vnd": None, "advance_months": None,
                  "payment_cycle_months": None, "min_lease_months": None, "fees": [], "one_time_vnd": None},
        "source": f"https://www.chotot.com/{ad_id}.htm", "synthetic": False, "features_text": None,
        "landlord_id": "owner-a", "description": description, "posted_at": posted,
        "poster_kind": poster, "ward": None, "ward_2025": None, "street": None, "available_from": None,
    }


def quota_handler(inventory, seen):
    """Serve pages from inventory[(region, category, f)] and record request params."""
    def handler(request):
        params = dict(request.url.params)
        seen.append(params)
        key = (int(params["region_v2"]), int(params["cg"]), params["f"])
        offset, limit = int(params["o"]), int(params["limit"])
        ads = inventory.get(key, [])
        return httpx.Response(200, json={"total": len(ads), "ads": ads[offset:offset + limit]})
    return handler


def run_crawl(inventory, targets, tmp_path):
    seen: list[dict] = []
    real_client = httpx.Client

    def fake_client(**kwargs):
        return real_client(transport=httpx.MockTransport(quota_handler(inventory, seen)), **kwargs)

    original = httpx.Client
    httpx.Client = staticmethod(fake_client)
    try:
        rooms, stats = crawl(targets, 0.0, tmp_path / "raw", log=lambda *_: None)
    finally:
        httpx.Client = original
    return rooms, stats, seen


def base_ad(ad_id, **overrides):
    ad = {"ad_id": ad_id, "list_id": 87761600 + ad_id, "list_time": 1793332800000 + ad_id,
          "subject": f"Phòng trọ Quận 7 số {ad_id}", "body": "Phòng mới.", "price": 3_000_000,
          "size": 20, "region_name": "TP Hồ Chí Minh", "area_name": "Quận 7", "company_ad": False}
    ad.update(overrides)
    return ad


# --- FC-02 --------------------------------------------------------------------

def test_targets_have_headroom_and_individual_first():
    assert CRAWLER_VERSION == "2.3"
    targets = targets_for(2500)
    assert [(t.region, t.category, t.max_ads, t.poster) for t in targets] == [
        (REGION_HCM, CATEGORY_ROOM, 1625, "p"), (REGION_HCM, CATEGORY_APARTMENT, 1625, "p"),
        (REGION_HANOI, CATEGORY_ROOM, 1625, "p"), (REGION_HANOI, CATEGORY_APARTMENT, 1625, "p")]


def test_fetch_sends_f_and_poster_kind_follows_source_filter(tmp_path):
    inventory = {(REGION_HCM, CATEGORY_ROOM, "p"): [base_ad(1), base_ad(2, company_ad=True),
                                                    base_ad(3, company_ad=None)],
                 (REGION_HCM, CATEGORY_ROOM, "c"): [base_ad(9, company_ad=False)]}
    rooms, stats, seen = run_crawl(inventory, (Target(REGION_HCM, CATEGORY_ROOM, 3, "p"),
                                              Target(REGION_HCM, CATEGORY_ROOM, 2, "c")), tmp_path)
    by_poster = {room["id"]: room["poster_kind"] for room in rooms}
    # G1: the source filter decides, never the ad content.
    assert by_poster == {"chotot-1": "individual", "chotot-2": "individual", "chotot-3": "individual",
                         "chotot-9": "broker"}
    f_values = {params["f"] for params in seen}
    assert f_values == {"p", "c"}
    assert [row["poster"] for row in stats["by_target"]] == ["p", "c"]
    assert [row["fetched"] for row in stats["by_target"]] == [3, 1]


def test_broker_topup_only_when_individual_short_and_capped_by_13x(tmp_path):
    inventory = {(REGION_HCM, CATEGORY_ROOM, "p"): [base_ad(index) for index in range(4)],
                 (REGION_HCM, CATEGORY_ROOM, "c"): [base_ad(100 + index) for index in range(12)]}
    rooms, stats, seen = run_crawl(inventory, (Target(REGION_HCM, CATEGORY_ROOM, 10, "p"),), tmp_path)
    # f=p stopped at its supply (4 < 10); the top-up f=c target is ceil(6*1.3)=8.
    assert [row["poster"] for row in stats["by_target"]] == ["p", "c"]
    assert [row["fetched"] for row in stats["by_target"]] == [4, 8]
    assert [row["available_total"] for row in stats["by_target"]] == [4, 12]
    assert len({room["id"] for room in rooms}) == 12
    assert [params["f"] for params in seen] == ["p", "c"]


def test_enough_individual_means_no_broker_call(tmp_path):
    inventory = {(REGION_HCM, CATEGORY_ROOM, "p"): [base_ad(index) for index in range(5)]}
    rooms, stats, seen = run_crawl(inventory, (Target(REGION_HCM, CATEGORY_ROOM, 5, "p"),), tmp_path)
    assert [row["poster"] for row in stats["by_target"]] == ["p"]
    assert {params["f"] for params in seen} == {"p"}
    assert stats["kept"] == 5


def test_deadline_raises_and_writes_no_snapshot(tmp_path):
    with pytest.raises(CrawlTimeout):
        _crawl_past_deadline(tmp_path)
    # C2: no snapshot files may exist after a timeout.
    assert not (tmp_path / "catalog.json").exists() and not (tmp_path / "manifest.json").exists()


def _crawl_past_deadline(tmp_path):
    seen: list[dict] = []
    real_client = httpx.Client

    def fake_client(**kwargs):
        return real_client(transport=httpx.MockTransport(quota_handler({}, seen)), **kwargs)

    original = httpx.Client
    httpx.Client = staticmethod(fake_client)
    try:
        crawl((Target(REGION_HCM, CATEGORY_ROOM, 10, "p"),), 0.0, tmp_path / "raw",
              log=lambda *_: None, deadline=time.monotonic() - 1)
    finally:
        httpx.Client = original


def test_makeup_rounds_max_two_and_target_the_short_combo(tmp_path):
    calls: list[list[Target]] = []

    def fake_fetch(targets, sleep_s, raw_dir, log=print, deadline=None):
        calls.append(list(targets))
        base = 1000 * len(calls)
        # Own coordinates per round: equal titles across rounds must not meet in
        # one layer-2 coordinate group.
        rooms = [make_room(base + index, coords=(10.7 + len(calls) * 0.1, 106.7))
                 for index in range(2)]
        return rooms, {"pages": 1, "ads_seen": 2, "skipped": {}, "by_target": []}

    selected, stats = crawl_catalog(10, 0.0, tmp_path / "raw", log=lambda *_: None,
                                    fetch=fake_fetch)
    # Initial pass + at most two f=c makeup rounds, whatever the shortage.
    assert len(calls) == 3
    assert all(len(targets) == 1 and targets[0].poster == "c"
               and (targets[0].region, targets[0].category) == (REGION_HCM, CATEGORY_ROOM)
               for targets in calls[1:])
    assert stats["selection"]["pre_balance"] == {"TP.HCM:1050": 6}
    # Quota 5: the six pooled rooms are trimmed deterministically (oldest ad_id last).
    assert [room["id"] for room in selected] == ["chotot-1000", "chotot-1001",
                                                 "chotot-2000", "chotot-2001", "chotot-3000"]


def test_makeup_rounds_reseving_same_ads_never_duplicates_pool(tmp_path):
    calls: list[list[Target]] = []

    def fake_fetch(targets, sleep_s, raw_dir, log=print, deadline=None):
        calls.append(list(targets))
        # The API keeps serving the same two broker ads on every round (f=c).
        rooms = [make_room(500 + index, poster="broker", coords=(10.7, 106.7))
                 for index in range(2)]
        return rooms, {"pages": 1, "ads_seen": 2, "skipped": {}, "by_target": [
            {"region": REGION_HCM, "category": CATEGORY_ROOM, "poster": "c",
             "available_total": 2, "fetched": 2, "kept": 2}]}

    selected, stats = crawl_catalog(10, 0.0, tmp_path / "raw", log=lambda *_: None,
                                    fetch=fake_fetch)
    assert len(calls) == 3  # still short, still capped at two makeup rounds
    ids = [room["id"] for room in selected]
    assert len(ids) == len(set(ids)) == 2  # pool dedup keeps exactly one copy
    assert stats["selection"]["pre_balance"] == {"TP.HCM:1050": 2}
    # FC-02.5: by_target rows carry kept_after_filters/selected, mapped from the
    # "p"/"c" filter code onto poster_kind.
    row = stats["by_target"][0]
    assert row["kept_after_filters"] == 2 and row["selected"] == 2


def test_makeup_disabled_when_not_needed(tmp_path):
    calls: list[list[Target]] = []

    def fake_fetch(targets, sleep_s, raw_dir, log=print, deadline=None):
        calls.append(list(targets))
        # Per-room coordinates so the twelve rooms never share a layer-2 group.
        rooms = [make_room(100 + index, city="Hà Nội", coords=(21.0 + index * 0.001, 105.8))
                 for index in range(6)]
        rooms += [make_room(200 + index, coords=(10.7 + index * 0.001, 106.7)) for index in range(6)]
        return rooms, {"pages": 1, "ads_seen": len(rooms), "skipped": {}, "by_target": []}

    crawl_catalog(12, 0.0, tmp_path / "raw", log=lambda *_: None, fetch=fake_fetch)
    assert len(calls) == 1  # both cities reach the quota: no f=c round


# --- FC-03 --------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Chỉ từ 3 triệu/tháng", "Giá từ 3.5tr", "Giá chỉ từ 2.5 triệu", "Còn nhiều phòng",
    "Còn 2 phòng trống", "Giá 3-5 triệu", "2tr-3,5tr có thương lượng", "Giá từ 2,5tr còn phòng",
])
def test_multi_unit_posts_are_filtered(text):
    assert multi_unit_reason(text) == "multi_unit_or_price_range"


@pytest.mark.parametrize("text", [
    "Giá từ chủ nhà, xin liên hệ", "Giá từ 1/12 tăng còn chỗ", "Phòng đẹp giá 3 triệu thương lượng",
    "Còn phòng 20m2 full nội thất", "Phòng trống từ 1/12", "Chỉ cách trường 500m",
    "Giá 3,5 triệu đóng 1 tháng 1 lần", "Giá từ 1/12/2026 áp dụng",
])
def test_normal_posts_are_not_filtered(text):
    assert multi_unit_reason(text) is None


def test_layer2_near_duplicate_keeps_best_by_g3():
    twin = dict(coords=(10.750, 106.700), price=3_000_000, size=20)
    individual_older = make_room(1, title="Phòng trọ Quận 7 giá rẻ", poster="individual",
                                 posted="2026-10-25T04:00:00+00:00", **twin)
    broker_newer = make_room(2, title="phong tro quan 7 gia re", poster="broker", **twin)
    different_title = make_room(3, title="Căn hộ studio có thang máy", poster="broker", **twin)
    no_coords = make_room(4, title="Phòng trọ Quận 7 giá rẻ", poster="individual", coords=(None, None))
    kept, skipped = filter_rooms([broker_newer, individual_older, different_title, no_coords])
    ids = {room["id"] for room in kept}
    # G3: individual wins over newer broker; the distinct title and the
    # coordinate-less room survive (layer 2 skips rooms without coords).
    assert ids == {"chotot-1", "chotot-3", "chotot-4"}
    assert skipped["near_duplicate"] == {"TP.HCM|broker": 1}


def test_selection_is_deterministic_individual_first_then_newest():
    rooms = [make_room(5, posted="2026-10-20T00:00:00+00:00"),
             make_room(1, posted="2026-10-28T00:00:00+00:00"),
             make_room(3, posted="2026-10-28T00:00:00+00:00"),
             make_room(2, poster="broker", posted="2026-10-30T00:00:00+00:00"),
             make_room(16, poster="broker", posted="2026-10-29T00:00:00+00:00")]
    first, first_stats = select_catalog(rooms, 4)  # quota 2 per combo
    second, _ = select_catalog(list(reversed(rooms)), 4)
    assert [room["id"] for room in first] == [room["id"] for room in second] == ["chotot-1", "chotot-3"]
    assert first_stats["selected"] == {"TP.HCM:1050": 2}
    assert first_stats["poster_split"] == {"TP.HCM:1050:individual": 2}


def test_g6_lowers_both_cities_together():
    rooms = [make_room(index, coords=(10.7 + index * 0.001, 106.7)) for index in range(6)]
    rooms += [make_room(100 + index, city="Hà Nội", coords=(21.0 + index * 0.001, 105.8))
              for index in range(2)]  # Hanoi: only 2
    selected, stats = select_catalog(rooms, 10)  # quota 5 per combo, Hanoi can only give 2
    by_city = {room["city"] for room in selected}
    counts = {city: sum(1 for room in selected if room["city"] == city) for city in by_city}
    assert counts == {"TP.HCM": 2, "Hà Nội": 2}
    assert stats["final_per_city"] == 2
    assert stats["selected"] == {"TP.HCM:1050": 2, "Hà Nội:1050": 2}


def test_account_id_never_reaches_raw_or_catalog(tmp_path):
    inventory = {(REGION_HCM, CATEGORY_ROOM, "p"): [base_ad(index, account_id=777) for index in range(5)]}
    rooms, stats, _ = run_crawl(inventory, (Target(REGION_HCM, CATEGORY_ROOM, 5, "p"),), tmp_path)
    selected, _ = select_catalog(rooms, 10)
    # G4: account_id lives only in the in-memory dedup key, never on disk.
    assert json.dumps(selected).find("777") == -1
    assert json.dumps(selected).find("account_id") == -1
    for page in sorted((tmp_path / "raw").glob("page-*.json")):
        assert "account_id" not in page.read_text(encoding="utf-8")
