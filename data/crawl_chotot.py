"""Crawler tin cho thuê từ API công khai của Chợ Tốt → snapshot catalog demo.

Quyết định 30/10/2026: dùng phòng thật làm **catalog demo riêng**, không thay
`data/catalog/rooms.json` (kho giả lập dùng cho eval). Mỗi lần chạy tạo một
snapshot cố định trong `.local/chotot/<snapshot_id>/` (ngoài git, repo công khai):

- `raw/page-*.json`: trang API đã bỏ các khóa trong `DROPPED_KEYS` (CA-01),
  nội dung đã che SĐT/email, tọa độ làm tròn 3 chữ số; ảnh giữ dưới dạng URL;
- `catalog.json`: phòng theo schema `Room`, nạp được bằng `HOMEMATCH_CATALOG_PATH`
  hoặc `python -m backend.manage import --catalog`;
- `manifest.json`: ngày cào, nguồn, số lượng (kèm `raw_ads`, `raw_sha256`),
  SHA-256 của `catalog.json` và khối `privacy`.

Từ 2.2, mỗi phòng thêm: nội dung tin đã che (description), ngày đăng, loại người
đăng (theo bộ lọc nguồn cào), phường cũ/mới, tên đường, ngày trống, kỳ thanh
toán, thời hạn hợp đồng tối thiểu và các khóa tiện ích.

Từ 2.3 (FC-02/FC-03): cào theo hạn mức `--per-city` (mặc định 2.500 tin mỗi
thành phố, mỗi loại phòng một nửa), ưu tiên tin cá nhân (`f=p`), thiếu thì bù
tin môi giới (`f=c`); `poster_kind` lấy từ bộ lọc nguồn, không đoán từ nội dung.
Sau khi cào chạy ba lớp lọc (trùng chính xác, trùng gần đúng giữa các tài khoản,
tin "nhiều phòng/giá từ") rồi mới chọn theo hạn mức, cân bằng hai thành phố.

Từ 2.4 (CA-01…CA-03): raw giữ MỌI trường API trả về (trừ khóa cấm ở `DROPPED_KEYS`)
qua `audit_raw` trước khi ghi; `--all` cào đủ 8 tổ hợp f=p/f=c không giới hạn,
nhóm chạm trần phân trang (total ≥ 9.500) chia theo quận `area_v2`; toàn bộ raw
đẩy lên bảng `chotot_raw_ads`. Mỗi phòng thêm `source_images` (URL ảnh CDN Chợ
Tốt, tối đa 30 — chỉ lưu URL, không tải file), `toilets`, `project_name` và
`poster_name` (tên hiển thị người đăng; chỉ trả qua khối contact cho người đã
đăng nhập — C1b). Không thu thập SĐT, avatar, mã/tên tài khoản hay gọi endpoint
chi tiết. Phí chỉ lấy khi đọc được con số hợp lý trong tin; không đọc được thì
để null (không bao giờ là 0). `landlord_id` là tài khoản demo owner2..d, không
phải người đăng thật.
"""
from __future__ import annotations

import argparse
import calendar
import difflib
import hashlib
import json
import math
import os
import re
import shutil
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse
from decimal import Decimal
from pathlib import Path
from typing import Literal

import httpx

from backend.app.conversations import PHONE, mask_pii
from backend.app.locations import canonical_area, canonical_city
from backend.app.models import Room

ROOT = Path(__file__).resolve().parents[1]
CRAWLER_VERSION = "2.4"
LISTING_URL = "https://gateway.chotot.com/v1/public/ad-listing"
# Trang tin gốc theo list_id (không phải ad_id); Chợ Tốt chuyển hướng 301 sang đúng chuyên mục.
ORIGINAL_URL = "https://www.chotot.com/{list_id}.htm"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) KLTN-research-crawler"
PAGE_SIZE = 50
VIETNAM_TZ = timezone(timedelta(hours=7))
# FC-02: dự phòng 30% cho phần tin bị lọc ở FC-03.
FETCH_HEADROOM = 1.3

REGION_HCM, REGION_HANOI = 13000, 12000
CATEGORY_ROOM, CATEGORY_APARTMENT = 1050, 1010


@dataclass(frozen=True)
class Target:
    region: int
    category: int
    # CA-02: None = cào hết không giới hạn số tin (chỉ dùng với --all).
    max_ads: int | None
    # Bộ lọc nguồn (G1): "p" chỉ tin cá nhân, "c" chỉ tin môi giới/tài khoản chuyên.
    poster: Literal["p", "c"] = "p"
    # CA-02: chia nhỏ nhóm chạm trần phân trang theo mã quận area_v2.
    area_v2: int | None = None
    # CA-02: chỉ với --all và --scale < 1 — dừng mỗi nhóm ở ceil(total × fraction)
    # sau khi biết total từ API (chạy thử 2%); None = cào hết.
    fraction: float | None = None


def targets_for(per_city: int) -> tuple[Target, ...]:
    """FC-02: mỗi thành phố `per_city` tin, mỗi loại phòng một nửa; vòng đầu chỉ
    cào tin cá nhân với dự phòng 1,3×. Vòng bù tin môi giới do crawl() tự thêm
    khi cá nhân không đủ, và crawl_catalog() thêm lại sau khi lọc (tối đa 2 vòng)."""
    goal = math.ceil(per_city / 2 * FETCH_HEADROOM)
    return tuple(Target(region, category, goal, "p")
                 for region in (REGION_HCM, REGION_HANOI)
                 for category in (CATEGORY_ROOM, CATEGORY_APARTMENT))


def all_targets(fraction: float | None = None) -> tuple[Target, ...]:
    """CA-02: đủ 8 tổ hợp thành phố × chuyên mục × f=p/f=c, không giới hạn số tin;
    f=p đứng trước f=c để tin đăng ở cả hai nguồn lấy bản cá nhân trước.
    `fraction` chỉ dùng cho chạy thử (--scale < 1): mỗi nhóm dừng ở ceil(total × fraction)."""
    return tuple(Target(region, category, None, poster, fraction=fraction)
                 for region in (REGION_HCM, REGION_HANOI)
                 for category in (CATEGORY_ROOM, CATEGORY_APARTMENT)
                 for poster in ("p", "c"))


# CA-02: nhóm có total từ ngưỡng này trở lên không cào hết được qua offset
# (trần phân trang API là 10.000) → chia theo quận area_v2 sau khi hết trang.
AREA_SPLIT_THRESHOLD = 9500

# CA-01: raw giữ MỌI trường API trả về (kể cả ảnh, video, khóa mới xuất hiện sau
# này), chỉ bỏ các khóa trong DROPPED_KEYS ở mọi độ sâu. Khóa lạ mặc định được
# giữ và phải qua audit_raw trước khi ghi snapshot.
# 2.2 xác minh thực tế (2026-10-31, ~450 tin mẫu): params chỉ có "Hướng ban công",
# ad_features/pty_characteristics rỗng 100% — nay giữ lại như mọi trường khác.
DROPPED_KEYS = frozenset({
    # Định danh người đăng
    "account_id", "account_oid", "account_name", "avatar", "phone",
    "shop", "shop_alias", "facebook_id", "cta_buttons",
    # Vị trí chính xác
    "street_number", "streetnumber_display", "unitnumber", "unitnumber_display",
    "detail_address", "block", "location", "pty_map", "pty_map_modifier", "pty_map_v2",
})
# C1: seller_info chỉ được giữ hai khóa đếm tin (đã đăng/đã bán).
SELLER_INFO_ALLOWED = frozenset({"live_ads", "sold_ads"})
# URL dạng tọa độ/bản đồ vị trí chính xác (kích thước ghép WxH_WxH) không được lưu.
COORDINATE_URL = re.compile(r"\d+x\d+_\d+x\d+")

# Từ khoá tiện ích, so khớp trên bản bỏ dấu; không thấy thì null (không suy là không có).
KEYWORD_AMENITIES: dict[str, tuple[str, ...]] = {
    "air_conditioning": ("may lanh", "dieu hoa"),
    "private_bathroom": ("wc rieng", "ve sinh rieng", "toilet rieng", "khep kin", "wc trong phong"),
    "window": ("cua so",),
    "balcony": ("ban cong",),
    "parking": ("giu xe", "gui xe", "cho de xe", "de xe", "ham xe", "bai xe", "parking"),
    "quiet": ("yen tinh",),
    "washing_machine": ("may giat",),
    "furniture": ("noi that", "full do", "day du tien nghi"),
    "pets_allowed": ("nuoi thu cung", "nuoi pet", "nuoi cho", "nuoi meo", "pet friendly"),
    "kitchen": ("bep", "ke bep", "cho nau an", "duoc nau an"),
    "wifi": ("wifi", "internet"),
    "elevator": ("thang may",),
    "security_24h": ("bao ve 24", "an ninh 24", "bao ve truc"),
    "camera": ("camera",),
    "loft": ("gac lung", "co gac", "gac xep"),
    "flexible_hours": ("gio giac tu do", "tu do gio giac", "gio tu do"),
    "no_shared_landlord": ("khong chung chu", "ko chung chu", "khong o chung chu"),
    "water_heater": ("nong lanh", "may nuoc nong", "binh nong lanh"),
    "fridge": ("tu lanh",),
}
NEGATION = re.compile(r"\b(?:khong|ko|cam|khong duoc)\s+(?:cho\s+)?(?:\w+\s+){0,1}$")
# Khóa whose keyword itself contains the negation ("không chung chủ"): checking
# NEGATION would misread the phrase as a denial. A bare "chung chủ" then means false.
NO_NEGATION_CHECK = frozenset({"no_shared_landlord"})
SHARED_LANDLORD_POSITIVE = re.compile(r"\b(?:khong|ko)\s+(?:o\s+)?chung chu\b")
SHARED_LANDLORD_NEGATIVE = re.compile(r"\b(?<!khong )(?<!ko )chung chu\b")
HCM_MERGED_AREAS = {"quan 2": "TP. Thủ Đức", "quan 9": "TP. Thủ Đức"}
# A-2: mã `area_v2` → tên quận lập từ dữ liệu thật của snapshot
# chotot-2026-11-07-5k (07/11/2026): đếm `area_name` theo từng `area_v2` trên
# 35.580 tin raw; chỉ mã nào LUÔN khớp đúng một tên mới vào bảng (40/40 mã có
# tên đều khớp duy nhất, không có mã mâu thuẫn). Tên đi qua logic chuẩn hóa sẵn
# có (HCM_MERGED_AREAS, canonical_area); mã không có trong bảng → "Không rõ",
# không đoán từ tên phường hay tọa độ.
AREA_V2_NAMES: dict[int, str] = {
    # Hà Nội
    12073: "Quận Hoàn Kiếm", 12074: "Quận Ba Đình", 12075: "Quận Đống Đa",
    12076: "Quận Hai Bà Trưng", 12077: "Quận Thanh Xuân", 12078: "Quận Tây Hồ",
    12079: "Quận Cầu Giấy", 12080: "Quận Hoàng Mai", 12081: "Quận Long Biên",
    12082: "Huyện Đông Anh", 12084: "Huyện Thanh Trì", 12086: "Quận Hà Đông",
    12088: "Huyện Đan Phượng", 12089: "Huyện Hoài Đức", 12092: "Huyện Chương Mỹ",
    12121: "Quận Nam Từ Liêm", 12123: "Huyện Gia Lâm", 12127: "Huyện Thanh Oai",
    12129: "Quận Bắc Từ Liêm",
    # TP.HCM
    13096: "Quận 1", 13098: "Quận 3", 13099: "Quận 4", 13100: "Quận 5",
    13101: "Quận 6", 13102: "Quận 7", 13103: "Quận 8", 13105: "Quận 10",
    13106: "Quận 11", 13107: "Quận 12", 13108: "Quận Bình Tân",
    13109: "Quận Bình Thạnh", 13110: "Quận Gò Vấp", 13111: "Quận Phú Nhuận",
    13112: "Quận Tân Bình", 13113: "Quận Tân Phú", 13115: "Huyện Bình Chánh",
    13116: "Huyện Củ Chi", 13117: "Huyện Hóc Môn", 13118: "Huyện Nhà Bè",
    13119: "Thành phố Thủ Đức",
}
EMOJI_AND_SYMBOLS = re.compile(r"[^\w\s,.;:()/&+%\-–'\"!?]", re.UNICODE)


def fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", unicodedata.normalize("NFC", value).casefold())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.replace("đ", "d")


# --- Phí trong nội dung tin -------------------------------------------------

AMOUNT = r"(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?(?:k\d{1,3})?)\s*(k|nghin|ngan|tr|trieu|d|vnd|dong)?"


def parse_vnd(number: str, unit: str | None) -> Decimal | None:
    """'3.5k'→3500, '3k8'→3800, '4.000'→4000, '1,2tr'→1200000; không hiểu → None."""
    number = number.strip()
    if re.fullmatch(r"\d+k\d{1,3}", number):
        whole, frac = number.split("k")
        return Decimal(whole) * 1000 + Decimal(frac.ljust(3, "0"))
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", number) and unit not in ("k", "nghin", "ngan", "tr", "trieu"):
        return Decimal(re.sub(r"[.,]", "", number))
    try:
        value = Decimal(number.replace(",", "."))
    except ArithmeticError:
        return None
    if unit in ("k", "nghin", "ngan"):
        return value * 1000
    if unit in ("tr", "trieu"):
        return value * 1_000_000
    return value


@dataclass(frozen=True)
class FeeRule:
    name: str
    mode: str
    pattern: re.Pattern
    low: int
    high: int


def _rule(name: str, mode: str, keyword: str, per: str | None, low: int, high: int) -> FeeRule:
    suffix = rf"\s*(?:/|mot|1|moi|\s)\s*(?:{per})\b" if per else ""
    return FeeRule(name, mode, re.compile(rf"\b(?:{keyword})\b[^0-9\n]{{0,12}}{AMOUNT}{suffix}"), low, high)


FEE_RULES = (
    _rule("electricity", "kwh", r"dien", r"kwh|kw|so|ki|ky", 1_500, 6_000),
    _rule("water", "person", r"nuoc", r"nguoi|ng", 20_000, 300_000),
    _rule("water", "m3", r"nuoc", r"khoi|m3", 5_000, 50_000),
    _rule("internet", "fixed", r"wifi|internet|mang", None, 30_000, 500_000),
    _rule("parking", "vehicle", r"xe|giu xe|gui xe", r"xe|chiec|thang", 30_000, 600_000),
    _rule("service", "fixed", r"dich vu|phi quan ly|phi dv|dv", None, 30_000, 2_000_000),
)
INCLUDED = {
    "internet": re.compile(r"\b(?:free|mien phi)\s+(?:wifi|internet|mang)|\b(?:wifi|internet)\s+(?:free|mien phi)"),
    "parking": re.compile(r"\b(?:free|mien phi)\s+(?:giu |gui |de )?xe|\b(?:giu|gui|de) xe\s+(?:free|mien phi)"),
}


def extract_fees(text: str, ad_id: int | str) -> tuple[list[dict], list[str]]:
    """Phí đọc được từ tin; mỗi phí ghi nguồn là nội dung tin. Trả kèm danh sách phí đọc được."""
    haystack = fold(text)
    fees: dict[str, dict] = {}
    for rule in FEE_RULES:
        if rule.name in fees:
            continue
        for match in rule.pattern.finditer(haystack):
            amount = parse_vnd(match.group(1), match.group(2))
            if amount is not None and rule.low <= amount <= rule.high:
                fees[rule.name] = {"name": rule.name, "amount_vnd": str(amount.quantize(Decimal(1))),
                                   "mode": rule.mode, "included_in_rent": False,
                                   "source": f"chotot://ad/{ad_id}/body#{rule.name}"}
                break
    for name, pattern in INCLUDED.items():
        if name not in fees and pattern.search(haystack):
            fees[name] = {"name": name, "amount_vnd": "0", "mode": "fixed", "included_in_rent": True,
                          "source": f"chotot://ad/{ad_id}/body#{name}-included"}
    return list(fees.values()), sorted(fees)


def detect_amenities(text: str) -> dict[str, bool | None]:
    haystack = fold(text)
    amenities: dict[str, bool | None] = {}
    for name, keywords in KEYWORD_AMENITIES.items():
        value: bool | None = None
        if name in NO_NEGATION_CHECK:
            # "không chung chủ" is itself the amenity: a hit means true, a bare
            # "chung chủ" (without không/ko) means false, nothing found stays null.
            if SHARED_LANDLORD_POSITIVE.search(haystack):
                value = True
            elif SHARED_LANDLORD_NEGATIVE.search(haystack):
                value = False
            amenities[name] = value
            continue
        for keyword in keywords:
            for match in re.finditer(rf"\b{re.escape(keyword)}\b", haystack):
                if NEGATION.search(haystack[max(0, match.start() - 24):match.start()]):
                    value = False if value is None else value
                else:
                    value = True
        amenities[name] = value
    return amenities


# --- Điều khoản thuê trong nội dung tin (kỳ thanh toán, thời hạn, ngày trống) ---

# "đóng/thanh toán/trả N tháng (1 lần|/lần)" hoặc "N tháng đóng 1 lần".
PAYMENT_CYCLE = re.compile(
    r"\b(?:(?:dong|thanh toan|tra)(?: tien)?\s+(\d{1,2})\s*thang\s*(?:/|1\s*|mot\s*)lan\b"
    r"|\b(\d{1,2})\s*thang\s+(?:dong|thanh toan|tra)\s+(?:1\s*|mot\s*)?lan\b)")
# "hợp đồng/HĐ (tối thiểu|ít nhất)? N tháng|N năm" (năm × 12).
MIN_LEASE = re.compile(r"\b(?:hop dong|hd)\s+(?:(?:toi thieu|it nhat)\s+)?(\d{1,2})\s*(thang|nam)\b")
# "trống (từ|từ ngày|ngày)? D/M(YYYY)" → ngày trống gần nhất sau ngày đăng.
# FC-01: "trống" folds to "trong", so "trống ngày 5/11" must read as a date,
# not fall through to available-now.
AVAILABLE_FROM = re.compile(
    r"\btrong\s+(?:tu\s+)?(?:ngay\s+)?(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?\b")
# "trống ngay/vào ở ngay" only when no specific day follows: "trống ngày 5/11"
# names a date and "trống ngày mai" is unresolvable, so neither is "now".
AVAILABLE_NOW = re.compile(
    r"\b(?:trong ngay|vao o ngay)\b(?!\s*(?:tu\s+|ngay\s+)?(?:\d{1,2}[/.\-]\d{1,2}|\bmai\b))")


def parse_payment_cycle(haystack: str) -> int | None:
    match = PAYMENT_CYCLE.search(haystack)
    if match is None:
        return None
    months = int(match.group(1) or match.group(2))
    return months if 1 <= months <= 12 else None


def parse_min_lease(haystack: str) -> int | None:
    match = MIN_LEASE.search(haystack)
    if match is None:
        return None
    months = int(match.group(1)) * (12 if match.group(2) == "nam" else 1)
    return months if 1 <= months <= 60 else None


def _shift_months(value: date, months: int) -> date:
    """Same day `months` months away, clamped to the last valid day (29/2 → 28/2)."""
    total = value.year * 12 + value.month - 1 + months
    year, index = divmod(total, 12)
    month = index + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _resolve_past_vacancy(candidate: date, posted_date: date) -> date | None:
    """FC-01: a vacancy date at or before the posting day means either the room
    is vacant now (within 90 days back → the posting day), the poster means next
    year (more than six months back), or the phrasing is ambiguous (in between
    → None, never guessed)."""
    if (posted_date - candidate).days <= 90:
        return posted_date
    if candidate < _shift_months(posted_date, -6):
        return date(posted_date.year + 1, candidate.month, candidate.day)
    return None


def parse_available_from(haystack: str, posted_at: datetime | None) -> str | None:
    """Ngày trống dạng ISO; phải có mốc ngày đăng để tính "gần nhất sau ngày đăng"."""
    if posted_at is None:
        return None
    posted_date = posted_at.astimezone(VIETNAM_TZ).date()
    if match := AVAILABLE_FROM.search(haystack):
        day, month = int(match.group(1)), int(match.group(2))
        year = match.group(3)
        try:
            if year is not None:
                candidate = date(int(year) if len(year) == 4 else 2000 + int(year), month, day)
            else:
                candidate = date(posted_date.year, month, day)
                # Ngày trống là ngày gần nhất SAU ngày đăng; đã qua thì theo luật 90 ngày/6 tháng.
                if candidate <= posted_date:
                    candidate = _resolve_past_vacancy(candidate, posted_date)
                    if candidate is None:
                        return None
        except ValueError:
            return None
        return candidate.isoformat()
    if AVAILABLE_NOW.search(haystack):
        return posted_date.isoformat()
    return None


def extract_terms(text: str, posted_at: datetime | None) -> dict:
    """Điều khoản đọc được từ tin; chỗ nào khớp không rõ thì null (F5, không suy đoán)."""
    haystack = fold(text)
    return {"payment_cycle_months": parse_payment_cycle(haystack),
            "min_lease_months": parse_min_lease(haystack),
            "available_from": parse_available_from(haystack, posted_at)}


# --- Chuẩn hóa một tin ------------------------------------------------------

def clean_title(subject: str) -> str:
    # Chợ Tốt có tin gửi chữ tổ hợp (NFD); phải gộp dấu trước khi lọc ký hiệu, kẻo mất dấu.
    title = EMOJI_AND_SYMBOLS.sub(" ", mask_pii(unicodedata.normalize("NFC", subject)))
    title = " ".join(title.split()).strip(" -–,.")
    return title[:120] or "Tin cho thuê"


def city_and_area(ad: dict) -> tuple[str | None, str]:
    city = canonical_city(ad.get("region_name"))
    raw_area = " ".join(str(ad.get("area_name") or "").split())
    if not raw_area:
        # A-2: thiếu `area_name` thì suy quận từ mã `area_v2` đã đối chiếu;
        # mã lạ/không có trong bảng → "Không rõ", không đoán từ dữ liệu khác.
        name = AREA_V2_NAMES.get(ad.get("area_v2"))
        if name is None:
            return city, "Không rõ"
        merged = HCM_MERGED_AREAS.get(fold(name)) if city == "TP.HCM" else None
        return city, merged or canonical_area(name, city) or name
    merged = HCM_MERGED_AREAS.get(fold(raw_area)) if city == "TP.HCM" else None
    return city, merged or canonical_area(raw_area, city) or raw_area


def room_type_of(ad: dict) -> tuple[str, int | None]:
    subject = fold(str(ad.get("subject") or ""))
    if ad.get("category") == CATEGORY_APARTMENT:
        bedrooms = ad.get("rooms")
        if "studio" in subject or not isinstance(bedrooms, int) or bedrooms < 1:
            return "studio", None
        return "apartment", min(bedrooms, 5)
    return ("studio" if "studio" in subject else "room"), None


def source_of(ad: dict) -> str:
    """Link tin gốc để người thuê liên hệ người đăng ngay trên Chợ Tốt; thiếu list_id thì giữ mã nội bộ."""
    list_id = ad.get("list_id")
    return ORIGINAL_URL.format(list_id=list_id) if isinstance(list_id, int) else f"chotot://ad/{ad['ad_id']}"


