from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from backend.app.models import Extraction, Profile, Room

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261001
SEED_V2 = 20261005
OBSERVED_AT = "2026-10-01T00:00:00+07:00"
DATASET_ID = "homematch-synthetic-v2"
NOTICE = "Hoàn toàn giả lập; không phải phòng có thật hoặc biểu giá thị trường."
AREAS = ["Quận 7", "Quận 1", "Quận 3", "Quận 10", "Quận Bình Thạnh"]
CENTERS = [(10.735, 106.721), (10.775, 106.700), (10.785, 106.685),
           (10.773, 106.668), (10.803, 106.711)]
V1_ROOMS = 80
V2_ROOMS = 220
HCM_V2_COUNT = 40
HCM_V2_AREAS = ["Quận Gò Vấp", "TP. Thủ Đức", "Quận 7", "Quận Bình Thạnh"]
HCM_V2_CENTERS = [(10.838, 106.665), (10.850, 106.772), (10.735, 106.721), (10.803, 106.711)]
HANOI_AREAS = ["Quận Cầu Giấy", "Quận Đống Đa", "Quận Hai Bà Trưng", "Quận Thanh Xuân",
               "Quận Nam Từ Liêm", "Quận Hoàng Mai"]
HANOI_CENTERS = [(21.033, 105.795), (21.018, 105.829), (21.006, 105.858), (20.994, 105.814),
                 (21.012, 105.765), (20.975, 105.863)]
# Synthetic rent bands per type; they make budget cases meaningful, they are not market prices.
RENTS = {"room": [2_200_000, 2_600_000, 3_000_000, 3_500_000, 4_000_000, 4_800_000],
         "studio": [4_200_000, 5_000_000, 5_800_000, 6_500_000, 7_500_000, 8_500_000],
         "apartment-1": [7_500_000, 8_500_000, 9_500_000, 11_000_000, 13_000_000],
         "apartment-2": [10_500_000, 12_000_000, 14_000_000, 16_500_000, 19_000_000]}
SIZES = {"room": [15, 18, 20, 24, 28], "studio": [25, 28, 32, 36, 40],
         "apartment-1": [40, 45, 50, 55], "apartment-2": [60, 65, 70, 78]}
CAPACITY = {"room": [1, 2, 3], "studio": [1, 2], "apartment-1": [1, 2, 3], "apartment-2": [2, 3, 4]}
SERVICE = {"room": [50_000, 100_000], "studio": [150_000, 250_000],
           "apartment-1": [300_000, 500_000], "apartment-2": [500_000, 800_000]}
TYPE_LABEL = {"room": "Phòng", "studio": "Studio", "apartment-1": "Căn hộ 1PN", "apartment-2": "Căn hộ 2PN"}
FEATURES = [
    "View thành phố từ tầng cao.", "Nhìn ra hồ, thoáng gió.", "Nhiều ánh sáng tự nhiên buổi sáng.",
    "Gần công viên, tiện đi bộ.", "Hẻm yên tĩnh, ít xe qua lại.", "Gần chợ và siêu thị.",
    "Gần trạm xe buýt.", "Tòa nhà có thang máy và bảo vệ.",
]
# Synthetic landlords: one trial account per city (owner2 = TP.HCM,
# owner1 = Hà Nội) publishes the whole city portfolio.
LANDLORD_RULES = {
    "owner2": "Giờ giấc tự do, cổng khóa lúc 23:30 (có vân tay). Điện tính theo công tơ riêng, nước theo người. "
               "Gửi xe máy trong nhà để xe tầng trệt, mỗi phòng 1 xe miễn phí. Không nấu ăn bằng than.",
    "owner1": "Tòa nhà có bảo vệ 24/7, ra vào bằng thẻ từ. Điện tính theo giá nhà nước bậc thang quy đổi, "
               "nước theo m³. Phí dịch vụ gồm vệ sinh hành lang và thang máy. Khách ở lại qua đêm cần đăng ký.",
}
AMENITIES = ["window", "quiet", "parking", "private_bathroom", "air_conditioning",
             "washing_machine", "balcony", "furniture", "pets_allowed"]
DESCRIPTIONS = [
    "Phòng có cửa sổ đón nắng, phù hợp người thích ánh sáng tự nhiên.",
    "Phòng yên tĩnh trong khu dân cư, thuận tiện đọc sách và học tại nhà.",
    "Phòng có chỗ gửi xe và lối vào riêng, thuận tiện sinh hoạt.",
    "Phòng có vệ sinh riêng, ưu tiên không gian sinh hoạt cá nhân.",
    "Phòng có máy lạnh, phù hợp người cần không gian mát để làm việc.",
    "Phòng có máy giặt dùng chung hoặc riêng, tiện giặt đồ định kỳ.",
    "Phòng có ban công để phơi đồ và có không gian ngoài trời riêng.",
    "Phòng có nội thất cơ bản, dọn vào ở được ngay.",
    "Khu trọ cho phép nuôi thú cưng nhỏ.",
    "Phòng đơn giản, tiện ích cơ bản, phù hợp người ít yêu cầu nội thất.",
]


def dump_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fee(name: str, amount: int | str | None, mode: str = "fixed", included: bool = False) -> dict:
    return {"name": name, "amount_vnd": amount, "mode": mode,
            "included_in_rent": included, "source": f"synthetic://fees/{name}"}


def base_quote(rent: int = 2_500_000) -> dict:
    return {"rent_vnd": rent, "deposit_vnd": rent, "advance_months": 1, "one_time_vnd": 0,
            "fees": [fee("electricity", 3000, "kwh"), fee("water", 80_000, "person"),
                     fee("internet", 100_000), fee("parking", 100_000, "vehicle"),
                     fee("service", 50_000)]}


def make_catalog(count: int = V2_ROOMS) -> tuple[list[dict], dict]:
    if count not in (40, V1_ROOMS, V2_ROOMS):
        raise ValueError(f"Catalog count must be {V2_ROOMS} (v2), 80 (v1 rooms only) or the explicit fallback 40.")
    rng = random.Random(SEED)
    seeds = json.loads((ROOT / "backend/data/demo_rooms.json").read_text())["rooms"]
    rooms, metadata = [], {}
    for index in range(min(count, V1_ROOMS)):
        room_id = f"synthetic-room-{index + 1:03d}"
        if index < len(seeds):
            value = copy.deepcopy(seeds[index])
            value.update(id=room_id, city="TP.HCM", room_type="room")
            origin = f"backend/data/demo_rooms.json#{seeds[index]['id']}"
        else:
            area_index = (index - 12) % len(AREAS)
            lat, lon = CENTERS[area_index]
            rent = rng.choice([1_800_000, 2_100_000, 2_400_000, 2_800_000, 3_100_000,
                               3_500_000, 3_900_000, 4_500_000, 5_500_000])
            style = index % 6
            amenities = {name: bool(rng.getrandbits(1)) for name in AMENITIES}
            if style < 5:
                amenities[AMENITIES[style]] = True
            quote = base_quote(rent)
            quote["fees"][0]["amount_vnd"] = rng.choice([2500, 3000, 3500, 4000, 5000])
            quote["fees"][1] = fee("water", rng.choice([15_000, 20_000, 25_000]), "m3")
            quote["fees"][2]["included_in_rent"] = index % 4 == 0
            quote["fees"][3]["amount_vnd"] = rng.choice([0, 80_000, 100_000, 150_000])
            quote["advance_months"] = 2 if index % 8 == 0 else 1
            quote["one_time_vnd"] = 100_000 if index % 7 == 0 else 0
            value = {"id": room_id, "revision": 1, "title": f"Phòng giả lập {index + 1:03d}",
                     "city": "TP.HCM", "area": AREAS[area_index], "room_type": "room",
                     "capacity": rng.choice([1, 2, 3]), "area_m2": rng.choice([16, 18, 22, 26, 30]),
                     "published": index % 19 != 0, "available": index % 17 != 0,
                     "amenities": amenities, "latitude": round(lat + rng.uniform(-0.009, 0.009), 6),
                     "longitude": round(lon + rng.uniform(-0.009, 0.009), 6),
                     "location_accuracy": "approximate", "uncertainty_m": rng.choice([25, 50, 100, 200]),
                     "quote": quote, "source": f"synthetic://rooms/{room_id}", "synthetic": True}
            origin = f"template:style-{style}:seed-{SEED}"
            if index % 13 == 0:
                value["quote"]["fees"][1]["amount_vnd"] = None
            if index % 11 == 0:
                value["amenities"]["private_bathroom"] = None
            if index % 23 == 0:
                value["capacity"] = None
            if index % 29 == 0:
                value["available"] = None
            if index % 31 == 0:
                value.update(latitude=None, longitude=None, uncertainty_m=None, location_accuracy="area_only")
            if index % 37 == 0:
                value["quote"]["deposit_vnd"] = None
        value["source"] = f"synthetic://rooms/{room_id}"
        for charge in value["quote"]["fees"]:
            charge["source"] = f"synthetic://rooms/{room_id}/fees/{charge['name']}"
        # Only describe amenities actually true: semantic text never invents unknown evidence.
        fragments = [DESCRIPTIONS[AMENITIES.index(name)] for name in AMENITIES
                     if value["amenities"].get(name) is True]
        description = " ".join(fragments) if fragments else DESCRIPTIONS[-1]
        value["title"] = f"Phòng giả lập {index + 1:03d}. {description}"
        validated = Room.model_validate(value).model_dump(mode="json")
        rooms.append(validated)
        metadata[room_id] = {"origin": origin, "observed_at": OBSERVED_AT,
                             "location_source": "synthetic://coordinate-fixture",
                             "location_notice": "Tọa độ giả lập, không định danh địa chỉ thật.",
                             "semantic_text": description, "synthetic": True}
    for value in rooms:
        value["landlord_id"] = landlord_for(value["city"], value["area"], value["id"])
        value["house_rules"] = LANDLORD_RULES[value["landlord_id"]]
    # Deliberate uncertainty boundary near the synthetic Quận 7 destination (last v1 room).
    rooms[-1].update(area="Quận 7", latitude=10.744, longitude=106.721,
                     location_accuracy="approximate", uncertainty_m=250)
    if count == V2_ROOMS:
        for value, meta in make_v2_rooms(count - V1_ROOMS):
            rooms.append(value)
            metadata[value["id"]] = meta
    return rooms, metadata


