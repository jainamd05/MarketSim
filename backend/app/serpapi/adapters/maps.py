"""google_maps adapter – location-specific competitors for physical shops."""
from __future__ import annotations

from typing import Any

from app.schemas.analysis import Observation, SearchOutcome
from app.serpapi.normalize import EvidenceRegistry, as_float, as_int, as_list, as_str, domain_of, get, make_observation

ENGINE = "google_maps"


def build_params(term: str, city: str, locality: str | None, market: dict[str, Any]) -> dict[str, Any]:
    place = f"{locality}, {city}" if locality else city
    return {"q": f"{term} in {place}", "type": "search", "hl": market.get("hl", "en"), "gl": market["gl"]}


def parse(outcome: SearchOutcome, registry: EvidenceRegistry, *, country: str, focus: str | None,
          limit: int = 20) -> list[Observation]:
    data = outcome.data or {}
    results = as_list(data.get("local_results"))
    if not results and isinstance(data.get("place_results"), dict):
        results = [data["place_results"]]
    out: list[Observation] = []
    for raw in results:
        if not isinstance(raw, dict):
            continue
        title = as_str(raw.get("title"))
        if not title:
            continue
        website = as_str(raw.get("website"), 2000)
        types = [t for t in (as_str(x) for x in as_list(raw.get("types"))) if t]
        normalized = {
            "title": title,
            "rating": as_float(raw.get("rating")),
            "reviews": as_int(raw.get("reviews")),
            "address": as_str(raw.get("address")),
            "website": website,
            "domain": domain_of(website),
            "type": as_str(raw.get("type")),
            "types": types or None,
            "price_level": as_str(raw.get("price")),
            "place_id": as_str(raw.get("place_id")),
            "latitude": as_float(get(raw, "gps_coordinates", "latitude")),
            "longitude": as_float(get(raw, "gps_coordinates", "longitude")),
            "open_state": as_str(raw.get("open_state")),
        }
        link = website or as_str(raw.get("link"), 2000)
        out.append(make_observation(
            registry, outcome, kind="local_business", classification="map_listing",
            query=outcome.params.get("q", ""), country=country, title=title, normalized=normalized,
            original=raw, source_url=link, source_id=normalized["place_id"], focus=focus,
        ))
        if len(out) >= limit:
            break
    return out
