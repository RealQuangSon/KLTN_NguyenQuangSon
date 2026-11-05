"""Crawler tin cho thuê từ API công khai của Chợ Tốt → snapshot catalog demo.

Quyết định 30/10/2026: dùng phòng thật làm **catalog demo riêng**, không thay
`data/catalog/rooms.json` (kho giả lập dùng cho eval). Mỗi lần chạy tạo một
snapshot cố định trong `.local/chotot/<snapshot_id>/` (ngoài git, repo công khai):

- `raw/page-*.json`: trang API đã lọc theo allowlist trường, nội dung đã che SĐT/email;
- `catalog.json`: phòng theo schema `Room`, nạp được bằng `HOMEMATCH_CATALOG_PATH`
  hoặc `python -m backend.manage import --catalog`;
- `manifest.json`: ngày cào, nguồn, số lượng, SHA-256 của `catalog.json`.

Từ 2.2, mỗi phòng thêm: nội dung tin đã che (description), ngày đăng, loại người
đăng (broker khi company_ad=True; rỗng thì null), phường cũ/mới, tên đường,
ngày trống, kỳ thanh toán, thời hạn hợp đồng tối thiểu và 10 khóa tiện ích mới.

Từ 2.3 (FC-02/FC-03): cào theo hạn mức `--per-city` (mặc định 2.500 tin mỗi
thành phố, mỗi loại phòng một nửa), ưu tiên tin cá nhân (`f=p`), thiếu thì bù
tin môi giới (`f=c`); `poster_kind` lấy từ bộ lọc nguồn, không đoán từ nội dung.
Sau khi cào chạy ba lớp lọc (trùng chính xác, trùng gần đúng giữa các tài khoản,
tin "nhiều phòng/giá từ") rồi mới chọn theo hạn mức, cân bằng hai thành phố.

Không thu thập tên, ID, avatar người đăng hay ảnh. Phí chỉ lấy khi đọc được con số
hợp lý trong tin; không đọc được thì để null (không bao giờ là 0). `landlord_id`
là tài khoản demo owner-a..d để chạy luồng duyệt, không phải người đăng thật.
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
from decimal import Decimal
from pathlib import Path
from typing import Literal

import httpx

from backend.app.conversations import mask_pii
from backend.app.locations import canonical_area, canonical_city
from backend.app.models import Room

ROOT = Path(__file__).resolve().parents[1]
CRAWLER_VERSION = "2.3"
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
    max_ads: int
    # Bộ lọc nguồn (G1): "p" chỉ tin cá nhân, "c" chỉ tin môi giới/tài khoản chuyên.
    poster: Literal["p", "c"] = "p"


def targets_for(per_city: int) -> tuple[Target, ...]:
    """FC-02: mỗi thành phố `per_city` tin, mỗi loại phòng một nửa; vòng đầu chỉ
    cào tin cá nhân với dự phòng 1,3×. Vòng bù tin môi giới do crawl() tự thêm
    khi cá nhân không đủ, và crawl_catalog() thêm lại sau khi lọc (tối đa 2 vòng)."""
    goal = math.ceil(per_city / 2 * FETCH_HEADROOM)
    return tuple(Target(region, category, goal, "p")
                 for region in (REGION_HCM, REGION_HANOI)
                 for category in (CATEGORY_ROOM, CATEGORY_APARTMENT))

# Chỉ giữ các trường này trong bản thô; mọi thứ về người đăng, ảnh, video bị bỏ.
# 2.2 xác minh thực tế (2026-10-31, ~450 tin mẫu, hai chuyên mục × hai thành phố):
# params chỉ có "Hướng ban công", ad_features/pty_characteristics rỗng 100% —
# không có tiện ích dạng cấu trúc nên KHÔNG đưa ba trường đó vào allowlist.
RAW_ALLOWLIST = (
    "ad_id", "list_id", "list_time", "subject", "body", "price", "size", "deposit",
    "region_name", "area_name", "ward_name", "ward_name_v3", "region_name_v3",
    "company_ad", "street_name", "latitude", "longitude",
    "category", "category_name", "type", "rooms", "toilets", "furnishing_rent",
    "furnishing_sell", "apartment_type", "feature_params", "state", "status",
    "is_price_not_valid",
)

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
        return city, "Không rõ"
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
    # Tài khoản demo để chạy luồng chủ nhà duyệt; không phải người đăng tin thật.
    if city == "Hà Nội":
        return "owner-c" if ad_id % 2 else "owner-d"
    return "owner-a" if ad_id % 2 else "owner-b"


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


def to_room(ad: dict, poster: Literal["p", "c"] | None = None) -> tuple[dict | None, str | None, list[str]]:
    """Trả (room, lý do bỏ, phí đọc được)."""
    ad_id = ad.get("ad_id")
    price, size = ad.get("price"), ad.get("size")
    if not isinstance(ad_id, int):
        return None, "ad_id_missing", []
    if ad.get("is_price_not_valid") or not isinstance(price, (int, float)) or price <= 0:
        return None, "price_missing", []
    if not 500_000 <= price <= 50_000_000:
        return None, "price_out_of_range", []
    if not isinstance(size, (int, float)) or not 5 <= size <= 300:
        return None, "size_missing_or_out_of_range", []
    city, area = city_and_area(ad)
    if city not in ("TP.HCM", "Hà Nội"):
        return None, "city_out_of_scope", []
    subject = str(ad.get("subject") or "")
    # Nội dung tin đã che SĐT/email trước khi dùng cho mọi trích xuất.
    body = mask_pii(unicodedata.normalize("NFC", str(ad.get("body") or "")))
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
        "area_m2": float(size),
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
    }
    return Room.model_validate(room).model_dump(mode="json"), None, fee_names


def strip_raw(ad: dict) -> dict:
    kept = {key: ad[key] for key in RAW_ALLOWLIST if key in ad}
    for key in ("subject", "body", "street_name"):
        if isinstance(kept.get(key), str):
            kept[key] = mask_pii(kept[key])
    return kept


# --- Cào ----------------------------------------------------------------------

class CrawlTimeout(Exception):
    """FC-02/C2: quá --max-minutes; dừng sạch, không ghi snapshot."""


def fetch_page(client: httpx.Client, target: Target, offset: int, limit: int) -> dict:
    params = {"region_v2": target.region, "cg": target.category, "st": "u", "limit": limit,
              "o": offset, "f": target.poster}
    for attempt in range(4):
        response = client.get(LISTING_URL, params=params)
        if response.status_code in (429, 500, 502, 503, 504):
            time.sleep(5 * (attempt + 1))
            continue
        response.raise_for_status()
        return response.json()
    response.raise_for_status()
    return response.json()


def crawl(targets: tuple[Target, ...], sleep_s: float, raw_dir: Path, log=print,
          deadline: float | None = None) -> tuple[list[dict], dict]:
    """Cào từng target theo thứ tự; lớp 1 trùng chính xác (cùng ad_id hoặc cùng
    account_id + tiêu đề + giá + diện tích, account_id chỉ dùng ở đây — G4) giữ
    nguyên như 2.2. Target `f=p` thiếu so với max_ads thì tự cào thêm `f=c` cho
    phần thiếu × 1,3 (FC-02.3). Quá deadline thì raise CrawlTimeout (C2)."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    rooms: list[dict] = []
    seen_ids: set[int] = set()
    seen_keys: set[tuple] = set()
    stats: dict = {"pages": 0, "ads_seen": 0, "kept": 0, "skipped": {}, "fees_found": {}, "by_target": []}

    def skip(reason: str):
        stats["skipped"][reason] = stats["skipped"].get(reason, 0) + 1

    def run_target(target: Target) -> None:
        fetched = 0
        kept_before = len(rooms)
        total = None
        while fetched < target.max_ads:
            if deadline is not None and time.monotonic() > deadline:
                raise CrawlTimeout(f"Quá thời hạn {target.region}/{target.category}/f={target.poster}")
            limit = min(PAGE_SIZE, target.max_ads - fetched)
            payload = fetch_page(client, target, fetched, limit)
            total = payload.get("total", total)
            ads = payload.get("ads") or []
            if not ads:
                break
            page_name = f"page-{target.region}-{target.category}-{target.poster}-{fetched // PAGE_SIZE:03d}.json"
            (raw_dir / page_name).write_text(
                json.dumps([strip_raw(ad) for ad in ads], ensure_ascii=False, indent=1), encoding="utf-8")
            stats["pages"] += 1
            stats["ads_seen"] += len(ads)
            for ad in ads:
                ad_id = ad.get("ad_id")
                # Tin đăng lại: cùng người đăng, cùng tiêu đề, giá, diện tích. account_id chỉ dùng ở đây.
                key = (ad.get("account_id"), fold(str(ad.get("subject") or "")), ad.get("price"), ad.get("size"))
                if ad_id in seen_ids or key in seen_keys:
                    skip("duplicate")
                    continue
                seen_ids.add(ad_id)
                seen_keys.add(key)
                try:
                    room, reason, fee_names = to_room(ad, target.poster)
                except Exception as error:  # noqa: BLE001 - ghi nhận rồi bỏ tin lỗi schema
                    skip(f"schema:{type(error).__name__}")
                    continue
                if room is None:
                    skip(reason or "unknown")
                    continue
                for name in fee_names:
                    stats["fees_found"][name] = stats["fees_found"].get(name, 0) + 1
                rooms.append(room)
            fetched += len(ads)
            log(f"  region={target.region} cg={target.category} f={target.poster}"
                f" fetched={fetched}/{min(target.max_ads, total or 0)} kept_total={len(rooms)}")
            if total is not None and fetched >= total:
                break
            time.sleep(sleep_s)
        stats["by_target"].append({"region": target.region, "category": target.category,
                                   "poster": target.poster, "available_total": total, "fetched": fetched,
                                   "kept": len(rooms) - kept_before})
        # FC-02.3: tin cá nhân không đủ mốc 1,3× hạn mức thì bù tin môi giới cho phần thiếu × 1,3.
        if target.poster == "p" and 0 < fetched < target.max_ads:
            top_up = Target(target.region, target.category,
                            math.ceil((target.max_ads - fetched) * FETCH_HEADROOM), "c")
            log(f"  f=p thiếu ({fetched}/{target.max_ads}); bù f=c tới {top_up.max_ads}")
            run_target(top_up)

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
    xuống. Tất định: cùng đầu vào cho cùng kết quả; `pre_balance` là số tin qua
    lọc trước khi cân bằng để crawl_catalog biết combo nào còn thiếu."""
    quota = per_city // 2
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

    def take(combo: tuple[str, int], limit: int) -> list[dict]:
        return pool[combo][:max(0, limit)]

    chosen: dict[tuple[str, int], list[dict]] = {combo: take(combo, quota) for combo in pool}
    if balance:
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
                  fetch=None) -> tuple[list[dict], dict]:
    """Toàn pipeline FC-02/FC-03: cào (ưu tiên cá nhân, tự bù môi giới trong mỗi
    tổ hợp) → ba lớp lọc → chọn hạn mức → combo còn thiếu thì cào thêm vòng f=c
    cho đúng tổ hợp đó (tối đa `max_extra_rounds`) → chọn lại và áp G6.
    `fetch` thay được trong test (mặc định là crawl)."""
    fetch = fetch or crawl
    pool, stats = fetch(targets_for(per_city), sleep_s, raw_dir, log, deadline)
    selected, select_stats = select_catalog(pool, per_city)
    quota = per_city // 2
    cities = {"TP.HCM": REGION_HCM, "Hà Nội": REGION_HANOI}
    for _ in range(max_extra_rounds):
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
-- Bản văn nguyên gốc: jsonb đổi thứ tự khóa nên không dựng lại đúng byte (và đúng hash) từ cột jsonb.
ALTER TABLE chotot_snapshots ADD COLUMN IF NOT EXISTS catalog_json text;
ALTER TABLE chotot_snapshots ADD COLUMN IF NOT EXISTS manifest_json text;
"""


