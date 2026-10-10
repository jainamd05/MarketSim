"""Runs the demonstration profile through the real LangGraph workflow (DEMO fixtures, in-memory
SQLite) and saves every dashboard API response to frontend/src/test/fixtures/demo-analysis.json.

The frontend test suite renders the dashboard from this saved analysis.

    python scripts/export_demo_analysis.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.main import create_app  # noqa: E402
from app.schemas.profile import demo_profile  # noqa: E402

OUT = ROOT.parent / "frontend" / "src" / "test" / "fixtures" / "demo-analysis.json"


def main() -> None:
    settings = Settings(_env_file=None, database_url="sqlite://", inline_analysis=True, demo_mode="true", llm_provider="none")
    with TestClient(create_app(settings, db=Database("sqlite://"))) as c:
        pid = c.post("/api/profiles", json={"profile": demo_profile().model_dump(mode="json"), "status": "confirmed"}).json()["profile"]["id"]
        aid = c.post("/api/analyses", json={"profile_id": pid}).json()["analysis_id"]
        bundle = {
            "config": c.get("/api/config").json(),
            "status": c.get(f"/api/analyses/{aid}").json(),
            "events": c.get(f"/api/analyses/{aid}/events").json(),
            "competitors": c.get(f"/api/analyses/{aid}/competitors").json(),
            "trends": c.get(f"/api/analyses/{aid}/trends").json(),
            "strategies": c.get(f"/api/analyses/{aid}/strategies").json(),
            "report": c.get(f"/api/analyses/{aid}/report").json(),
            "evidence": c.get(f"/api/analyses/{aid}/evidence").json(),
        }
    assert bundle["status"]["status"] in {"completed", "partial"}, bundle["status"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(bundle, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Saved analysis {aid} ({bundle['status']['status']}) to {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