def landlord_for(city: str, area: str, room_id: str) -> str:
    # Một tài khoản dùng thử mỗi thành phố; việc chia owner để "chủ nhà duyệt
    # gợi ý" đã bỏ theo quyết định 05/11/2026 nên không còn lý do giữ 4 owner.
    return "owner1" if city == "Hà Nội" else "owner2"


def make_v2_rooms(count: int) -> list[tuple[dict, dict]]:
    """Hà Nội plus TP.HCM studios/apartments, drawn from a separate seed so v1 rooms stay identical."""
    rng = random.Random(SEED_V2)
    result = []
    for offset in range(count):
        index = V1_ROOMS + offset
        room_id = f"synthetic-room-{index + 1:03d}"
        if offset < HCM_V2_COUNT:
            city, area_index = "TP.HCM", offset % len(HCM_V2_AREAS)
            area, (lat, lon) = HCM_V2_AREAS[area_index], HCM_V2_CENTERS[area_index]
            kind = "studio" if (offset // len(HCM_V2_AREAS)) % 2 == 0 else "apartment"
        else:
            hanoi = offset - HCM_V2_COUNT
            city, area_index = "Hà Nội", hanoi % len(HANOI_AREAS)
            area, (lat, lon) = HANOI_AREAS[area_index], HANOI_CENTERS[area_index]
            kind = "room" if hanoi % 10 < 4 else "studio" if hanoi % 10 < 6 else "apartment"
        bedrooms = (1 if rng.random() < 0.6 else 2) if kind == "apartment" else None
        band = f"apartment-{bedrooms}" if kind == "apartment" else kind
        rent = rng.choice(RENTS[band])
        amenities = {name: bool(rng.getrandbits(1)) for name in AMENITIES}
        if kind != "room":
            amenities.update(private_bathroom=True, furniture=rng.random() < 0.8,
                             air_conditioning=rng.random() < 0.85)
        electricity = rng.choice([3500, 3800, 4000] if city == "Hà Nội" else [3000, 3500, 4000])
        water = (fee("water", rng.choice([80_000, 100_000, 120_000]), "person") if offset % 2
                 else fee("water", rng.choice([20_000, 25_000, 30_000]), "m3"))
        quote = {"rent_vnd": rent,
                 "deposit_vnd": rent * (rng.choice([1, 2]) if kind == "apartment" else 1),
                 "advance_months": rng.choice([1, 3]) if kind == "apartment" else rng.choice([1, 1, 2]),
                 "one_time_vnd": rng.choice([0, 0, 200_000]),
                 "fees": [fee("electricity", electricity, "kwh"), water,
                          fee("internet", rng.choice([100_000, 150_000, 200_000]),
                              included=kind == "apartment" and offset % 3 == 0),
                          fee("parking", rng.choice([100_000, 120_000, 150_000]), "vehicle"),
                          fee("service", rng.choice(SERVICE[band]))]}
        value = {"id": room_id, "revision": 1, "city": city, "area": area, "room_type": kind,
                 "bedrooms": bedrooms, "capacity": rng.choice(CAPACITY[band]),
                 "area_m2": rng.choice(SIZES[band]), "published": offset % 19 != 7,
                 "available": offset % 17 != 5, "amenities": amenities,
                 "latitude": round(lat + rng.uniform(-0.009, 0.009), 6),
                 "longitude": round(lon + rng.uniform(-0.009, 0.009), 6),
                 "location_accuracy": "approximate", "uncertainty_m": rng.choice([25, 50, 100, 200]),
                 "quote": quote, "source": f"synthetic://rooms/{room_id}", "synthetic": True,
                 "features_text": " ".join(rng.sample(FEATURES, 2))}
        value["landlord_id"] = landlord_for(city, area, room_id)
        value["house_rules"] = LANDLORD_RULES[value["landlord_id"]]
        # Deliberate unknowns, mirroring the v1 cases so every type has verification paths.
        if offset % 13 == 3:
            value["quote"]["fees"][1]["amount_vnd"] = None
        if offset % 11 == 4:
            value["amenities"]["private_bathroom"] = None
        if offset % 23 == 6:
            value["capacity"] = None
        if offset % 29 == 8:
            value["available"] = None
        if offset % 31 == 9:
            value.update(latitude=None, longitude=None, uncertainty_m=None, location_accuracy="area_only")
        if offset % 37 == 10:
            value["quote"]["deposit_vnd"] = None
        if kind == "apartment" and offset % 14 == 2:
            value["bedrooms"] = None
        for charge in value["quote"]["fees"]:
            charge["source"] = f"synthetic://rooms/{room_id}/fees/{charge['name']}"
        fragments = [DESCRIPTIONS[AMENITIES.index(name)] for name in AMENITIES
                     if value["amenities"].get(name) is True]
        description = " ".join(fragments) if fragments else DESCRIPTIONS[-1]
        value["title"] = f"{TYPE_LABEL[band]} giả lập {index + 1:03d}. {description}"
        validated = Room.model_validate(value).model_dump(mode="json")
        result.append((validated, {"origin": f"template-v2:{band}:seed-{SEED_V2}", "observed_at": OBSERVED_AT,
                                   "location_source": "synthetic://coordinate-fixture",
                                   "location_notice": "Tọa độ giả lập, không định danh địa chỉ thật.",
                                   "semantic_text": f"{description} {value['features_text']}",
                                   "synthetic": True}))
    return result


# These synthetic utterance/gold pairs are authored test inputs, not human room-relevance judgments.
CASES = [
    ("Tìm phòng TP.HCM Quận 7 cho 1 người, thoáng và yên tĩnh, tầm 3,5 triệu.", "TP.HCM", "Quận 7", 1, ["window", "quiet"], False, "find_room"),
    ("Thuê phòng TP.HCM Quận 1 cho 2 người, có máy lạnh và WC riêng.", "TP.HCM", "Quận 1", 2, ["air_conditioning", "private_bathroom"], False, "find_room"),
    ("Tìm trọ TP.HCM Quận 3 cho 1 người, có chỗ để xe.", "TP.HCM", "Quận 3", 1, ["parking"], False, "find_room"),
    ("Tìm phòng Quận 7 cho 1 người, gần trường và có cửa sổ.", None, "Quận 7", 1, ["window"], True, "find_room"),
    ("Tìm phòng TP.HCM Quận 10 cho 2 người, yên tĩnh.", "TP.HCM", "Quận 10", 2, ["quiet"], False, "find_room"),
    ("Tìm phòng TP.HCM cho 1 người, có cửa sổ, gần nơi làm.", "TP.HCM", None, 1, ["window"], True, "find_room"),
    ("Muốn thuê phòng TP.HCM Quận 7 cho 3 người, gửi xe và vệ sinh riêng.", "TP.HCM", "Quận 7", 3, ["parking", "private_bathroom"], False, "find_room"),
    ("Tìm phòng TP.HCM Quận 1, chưa biết ở mấy người, cần điều hòa và máy giặt.", "TP.HCM", "Quận 1", None, ["air_conditioning", "washing_machine"], False, "find_room"),
    ("Tìm trọ TP.HCM Quận 3 cho 2 người, ít ồn và thoáng.", "TP.HCM", "Quận 3", 2, ["window", "quiet"], False, "find_room"),
    ("Tìm phòng khoảng 3 triệu, gần trường.", None, None, None, [], True, "find_room"),
    ("Tìm phòng TP.HCM Quận 7 cho 1 người, có cửa sổ và WC riêng.", "TP.HCM", "Quận 7", 1, ["window", "private_bathroom"], False, "find_room"),
    ("Muốn thuê phòng TP.HCM Quận 1 cho 1 người, yên tĩnh và máy lạnh.", "TP.HCM", "Quận 1", 1, ["quiet", "air_conditioning"], False, "find_room"),
    ("Tìm phòng TP.HCM Quận 3 cho 3 người, có chỗ gửi xe và nội thất cơ bản.", "TP.HCM", "Quận 3", 3, ["parking", "furniture"], False, "find_room"),
    ("Tìm phòng Quận 10 cho 2 người, vệ sinh riêng.", None, "Quận 10", 2, ["private_bathroom"], False, "find_room"),
    ("Tìm phòng TP.HCM cho 2 người, gần nơi làm và ít ồn.", "TP.HCM", None, 2, ["quiet"], True, "find_room"),
    ("Thuê phòng TP.HCM Quận 7 cho 2 người, thoáng và có máy lạnh.", "TP.HCM", "Quận 7", 2, ["window", "air_conditioning"], False, "find_room"),
    ("Tìm phòng TP.HCM Quận 1 cho 1 người, không cần máy lạnh, cần cửa sổ.", "TP.HCM", "Quận 1", 1, ["window"], False, "find_room"),
    ("Tìm trọ TP.HCM Quận 3 cho 1 người, không cần gửi xe, cần yên tĩnh.", "TP.HCM", "Quận 3", 1, ["quiet"], False, "find_room"),
    ("Tìm phòng TP.HCM Quận 10 cho 1 người, 3 triệu là tổng tháng hay tiền phòng nhỉ?", "TP.HCM", "Quận 10", 1, [], False, "find_room"),
    ("Tìm phòng gần trường, có chỗ để xe cho 1 người, chưa chọn thành phố.", None, None, 1, ["parking"], True, "find_room"),
    ("Cần phòng TP.HCM Quận 7 cho 2 người, sáng tự nhiên và ít tiếng động.", "TP.HCM", "Quận 7", 2, ["window", "quiet"], False, "find_room"),
    ("Tìm phòng TP.HCM Quận 1 cho 3 người, WC riêng, gửi xe và có ban công.", "TP.HCM", "Quận 1", 3, ["parking", "private_bathroom", "balcony"], False, "find_room"),
    ("Tìm phòng TP.HCM Quận 3 cho 1 người, để xe và máy lạnh.", "TP.HCM", "Quận 3", 1, ["parking", "air_conditioning"], False, "find_room"),
    ("Tìm phòng TP.HCM Quận 10 cho 2 người, có cửa sổ và WC riêng.", "TP.HCM", "Quận 10", 2, ["window", "private_bathroom"], False, "find_room"),
    ("Tìm phòng TP.HCM cho 1 người, gần nơi làm và có điều hòa.", "TP.HCM", None, 1, ["air_conditioning"], True, "find_room"),
    ("Tìm phòng tầm 3 triệu cho 2 người, không biết trường nào gần.", None, None, 2, [], True, "find_room"),
    ("Tính chi phí phòng TP.HCM Quận 7 cho 2 người.", "TP.HCM", "Quận 7", 2, [], False, "calculate_cost"),
    ("Tính tiền vào ở phòng TP.HCM Quận 1 cho 1 người.", "TP.HCM", "Quận 1", 1, [], False, "calculate_cost"),
    ("Tôi muốn gặp người thật, nhân viên tư vấn về phòng TP.HCM.", "TP.HCM", None, None, [], False, "human_support"),
    ("Chào bạn, mình chưa quyết định nhu cầu.", None, None, None, [], False, "unknown"),
]


HANOI_DESTINATION = {"label": "Điểm đến giả lập Cầu Giấy", "latitude": 21.034, "longitude": 105.794,
                     "uncertainty_m": 50, "max_distance_m": 2_000}
THU_DUC_DESTINATION = {"label": "Điểm đến giả lập Thủ Đức", "latitude": 10.850, "longitude": 106.772,
                       "uncertainty_m": 50, "max_distance_m": 2_000}
# v2 cases: Hà Nội, studios/apartments, area aliases and loan/income scenarios. Authored, not real customers.
V2_CASES = [
    {"text": "Tìm căn hộ 1 phòng ngủ ở Cầu Giấy, Hà Nội cho 2 người, gần trường, view thoáng.",
     "city": "Hà Nội", "area": "Quận Cầu Giấy", "people": 2, "prefs": ["window"], "destination": True,
     "intent": "find_room", "room_type": "apartment", "bedrooms": 1, "split": "dev",
     "profile": {"min_bedrooms": 1, "max_monthly_cost_vnd": 16_000_000, "max_initial_cash_vnd": 50_000_000,
                 "monthly_income_vnd": 35_000_000}, "soft": "Nhìn ra hồ, thoáng gió. Nhiều ánh sáng tự nhiên."},
    {"text": "Thuê studio Đống Đa HN cho 1 người, có máy giặt và nội thất.",
     "city": "Hà Nội", "area": "Quận Đống Đa", "people": 1, "prefs": ["washing_machine", "furniture"],
     "destination": False, "intent": "find_room", "room_type": "studio", "split": "dev",
     "profile": {"max_monthly_cost_vnd": 10_000_000, "max_initial_cash_vnd": 25_000_000}},
    {"text": "Tìm phòng trọ Hai Bà Trưng Hà Nội cho 2 người, có chỗ để xe.",
     "city": "Hà Nội", "area": "Quận Hai Bà Trưng", "people": 2, "prefs": ["parking"], "destination": False,
     "intent": "find_room", "room_type": "room", "split": "test",
     "profile": {"max_monthly_cost_vnd": 5_500_000, "max_initial_cash_vnd": 10_000_000}},
    {"text": "Căn hộ 2 phòng ngủ Thanh Xuân, Hà Nội cho 3 người, có ban công.",
     "city": "Hà Nội", "area": "Quận Thanh Xuân", "people": 3, "prefs": ["balcony"], "destination": False,
     "intent": "find_room", "room_type": "apartment", "bedrooms": 2, "split": "test",
     "profile": {"min_bedrooms": 2, "max_monthly_cost_vnd": 24_000_000, "max_initial_cash_vnd": 30_000_000,
                 "loan": {"annual_rate": "0.12", "term_months": 12, "max_principal_vnd": 60_000_000}}},
    {"text": "tim tro hanoi nam tu liem 1 nguoi, yen tinh",
     "city": "Hà Nội", "area": "Quận Nam Từ Liêm", "people": 1, "prefs": ["quiet"], "destination": False,
     "intent": "find_room", "room_type": None, "split": "dev",
     "profile": {"max_monthly_cost_vnd": 5_000_000, "max_initial_cash_vnd": 10_000_000}},
    {"text": "Tìm studio Sài Gòn Q7 cho 1 người, có máy lạnh.",
     "city": "TP.HCM", "area": "Quận 7", "people": 1, "prefs": ["air_conditioning"], "destination": False,
     "intent": "find_room", "room_type": "studio", "split": "dev",
     "profile": {"max_monthly_cost_vnd": 10_000_000, "max_initial_cash_vnd": 25_000_000}},
    {"text": "Thuê căn hộ Gò Vấp HCM cho 2 người, có máy giặt.",
     "city": "TP.HCM", "area": "Quận Gò Vấp", "people": 2, "prefs": ["washing_machine"], "destination": False,
     "intent": "find_room", "room_type": "apartment", "split": "test",
     "profile": {"max_monthly_cost_vnd": 16_000_000, "max_initial_cash_vnd": 50_000_000}},
    {"text": "Tìm căn hộ Thủ Đức cho 2 người gần trường, có nội thất.",
     "city": None, "area": "TP. Thủ Đức", "people": 2, "prefs": ["furniture"], "destination": True,
     "intent": "find_room", "room_type": "apartment", "split": "test", "confirmed_city": "TP.HCM",
     "profile": {"max_monthly_cost_vnd": 16_000_000, "max_initial_cash_vnd": 50_000_000}},
    {"text": "Tìm phòng Hoàng Mai cho 1 người, có WC riêng.",
     "city": None, "area": "Quận Hoàng Mai", "people": 1, "prefs": ["private_bathroom"], "destination": False,
     "intent": "find_room", "room_type": None, "split": "test", "confirmed_city": "Hà Nội",
     "profile": {"max_monthly_cost_vnd": 5_500_000, "max_initial_cash_vnd": 10_000_000}},
    {"text": "Tôi thu nhập khoảng 20 triệu, muốn thuê căn hộ Cầu Giấy HN cho 2 người, không đủ tiền cọc thì vay được không?",
     "city": "Hà Nội", "area": "Quận Cầu Giấy", "people": 2, "prefs": [], "destination": False,
     "intent": "find_room", "room_type": "apartment", "split": "dev",
     "profile": {"max_monthly_cost_vnd": 18_000_000, "max_initial_cash_vnd": 15_000_000,
                 "monthly_income_vnd": 20_000_000, "cost_split": "equal",
                 "loan": {"annual_rate": "0.12", "term_months": 12, "max_principal_vnd": 40_000_000}}},
    {"text": "Tính chi phí căn hộ Đống Đa Hà Nội cho 2 người.",
     "city": "Hà Nội", "area": "Quận Đống Đa", "people": 2, "prefs": [], "destination": False,
     "intent": "calculate_cost", "room_type": "apartment", "split": "test",
     "profile": {"max_monthly_cost_vnd": 16_000_000, "max_initial_cash_vnd": 50_000_000}},
    {"text": "Tìm phòng Hà Nội cho 1 người, gần nơi làm, có điều hòa.",
     "city": "Hà Nội", "area": None, "people": 1, "prefs": ["air_conditioning"], "destination": True,
     "intent": "find_room", "room_type": None, "split": "test",
     "profile": {"max_monthly_cost_vnd": 5_500_000, "max_initial_cash_vnd": 10_000_000}},
    {"text": "Cần studio Bình Thạnh TP.HCM cho 1 người, thoáng.",
     "city": "TP.HCM", "area": "Quận Bình Thạnh", "people": 1, "prefs": ["window"], "destination": False,
     "intent": "find_room", "room_type": "studio", "split": "test",
     "profile": {"max_monthly_cost_vnd": 10_000_000, "max_initial_cash_vnd": 25_000_000}},
    {"text": "Thuê căn hộ HN Hai Bà Trưng cho 2 người, nuôi thú cưng.",
     "city": "Hà Nội", "area": "Quận Hai Bà Trưng", "people": 2, "prefs": ["pets_allowed"], "destination": False,
     "intent": "find_room", "room_type": "apartment", "split": "test",
     "profile": {"max_monthly_cost_vnd": 20_000_000, "max_initial_cash_vnd": 60_000_000,
                 "monthly_income_vnd": 30_000_000}},
    {"text": "Tìm phòng Long Biên Hà Nội cho 2 người, yên tĩnh và có cửa sổ.",
     "city": "Hà Nội", "area": "Quận Long Biên", "people": 2, "prefs": ["window", "quiet"], "destination": False,
     "intent": "find_room", "room_type": None, "split": "test",
     "profile": {"max_monthly_cost_vnd": 5_500_000, "max_initial_cash_vnd": 10_000_000}},
]


# DA-01 gold intents: authored utterances for every chat route, not human judgments.
# Gold is what a human would label the utterance; the offline rules may disagree and the
# `eval intents` suite records that (measurement only, no pass/fail threshold).
# simulate_finance is gold for AG-02: until it lands, those cases are expected to misroute.
INTENT_CASES = [
    {"case_id": "I001", "split": "dev", "intent": "handbook", "text": "Nội quy nhà có cho nấu ăn bằng than không?"},
    {"case_id": "I002", "split": "test", "intent": "handbook", "text": "Cho mình hỏi quy định gửi xe máy của nhà thế nào?"},
    {"case_id": "I003", "split": "dev", "intent": "handbook", "text": "Khách thuê dài hạn có phải làm tạm trú không?"},
    {"case_id": "I004", "split": "test", "intent": "handbook", "text": "Trường hợp nào được hoàn cọc, mình muốn đọc điều khoản."},
    {"case_id": "I005", "split": "test", "intent": "handbook", "text": "Quyền lợi của người thuê trong hợp đồng có gì?"},
    {"case_id": "I006", "split": "dev", "intent": "handbook", "text": "Cho mình xem cẩm nang thuê phòng với."},
    {"case_id": "I007", "split": "test", "intent": "handbook", "text": "noi quy cho nuoi thu cung dc ko?"},
    {"case_id": "I008", "split": "test", "intent": "handbook", "text": "Điều khoản về khách ở lại qua đêm ghi gì?"},
    {"case_id": "I009", "split": "dev", "intent": "human_support", "text": "Mình muốn nói chuyện với người thật, không trả lời máy nữa."},
    {"case_id": "I010", "split": "test", "intent": "human_support", "text": "Cho gặp nhân viên tư vấn giúp mình với."},
    {"case_id": "I011", "split": "dev", "intent": "human_support", "text": "Tôi muốn gặp quản lý để trao đổi trực tiếp về phòng."},
    {"case_id": "I012", "split": "test", "intent": "human_support", "text": "Làm sao chat với chủ nhà của phòng này?"},
    {"case_id": "I013", "split": "test", "intent": "human_support", "text": "Mình cần nói chuyện với chủ nhà về lịch xem phòng."},
    {"case_id": "I014", "split": "test", "intent": "human_support", "text": "gap chu nha duoc khong, minh hoi truc tiep"},
    {"case_id": "I015", "split": "dev", "intent": "calculate_cost", "text": "Tính chi phí vào ở phòng Quận 7 cho 2 người."},
    {"case_id": "I016", "split": "test", "intent": "calculate_cost", "text": "Tính tiền vào ở căn hộ Đống Đa cho 1 người."},
    {"case_id": "I017", "split": "dev", "intent": "calculate_cost", "text": "Mô phỏng chi phí thuê studio Bình Thạnh giúp mình."},
    {"case_id": "I018", "split": "test", "intent": "calculate_cost", "text": "tinh tien vao o tro q7 1 nguoi roi ra sao?"},
    {"case_id": "I019", "split": "test", "intent": "calculate_cost", "text": "Cho mình tính chi phí vào ở của phòng này với 2 người và 1 xe máy."},
    {"case_id": "I020", "split": "test", "intent": "calculate_cost", "text": "Muốn biết tổng tháng và tiền cọc, mô phỏng chi phí căn hộ 2 phòng ngủ."},
    {"case_id": "I021", "split": "dev", "intent": "simulate_finance", "text": "Nếu vay 12 tháng thì sao nhỉ?"},
    {"case_id": "I022", "split": "test", "intent": "simulate_finance", "text": "vay 20 triệu lãi 10% trong 6 tháng thì trả bao nhiêu?"},
    {"case_id": "I023", "split": "dev", "intent": "simulate_finance", "text": "trả góp 24 tháng lãi suất 12,5% được không?"},
    {"case_id": "I024", "split": "test", "intent": "simulate_finance", "text": "Tính tiền vay 15 triệu trong 12 tháng giúp mình."},
    {"case_id": "I025", "split": "test", "intent": "simulate_finance", "text": "Mình muốn mô phỏng khoản vay 30 triệu lãi 9.5%."},
    {"case_id": "I026", "split": "dev", "intent": "simulate_finance", "text": "Xem trước số tiền trả góp khi vay tiền cọc căn hộ."},
    {"case_id": "I027", "split": "test", "intent": "simulate_finance", "text": "lai vay 8%/nam, vay 10 trieu tra trong 18 thang duoc khong?"},
    {"case_id": "I028", "split": "test", "intent": "simulate_finance", "text": "Tính giúp mình khoản trả góp vay tiền thuê phòng 3 tháng đầu."},
    {"case_id": "I029", "split": "dev", "intent": "find_room", "text": "Tìm phòng Quận 3 cho 1 người, cần cửa sổ."},
    {"case_id": "I030", "split": "test", "intent": "find_room", "text": "tim tro hcm binh thanh 2 nguoi co may lanh"},
    {"case_id": "I031", "split": "dev", "intent": "find_room", "text": "Mình cần thuê căn hộ Cầu Giấy cho 2 người."},
    {"case_id": "I032", "split": "test", "intent": "find_room", "text": "Phòng trọ gần trường ở Thủ Đức cho 1 người."},
    {"case_id": "I033", "split": "dev", "intent": "find_room", "text": "studio q7 giá 5 triệu có máy giặt không?"},
    {"case_id": "I034", "split": "test", "intent": "find_room", "text": "tim phong q3 1 nguoi co wc rieng dc ko?"},
    {"case_id": "I035", "split": "dev", "intent": "unknown", "text": "Chào bạn, mình chưa quyết định nhu cầu."},
    {"case_id": "I036", "split": "test", "intent": "unknown", "text": "hello"},
    # "trời" chứa "tro": ca bắt lỗi chuỗi con của luật offline, gold vẫn là unknown.
    {"case_id": "I037", "split": "dev", "intent": "unknown", "text": "Hôm nay trời đẹp quá."},
    {"case_id": "I038", "split": "test", "intent": "unknown", "text": "0987654321"},
]

# DA-02: hand-authored expected outputs for interpreter.parse_loan_terms (AG-02).
# Ranges and decimal-comma handling follow the loan-parsing rules below.
LOAN_PARSE_CASES = [
    {"case_id": "LP01", "text": "nếu vay 12 tháng thì sao",
     "expected": {"term_months": 12, "annual_rate": None, "principal_vnd": None},
     "note": "chỉ có kỳ hạn"},
    {"case_id": "LP02", "text": "vay 20 triệu lãi 10% trong 6 tháng",
     "expected": {"term_months": 6, "annual_rate": 10.0, "principal_vnd": 20_000_000},
     "note": "đủ ba giá trị"},
    {"case_id": "LP03", "text": "trả góp 24 tháng lãi suất 12,5%",
     "expected": {"term_months": 24, "annual_rate": 12.5, "principal_vnd": None},
     "note": "dấu phẩy thập phân"},
    {"case_id": "LP04", "text": "cho vay 1,5 triệu được không",
     "expected": {"term_months": None, "annual_rate": None, "principal_vnd": 1_500_000},
     "note": "dấu phẩy thập phân của tiền"},
    {"case_id": "LP05", "text": "lãi 0% vay 12 tháng thì sao",
     "expected": {"term_months": 12, "annual_rate": 0.0, "principal_vnd": None},
     "note": "lãi 0% là giá trị hợp lệ, không phải null"},
    {"case_id": "LP06", "text": "12 tháng",
     "expected": {"term_months": 12, "annual_rate": None, "principal_vnd": None},
     "note": "không có chữ 'vay'; việc parse tách khỏi việc xếp ý định (DA-01)"},
    {"case_id": "LP07", "text": "vay 100 tháng",
     "expected": {"term_months": None, "annual_rate": None, "principal_vnd": None},
     "note": "kỳ hạn ngoài khoảng 1–60 → null"},
    {"case_id": "LP08", "text": "vay 20 triệu lãi 60%",
     "expected": {"term_months": None, "annual_rate": None, "principal_vnd": 20_000_000},
     "note": "lãi ngoài khoảng 0–50 → null"},
    {"case_id": "LP09", "text": "vay 6 tháng hay 12 tháng tốt hơn?",
     "expected": {"term_months": 6, "annual_rate": None, "principal_vnd": None},
     "note": "hai số tháng: lấy số đầu tiên (re.search khớp đầu tiên)"},
    {"case_id": "LP10", "text": "lai suat 9.5% vay 18 thang",
     "expected": {"term_months": 18, "annual_rate": 9.5, "principal_vnd": None},
     "note": "không dấu; dấu chấm thập phân"},
    {"case_id": "LP11", "text": "vay 20tr",
     "expected": {"term_months": None, "annual_rate": None, "principal_vnd": 20_000_000},
     "note": "đơn vị 'tr'"},
    {"case_id": "LP12", "text": "trả góp 3 tháng, tiền phòng 2,5 triệu mỗi tháng",
     "expected": {"term_months": 3, "annual_rate": None, "principal_vnd": 2_500_000},
     "note": "kỳ hạn và tiền trong cùng câu"},
    {"case_id": "LP13", "text": "muốn vay 35 triệu, lãi 12%/năm, trả trong 36 tháng",
     "expected": {"term_months": 36, "annual_rate": 12.0, "principal_vnd": 35_000_000},
     "note": "lãi theo năm, dấu '%' ngay sau số"},
    {"case_id": "LP14", "text": "cho mình vay tiền cọc với",
     "expected": {"term_months": None, "annual_rate": None, "principal_vnd": None},
     "note": "không có số nào"},
    {"case_id": "LP15", "text": "vay 500 nghìn trả trong 3 tháng",
     "expected": {"term_months": 3, "annual_rate": None, "principal_vnd": None},
     "note": "đơn vị 'nghìn' không được đọc tiền → null"},
    {"case_id": "LP16", "text": "vay 12,5 triệu lãi 15,5% trong 9 tháng",
     "expected": {"term_months": 9, "annual_rate": 15.5, "principal_vnd": 12_500_000},
     "note": "dấu phẩy thập phân ở cả tiền và lãi"},
    {"case_id": "LP17", "text": "vay 5 triệu trả 60 tháng",
     "expected": {"term_months": 60, "annual_rate": None, "principal_vnd": 5_000_000},
     "note": "biên trên kỳ hạn 60 vẫn hợp lệ"},
    {"case_id": "LP18", "text": "vay 5 triệu lãi 50%",
     "expected": {"term_months": None, "annual_rate": 50.0, "principal_vnd": 5_000_000},
     "note": "biên trên lãi 50 vẫn hợp lệ"},
    {"case_id": "LP19", "text": "vay 61 tháng thì sao",
     "expected": {"term_months": None, "annual_rate": None, "principal_vnd": None},
     "note": "61 ngoài khoảng 1–60 → null"},
]


def _inv_fee(case_id: str, name: str, amount: int | str | None, mode: str = "fixed",
             included: bool = False) -> dict:
    source = f"synthetic://oracle-invoices/{case_id}/{name}"
    return {"name": name, "amount_vnd": amount, "mode": mode,
            "included_in_rent": included, "source": source}


def _inv_quote(case_id: str, rent: int, electricity: int | str | None = 3_000,
               electricity_included: bool = False, water: dict | None = None,
               water_included: bool = False, internet: int | None = 100_000,
               internet_included: bool = False, parking: int | None = 100_000,
               parking_included: bool = False, service: int | None = 50_000,
               service_included: bool = False) -> dict:
    water = water or {"amount_vnd": 80_000, "mode": "person"}
    return {"rent_vnd": rent, "deposit_vnd": rent, "advance_months": 1, "one_time_vnd": 0,
            "fees": [_inv_fee(case_id, "electricity", electricity, "kwh", electricity_included),
                     _inv_fee(case_id, "water", water["amount_vnd"], water["mode"], water_included),
                     _inv_fee(case_id, "internet", internet, "fixed", internet_included),
                     _inv_fee(case_id, "parking", parking, "vehicle", parking_included),
                     _inv_fee(case_id, "service", service, "fixed", service_included)]}


def _inv_line(name: str, label: str, quantity: str, unit_price: str, amount: int) -> dict:
    return {"name": name, "label": label, "quantity": quantity,
            "unit_price": unit_price, "amount_vnd": amount}


def _rent_line(rent: int) -> dict:
    return _inv_line("rent", "Tiền thuê", "1", str(rent), rent)


def _included_line(name: str, label: str) -> dict:
    return _inv_line(name, f"{label} (đã gồm trong thuê)", "0", "0", 0)


# DA-03: hand-computed PMS invoice oracle. Expected totals and lines are authored
# arithmetic, never engine output; each line rounds HALF_UP to whole VND.
INVOICE_CASES = [
    {"case_id": "INV-01-reference", "description": "Ví dụ có sẵn trong test_pms.py: 150 kWh, 2 người, 1 xe.",
     "room_type": "room",
     "quote": _inv_quote("INV-01", 2_500_000),
     "lease": {"rent_vnd": 2_500_000, "occupants": 2, "vehicles": 1},
     "reading": {"period": "2026-10", "electricity_start": "1200", "electricity_end": "1350"},
     "expected_total_vnd": 3_360_000, "expected_error": None,
     "lines": [_rent_line(2_500_000),
               _inv_line("electricity", "Điện", "150", "3000", 450_000),
               _inv_line("water", "Nước", "2", "80000", 160_000),
               _inv_line("internet", "Internet", "1", "100000", 100_000),
               _inv_line("parking", "Gửi xe", "1", "100000", 100_000),
               _inv_line("service", "Dịch vụ", "1", "50000", 50_000)],
     "calculation_note": "2500000+150*3000+2*80000+100000+1*100000+50000=3360000"},
    {"case_id": "INV-02-electricity-rounding", "description": "Điện số lẻ cần làm tròn HALF_UP.",
     "room_type": "room",
     "quote": _inv_quote("INV-02", 2_500_000, electricity="3000.5"),
     "lease": {"rent_vnd": 2_500_000, "occupants": 1, "vehicles": 1},
     "reading": {"period": "2026-10", "electricity_start": "100", "electricity_end": "200.5"},
     "expected_total_vnd": 3_131_550, "expected_error": None,
     "lines": [_rent_line(2_500_000),
               _inv_line("electricity", "Điện", "100.5", "3000.5", 301_550),
               _inv_line("water", "Nước", "1", "80000", 80_000),
               _inv_line("internet", "Internet", "1", "100000", 100_000),
               _inv_line("parking", "Gửi xe", "1", "100000", 100_000),
               _inv_line("service", "Dịch vụ", "1", "50000", 50_000)],
     "calculation_note": "100.5*3000.5=301550.25→HALF_UP 301550; 2500000+301550+80000+100000+100000+50000=3131550"},
    {"case_id": "INV-03-water-m3", "description": "Nước theo m³ với chỉ số lẻ, xe bằng 0.",
     "room_type": "room",
     "quote": _inv_quote("INV-03", 2_500_000, water={"amount_vnd": 20_000, "mode": "m3"}),
     "lease": {"rent_vnd": 2_500_000, "occupants": 2, "vehicles": 0},
     "reading": {"period": "2026-10", "electricity_start": "512", "electricity_end": "632",
                 "water_start": "45.5", "water_end": "52.5"},
     "expected_total_vnd": 3_150_000, "expected_error": None,
     "lines": [_rent_line(2_500_000),
               _inv_line("electricity", "Điện", "120", "3000", 360_000),
               _inv_line("water", "Nước", "7.0", "20000", 140_000),
               _inv_line("internet", "Internet", "1", "100000", 100_000),
               _inv_line("parking", "Gửi xe", "0", "100000", 0),
               _inv_line("service", "Dịch vụ", "1", "50000", 50_000)],
     "calculation_note": "120*3000=360000; 52.5-45.5=7.0 m3*20000=140000; 0 xe*100000=0; tổng 3150000"},
    {"case_id": "INV-04-water-person", "description": "Nước theo người với 3 người ở.",
     "room_type": "room",
     "quote": _inv_quote("INV-04", 2_500_000),
     "lease": {"rent_vnd": 2_500_000, "occupants": 3, "vehicles": 1},
     "reading": {"period": "2026-10", "electricity_start": "0", "electricity_end": "200"},
     "expected_total_vnd": 3_590_000, "expected_error": None,
     "lines": [_rent_line(2_500_000),
               _inv_line("electricity", "Điện", "200", "3000", 600_000),
               _inv_line("water", "Nước", "3", "80000", 240_000),
               _inv_line("internet", "Internet", "1", "100000", 100_000),
               _inv_line("parking", "Gửi xe", "1", "100000", 100_000),
               _inv_line("service", "Dịch vụ", "1", "50000", 50_000)],
     "calculation_note": "200*3000=600000; 3*80000=240000; tổng 3590000"},
    {"case_id": "INV-05-many-vehicles", "description": "Nhiều xe (3 xe gửi).",
     "room_type": "room",
     "quote": _inv_quote("INV-05", 2_500_000),
     "lease": {"rent_vnd": 2_500_000, "occupants": 1, "vehicles": 3},
     "reading": {"period": "2026-10", "electricity_start": "10", "electricity_end": "60"},
     "expected_total_vnd": 3_180_000, "expected_error": None,
     "lines": [_rent_line(2_500_000),
               _inv_line("electricity", "Điện", "50", "3000", 150_000),
               _inv_line("water", "Nước", "1", "80000", 80_000),
               _inv_line("internet", "Internet", "1", "100000", 100_000),
               _inv_line("parking", "Gửi xe", "3", "100000", 300_000),
               _inv_line("service", "Dịch vụ", "1", "50000", 50_000)],
     "calculation_note": "50*3000=150000; 3*100000=300000; tổng 3180000"},
    {"case_id": "INV-06-included-internet", "description": "Internet đã gồm trong tiền thuê, không cộng.",
     "room_type": "room",
     "quote": _inv_quote("INV-06", 2_500_000, internet_included=True),
     "lease": {"rent_vnd": 2_500_000, "occupants": 1, "vehicles": 1},
     "reading": {"period": "2026-10", "electricity_start": "0", "electricity_end": "100"},
     "expected_total_vnd": 3_030_000, "expected_error": None,
     "lines": [_rent_line(2_500_000),
               _inv_line("electricity", "Điện", "100", "3000", 300_000),
               _inv_line("water", "Nước", "1", "80000", 80_000),
               _included_line("internet", "Internet"),
               _inv_line("parking", "Gửi xe", "1", "100000", 100_000),
               _inv_line("service", "Dịch vụ", "1", "50000", 50_000)],
     "calculation_note": "Internet included→0; 2500000+300000+80000+100000+50000=3030000"},
    {"case_id": "INV-07-reading-decreased", "description": "Chỉ số điện cuối nhỏ hơn đầu.",
     "room_type": "room",
     "quote": _inv_quote("INV-07", 2_500_000),
     "lease": {"rent_vnd": 2_500_000, "occupants": 1, "vehicles": 1},
     "reading": {"period": "2026-10", "electricity_start": "500", "electricity_end": "480"},
     "expected_total_vnd": None, "expected_error": "reading_decreased",
     "lines": None,
     "calculation_note": "480<500 → từ chối ghi chỉ số, không lập hóa đơn"},
    {"case_id": "INV-08-missing-rate", "description": "Thiếu đơn giá nước (amount null).",
     "room_type": "room",
     "quote": _inv_quote("INV-08", 2_500_000, water={"amount_vnd": None, "mode": "person"}),
     "lease": {"rent_vnd": 2_500_000, "occupants": 1, "vehicles": 1},
     "reading": {"period": "2026-10", "electricity_start": "0", "electricity_end": "50"},
     "expected_total_vnd": None, "expected_error": "invoice_incomplete",
     "lines": None,
     "calculation_note": "Đơn giá nước null → từ chối lập hóa đơn, không bao giờ tính 0"},
    {"case_id": "INV-09-zero-kwh", "description": "Điện 0 kWh (chỉ số không đổi).",
     "room_type": "room",
     "quote": _inv_quote("INV-09", 2_500_000),
     "lease": {"rent_vnd": 2_500_000, "occupants": 1, "vehicles": 1},
     "reading": {"period": "2026-10", "electricity_start": "700", "electricity_end": "700"},
     "expected_total_vnd": 2_830_000, "expected_error": None,
     "lines": [_rent_line(2_500_000),
               _inv_line("electricity", "Điện", "0", "3000", 0),
               _inv_line("water", "Nước", "1", "80000", 80_000),
               _inv_line("internet", "Internet", "1", "100000", 100_000),
               _inv_line("parking", "Gửi xe", "1", "100000", 100_000),
               _inv_line("service", "Dịch vụ", "1", "50000", 50_000)],
     "calculation_note": "0*3000=0; 2500000+80000+100000+100000+50000=2830000"},
    {"case_id": "INV-10-large-apartment", "description": "Tiền thuê lớn: căn hộ 2 phòng ngủ.",
     "room_type": "apartment",
     "quote": _inv_quote("INV-10", 16_500_000, electricity=3_500,
                         water={"amount_vnd": 100_000, "mode": "person"}, internet=200_000,
                         parking=150_000, service=800_000),
     "lease": {"rent_vnd": 16_500_000, "occupants": 2, "vehicles": 2},
     "reading": {"period": "2026-10", "electricity_start": "1000", "electricity_end": "1180"},
     "expected_total_vnd": 18_630_000, "expected_error": None,
     "lines": [_rent_line(16_500_000),
               _inv_line("electricity", "Điện", "180", "3500", 630_000),
               _inv_line("water", "Nước", "2", "100000", 200_000),
               _inv_line("internet", "Internet", "1", "200000", 200_000),
               _inv_line("parking", "Gửi xe", "2", "150000", 300_000),
               _inv_line("service", "Dịch vụ", "1", "800000", 800_000)],
     "calculation_note": "180*3500=630000; 2*100000=200000; 2*150000=300000; tổng 18630000"},
    {"case_id": "INV-11-water-reading-missing", "description": "Nước theo m³ nhưng thiếu chỉ số nước.",
     "room_type": "room",
     "quote": _inv_quote("INV-11", 2_500_000, water={"amount_vnd": 20_000, "mode": "m3"}),
     "lease": {"rent_vnd": 2_500_000, "occupants": 1, "vehicles": 1},
     "reading": {"period": "2026-10", "electricity_start": "0", "electricity_end": "100"},
     "expected_total_vnd": None, "expected_error": "invoice_incomplete",
     "lines": None,
     "calculation_note": "Thiếu chỉ số nước → từ chối lập hóa đơn, không đoán số nước"},
    {"case_id": "INV-12-all-included", "description": "Mọi phí đã gồm trong tiền thuê, không cần chỉ số.",
     "room_type": "room",
     "quote": _inv_quote("INV-12", 2_500_000, electricity_included=True,
                         water={"amount_vnd": 80_000, "mode": "person"}, water_included=True,
                         internet_included=True, parking_included=True, service_included=True),
     "lease": {"rent_vnd": 2_500_000, "occupants": 2, "vehicles": 1},
     "reading": None,
     "expected_total_vnd": 2_500_000, "expected_error": None,
     "lines": [_rent_line(2_500_000),
               _included_line("electricity", "Điện"),
               _included_line("water", "Nước"),
               _included_line("internet", "Internet"),
               _included_line("parking", "Gửi xe"),
               _included_line("service", "Dịch vụ")],
     "calculation_note": "Mọi phí included→0; tổng bằng tiền thuê 2500000"},
]


def make_intent_cases() -> dict:
    counts: Counter = Counter(case["intent"] for case in INTENT_CASES)
    splits: Counter = Counter(case["split"] for case in INTENT_CASES)
    return {"notice": NOTICE,
            "purpose": "Gold intent routing cases for the chat graph; authored synthetic utterances, not human judgments.",
            "decision": "predicted = fixed_intent(text) or DemoInterpreter().extract(text).intent; "
                        "matches the _build_chat_graph route node for the demo interpreter.",
            "simulate_finance_status": "gold ahead of backend; AG-02 adds the intent, cases are expected to misroute until then",
            "gate": "measurement_only_no_accuracy_threshold",
            "counts": {"by_intent": dict(sorted(counts.items())), "by_split": dict(sorted(splits.items()))},
            "cases": [dict(case) for case in INTENT_CASES]}


def make_loan_parse_oracle() -> dict:
    return {"notice": NOTICE,
            "purpose": "Independent expected outputs for backend.app.interpreter.parse_loan_terms (AG-02); "
                       "authored by hand, never derived from backend code.",
            "rules": {
                "input": "so khớp trên văn bản đã bỏ dấu (folded); parse tách riêng khỏi việc xếp ý định.",
                "term_months": r"(\d{1,3})\s*thang; hợp lệ 1–60, ngoài khoảng → null; nhiều số khớp thì lấy số đầu tiên.",
                "annual_rate": r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%; dấu phẩy thập phân đổi thành dấu chấm; hợp lệ 0–50, ngoài khoảng → null.",
                "principal_vnd": r"tiền đọc theo (\d+(?:[.,]\d+)?)\s*(trieu|tr\b); dấu phẩy là thập phân (1,5 triệu = 1500000); đơn vị khác (nghìn, đồng) → null."},
            "sources": "Quy tắc đọc kịch bản vay trong docs/tai-chinh-thue.md",
            "cases": [dict(case) for case in LOAN_PARSE_CASES]}


def make_invoice_oracle() -> dict:
    cases = [{**case, "origin": "authored_independent_arithmetic_constants", "synthetic": True,
              "human_cross_check_status": "pending"} for case in INVOICE_CASES]
    return {"notice": NOTICE,
            "purpose": "Hand-computed PMS invoice oracle; inputs mirror the lease quote snapshot, "
                       "meter readings, occupants and vehicles that pms.invoice_lines consumes.",
            "rounding": "mỗi dòng nhân số lượng × đơn giá rồi làm tròn HALF_UP sang VND nguyên; "
                        "phí included_in_rent ra dòng 0; đơn giá/chỉ số thiếu thì từ chối lập, không tính 0.",
            "expected_shape": "mỗi ca có expected_total_vnd hoặc expected_error; lines theo thứ tự dòng hóa đơn "
                              "(rent trước, phí theo thứ tự quote); label chỉ để đọc, suite so tên khoản, số lượng, đơn giá và thành tiền.",
            "cases": cases}


def make_v2_profiles(start_number: int) -> list[dict]:
    rows = []
    for offset, case in enumerate(V2_CASES):
        number = start_number + offset
        gold = Extraction(intent=case["intent"], city=case["city"], area=case["area"],
                          room_type=case["room_type"], bedrooms=case.get("bedrooms"), people=case["people"],
                          preferences=case["prefs"], needs_destination=case["destination"])
        city = case["city"] or case["confirmed_city"]
        profile = {"city": city, "area": case["area"], "room_type": case["room_type"] or "room",
                   "must_amenities": [], "preferences": case["prefs"],
                   "scenario": {"people": case["people"] or 1, "vehicles": 1 if "parking" in case["prefs"] else 0,
                                "electricity_kwh": "140", "water_m3": "3",
                                "moving_vnd": 500_000, "setup_vnd": 1_000_000},
                   **case["profile"]}
        if case["destination"]:
            profile["destination"] = HANOI_DESTINATION if city == "Hà Nội" else THU_DUC_DESTINATION
        soft = case.get("soft") or " ".join(DESCRIPTIONS[AMENITIES.index(name)] for name in case["prefs"]) or None
        profile["soft_description"] = soft
        validated = Profile.model_validate(profile).model_dump(mode="json")
        profile_id = f"profile-{number:03d}"
        money_hint = 20_000_000 if "20 triệu" in case["text"] else None
        rows.append({"profile_id": profile_id, "group_id": profile_id, "template_id": f"authored-v2-case-{offset + 1:02d}",
                     "split": case["split"], "synthetic": True,
                     "gold_origin": "authored_synthetic_case_not_real_customer_validation",
                     "utterances": [{"utterance_id": f"{profile_id}-u1", "text": case["text"],
                                     "gold": gold.model_dump(mode="json")}],
                     "confirmed_profile": validated, "confirmed_soft_description": soft,
                     "confirmation_notice": "Hồ sơ này là kịch bản form đã xác nhận riêng; không phải LLM suy ra dữ kiện thiếu.",
                     "expected_questions": (["city"] if case["city"] is None and case["intent"] == "find_room" else [])
                        + (["budget_meaning"] if money_hint else []) + (["destination"] if case["destination"] else []),
                     "financial_gold": {"budget_hint_vnd": money_hint, "hint_is_confirmation": False}})
    return rows


def make_profiles(count: int = 45) -> list[dict]:
    if count not in (20, 30, 45):
        raise ValueError("Profile count must be 45 (v2), 30 (v1) or the explicitly selected fallback 20.")
    if count == 45:
        return make_profiles(30) + make_v2_profiles(31)
    # Deterministic stratification spreads cities missing/negation/intent cases across splits.
    selected = list(range(30)) if count == 30 else list(range(16)) + [17, 19, 26, 28]
    dev_indices = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9} if count == 30 else {0, 1, 2, 3, 4, 5, 6, 26}
    rows = []
    for number, case_index in enumerate(selected, 1):
        utterance, city, area, people, preferences, destination, intent = CASES[case_index]
        gold = Extraction(intent=intent, city=city, area=area, people=people,
                          preferences=preferences, needs_destination=destination)
        confirmed_people = people or 1
        budget = [3_000_000, 3_500_000, 4_000_000, 4_500_000, 5_000_000][case_index % 5]
        if case_index == 25:
            budget = 500_000  # Purposeful no-match, not a market assertion.
        profile = {"city": "TP.HCM", "area": area, "room_type": "room",
                   "max_monthly_cost_vnd": budget, "max_initial_cash_vnd": 9_000_000,
                   "must_amenities": ["private_bathroom"] if case_index % 3 == 0 else [],
                   "preferences": preferences, "scenario": {"people": confirmed_people,
                    "vehicles": 1 if "parking" in preferences else 0, "electricity_kwh": "140",
                    "water_m3": "3", "moving_vnd": 300_000, "setup_vnd": 200_000}}
        if destination:
            profile["destination"] = {"label": "Điểm đến giả lập", "latitude": 10.735,
                "longitude": 106.721, "uncertainty_m": 50, "max_distance_m": 1_100}
        soft = " ".join(DESCRIPTIONS[AMENITIES.index(name)] for name in preferences)
        if "soft_description" in Profile.model_fields:
            profile["soft_description"] = soft or None
        validated = Profile.model_validate(profile).model_dump(mode="json")
        profile_id = f"profile-{number:03d}"
        utterances = [{"utterance_id": f"{profile_id}-u1", "text": utterance,
                       "gold": gold.model_dump(mode="json")}]
        if case_index % 4 == 0:
            utterances.append({"utterance_id": f"{profile_id}-u2", "text": "Mình đang cân nhắc: " + utterance,
                               "gold": gold.model_dump(mode="json")})
        rows.append({"profile_id": profile_id, "group_id": profile_id,
                     "template_id": f"authored-case-{case_index + 1:02d}",
                     "split": "dev" if case_index in dev_indices else "test", "synthetic": True,
                     "gold_origin": "authored_synthetic_case_not_real_customer_validation",
                     "utterances": utterances, "confirmed_profile": validated,
                     "confirmed_soft_description": soft or None,
                     "confirmation_notice": "Hồ sơ này là kịch bản form đã xác nhận riêng; không phải LLM suy ra dữ kiện thiếu.",
                     "expected_questions": (["city"] if city is None and intent == "find_room" else [])
                        + (["budget_meaning"] if "triệu" in utterance else [])
                        + (["destination"] if destination else []),
                     "financial_gold": {"budget_hint_vnd": 3_500_000 if case_index == 0 else
                          3_000_000 if "3 triệu" in utterance else None,
                                        "hint_is_confirmation": False}})
    return rows


