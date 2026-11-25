"""LF-02: crawler 2.2 maps the new listing fields from Chợ Tốt ads.

All mapping runs on synthetic ad dicts (to_room is pure) plus one crawl pass
over httpx.MockTransport — no network. Unknown values stay null; the raw
snapshot keeps every field the API returns except DROPPED_KEYS (C1/CA-01).
"""
import json

import httpx
import pytest

from data.crawl_chotot import (AREA_V2_NAMES, BALCONY_DIRECTION_NAMES, CRAWLER_VERSION, DROPPED_KEYS,
                               KEYWORD_AMENITIES, RawAuditError, Target, REGION_HCM, CATEGORY_ROOM,
                               audit_raw, crawl, detect_amenities, extract_terms, source_videos_of,
                               strip_raw, to_room, videos_dropped_bad_shape)

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
        # B-1: catalog chỉ nhận tin có ảnh — helper mặc định 1 ảnh CDN.
        "images": ["https://cdn.chotot.com/q7/123.jpg"],
    }
    ad.update(overrides)
    return ad


def test_crawler_version_bumped_and_dropped_keys_cover_identifiers():
    assert CRAWLER_VERSION == "2.4"  # CA-03: full raw snapshot + chotot_raw_ads table
    # CA-01: mọi định danh người đăng và trường vị trí chính xác đều trong danh sách cấm.
    for key in ("account_id", "account_oid", "account_name", "avatar", "phone", "shop", "shop_alias",
                "facebook_id", "cta_buttons", "street_number", "streetnumber_display", "unitnumber",
                "unitnumber_display", "detail_address", "block", "location", "pty_map",
                "pty_map_modifier", "pty_map_v2"):
        assert key in DROPPED_KEYS


def test_raw_keeps_everything_except_dropped_keys_at_any_depth():
    ad = base_ad(
        # Mọi khóa cấm, cả ở cấp trên cùng...
        account_oid="oid-x", avatar="https://cdn.chotot.com/avatar.jpg", phone="0901234567",
        shop={"id": 1}, shop_alias="shop-x", facebook_id="fb-x", cta_buttons=[{"label": "call"}],
        street_number="12/3", streetnumber_display="12/3", unitnumber="P01", unitnumber_display="P01",
        detail_address="Nhà số 12", block="A1", location={"latitude": 10.123456},
        pty_map="map", pty_map_modifier="mod", pty_map_v2="map2",
        # ...lẫn lồng trong khóa lạ mà API có thể trả thêm.
        new_field={"deep": {"deeper": [{"account_id": 9, "phone": "0908765432"}]}},
        nested_list=[{"account_name": "x", "keep": "ok"}],
        seller_info={"rating": 5, "live_ads": 2, "sold_ads": 1, "full_name": "Nguyễn Văn A"},
        full_name="Nguyễn Văn A 0901234567",
        images=["https://cdn.chotot.com/1.jpg"], videos=["https://cdn.chotot.com/v.mp4"],
        image={"url": "https://cdn.chotot.com/1.jpg"}, floornumber=3,
        latitude=10.123456, longitude=106.654321,
    )
    raw = strip_raw(ad)
    for key in DROPPED_KEYS:
        assert key not in raw
    # Khóa lạ và trường media được giữ mặc định.
    for key in ("images", "videos", "image", "floornumber", "new_field", "nested_list"):
        assert key in raw
    # Khóa cấm mất cả khi lồng sâu trong dict/list của khóa lạ.
    assert raw["new_field"] == {"deep": {"deeper": [{}]}}
    assert raw["nested_list"] == [{"keep": "ok"}]
    # seller_info chỉ còn hai khóa đếm tin; full_name lồng nhau bị bỏ.
    assert raw["seller_info"] == {"live_ads": 2, "sold_ads": 1}
    # Tọa độ làm tròn 3 chữ số thập phân (C2) cả trong raw.
    assert raw["latitude"] == 10.123 and raw["longitude"] == 106.654
    # full_name cấp trên cùng được giữ (C1) nhưng SĐT trong tên bị che;
    # chuỗi URL ảnh đi qua nguyên vẹn, không bị mask_pii đổi.
    assert "[SĐT đã che]" in raw["full_name"] and "0901234567" not in raw["full_name"]
    assert raw["images"] == ["https://cdn.chotot.com/1.jpg"]
    assert raw["image"] == {"url": "https://cdn.chotot.com/1.jpg"}
    assert raw["videos"] == ["https://cdn.chotot.com/v.mp4"]
    assert raw["ward_name_v3"] == "Phường Tân Hưng" and raw["company_ad"] is True


