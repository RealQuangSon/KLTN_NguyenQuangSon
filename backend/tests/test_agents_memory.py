import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.agents import AGENT_TOOLS, ToolBox
from backend.app import memory
from backend.app.catalog import Catalog
from backend.app.main import create_app
from backend.app.memory import consented, recall
from backend.app.models import Actor, DomainError
from backend.app.semantic import QueryEmbeddingCache
from backend.app.service import HomeMatchService


def test_toolbox_enforces_allowlist_and_step_limit():
    box = ToolBox(max_steps=2)
    assert box.call("finance", "calculate_cost", lambda: "ok") == "ok"
    with pytest.raises(DomainError) as denied:
        box.call("needs", "match_catalog", lambda: None)
    assert denied.value.code == "tool_not_allowed" and box.denied == [{"agent": "needs", "tool": "match_catalog"}]
    box.call("ranking", "match_catalog", lambda: None)
    with pytest.raises(DomainError) as limited:
        box.call("ranking", "explain_candidate", lambda: None)
    assert limited.value.code == "agent_step_limit"
    # Money comes only from finance tools; no other agent can reach them.
    finance_tools = AGENT_TOOLS["finance"]
    assert all(not (tools & finance_tools) for agent, tools in AGENT_TOOLS.items() if agent != "finance")


def test_each_turn_records_the_agent_and_its_tools(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "Tìm căn hộ Cầu Giấy Hà Nội cho 2 người")
    provenance = reply["provenance"]
    assert provenance["agent"] == "needs" and provenance["tools"] == ["extract_needs", "update_draft"]
    reply = service.message(sid, renter, "Tính chi phí giúp tôi")
    provenance = reply["provenance"]
    assert provenance["agent"] == "finance" and provenance["steps"] == 0


def test_ranking_agent_is_recorded_in_run_diagnostics(service, renter, landlord, profile):
    sid = service.create_session(renter)["session_id"]
    run_id = service.confirm(sid, renter, profile, 0)["run_id"]
    assert service.repo.run(run_id)["diagnostics"]["agent"] == {
        "agent": "ranking", "tools": ["match_catalog"], "steps": 1}


def consent(service, user_id: str, value: bool):
    from backend.app.auth import update_account_profile
    with service.repo.db:  # the plain service fixture does not seed accounts
        service.repo.db.execute("INSERT INTO hm_users(id,role,password_hash) VALUES(?,?,?) "
                                "ON CONFLICT(id) DO NOTHING", (user_id, "renter", "unused"))
    update_account_profile(service.repo, user_id, {"consents": {"remember_sessions": value}})


def test_memory_requires_consent_and_only_prefills_inferred_fields(service, renter, profile):
    first = service.create_session(renter)["session_id"]
    service.confirm(first, renter, profile, 0)
    assert service.create_session(renter)["draft"]["preferences"] == []  # no consent, nothing kept
    consent(service, renter.id, True)
    assert consented(service.repo, renter.id)
    second = service.create_session(renter)["session_id"]
    service.confirm(second, renter, profile.model_copy(update={"monthly_income_vnd": 30_000_000}), 0)
    third = service.create_session(renter)
    draft = third["draft"]
    assert draft["city"] == "TP.HCM" and draft["area"] == "Quận 7"
    assert set(draft["preferences"]) == {"window", "quiet", "private_bathroom"}
    assert draft["field_status"]["city"] == "inferred"
    assert draft["evidence_ref"]["city"] == f"memory:{second}"
    assert third["confirmed_profile"] is None and third["draft_revision"] == 0
    stored = service.repo.db.execute("SELECT payload_json FROM hm_preference_memory WHERE user_id=?",
                                     (renter.id,)).fetchone()["payload_json"]
    assert "income" not in stored and "max_" not in stored and "loan" not in stored


def test_memory_api_forget_and_consent_withdrawal(service, profile):
    renter = Actor(id="renter", role="renter")
    consent(service, renter.id, True)
    sid = service.create_session(renter)["session_id"]
    service.confirm(sid, renter, profile, 0)
    with TestClient(create_app(lambda: service)) as client:
        headers = {"Authorization": "Bearer demo-renter"}
        body = client.get("/me/memory", headers=headers).json()
        assert body["consented"] and body["memory"]["fields"]["area"] == "Quận 7"
        assert client.delete("/me/memory/area", headers=headers).json() == {"status": "forgotten", "field": "area"}
        assert client.get("/me/memory", headers=headers).json()["memory"]["fields"]["area"] is None
        assert client.delete("/me/memory/monthly_income_vnd", headers=headers).status_code == 422
        client.patch("/me/profile", headers=headers, json={"consents": {"remember_sessions": False}})
        assert service.repo.db.execute("SELECT COUNT(*) AS n FROM hm_preference_memory").fetchone()["n"] == 0
        consent(service, renter.id, True)
        assert client.get("/me/memory", headers=headers).json()["memory"] is None


