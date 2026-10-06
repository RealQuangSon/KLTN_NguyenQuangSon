"""Deterministic multi-criteria comparison advice (tenant portal).

Pros/cons and the suggested pick are computed from the cost engine output and
listing evidence only; the advisor never invents a number. Unknown totals never
win a "cheapest" comparison, and a room over the confirmed budget is never the
suggested pick.
"""
from __future__ import annotations

BAND_RANK = {"phu_hop": 0, "chua_ro": 1, "can_nhac": 2, "vuot": 3}


def _money(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " ₫"


def advise(items: list[dict], *, budget: int | None = None, preferences: list[str] | None = None) -> dict:
    preferences = preferences or []
    rows = []
    for item in items:
        cost = item["cost"]
        affordability = cost.get("affordability") or {}
        rows.append({
            "room_id": item.get("room_id") or item.get("id"), "title": item["title"].split(". ")[0],
            "monthly": cost["monthly_total_vnd"], "initial": cost["initial_total_vnd"],
            "area": item.get("area_m2"),
            "band": affordability.get("band"),
            "burden": affordability.get("renter_burden_vnd") or cost["monthly_total_vnd"],
            "matched": [name for name in preferences if (item.get("amenities") or {}).get(name) is True]
                       if item.get("amenities") is not None else None,
            "missing": cost["missing_monthly"] + cost["missing_initial"],
            "verification": item.get("verification") or [],
        })

    def extreme(key, lowest=True):
        known = [row for row in rows if row[key] is not None]
        if len(known) < 2:
            return set(), set()
        values = [row[key] for row in known]
        best, worst = (min(values), max(values)) if lowest else (max(values), min(values))
        if best == worst:
            return set(), set()
        return ({row["room_id"] for row in known if row[key] == best},
                {row["room_id"] for row in known if row[key] == worst})

    cheapest, priciest = extreme("monthly")
    lowest_initial, highest_initial = extreme("initial")
    largest, smallest = extreme("area", lowest=False)
    for row in rows:
        pros, cons = [], []
        if row["room_id"] in cheapest:
            pros.append(f"Tổng tháng thấp nhất ({_money(row['monthly'])})")
        if row["room_id"] in priciest:
            cons.append(f"Tổng tháng cao nhất ({_money(row['monthly'])})")
        if row["room_id"] in lowest_initial:
            pros.append(f"Tiền vào ở thấp nhất ({_money(row['initial'])})")
        if row["room_id"] in highest_initial:
            cons.append(f"Tiền vào ở cao nhất ({_money(row['initial'])})")
        if row["room_id"] in largest:
            pros.append(f"Rộng nhất ({row['area']:g} m²)")
        if row["room_id"] in smallest:
            cons.append(f"Nhỏ nhất ({row['area']:g} m²)")
        if preferences and row["matched"] is not None:
            (pros if len(row["matched"]) == len(preferences) else cons).append(
                f"Đáp ứng {len(row['matched'])}/{len(preferences)} ưu tiên")
        if row["band"] == "phu_hop":
            pros.append("Trong mức khuyến nghị so với thu nhập")
        elif row["band"] == "vuot":
            cons.append("Vượt mức khuyến nghị so với thu nhập")
        if budget is not None and row["monthly"] is not None and row["monthly"] > budget:
            cons.append(f"Vượt ngân sách tháng {_money(row['monthly'] - budget)}")
        if row["missing"]:
            cons.append("Còn khoản chưa rõ: " + ", ".join(row["missing"]))
        row["pros"], row["cons"] = pros, cons

    eligible = [row for row in rows if row["monthly"] is not None and (budget is None or row["monthly"] <= budget)]
    if not eligible:
        return {"recommended_room_id": None, "rooms": rows,
                "summary": "Chưa có phòng nào vừa đủ dữ liệu chi phí vừa nằm trong ngân sách để đề xuất."}
    eligible.sort(key=lambda row: (BAND_RANK.get(row["band"], 1), -(len(row["matched"] or [])),
                                   row["burden"], -(row["area"] or 0), row["room_id"]))
    pick = eligible[0]
    reasons = [text for text in pick["pros"]][:3] or ["chi phí trong ngân sách và đủ dữ liệu"]
    return {"recommended_room_id": pick["room_id"], "rooms": rows,
            "summary": f"Đề xuất {pick['title']}: " + "; ".join(reasons).lower()
                       + ". Đây là gợi ý theo dữ liệu đã có, bạn vẫn nên xem phòng trước khi quyết định."}
