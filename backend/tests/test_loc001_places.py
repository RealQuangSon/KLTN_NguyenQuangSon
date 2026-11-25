"""LOC-001: danh mục địa danh đã kiểm chứng + find_place tra bản đồ (offline).

Geocoder luôn là bản giả (`fetch` tiêm vào); conftest đặt HOMEMATCH_GEOCODER=off nên
không test nào chạm mạng."""
import json
from types import SimpleNamespace

import pytest

from backend.app import geocode, locations
from backend.app.geocode import Geocoder, sanitize_query, uncertainty_from_bbox
from backend.app.interpreter import OpenAIInterpreter
from backend.app.service import HomeMatchService
from backend.tests.test_agent_loop import FakeClient, call, message
from data import verify_places

HN_VIEWBOX_PREFIX = "105.28"


def meters(lat1, lon1, lat2, lon2):
    return verify_places.distance_m(lat1, lon1, lat2, lon2)


# ---------------------------------------------------------------- danh mục

def test_every_place_has_kind_source_verified_at_and_realistic_uncertainty():
    places = locations._PLACES
    assert len(places) >= 80
    assert verify_places.check_structure(places) == []
    for place in places:
        assert place["kind"] in {"school", "hospital", "transit", "mall", "work", "area"}
        assert place["source"] in {"osm", "manual"}
        assert place["verified_at"] == "2026-11-23"
        assert place["uncertainty_m"] >= 150


BARE_AREA_NAMES = {"my dinh", "gia lam", "linh trung", "tan tao", "mien tay", "times", "landmark", "xuan thuy",
                   "giap bat", "chu nhan", "quin te", "hus", "hanu_sp"}


def test_no_alias_collides_with_area_names_or_bare_area_list():
    area_names = set()
    for _city, name, alias, _pattern in locations._AREA_PATTERNS:
        area_names |= {locations.fold(name), alias}
    for place in locations._PLACES:
        for value in [*place["names"], *place["aliases"]]:
            folded = locations.fold(value)
            assert folded not in area_names, (place["id"], value)
            if place["id"] != "hn-hus":      # "hus" là viết tắt đúng của KHTN Hà Nội
                assert folded not in BARE_AREA_NAMES, (place["id"], value)


def test_catalog_coordinates_are_the_verified_ones():
    giap_bat = locations.resolve_place("gần bến xe Giáp Bát")
    assert giap_bat["id"] == "hn-ben-xe-giap-bat"
    assert meters(giap_bat["latitude"], giap_bat["longitude"], 20.9806, 105.8422) <= 300
    nuce = locations.resolve_place("gần ĐH Xây dựng")
    assert nuce["id"] == "hn-nuce"
    assert meters(nuce["latitude"], nuce["longitude"], 21.0006, 105.8452) <= 400
    assert locations.resolve_place("gần Đại học Xây dựng Hà Nội")["id"] == "hn-nuce"
    assert locations.resolve_place("gần dai hoc xay dung")["id"] == "hn-nuce"


def test_area_words_are_not_places_but_typed_names_are():
    assert locations.resolve_place("phòng ở Mỹ Đình") is None
    assert locations.resolve_place("phòng ở Gia Lâm") is None
    assert locations.resolve_place("gần bến xe Mỹ Đình")["id"] == "hn-ben-xe-my-dinh"
    assert locations.resolve_place("gần Landmark", "Hà Nội") is None
    assert locations.resolve_place("gần Keangnam Landmark 72")["id"] == "hn-keangnam"
    assert locations.resolve_place("gần Landmark 81")["id"] == "hcm-landmark81"


def test_school_abbreviations_point_at_the_right_school():
    assert locations.resolve_place("gần hutech")["label"] == "Đại học Công nghệ TP.HCM"
    assert locations.resolve_place("gần hcmute")["id"] == "hcm-hcmute"
    assert locations.resolve_place("gần hanu")["label"] == "Đại học Hà Nội"
    assert locations.resolve_place("gần hnue")["label"] == "Đại học Sư phạm Hà Nội"
    assert locations.resolve_place("gần hcmus")["city"] == "TP.HCM"
    assert locations.resolve_place("gần hus")["city"] == "Hà Nội"
    assert locations.resolve_place("gần lotte center")["id"] == "hn-lotte-center"


