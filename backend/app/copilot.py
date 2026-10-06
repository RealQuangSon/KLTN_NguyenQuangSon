"""Landlord AI co-pilot: marketing copy, multi-channel sharing and an advisory assistant.

Everything is grounded in the landlord's own data and the shared catalog:
posts only state facts from the listing (unknown fees/amenities are omitted,
never invented); price advice comes from comparable published rooms, with the
sample size shown; the assistant routes questions by keywords and answers from
deterministic computations. Nothing is posted to social networks automatically.
"""
from __future__ import annotations

import re
from statistics import median
from urllib.parse import quote

from .costs import calculate_cost
from .locations import fold
from .models import Scenario

AMENITY_TEXT = {
    "window": "cửa sổ thoáng", "quiet": "yên tĩnh", "parking": "chỗ để xe", "private_bathroom": "WC riêng",
    "air_conditioning": "máy lạnh", "washing_machine": "máy giặt", "balcony": "ban công",
    "furniture": "nội thất", "pets_allowed": "cho nuôi thú cưng",
}
TYPE_TEXT = {"room": "Phòng trọ", "studio": "Studio", "apartment": "Căn hộ"}
CHANNELS = ("facebook", "zalo", "forum")


def _money(value: int | None) -> str:
    if value is None:
        return "liên hệ"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " triệu"
    return f"{value:,}".replace(",", ".") + " đ"


def comparables(rooms, room, area_band: float = 0.35) -> list:
    return [other for other in rooms if other.id != room.id and other.published and other.city == room.city
            and other.area == room.area and other.room_type == room.room_type
            and abs(other.area_m2 - room.area_m2) <= room.area_m2 * area_band]


def price_advice(rooms, room) -> dict:
    peers = comparables(rooms, room)
    if len(peers) < 3:
        # Widen to the same city and type when the district has too few peers.
        peers = [other for other in rooms if other.id != room.id and other.published and other.city == room.city
                 and other.room_type == room.room_type and abs(other.area_m2 - room.area_m2) <= room.area_m2 * 0.35]
        scope = f"cùng loại tại {room.city}"
    else:
        scope = f"cùng loại tại {room.area}"
    if len(peers) < 3:
        return {"room_id": room.id, "sample": len(peers), "scope": scope, "suggested_min": None,
                "suggested_max": None, "median": None, "position": None,
                "message": "Chưa đủ phòng tương đương (cần ít nhất 3) để đề xuất giá."}
    middle = int(median(other.quote.rent_vnd for other in peers))
    low, high = int(middle * 0.95 / 50_000) * 50_000, int(middle * 1.05 / 50_000 + 0.999) * 50_000
    rent = room.quote.rent_vnd
    gap = (rent - middle) / middle
    position = "cao hơn" if gap > 0.05 else "thấp hơn" if gap < -0.05 else "ngang"
    return {"room_id": room.id, "sample": len(peers), "scope": scope, "median": middle, "suggested_min": low,
            "suggested_max": high, "position": position, "gap_ratio": round(gap, 3),
            "message": f"Giá thuê hiện tại {_money(rent)} {position} mặt bằng {len(peers)} phòng {scope} "
                       f"(trung vị {_money(middle)}). Khoảng đề xuất: {_money(low)} – {_money(high)}."}


def strengths(rooms, room) -> list[str]:
    points = []
    advice = price_advice(rooms, room)
    if advice["position"] == "thấp hơn":
        points.append("giá tốt hơn mặt bằng khu vực")
    if room.room_type == "apartment" and room.bedrooms:
        points.append(f"{room.bedrooms} phòng ngủ")
    points.append(f"{room.area_m2:g} m²")
    points += [AMENITY_TEXT[name] for name, value in room.amenities.items() if value is True and name in AMENITY_TEXT]
    return points