class CountingProvider:
    model, dimensions = "fixture-embedding", 3

    def __init__(self):
        self.calls = 0

    def embed(self, text):
        self.calls += 1
        return [1.0, 0.0, float(len(text))]


def test_query_embedding_cache_survives_a_new_cache_instance(service):
    provider, lookups = CountingProvider(), []
    cache = QueryEmbeddingCache(service.repo, provider, on_lookup=lambda hit: lookups.append(hit))
    first = cache.embed("yên tĩnh, nhiều ánh sáng")
    assert cache.embed("yên tĩnh, nhiều ánh sáng") == first
    # A restart builds a new cache object; the vector is read back from the ledger table.
    assert QueryEmbeddingCache(service.repo, provider).embed("yên tĩnh, nhiều ánh sáng") == first
    assert provider.calls == 1 and lookups == [False, True]
    service.metrics.semantic_query(hit=True)
    assert service.metrics.snapshot()["semantic_usage"]["query_cache_hits"] == 1


# --- Memory tích lũy qua các phiên -----------------------------------------------------------

def _confirm(service, renter, profile, preferences, must=()):
    sid = service.create_session(renter)["session_id"]
    service.confirm(sid, renter, profile.model_copy(update={"preferences": list(preferences),
                                                            "must_amenities": list(must)}), 0)
    return sid


def _details(service, user_id="renter"):
    return {item["key"]: item for item in recall(service.repo, user_id)["preference_details"]}


def test_preferences_accumulate_across_sessions_strongest_first(service, renter, profile):
    consent(service, renter.id, True)
    _confirm(service, renter, profile, ["window", "quiet"])
    assert service.create_session(renter)["draft"]["preferences"] == ["quiet", "window"]
    _confirm(service, renter, profile, ["quiet", "window", "balcony"])
    draft = service.create_session(renter)["draft"]
    assert draft["preferences"] == ["quiet", "window", "balcony"]
    assert draft["field_status"]["preferences"] == "inferred"
    details = _details(service)
    assert details["window"]["sessions"] == 2 and details["balcony"]["sessions"] == 1


def test_preference_removed_from_the_form_is_dropped_and_stays_out(service, renter, profile):
    consent(service, renter.id, True)
    _confirm(service, renter, profile, ["window", "quiet"])
    _confirm(service, renter, profile, ["window"])  # nháp có "quiet", khách bỏ nó trên form
    assert service.create_session(renter)["draft"]["preferences"] == ["window"]
    assert "quiet" not in _details(service)


def test_preference_absent_from_two_sessions_decays(service, renter, profile):
    consent(service, renter.id, True)
    # Các phiên mở trước khi có ghi nhớ: nháp rỗng, nên vắng mặt không phải là khách bỏ đi.
    sessions = [service.create_session(renter)["session_id"] for _ in range(3)]
    for sid, preference in zip(sessions, ("window", "quiet", "balcony")):
        service.confirm(sid, renter, profile.model_copy(update={"preferences": [preference],
                                                                "must_amenities": []}), 0)
    assert set(_details(service)) == {"quiet", "balcony"}


def test_reconfirming_one_session_counts_once(service, renter, profile):
    consent(service, renter.id, True)
    sid = _confirm(service, renter, profile, ["window"], must=[])
    revision = service.session(sid, renter)["draft_revision"]
    service.confirm(sid, renter, profile.model_copy(update={"preferences": ["window"], "must_amenities": []}), revision)
    assert _details(service)["window"]["sessions"] == 1


def test_prefill_is_capped_but_account_sees_everything(service, renter, profile):
    consent(service, renter.id, True)
    many = ["window", "quiet", "balcony", "wifi", "parking", "kitchen", "elevator", "fridge"]
    _confirm(service, renter, profile, many)
    assert len(service.create_session(renter)["draft"]["preferences"]) == memory.MAX_PREFILLED_PREFERENCES
    assert len(recall(service.repo, renter.id)["fields"]["preferences"]) == len(many)


def test_saved_signals_need_a_distinctive_amenity():
    def room(identifier, **amenities):
        return SimpleNamespace(id=identifier, published=True, amenities=amenities)
    catalog = [room(f"r{i}", wifi=True, balcony=i < 2, kitchen=None) for i in range(10)]
    saved = catalog[:2]
    # balcony: 2/2 phòng đã lưu, 20% cả kho. wifi: phòng nào cũng có nên không nói lên điều gì.
    assert memory.saved_signals(saved, catalog) == ["balcony"]
    assert memory.saved_signals(saved[:1], catalog) == []  # một phòng là chưa đủ bằng chứng
    mixed = [catalog[0], catalog[2], catalog[3], catalog[4]]
    assert memory.saved_signals(mixed, catalog) == []  # dưới 60% số phòng đã lưu


@pytest.fixture
def large_catalog_service(tmp_path):
    """Kho 12 phòng demo quá đồng đều để có tiện ích nào nổi bật giữa các phòng đã lưu."""
    agent = HomeMatchService(tmp_path / "memory.sqlite", catalog=Catalog(Path("data/catalog/rooms.json")))
    yield agent
    agent.close()