def test_place_kind_reads_kind_field_before_name_heuristic():
    assert locations.place_kind({"kind": "mall", "names": ["Đại học giả"]}) == "mall"
    assert locations.place_kind({"names": ["Bệnh viện X"]}) == "hospital"
    kinds = {locations.place_kind(place) for place in locations._PLACES}
    assert kinds == {"school", "hospital", "transit", "mall", "work", "area"}


def test_candidates_report_both_cities_for_a_bare_ambiguous_name():
    for text in ("Bách Khoa", "Đại học Bách Khoa", "ĐH Bách khoa"):
        found = locations.resolve_place_candidates(text)
        assert {item["city"] for item in found} == {"Hà Nội", "TP.HCM"}, text
        assert locations.resolve_place(text) is None
    assert [item["id"] for item in locations.resolve_place_candidates("Bách Khoa", "Hà Nội")] == ["hn-hust"]
    assert locations.place_by_id("hn-hust")["label"] == "Đại học Bách Khoa Hà Nội"
    assert locations.place_by_id("geo:1234") is None


# ---------------------------------------------------------------- geocoder

def nominatim_item(name, lat, lon, box=None, addresstype="amenity", category="amenity"):
    item = {"lat": str(lat), "lon": str(lon), "name": name, "display_name": f"{name}, Phường X, Việt Nam",
            "addresstype": addresstype, "category": category}
    if box:
        item["boundingbox"] = [str(value) for value in box]
    return item


class Fetch:
    """Nominatim giả: trả theo thành phố của viewbox; đếm số lần gọi."""

    def __init__(self, hanoi=None, hcm=None, status=200):
        self.hanoi, self.hcm, self.status = hanoi or [], hcm or [], status
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, params, timeout):
        self.calls.append((url, params))
        if "nominatim" not in url:
            return self.status, None
        if self.status != 200:
            return self.status, None
        return 200, self.hanoi if params["viewbox"].startswith(HN_VIEWBOX_PREFIX) else self.hcm


def geo(fetch, provider="nominatim", **kwargs):
    return Geocoder(provider=provider, fetch=fetch, sleep=lambda _s: None, **kwargs)


PHENIKAA = nominatim_item("Đại học Phenikaa", 20.9628, 105.7458, box=(20.9590, 20.9666, 105.7420, 105.7496))


def test_geocoder_off_never_calls_fetch():
    fetch = Fetch(hanoi=[PHENIKAA])
    assert geo(fetch, "off").lookup("Đại học Phenikaa", "Hà Nội") == {"status": "off"}
    assert fetch.calls == []
    with pytest.raises(ValueError):
        Geocoder(provider="bogus")


def test_conftest_sets_geocoder_off_for_the_service(service):
    assert service.geocoder.enabled is False


def test_geocoder_ok_result_uses_bbox_uncertainty_city_and_privacy_params():
    fetch = Fetch(hanoi=[PHENIKAA])
    result = geo(fetch).lookup("gần Đại học Phenikaa", "Hà Nội")
    assert result["status"] == "ok" and result["place_id"].startswith("geo:")
    assert (result["latitude"], result["longitude"]) == (20.9628, 105.7458)
    assert result["uncertainty_m"] == uncertainty_from_bbox([20.9590, 20.9666, 105.7420, 105.7496])
    assert 150 <= result["uncertainty_m"] <= 2000
    (url, params), = fetch.calls
    assert params["q"] == "Đại học Phenikaa"          # bỏ "gần"; thành phố nằm ở viewbox
    assert params["bounded"] == 1 and params["countrycodes"] == "vn"
    assert set(params) == {"q", "format", "countrycodes", "limit", "viewbox", "bounded", "accept-language"}


def test_geocoder_cache_avoids_second_request_and_paces_nominatim():
    fetch = Fetch(hanoi=[PHENIKAA])
    sleeps, now = [], [100.0]
    geocoder = Geocoder(provider="nominatim", fetch=fetch, clock=lambda: now[0], sleep=sleeps.append)
    geocoder.lookup("Đại học Phenikaa", "Hà Nội")
    geocoder.lookup("đại học PHENIKAA", "Hà Nội")        # cùng khóa sau fold → cache
    assert len(fetch.calls) == 1
    geocoder.lookup("Đại học Khác Hoàn Toàn", "Hà Nội")
    assert len(fetch.calls) == 2 and sleeps and sleeps[0] >= 1.0