def marketing_post(rooms, room, channel: str, listing_url: str) -> dict:
    if channel not in CHANNELS:
        raise ValueError(channel)
    cost = calculate_cost(room.quote, Scenario())
    kind = TYPE_TEXT[room.room_type] + (f" {room.bedrooms}PN" if room.bedrooms else "")
    title = room.title.split(". ")[0]
    points = strengths(rooms, room)
    features = room.features_text or ""
    rent, monthly = _money(room.quote.rent_vnd), _money(cost.monthly_total_vnd)
    deposit = _money(room.quote.deposit_vnd) if room.quote.deposit_vnd is not None else "thỏa thuận"
    fees_note = ("Tổng chi phí tham khảo khoảng " + monthly + "/tháng (1 người, 1 xe)."
                 if cost.monthly_total_vnd is not None else "Một số phí cần hỏi thêm chủ nhà.")
    if channel == "facebook":
        tags = " ".join("#" + re.sub(r"\W", "", fold(word).title()) for word in
                        (room.area, room.city, kind.split()[0], "ChoThue", "HomeMatch"))
        text = (f"🏠 {kind.upper()} CHO THUÊ – {room.area.upper()}, {room.city.upper()}\n\n"
                f"✨ {title}\n💰 Giá thuê: {rent}/tháng · Cọc: {deposit}\n📐 Diện tích: {room.area_m2:g} m²\n"
                + "".join(f"✅ {point.capitalize()}\n" for point in points[:6])
                + (f"🌿 {features}\n" if features else "")
                + f"ℹ️ {fees_note}\n\n👉 Xem chi tiết & đặt lịch xem: {listing_url}\n\n{tags}")
    elif channel == "zalo":
        text = (f"{kind} {room.area}, {room.city} – {rent}/tháng.\n"
                f"{', '.join(points[:4]).capitalize()}.\n{fees_note}\nXem & hẹn lịch: {listing_url}")
    else:
        text = (f"[Cho thuê] {kind} {room.area}, {room.city} – {rent}/tháng\n\n"
                f"- Diện tích: {room.area_m2:g} m²\n- Giá thuê: {rent}/tháng; cọc {deposit}\n"
                f"- Tiện ích: {', '.join(points) or 'liên hệ'}\n"
                + (f"- Mô tả: {features}\n" if features else "")
                + (f"- Nội quy: {room.house_rules}\n" if room.house_rules else "")
                + f"- Chi phí: {fees_note}\n\nChi tiết, bản đồ, đặt lịch xem: {listing_url}")
    share = {"facebook": f"https://www.facebook.com/sharer/sharer.php?u={quote(listing_url, safe='')}",
             "zalo": None, "forum": None}[channel]
    return {"channel": channel, "text": text, "listing_url": listing_url, "share_url": share,
            "highlights": points[:6],
            "notice": "Nội dung chỉ dùng dữ liệu của tin; HomeMatch không tự đăng lên mạng xã hội. "
                      "Bấm chia sẻ hoặc sao chép để đăng."}


ROOM_ID = re.compile(r"(room-[0-9a-f]{10}|synthetic-room-\d{3}|demo-\d{2})")


def _mentioned_room(question: str, own: list):
    match = ROOM_ID.search(question.lower())
    if match:
        return next((room for room in own if room.id == match.group(1)), None)
    number = re.search(r"phong\s*(\d{1,3})\b", fold(question))
    if number:
        suffix = f"-{int(number.group(1)):03d}"
        return next((room for room in own if room.id.endswith(suffix) or room.id.endswith(f"-{int(number.group(1)):02d}")),
                    None)
    return None


