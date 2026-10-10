"""SQLAlchemy ORM entities. Every finding is linked to its AnalysisRun.

No API secrets are ever stored: SearchRequest.params is sanitised by the gateway
before persistence and the cache key is computed without the api_key.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BusinessProfileRecord(Base):
    __tablename__ = "business_profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    business_type: Mapped[str] = mapped_column(String(16))
    business_stage: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(64))
    pilot_country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(ForeignKey("business_profiles.id"))
    profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    mode: Mapped[str] = mapped_column(String(8))  # live | demo
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|completed|partial|failed
    llm_mode: Mapped[str] = mapped_column(String(32), default="deterministic")
    request_budget: Mapped[int] = mapped_column(Integer, default=12)
    requests_used: Mapped[int] = mapped_column(Integer, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    fixture_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    current_agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Aggregated, non-tabular agent outputs (price groups, trend summaries, news/risks, usage).
    results: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    warnings: Mapped[list[Any]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    events: Mapped[list["AgentEvent"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")


class AgentEvent(Base):
    __tablename__ = "agent_events"
    __table_args__ = (UniqueConstraint("analysis_id", "seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    agent: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(48))
    message: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    analysis: Mapped[AnalysisRun] = relationship(back_populates="events")


class SearchRequest(Base):
    __tablename__ = "search_requests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    agent: Mapped[str] = mapped_column(String(64))
    engine: Mapped[str] = mapped_column(String(48))
    params: Mapped[dict[str, Any]] = mapped_column(JSON)  # sanitised, never contains api_key
    purpose: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24))
    data_origin: Mapped[str] = mapped_column(String(16))  # live | cache | demo_fixture | none
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    serpapi_search_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvidenceSource(Base):
    __tablename__ = "evidence_sources"
    __table_args__ = (UniqueConstraint("analysis_id", "ref"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    ref: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(32))
    engine: Mapped[str] = mapped_column(String(48))
    query: Mapped[str] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    title: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    classification: Mapped[str] = mapped_column(String(48))
    freshness: Mapped[str] = mapped_column(String(24))
    data_origin: Mapped[str] = mapped_column(String(16))
    published_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    normalized: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    original: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Competitor(Base):
    __tablename__ = "competitors"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    key: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(256))
    relation: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class ProductListing(Base):
    __tablename__ = "product_listings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    evidence_ref: Mapped[str] = mapped_column(String(32))
    competitor_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    focus: Mapped[str] = mapped_column(String(64))
    country: Mapped[str] = mapped_column(String(8))
    title: Mapped[str] = mapped_column(Text)
    merchant: Mapped[str | None] = mapped_column(String(256), nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_price_basis: Mapped[str | None] = mapped_column(String(24), nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class TrendObservation(Base):
    __tablename__ = "trend_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    evidence_ref: Mapped[str] = mapped_column(String(32))
    query: Mapped[str] = mapped_column(String(256))
    geo: Mapped[str] = mapped_column(String(16))
    date_range: Mapped[str] = mapped_column(String(32))
    point_label: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    partial: Mapped[bool] = mapped_column(Boolean, default=False)


class BusinessStrategy(Base):
    __tablename__ = "business_strategies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    strategy_key: Mapped[str] = mapped_column(String(64))
    archetype: Mapped[str] = mapped_column(String(48))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class SimulationScenario(Base):
    __tablename__ = "simulation_scenarios"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    strategy_key: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class CriticEvaluation(Base):
    __tablename__ = "critic_evaluations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    round: Mapped[int] = mapped_column(Integer)
    strategy_key: Mapped[str] = mapped_column(String(64))
    passed: Mapped[bool] = mapped_column(Boolean)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), unique=True)
    inputs_hash: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SerpApiCacheEntry(Base):
    __tablename__ = "serpapi_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    engine: Mapped[str] = mapped_column(String(48))
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    response: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