def test_geocoder_drops_results_outside_the_city_box_and_coarse_results():
    far = nominatim_item("Đại học Phenikaa", 10.80, 106.70)       # tọa độ TP.HCM khi tra Hà Nội
    assert geo(Fetch(hanoi=[far])).lookup("Đại học Phenikaa", "Hà Nội")["status"] == "not_found"
    coarse = nominatim_item("Hà Nội", 21.03, 105.85, addresstype="city", category="boundary")
    assert geo(Fetch(hanoi=[coarse])).lookup("Hà Nội", "Hà Nội")["status"] == "not_found"
    unrelated = nominatim_item("Công viên Thống Nhất", 21.0, 105.85)
    assert geo(Fetch(hanoi=[unrelated])).lookup("Đại học Phenikaa", "Hà Nội")["status"] == "not_found"


def test_geocoder_district_result_is_area_not_anchor():
    district = nominatim_item("Dịch Vọng Hậu", 21.04, 105.78, addresstype="suburb", category="boundary")
    result = geo(Fetch(hanoi=[district])).lookup("Dịch Vọng Hậu", "Hà Nội")
    assert result["status"] == "area" and result["label"] == "Dịch Vọng Hậu"


def test_geocoder_without_city_is_ambiguous_when_both_cities_match():
    hn = nominatim_item("Công viên Hòa Bình", 21.07, 105.77)
    hcm = nominatim_item("Công viên Hòa Bình", 10.80, 106.70)
    result = geo(Fetch(hanoi=[hn], hcm=[hcm])).lookup("Công viên Hòa Bình")
    assert result["status"] == "ambiguous"
    assert {item["city"] for item in result["candidates"]} == {"Hà Nội", "TP.HCM"}
    only_hn = geo(Fetch(hanoi=[hn])).lookup("Công viên Hòa Bình")
    assert only_hn["status"] == "ok" and only_hn["city"] == "Hà Nội"


def test_geocoder_network_errors_are_not_found_and_not_cached():
    fetch = Fetch(status=500)
    geocoder = geo(fetch)
    assert geocoder.lookup("Đại học Phenikaa", "Hà Nội")["status"] == "not_found"
    fetch.status = 200
    fetch.hanoi = [PHENIKAA]
    assert geocoder.lookup("Đại học Phenikaa", "Hà Nội")["status"] == "ok"

    def boom(*_args):
        raise TimeoutError("chậm")
    assert geo(boom).lookup("Đại học Phenikaa", "Hà Nội")["status"] == "not_found"


def test_goong_403_disables_goong_then_falls_back_to_nominatim():
    calls = []

    def fetch(url, params, timeout):
        calls.append(url)
        if "goong" in url:
            return 403, None
        return 200, [PHENIKAA]
    geocoder = geo(fetch, "auto", goong_key="fake-key")
    assert geocoder.lookup("Đại học Phenikaa", "Hà Nội")["status"] == "ok"
    assert any("goong" in url for url in calls) and any("nominatim" in url for url in calls)
    calls.clear()
    geocoder.lookup("Đại học Khác", "Hà Nội")
    assert not any("goong" in url for url in calls)          # Goong bị tắt tới khi khởi động lại


@pytest.mark.parametrize("text", [
    "số 12 ngõ 34 Trần Duy Hưng", "12 ngõ 5 Láng Hạ", "hẻm 34/5 Lê Văn Sỹ", "gần 45 Nguyễn Trãi",
    "nhà 12/3 Bạch Đằng", "tầng 5 tòa A", "0912345678 Cầu Giấy", "liên hệ a@b.com", "34B Hoàng Cầu"])
def test_addresses_and_contacts_are_never_sent(text):
    assert sanitize_query(text)[0] is None
    fetch = Fetch(hanoi=[PHENIKAA])
    assert geo(fetch).lookup(text, "Hà Nội")["status"] == "address_not_sent"
    assert fetch.calls == []


def test_landmark_names_with_numbers_are_still_sent():
    assert sanitize_query("gần Landmark 81")[0] == "Landmark 81"
    assert sanitize_query("Bệnh viện 115")[0] == "Bệnh viện 115"
    assert sanitize_query("x" * 200)[0] == "x" * 80