def landlord_for(city: str, ad_id: int) -> str:
    # Tài khoản demo chủ nhà theo thành phố; không phải người đăng tin thật.
    return "owner1" if city == "Hà Nội" else "owner2"


def features_from(amenities: dict[str, bool | None]) -> str | None:
    labels = {"window": "có cửa sổ", "balcony": "có ban công", "quiet": "khu yên tĩnh",
              "furniture": "có nội thất", "washing_machine": "có máy giặt"}
    parts = [label for key, label in labels.items() if amenities.get(key)]
    return ("Theo tin đăng: " + ", ".join(parts) + ".") if parts else None


def feature_text(ad: dict) -> str:
    items = ((ad.get("feature_params") or {}).get("compare") or {}).get("items") or []
    return " ".join(str(item.get("value") or "") for item in items if isinstance(item, dict))


def furnishing_amenity(ad: dict) -> bool | None:
    """Tiện nghi từ mã `furnishing_rent`. Nhãn thật đã xác minh 31/10/2026 trên
    API (`feature_params.compare.items`, nhãn "Tình trạng nội thất") và trang tin:
    1 = "Nội thất cao cấp", 2 = "Nội thất đầy đủ", 3 = "Nhà trống". Thiếu mã thì
    trả None để từ khóa nội dung quyết định, không suy đoán."""
    code = ad.get("furnishing_rent")
    if code in (1, 2):
        return True
    if code == 3:
        return False
    return None


def posted_time_of(ad: dict) -> datetime | None:
    """`list_time` là epoch mili giây (UTC); thiếu hoặc sai kiểu thì None."""
    list_time = ad.get("list_time")
    if not isinstance(list_time, (int, float)) or list_time <= 0:
        return None
    return datetime.fromtimestamp(list_time / 1000, tz=timezone.utc)


def clean_text(value) -> str | None:
    """Chuẩn hóa khoảng trắng; rỗng thì None. Tên đường/phường, không có số nhà."""
    if not isinstance(value, str):
        return None
    cleaned = " ".join(unicodedata.normalize("NFC", value).split())
    return cleaned or None


def poster_kind_of(ad: dict, poster: Literal["p", "c"] | None) -> str | None:
    """G1: poster_kind chỉ đến từ bộ lọc nguồn của lượt cào; nội dung tin không
    được dùng để đoán. poster=None giữ hành vi cũ (company_ad=True → broker)."""
    if poster == "p":
        return "individual"
    if poster == "c":
        return "broker"
    return "broker" if ad.get("company_ad") is True else None


def source_images_of(ad: dict) -> list[str]:
    """CA-04/C5: URL ảnh CDN Chợ Tốt theo thứ tự của tin, tối đa 30; URL khác
    cdn.chotot.com bị loại. Chỉ lưu URL, không tải file."""
    images = ad.get("images")
    images = images if isinstance(images, list) else []
    urls = [url for url in images
            if isinstance(url, str) and url.startswith("https://cdn.chotot.com/")]
    return urls[:30]


# Cloudflare Stream (videodelivery.net) — chỉ nhận URL https, không khoảng
# trắng, hostname ĐÚNG bằng videodelivery.net (không subdomain) và path đúng
# dạng manifest/thumbnail với mã video 32 ký tự hex (chặn lỗi
# che nhầm dãy số trong mã video khi lưu raw).
VIDEO_HOST = "videodelivery.net"
STREAM_MANIFEST_PATH = re.compile(r"/[0-9a-f]{32}/manifest/video\.m3u8")
STREAM_THUMBNAIL_PATH = re.compile(r"/[0-9a-f]{32}/thumbnails/thumbnail\.jpg")


def is_stream_video_url(value: str, *, thumbnail: bool = False) -> bool:
    """True khi chuỗi là URL video/thumbnail Cloudflare Stream đúng dạng — chỉ
    những URL này được miễn che khi lưu raw và được nhận vào source_videos."""
    if not isinstance(value, str) or not value.lower().startswith("https://"):
        return False
    if re.search(r"\s", value):
        return False
    parsed = urlparse(value)
    if (parsed.hostname or "").lower() != VIDEO_HOST:
        return False
    shape = STREAM_THUMBNAIL_PATH if thumbnail else STREAM_MANIFEST_PATH
    return bool(shape.fullmatch(parsed.path))


def _video_candidates(ad: dict) -> list[dict]:
    """Các mục video thô của tin: dict từ khóa `video` và `videos` (list)."""
    candidates: list[dict] = []
    video = ad.get("video")
    if isinstance(video, dict):
        candidates.append(video)
    elif isinstance(video, list):
        candidates.extend(entry for entry in video if isinstance(entry, dict))
    videos = ad.get("videos")
    if isinstance(videos, list):
        candidates.extend(entry for entry in videos if isinstance(entry, dict))
    return candidates


def source_videos_of(ad: dict) -> list[dict]:
    """Video của tin (nếu có): {url, thumbnail}, tối đa 3. B-A-2: chỉ nhận url
    đúng dạng path manifest và thumbnail đúng dạng path thumbnail; mục sai dạng
    bị bỏ, không giữ URL hỏng."""
    result: list[dict] = []
    for entry in _video_candidates(ad):
        url = entry.get("url")
        if not is_stream_video_url(url):
            continue
        thumbnail = entry.get("thumbnail") or entry.get("thumbnail_url") or entry.get("image")
        if not (isinstance(thumbnail, str) and is_stream_video_url(thumbnail, thumbnail=True)):
            continue
        result.append({"url": url, "thumbnail": thumbnail})
    return result[:3]


def videos_dropped_bad_shape(ad: dict) -> int:
    """A-3: số mục video bị bỏ vì sai dạng (đã trừ các mục bị cắt bởi trần 3 —
    trả số mục ứng viên không qua được kiểm tra dạng)."""
    candidates = _video_candidates(ad)
    dropped = sum(
        1 for entry in candidates
        if not (is_stream_video_url(entry.get("url"))
                and isinstance(entry.get("thumbnail"), str)
                and is_stream_video_url(entry["thumbnail"], thumbnail=True)))
    return dropped


# --- Diện tích đọc từ nội dung tin -----------------------------
# Chỉ nhận khi có "rộng"/"diện tích"/"dt" đứng trước số, hoặc số đi liền
# m2/m²/met vuông. "cách 45m", "hẻm 3m" không phải diện tích. Dùng bản bỏ dấu.
AREA_MIN, AREA_MAX = 5, 300
AREA_KEYWORD_TEXT = re.compile(
    r"(?<!\w)(?:rong|dien tich|dt)\s*:?\s*(\d{1,3}(?:[.,]\d)?)(?!\d)"
    r"\s*(?:m2|m²|met vuong|m vuong|m)?")
AREA_UNIT_TEXT = re.compile(r"(?<!\d)(\d{1,3}(?:[.,]\d)?)\s*(?:m2|m²|met vuong|m vuong)\b")


def area_from_text_of(*texts: str) -> float | None:
    """Đọc diện tích từ tiêu đề rồi nội dung; chỉ nhận 5–300 m², không đọc được
    thì None — không điền số giả."""
    for text in texts:
        haystack = fold(text)
        for pattern in (AREA_KEYWORD_TEXT, AREA_UNIT_TEXT):
            for match in pattern.finditer(haystack):
                try:
                    value = float(str(match.group(1)).replace(",", "."))
                except ValueError:
                    continue
                if AREA_MIN <= value <= AREA_MAX:
                    return value
    return None


# --- Trường mới từ params/khóa đã biết -------------------------
# Chỉ nhận NHÃN chữ khớp từ khóa (params có cặp label/value); chỉ có mã số chưa
# xác minh nghĩa thì null, không tự đoán.

# B-2: mã `balconydirection` → nhãn, đối chiếu từ dữ liệu thật của snapshot
# chotot-2026-11-07-5k (07/11/2026): mỗi mã xuất hiện cùng tin với nhãn
# `params` "Hướng ban công" và LUÔN khớp đúng một nhãn — 1 Đông/57, 2 Tây/6,
# 3 Nam/35, 4 Bắc/5, 5 Đông Bắc/21, 6 Đông Nam/74, 7 Tây Bắc/11, 8 Tây Nam/7.
# KHÔNG áp cho `direction`: chưa có nhãn thật nào để đối chiếu.
BALCONY_DIRECTION_NAMES: dict[int, str] = {
    1: "Hướng Đông", 2: "Hướng Tây", 3: "Hướng Nam", 4: "Hướng Bắc",
    5: "Hướng Đông Bắc", 6: "Hướng Đông Nam", 7: "Hướng Tây Bắc",
    8: "Hướng Tây Nam",
}


def _labelled_param(ad: dict, keywords: tuple[str, ...],
                    exclude: tuple[str, ...] = ()) -> str | None:
    """Đọc value từ cặp label/value của `params`. Dữ liệu thật (snapshot
    chotot-2026-11-07-5k) cho `params` là DANH SÁCH mục {id, label, value};
    chấp nhận thêm dạng dict cũ để không vỡ test giả lập cũ."""
    params = ad.get("params")
    entries = []
    if isinstance(params, list):
        entries = [entry for entry in params if isinstance(entry, dict)]
    elif isinstance(params, dict):
        entries = [entry for entry in params.values() if isinstance(entry, dict)]
    for entry in entries:
        label = fold(str(entry.get("label") or ""))
        if any(keyword in label for keyword in keywords) \
                and not any(word in label for word in exclude):
            value = entry.get("value")
            if isinstance(value, str) and value.strip():
                return clean_text(value)
    return None


def _plain_label_or_none(value) -> str | None:
    """Nhận nhãn chữ; mã thuần số chưa xác minh nghĩa thì null."""
    text = clean_text(value) if isinstance(value, str) else None
    return text if text and not text.isdigit() else None


def floor_of(ad: dict) -> str | None:
    value = _labelled_param(ad, ("tang", "lau"))
    if value:
        return value
    number = ad.get("floornumber")
    if isinstance(number, int) and not isinstance(number, bool) and number >= 0:
        return str(number)
    return None


def direction_of(ad: dict) -> str | None:
    value = _labelled_param(ad, ("huong",), ("ban cong",))
    if value:
        return value
    # Chỉ nhận nhãn chữ; mã số của `direction` chưa có nhãn thật để đối chiếu
    # nên luôn null (B-3), không suy từ bảng hướng ban công.
    return _plain_label_or_none(ad.get("direction"))


def balcony_direction_of(ad: dict) -> str | None:
    value = _labelled_param(ad, ("ban cong",))
    if value:
        return value
    code = ad.get("balconydirection")
    if isinstance(code, int) and not isinstance(code, bool):
        return BALCONY_DIRECTION_NAMES.get(code)
    if isinstance(code, str) and code.strip().isdigit():
        return BALCONY_DIRECTION_NAMES.get(int(code))
    return _plain_label_or_none(code)


def property_subtype_of(ad: dict) -> str | None:
    return _labelled_param(ad, ("loai hinh",))


def poster_name_of(ad: dict) -> str | None:
    """C1/C1b: chỉ tên hiển thị cấp trên cùng; che SĐT/email nằm trong tên."""
    name = clean_text(ad.get("full_name"))
    return mask_pii(name) if name else None


