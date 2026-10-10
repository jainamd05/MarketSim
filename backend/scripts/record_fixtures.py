"""Records GENUINE SerpApi responses for a profile so they can be replayed offline.

Requires SERPAPI_API_KEY (in backend/.env or the environment). Uses real SerpApi credits
(at most the configured request budget). Output goes to fixtures/serpapi/recorded-<UTC date>/
with a manifest marked ``"synthetic": false``. Review the files before committing them.

    python scripts/record_fixtures.py                 # records the demonstration profile
    FIXTURE_VERSION=recorded-2026-10-10 DEMO_MODE=true uvicorn ...   # replay later
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app import models  # noqa: E402
from app.config import FIXTURES_DIR, Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.schemas.profile import demo_profile  # noqa: E402
from app.serpapi.gateway import scrub  # noqa: E402
from app.services.analysis_service import AnalysisService  # noqa: E402


def main() -> int:
    settings = Settings(database_url="sqlite://", inline_analysis=True, demo_mode="false")
    if not settings.serpapi_api_key:
        print("SERPAPI_API_KEY is not set – nothing recorded.", file=sys.stderr)
        return 2
    db = Database("sqlite://")
    db.create_all()
    service = AnalysisService(db, settings)
    with db.write() as s:
        prof = models.BusinessProfileRecord(business_type="online", business_stage="new", category="food_beverages",
                                            pilot_country="IN", data=demo_profile().model_dump(mode="json"))
        s.add(prof)
        s.flush()
        pid = prof.id
    analysis_id = service.create(pid, "live")
    version = f"recorded-{datetime.now(timezone.utc):%Y-%m-%d}"
    out = FIXTURES_DIR / version
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    with db.session() as s:
        rows = s.scalars(select(models.SearchRequest).where(models.SearchRequest.analysis_id == analysis_id)).all()
        for i, r in enumerate(rows, start=1):
            if r.response is None or r.status not in {"ok", "empty"}:
                print(f"  skipped {r.engine} {r.params}: {r.status} {r.error or ''}")
                continue
            name = f"{i:02d}_{r.engine}.json"
            text = scrub(json.dumps(r.response, ensure_ascii=False, indent=2), settings.serpapi_api_key)
            (out / name).write_text(text + "\n", encoding="utf-8")
            entries.append({"engine": r.engine, "params": r.params, "file": name})
        run = s.get(models.AnalysisRun, analysis_id)
    manifest = {"version": version, "synthetic": False, "created_at": datetime.now(timezone.utc).isoformat(),
                "note": "Genuine SerpApi responses recorded for offline replay.", "entries": entries}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Analysis {run.status}; recorded {len(entries)} response(s) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