# ---------------------------------------------------------------- vòng lặp agent

@pytest.fixture
def loop_service(tmp_path):
    agent = HomeMatchService(tmp_path / "loc001.sqlite", interpreter=OpenAIInterpreter(
        client=SimpleNamespace(), model="fixture-model"))
    yield agent
    agent.close()


def tool_texts(client):
    """Nội dung mọi message role=tool đã gửi lại cho model."""
    out = []
    for request in client.requests:
        out += [str(m["content"]) for m in request["messages"] if m.get("role") == "tool"]
    return "\n".join(out)


def run(loop_service, renter, turns, text):
    client = FakeClient(turns)
    loop_service.interpreter.client = client
    sid = loop_service.create_session(renter)["session_id"]
    reply = loop_service.message(sid, renter, text)
    return sid, reply, client


def test_unknown_place_is_geocoded_then_written_by_place_id(loop_service, renter):
    fetch = Fetch(hanoi=[PHENIKAA])
    loop_service.geocoder = geo(fetch)
    # place_id phụ thuộc kết quả giả → tính trước bằng cùng geocoder.
    place_id = geo(Fetch(hanoi=[PHENIKAA])).lookup("Đại học Phenikaa", "Hà Nội")["place_id"]
    sid, reply, client = run(loop_service, renter, [
        message(tool_calls=[call("c1", "find_place", query="Đại học Phenikaa", city_hint="Hà Nội")]),
        message(tool_calls=[call("c2", "update_needs",
                                 patch={"city": "Hà Nội", "destination_place_id": place_id})]),
        message(content="Mình hiểu Đại học Phenikaa ở Hà Đông, vị trí ước tính — sai thì bạn sửa nhé."),
    ], "Tìm phòng trọ gần Đại học Phenikaa")
    assert reply["agent_mode"] == "loop"
    assert place_id in tool_texts(client) and '"source": "geocoder"' in tool_texts(client)
    destination = loop_service.session(sid, renter)["draft"]["destination"]
    assert (destination["latitude"], destination["longitude"]) == (20.9628, 105.7458)
    assert destination["uncertainty_m"] == uncertainty_from_bbox([20.9590, 20.9666, 105.7420, 105.7496])
    assert destination["label"] == "Đại học Phenikaa"
    assert len(fetch.calls) == 1
    # Chỉ tên + khung thành phố rời máy: không id phiên/người dùng trong tham số.
    assert sid not in json.dumps(fetch.calls[0][1]) and renter.id not in json.dumps(fetch.calls[0][1])


def test_destination_text_falls_back_to_the_session_cache(loop_service, renter):
    loop_service.geocoder = geo(Fetch(hanoi=[PHENIKAA]))
    sid, reply, client = run(loop_service, renter, [
        message(tool_calls=[call("c1", "find_place", query="Đại học Phenikaa", city_hint="Hà Nội")]),
        message(tool_calls=[call("c2", "update_needs",
                                 patch={"city": "Hà Nội", "destination_text": "Đại học Phenikaa"})]),
        message(content="Đã ghim Đại học Phenikaa (vị trí ước tính)."),
    ], "Tìm phòng gần Đại học Phenikaa")
    assert loop_service.session(sid, renter)["draft"]["destination"]["latitude"] == 20.9628


def test_unknown_or_unmentioned_place_ids_are_rejected(loop_service, renter):
    loop_service.geocoder = geo(Fetch(hanoi=[PHENIKAA]))
    sid, reply, client = run(loop_service, renter, [
        message(tool_calls=[call("c1", "update_needs", patch={"destination_place_id": "geo:deadbeef"})]),
        message(tool_calls=[call("c2", "find_place", query="Đại học Phenikaa", city_hint="Hà Nội")]),
        message(content="Mình cần bạn nói rõ nơi muốn ở gần."),
    ], "Mình cần thuê chỗ ở, bạn tư vấn giúp nhé")
    assert "unknown_place" in tool_texts(client)
    # Có place_id nhưng khách chưa hề nêu tên → bị chặn bởi kiểm tra HN-13.3.5.
    place_id = geo(Fetch(hanoi=[PHENIKAA])).lookup("Đại học Phenikaa", "Hà Nội")["place_id"]
    client2 = FakeClient([
        message(tool_calls=[call("d1", "update_needs", patch={"destination_place_id": place_id})]),
        message(content="Bạn muốn ở gần đâu?"),
    ])
    loop_service.interpreter.client = client2
    loop_service.message(sid, renter, "Mình cần chỗ ở sạch sẽ, bạn gợi ý giúp")
    assert "destination_not_mentioned" in tool_texts(client2)
    assert loop_service.session(sid, renter)["draft"]["destination"] is None


