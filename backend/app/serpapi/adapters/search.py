"""google (web search) adapter – competitor websites and external market context.

Search snippets do not prove claims made on destination websites; observations are
classified as ``search_snippet``.
"""
from __future__ import annotations

from typing import Any

from app.schemas.analysis import Observation, SearchOutcome
from app.serpapi.normalize import EvidenceRegistry, as_list, as_str, domain_of, make_observation

ENGINE = "google"


def build_params(query: str, market: dict[str, Any]) -> dict[str, Any]:
    return {"q": query, "gl": market["gl"], "hl": market.get("hl", "en"), "google_domain": market["google_domain"]}


def parse(outcome: SearchOutcome, registry: EvidenceRegistry, *, country: str, focus: str | None,
          limit: int = 10) -> list[Observation]:
    data = outcome.data or {}
    out: list[Observation] = []
    for raw in as_list(data.get("organic_results")):
        if not isinstance(raw, dict):
            continue
        link = as_str(raw.get("link"), 2000)
        title = as_str(raw.get("title"))
        if not title or not link:
            continue
        normalized = {
            "title": title,
            "link": link,
            "domain": domain_of(link),
            "displayed_link": as_str(raw.get("displayed_link")),
            "snippet": as_str(raw.get("snippet"), 400),
            "source": as_str(raw.get("source")),
            "position": raw.get("position") if isinstance(raw.get("position"), int) else None,
        }
        out.append(make_observation(
            registry, outcome, kind="competitor_page", classification="search_snippet",
            query=outcome.params.get("q", ""), country=country, title=title, normalized=normalized,
            original=raw, source_url=link, source_id=normalized["domain"], focus=focus,
        ))
        if len(out) >= limit:
            break
    return out