def test_audit_raw_catches_each_violation_kind():
    clean = strip_raw(base_ad())
    assert audit_raw(clean) == []
    with_dropped = {**clean, "account_id": 1}
    assert any(v.startswith("dropped_key:account_id") for v in audit_raw(with_dropped))
    too_precise = {**clean, "latitude": 10.123456}
    assert any(v.startswith("coordinates:latitude") for v in audit_raw(too_precise))
    map_url = {**clean, "image": "https://cdn.chotot.com/240x240_480x480.jpg"}
    assert any(v.startswith("coordinate_url:image") for v in audit_raw(map_url))
    phone_left = {**clean, "body": "Gọi số 0901234567 ngay"}
    assert any(v.startswith("phone_in_text:body") for v in audit_raw(phone_left))
    extra_seller = {**clean, "seller_info": {"live_ads": 1, "sold_ads": 0, "rating": 5}}
    assert any(v.startswith("seller_info_key:seller_info.rating") for v in audit_raw(extra_seller))


def test_crawl_stops_without_snapshot_when_raw_audit_fails(tmp_path, monkeypatch):
    ads = [base_ad(), base_ad(ad_id=456, list_id=87761700, subject="Phòng có ảnh bản đồ",
                              body="Xem bản đồ vị trí.", image="https://cdn.chotot.com/240x240_480x480.jpg")]

    def handler(request):
        return httpx.Response(200, json={"total": 2, "ads": [strip_raw(ad) for ad in ads]})

    real_client = httpx.Client

    def fake_client(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("data.crawl_chotot.httpx.Client", staticmethod(fake_client))
    raw_dir = tmp_path / "raw"
    with pytest.raises(RawAuditError) as raised:
        crawl((Target(REGION_HCM, CATEGORY_ROOM, 2),), 0.0, raw_dir, log=lambda *_: None)
    # Thông báo lỗi chỉ nêu tên khóa, không nêu giá trị vi phạm.
    assert "coordinate_url" in str(raised.value) and "cdn.chotot.com" not in str(raised.value)
    assert not list(raw_dir.glob("page-*.json"))


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


def test_to_room_maps_crawl_display_fields_and_filters_image_urls():
    cdn = "https://cdn.chotot.com/abc/1.jpg"
    images = [cdn, "https://other-cdn.example/x.jpg", "not-a-url", cdn + "?v=2"]
    ad = base_ad(images=images + [f"https://cdn.chotot.com/{index}.jpg" for index in range(30)],
                 toilets=2, pty_project_name="  Chung cư  New  City ", full_name="Nguyễn Văn A 0901234567")
    room, reason, _ = to_room(ad)
    assert reason is None
    # Chỉ URL CDN Chợ Tốt được giữ, tối đa 30, theo thứ tự của tin (C5/CA-04).
    assert room["source_images"][0] == cdn
    assert all(url.startswith("https://cdn.chotot.com/") for url in room["source_images"])
    assert len(room["source_images"]) == 30
    assert room["toilets"] == 2
    assert room["project_name"] == "Chung cư New City"
    # C1b: tên người đăng giữ trong Room nhưng SĐT trong tên bị che.
    assert "[SĐT đã che]" in room["poster_name"] and "0901234567" not in room["poster_name"]


def test_to_room_missing_display_fields_stay_empty_or_null():
    # B-1: tin không có ảnh bị loại nên helper dùng ảnh mặc định; kiểm tra
    # "không có" bằng cách bỏ ảnh khỏi tin... không được: to_room từ chối.
    no_image, reason, _ = to_room(base_ad(images=[]))
    assert no_image is None and reason == "no_image"
    room, _, _ = to_room(base_ad())
    assert room["source_images"] == [base_ad()["images"][0]]
    assert room["source_videos"] == []
    assert room["toilets"] is None
    assert room["project_name"] is None
    assert room["floor"] is None and room["direction"] is None
    assert room["balcony_direction"] is None and room["property_subtype"] is None
    assert room["poster_name"] is None
    # Giá trị sai kiểu/khoảng giá không được nhận (không bao giờ 0 giả tạo).
    bad, bad_reason, _ = to_room(base_ad(toilets=-1, images="not-a-list"))
    assert bad is None and bad_reason == "no_image"
    no_video_host, _, _ = to_room(base_ad(video={"url": "https://other.host/x.m3u8"}))
    assert no_video_host["source_videos"] == []


def test_size_missing_reads_area_from_text_but_not_from_distances():
    # A-2: thiếu size → đọc từ tiêu đề rồi nội dung; chỉ nhận "rộng/diện tích/dt"
    # đứng trước số hoặc số đi liền m2; "cách 45m", "hẻm 3m" không phải diện tích.
    room, reason, _ = to_room(base_ad(size=None, subject="Phòng trọ rộng 45m Quận 7"))
    assert reason is None and room["area_m2"] == 45.0
    room, _, _ = to_room(base_ad(size=None, subject="Phòng trọ Quận 7",
                                 body="Diện tích: 38.5m2, giá tốt."))
    assert room["area_m2"] == 38.5
    room, _, _ = to_room(base_ad(size=None, subject="Phòng DT45m2 còn trống"))
    assert room["area_m2"] == 45.0
    # "cách 45m" (khoảng cách) và "hẻm 3m" (lối đi) không được nhận.
    room, _, _ = to_room(base_ad(size=None, subject="Phòng cách 45m Quận 7",
                                 body="Hẻm 3m, phòng sạch."))
    assert room["area_m2"] is None
    # Điện thoại sau "đt" không bị đọc nhầm thành diện tích.
    room, _, _ = to_room(base_ad(size=None, subject="Liên hệ đt 0901234567"))
    assert room["area_m2"] is None
    # Không đọc được thì null, không điền số giả.
    room, _, _ = to_room(base_ad(size=None))
    assert room["area_m2"] is None


def test_size_out_of_range_still_rejected_even_if_text_has_area():
    # A-3: size từ API có nhưng ngoài 5–300 m² thì loại như cũ.
    rejected, reason, _ = to_room(base_ad(size=400))
    assert rejected is None and reason == "size_out_of_range"
    rejected, reason, _ = to_room(base_ad(size=2))
    assert rejected is None and reason == "size_out_of_range"


def _stream_url(uid="97400dfa043909842d35f1280ee9e0a6", *, thumbnail=False):
    return (f"https://videodelivery.net/{uid}/thumbnails/thumbnail.jpg" if thumbnail
            else f"https://videodelivery.net/{uid}/manifest/video.m3u8")


def test_source_videos_only_exact_host_and_valid_shape_capped_at_three():
    ad = base_ad(video=[
        {"url": _stream_url("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
         "thumbnail": _stream_url("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", thumbnail=True)},
        {"url": "http://videodelivery.net/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/manifest/video.m3u8"},  # không phải https
        {"url": "https://videodelivery.net.evil.com/cccccccccccccccccccccccccccccccc/manifest/video.m3u8"},  # host giả
        {"url": "https://client.videodelivery.net/dddddddddddddddddddddddddddddddd/manifest/video.m3u8"},  # subdomain
        {"url": _stream_url("eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"),
         "thumbnail": _stream_url("eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", thumbnail=True)},
        {"url": _stream_url("ffffffffffffffffffffffffffffffff"),
         "thumbnail": _stream_url("ffffffffffffffffffffffffffffffff", thumbnail=True)},
        {"url": _stream_url("1111111111111111111111111111111a"),
         "thumbnail": "https://cdn.chotot.com/wrong-shape.jpg"},  # thumbnail sai dạng
        {"url": _stream_url("22222222222222222222222222222222b")},  # thiếu thumbnail
    ])
    room, _, _ = to_room(ad)
    urls = [video["url"] for video in room["source_videos"]]
    # Mục 1, 5, 6 đạt dạng; mục 7 (thumbnail sai) và 8 (thiếu thumbnail) bị bỏ.
    assert urls == [_stream_url("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
                    _stream_url("eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"),
                    _stream_url("ffffffffffffffffffffffffffffffff")]
    assert all(v["thumbnail"].endswith("/thumbnails/thumbnail.jpg") for v in room["source_videos"])
    assert all(v["thumbnail"].startswith("https://videodelivery.net/") for v in room["source_videos"])


def test_stream_video_url_with_long_digits_survives_raw_masking():
    # URL video/thumbnail đúng dạng giữ nguyên khi lưu raw —
    # dãy số dài trong mã video không bị mask_pii che thành "[SĐT đã che]".
    uid = "97400dfa043909842d35f1280ee9e0a6"
    ad = base_ad(video={"url": _stream_url(uid),
                        "thumbnail": _stream_url(uid, thumbnail=True)})
    raw = strip_raw(ad)
    assert raw["video"]["url"] == _stream_url(uid)
    assert raw["video"]["thumbnail"] == _stream_url(uid, thumbnail=True)
    assert "[SĐT đã che]" not in json.dumps(raw, ensure_ascii=False)
    # SĐT trong văn bản thường vẫn bị che như cũ.
    assert "0901234567" not in strip_raw(base_ad(body="Gọi 0901234567"))["body"]
    # URL có "[SĐT đã che]" sai dạng → source_videos_of loại, không giữ URL hỏng.
    broken = {"url": "https://videodelivery.net/97400dfa[SĐT đã che]d35f1280ee9e0a6/manifest/video.m3u8",
              "thumbnail": "https://videodelivery.net/97400dfa[SĐT đã che]d35f1280ee9e0a6/thumbnails/thumbnail.jpg"}
    assert source_videos_of({"video": broken}) == []
    # Mục sai dạng được đếm cho manifest.
    assert videos_dropped_bad_shape({"video": broken}) == 1
    assert videos_dropped_bad_shape({"video": {"url": _stream_url(uid),
                                               "thumbnail": _stream_url(uid, thumbnail=True)}}) == 0


def test_new_spec_fields_from_params_or_plain_labels_only():
    # B-1: `params` thật là DANH SÁCH mục {id, label, value}.
    ad = base_ad(
        params=[{"id": "direction", "label": "Hướng nhà", "value": "Đông"},
                {"id": "balconydirection", "label": "Hướng ban công", "value": "Hướng Nam"},
                {"id": "property_subtype", "label": "Loại hình", "value": "Chung cư mini"}],
        floornumber=3,
    )
    room, _, _ = to_room(ad)
    assert room["direction"] == "Đông" and room["balcony_direction"] == "Hướng Nam"
    assert room["property_subtype"] == "Chung cư mini"
    assert room["floor"] == "3"
    # Chỉ có mã số chưa xác minh nghĩa thì null, không tự đoán.
    coded, _, _ = to_room(base_ad(direction=2, floornumber=2))
    assert coded["direction"] is None and coded["floor"] == "2"
    assert coded["property_subtype"] is None


def test_missing_area_name_derives_district_from_area_v2():
    # A-2: thiếu area_name thì suy quận từ mã area_v2 đã đối chiếu.
    room, reason, _ = to_room(base_ad(area_name=None, area_v2=13107))
    assert reason is None and room["area"] == "Quận 12"
    room, _, _ = to_room(base_ad(area_name=None, area_v2=13119))
    assert room["area"] == "TP. Thủ Đức"  # đi qua chuẩn hóa sẵn có
    room, _, _ = to_room(base_ad(area_name=None, area_v2=12079))
    assert room["area"] == "Quận Cầu Giấy"
    # A-3: mã lạ hoặc thiếu mã → "Không rõ", không đoán từ phường/tọa độ.
    room, _, _ = to_room(base_ad(area_name=None, area_v2=99999))
    assert room["area"] == "Không rõ"
    room, _, _ = to_room(base_ad(area_name=None))
    assert room["area"] == "Không rõ"
    # area_name có sẵn thì dùng như cũ, không cần bảng mã.
    room, _, _ = to_room(base_ad(area_name="Quận 7", area_v2=99999))
    assert room["area"] == "Quận 7"


def test_balcony_direction_code_table_and_direction_stays_label_only():
    # B-2: mã 1–8 của khóa `balconydirection` ra đúng nhãn đã đối chiếu.
    assert sorted(BALCONY_DIRECTION_NAMES) == [1, 2, 3, 4, 5, 6, 7, 8]
    for code, label in BALCONY_DIRECTION_NAMES.items():
        room, _, _ = to_room(base_ad(balconydirection=code))
        assert room["balcony_direction"] == label
        room, _, _ = to_room(base_ad(balconydirection=str(code)))
        assert room["balcony_direction"] == label
    # Mã ngoài 1–8 → null.
    room, _, _ = to_room(base_ad(balconydirection=9))
    assert room["balcony_direction"] is None
    room, _, _ = to_room(base_ad(balconydirection="0"))
    assert room["balcony_direction"] is None
    # B-3: `direction` chỉ nhận nhãn chữ; mã số → null dù bảng hướng ban công có.
    room, _, _ = to_room(base_ad(direction=2))
    assert room["direction"] is None
    room, _, _ = to_room(base_ad(direction="2"))
    assert room["direction"] is None
    room, _, _ = to_room(base_ad(direction="Tây"))
    assert room["direction"] == "Tây"
    # Hướng ban công không lọt vào kết quả tool gửi model (C1b/B).
    from backend.app.agent_tools import redact_result
    room, _, _ = to_room(base_ad(balconydirection=6))
    sent_to_model = redact_result(dict(room))
    for key in ("balcony_direction", "direction", "floor", "property_subtype", "source_videos"):
        assert key not in sent_to_model
    assert "Hướng Đông Nam" not in json.dumps(sent_to_model, ensure_ascii=False)


def test_tool_result_for_model_never_carries_display_fields_or_poster_name():
    from data.crawl_chotot import to_room
    room, _, _ = to_room(base_ad(images=["https://cdn.chotot.com/1.jpg"], toilets=1,
                                 pty_project_name="Chung cư X", full_name="Người đăng"))
    from backend.app.agent_tools import redact_result
    sent_to_model = redact_result(dict(room))
    for key in ("poster_name", "source_images", "toilets", "project_name",
                "source_videos", "floor", "direction", "balcony_direction",
                "property_subtype"):
        assert key not in sent_to_model
    assert "cdn.chotot.com" not in json.dumps(sent_to_model)
    assert "videodelivery.net" not in json.dumps(sent_to_model)
    assert "Người đăng" not in json.dumps(sent_to_model)


def test_raw_masks_text_and_non_chotot_urls_but_keeps_chotot_urls_intact():
    # LỖI 2: PII lọt qua nhánh startswith("http") — định nghĩa URL đúng phải là
    # chuỗi không có khoảng trắng, parse được http/https và host chotot.com
    # (hoặc subdomain, so theo hostname). Mọi chuỗi khác đều che PII, kể cả
    # trong list.
    ad = base_ad(
        body="https://zalo.me/0901234567 liên hệ chủ nhà",
        zalo="https://zalo.me/0901234567",
        images=["https://cdn.chotot.com/1122334455667/800x600.jpg", "gọi 0901234567"],
        extra_list=["gọi 0901234567"],
        video_url="https://video.chotot.com/998877665544332/v.mp4",
    )
    raw = strip_raw(ad)
    assert "0901234567" not in json.dumps(raw, ensure_ascii=False)
    assert raw["body"] == "https://zalo.me/[SĐT đã che] liên hệ chủ nhà"
    assert raw["zalo"] == "https://zalo.me/[SĐT đã che]"
    # URL ảnh/video chotot.com giữ nguyên kể cả khi chứa dãy số dài.
    assert raw["images"][0] == "https://cdn.chotot.com/1122334455667/800x600.jpg"
    assert raw["video_url"] == "https://video.chotot.com/998877665544332/v.mp4"
    # Chuỗi trong list được xử lý như mọi chuỗi khác (trước đây giữ nguyên).
    assert raw["images"][1] == "gọi [SĐT đã che]"
    assert raw["extra_list"] == ["gọi [SĐT đã che]"]
    # Sau strip, audit sạch: không còn SĐT ở văn bản lẫn URL lạ, và URL chotot
    # chứa dãy số dài không bị báo nhầm.
    assert audit_raw(raw) == []
    with_phone_url = {**raw, "zalo": "https://zalo.me/0901234567"}
    assert any(v.startswith("phone_in_text:zalo") for v in audit_raw(with_phone_url))
    with_phone_text = {**raw, "body": "Gọi số 0901234567"}
    assert any(v.startswith("phone_in_text:body") for v in audit_raw(with_phone_text))


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
