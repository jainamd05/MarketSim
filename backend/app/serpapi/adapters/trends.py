"""google_trends adapter – interest over time, related queries, interest by region.

Values are relative (0–100) indices. The adapter preserves that context and never
converts them into volumes.
"""
from __future__ import annotations

from typing import Any

from app.schemas.analysis import Observation, SearchOutcome
from app.serpapi.normalize import EvidenceRegistry, as_float, as_int, as_list, as_str, get, make_observation

ENGINE = "google_trends"
DEFAULT_RANGE = "today 12-m"


def build_timeseries_params(queries: list[str], geo: str, date: str = DEFAULT_RANGE) -> dict[str, Any]:
    # SerpApi allows up to 5 comma-separated queries for TIMESERIES comparisons.
    return {"q": ",".join(queries[:5]), "geo": geo, "date": date, "data_type": "TIMESERIES"}


def build_related_params(query: str, geo: str, date: str = DEFAULT_RANGE) -> dict[str, Any]:
    return {"q": query, "geo": geo, "date": date, "data_type": "RELATED_QUERIES"}


def build_region_params(query: str, geo: str, date: str = DEFAULT_RANGE) -> dict[str, Any]:
    return {"q": query, "geo": geo, "date": date, "data_type": "GEO_MAP_0"}


def parse_timeseries(outcome: SearchOutcome, registry: EvidenceRegistry, *, country: str,
                     query_focus: dict[str, str]) -> tuple[list[dict[str, Any]], list[Observation]]:
    """Returns (points, observations). points: [{date, timestamp, partial, <query>: value|None}]."""
    data = outcome.data or {}
    timeline = as_list(get(data, "interest_over_time", "timeline_data"))
    queries = [q.strip() for q in outcome.params.get("q", "").split(",") if q.strip()]
    points: list[dict[str, Any]] = []
    for row in timeline:
        if not isinstance(row, dict):
            continue
        point: dict[str, Any] = {
            "date": as_str(row.get("date")) or "",
            "timestamp": as_int(row.get("timestamp")),
            "partial": bool(row.get("partial_data", False)),
        }
        for q in queries:
            point[q] = None
        for v in as_list(row.get("values")):
            if not isinstance(v, dict):
                continue
            q = as_str(v.get("query"))
            if not q:
                continue
            value = v.get("extracted_value")
            point[q] = as_float(value) if value is not None else as_float(v.get("value"))
        points.append(point)

    observations = []
    for q in queries:
        series = [p.get(q) for p in points]
        valid = [s for s in series if s is not None]
        observations.append(make_observation(
            registry, outcome, kind="trend_series", classification="relative_search_interest", query=q,
            country=country, title=f"Google Trends interest over time: {q}",
            normalized={"query": q, "geo": outcome.params.get("geo"), "date_range": outcome.params.get("date"),
                        "points": len(valid), "compared_with": [x for x in queries if x != q],
                        "scale": "relative 0-100 across compared terms"},
            original={"query": q, "series_sample": series[:6]},
            source_url=as_str(get(data, "search_metadata", "google_trends_url"), 2000),
            focus=query_focus.get(q),
        ))
    return points, observations


def parse_related(outcome: SearchOutcome, registry: EvidenceRegistry, *, country: str,
                  focus: str | None) -> tuple[dict[str, Any], list[Observation]]:
    data = outcome.data or {}
    rq = data.get("related_queries") if isinstance(data.get("related_queries"), dict) else {}
    result: dict[str, Any] = {"query": outcome.params.get("q"), "top": [], "rising": []}
    observations: list[Observation] = []
    for bucket in ("top", "rising"):
        for item in as_list(rq.get(bucket))[:10]:
            if not isinstance(item, dict) or not as_str(item.get("query")):
                continue
            entry = {
                "query": as_str(item.get("query")),
                "value_text": as_str(item.get("value")),
                "value": as_float(item.get("extracted_value")),
            }
            result[bucket].append(entry)
    if result["top"] or result["rising"]:
        observations.append(make_observation(
            registry, outcome, kind="related_query", classification="relative_search_interest",
            query=outcome.params.get("q", ""), country=country,
            title=f"Related queries for '{outcome.params.get('q')}'",
            normalized={"top": [e["query"] for e in result["top"]], "rising": [e["query"] for e in result["rising"]]},
            original={"top": result["top"][:5], "rising": result["rising"][:5]},
            source_url=as_str(get(data, "search_metadata", "google_trends_url"), 2000), focus=focus,
        ))
    return result, observations


def parse_regions(outcome: SearchOutcome, registry: EvidenceRegistry, *, country: str,
                  focus: str | None) -> tuple[list[dict[str, Any]], list[Observation]]:
    data = outcome.data or {}
    regions = []
    for item in as_list(data.get("interest_by_region"))[:20]:
        if not isinstance(item, dict):
            continue
        name = as_str(item.get("location"))
        if not name:
            continue
        regions.append({"location": name, "value": as_float(item.get("extracted_value"))
                        if item.get("extracted_value") is not None else as_float(item.get("value"))})
    observations = []
    if regions:
        observations.append(make_observation(
            registry, outcome, kind="regional_interest", classification="relative_search_interest",
            query=outcome.params.get("q", ""), country=country,
            title=f"Interest by region for '{outcome.params.get('q')}'",
            normalized={"regions": regions[:10]}, original={"interest_by_region": regions[:10]}, focus=focus,
        ))
    return regions, observations