def to_room(ad: dict, poster: Literal["p", "c"] | None = None) -> tuple[dict | None, str | None, list[str]]:
    """Trả (room, lý do bỏ, phí đọc được)."""
    ad_id = ad.get("ad_id")
    price = ad.get("price")
    if not isinstance(ad_id, int):
        return None, "ad_id_missing", []
    if ad.get("is_price_not_valid") or not isinstance(price, (int, float)) or price <= 0:
        return None, "price_missing", []
    if not 500_000 <= price <= 50_000_000:
        return None, "price_out_of_range", []
    city, area = city_and_area(ad)
    if city not in ("TP.HCM", "Hà Nội"):
        return None, "city_out_of_scope", []
    subject = str(ad.get("subject") or "")
    # Nội dung tin đã che SĐT/email trước khi dùng cho mọi trích xuất.
    body = mask_pii(unicodedata.normalize("NFC", str(ad.get("body") or "")))
    images = source_images_of(ad)
    if not images:
        # A/B-1: catalog chỉ nhận tin có ít nhất 1 ảnh; tin không ảnh bị bỏ,
        # raw vẫn giữ (CA-02.5).
        return None, "no_image", []
    # A-2/A-3: thiếu size thì đọc từ tiêu đề rồi nội dung; có size nhưng ngoài
    # 5–300 m² vẫn loại; không đọc được thì null, không điền số giả.
    size = ad.get("size")
    has_size = isinstance(size, (int, float)) and not isinstance(size, bool)
    if has_size and not 5 <= size <= 300:
        return None, "size_out_of_range", []
    if not has_size:
        size = area_from_text_of(subject, body)
    text = f"{subject}\n{body}\n{feature_text(ad)}"
    fees, fee_names = extract_fees(text, ad_id)
    amenities = detect_amenities(text)
    # Ưu tiên thuộc tính cấu trúc: mã nội thất đã xác minh nhãn đè lên từ khóa.
    furnishing = furnishing_amenity(ad)
    if furnishing is not None:
        amenities["furniture"] = furnishing
    posted_at = posted_time_of(ad)
    terms = extract_terms(text, posted_at)
    room_type, bedrooms = room_type_of(ad)
    latitude, longitude = ad.get("latitude"), ad.get("longitude")
    has_coords = isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)) and latitude and longitude
    deposit = ad.get("deposit")
    room = {
        "id": f"chotot-{ad_id}",
        "revision": 1,
        "title": clean_title(subject),
        "city": city,
        "area": area,
        "room_type": room_type,
        "bedrooms": bedrooms,
        "capacity": None,
        "area_m2": float(size) if size is not None else None,
        "published": True,
        "available": True,
        "amenities": amenities,
        # Làm tròn ~100 m: vị trí công khai chỉ cần gần đúng.
        "latitude": round(float(latitude), 3) if has_coords else None,
        "longitude": round(float(longitude), 3) if has_coords else None,
        "location_accuracy": "approximate" if has_coords else "area_only",
        "uncertainty_m": 300.0 if has_coords else None,
        "quote": {
            "rent_vnd": int(price),
            "deposit_vnd": int(deposit) if isinstance(deposit, (int, float)) and deposit > 0 else None,
            "advance_months": None,
            "payment_cycle_months": terms["payment_cycle_months"],
            "min_lease_months": terms["min_lease_months"],
            "fees": fees,
            "one_time_vnd": None,
        },
        "source": source_of(ad),
        "synthetic": False,
        "features_text": features_from(amenities),
        "landlord_id": landlord_for(city, ad_id),
        # Nội dung tin: bản đã che SĐT/email, cắt còn 4000 ký tự.
        "description": body[:4000] or None,
        "posted_at": posted_at.isoformat() if posted_at else None,
        # G1: theo bộ lọc nguồn của lượt cào, không đoán từ nội dung tin.
        "poster_kind": poster_kind_of(ad, poster),
        "ward": clean_text(ad.get("ward_name")),
        "ward_2025": clean_text(ad.get("ward_name_v3")),
        "street": clean_text(ad.get("street_name")),
        "available_from": terms["available_from"],
        # CA-04: ảnh CDN theo thứ tự tin; nhà vệ sinh và tên dự án theo mã API,
        # không có thì rỗng/null; poster_name chỉ đi qua khối contact (C1b).
        "source_images": images,
        "source_videos": source_videos_of(ad),
        "toilets": ad.get("toilets") if isinstance(ad.get("toilets"), int)
        and not isinstance(ad.get("toilets"), bool) and ad.get("toilets") >= 0 else None,
        "project_name": clean_text(ad.get("pty_project_name")),
        "poster_name": poster_name_of(ad),
        # C-1: tầng, hướng, hướng ban công, loại hình — chỉ từ nhãn/khóa đã biết,
        # mã số chưa xác minh nghĩa thì null.
        "floor": floor_of(ad),
        "direction": direction_of(ad),
        "balcony_direction": balcony_direction_of(ad),
        "property_subtype": property_subtype_of(ad),
    }
    return Room.model_validate(room).model_dump(mode="json"), None, fee_names


def is_chotot_url(value: str) -> bool:
    """URL http/https KHÔNG có khoảng trắng và host (theo hostname, không so
    chuỗi con) là chotot.com hoặc subdomain của nó. Chuỗi khác là văn bản."""
    if not value or re.search(r"\s", value):
        return False
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return parsed.scheme in ("http", "https") and \
        (host == "chotot.com" or host.endswith(".chotot.com"))


def _clean_raw_string(value: str) -> str:
    """URL Chợ Tốt và URL video/thumbnail Cloudflare Stream ĐÚNG dạng giữ
    nguyên (B-A-1: mã video 32 hex bị mask_pii che nhầm là SĐT); mọi chuỗi
    khác — văn bản, URL lạ, URL sai dạng — đều che PII."""
    text = unicodedata.normalize("NFC", value)
    if is_chotot_url(text) or is_stream_video_url(text) \
            or is_stream_video_url(text, thumbnail=True):
        return text
    return mask_pii(text)


def _strip_raw_value(value, top_level: bool = True):
    """Duyệt đệ quy dict/list: bỏ khóa cấm ở mọi độ sâu; `full_name` chỉ giữ ở
    cấp trên cùng của tin; `seller_info` chỉ còn live_ads/sold_ads; tọa độ làm
    tròn 3 chữ số; chuỗi (cả trong list) là URL Chợ Tốt thì giữ, còn lại che PII."""
    if isinstance(value, str):
        return _clean_raw_string(value)
    if isinstance(value, list):
        return [_strip_raw_value(item, top_level=False) for item in value]
    if not isinstance(value, dict):
        return value
    cleaned: dict = {}
    for key, item in value.items():
        if key in DROPPED_KEYS:
            continue
        if not top_level and key == "full_name":
            continue
        if key == "seller_info" and isinstance(item, dict):
            cleaned[key] = {name: _strip_raw_value(sub, top_level=False)
                            for name, sub in item.items() if name in SELLER_INFO_ALLOWED}
            continue
        if key in ("latitude", "longitude") and isinstance(item, (int, float)) \
                and not isinstance(item, bool):
            cleaned[key] = round(float(item), 3)
            continue
        cleaned[key] = _strip_raw_value(item, top_level=False)
    return cleaned


def strip_raw(ad: dict) -> dict:
    return _strip_raw_value(dict(ad))


def audit_raw(ad: dict) -> list[str]:
    """CA-01: kiểm tra bản raw đã strip trước khi ghi; trả về danh sách vi phạm.
    Chỉ ghi TÊN KHÓA/vị trí, không bao giờ ghi giá trị."""
    violations: list[str] = []

    def walk(value, path: str) -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
            return
        if isinstance(value, dict):
            for key, item in value.items():
                key_path = f"{path}.{key}" if path else str(key)
                if key in DROPPED_KEYS:
                    violations.append(f"dropped_key:{key_path}")
                    continue
                if key == "seller_info" and isinstance(item, dict):
                    for name in sorted(set(item) - SELLER_INFO_ALLOWED):
                        violations.append(f"seller_info_key:{key_path}.{name}")
                    walk({name: item[name] for name in item if name in SELLER_INFO_ALLOWED}, key_path)
                    continue
                if key in ("latitude", "longitude"):
                    text = f"{float(item):.10f}" if isinstance(item, (int, float)) \
                        and not isinstance(item, bool) else ""
                    decimals = len(text.split(".", 1)[1].rstrip("0")) if "." in text else 0
                    if decimals > 3:
                        violations.append(f"coordinates:{key_path}")
                    continue
                walk(item, key_path)
            return
        if isinstance(value, str):
            if is_chotot_url(value):
                # URL ảnh/video Chợ Tốt: chỉ chặn mẫu tọa độ, không báo nhầm
                # dãy số (mã ảnh) trong URL.
                if COORDINATE_URL.search(value):
                    violations.append(f"coordinate_url:{path}")
            elif PHONE.search(value):
                # Văn bản hoặc URL ngoài chotot.com (zalo, facebook…) còn SĐT.
                violations.append(f"phone_in_text:{path}")

    walk(ad, "")
    return violations


# --- Cào ----------------------------------------------------------------------

class CrawlTimeout(Exception):
    """FC-02/C2: quá --max-minutes; dừng sạch, không ghi snapshot."""


class RawAuditError(Exception):
    """CA-01: bản raw còn vi phạm riêng tư; dừng sạch, không ghi snapshot."""


def fetch_page(client: httpx.Client, target: Target, offset: int, limit: int) -> dict:
    params = {"region_v2": target.region, "cg": target.category, "st": "u", "limit": limit,
              "o": offset, "f": target.poster}
    if target.area_v2 is not None:
        params["area_v2"] = target.area_v2
    for attempt in range(4):
        response = client.get(LISTING_URL, params=params)
        if response.status_code in (429, 500, 502, 503, 504):
            time.sleep(5 * (attempt + 1))
            continue
        response.raise_for_status()
        return response.json()
    response.raise_for_status()
    return response.json()


def _process_ad(ad: dict, poster: Literal["p", "c"], rooms: list, seen_ids: set,
                seen_keys: set, stats: dict) -> None:
    """Lớp 1 khử trùng + to_room cho một tin — dùng chung cho crawl() và
    rebuild_catalog() (E-1). `account_id` chỉ dùng ở đây; raw đã strip không
    còn account_id nên rebuild khử trùng bằng tiêu đề/giá/diện tích."""
    def skip(reason: str):
        stats["skipped"][reason] = stats["skipped"].get(reason, 0) + 1

    ad_id = ad.get("ad_id")
    # Tin đăng lại: cùng người đăng, cùng tiêu đề, giá, diện tích.
    key = (ad.get("account_id"), fold(str(ad.get("subject") or "")), ad.get("price"), ad.get("size"))
    if ad_id in seen_ids or key in seen_keys:
        skip("duplicate")
        return
    seen_ids.add(ad_id)
    seen_keys.add(key)
    try:
        room, reason, fee_names = to_room(ad, poster)
    except Exception as error:  # noqa: BLE001 - ghi nhận rồi bỏ tin lỗi schema
        skip(f"schema:{type(error).__name__}")
        return
    if room is None:
        skip(reason or "unknown")
        return
    for name in fee_names:
        stats["fees_found"][name] = stats["fees_found"].get(name, 0) + 1
    if room["area_m2"] is not None and not isinstance(ad.get("size"), (int, float)):
        # A-2: diện tích đọc từ tiêu đề/nội dung (không có size từ API).
        stats["area_from_text"] += 1
    if not str(ad.get("area_name") or "").strip():
        # A-4: quận suy từ mã area_v2 hay vẫn "Không rõ".
        if room["area"] == "Không rõ":
            stats["area_unknown"] += 1
        else:
            stats["area_from_area_v2"] += 1
    if room["source_videos"]:
        stats["with_videos"] += 1
    stats["videos_dropped_bad_shape"] += videos_dropped_bad_shape(ad)
    rooms.append(room)


