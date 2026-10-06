import pytest

from backend.app.catalog import Catalog
from backend.app.interpreter import DemoInterpreter
from backend.app.locations import canonical_area, canonical_city, find_area, find_city
from backend.app.models import Profile, Scenario


@pytest.mark.parametrize("text, city, area", [
    ("Tìm phòng TP.HCM Quận Bình Thạnh cho 1 người", "TP.HCM", "Quận Bình Thạnh"),
    ("Tìm phòng Sài Gòn Q7 1 người", "TP.HCM", "Quận 7"),
    ("tìm trọ q.10 hcm", "TP.HCM", "Quận 10"),
    ("Tìm trọ Hà Nội Cầu Giấy cho 2 người", "Hà Nội", "Quận Cầu Giấy"),
    ("tim tro hanoi dong da", "Hà Nội", "Quận Đống Đa"),
    ("Căn hộ Nam Từ Liêm, HN", "Hà Nội", "Quận Nam Từ Liêm"),
    # City stays unknown when not stated; it is asked, never defaulted.
    ("Tìm phòng Quận 7 cho 1 người", None, "Quận 7"),
    ("Tìm phòng gần trường, tầm 3 triệu", None, None),
])
def test_demo_interpreter_reads_city_and_area_aliases(text, city, area):
    extraction = DemoInterpreter().extract(text)
    assert (extraction.city, extraction.area) == (city, area)


def test_numbered_districts_do_not_shadow_each_other():
    assert find_area("quan 1") == "Quận 1"
    assert find_area("quận 10") == "Quận 10"
    assert find_area("q12 gần chợ") == "Quận 12"


def test_area_is_scoped_by_city_and_both_cities_named_is_ambiguous():
    assert find_area("Bình Thạnh", "Hà Nội") is None
    assert find_city("so sánh Hà Nội với Sài Gòn") is None


def test_unknown_names_pass_through_unchanged():
    assert canonical_city("Đà Nẵng") == "Đà Nẵng"
    assert canonical_area("Hải Châu", "Đà Nẵng") == "Hải Châu"


def test_hard_filter_accepts_alias_spellings():
    catalog = Catalog()
    room = catalog.rooms()[0]
    base = dict(room_type=room.room_type, max_monthly_cost_vnd=50_000_000, scenario=Scenario(people=1))
    canonical, _ = catalog.eligible_candidates(Profile(city=room.city, area=room.area, **base))
    alias = room.area.replace("Quận ", "Q")
    aliased, _ = catalog.eligible_candidates(Profile(city="Sài Gòn" if room.city == "TP.HCM" else room.city,
                                                     area=alias, **base))
    assert canonical and [c.room_id for c in aliased] == [c.room_id for c in canonical]


def test_frontend_location_list_matches_backend_dictionary():
    import re
    from pathlib import Path
    from backend.app.locations import AREA_ALIASES
    source = (Path(__file__).resolve().parents[2] / "frontend/src/locations.ts").read_text(encoding="utf-8")
    block = source.split("export const cityAreas", 1)[1].split("};", 1)[0]
    parsed, city = {}, None
    for line in block.splitlines():
        if match := re.match(r'\s*"(.+)": \[', line):
            city = match[1]
            parsed[city] = []
        elif match := re.match(r'\s*"(.+)",', line):
            parsed[city].append(match[1])
    assert parsed == {city: list(areas) for city, areas in AREA_ALIASES.items()}
