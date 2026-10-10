"""Typed FastAPI routes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select

from app import models
from app.agents.runtime import AGENT_LABELS
from app.llm.adapter import DEFAULT_MODELS
from app.onboarding import registry
from app.schemas.analysis import Strategy
from app.schemas.api import (
    AnalysisCreate, AnalysisCreated, AnalysisListItem, AnalysisStatus, ConfigResponse, EventOut, EventsResponse,
    HealthResponse, ProfileResponse, SimulateRequest, SimulateResponse,
)
from app.schemas.profile import BusinessProfile, ProfileCreate, demo_profile
from app.serpapi.gateway import ENGINE_ALLOWLIST, FixtureStore
from app.services.analysis_service import AnalysisModeError
from app.simulation.engine import run_simulation

VERSION = "0.1.0"
router = APIRouter(prefix="/api")
PIPELINE_AGENTS = ["supervisor", "competitor_discovery", "pricing_intelligence", "demand_trends", "market_news",
                   "strategy_generation", "quantitative_simulation", "strategy_critic", "report_composer"]


def _db(request: Request):
    return request.app.state.db


def _settings(request: Request):
    return request.app.state.settings


def _profile_out(rec: models.BusinessProfileRecord) -> BusinessProfile:
    return BusinessProfile(**rec.data, id=rec.id, status=rec.status, created_at=rec.created_at, updated_at=rec.updated_at)


def _run_or_404(session, analysis_id: str) -> models.AnalysisRun:
    run = session.get(models.AnalysisRun, analysis_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "analysis_not_found",
                                                               "message": f"Analysis '{analysis_id}' not found."})
    return run


def _require_finished(run: models.AnalysisRun) -> None:
    if run.status in {"queued", "running"}:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"code": "analysis_in_progress",
                                                              "message": "Analysis is still running; results are not ready yet."})


# ---------------------------------------------------------------- system
@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=VERSION, time=datetime.now(timezone.utc))


@router.get("/config", response_model=ConfigResponse)
def config(request: Request) -> ConfigResponse:
    s = _settings(request)
    return ConfigResponse(
        default_data_mode=s.default_data_mode, demo_mode_setting=s.demo_mode, serpapi_configured=s.has_serpapi_key,
        live_available=s.has_serpapi_key and s.demo_mode != "true", llm_provider=s.llm_provider, llm_enabled=s.llm_enabled,
        llm_model=(s.llm_model or DEFAULT_MODELS.get(s.llm_provider)) if s.llm_enabled else None,
        max_serpapi_requests_per_analysis=s.max_serpapi_requests_per_analysis,
        serpapi_cache_ttl_seconds=s.serpapi_cache_ttl_seconds, fixture_version=s.fixture_version,
        fixtures_synthetic=FixtureStore(s.fixture_version).synthetic, engines=sorted(ENGINE_ALLOWLIST),
    )


# ------------------------------------------------------------- onboarding
@router.get("/onboarding/questions")
def onboarding_questions() -> dict[str, Any]:
    return registry.load_registry()


@router.get("/onboarding/demo-profile")
def onboarding_demo_profile() -> dict[str, Any]:
    return demo_profile().model_dump(mode="json")


# ---------------------------------------------------------------- profiles
@router.post("/profiles", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(body: ProfileCreate, request: Request) -> ProfileResponse:
    p = body.profile
    with _db(request).write() as s:
        rec = models.BusinessProfileRecord(business_type=p.business_type, business_stage=p.business_stage,
                                           category=p.category, pilot_country=p.pilot_country, status=body.status,
                                           data=p.model_dump(mode="json"))
        s.add(rec)
        s.flush()
        return ProfileResponse(profile=_profile_out(rec))


@router.get("/profiles/{profile_id}", response_model=ProfileResponse)
def get_profile(profile_id: str, request: Request) -> ProfileResponse:
    with _db(request).session() as s:
        rec = s.get(models.BusinessProfileRecord, profile_id)
        if rec is None:
            raise HTTPException(404, detail={"code": "profile_not_found", "message": f"Profile '{profile_id}' not found."})
        return ProfileResponse(profile=_profile_out(rec))


@router.put("/profiles/{profile_id}", response_model=ProfileResponse)
def update_profile(profile_id: str, body: ProfileCreate, request: Request) -> ProfileResponse:
    p = body.profile
    with _db(request).write() as s:
        rec = s.get(models.BusinessProfileRecord, profile_id)
        if rec is None:
            raise HTTPException(404, detail={"code": "profile_not_found", "message": f"Profile '{profile_id}' not found."})
        rec.business_type, rec.business_stage, rec.category = p.business_type, p.business_stage, p.category
        rec.pilot_country, rec.status, rec.data = p.pilot_country, body.status, p.model_dump(mode="json")
        rec.updated_at = datetime.now(timezone.utc)
        s.flush()
        return ProfileResponse(profile=_profile_out(rec))


# ---------------------------------------------------------------- analyses
@router.post("/analyses", response_model=AnalysisCreated, status_code=status.HTTP_202_ACCEPTED)
def create_analysis(body: AnalysisCreate, request: Request) -> AnalysisCreated:
    service = request.app.state.service
    try:
        analysis_id = service.create(body.profile_id, body.mode, body.request_budget)
    except KeyError:
        raise HTTPException(404, detail={"code": "profile_not_found", "message": f"Profile '{body.profile_id}' not found."})
    except AnalysisModeError as exc:
        raise HTTPException(400, detail={"code": "mode_unavailable", "message": str(exc)})
    with _db(request).session() as s:
        run = s.get(models.AnalysisRun, analysis_id)
        return AnalysisCreated(analysis_id=analysis_id, mode=run.mode, status=run.status)


@router.get("/analyses", response_model=list[AnalysisListItem])
def list_analyses(request: Request, limit: int = Query(20, ge=1, le=100)) -> list[AnalysisListItem]:
    with _db(request).session() as s:
        runs = s.scalars(select(models.AnalysisRun).order_by(models.AnalysisRun.created_at.desc()).limit(limit)).all()
        return [AnalysisListItem(id=r.id, mode=r.mode, status=r.status, created_at=r.created_at,
                                 category=r.profile_snapshot.get("category", ""),
                                 business_type=r.profile_snapshot.get("business_type", "")) for r in runs]


@router.get("/analyses/{analysis_id}", response_model=AnalysisStatus)
def get_analysis(analysis_id: str, request: Request) -> AnalysisStatus:
    with _db(request).session() as s:
        run = _run_or_404(s, analysis_id)
        done = s.scalars(select(models.AgentEvent.agent).where(
            models.AgentEvent.analysis_id == analysis_id, models.AgentEvent.event_type.in_(["agent_completed", "agent_failed"]))).all()
        completed = [a for a in PIPELINE_AGENTS if a in set(done)]
        return AnalysisStatus(
            id=run.id, profile_id=run.profile_id, mode=run.mode, status=run.status, llm_mode=run.llm_mode,
            current_agent=run.current_agent, request_budget=run.request_budget, requests_used=run.requests_used,
            cache_hits=run.cache_hits, fixture_version=run.fixture_version,
            progress={"completed_agents": completed, "total_agents": len(PIPELINE_AGENTS),
                      "percent": round(100 * len(completed) / len(PIPELINE_AGENTS)),
                      "agents": [{"id": a, "label": AGENT_LABELS[a]} for a in PIPELINE_AGENTS]},
            warnings=run.warnings or [], error=run.error, profile=run.profile_snapshot, plan=run.plan,
            created_at=run.created_at, started_at=run.started_at, completed_at=run.completed_at,
        )


@router.get("/analyses/{analysis_id}/events", response_model=EventsResponse)
def get_events(analysis_id: str, request: Request, after: int = Query(0, ge=0)) -> EventsResponse:
    with _db(request).session() as s:
        run = _run_or_404(s, analysis_id)
        rows = s.scalars(select(models.AgentEvent).where(models.AgentEvent.analysis_id == analysis_id,
                                                         models.AgentEvent.seq > after)
                         .order_by(models.AgentEvent.seq)).all()
        events = [EventOut(seq=e.seq, ts=e.ts, agent=e.agent, agent_label=e.meta.get("agent_label", e.agent),
                           event_type=e.event_type, message=e.message,
                           meta={k: v for k, v in e.meta.items() if k != "agent_label"}) for e in rows]
        return EventsResponse(analysis_id=analysis_id, status=run.status, events=events,
                              last_seq=events[-1].seq if events else after)


@router.get("/analyses/{analysis_id}/competitors")
def get_competitors(analysis_id: str, request: Request) -> dict[str, Any]:
    with _db(request).session() as s:
        run = _run_or_404(s, analysis_id)
        _require_finished(run)
        comps = s.scalars(select(models.Competitor).where(models.Competitor.analysis_id == analysis_id)).all()
        listings = s.scalars(select(models.ProductListing).where(models.ProductListing.analysis_id == analysis_id)).all()
        groups = (run.results or {}).get("price_groups", {})
        product_details = [{"ref": e.ref, "title": e.title, "url": e.source_url, **e.normalized} for e in s.scalars(
            select(models.EvidenceSource).where(models.EvidenceSource.analysis_id == analysis_id,
                                                models.EvidenceSource.kind == "product_detail")).all()]
        countries = sorted({l.country for l in listings} | {c for x in comps for c in x.data.get("countries", [])})
        return {"analysis_id": analysis_id, "mode": run.mode, "countries": countries,
                "competitors": [c.data for c in comps], "listings": [l.data for l in listings],
                "price_groups": list(groups.values()), "product_details": product_details,
                "note": "Sampled search listings only – not market share, sales or a complete census."}


@router.get("/analyses/{analysis_id}/trends")
def get_trends(analysis_id: str, request: Request) -> dict[str, Any]:
    with _db(request).session() as s:
        run = _run_or_404(s, analysis_id)
        _require_finished(run)
        trends = (run.results or {}).get("trends", {})
        stored_points = s.scalars(select(models.TrendObservation).where(
            models.TrendObservation.analysis_id == analysis_id)).all()
        return {"analysis_id": analysis_id, "mode": run.mode, "by_country": trends,
                "countries": list(trends.keys()), "stored_points": len(stored_points)}


@router.get("/analyses/{analysis_id}/strategies")
def get_strategies(analysis_id: str, request: Request) -> dict[str, Any]:
    with _db(request).session() as s:
        run = _run_or_404(s, analysis_id)
        _require_finished(run)
        rows = s.scalars(select(models.BusinessStrategy).where(models.BusinessStrategy.analysis_id == analysis_id)
                         .order_by(models.BusinessStrategy.strategy_key, models.BusinessStrategy.revision)).all()
        sims = s.scalars(select(models.SimulationScenario).where(models.SimulationScenario.analysis_id == analysis_id)).all()
        critic = s.scalars(select(models.CriticEvaluation).where(models.CriticEvaluation.analysis_id == analysis_id)
                           .order_by(models.CriticEvaluation.round, models.CriticEvaluation.strategy_key)).all()
        final = [r.data for r in rows if r.is_final]
        sim_by = {(x.strategy_key, x.revision): x.data for x in sims}
        rounds: dict[int, dict[str, Any]] = {}
        for c in critic:
            rounds.setdefault(c.round, {"round": c.round, "decision": c.data.get("decision"), "evaluations": []})
            rounds[c.round]["evaluations"].append(c.data)
        return {
            "analysis_id": analysis_id, "mode": run.mode,
            "strategies": final,
            "simulations": {f["key"]: sim_by.get((f["key"], f["revision"])) for f in final},
            "history": [r.data for r in rows],
            "simulation_history": [x.data for x in sims],
            "critic_rounds": [rounds[k] for k in sorted(rounds)],
        }


@router.post("/analyses/{analysis_id}/simulate", response_model=SimulateResponse)
def simulate(analysis_id: str, body: SimulateRequest, request: Request) -> SimulateResponse:
    settings = _settings(request)
    with _db(request).session() as s:
        run = _run_or_404(s, analysis_id)
        _require_finished(run)
        row = s.scalars(select(models.BusinessStrategy).where(
            models.BusinessStrategy.analysis_id == analysis_id, models.BusinessStrategy.strategy_key == body.strategy_key,
            models.BusinessStrategy.is_final.is_(True))).first()
        if row is None:
            raise HTTPException(404, detail={"code": "strategy_not_found", "message": f"Strategy {body.strategy_key} not found."})
        strategy = Strategy.model_validate(row.data)
    if body.inputs.model != strategy.sim_inputs.model:
        raise HTTPException(422, detail={"code": "model_mismatch",
                                         "message": f"Strategy uses the {strategy.sim_inputs.model} model."})
    if body.inputs.currency != strategy.sim_inputs.currency:
        raise HTTPException(422, detail={"code": "currency_mismatch",
                                         "message": "Inputs must stay in the strategy currency; no FX conversion is applied."})
    sim = run_simulation(strategy.key, strategy.revision, body.inputs, strategy.product_mix,
                         iterations=settings.monte_carlo_iterations, seed=settings.monte_carlo_seed,
                         inventory_budget=body.inventory_budget)
    return SimulateResponse(analysis_id=analysis_id, simulation=sim)


@router.get("/analyses/{analysis_id}/report")
def get_report(analysis_id: str, request: Request) -> dict[str, Any]:
    with _db(request).session() as s:
        run = _run_or_404(s, analysis_id)
        _require_finished(run)
        rep = s.scalars(select(models.AnalysisReport).where(models.AnalysisReport.analysis_id == analysis_id)).first()
        if rep is None:
            raise HTTPException(404, detail={"code": "report_not_found",
                                             "message": "No report was produced (the analysis may have failed)."})
        return {"analysis_id": analysis_id, "inputs_hash": rep.inputs_hash, "content_hash": rep.content_hash,
                "report": rep.content}


@router.get("/analyses/{analysis_id}/evidence")
def get_evidence(analysis_id: str, request: Request) -> dict[str, Any]:
    with _db(request).session() as s:
        run = _run_or_404(s, analysis_id)
        evidence = s.scalars(select(models.EvidenceSource).where(models.EvidenceSource.analysis_id == analysis_id)
                             .order_by(models.EvidenceSource.ref)).all()
        searches = s.scalars(select(models.SearchRequest).where(models.SearchRequest.analysis_id == analysis_id)
                             .order_by(models.SearchRequest.requested_at)).all()
        return {
            "analysis_id": analysis_id, "mode": run.mode,
            "evidence": [{"ref": e.ref, "kind": e.kind, "engine": e.engine, "query": e.query, "country": e.country,
                          "title": e.title, "source_url": e.source_url, "classification": e.classification,
                          "freshness": e.freshness, "data_origin": e.data_origin, "published_at": e.published_at,
                          "retrieved_at": e.retrieved_at, "normalized": e.normalized} for e in evidence],
            "searches": [{"engine": r.engine, "params": r.params, "agent": r.agent, "purpose": r.purpose,
                          "status": r.status, "data_origin": r.data_origin, "result_count": r.result_count,
                          "duration_ms": r.duration_ms, "attempts": r.attempts, "error": r.error,
                          "requested_at": r.requested_at} for r in searches],
        }