def crawl(targets: tuple[Target, ...], sleep_s: float, raw_dir: Path, log=print,
          deadline: float | None = None) -> tuple[list[dict], dict]:
    """Cào từng target theo thứ tự; lớp 1 trùng chính xác (cùng ad_id hoặc cùng
    account_id + tiêu đề + giá + diện tích, account_id chỉ dùng ở đây — G4) giữ
    nguyên như 2.2. Target `f=p` thiếu so với max_ads thì tự cào thêm `f=c` cho
    phần thiếu × 1,3 (FC-02.3); với `max_ads=None` (--all, CA-02) không có vòng bù.
    Nhóm không giới hạn mà `total >= 9500` (gần trần phân trang 10.000) thì cào
    lại từng quận `area_v2` đã thấy; quận vẫn chạm ngưỡng chỉ ghi cảnh báo.
    Quá deadline thì raise CrawlTimeout (C2)."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    rooms: list[dict] = []
    seen_ids: set[int] = set()
    seen_keys: set[tuple] = set()
    stats: dict = {"pages": 0, "ads_seen": 0, "raw_ads": 0, "kept": 0, "skipped": {}, "fees_found": {},
                   "image_mismatch": 0, "area_from_text": 0, "with_videos": 0,
                   "area_from_area_v2": 0, "area_unknown": 0, "videos_dropped_bad_shape": 0,
                   "capped_groups": [], "capped_areas": [], "by_target": []}

    def skip(reason: str):
        stats["skipped"][reason] = stats["skipped"].get(reason, 0) + 1

    def run_target(target: Target) -> None:
        fetched = 0
        kept_before = len(rooms)
        mismatch_before = stats["image_mismatch"]
        total = None
        seen_areas: set[int] = set()
        while target.max_ads is None or fetched < target.max_ads:
            if deadline is not None and time.monotonic() > deadline:
                raise CrawlTimeout(f"Quá thời hạn {target.region}/{target.category}/f={target.poster}")
            limit = PAGE_SIZE if target.max_ads is None else min(PAGE_SIZE, target.max_ads - fetched)
            if target.fraction is not None and total is not None:
                # Chạy thử: trang cuối lấy đúng phần còn thiếu của ceil(total × fraction).
                limit = min(limit, max(1, math.ceil(total * target.fraction) - fetched))
            payload = fetch_page(client, target, fetched, limit)
            total = payload.get("total", total)
            ads = payload.get("ads") or []
            if not ads:
                break
            seen_areas.update(ad.get("area_v2") for ad in ads if isinstance(ad.get("area_v2"), int))
            area_tag = "" if target.area_v2 is None else f"-a{target.area_v2}"
            page_name = (f"page-{target.region}-{target.category}-{target.poster}"
                         f"{area_tag}-{fetched // PAGE_SIZE:03d}.json")
            stripped = [strip_raw(ad) for ad in ads]
            # CA-01: mọi tin phải qua audit trước khi raw chạm đĩa; vi phạm là dừng
            # sạch, không ghi snapshot. Thông báo chỉ nêu tên khóa, không nêu giá trị.
            for index, raw_ad in enumerate(stripped):
                problems = audit_raw(raw_ad)
                if problems:
                    raise RawAuditError(
                        f"Tin thứ {index} trang {page_name} còn vi phạm riêng tư: " + ", ".join(problems))
            (raw_dir / page_name).write_text(
                json.dumps(stripped, ensure_ascii=False, indent=1), encoding="utf-8")
            stats["pages"] += 1
            stats["ads_seen"] += len(ads)
            stats["raw_ads"] += len(stripped)
            stats["image_mismatch"] += sum(
                1 for ad in ads if isinstance(ad.get("number_of_images"), int)
                and ad["number_of_images"] != len(ad.get("images") or []))
            for ad in ads:
                _process_ad(ad, target.poster, rooms, seen_ids, seen_keys, stats)
            fetched += len(ads)
            ceiling = "hết" if target.max_ads is None else str(target.max_ads)
            log(f"  region={target.region} cg={target.category} f={target.poster}"
                f" area={target.area_v2} fetched={fetched}/{ceiling or total or 0} kept_total={len(rooms)}")
            if total is not None and fetched >= total:
                break
            # CA-02: chạy thử --scale < 1 với --all — mỗi nhóm dừng ở ceil(total × fraction).
            if target.fraction is not None and total is not None \
                    and fetched >= math.ceil(total * target.fraction):
                break
            time.sleep(sleep_s)
        stats["by_target"].append({"region": target.region, "category": target.category,
                                   "poster": target.poster, "area_v2": target.area_v2,
                                   "available_total": total, "fetched": fetched,
                                   "raw_ads": fetched,
                                   "image_mismatch": stats["image_mismatch"] - mismatch_before,
                                   "kept": len(rooms) - kept_before})
        # CA-02.2: quận vẫn chạm ngưỡng → chỉ cảnh báo, không chia tiếp.
        if target.area_v2 is not None and total is not None and total >= AREA_SPLIT_THRESHOLD:
            stats["capped_areas"].append({"region": target.region, "category": target.category,
                                          "poster": target.poster, "area_v2": target.area_v2,
                                          "total": total,
                                          "warning": "quận vẫn >= ngưỡng trần phân trang; không chia tiếp"})
        # FC-02.3: tin cá nhân không đủ mốc 1,3× hạn mức thì bù tin môi giới cho phần thiếu × 1,3.
        if target.max_ads is not None and target.poster == "p" and 0 < fetched < target.max_ads:
            top_up = Target(target.region, target.category,
                            math.ceil((target.max_ads - fetched) * FETCH_HEADROOM), "c")
            log(f"  f=p thiếu ({fetched}/{target.max_ads}); bù f=c tới {top_up.max_ads}")
            run_target(top_up)
            return
        # CA-02.2: --all chạm trần phân trang → chia lại từng quận area_v2 đã thấy.
        # Chạy thử (--scale < 1, fraction khác None) chỉ lấy mẫu: KHÔNG chia quận,
        # vẫn ghi nhóm chạm trần kèm ghi chú để manifest nói rõ vì sao chỉ có mẫu.
        if target.max_ads is None and target.area_v2 is None and \
                total is not None and total >= AREA_SPLIT_THRESHOLD:
            trial = target.fraction is not None
            entry = {"region": target.region, "category": target.category,
                     "poster": target.poster, "total": total, "areas": sorted(seen_areas),
                     "split": not trial}
            if trial:
                entry["note"] = "chạy thử --scale < 1: chỉ lấy mẫu, không chia quận"
            stats["capped_groups"].append(entry)
            if trial:
                log(f"  nhóm {target.region}/{target.category}/f={target.poster} chạm trần "
                    f"(total={total}); chạy thử chỉ lấy mẫu, không chia quận")
                return
            log(f"  nhóm {target.region}/{target.category}/f={target.poster} chạm trần "
                f"(total={total}); chia {len(entry['areas'])} quận")
            for code in entry["areas"]:
                run_target(Target(target.region, target.category, None, target.poster, code))

    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20.0) as client:
        for target in targets:
            run_target(target)
    stats["kept"] = len(rooms)
    return rooms, stats


# --- FC-03: ba lớp lọc + chọn tin theo hạn mức cân bằng ------------------------

# Lớp 3 (G2): tin nhiều phòng / giá từ — giá không phải của một phòng cụ thể.
# "giá từ" chỉ tính là chặn giá khi KHÔNG đứng trước "chủ (nhà)" và không phải
# một ngày D/M: "giá từ 1/12 tăng" là mốc ngày, còn "giá từ 3.5tr" là giá vì có
# đơn vị tiền ngay sau số.
MULTI_UNIT = re.compile(
    r"\bchi tu\b"
    r"|\bgia (?:chi )?tu\b(?!\s*(?:(?:cua )?chu\b"
    r"|\d{1,2}[/.\-]\d{1,2}\b(?!\s*(?:k|tr|trieu|nghin|ngan|vnd|dong)\b)))"
    r"|\b(?:con )?nhieu phong\b"
    r"|\b\d+\s*phong trong\b")
MULTI_UNIT_REASON = "multi_unit_or_price_range"
# Khoảng giá "3-5tr", "2tr-3,5tr" (gạch thường hoặc en-dash); ngày "15/10-30/10" không khớp.
PRICE_RANGE = re.compile(r"\b\d+(?:tr|trieu)?\s*[-–]\s*\d+(?:[.,]\d+)?\s*(?:tr|trieu)\b")
# Lớp 2: trùng gần đúng giữa các tài khoản — cùng tọa độ/giá/diện tích/loại và
# tiêu đề bỏ dấu giống nhau ≥ 0,8 (chỉ so trong cùng nhóm tọa độ, không O(n²)).
NEAR_DUPLICATE_RATIO = 0.8
# Thứ tự giữ/chọn (G3): individual trước broker, tin mới hơn trước, ad_id nhỏ trước.
POSTER_RANK = {"individual": 0, "broker": 1}


def multi_unit_reason(text: str) -> str | None:
    haystack = fold(text)
    if MULTI_UNIT.search(haystack) or PRICE_RANGE.search(haystack):
        return MULTI_UNIT_REASON
    return None


def keep_order(room: dict) -> tuple:
    """G3: individual trước broker, rồi tin mới hơn (posted_at), rồi ad_id nhỏ hơn."""
    posted = room.get("posted_at")
    try:
        epoch = -datetime.fromisoformat(str(posted).replace("Z", "+00:00")).timestamp() if posted else 0.0
    except ValueError:
        epoch = 0.0
    ad_id = int(room["id"].removeprefix("chotot-")) if room["id"].startswith("chotot-") else 0
    return (POSTER_RANK.get(room.get("poster_kind"), 2), epoch, ad_id)


def folded_title(room: dict) -> str:
    return " ".join(fold(room["title"]).split())


def filter_rooms(rooms: list[dict]) -> tuple[list[dict], dict]:
    """Lớp 2 (trùng gần đúng giữa các tài khoản) và lớp 3 (nhiều phòng/giá từ).
    Lớp 1 (trùng chính xác) đã chạy trong crawl(). Trả (phòng còn lại, thống kê
    số tin bị loại theo thành phố|poster_kind cho từng lớp)."""
    skipped: dict[str, dict[str, int]] = {"near_duplicate": {}, MULTI_UNIT_REASON: {}}
    kept: list[dict] = []
    # Lớp 3 trước để không tốn công so trùng cho tin sắp bị loại.
    for room in sorted(rooms, key=keep_order):
        reason = multi_unit_reason(f"{room['title']} {room.get('description') or ''}")
        if reason:
            key = f"{room['city']}|{room.get('poster_kind')}"
            skipped[reason][key] = skipped[reason].get(key, 0) + 1
            continue
        kept.append(room)
    # Lớp 2: nhóm theo (tọa độ đã làm tròn, giá, diện tích, loại phòng); tin không
    # có tọa độ thì bỏ qua lớp này. Trong nhóm giữ bản đầu theo G3.
    groups: dict[tuple, list[dict]] = {}
    without_coords: list[dict] = []
    for room in kept:
        if room["latitude"] is None or room["longitude"] is None:
            without_coords.append(room)
            continue
        groups.setdefault((room["latitude"], room["longitude"], room["quote"]["rent_vnd"],
                           room["area_m2"], room["room_type"]), []).append(room)
    survivors: list[dict] = list(without_coords)
    for group in groups.values():
        survivors.extend(group) if len(group) == 1 else survivors.extend(_drop_near_duplicates(group, skipped))
    return survivors, skipped


def _drop_near_duplicates(group: list[dict], skipped: dict) -> list[dict]:
    kept: list[dict] = []
    kept_titles: list[str] = []
    for room in group:  # group đã theo thứ tự G3: bản đầu là bản giữ
        title = folded_title(room)
        if any(difflib.SequenceMatcher(None, title, other).ratio() >= NEAR_DUPLICATE_RATIO
               for other in kept_titles):
            key = f"{room['city']}|{room.get('poster_kind')}"
            skipped["near_duplicate"][key] = skipped["near_duplicate"].get(key, 0) + 1
            continue
        kept.append(room)
        kept_titles.append(title)
    return kept


def category_of(room: dict) -> int:
    # studio tính vào nhóm phòng (cùng chuyên mục 1050).
    return CATEGORY_APARTMENT if room["room_type"] == "apartment" else CATEGORY_ROOM


def select_catalog(rooms: list[dict], per_city: int,
                   balance: bool = True) -> tuple[list[dict], dict]:
    """Chạy lớp 2+3 rồi chọn theo hạn mức cho mỗi (thành phố, loại phòng): sắp
    individual trước broker, mới trước cũ, ad_id; lấy per_city/2 tin đầu. G6: hai
    thành phố phải bằng nhau — tính theo từng loại phòng, bên thiếu hạ cả hai
    xuống. CA-02: per_city <= 0 là không giới hạn — giữ mọi tin qua được lọc,
    không cân bằng G6. Tất định: cùng đầu vào cho cùng kết quả; `pre_balance` là
    số tin qua lọc trước khi cân bằng để crawl_catalog biết combo nào còn thiếu."""
    quota = None if per_city <= 0 else per_city // 2
    filtered, skipped = filter_rooms(rooms)
    pool: dict[tuple[str, int], list[dict]] = {}
    kept_after: dict[str, int] = {}
    for room in filtered:
        combo = (room["city"], category_of(room))
        pool.setdefault(combo, []).append(room)
        key = f"{room['city']}:{category_of(room)}:{room.get('poster_kind')}"
        kept_after[key] = kept_after.get(key, 0) + 1
    for combo in pool:
        pool[combo].sort(key=keep_order)
    stats: dict = {"quota_per_combo": quota, "skipped": skipped, "kept_after": kept_after,
                   "pre_balance": {}, "selected": {}, "poster_split": {}, "areas": {},
                   "final_per_city": None, "over_25pct_removed": []}
    for combo, items in pool.items():
        stats["pre_balance"][f"{combo[0]}:{combo[1]}"] = len(items)

    def take(combo: tuple[str, int], limit: int | None) -> list[dict]:
        if limit is None:
            return list(pool[combo])
        return pool[combo][:max(0, limit)]

    chosen: dict[tuple[str, int], list[dict]] = {combo: take(combo, quota) for combo in pool}
    if balance and quota is not None:
        # G6: từng loại phòng phải bằng nhau giữa hai thành phố.
        for category in (CATEGORY_ROOM, CATEGORY_APARTMENT):
            combos = [(city, category) for city in ("TP.HCM", "Hà Nội") if (city, category) in pool]
            if len(combos) == 2:
                limit = min(quota, *(len(pool[combo]) for combo in combos))
                for combo in combos:
                    chosen[combo] = take(combo, limit)
    order = [(city, category) for city in ("TP.HCM", "Hà Nội")
             for category in (CATEGORY_ROOM, CATEGORY_APARTMENT)]
    selected = [room for combo in order if combo in chosen for room in chosen[combo]]
    by_city_total: dict[str, int] = {}
    for combo, items in chosen.items():
        city = combo[0]
        stats["selected"][f"{city}:{combo[1]}"] = len(items)
        by_city_total[city] = by_city_total.get(city, 0) + len(items)
        for room in items:
            key = f"{city}:{combo[1]}:{room.get('poster_kind')}"
            stats["poster_split"][key] = stats["poster_split"].get(key, 0) + 1
            stats["areas"].setdefault(city, {})
            stats["areas"][city][room["area"]] = stats["areas"][city].get(room["area"], 0) + 1
    if balance:
        stats["final_per_city"] = min(by_city_total.values()) if by_city_total else 0
    # Một nhóm (city, poster) bị lớp 3 loại > 25% → luật có thể đang quá rộng.
    group_after: dict[str, int] = {}
    for key, count in kept_after.items():
        city, _category, poster = key.split(":")
        group = f"{city}|{poster}"
        group_after[group] = group_after.get(group, 0) + count
    for group, after in group_after.items():
        removed = skipped[MULTI_UNIT_REASON].get(group, 0)
        total = after + removed
        if total and removed / total > 0.25:
            stats["over_25pct_removed"].append({"group": group, "removed": removed, "total": total})
    return selected, stats


def crawl_catalog(per_city: int, sleep_s: float, raw_dir: Path, log=print,
                  deadline: float | None = None, max_extra_rounds: int = 2,
                  fetch=None, full: bool = False, scale: float = 1.0) -> tuple[list[dict], dict]:
    """Toàn pipeline FC-02/FC-03: cào (ưu tiên cá nhân, tự bù môi giới trong mỗi
    tổ hợp) → ba lớp lọc → chọn hạn mức → combo còn thiếu thì cào thêm vòng f=c
    cho đúng tổ hợp đó (tối đa `max_extra_rounds`) → chọn lại và áp G6.
    CA-02: `full=True` (--all) cào đủ 8 tổ hợp f=p/f=c không giới hạn; mọi tổ hợp
    đã được cào hết nên không còn vòng bù. Với --all và `scale < 1` mỗi nhóm dừng
    ở ceil(total × scale) để chạy thử. `fetch` thay được trong test."""
    fetch = fetch or crawl
    if full:
        targets = all_targets(scale if scale < 1.0 else None)
    else:
        targets = targets_for(per_city)
    pool, stats = fetch(targets, sleep_s, raw_dir, log, deadline)
    selected, select_stats = select_catalog(pool, per_city)
    quota = None if per_city <= 0 else per_city // 2
    cities = {"TP.HCM": REGION_HCM, "Hà Nội": REGION_HANOI}
    for _ in range(0 if full else max_extra_rounds):
        if quota is None:
            break
        counts = select_stats["pre_balance"]
        shortage = [key for key, count in counts.items() if count < quota]
        if not shortage:
            break
        top_ups = tuple(Target(cities[key.rsplit(":", 1)[0]], int(key.rsplit(":", 1)[1]),
                               math.ceil((quota - counts[key]) * FETCH_HEADROOM), "c")
                        for key in shortage)
        log(f"  Sau lọc còn thiếu {len(shortage)} tổ hợp; cào thêm f=c: " + ", ".join(shortage))
        extra, extra_stats = fetch(top_ups, sleep_s, raw_dir, log, deadline)
        for key in ("pages", "ads_seen"):
            stats[key] += extra_stats[key]
        for reason, count in extra_stats["skipped"].items():
            stats["skipped"][reason] = stats["skipped"].get(reason, 0) + count
        stats["by_target"].extend(extra_stats["by_target"])
        # Mỗi vòng fetch() là một lượt crawl() riêng nên lớp 1 không dùng lại được:
        # chặn bản sao theo room id trước khi gộp, kẻo lớp 2 phải hấp thụ thay.
        pool_ids = {room["id"] for room in pool}
        pool += [room for room in extra if room["id"] not in pool_ids]
        selected, select_stats = select_catalog(pool, per_city)
    stats["selection"] = select_stats
    _merge_selection_into_by_target(stats, select_stats)
    return selected, stats


def _merge_selection_into_by_target(stats: dict, select_stats: dict) -> None:
    """FC-02.5: mỗi (city, type, poster) trong by_target có thêm
    kept_after_filters (số tin qua ba lớp lọc) và selected (số tin được chọn).
    by_target dùng mã bộ lọc "p"/"c", kept_after/poster_split dùng poster_kind."""
    poster_kind_of_code = {"p": "individual", "c": "broker"}
    selected_by: dict[tuple, int] = {}
    for key, count in select_stats.get("poster_split", {}).items():
        city, category, poster = key.split(":")
        selected_by[(city, category, poster)] = count
    kept_after: dict[tuple, int] = {}
    for key, count in select_stats.get("kept_after", {}).items():
        city, category, poster = key.split(":")
        kept_after[(city, category, poster)] = count
    for row in stats.get("by_target", []):
        city = {REGION_HCM: "TP.HCM", REGION_HANOI: "Hà Nội"}.get(row["region"])
        poster = poster_kind_of_code.get(row["poster"], row["poster"])
        row["kept_after_filters"] = kept_after.get((city, str(row["category"]), poster), 0)
        row["selected"] = selected_by.get((city, str(row["category"]), poster), 0)


def _parse_page_name(name: str) -> tuple[int, int, str, int | None, int] | None:
    """Đọc (region, category, poster, area_v2, số trang) từ tên trang raw.
    Dùng để dựng lại đúng thứ tự cào gốc khi rebuild (E-1)."""
    match = re.fullmatch(r"page-(\d+)-(\d+)-([pc])(?:-a(\d+))?-(\d+)\.json", name)
    if match is None:
        return None
    region, category, poster, area, number = match.groups()
    return int(region), int(category), poster, (int(area) if area else None), int(number)


def _page_order(key: tuple[int, int, str, int | None, int]) -> tuple:
    """Thứ tự cào gốc của all_targets(): thành phố HCM → Hà Nội, phòng → căn hộ,
    f=p → f=c; trong mỗi tổ hợp: trang gốc trước, trang quận theo mã tăng dần."""
    region, category, poster, area, number = key
    return (0 if region == REGION_HCM else 1, 0 if category == CATEGORY_ROOM else 1,
            0 if poster == "p" else 1, 0 if area is None else 1 + area, number)


def rebuild_catalog(source_dir: Path, per_city: int, raw_dir: Path, log=print,
                    deadline: float | None = None) -> tuple[list[dict], dict]:
    """E-1: dựng lại catalog từ raw của snapshot cũ, KHÔNG gọi mạng. Đọc trang
    raw theo đúng thứ tự cào gốc, strip + audit lại từng tin rồi chạy đúng
    pipeline: lớp 1 khử trùng (dùng chung _process_ad) → to_room → ba lớp lọc →
    chọn theo hạn mức + G6. Snapshot cũ giữ nguyên; snapshot mới có raw riêng
    (bản strip lại, tường minh cùng audit). account_id đã bị bỏ khỏi raw (G4)
    nên khóa tin đăng lại chỉ còn tiêu đề/giá/diện tích — khác biệt đã biết so
    với lượt cào gốc."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    rooms: list[dict] = []
    seen_ids: set = set()
    seen_keys: set = set()
    stats: dict = {"pages": 0, "ads_seen": 0, "raw_ads": 0, "kept": 0, "skipped": {}, "fees_found": {},
                   "image_mismatch": 0, "area_from_text": 0, "with_videos": 0,
                   "area_from_area_v2": 0, "area_unknown": 0, "videos_dropped_bad_shape": 0,
                   "capped_groups": [], "capped_areas": [], "by_target": [], "rebuild_from": str(source_dir.name)}
    pages = []
    for path in sorted((source_dir / "raw").glob("page-*.json")):
        parsed = _parse_page_name(path.name)
        if parsed is None:
            log(f"  bỏ qua trang lạ {path.name}")
            continue
        pages.append((parsed, path))
    pages.sort(key=lambda item: _page_order(item[0]))
    poster_rank = {"p": "individual", "c": "broker"}
    combo_seen: dict[tuple, dict] = {}
    for (region, category, poster, _area, _number), path in pages:
        if deadline is not None and time.monotonic() > deadline:
            raise CrawlTimeout(f"Quá thời hạn rebuild trang {path.name}")
        ads = json.loads(path.read_text(encoding="utf-8"))
        stripped = [strip_raw(ad) for ad in ads]
        for index, raw_ad in enumerate(stripped):
            problems = audit_raw(raw_ad)
            if problems:
                raise RawAuditError(
                    f"Tin thứ {index} trang {path.name} còn vi phạm riêng tư: " + ", ".join(problems))
        (raw_dir / path.name).write_text(
            json.dumps(stripped, ensure_ascii=False, indent=1), encoding="utf-8")
        stats["pages"] += 1
        stats["ads_seen"] += len(ads)
        stats["raw_ads"] += len(stripped)
        for ad in stripped:
            _process_ad(ad, poster, rooms, seen_ids, seen_keys, stats)
        row = combo_seen.setdefault((region, category, poster),
                                    {"region": region, "category": category, "poster": poster,
                                     "pages": 0, "fetched": 0})
        row["pages"] += 1
        row["fetched"] += len(ads)
        log(f"  rebuild {path.name}: {len(ads)} tin, giữ cộng dồn {len(rooms)}")
    for row in combo_seen.values():
        row["kept_after_filters"] = 0
        row["selected"] = 0
        stats["by_target"].append({**row, "area_v2": None, "available_total": None,
                                   "raw_ads": row["fetched"], "image_mismatch": 0,
                                   "kept": 0})
    pool, stats["kept"] = rooms, len(rooms)
    selected, select_stats = select_catalog(pool, per_city)
    stats["selection"] = select_stats
    _merge_selection_into_by_target(stats, select_stats)
    return selected, stats


