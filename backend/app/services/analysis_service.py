"""Creates analysis runs, executes the LangGraph workflow on a background thread and
persists every result to SQLite. No Redis/Celery: a small ThreadPoolExecutor is enough
for a local MVP, and progress is persisted so the browser can poll or stream it."""
from __future__ import annotations

import logging
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select

from app import models
from app.agents.graph import GRAPH_RECURSION_LIMIT, build_graph
from app.agents.report import content_hash
from app.agents.runtime import AnalysisRuntime, EventEmitter
from app.config import Settings
from app.db import Database
from app.llm.adapter import get_llm
from app.schemas.analysis import SearchOutcome
from app.serpapi.gateway import FixtureStore, ResponseCache, SerpApiGateway, SyntheticFixtureStore

log = logging.getLogger("marketsim.service")


class AnalysisModeError(ValueError):
    pass


class AnalysisService:
    def __init__(self, db: Database, settings: Settings, *, serpapi_transport: httpx.BaseTransport | None = None,
                 llm_transport: httpx.BaseTransport | None = None, max_workers: int = 2) -> None:
        self.db = db
        self.settings = settings
        self.serpapi_transport = serpapi_transport
        self.llm_transport = llm_transport
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="analysis")
        self.futures: dict[str, Future] = {}

    # --------------------------------------------------------------- create
    def resolve_mode(self, requested: str | None) -> str:
        mode = requested or self.settings.default_data_mode
        if mode == "live" and not self.settings.has_serpapi_key:
            raise AnalysisModeError("LIVE mode requires SERPAPI_API_KEY. Configure it in backend/.env or choose DEMO mode.")
        if mode == "live" and self.settings.demo_mode == "true":
            raise AnalysisModeError("The server is configured with DEMO_MODE=true; LIVE analyses are disabled.")
        return mode

    def create(self, profile_id: str, requested_mode: str | None, budget: int | None = None) -> str:
        mode = self.resolve_mode(requested_mode)
        with self.db.write() as s:
            prof = s.get(models.BusinessProfileRecord, profile_id)
            if prof is None:
                raise KeyError(profile_id)
            prof.status = "confirmed"
            run = models.AnalysisRun(
                profile_id=profile_id, profile_snapshot=prof.data, mode=mode, status="queued",
                request_budget=budget or self.settings.max_serpapi_requests_per_analysis,
                llm_mode="llm" if self.settings.llm_enabled else "deterministic",
                fixture_version=self.settings.fixture_version if mode == "demo" else None,
            )
            s.add(run)
            s.flush()
            analysis_id = run.id
        if self.settings.inline_analysis:
            self.run(analysis_id)
        else:
            self.futures[analysis_id] = self.executor.submit(self.run, analysis_id)
        return analysis_id

    # ------------------------------------------------------------------ run
    def _demo_fixtures(self) -> FixtureStore:
        """Recorded fixtures first; when enabled, synthetic payloads fill any gaps.

        This keeps the demonstration profile byte-identical while letting any other
        questionnaire answer produce a populated DEMO run.
        """
        if self.settings.demo_synthetic_fallback:
            return SyntheticFixtureStore(self.settings.fixture_version)
        return FixtureStore(self.settings.fixture_version)

    def build_runtime(self, run: models.AnalysisRun) -> AnalysisRuntime:
        emitter = EventEmitter(run.id, sink=lambda e: self._persist_event(run.id, e))

        def persist(outcome: SearchOutcome) -> None:
            self._persist_search(run.id, outcome)
            self._update_run(run.id, requests_used=gateway.requests_used, cache_hits=gateway.cache_hits)

        gateway = SerpApiGateway(
            mode=run.mode, settings=self.settings, budget=run.request_budget,
            cache=ResponseCache(self.db) if run.mode == "live" else None,
            fixtures=self._demo_fixtures() if run.mode == "demo" else None,
            transport=self.serpapi_transport, on_event=emitter.tool_event, persist=persist,
        )
        llm = get_llm(self.settings, self.llm_transport)
        rt = AnalysisRuntime(analysis_id=run.id, mode=run.mode, settings=self.settings, gateway=gateway,
                             emitter=emitter, llm=llm)
        rt.on_agent_change = lambda agent: self._update_run(run.id, current_agent=agent,
                                                            requests_used=gateway.requests_used,
                                                            cache_hits=gateway.cache_hits)
        return rt

    def run(self, analysis_id: str) -> None:
        with self.db.session() as s:
            run = s.get(models.AnalysisRun, analysis_id)
            if run is None:
                return
            s.expunge(run)
        rt = self.build_runtime(run)
        self._update_run(analysis_id, status="running", started_at=datetime.now(timezone.utc), llm_mode=rt.llm_mode)
        rt.emitter.emit("supervisor", "analysis_started",
                        f"Analysis started in {run.mode.upper()} mode ({rt.llm_mode}); request budget {run.request_budget}.",
                        mode=run.mode, budget=run.request_budget)
        try:
            graph = build_graph(rt)
            final = graph.invoke({"analysis_id": analysis_id, "mode": run.mode, "profile": run.profile_snapshot,
                                  "observations": [], "warnings": [], "failed_agents": [], "node_trace": [],
                                  "critic_rounds": [], "strategy_history": [], "simulation_history": []},
                                 {"recursion_limit": GRAPH_RECURSION_LIMIT})
            self._persist_results(analysis_id, final, rt)
            status = final.get("report", {}).get("status", "partial")
            rt.emitter.emit("report_composer", "analysis_completed",
                            f"Analysis {status}. {rt.gateway.requests_used} of {rt.gateway.budget} request(s) used.",
                            status=status, requests_used=rt.gateway.requests_used)
            self._update_run(analysis_id, status=status, completed_at=datetime.now(timezone.utc), current_agent=None,
                             requests_used=rt.gateway.requests_used, cache_hits=rt.gateway.cache_hits)
        except Exception as exc:  # pragma: no cover - last-resort guard
            log.error("analysis %s failed: %s", analysis_id, traceback.format_exc())
            rt.emitter.emit("supervisor", "analysis_failed", f"Analysis failed: {type(exc).__name__}: {str(exc)[:300]}")
            self._update_run(analysis_id, status="failed", error=f"{type(exc).__name__}: {str(exc)[:500]}",
                             completed_at=datetime.now(timezone.utc), current_agent=None)

    # -------------------------------------------------------------- persist
    def _update_run(self, analysis_id: str, **fields: Any) -> None:
        with self.db.write() as s:
            run = s.get(models.AnalysisRun, analysis_id)
            if run is not None:
                for k, v in fields.items():
                    setattr(run, k, v)

    def _persist_event(self, analysis_id: str, event: dict[str, Any]) -> None:
        with self.db.write() as s:
            s.add(models.AgentEvent(analysis_id=analysis_id, seq=event["seq"], ts=datetime.fromisoformat(event["ts"]),
                                    agent=event["agent"], event_type=event["event_type"], message=event["message"],
                                    meta={**event["meta"], "agent_label": event["agent_label"]}))

    def _persist_search(self, analysis_id: str, o: SearchOutcome) -> None:
        with self.db.write() as s:
            s.add(models.SearchRequest(
                analysis_id=analysis_id, agent=o.agent, engine=o.engine, params=o.params, purpose=o.purpose,
                status=o.status, data_origin=o.data_origin, http_status=o.http_status, attempts=o.attempts,
                duration_ms=o.duration_ms, result_count=o.result_count, error=o.error, serpapi_search_id=o.search_id,
                response=o.data if o.status in {"ok", "empty"} else None, requested_at=o.retrieved_at,
            ))

    def _persist_results(self, analysis_id: str, state: dict[str, Any], rt: AnalysisRuntime) -> None:
        report = state.get("report") or {}
        final_keys = {(s["key"], s["revision"]) for s in state.get("strategies", [])}
        with self.db.write() as s:
            run = s.get(models.AnalysisRun, analysis_id)
            run.plan = state.get("plan")
            run.warnings = state.get("warnings", [])
            run.results = {
                "price_groups": state.get("price_groups", {}), "trends": state.get("trends", {}),
                "news": state.get("news", {}), "usage": rt.gateway.usage(), "node_trace": state.get("node_trace", []),
                "branch": state.get("branch"), "failed_agents": state.get("failed_agents", []),
            }
            for obs in rt.evidence.items.values():
                s.add(models.EvidenceSource(
                    analysis_id=analysis_id, ref=obs.ref, kind=obs.kind, engine=obs.engine, query=obs.query,
                    country=obs.country, title=obs.title, source_url=obs.source_url, source_id=obs.source_id,
                    classification=obs.classification, freshness=obs.freshness, data_origin=obs.data_origin,
                    published_at=obs.published_at, retrieved_at=obs.retrieved_at,
                    normalized=obs.model_dump(mode="json")["normalized"], original=obs.model_dump(mode="json")["original"],
                ))
            for c in state.get("competitors", []):
                s.add(models.Competitor(analysis_id=analysis_id, key=c["key"], name=c["name"], relation=c["relation"], data=c))
            for l in state.get("listings", []):
                s.add(models.ProductListing(
                    analysis_id=analysis_id, evidence_ref=l["evidence_ref"], competitor_key=l.get("merchant_key"),
                    focus=l["focus"], country=l["country"], title=l["title"], merchant=l.get("merchant"),
                    price=l.get("price"), currency=l.get("currency"), unit_price=l.get("unit_price"),
                    unit_price_basis=l.get("unit_price_basis"), data=l,
                ))
            for country, t in (state.get("trends") or {}).items():
                for p in t.get("points", []):
                    for q in t.get("queries", []):
                        ref = next((r for r in t.get("evidence_refs", []) if rt.evidence.items.get(r)
                                    and rt.evidence.items[r].kind == "trend_series"
                                    and rt.evidence.items[r].normalized.get("query") == q), "")
                        s.add(models.TrendObservation(analysis_id=analysis_id, evidence_ref=ref, query=q,
                                                      geo=t.get("geo") or country, date_range=t.get("date_range") or "",
                                                      point_label=p.get("date", ""), timestamp=p.get("timestamp"),
                                                      value=p.get(q), partial=bool(p.get("partial"))))
            for st in state.get("strategy_history", []):
                s.add(models.BusinessStrategy(analysis_id=analysis_id, strategy_key=st["key"], archetype=st["archetype"],
                                              revision=st["revision"], is_final=(st["key"], st["revision"]) in final_keys,
                                              data=st))
            for sim in state.get("simulation_history", []):
                s.add(models.SimulationScenario(analysis_id=analysis_id, strategy_key=sim["strategy_key"],
                                                revision=sim["revision"], data=sim))
            for rnd in state.get("critic_rounds", []):
                for ev in rnd["evaluations"]:
                    s.add(models.CriticEvaluation(analysis_id=analysis_id, round=rnd["round"], strategy_key=ev["strategy_key"],
                                                  passed=ev["passed"], data={**ev, "decision": rnd["decision"]}))
            if report:
                s.add(models.AnalysisReport(analysis_id=analysis_id, inputs_hash=report.get("inputs_hash", ""),
                                            content_hash=content_hash(report), content=report))

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)
