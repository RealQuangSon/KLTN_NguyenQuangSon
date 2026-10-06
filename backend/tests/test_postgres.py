"""Opt-in real PostgreSQL tests; temporary schemas, no model/embedding API calls."""
import pytest

from backend.app.models import Actor, CatalogStatus, Review
from backend.app.service import HomeMatchService


def test_postgres_checkpoint_restart_auth_and_stale(postgres_storage, profile):
    from backend.app.auth import SeedAuth
    renter, landlord = Actor(id="renter-a", role="renter"), Actor(id="owner-a", role="owner")
    first = HomeMatchService(postgres_storage)
    auth = SeedAuth(first.repo, first.lock)
    credentials = auth.login("renter-a", "local-renter-a-password")
    sid = first.create_session(renter)["session_id"]
    pending = first.confirm(sid, renter, profile, 0)
    review = Review(decision="approve", expected_profile_version=1, reason="Kiểm tra PG", idempotency_key="pg-1")
    first.repo.review(pending["run_id"], landlord.id, review)  # recorded event before process restart
    first.close()
    second = HomeMatchService(postgres_storage)
    try:
        assert SeedAuth(second.repo, second.lock).actor(credentials["access_token"]) == renter
        assert second.results(sid, renter)["results"] == []
        second.retry(pending["run_id"], landlord)
        assert second.results(sid, renter)["status"] == "published"
        room = second.catalog.rooms()[0]
        second.change_room_status(room.id, landlord, CatalogStatus(expected_revision=room.revision, available=False))
        assert second.results(sid, renter)["status"] == "invalidated"
    finally:
        second.close()


def test_postgres_catalog_writer_before_finalize_blocks_old_publish(postgres_storage, profile):
    renter, landlord = Actor(id="renter-a", role="renter"), Actor(id="owner-a", role="owner")
    service = HomeMatchService(postgres_storage)
    writer = HomeMatchService(postgres_storage)
    try:
        sid = service.create_session(renter)["session_id"]
        pending = service.confirm(sid, renter, profile, 0)
        request = Review(decision="approve", expected_profile_version=1, reason="Race kiểm soát", idempotency_key="race-1")
        service.repo.review(pending["run_id"], landlord.id, request)
        room = writer.catalog.rooms()[0]
        writer.change_room_status(room.id, landlord, CatalogStatus(expected_revision=room.revision, available=False))
        # Writer's transaction committed before graph finalization.
        from langgraph.types import Command
        event = service.repo.run(pending["run_id"])["decision"]
        with service.lock:
            service.recommendation_graph.invoke(Command(resume={"event_id": event["event_id"]}), service._config(pending["run_id"]))
        assert service.results(sid, renter)["status"] == "invalidated"
        assert service.results(sid, renter)["results"] == []
    finally:
        service.close()
        writer.close()


class FixtureEmbeddings:
    """Deterministic vectors for SQL integration; no evidence of model quality."""
    model = "fixture-embedding-v1"
    dimensions = 3

    def __init__(self):
        self.calls = []

    def embed(self, text):
        self.calls.append(text)
        return [1.0, 0.0, 0.0] if "quiet: có" in text or text == "phòng yên tĩnh" else [0.0, 1.0, 0.0]


def test_postgres_pgvector_exact_coverage_versions_and_reindex(postgres_storage, profile):
    from backend.app.models import DomainError, Room
    from backend.app.semantic import PostgresSemantic

    service = HomeMatchService(postgres_storage)
    try:
        provider = FixtureEmbeddings()
        scorer = PostgresSemantic(service.repo, service.catalog, provider)
        service.catalog.semantic_scorer = scorer
        assert scorer.index()["indexed"] == len(service.catalog.rooms())
        initial_calls = len(provider.calls)
        assert scorer.index()["indexed"] == 0 and len(provider.calls) == initial_calls
        profile.soft_description = "phòng yên tĩnh"
        baseline, base_diagnostics = service.catalog.rank(profile, "B1")
        proposed, diagnostics = service.catalog.rank(profile, "P")
        assert {item.room_id for item in baseline} == {item.room_id for item in proposed}
        assert diagnostics["algorithm"] == "P" and diagnostics["ranking_version"] != base_diagnostics["ranking_version"]
        assert diagnostics["ranking_config"]["embedding_model"] == provider.model
        assert len(provider.calls) == initial_calls + 1
        by_id = {item.room_id: item for item in baseline}
        for item in proposed:
            assert item.cost == by_id[item.room_id].cost
            assert item.components["semantic"] in {0.5, 1.0}
            assert item.score == round(.7 * by_id[item.room_id].score + .3 * item.components["semantic"], 6)

        original = next(room for room in service.catalog.rooms() if room.id == proposed[0].room_id)
        priced = Room.model_validate({**original.model_dump(), "revision": original.revision + 1,
                                     "quote": {**original.quote.model_dump(), "rent_vnd": original.quote.rent_vnd + 1}})
        service.catalog.import_rooms([priced])
        calls = len(provider.calls)
        assert scorer.index()["indexed"] == 0 and len(provider.calls) == calls
        changed = Room.model_validate({**priced.model_dump(), "revision": priced.revision + 1,
                                      "amenities": {**priced.amenities, "quiet": not bool(priced.amenities.get("quiet"))}})
        service.catalog.import_rooms([changed])
        with pytest.raises(DomainError) as error:
            scorer.similarities(profile.soft_description, [changed.id])
        assert error.value.code == "semantic_unavailable" and len(provider.calls) == calls
        assert scorer.index()["indexed"] == 1 and len(provider.calls) == calls + 1
        assert scorer.similarities(profile.soft_description, [changed.id])
        service.repo.db.execute("UPDATE hm_embeddings SET embedding='[0,0,0]'::vector WHERE room_id=?", (changed.id,))
        with pytest.raises(DomainError) as error:
            scorer.similarities(profile.soft_description, [changed.id])
        assert error.value.code == "semantic_unavailable"
    finally:
        service.close()


def test_postgres_missing_vector_falls_back_without_dropping_eligible_rooms(postgres_storage, renter, landlord, profile):
    from backend.app.semantic import PostgresSemantic

    service = HomeMatchService(postgres_storage)
    try:
        service.catalog.semantic_scorer = PostgresSemantic(service.repo, service.catalog, FixtureEmbeddings())
        profile.soft_description = "phòng yên tĩnh"
        expected, _ = service.catalog.match(profile, "B1")
        service.matching_method = "P"
        sid = service.create_session(renter)["session_id"]
        pending = service.confirm(sid, renter, profile, 0)
        draft = service.draft(pending["run_id"], landlord)
        assert draft["diagnostics"]["algorithm"] == "B1_fallback"
        assert draft["diagnostics"]["semantic_status"] == "unavailable"
        assert [item["room_id"] for item in draft["items"]] == [item.room_id for item in expected]
        assert service.results(sid, renter)["results"] == []
    finally:
        service.close()