def vacancy_report(repo, rooms, own) -> list[dict]:
    result = []
    for room in own:
        if room.occupancy in ("rented", "deposited") or room.available is False:
            continue
        views = repo.db.execute("SELECT COUNT(*) AS n FROM hm_room_views WHERE room_id=?", (room.id,)).fetchone()["n"]
        viewings = repo.db.execute("SELECT COUNT(*) AS n FROM hm_viewings WHERE room_id=?", (room.id,)).fetchone()["n"]
        reasons = []
        advice = price_advice(rooms, room)
        if advice["position"] == "cao hơn":
            reasons.append(f"giá cao hơn mặt bằng {round(advice['gap_ratio'] * 100)}% (trung vị {_money(advice['median'])})")
        unknown_fees = [fee.name for fee in room.quote.fees if fee.amount_vnd is None and not fee.included_in_rent]
        if unknown_fees:
            reasons.append("thiếu đơn giá: " + ", ".join(unknown_fees) + " (khách không thấy tổng chi phí)")
        unknown = [AMENITY_TEXT.get(name, name) for name, value in room.amenities.items() if value is None]
        if unknown:
            reasons.append("tiện ích chưa rõ: " + ", ".join(unknown))
        if not room.published:
            reasons.append("tin đang ẩn")
        if room.location_accuracy == "area_only":
            reasons.append("chưa có vị trí trên bản đồ")
        if views == 0:
            reasons.append("chưa có lượt xem tin")
        elif viewings == 0:
            reasons.append(f"{views} lượt xem nhưng chưa có ai đặt lịch")
        if not room.features_text:
            reasons.append("chưa có mô tả điểm nổi bật")
        result.append({"room_id": room.id, "title": room.title.split(". ")[0], "views": views, "viewings": viewings,
                       "reasons": reasons or ["không thấy vấn đề rõ ràng trong dữ liệu; thử đăng lại tin đa kênh"]})
    return result


def assistant(repo, rooms, landlord_id: str, question: str, dashboard: dict) -> dict:
    text = fold(question)
    own = [room for room in rooms if room.landlord == landlord_id]
    room = _mentioned_room(question, own)
    if any(word in text for word in ("gia", "bao nhieu", "dinh gia", "tang gia", "giam gia")) and \
            not any(word in text for word in ("doanh thu", "cong no")):
        targets = [room] if room else [r for r in own if r.occupancy not in ("rented",)][:5]
        advice = [price_advice(rooms, target) | {"title": target.title.split(". ")[0]} for target in targets]
        return {"intent": "price_advice", "answer": "\n".join(f"{item['title']}: {item['message']}" for item in advice),
                "data": advice}
    if any(word in text for word in ("trong lau", "phong trong", "chua thue", "it khach", "vi sao", "tai sao")):
        report = vacancy_report(repo, rooms, [room] if room else own)
        if not report:
            return {"intent": "vacancy", "answer": "Hiện không có phòng trống.", "data": []}
        lines = [f"{item['title']}: " + "; ".join(item["reasons"]) + "." for item in report]
        return {"intent": "vacancy", "answer": "Phân tích phòng còn trống:\n" + "\n".join(lines), "data": report}
    if any(word in text for word in ("doanh thu", "cong no", "no dong", "thu tien", "qua han")):
        return {"intent": "finance",
                "answer": (f"Tháng {dashboard['month']}: thực thu {_money(dashboard['revenue_month_vnd'])}; công nợ tồn "
                           f"{_money(dashboard['outstanding_vnd'])}; {dashboard['overdue_invoices']} hóa đơn quá hạn."),
                "data": {key: dashboard[key] for key in ("revenue_month_vnd", "outstanding_vnd", "overdue_invoices")}}
    if any(word in text for word in ("lap day", "ty le", "bao nhieu phong", "tinh trang")):
        rate = dashboard["occupancy_rate"]
        return {"intent": "occupancy",
                "answer": (f"{dashboard['rooms']} phòng: {dashboard['rented']} đã thuê, {dashboard['deposited']} đã cọc, "
                           f"{dashboard['vacant']} trống" + (f"; lấp đầy {round(rate * 100)}%." if rate is not None else ".")),
                "data": {key: dashboard[key] for key in ("rooms", "rented", "deposited", "vacant", "occupancy_rate")}}
    return {"intent": "help",
            "answer": ("Tôi có thể: phân tích vì sao phòng trống lâu, đề xuất giá thuê theo phòng tương đương, "
                       "báo doanh thu/công nợ, tỷ lệ lấp đầy. Ví dụ: “Vì sao phòng trống lâu?”, "
                       "“Phòng 012 nên cho thuê giá bao nhiêu?”"), "data": None}
