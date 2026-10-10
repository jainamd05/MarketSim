"""Per-analysis runtime context shared by graph nodes (not part of the serialisable state)."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from app.config import Settings
from app.llm.adapter import LLMClient
from app.schemas.analysis import SearchOutcome
from app.serpapi.gateway import SerpApiGateway
from app.serpapi.normalize import EvidenceRegistry

log = logging.getLogger("marketsim.agents")

AGENT_LABELS = {
    "supervisor": "Supervisor & Planning Agent",
    "competitor_discovery": "Competitor Discovery Agent",
    "pricing_intelligence": "Pricing Intelligence Agent",
    "demand_trends": "Demand & Trend Intelligence Agent",
    "market_news": "Market News & Risk Agent",
    "strategy_generation": "Strategy Generation Agent",
    "quantitative_simulation": "Quantitative Simulation Agent",
    "strategy_critic": "Strategy Critic & Validation Agent",
    "strategy_revision": "Strategy Generation Agent (targeted revision)",
    "report_composer": "Report Composer",
}


def _query_of(params: dict[str, Any]) -> str | None:
    for key in ("q", "k", "product_id"):
        if params.get(key):
            return str(params[key])[:120]
    if params.get("page_token"):
        return "page_token:" + str(params["page_token"])[:16] + "…"
    return None


class EventEmitter:
    """Records execution events in order. ``sink`` persists each event immediately."""

    def __init__(self, analysis_id: str, sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.analysis_id = analysis_id
        self._sink = sink
        self._lock = threading.Lock()
        self._seq = 0
        self.events: list[dict[str, Any]] = []

    def emit(self, agent: str, event_type: str, message: str, **meta: Any) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            event = {"seq": self._seq, "ts": datetime.now(timezone.utc).isoformat(), "agent": agent,
                     "agent_label": AGENT_LABELS.get(agent, agent), "event_type": event_type,
                     "message": message, "meta": {k: v for k, v in meta.items() if v is not None}}
            self.events.append(event)
            if self._sink:
                try:
                    self._sink(event)
                except Exception:  # never break the graph because of telemetry
                    log.exception("event sink failed")
        return event

    def tool_event(self, event_type: str, outcome: SearchOutcome) -> None:
        query = _query_of(outcome.params)
        if event_type == "tool_requested":
            msg = f"{outcome.engine} requested" + (f" for “{query}”" if query else "")
        elif event_type == "tool_completed":
            origin = {"demo_fixture": " (demo fixture)", "cache": " (cache hit)"}.get(outcome.data_origin, "")
            msg = f"{outcome.engine} returned {outcome.result_count} result(s){origin}"
            if outcome.status == "deduplicated":
                msg = f"{outcome.engine}: identical search de-duplicated (no extra request)"
            elif outcome.status == "empty":
                msg = f"{outcome.engine} returned no results{origin}"
        elif event_type == "tool_skipped":
            msg = f"{outcome.engine} skipped: {outcome.error}"
        else:
            msg = f"{outcome.engine} failed: {outcome.error or outcome.status}"
        self.emit(outcome.agent or "unknown", event_type, msg, engine=outcome.engine, query=query,
                  status=outcome.status, result_count=outcome.result_count if event_type != "tool_requested" else None,
                  duration_ms=outcome.duration_ms if event_type != "tool_requested" else None,
                  data_origin=outcome.data_origin, attempts=outcome.attempts or None, http_status=outcome.http_status)


@dataclass
class AnalysisRuntime:
    analysis_id: str
    mode: str  # live | demo
    settings: Settings
    gateway: SerpApiGateway
    emitter: EventEmitter
    evidence: EvidenceRegistry = field(default_factory=EvidenceRegistry)
    llm: LLMClient | None = None
    on_agent_change: Callable[[str], None] | None = None

    @property
    def llm_mode(self) -> str:
        return f"llm:{self.llm.label}" if self.llm else "deterministic"
