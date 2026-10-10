"""google_news adapter – recent market developments with publication dates and links."""
from __future__ import annotations

from typing import Any

from app.schemas.analysis import Observation, SearchOutcome
from app.serpapi.normalize import (
    EvidenceRegistry, as_list, as_str, make_observation, news_freshness, parse_news_date,
)

ENGINE = "google_news"


def build_params(query: str, market: dict[str, Any]) -> dict[str, Any]:
    return {"q": query, "gl": market["gl"], "hl": market.get("hl", "en")}


def _flatten(items: list[Any]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("link") or item.get("title"):
            flat.append(item)
        for story in as_list(item.get("stories")):
            if isinstance(story, dict):
                flat.append(story)
        highlight = item.get("highlight")
        if isinstance(highlight, dict):
            flat.append(highlight)
    return flat


def parse(outcome: SearchOutcome, registry: EvidenceRegistry, *, country: str, focus: str | None,
          limit: int = 12) -> list[Observation]:
    data = outcome.data or {}
    out: list[Observation] = []
    seen: set[str] = set()
    for raw in _flatten(as_list(data.get("news_results"))):
        title = as_str(raw.get("title"))
        link = as_str(raw.get("link"), 2000)
        if not title or (link and link in seen):
            continue
        if link:
            seen.add(link)
        source = raw.get("source")
        source_name = as_str(source.get("name")) if isinstance(source, dict) else as_str(source)
        date_text = as_str(raw.get("iso_date")) or as_str(raw.get("date"))
        published = parse_news_date(date_text, outcome.retrieved_at)
        freshness, age = news_freshness(published, outcome.retrieved_at)
        if outcome.data_origin == "demo_fixture":
            freshness = "demo_fixture"
        normalized = {
            "title": title,
            "link": link,
            "source": source_name,
            "date_text": as_str(raw.get("date")),
            "published_at": published.isoformat() if published else None,
            "age_days": age,
            "snippet": as_str(raw.get("snippet"), 400),
        }
        out.append(make_observation(
            registry, outcome, kind="news_article", classification="reported_news",
            query=outcome.params.get("q", ""), country=country, title=title, normalized=normalized,
            original=raw, source_url=link, source_id=source_name, focus=focus,
            published_at=normalized["published_at"], freshness=freshness,
        ))
        if len(out) >= limit:
            break
    return out
