"""Loads the shared, configuration-driven questionnaire registry (shared/questionnaire.json)."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from app.config import QUESTIONNAIRE_PATH


@lru_cache
def load_registry() -> dict[str, Any]:
    with open(QUESTIONNAIRE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def category(value: str) -> dict[str, Any] | None:
    return next((c for c in load_registry()["categories"] if c["value"] == value), None)


def subcategory(category_value: str, sub_value: str) -> dict[str, Any] | None:
    cat = category(category_value)
    if not cat:
        return None
    return next((s for s in cat["subcategories"] if s["value"] == sub_value), None)


def market(code: str) -> dict[str, Any] | None:
    return next((m for m in load_registry()["markets"] if m["code"] == code.upper()), None)


def market_name(code: str | None) -> str:
    if not code:
        return "Unknown"
    m = market(code)
    return m["label"] if m else code.upper()


def market_currency(code: str | None) -> str | None:
    m = market(code) if code else None
    return m["currency"] if m else None


def budget_band(value: str) -> dict[str, Any] | None:
    return next((b for b in load_registry()["budget_bands"] if b["value"] == value), None)


def label_for(options: list[dict[str, Any]], value: str | None) -> str | None:
    if value is None:
        return None
    match = next((o for o in options if o.get("value") == value), None)
    return match["label"] if match else value


def valid_values(options: list[dict[str, Any]]) -> set[str]:
    return {o["value"] for o in options}
