"""google_autocomplete adapter – keyword expansion for demand research (suggestions, not volumes)."""
from __future__ import annotations

from typing import Any

from app.schemas.analysis import Observation, SearchOutcome
from app.serpapi.normalize import EvidenceRegistry, as_list, as_str, make_observation

ENGINE = "google_autocomplete"


def build_params(query: str, market: dict[str, Any]) -> dict[str, Any]:
    return {"q": query, "gl": market["gl"], "hl": market.get("hl", "en")}


def parse(outcome: SearchOutcome, registry: EvidenceRegistry, *, country: str,
          focus: str | None) -> tuple[list[str], list[Observation]]:
    data = outcome.data or {}
    suggestions = []
    for raw in as_list(data.get("suggestions")):
        value = as_str(raw.get("value")) if isinstance(raw, dict) else as_str(raw)
        if value and value not in suggestions:
            suggestions.append(value)
    observations = []
    if suggestions:
        observations.append(make_observation(
            registry, outcome, kind="keyword_suggestion", classification="search_suggestion",
            query=outcome.params.get("q", ""), country=country,
            title=f"Autocomplete suggestions for '{outcome.params.get('q')}'",
            normalized={"suggestions": suggestions[:10]}, original={"suggestions": suggestions[:10]}, focus=focus,
        ))
    return suggestions[:10], observations