def _distinctive_amenity(service):
    rooms = [room for room in service.catalog.rooms() if room.published]
    for key in sorted(memory.AMENITIES):
        having = [room for room in rooms if room.amenities.get(key) is True]
        if len(having) >= 2 and len(having) / len(rooms) <= 0.5:
            return key, having[:2]
    raise AssertionError("catalog thử không có tiện ích đủ phân biệt")


def test_saved_rooms_only_suggest_and_can_be_muted(large_catalog_service, renter, profile):
    service = large_catalog_service
    consent(service, renter.id, True)
    key, rooms = _distinctive_amenity(service)
    for room in rooms:
        service.repo.save_room(renter.id, room.id)
    _confirm(service, renter, profile, [])
    third = service.create_session(renter)
    assert key in third["draft"]["preferences"]
    assert third["draft"]["field_status"]["preferences"] == "inferred"
    assert third["confirmed_profile"] is None
    assert _details(service)[key] == {"key": key, "sessions": 0, "from_saved": True}
    # Khách bỏ gợi ý trên form: phòng vẫn đang lưu nhưng lần sau không suy lại nữa.
    kept = [item for item in third["draft"]["preferences"] if item != key]
    service.confirm(third["session_id"], renter,
                    profile.model_copy(update={"preferences": kept, "must_amenities": []}), 0)
    assert key not in _details(service)
    _confirm(service, renter, profile, [])
    assert key not in _details(service)


def test_saved_suggestion_disappears_after_unsaving(large_catalog_service, renter, profile):
    service = large_catalog_service
    consent(service, renter.id, True)
    key, rooms = _distinctive_amenity(service)
    earlier = service.create_session(renter)["session_id"]  # nháp rỗng, không gợi ý gì để bỏ
    for room in rooms:
        service.repo.save_room(renter.id, room.id)
    _confirm(service, renter, profile, [])
    assert key in _details(service)
    for room in rooms:
        service.repo.unsave_room(renter.id, room.id)
    service.confirm(earlier, renter, profile.model_copy(update={"preferences": [], "must_amenities": []}), 0)
    assert key not in _details(service)


def test_no_consent_means_saved_rooms_are_not_mined(large_catalog_service, renter, profile):
    service = large_catalog_service
    _, rooms = _distinctive_amenity(service)
    for room in rooms:
        service.repo.save_room(renter.id, room.id)
    _confirm(service, renter, profile, [])
    assert service.repo.db.execute("SELECT COUNT(*) AS n FROM hm_preference_memory").fetchone()["n"] == 0


def test_forget_one_preference_api(service, profile):
    renter = Actor(id="renter", role="renter")
    consent(service, renter.id, True)
    _confirm(service, renter, profile, ["window", "quiet"])
    with TestClient(create_app(lambda: service)) as client:
        headers = {"Authorization": "Bearer demo-renter"}
        response = client.delete("/me/memory/preferences/quiet", headers=headers)
        assert response.json() == {"status": "forgotten", "field": "quiet"}
        body = client.get("/me/memory", headers=headers).json()
        assert body["memory"]["fields"]["preferences"] == ["window"]
        assert [item["key"] for item in body["memory"]["preference_details"]] == ["window"]
        assert client.delete("/me/memory/preferences/monthly_income_vnd", headers=headers).status_code == 422
        assert client.delete("/me/memory/preferences", headers=headers).json()["field"] == "preferences"
        assert client.get("/me/memory", headers=headers).json()["memory"]["preference_details"] == []


def test_legacy_flat_memory_row_keeps_working(service, renter, profile):
    consent(service, renter.id, True)
    with service.repo.db:
        service.repo.db.execute(
            "INSERT INTO hm_preference_memory(user_id,payload_json,source_session,updated_at) VALUES(?,?,?,?)",
            (renter.id, json.dumps({"city": "TP.HCM", "area": "Quận 7", "room_type": None, "bedrooms": None,
                                    "preferences": ["window"], "soft_description": None}), "old", "2026-01-01"))
    assert _details(service)["window"] == {"key": "window", "sessions": 1, "from_saved": False}
    _confirm(service, renter, profile, ["window", "quiet"])
    assert _details(service)["window"]["sessions"] == 2


def test_accumulated_payload_holds_no_money_or_income(service, renter, profile):
    consent(service, renter.id, True)
    _confirm(service, renter, profile.model_copy(update={"monthly_income_vnd": 30_000_000}), ["window"])
    _confirm(service, renter, profile.model_copy(update={"monthly_income_vnd": 30_000_000}), ["window", "quiet"])
    stored = service.repo.db.execute("SELECT payload_json FROM hm_preference_memory WHERE user_id=?",
                                     (renter.id,)).fetchone()["payload_json"]
    for forbidden in ("income", "max_", "loan", "destination", "30000000"):
        assert forbidden not in stored
