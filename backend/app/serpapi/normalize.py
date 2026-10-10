"""Defensive parsing helpers shared by all SerpApi adapters.

SerpApi payloads vary by query and engine version, so nothing here assumes a field exists.
"""
from __future__ import annotations

import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from app.schemas.analysis import Observation, SearchOutcome

# ---------------------------------------------------------------- primitives

def get(obj: Any, *path: str | int, default: Any = None) -> Any:
    cur = obj
    for key in path:
        if isinstance(key, int):
            if isinstance(cur, list) and -len(cur) <= key < len(cur):
                cur = cur[key]
            else:
                return default
        elif isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return default if cur is None else cur


def as_str(value: Any, max_len: int = 500) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value[:max_len] if value else None


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        m = re.search(r"-?\d[\d,]*\.?\d*", value)
        if m:
            try:
                return float(m.group(0).replace(",", ""))
            except ValueError:
                return None
    return None


def as_int(value: Any) -> int | None:
    """Parses ints including SerpApi style '1.2K', '3,456', '(512)'."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        m = re.search(r"(\d[\d,]*\.?\d*)\s*([kKmM])?", value)
        if not m:
            return None
        number = float(m.group(1).replace(",", ""))
        suffix = (m.group(2) or "").lower()
        number *= {"k": 1_000, "m": 1_000_000}.get(suffix, 1)
        return int(round(number))
    return None


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return None
    host = host.split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else (host or None)


# ------------------------------------------------------------------ currency
_CURRENCY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("INR", re.compile(r"₹|\bRs\.?\s?\d|\bINR\b", re.IGNORECASE)),
    ("GBP", re.compile(r"£|\bGBP\b")),
    ("AED", re.compile(r"\bAED\b|د\.إ")),
    ("EUR", re.compile(r"€|\bEUR\b")),
    ("USD", re.compile(r"US\$|\bUSD\b")),
]


def detect_currency(price_text: str | None, market_currency: str | None) -> tuple[str | None, str]:
    """Returns (currency, status). status: detected | inferred_from_market | missing | mismatch.

    A bare "$" is only accepted as USD in a USD market; elsewhere it is ambiguous and flagged.
    """
    if not price_text:
        return None, "missing"
    for code, pattern in _CURRENCY_PATTERNS:
        if pattern.search(price_text):
            status = "detected" if (market_currency is None or code == market_currency) else "mismatch"
            return code, status
    if "$" in price_text:
        if market_currency == "USD":
            return "USD", "inferred_from_market"
        return "USD?", "mismatch"
    return None, "missing"


# ----------------------------------------------------------------- freshness
def parse_news_date(raw: Any, retrieved_at: datetime) -> datetime | None:
    text = as_str(raw)
    if not text:
        return None
    try:  # ISO 8601
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)  # SerpApi google_news: "10/08/2026, 07:00 AM, +0000 UTC"
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)), tzinfo=timezone.utc)
        except ValueError:
            return None
    m = re.match(r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", text, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        days = {"minute": n / 1440, "hour": n / 24, "day": n, "week": 7 * n, "month": 30 * n, "year": 365 * n}[unit]
        return retrieved_at - timedelta(days=days)
    for fmt in ("%b %d, %Y", "%d %b %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def news_freshness(published: datetime | None, reference: datetime) -> tuple[str, int | None]:
    if published is None:
        return "unknown", None
    age = max(0, (reference - published).days)
    if age <= 30:
        return "current", age
    if age <= 180:
        return "recent", age
    return "stale", age


def retrieval_freshness(outcome: SearchOutcome) -> str:
    if outcome.data_origin == "demo_fixture":
        return "demo_fixture"
    if outcome.data_origin in {"live", "cache"}:
        return "current"
    return "unknown"


# ------------------------------------------------------------ evidence refs
class EvidenceRegistry:
    """Allocates stable, human-readable evidence references (SHOP-001, NEWS-004, ...)."""

    PREFIX = {
        "google_shopping": "SHOP", "google_product": "PROD", "google_immersive_product": "PROD",
        "google": "WEB", "google_maps": "MAP", "google_trends": "TRD", "google_news": "NEWS",
        "google_autocomplete": "AC", "amazon": "AMZ",
    }

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._lock = threading.Lock()
        self.items: dict[str, Observation] = {}

    def next_ref(self, engine: str) -> str:
        prefix = self.PREFIX.get(engine, "EV")
        with self._lock:
            self._counters[prefix] = self._counters.get(prefix, 0) + 1
            return f"{prefix}-{self._counters[prefix]:03d}"

    def add(self, obs: Observation) -> Observation:
        with self._lock:
            self.items[obs.ref] = obs
        return obs


def make_observation(registry: EvidenceRegistry, outcome: SearchOutcome, *, kind: str, classification: str,
                     query: str, country: str | None, title: str, normalized: dict[str, Any],
                     original: dict[str, Any], source_url: str | None = None, source_id: str | None = None,
                     focus: str | None = None, published_at: str | None = None,
                     freshness: str | None = None) -> Observation:
    obs = Observation(
        ref=registry.next_ref(outcome.engine), kind=kind, engine=outcome.engine, query=query, country=country,
        retrieved_at=outcome.retrieved_at, source_url=source_url, source_id=source_id, title=title or "(untitled)",
        classification=classification, freshness=freshness or retrieval_freshness(outcome),
        data_origin=outcome.data_origin, published_at=published_at, focus=focus,
        normalized={k: v for k, v in normalized.items() if v is not None}, original=_trim(original),
    )
    return registry.add(obs)


def _trim(original: dict[str, Any], max_chars: int = 4000) -> dict[str, Any]:
    """Keep the original payload item for provenance, dropping heavy media fields."""
    drop = {"thumbnail", "thumbnails", "serpapi_thumbnail", "images", "media", "favicon", "icon", "serpapi_link",
            "serpapi_product_api", "serpapi_product_api_comparative", "serpapi_immersive_product_api"}
    out: dict[str, Any] = {}
    budget = max_chars
    for key, value in original.items() if isinstance(original, dict) else []:
        if key in drop:
            continue
        size = len(str(value))
        if size > budget:
            continue
        out[key] = value
        budget -= size
    return out