def relink_snapshot(source_dir: Path, target_dir: Path, snapshot_id: str) -> dict:
    """Snapshot mới từ snapshot cũ, chỉ đổi `source` của mỗi phòng thành link tin gốc
    (list_id lấy từ raw/ của snapshot cũ). Không cào lại; snapshot cũ giữ nguyên."""
    old_manifest = json.loads((source_dir / "manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((source_dir / "catalog.json").read_text(encoding="utf-8"))
    list_ids: dict[int, int] = {}
    for page in sorted((source_dir / "raw").glob("page-*.json")):
        for ad in json.loads(page.read_text(encoding="utf-8")):
            if isinstance(ad.get("ad_id"), int) and isinstance(ad.get("list_id"), int):
                list_ids[ad["ad_id"]] = ad["list_id"]
    linked = 0
    for room in catalog["rooms"]:
        ad_id = int(room["id"].removeprefix("chotot-"))
        room["source"] = source_of({"ad_id": ad_id, "list_id": list_ids.get(ad_id)})
        linked += room["source"].startswith("https://")
    catalog["snapshot_id"] = snapshot_id
    target_dir.mkdir(parents=True)
    (target_dir / "raw").symlink_to((source_dir / "raw").resolve(), target_is_directory=True)
    catalog_path = target_dir / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    manifest = {**old_manifest, "snapshot_id": snapshot_id, "crawler_version": CRAWLER_VERSION,
                "derived_from": {"snapshot_id": old_manifest["snapshot_id"],
                                 "catalog_sha256": old_manifest["catalog_sha256"],
                                 "change": "source = link tin gốc theo list_id"},
                "catalog_sha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest()}
    (target_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8")
    return {"snapshot": str(target_dir), "rooms": len(catalog["rooms"]), "linked": linked}


def summarize(rooms: list[dict]) -> dict:
    def count(key):
        result: dict[str, int] = {}
        for room in rooms:
            result[str(room[key])] = result.get(str(room[key]), 0) + 1
        return dict(sorted(result.items(), key=lambda item: -item[1]))
    with_full_fees = sum(1 for room in rooms
                         if {"electricity", "water", "internet", "parking", "service"}
                         <= {fee["name"] for fee in room["quote"]["fees"]})
    return {"cities": count("city"), "room_types": count("room_type"), "areas": count("area"),
            "posters": count("poster_kind"),
            "with_coordinates": sum(1 for room in rooms if room["latitude"] is not None),
            "with_deposit": sum(1 for room in rooms if room["quote"]["deposit_vnd"] is not None),
            "with_all_required_fees": with_full_fees}


# --- Đẩy snapshot lên Postgres online -----------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chotot_snapshots (
    snapshot_id text PRIMARY KEY,
    captured_at timestamptz NOT NULL,
    catalog_sha256 text NOT NULL,
    rooms integer NOT NULL,
    manifest jsonb NOT NULL,
    uploaded_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS chotot_listings (
    snapshot_id text NOT NULL REFERENCES chotot_snapshots(snapshot_id) ON DELETE CASCADE,
    room_id text NOT NULL,
    ad_id bigint NOT NULL,
    city text NOT NULL,
    area text NOT NULL,
    room_type text NOT NULL,
    rent_vnd bigint NOT NULL,
    area_m2 real NOT NULL,
    room jsonb NOT NULL,
    raw jsonb,
    PRIMARY KEY (snapshot_id, room_id)
);
CREATE INDEX IF NOT EXISTS chotot_listings_city_area ON chotot_listings(snapshot_id, city, area);
-- CA-03: toàn bộ bản thô của mọi tin trong snapshot (kể cả tin bị lọc loại khỏi
-- catalog); chotot_listings.raw để NULL với snapshot mới để không lưu trùng.
CREATE TABLE IF NOT EXISTS chotot_raw_ads (
    snapshot_id text NOT NULL REFERENCES chotot_snapshots(snapshot_id) ON DELETE CASCADE,
    ad_id bigint NOT NULL,
    list_id bigint,
    raw jsonb NOT NULL,
    PRIMARY KEY (snapshot_id, ad_id)
);
-- Bản văn nguyên gốc: jsonb đổi thứ tự khóa nên không dựng lại đúng byte (và đúng hash) từ cột jsonb.
ALTER TABLE chotot_snapshots ADD COLUMN IF NOT EXISTS catalog_json text;
ALTER TABLE chotot_snapshots ADD COLUMN IF NOT EXISTS manifest_json text;
-- A-5: tin không ghi và không đọc được diện tích thì area_m2 là NULL.
ALTER TABLE chotot_listings ALTER COLUMN area_m2 DROP NOT NULL;
"""


def raw_files_of(snapshot_dir: Path) -> list[Path]:
    return sorted((snapshot_dir / "raw").glob("page-*.json"))


def raw_sha256_of(snapshot_dir: Path) -> str:
    """CA-03: SHA-256 trên nội dung các file raw nối lại theo thứ tự tên."""
    hasher = hashlib.sha256()
    for file in raw_files_of(snapshot_dir):
        hasher.update(file.read_bytes())
    return hasher.hexdigest()


def push_snapshot(snapshot_dir: Path, database_url: str, force: bool = False, log=print,
                  max_raw_mb: float = 300.0) -> dict:
    """Ghi một snapshot đã cào lên Postgres. Snapshot đã có cùng hash thì bỏ qua;
    khác hash thì từ chối (snapshot bất biến) trừ khi --force. CA-03: toàn bộ tin
    trong raw/ được ghi vào `chotot_raw_ads` theo lô; `chotot_listings.raw` để NULL
    với snapshot mới để không lưu trùng. Vượt --max-raw-mb thì dừng trước khi đẩy."""
    import psycopg
    from psycopg.types.json import Jsonb

    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    catalog_path = snapshot_dir / "catalog.json"
    if hashlib.sha256(catalog_path.read_bytes()).hexdigest() != manifest["catalog_sha256"]:
        raise SystemExit("catalog.json không khớp hash trong manifest.json; không đẩy bản đã bị sửa.")
    catalog_text = catalog_path.read_text(encoding="utf-8")
    manifest_text = (snapshot_dir / "manifest.json").read_text(encoding="utf-8")
    rooms = json.loads(catalog_text)["rooms"]
    files = raw_files_of(snapshot_dir)
    raw_bytes = sum(file.stat().st_size for file in files)
    raw_count = 0
    for file in files:
        raw_count += len(json.loads(file.read_text(encoding="utf-8")))
    log(f"Raw dự kiến đẩy: {raw_count} tin, {raw_bytes / (1024 * 1024):.1f} MB trên đĩa "
        f"(trần --max-raw-mb={max_raw_mb:g}).")
    if raw_bytes > max_raw_mb * 1024 * 1024:
        raise SystemExit(f"Raw {raw_bytes / (1024 * 1024):.1f} MB vượt --max-raw-mb={max_raw_mb:g}; "
                         "không đẩy. Chạy lại với trần cao hơn nếu chắc chắn.")
    snapshot_id = manifest["snapshot_id"]
    with psycopg.connect(database_url, connect_timeout=20) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
            log(f"Dung lượng DB đích trước khi đẩy: {cursor.fetchone()[0]}.")
            cursor.execute(SCHEMA_SQL)
            cursor.execute("SELECT catalog_sha256 FROM chotot_snapshots WHERE snapshot_id=%s", (snapshot_id,))
            existing = cursor.fetchone()
            if existing and existing[0] == manifest["catalog_sha256"] and not force:
                cursor.execute(
                    "UPDATE chotot_snapshots SET catalog_json=%s, manifest_json=%s "
                    "WHERE snapshot_id=%s AND catalog_json IS NULL",
                    (catalog_text, manifest_text, snapshot_id))
                log(f"Snapshot {snapshot_id} đã có trên DB với cùng hash; "
                    + ("bổ sung bản văn gốc." if cursor.rowcount else "bỏ qua."))
            else:
                if existing and not force:
                    raise SystemExit(f"Snapshot {snapshot_id} đã có trên DB với hash khác; dùng --force nếu chắc chắn.")
                cursor.execute("DELETE FROM chotot_snapshots WHERE snapshot_id=%s", (snapshot_id,))
                cursor.execute(
                    "INSERT INTO chotot_snapshots(snapshot_id, captured_at, catalog_sha256, rooms, manifest, "
                    "catalog_json, manifest_json) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (snapshot_id, manifest["captured_at"], manifest["catalog_sha256"], len(rooms), Jsonb(manifest),
                     catalog_text, manifest_text))
                cursor.executemany(
                    "INSERT INTO chotot_listings(snapshot_id, room_id, ad_id, city, area, room_type, rent_vnd, "
                    "area_m2, room, raw) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [(snapshot_id, room["id"], int(room["id"].split("-", 1)[1]), room["city"], room["area"],
                      room["room_type"], room["quote"]["rent_vnd"], room["area_m2"], Jsonb(room), None)
                     for room in rooms])
            # CA-03: mọi tin trong raw/ vào chotot_raw_ads theo lô; trùng ad_id
            # (chia quận) giữ bản đầu. Lỗi ad_id không phải số nguyên là dữ liệu hỏng.
            batch: list[tuple] = []
            seen_raw_ids: set[int] = set()

            def flush():
                nonlocal batch
                if batch:
                    cursor.executemany(
                        "INSERT INTO chotot_raw_ads(snapshot_id, ad_id, list_id, raw) "
                        "VALUES (%s, %s, %s, %s) ON CONFLICT (snapshot_id, ad_id) DO NOTHING", batch)
                    batch = []

            for file in files:
                for ad in json.loads(file.read_text(encoding="utf-8")):
                    ad_id = ad.get("ad_id")
                    if not isinstance(ad_id, int):
                        raise SystemExit(f"Raw {file.name} có tin thiếu ad_id; không đẩy bản không hợp lệ.")
                    seen_raw_ids.add(ad_id)
                    batch.append((snapshot_id, ad_id, ad.get("list_id"), Jsonb(ad)))
                    if len(batch) >= 500:
                        flush()
            flush()
            cursor.execute("SELECT count(*) FROM chotot_listings WHERE snapshot_id=%s", (snapshot_id,))
            stored = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM chotot_raw_ads WHERE snapshot_id=%s", (snapshot_id,))
            raw_stored = cursor.fetchone()[0]
    if stored != len(rooms):
        raise SystemExit(f"DB có {stored} phòng, snapshot có {len(rooms)}.")
    if raw_stored != len(seen_raw_ids):
        raise SystemExit(f"DB có {raw_stored} tin raw, snapshot có {len(seen_raw_ids)} ad_id.")
    return {"snapshot_id": snapshot_id, "rooms_on_db": stored, "raw_on_db": raw_stored}


def list_snapshots(database_url: str) -> list[dict]:
    import psycopg

    with psycopg.connect(database_url, connect_timeout=20) as connection:
        rows = connection.execute(
            "SELECT snapshot_id, captured_at, rooms, catalog_sha256, catalog_json IS NOT NULL "
            "FROM chotot_snapshots ORDER BY captured_at").fetchall()
    return [{"snapshot_id": row[0], "captured_at": row[1].isoformat(), "rooms": row[2],
             "catalog_sha256": row[3], "restorable": row[4]} for row in rows]


def pull_snapshot(snapshot_id: str, out_dir: Path, database_url: str, force: bool = False) -> dict:
    """Dựng lại `catalog.json` + `manifest.json` từ DB về máy và kiểm SHA-256 trước khi ghi."""
    import psycopg

    with psycopg.connect(database_url, connect_timeout=20) as connection:
        row = connection.execute(
            "SELECT catalog_sha256, catalog_json, manifest_json FROM chotot_snapshots WHERE snapshot_id=%s",
            (snapshot_id,)).fetchone()
    if row is None:
        raise SystemExit(f"DB không có snapshot {snapshot_id}.")
    expected, catalog_text, manifest_text = row
    if catalog_text is None:
        raise SystemExit(f"Snapshot {snapshot_id} chưa có bản văn gốc trên DB; chạy --push-only từ máy còn bản tạm.")
    if hashlib.sha256(catalog_text.encode("utf-8")).hexdigest() != expected:
        raise SystemExit(f"catalog_json trên DB không khớp hash {expected}; không ghi.")
    snapshot_dir = out_dir / snapshot_id
    catalog_path = snapshot_dir / "catalog.json"
    if catalog_path.exists() and not force:
        if hashlib.sha256(catalog_path.read_bytes()).hexdigest() == expected:
            return {"snapshot": str(snapshot_dir), "status": "already_present"}
        raise SystemExit(f"{catalog_path} đã có và khác bản trên DB; dùng --force để ghi đè.")
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    catalog_path.write_bytes(catalog_text.encode("utf-8"))
    (snapshot_dir / "manifest.json").write_bytes(manifest_text.encode("utf-8"))
    return {"snapshot": str(snapshot_dir), "status": "restored", "catalog_sha256": expected}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot-id", default=f"chotot-{datetime.now(VIETNAM_TZ):%Y-%m-%d}")
    parser.add_argument("--out-dir", type=Path, default=ROOT / ".local" / "chotot")
    parser.add_argument("--per-city", type=int, default=2500,
                        help="Hạn mức tin mỗi thành phố cho catalog; mỗi loại phòng một nửa "
                             "(FC-02). 0 = không giới hạn, giữ mọi tin qua được lọc (CA-02).")
    parser.add_argument("--all", action="store_true",
                        help="Cào hết mọi tổ hợp thành phố × chuyên mục × f=p/f=c, không giới hạn "
                             "số tin; nhóm chạm trần phân trang được chia theo quận (CA-02).")
    parser.add_argument("--max-minutes", type=float, default=None,
                        help="Trần thời gian lượt cào; mặc định 20, với --all là 60. "
                             "Quá giờ thì dừng sạch, không ghi snapshot (C2).")
    parser.add_argument("--sleep", type=float, default=1.5, help="Nghỉ giữa các trang (giây).")
    parser.add_argument("--scale", type=float, default=1.0, help="Nhân số tin mỗi nhóm, ví dụ 0.02 để chạy thử.")
    parser.add_argument("--force", action="store_true", help="Cho phép ghi đè snapshot cùng tên.")
    parser.add_argument("--max-raw-mb", type=float, default=300.0,
                        help="Trần dung lượng raw khi đẩy lên DB; vượt thì dừng, không đẩy dở (CA-03).")
    parser.add_argument("--push-only", action="store_true",
                        help="Không cào; đẩy snapshot đã có trong --out-dir/--snapshot-id lên DB.")
    parser.add_argument("--pull", action="store_true",
                        help="Không cào; tải snapshot --snapshot-id từ DB về --out-dir (kiểm SHA-256).")
    parser.add_argument("--list", action="store_true", help="Liệt kê các snapshot đang có trên DB.")
    parser.add_argument("--rebuild-from", metavar="SNAPSHOT_ID",
                        help="Không cào; dựng lại --snapshot-id từ raw của snapshot cũ "
                             "(đúng pipeline lọc/chọn, không gọi mạng) (E-1).")
    parser.add_argument("--relink-from", metavar="SNAPSHOT_ID",
                        help="Không cào; tạo --snapshot-id từ snapshot cũ, đổi source thành link tin gốc.")
    arguments = parser.parse_args()
    # Chuỗi kết nối chỉ đọc từ biến môi trường để không lộ trong lịch sử lệnh.
    database_url = os.getenv("HOMEMATCH_CRAWL_DATABASE_URL")
    if (arguments.pull or arguments.list) and not database_url:
        parser.error("--pull/--list cần biến môi trường HOMEMATCH_CRAWL_DATABASE_URL.")
    if arguments.list:
        print(json.dumps(list_snapshots(database_url), ensure_ascii=False, indent=2))
        return
    if arguments.pull:
        print(json.dumps(pull_snapshot(arguments.snapshot_id, arguments.out_dir, database_url, arguments.force),
                         ensure_ascii=False))
        return

    snapshot_dir = arguments.out_dir / arguments.snapshot_id
    if arguments.relink_from:
        if snapshot_dir.exists():
            parser.error(f"{snapshot_dir} đã tồn tại; snapshot không ghi đè. Đổi --snapshot-id.")
        print(json.dumps(relink_snapshot(arguments.out_dir / arguments.relink_from, snapshot_dir,
                                         arguments.snapshot_id), ensure_ascii=False))
        return
    if arguments.push_only:
        if not database_url:
            parser.error("--push-only cần biến môi trường HOMEMATCH_CRAWL_DATABASE_URL.")
        print(json.dumps(push_snapshot(snapshot_dir, database_url, arguments.force, max_raw_mb=arguments.max_raw_mb), ensure_ascii=False))
        return
    if snapshot_dir.exists() and not arguments.force:
        parser.error(f"{snapshot_dir} đã tồn tại; snapshot không ghi đè. Đổi --snapshot-id hoặc dùng --force.")
    if arguments.rebuild_from and (arguments.all or arguments.scale != 1.0 or arguments.push_only):
        parser.error("--rebuild-from không dùng cùng --all/--scale/--push-only.")
    quota_city = int(arguments.per_city * arguments.scale)
    # CA-02: 0 là "không giới hạn" nên giữ nguyên; giá trị dương giữ mốc tối thiểu 2.
    per_city = max(2, quota_city) if quota_city > 0 else 0
    max_minutes = arguments.max_minutes if arguments.max_minutes is not None \
        else (60.0 if arguments.all else 20.0)
    deadline = time.monotonic() + max_minutes * 60
    captured_at = datetime.now(VIETNAM_TZ).isoformat(timespec="seconds")
    try:
        if arguments.rebuild_from:
            source_dir = arguments.out_dir / arguments.rebuild_from
            if not (source_dir / "raw").is_dir():
                parser.error(f"{source_dir} không có raw/; không dựng lại được.")
            rooms, stats = rebuild_catalog(source_dir, per_city, snapshot_dir / "raw",
                                           deadline=deadline)
        else:
            rooms, stats = crawl_catalog(per_city, arguments.sleep, snapshot_dir / "raw",
                                         deadline=deadline, full=arguments.all, scale=arguments.scale)
    except CrawlTimeout:
        # C2: quá giờ thì dừng sạch, không ghi snapshot dở dang.
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        raise SystemExit(f"Quá --max-minutes={max_minutes:g}; đã dừng và xóa thư mục tạm, "
                         "không ghi snapshot.") from None
    except RawAuditError as error:
        # CA-01: raw còn khóa cấm/tọa độ chính xác/SĐT → không ghi snapshot.
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        raise SystemExit(f"Vi phạm riêng tư trong raw; đã dừng và xóa thư mục tạm, không ghi snapshot. "
                         f"{error}") from None
    heavy = stats["selection"]["over_25pct_removed"]
    if heavy:
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        raise SystemExit("Lớp lọc 'nhiều phòng/giá từ' loại >25% ở nhóm "
                         + json.dumps(heavy, ensure_ascii=False)
                         + "; luật lọc có thể đang quá rộng, không ghi snapshot.")
    rooms.sort(key=lambda room: room["id"])

    catalog = {
        "notice": ("Tin cho thuê công khai cào từ API Chợ Tốt phục vụ demo KLTN. "
                   "Giá/phí/tiện ích theo nội dung tin, chưa kiểm chứng thực địa. Chủ nhà owner2..d là tài khoản "
                   "demo, không phải người đăng tin. Không phân phối lại."),
        "snapshot_id": arguments.snapshot_id,
        "rooms": rooms,
    }
    catalog_path = snapshot_dir / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    # CA-03: số tin raw và hash raw tính từ file trên đĩa, theo thứ tự tên.
    raw_ads_count = sum(len(json.loads(file.read_text(encoding="utf-8")))
                        for file in raw_files_of(snapshot_dir))
    manifest = {
        "snapshot_id": arguments.snapshot_id,
        "captured_at": captured_at,
        "source": LISTING_URL,
        "crawler": "data/crawl_chotot.py",
        "crawler_version": CRAWLER_VERSION,
        "crawl_mode": "rebuild" if arguments.rebuild_from else ("all" if arguments.all else "quota"),
        **({"derived_from": {"snapshot_id": arguments.rebuild_from,
                             "raw_sha256": raw_sha256_of(arguments.out_dir / arguments.rebuild_from),
                             "change": "dựng lại catalog từ raw, không cào lại"}}
           if arguments.rebuild_from else {}),
        "per_city": per_city,
        "final_per_city": stats["selection"]["final_per_city"],
        "rooms": len(rooms),
        "raw_ads": raw_ads_count,
        "raw_sha256": raw_sha256_of(snapshot_dir),
        "summary": summarize(rooms),
        "stats": stats,
        "catalog_sha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
        "privacy": {"seller_identifiers_dropped": True, "poster_name_kept": True, "images_dropped": False,
                    "image_urls_only": True, "detail_endpoint_used": False,
                    "phone_email_masked_in_raw": True, "coordinates_rounded_decimals": 3},
        "frozen": True,
    }
    (snapshot_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                                encoding="utf-8")
    print(json.dumps({"snapshot": str(snapshot_dir), "rooms": len(rooms),
                      "final_per_city": stats["selection"]["final_per_city"],
                      "summary": {k: v for k, v in manifest["summary"].items() if k != "areas"},
                      "skipped": stats["skipped"], "fees_found": stats["fees_found"],
                      "filters": stats["selection"]["skipped"]}, ensure_ascii=False))
    if database_url:
        print(json.dumps(push_snapshot(snapshot_dir, database_url, arguments.force, max_raw_mb=arguments.max_raw_mb), ensure_ascii=False))
    else:
        print("Chưa có HOMEMATCH_CRAWL_DATABASE_URL: snapshot mới nằm ở máy; chạy lại với --push-only để đẩy lên DB.")


if __name__ == "__main__":
    main()
