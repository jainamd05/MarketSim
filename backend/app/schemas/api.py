"""Request/response schemas for the HTTP API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analysis import SimInputs, StrategySimulation
from app.schemas.profile import BusinessProfile


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    time: datetime


class ConfigResponse(BaseModel):
    default_data_mode: Literal["live", "demo"]
    demo_mode_setting: str
    serpapi_configured: bool
    live_available: bool
    llm_provider: str
    llm_enabled: bool
    llm_model: str | None
    max_serpapi_requests_per_analysis: int
    serpapi_cache_ttl_seconds: int
    fixture_version: str
    fixtures_synthetic: bool
    engines: list[str]


class ProfileResponse(BaseModel):
    profile: BusinessProfile


class AnalysisCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=8, max_length=32, pattern=r"^[a-f0-9]+$")
    mode: Literal["live", "demo"] | None = None
    request_budget: int | None = Field(default=None, ge=1, le=30)


class AnalysisCreated(BaseModel):
    analysis_id: str
    mode: Literal["live", "demo"]
    status: str


class AnalysisStatus(BaseModel):
    id: str
    profile_id: str
    mode: str
    status: str
    llm_mode: str
    current_agent: str | None
    request_budget: int
    requests_used: int
    cache_hits: int
    fixture_version: str | None
    progress: dict[str, Any]
    warnings: list[Any]
    error: str | None
    profile: dict[str, Any]
    plan: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class AnalysisListItem(BaseModel):
    id: str
    mode: str
    status: str
    created_at: datetime
    category: str
    business_type: str


class EventOut(BaseModel):
    seq: int
    ts: datetime
    agent: str
    agent_label: str
    event_type: str
    message: str
    meta: dict[str, Any]


class EventsResponse(BaseModel):
    analysis_id: str
    status: str
    events: list[EventOut]
    last_seq: int


class SimulateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_key: str = Field(pattern=r"^S\d{1,2}$")
    inputs: SimInputs
    inventory_budget: float | None = Field(default=None, ge=0)


class SimulateResponse(BaseModel):
    analysis_id: str
    simulation: StrategySimulation
    serpapi_requests_made: int = 0
    note: str = "Recomputed with deterministic Python functions; no SerpApi requests were made."
