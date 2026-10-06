import pytest
import os
from urllib.parse import quote
from uuid import uuid4

from backend.app.models import Actor, Profile, Scenario
from backend.app.service import HomeMatchService


@pytest.fixture(autouse=True)
def offline_mode(monkeypatch):
    monkeypatch.setenv("HOMEMATCH_LLM_MODE", "demo")
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "demo")
    monkeypatch.setenv("HOMEMATCH_MATCHING_METHOD", "B1")
    monkeypatch.setenv("HOMEMATCH_EMBEDDING_MODE", "disabled")
    # Tests trigger automation explicitly; no background thread inside TestClient apps.
    monkeypatch.setenv("HOMEMATCH_JOBS_INTERVAL_SECONDS", "0")


@pytest.fixture
def postgres_storage():
    dsn = os.getenv("HOMEMATCH_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("HOMEMATCH_TEST_DATABASE_URL not configured; PostgreSQL not claimed tested")
    import psycopg
    schema = "hm_test_" + uuid4().hex
    admin = psycopg.connect(dsn, autocommit=True)
    admin.execute(f'CREATE SCHEMA "{schema}"')
    separator = "&" if "?" in dsn else "?"
    scoped = dsn + separator + "options=" + quote(f"-csearch_path={schema},public")
    try:
        yield scoped
    finally:
        admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        admin.close()


@pytest.fixture(params=["sqlite", "postgres"] if os.getenv("HOMEMATCH_TEST_DATABASE_URL") else ["sqlite"])
def storage(request, tmp_path):
    return request.getfixturevalue("postgres_storage") if request.param == "postgres" else tmp_path / "test.sqlite"


@pytest.fixture
def service(storage):
    agent = HomeMatchService(storage)
    yield agent
    agent.close()


@pytest.fixture
def renter():
    return Actor(id="renter-a", role="renter")


@pytest.fixture
def owner():
    return Actor(id="owner-a", role="owner")


@pytest.fixture
def landlord():
    return Actor(id="owner-a", role="owner")


@pytest.fixture
def admin():
    return Actor(id="admin-a", role="admin")


@pytest.fixture
def profile():
    return Profile(city="TP.HCM", area="Quận 7", max_monthly_cost_vnd=3_500_000,
                   max_initial_cash_vnd=6_500_000, must_amenities=["private_bathroom"],
                   preferences=["window", "quiet"], scenario=Scenario())
