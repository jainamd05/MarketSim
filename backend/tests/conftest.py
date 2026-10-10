"""Shared pytest fixtures. No test performs a real SerpApi or LLM network call:
DEMO mode reads fixtures and LIVE-mode tests inject httpx.MockTransport."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Database
from app.main import create_app
from app.schemas.profile import demo_profile


def make_settings(tmp_path: Path, **overrides) -> Settings:
    base = dict(database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}", inline_analysis=True,
                demo_mode="true", serpapi_backoff_base_seconds=0.0, monte_carlo_iterations=1000,
                llm_provider="none", serpapi_api_key=None)
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def db(settings: Settings) -> Database:
    database = Database(settings.resolved_database_url)
    database.create_all()
    yield database
    database.dispose()


@pytest.fixture
def client(settings: Settings, db: Database) -> TestClient:
    app = create_app(settings, db=db)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def demo_profile_json() -> dict:
    return demo_profile().model_dump(mode="json")


def run_demo(client: TestClient, profile: dict | None = None, **body) -> str:
    profile = profile or demo_profile().model_dump(mode="json")
    pid = client.post("/api/profiles", json={"profile": profile, "status": "confirmed"}).json()["profile"]["id"]
    resp = client.post("/api/analyses", json={"profile_id": pid, **body})
    assert resp.status_code == 202, resp.text
    return resp.json()["analysis_id"]