def make_oracles() -> list[dict]:
    """Expected figures are authored constants/calculation notes, never engine output."""
    scenario = {"people": 1, "vehicles": 1, "electricity_kwh": "140", "water_m3": "3",
                "moving_vnd": 300_000, "setup_vnd": 200_000}
    cases = []

    def add(name: str, quote: dict, usage: dict, monthly: int | None, initial: int | None,
            known_month: int, known_initial: int, missing_month=(), missing_initial=(), note=""):
        cases.append({"case_id": name, "quote": quote, "scenario": usage,
                      "expected": {"monthly_total_vnd": monthly, "initial_total_vnd": initial,
                          "monthly_known_vnd": known_month, "initial_known_vnd": known_initial,
                          "missing_monthly": list(missing_month), "missing_initial": list(missing_initial)},
                      "calculation_note": note, "origin": "authored_independent_arithmetic_constants",
                      "synthetic": True, "human_cross_check_status": "pending"})

    add("C01-reference", base_quote(), scenario, 3_250_000, 5_500_000, 3_250_000, 5_500_000,
        note="2500000+140*3000+80000+100000+100000+50000=3250000; 2500000+2500000+300000+200000=5500000")
    two = {**scenario, "people": 2, "vehicles": 2, "electricity_kwh": "200"}
    add("C02-people-vehicles", base_quote(), two, 3_610_000, 5_500_000, 3_610_000, 5_500_000,
        note="2500000+200*3000+2*80000+100000+2*100000+50000=3610000")
    quote = base_quote(); quote["fees"][1] = fee("water", 20_000, "m3")
    add("C03-water-m3", quote, scenario, 3_230_000, 5_500_000, 3_230_000, 5_500_000,
        note="Reference water80000 replaced by3*20000=60000; monthly3230000")
    quote = base_quote(); quote["fees"][2]["included_in_rent"] = True
    add("C04-included", quote, scenario, 3_150_000, 5_500_000, 3_150_000, 5_500_000,
        note="Included internet charged0:3250000-100000=3150000")
    quote = base_quote(); quote["fees"][3]["amount_vnd"] = 0
    add("C05-zero-with-source", quote, scenario, 3_150_000, 5_500_000, 3_150_000, 5_500_000,
        note="Parking explicit0 with source:3250000-100000=3150000")
    quote = base_quote(); quote["fees"][1]["amount_vnd"] = None
    add("C06-unknown-water", quote, scenario, None, 5_500_000, 3_170_000, 5_500_000,
        missing_month=("water",), note="Known3250000-80000=3170000; fullmonthly null")
    quote = base_quote(); quote["fees"] = [f for f in quote["fees"] if f["name"] != "service"]
    add("C07-absent-service", quote, scenario, None, 5_500_000, 3_200_000, 5_500_000,
        missing_month=("service",), note="Known3250000-50000=3200000; requiredservice absent meansnull")
    quote = base_quote(); quote["deposit_vnd"] = None
    add("C08-unknown-deposit", quote, scenario, 3_250_000, None, 3_250_000, 3_000_000,
        missing_initial=("deposit",), note="Known initial2500000+300000+200000=3000000; deposit unknown")
    quote = base_quote(); quote["advance_months"] = 3
    add("C09-three-months", quote, scenario, 3_250_000, 10_500_000, 3_250_000, 10_500_000,
        note="Deposit2500000+first_rent7500000+moving300000+setup200000=10500000; no extra firstmonth")
    quote = base_quote(); quote["one_time_vnd"] = 150_000
    add("C10-one-time", quote, scenario, 3_250_000, 5_650_000, 3_250_000, 5_650_000,
        note="Initial5500000+150000=5650000; monthly unchanged")
    usage = {**scenario, "vehicles": 0, "electricity_kwh": "0", "water_m3": "0"}
    quote = base_quote(); quote["fees"][1] = fee("water", 20_000, "m3")
    add("C11-zero-usage", quote, usage, 2_650_000, 5_500_000, 2_650_000, 5_500_000,
        note="2500000+0+0+100000+0+50000=2650000")
    quote = base_quote(); quote["fees"][0]["amount_vnd"] = "3000.5"
    usage = {**scenario, "electricity_kwh": "1"}
    add("C12-round-half-up", quote, usage, 2_833_001, 5_500_000, 2_833_001, 5_500_000,
        note="Electricity1*3000.5 roundedHALF_UP3001; 2500000+3001+80000+100000+100000+50000=2833001")
    quote = base_quote(); quote["fees"][0]["amount_vnd"] = None; quote["fees"][0]["included_in_rent"] = True
    add("C13-included-unknown-rate", quote, scenario, 2_830_000, 5_500_000, 2_830_000, 5_500_000,
        note="Included electricity0 evenrateunknown:3250000-420000=2830000")
    quote = base_quote(); quote.update(advance_months=None, one_time_vnd=None)
    add("C14-missing-initial", quote, scenario, 3_250_000, None, 3_250_000, 3_000_000,
        missing_initial=("first_rent", "one_time"), note="Known initialdeposit2500000+moving300000+setup200000=3000000")
    quote = base_quote(); quote["fees"].append(fee("cleaning", 75_000))
    add("C15-extra-monthly", quote, scenario, 3_325_000, 5_500_000, 3_325_000, 5_500_000,
        note="Namedextra monthlycleaning75000+3250000=3325000")
    for row in cases:
        row["budget_checks"] = []
    cases[0]["budget_checks"] = [{"monthly_limit_vnd": 3_250_000, "expected_monthly_pass": True},
                                  {"monthly_limit_vnd": 3_249_999, "expected_monthly_pass": False},
                                  {"initial_limit_vnd": 5_500_000, "expected_initial_pass": True},
                                  {"initial_limit_vnd": 5_499_999, "expected_initial_pass": False}]
    cases[5]["budget_checks"] = [{"monthly_limit_vnd": 9_000_000, "expected_monthly_pass": False}]
    return cases + make_affordability_oracles()