def push_snapshot(snapshot_dir: Path, database_url: str, force: bool = False, log=print) -> dict:
    """Ghi một snapshot đã cào lên Postgres. Snapshot đã có cùng hash thì bỏ qua;
    khác hash thì từ chối (snapshot bất biến) trừ khi --force."""
    import psycopg
    from psycopg.types.json import Jsonb

    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    catalog_path = snapshot_dir / "catalog.json"
    if hashlib.sha256(catalog_path.read_bytes()).hexdigest() != manifest["catalog_sha256"]:
        raise SystemExit("catalog.json không khớp hash trong manifest.json; không đẩy bản đã bị sửa.")
    catalog_text = catalog_path.read_text(encoding="utf-8")
    manifest_text = (snapshot_dir / "manifest.json").read_text(encoding="utf-8")
    rooms = json.loads(catalog_text)["rooms"]
    raw_by_ad: dict[int, dict] = {}
    for page in sorted((snapshot_dir / "raw").glob("page-*.json")):
        for ad in json.loads(page.read_text(encoding="utf-8")):
            raw_by_ad.setdefault(ad.get("ad_id"), ad)
    snapshot_id = manifest["snapshot_id"]
    with psycopg.connect(database_url, connect_timeout=20) as connection:
        with connection.cursor() as cursor:
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
                      room["room_type"], room["quote"]["rent_vnd"], room["area_m2"], Jsonb(room),
                      Jsonb(raw_by_ad.get(int(room["id"].split("-", 1)[1])))) for room in rooms])
            cursor.execute("SELECT count(*) FROM chotot_listings WHERE snapshot_id=%s", (snapshot_id,))
            stored = cursor.fetchone()[0]
    if stored != len(rooms):
        raise SystemExit(f"DB có {stored} phòng, snapshot có {len(rooms)}.")
    return {"snapshot_id": snapshot_id, "rooms_on_db": stored}


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
                        help="Hạn mức tin mỗi thành phố; mỗi loại phòng một nửa (FC-02).")
    parser.add_argument("--max-minutes", type=float, default=20.0,
                        help="Trần thời gian lượt cào; quá giờ thì dừng sạch, không ghi snapshot (C2).")
    parser.add_argument("--sleep", type=float, default=1.5, help="Nghỉ giữa các trang (giây).")
    parser.add_argument("--scale", type=float, default=1.0, help="Nhân số tin mỗi nhóm, ví dụ 0.02 để chạy thử.")
    parser.add_argument("--force", action="store_true", help="Cho phép ghi đè snapshot cùng tên.")
    parser.add_argument("--push-only", action="store_true",
                        help="Không cào; đẩy snapshot đã có trong --out-dir/--snapshot-id lên DB.")
    parser.add_argument("--pull", action="store_true",
                        help="Không cào; tải snapshot --snapshot-id từ DB về --out-dir (kiểm SHA-256).")
    parser.add_argument("--list", action="store_true", help="Liệt kê các snapshot đang có trên DB.")
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
        print(json.dumps(push_snapshot(snapshot_dir, database_url, arguments.force), ensure_ascii=False))
        return
    if snapshot_dir.exists() and not arguments.force:
        parser.error(f"{snapshot_dir} đã tồn tại; snapshot không ghi đè. Đổi --snapshot-id hoặc dùng --force.")
    per_city = max(2, int(arguments.per_city * arguments.scale))
    deadline = time.monotonic() + arguments.max_minutes * 60
    captured_at = datetime.now(VIETNAM_TZ).isoformat(timespec="seconds")
    try:
        rooms, stats = crawl_catalog(per_city, arguments.sleep, snapshot_dir / "raw", deadline=deadline)
    except CrawlTimeout:
        # C2: quá giờ thì dừng sạch, không ghi snapshot dở dang.
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        raise SystemExit(f"Quá --max-minutes={arguments.max_minutes:g}; đã dừng và xóa thư mục tạm, "
                         "không ghi snapshot.") from None
    heavy = stats["selection"]["over_25pct_removed"]
    if heavy:
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        raise SystemExit("Lớp lọc 'nhiều phòng/giá từ' loại >25% ở nhóm "
                         + json.dumps(heavy, ensure_ascii=False)
                         + "; luật lọc có thể đang quá rộng, không ghi snapshot.")
    rooms.sort(key=lambda room: room["id"])

    catalog = {
        "notice": ("Tin cho thuê công khai cào từ API Chợ Tốt phục vụ demo KLTN; không phải dữ liệu HubHome. "
                   "Giá/phí/tiện ích theo nội dung tin, chưa kiểm chứng thực địa. Chủ nhà owner-a..d là tài khoản "
                   "demo, không phải người đăng tin. Không phân phối lại."),
        "snapshot_id": arguments.snapshot_id,
        "rooms": rooms,
    }
    catalog_path = snapshot_dir / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    manifest = {
        "snapshot_id": arguments.snapshot_id,
        "captured_at": captured_at,
        "source": LISTING_URL,
        "crawler": "data/crawl_chotot.py",
        "crawler_version": CRAWLER_VERSION,
        "per_city": per_city,
        "final_per_city": stats["selection"]["final_per_city"],
        "rooms": len(rooms),
        "summary": summarize(rooms),
        "stats": stats,
        "catalog_sha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
        "privacy": {"seller_fields_dropped": True, "images_dropped": True,
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
        print(json.dumps(push_snapshot(snapshot_dir, database_url, arguments.force), ensure_ascii=False))
    else:
        print("Chưa có HOMEMATCH_CRAWL_DATABASE_URL: snapshot mới nằm ở máy; chạy lại với --push-only để đẩy lên DB.")


if __name__ == "__main__":
    main()
