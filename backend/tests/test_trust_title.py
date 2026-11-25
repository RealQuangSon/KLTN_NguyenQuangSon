"""Kiểm chứng "tiêu đề nhất quán": đọc giá kiểu Việt trong tiêu đề tin cào.

Lỗi thực tế (kiểm thử e2e 16/11/2026): "1,5tr" làm `int()` ném ValueError
(trang chi tiết 500) và "3.5 TRIỆU" bị đọc thành 5 triệu (cảnh báo sai).
"""
from types import SimpleNamespace

import pytest

from backend.app.trust import _title_consistency, _title_prices_vnd


def _room(title: str, rent_vnd: int | None, area_m2: float | None = None):
    return SimpleNamespace(
        title=title, area_m2=area_m2, quote=SimpleNamespace(rent_vnd=rent_vnd)
    )


@pytest.mark.parametrize(
    "title,expected",
    [
        ("CHÍNH CHỦ CHO THUÊ CĂN HỘ DỊCH VỤ 3.5 TRIỆU QUẬN 7", [3_500_000]),
        ("PHÒNG TRỌ GIÁ TỐT TẠI HÀ ĐÔNG – DỌN VÀO Ở NGAY 1,5tr", [1_500_000]),
        ("chdv 3tr2 full nội thất cao cấp", [3_200_000]),
        ("Phòng trọ gần trung tâm chỉ với 4tr3", [4_300_000]),
        ("Cho thuê 3PN giá rẻ 29triệu Vinhomes", [29_000_000]),
        ("Căn 1PN giá 17 Triệu", [17_000_000]),
        # "5 trung tâm" không phải giá; số nhà/quận không phải giá.
        ("Phòng quận 5 trung tâm, 25m2", []),
        ("Phòng trọ 30m2 giá rẻ", []),
    ],
)
def test_title_prices_read_vietnamese_shorthand(title, expected):
    assert _title_prices_vnd(title) == expected


def test_decimal_price_in_title_matches_rent():
    entry = _title_consistency(
        _room("CHÍNH CHỦ CHO THUÊ CĂN HỘ DỊCH VỤ 3.5 TRIỆU QUẬN 7", 3_500_000)
    )
    assert entry["status"] == "ok"


def test_comma_decimal_price_does_not_crash():
    entry = _title_consistency(_room("Phòng trọ dọn vào ở ngay 1,5tr", 1_500_000))
    assert entry["status"] == "ok"


def test_real_price_mismatch_still_warns():
    entry = _title_consistency(_room("Phòng đẹp 3tr2 full nội thất", 5_000_000))
    assert entry["status"] == "warn"
    assert "Giá trong tiêu đề" in entry["detail"]


def test_area_mismatch_warns_and_no_numbers_is_unknown():
    assert _title_consistency(_room("Studio 40m2", None, 20))["status"] == "warn"
    assert _title_consistency(_room("Phòng trọ sạch đẹp", 2_000_000))["status"] == (
        "unknown"
    )