def make_affordability_oracles() -> list[dict]:
    """Loan/ratio constants worked out by hand (annuity formula, ratio rounded HALF_UP to 4 places)."""
    scenario = {"people": 1, "vehicles": 1, "electricity_kwh": "140", "water_m3": "3",
                "moving_vnd": 300_000, "setup_vnd": 200_000}
    cases = []

    def add(name, quote, usage, inputs, expected, note):
        cases.append({"case_id": name, "quote": quote, "scenario": usage, "affordability": inputs,
                      "expected": {}, "expected_affordability": expected, "budget_checks": [],
                      "calculation_note": note, "origin": "authored_independent_arithmetic_constants",
                      "synthetic": True, "human_cross_check_status": "pending"})

    spec = {"rent_vnd": 6_000_000, "deposit_vnd": 6_000_000, "advance_months": 1, "one_time_vnd": 0,
            "fees": [fee("electricity", 3500, "kwh"), fee("water", 100_000, "person"), fee("internet", 150_000),
                     fee("parking", 100_000, "vehicle"), fee("service", 200_000)]}
    usage = {"people": 2, "vehicles": 1, "electricity_kwh": "120", "water_m3": "3",
             "moving_vnd": 500_000, "setup_vnd": 1_000_000}
    add("L01-worked-example", spec, usage,
        {"available_cash_vnd": 8_000_000, "monthly_income_vnd": 25_000_000,
         "loan": {"annual_rate": "0.12", "term_months": 6}},
        {"shortfall_vnd": 5_500_000, "installment_vnd": 949_016, "total_interest_vnd": 194_096,
         "burden_vnd": 8_019_016, "housing_ratio": "0.3208", "band": "can_nhac"},
        "docs/tai-chinh-thue.md §7: monthly7070000, initial13500000; P=5500000 r=0.01 n=6 → 949016; "
        "949016*6-5500000=194096; (7070000+949016)/25000000=0.32076→0.3208")
    add("L02-zero-rate", base_quote(), scenario,
        {"available_cash_vnd": 4_300_000, "loan": {"annual_rate": "0", "term_months": 12}},
        {"shortfall_vnd": 1_200_000, "installment_vnd": 100_000, "total_interest_vnd": 0,
         "burden_vnd": 3_350_000, "housing_ratio": None, "band": "chua_ro"},
        "initial5500000-4300000=1200000; r=0 → 1200000/12=100000; 3250000+100000; no income → chua_ro")
    add("L03-no-shortfall", base_quote(), scenario,
        {"available_cash_vnd": 6_000_000, "monthly_income_vnd": 10_000_000,
         "loan": {"annual_rate": "0.12", "term_months": 6}},
        {"shortfall_vnd": 0, "installment_vnd": None, "total_interest_vnd": None,
         "burden_vnd": 3_250_000, "housing_ratio": "0.3250", "band": "can_nhac"},
        "cash covers 5500000 → no loan; 3250000/10000000=0.3250")
    two = {**scenario, "people": 2, "vehicles": 2, "electricity_kwh": "200"}
    add("L04-equal-split", base_quote(), two,
        {"monthly_income_vnd": 6_000_000, "cost_split": "equal"},
        {"shortfall_vnd": None, "installment_vnd": None, "total_interest_vnd": None,
         "burden_vnd": 3_610_000, "housing_ratio": "0.3008", "band": "can_nhac"},
        "C02 monthly3610000; share 1805000; 1805000/6000000=0.30083→0.3008; cash unknown → shortfall null")
    add("L05-exceeds-cap", base_quote(), scenario,
        {"available_cash_vnd": 0, "loan": {"annual_rate": "0.10", "term_months": 12, "max_principal_vnd": 3_000_000}},
        {"shortfall_vnd": 5_500_000, "installment_vnd": 483_537, "total_interest_vnd": 302_444,
         "burden_vnd": 3_733_537, "housing_ratio": None, "band": "chua_ro", "exceeds_max_principal": True},
        "P=5500000 r=0.1/12 n=12 → 483537; 483537*12-5500000=302444; principal above cap 3000000")
    add("L06-boundary-30", base_quote(), scenario, {"monthly_income_vnd": 10_833_334},
        {"shortfall_vnd": None, "installment_vnd": None, "total_interest_vnd": None,
         "burden_vnd": 3_250_000, "housing_ratio": "0.3000", "band": "phu_hop"},
        "3250000/10833334=0.29999998→0.3000; band uses the rounded ratio, ≤0.30 is phu_hop")
    add("L07-boundary-40", base_quote(), scenario, {"monthly_income_vnd": 8_124_999},
        {"shortfall_vnd": None, "installment_vnd": None, "total_interest_vnd": None,
         "burden_vnd": 3_250_000, "housing_ratio": "0.4000", "band": "can_nhac"},
        "3250000/8124999=0.40000005→0.4000; ≤0.40 is can_nhac")
    return cases