def test_address_in_query_never_reaches_the_geocoder(loop_service, renter):
    fetch = Fetch(hanoi=[PHENIKAA])
    loop_service.geocoder = geo(fetch)
    sid, reply, client = run(loop_service, renter, [
        message(tool_calls=[call("c1", "find_place", query="số 12 ngõ 34 Trần Duy Hưng", city_hint="Hà Nội")]),
        message(content="Bạn cho mình tên đường hoặc một địa danh gần đó nhé?"),
    ], "Tìm phòng gần số 12 ngõ 34 Trần Duy Hưng")
    assert fetch.calls == []
    assert "address_not_sent" in tool_texts(client)


def test_geocoder_off_in_loop_returns_not_found_without_fetch(loop_service, renter):
    fetch = Fetch(hanoi=[PHENIKAA])
    loop_service.geocoder = geo(fetch, "off")
    sid, reply, client = run(loop_service, renter, [
        message(tool_calls=[call("c1", "find_place", query="Đại học Phenikaa", city_hint="Hà Nội")]),
        message(content="Mình chưa tra được nơi này; bạn cho mình quận nhé?"),
    ], "Tìm phòng gần Đại học Phenikaa")
    assert fetch.calls == []
    assert "không tìm thấy" in tool_texts(client).lower()


def test_out_of_box_result_is_rejected_in_loop(loop_service, renter):
    fetch = Fetch(hanoi=[nominatim_item("Đại học Phenikaa", 10.80, 106.70)])
    loop_service.geocoder = geo(fetch)
    sid, reply, client = run(loop_service, renter, [
        message(tool_calls=[call("c1", "find_place", query="Đại học Phenikaa", city_hint="Hà Nội")]),
        message(content="Mình chưa tìm thấy nơi này."),
    ], "Tìm phòng gần Đại học Phenikaa")
    assert '"found": false' in tool_texts(client).lower()
    assert loop_service.session(sid, renter)["draft"]["destination"] is None


def test_bach_khoa_without_city_is_ambiguous_with_two_candidates(loop_service, renter):
    fetch = Fetch()
    loop_service.geocoder = geo(fetch)
    sid, reply, client = run(loop_service, renter, [
        message(tool_calls=[call("c1", "find_place", query="Bách Khoa")]),
        message(content="Bạn muốn ở gần Bách Khoa nào: Hà Nội hay TP.HCM?"),
    ], "Tìm phòng gần Bách Khoa")
    text = tool_texts(client)
    assert '"reason": "ambiguous"' in text and "Hà Nội" in text and "TP.HCM" in text
    assert fetch.calls == []                                  # mơ hồ trong danh mục: không ra bản đồ


def test_catalog_hit_returns_place_id_and_wins_over_the_map(loop_service, renter):
    fetch = Fetch(hanoi=[PHENIKAA])
    loop_service.geocoder = geo(fetch)
    sid, reply, client = run(loop_service, renter, [
        message(tool_calls=[call("c1", "find_place", query="HUST", city_hint="Hà Nội")]),
        message(tool_calls=[call("c2", "update_needs",
                                 patch={"city": "Hà Nội", "destination_place_id": "hn-hust"})]),
        message(content="Mình hiểu HUST ở Đại Cồ Việt; sai thì bạn sửa."),
    ], "Tìm phòng gần HUST")
    assert '"source": "catalog"' in tool_texts(client) and fetch.calls == []
    assert loop_service.session(sid, renter)["draft"]["destination"]["label"] == "Đại học Bách Khoa Hà Nội"


def test_demo_graph_branch_stays_catalog_only(service, renter):
    service.geocoder = geo(Fetch(hanoi=[PHENIKAA]))
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "Tìm phòng trọ gần Đại học Phenikaa ở Hà Nội")
    assert service.session(sid, renter)["draft"]["destination"] is None
    assert service.geocoder.fetch.calls == []
