"""Centralised SerpApi gateway.

Every SerpApi request in MarketSim goes through :class:`SerpApiGateway`:

* engine allowlist + per-engine parameter allowlist and value validation
* per-analysis request budget (default 12) – no uncontrolled loops
* in-run de-duplication of identical searches
* persistent SQLite cache with TTL (LIVE mode)
* exponential backoff for transient failures (429 / 5xx / timeouts / network)
* bounded concurrency (semaphore)
* honest outcomes: failures are reported, never replaced by fixtures silently
* DEMO mode reads versioned fixtures from disk and labels them ``demo_fixture``
* the API key is never logged, persisted, cached or returned
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import httpx

from app.config import FIXTURES_DIR, Settings
from app.schemas.analysis import SearchOutcome

# httpx logs full request URLs (which contain api_key) at INFO level. Never allow that.
for _name in ("httpx", "httpcore", "httpx2", "httpcore2"):
    logging.getLogger(_name).setLevel(logging.WARNING)
log = logging.getLogger("marketsim.serpapi")

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"


@dataclass(frozen=True)
class EngineSpec:
    required: frozenset[str]
    allowed: frozenset[str]
    result_counter: Callable[[dict[str, Any]], int]


def _len(key: str) -> Callable[[dict[str, Any]], int]:
    def counter(data: dict[str, Any]) -> int:
        value = data.get(key)
        return len(value) if isinstance(value, list) else 0
    return counter


def _count_trends(data: dict[str, Any]) -> int:
    iot = data.get("interest_over_time")
    if isinstance(iot, dict) and isinstance(iot.get("timeline_data"), list):
        return len(iot["timeline_data"])
    rq = data.get("related_queries")
    if isinstance(rq, dict):
        return sum(len(v) for v in rq.values() if isinstance(v, list))
    ibr = data.get("interest_by_region")
    return len(ibr) if isinstance(ibr, list) else 0


def _count_product(data: dict[str, Any]) -> int:
    return 1 if isinstance(data.get("product_results"), dict) else 0


def _count_maps(data: dict[str, Any]) -> int:
    if isinstance(data.get("local_results"), list):
        return len(data["local_results"])
    return 1 if isinstance(data.get("place_results"), dict) else 0


ENGINE_SPECS: dict[str, EngineSpec] = {
    "google_shopping": EngineSpec(
        frozenset({"q"}), frozenset({"q", "gl", "hl", "location", "google_domain", "num", "start", "tbs"}),
        _len("shopping_results"),
    ),
    "google_product": EngineSpec(
        frozenset({"product_id"}),
        frozenset({"product_id", "gl", "hl", "offer_view", "google_domain", "reviews", "specs", "location"}),
        _count_product,
    ),
    "google_immersive_product": EngineSpec(frozenset({"page_token"}), frozenset({"page_token", "more_stores"}), _count_product),
    "google_trends": EngineSpec(
        frozenset({"q", "data_type"}), frozenset({"q", "geo", "date", "data_type", "cat", "gprop", "tz", "region", "hl"}),
        _count_trends,
    ),
    "google": EngineSpec(
        frozenset({"q"}), frozenset({"q", "gl", "hl", "location", "google_domain", "num", "start"}), _len("organic_results"),
    ),
    "google_news": EngineSpec(frozenset({"q"}), frozenset({"q", "gl", "hl", "so"}), _len("news_results")),
    "google_maps": EngineSpec(
        frozenset({"q", "type"}), frozenset({"q", "type", "ll", "hl", "gl", "google_domain", "start"}), _count_maps,
    ),
    "google_autocomplete": EngineSpec(frozenset({"q"}), frozenset({"q", "gl", "hl"}), _len("suggestions")),
    "amazon": EngineSpec(frozenset({"k"}), frozenset({"k", "amazon_domain", "language", "page"}), _len("organic_results")),
}
ENGINE_ALLOWLIST = frozenset(ENGINE_SPECS)

_SAFE_VALUE = re.compile(r"^[^\r\n\x00]{1,256}$")
_API_KEY_RE = re.compile(r"(api_key=)[^&\s'\"]+", re.IGNORECASE)


class ParamValidationError(ValueError):
    pass


def canonical_params(engine: str, params: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in params.items():
        if value is None or key in {"api_key", "engine", "output"}:
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        out[key] = str(value).strip()
    return dict(sorted(out.items()))


def cache_key(engine: str, params: dict[str, Any]) -> str:
    payload = json.dumps({"engine": engine, **canonical_params(engine, params)}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_request(engine: str, params: dict[str, Any]) -> dict[str, str]:
    if engine not in ENGINE_ALLOWLIST:
        raise ParamValidationError(f"Engine '{engine}' is not in the backend allowlist.")
    spec = ENGINE_SPECS[engine]
    canon = canonical_params(engine, params)
    unknown = set(canon) - spec.allowed
    if unknown:
        raise ParamValidationError(f"Parameters not allowed for {engine}: {sorted(unknown)}")
    missing = spec.required - set(canon)
    if missing:
        raise ParamValidationError(f"Missing required parameters for {engine}: {sorted(missing)}")
    for key, value in canon.items():
        if not _SAFE_VALUE.match(value):
            raise ParamValidationError(f"Invalid value for '{key}' (empty, too long or contains control characters).")
    return canon


def scrub(text: str, secret: str | None = None) -> str:
    text = _API_KEY_RE.sub(r"\1***", text)
    if secret:
        text = text.replace(secret, "***")
    return text


class FixtureStore:
    """Versioned demo fixtures: fixtures/serpapi/<version>/manifest.json + one JSON file per request."""

    def __init__(self, version: str = "v1", root: Path = FIXTURES_DIR) -> None:
        self.version = version
        self.dir = root / version
        manifest_path = self.dir / "manifest.json"
        self.manifest: dict[str, Any] = {"entries": []}
        if manifest_path.exists():
            self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self._index = {cache_key(e["engine"], e["params"]): e for e in self.manifest.get("entries", [])}

    @property
    def synthetic(self) -> bool:
        return bool(self.manifest.get("synthetic", True))

    def lookup(self, engine: str, params: dict[str, Any]) -> dict[str, Any] | None:
        entry = self._index.get(cache_key(engine, params))
        if not entry:
            return None
        return json.loads((self.dir / entry["file"]).read_text(encoding="utf-8"))


EventCallback = Callable[[str, SearchOutcome], None]
PersistCallback = Callable[[SearchOutcome], None]


@dataclass
class _Pending:
    event: threading.Event = field(default_factory=threading.Event)
    outcome: SearchOutcome | None = None


class SerpApiGateway:
    def __init__(
        self,
        *,
        mode: Literal["live", "demo"],
        settings: Settings,
        budget: int | None = None,
        cache: "ResponseCache | None" = None,
        fixtures: FixtureStore | None = None,
        transport: httpx.BaseTransport | None = None,
        on_event: EventCallback | None = None,
        persist: PersistCallback | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.mode = mode
        self.settings = settings
        self.budget = budget if budget is not None else settings.max_serpapi_requests_per_analysis
        self.cache = cache
        self.fixtures = fixtures if fixtures is not None else (FixtureStore(settings.fixture_version) if mode == "demo" else None)
        self._transport = transport
        self._on_event = on_event
        self._persist = persist
        self._sleep = sleep
        self._lock = threading.Lock()
        self._semaphore = threading.BoundedSemaphore(settings.serpapi_max_concurrency)
        self._memo: dict[str, _Pending] = {}
        self.requests_used = 0  # budget units consumed (network calls or fixture loads)
        self.cache_hits = 0
        self.deduplicated = 0
        self.history: list[SearchOutcome] = []

    # ------------------------------------------------------------------ public
    @property
    def remaining(self) -> int:
        return max(0, self.budget - self.requests_used)

    def usage(self) -> dict[str, Any]:
        statuses: dict[str, int] = {}
        for h in self.history:
            statuses[h.status] = statuses.get(h.status, 0) + 1
        return {
            "mode": self.mode,
            "budget": self.budget,
            "used": self.requests_used,
            "remaining": self.remaining,
            "cache_hits": self.cache_hits,
            "deduplicated": self.deduplicated,
            "by_status": statuses,
            "billable_note": (
                "Fixture loads are counted against the budget to mirror LIVE behaviour; no SerpApi credits are used."
                if self.mode == "demo"
                else "Cache hits and de-duplicated searches do not consume budget."
            ),
        }

    def search(self, engine: str, params: dict[str, Any], *, agent: str, purpose: str) -> SearchOutcome:
        started = time.perf_counter()
        try:
            canon = validate_request(engine, params)
        except ParamValidationError as exc:
            outcome = self._outcome(engine, canonical_params(engine, params), agent, purpose, "blocked", error=str(exc))
            return self._finish(outcome, started, emit_request=False)

        key = cache_key(engine, canon)
        with self._lock:
            pending = self._memo.get(key)
            if pending is None:
                pending = _Pending()
                self._memo[key] = pending
                owner = True
            else:
                owner = False
        if not owner:
            pending.event.wait()
            assert pending.outcome is not None
            self.deduplicated += 1
            dup = pending.outcome.model_copy(update={
                "status": "deduplicated" if pending.outcome.usable else pending.outcome.status,
                "agent": agent, "purpose": purpose, "duration_ms": 0.0,
            })
            self._emit("tool_completed" if dup.usable else "tool_failed", dup)
            with self._lock:
                self.history.append(dup)
            return dup

        try:
            outcome = self._execute(engine, canon, key, agent, purpose, started)
        except Exception as exc:  # defensive: never let one search crash the graph
            outcome = self._outcome(engine, canon, agent, purpose, "failed",
                                    error=scrub(f"{type(exc).__name__}: {exc}", self.settings.serpapi_api_key))
            outcome = self._finish(outcome, started)
        pending.outcome = outcome
        pending.event.set()
        return outcome

    # --------------------------------------------------------------- internals
    def _execute(self, engine: str, canon: dict[str, str], key: str, agent: str, purpose: str, started: float) -> SearchOutcome:
        # 1) persistent cache (LIVE only)
        if self.mode == "live" and self.cache is not None:
            cached = self.cache.get(key, self.settings.serpapi_cache_ttl_seconds)
            if cached is not None:
                data, created_at = cached
                self._emit("tool_requested", self._outcome(engine, canon, agent, purpose, "ok", origin="cache"))
                with self._lock:
                    self.cache_hits += 1
                outcome = self._outcome(engine, canon, agent, purpose, "ok", origin="cache", data=data,
                                        retrieved_at=created_at)
                return self._finish(outcome, started, emit_request=False)

        # 2) budget (decide under the lock, finish outside it – _finish takes the lock too)
        with self._lock:
            exhausted = self.requests_used >= self.budget
            if not exhausted:
                self.requests_used += 1
        if exhausted:
            outcome = self._outcome(engine, canon, agent, purpose, "skipped_budget",
                                    error=f"Request budget of {self.budget} exhausted.")
            return self._finish(outcome, started, emit_request=False)

        self._emit("tool_requested", self._outcome(engine, canon, agent, purpose, "ok",
                                                   origin="demo_fixture" if self.mode == "demo" else "live"))
        if self.mode == "demo":
            return self._finish(self._from_fixture(engine, canon, agent, purpose), started, emit_request=False)
        with self._semaphore:
            outcome = self._from_network(engine, canon, agent, purpose)
        if outcome.status in {"ok", "empty"} and outcome.data is not None and self.cache is not None:
            self.cache.put(key, engine, canon, outcome.data)
        return self._finish(outcome, started, emit_request=False)

    def _from_fixture(self, engine: str, canon: dict[str, str], agent: str, purpose: str) -> SearchOutcome:
        data = self.fixtures.lookup(engine, canon) if self.fixtures else None
        if data is None:
            return self._outcome(engine, canon, agent, purpose, "fixture_missing", origin="none",
                                 error="No saved demo fixture exists for this exact request.")
        outcome = self._classify_payload(engine, canon, agent, purpose, data, origin="demo_fixture", attempts=1)
        created = data.get("search_metadata", {}).get("created_at") if isinstance(data.get("search_metadata"), dict) else None
        if isinstance(created, str):
            try:  # SerpApi format: "2026-09-28 06:40:12 UTC" – the fixture's authored/recorded time
                outcome.retrieved_at = datetime.strptime(created.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return outcome

    def _from_network(self, engine: str, canon: dict[str, str], agent: str, purpose: str) -> SearchOutcome:
        api_key = self.settings.serpapi_api_key
        if not api_key:
            return self._outcome(engine, canon, agent, purpose, "failed", error="SERPAPI_API_KEY is not configured.")
        attempts = 0
        last_error = "unknown error"
        last_status: int | None = None
        max_attempts = 1 + self.settings.serpapi_max_retries
        with httpx.Client(timeout=self.settings.serpapi_timeout_seconds, transport=self._transport) as client:
            while attempts < max_attempts:
                attempts += 1
                try:
                    resp = client.get(SERPAPI_ENDPOINT, params={"engine": engine, **canon, "api_key": api_key, "output": "json"})
                    last_status = resp.status_code
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                        except ValueError:
                            last_error = "SerpApi returned a non-JSON response."
                            break
                        return self._classify_payload(engine, canon, agent, purpose, data, origin="live",
                                                      attempts=attempts, http_status=200)
                    message = self._error_message(resp)
                    if resp.status_code == 429 or resp.status_code >= 500:
                        last_error = f"HTTP {resp.status_code}: {message}"
                        self._backoff(attempts, max_attempts)
                        continue
                    last_error = f"HTTP {resp.status_code}: {message}"
                    break  # 400/401/403/404 are not transient
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_error = scrub(f"{type(exc).__name__}: {exc}", api_key)
                    self._backoff(attempts, max_attempts)
        return self._outcome(engine, canon, agent, purpose, "failed", error=scrub(last_error, api_key),
                             attempts=attempts, http_status=last_status)

    def _backoff(self, attempt: int, max_attempts: int) -> None:
        if attempt >= max_attempts:
            return
        base = self.settings.serpapi_backoff_base_seconds
        if base > 0:
            self._sleep(base * (2 ** (attempt - 1)) + random.uniform(0, base / 4))

    def _error_message(self, resp: httpx.Response) -> str:
        try:
            body = resp.json()
            if isinstance(body, dict) and isinstance(body.get("error"), str):
                return scrub(body["error"][:300], self.settings.serpapi_api_key)
        except ValueError:
            pass
        return "request failed"

    def _classify_payload(self, engine: str, canon: dict[str, str], agent: str, purpose: str, data: Any, *,
                          origin: str, attempts: int, http_status: int | None = None) -> SearchOutcome:
        if not isinstance(data, dict):
            return self._outcome(engine, canon, agent, purpose, "failed", origin=origin,
                                 error="Unexpected response shape (not a JSON object).", attempts=attempts)
        search_id = None
        meta = data.get("search_metadata")
        if isinstance(meta, dict):
            search_id = meta.get("id") if isinstance(meta.get("id"), str) else None
            if meta.get("status") == "Error" and not data.get("error"):
                data = {**data, "error": "SerpApi reported search status Error."}
        error = data.get("error")
        if isinstance(error, str) and error:
            lowered = error.lower()
            if "hasn't returned any results" in lowered or "no results" in lowered:
                return self._outcome(engine, canon, agent, purpose, "empty", origin=origin, data=data,
                                     error=error[:300], attempts=attempts, http_status=http_status, search_id=search_id)
            return self._outcome(engine, canon, agent, purpose, "failed", origin=origin,
                                 error=scrub(error[:300], self.settings.serpapi_api_key), attempts=attempts,
                                 http_status=http_status, search_id=search_id)
        count = ENGINE_SPECS[engine].result_counter(data)
        return self._outcome(engine, canon, agent, purpose, "ok" if count else "empty", origin=origin, data=data,
                             attempts=attempts, http_status=http_status, result_count=count, search_id=search_id)

    def _outcome(self, engine: str, canon: dict[str, str], agent: str, purpose: str, status: str, *,
                 origin: str = "none", data: dict[str, Any] | None = None, error: str | None = None,
                 attempts: int = 0, http_status: int | None = None, result_count: int = 0,
                 search_id: str | None = None, retrieved_at: datetime | None = None) -> SearchOutcome:
        if data is not None and status in {"ok", "empty"} and not result_count:
            result_count = ENGINE_SPECS[engine].result_counter(data) if engine in ENGINE_SPECS else 0
        return SearchOutcome(
            engine=engine, params=canon, purpose=purpose, agent=agent, status=status, data_origin=origin,
            data=data, error=error, attempts=attempts, http_status=http_status, result_count=result_count,
            retrieved_at=retrieved_at or datetime.now(timezone.utc), search_id=search_id,
        )

    def _finish(self, outcome: SearchOutcome, started: float, emit_request: bool = True) -> SearchOutcome:
        outcome.duration_ms = round((time.perf_counter() - started) * 1000, 1)
        if emit_request:
            self._emit("tool_requested", outcome)
        event = {
            "ok": "tool_completed", "empty": "tool_completed", "deduplicated": "tool_completed",
            "skipped_budget": "tool_skipped", "blocked": "tool_failed",
        }.get(outcome.status, "tool_failed")
        self._emit(event, outcome)
        with self._lock:
            self.history.append(outcome)
        if self._persist:
            try:
                self._persist(outcome)
            except Exception:  # persistence must not break research
                log.exception("Failed to persist search request")
        return outcome

    def _emit(self, event_type: str, outcome: SearchOutcome) -> None:
        if self._on_event:
            self._on_event(event_type, outcome)


class ResponseCache:
    """Persistent SerpApi response cache stored in SQLite (keyed without the api_key)."""

    def __init__(self, db) -> None:  # db: app.db.Database
        self.db = db

    def get(self, key: str, ttl_seconds: int) -> tuple[dict[str, Any], datetime] | None:
        from app.models import SerpApiCacheEntry

        if ttl_seconds <= 0:
            return None
        with self.db.session() as s:
            entry = s.get(SerpApiCacheEntry, key)
            if entry is None:
                return None
            created = entry.created_at if entry.created_at.tzinfo else entry.created_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - created > timedelta(seconds=ttl_seconds):
                return None
            return entry.response, created

    def put(self, key: str, engine: str, params: dict[str, Any], response: dict[str, Any]) -> None:
        from app.models import SerpApiCacheEntry

        with self.db.write() as s:
            entry = s.get(SerpApiCacheEntry, key)
            if entry is None:
                s.add(SerpApiCacheEntry(key=key, engine=engine, params=params, response=response))
            else:
                entry.response = response
                entry.params = params
                entry.created_at = datetime.now(timezone.utc)