def generate(output: Path, count: int = V2_ROOMS, profile_count: int = 45) -> dict:
    rooms, metadata = make_catalog(count)
    profiles = make_profiles(profile_count)
    dump_json(output / "catalog/rooms.json", {"notice": NOTICE, "rooms": rooms})
    dump_json(output / "catalog/pilot.json", {"notice": NOTICE,
                                               "rooms": rooms[:24] + [rooms[min(count, V1_ROOMS) - 1]]})
    dump_json(output / "catalog/metadata.json", metadata)
    dump_json(output / "catalog/alias_fixtures.json", {"notice": "Aliases are fixtures, never extra eligible rooms.",
        "aliases": [{"listing_id": "alias-001-a", "canonical_room_id": rooms[0]["id"], "revision": 1},
                    {"listing_id": "alias-001-b", "canonical_room_id": rooms[0]["id"], "revision": 1}],
        "different_rooms_same_area_not_duplicates": [rooms[0]["id"], rooms[1]["id"]]})
    dump_json(output / "catalog/source_register.json", {"synthetic_ratio": 1.0, "external_inventory_imported": False,
        "notice": NOTICE, "seed_origin": "backend/data/demo_rooms.json (12 authored synthetic fixtures adapted to TP.HCM/room); v2 templates for Hà Nội and studios/apartments",
        "template_seed": SEED, "pii_exclusions": 0,
        "permissions_notice": "No third-party export/crawl or rights claimed. Share only authored synthetic artifacts after project review."})
    for split in ("dev", "test"):
        path = output / f"profiles/{split}/profiles.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                for row in profiles if row["split"] == split), encoding="utf-8")
    dump_json(output / "profiles/split_manifest.json", {"grouping": "profile_id; all paraphrases share split",
        "seed": SEED, "counts": {split: sum(row["split"] == split for row in profiles) for split in ("dev", "test")},
        "profile_ids": {split: [row["profile_id"] for row in profiles if row["split"] == split] for split in ("dev", "test")},
        "scope": "small synthetic prototype; not representative", "fallback": profile_count == 20})
    dump_json(output / "oracles/cost_cases.json", {"notice": NOTICE, "cases": make_oracles()})
    dump_json(output / "profiles/intent_cases.json", make_intent_cases())
    dump_json(output / "oracles/loan_parse_cases.json", make_loan_parse_oracle())
    dump_json(output / "oracles/invoice_cases.json", make_invoice_oracle())
    files = [path for path in output.rglob("*") if path.is_file() and path.suffix in (".json", ".jsonl")
             and "manifests" not in path.parts]
    manifest = {"dataset_id": DATASET_ID if count == V2_ROOMS else "homematch-synthetic-v1",
                "dataset_version": 2 if count == V2_ROOMS else 1,
                "schema_version": "Room/Profile/Extraction imported",
                "generator_seed": SEED, "generator_seed_v2": SEED_V2, "synthetic": True, "canonical_rooms": count,
                "gold_profiles": profile_count, "frozen": False, "stage": "development",
                "labels_status": "pending_human_judgments", "source_notice": NOTICE,
                "artifacts": {str(path.relative_to(output)): file_hash(path) for path in sorted(files)}}
    dump_json(output / "manifests/development_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic HomeMatch inputs; no LLM/network.")
    parser.add_argument("--output", type=Path, default=ROOT / "data")
    parser.add_argument("--rooms", type=int, default=V2_ROOMS)
    parser.add_argument("--profiles", type=int, choices=(20, 30, 45), default=45)
    args = parser.parse_args()
    existing_freeze = args.output / "manifests/input_manifest.json"
    if existing_freeze.exists() and json.loads(existing_freeze.read_text()).get("frozen"):
        parser.error("Dataset has a frozen input manifest; use a new output/version rather than overwriting test inputs.")
    manifest = generate(args.output, args.rooms, args.profiles)
    print(json.dumps({key: manifest[key] for key in ("canonical_rooms", "gold_profiles", "frozen", "labels_status")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
