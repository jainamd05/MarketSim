"""Competitor intelligence: brand normalisation, merchant de-duplication, listing
normalisation, sampled price statistics and evidence-backed positioning tags.

Nothing here estimates market share or competitor sales: statistics describe the
sampled search listings only.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable

import pandas as pd

from app.intelligence.units import parse_quantity, unit_price
from app.schemas.analysis import CompetitorEntry, Listing, Observation, PositioningTag, PriceGroupStats
from app.serpapi.normalize import detect_currency, domain_of

MARKETPLACES = {
    "amazon", "flipkart", "bigbasket", "jiomart", "blinkit", "zepto", "swiggy", "swiggyinstamart", "instamart",
    "nykaa", "myntra", "meesho", "tatacliq", "snapdeal", "ebay", "walmart", "etsy", "noon", "target", "tesco",
    "sainsburys", "ocado", "carrefour", "indiamart", "firstcry", "ajio", "pharmeasy", "1mg", "tata1mg",
}
REFERENCE_DOMAINS = {
    "wikipedia", "quora", "reddit", "youtube", "facebook", "instagram", "linkedin", "economictimes", "livemint",
    "inc42", "yourstory", "forbes", "forbesindia", "ndtv", "thehindu", "hindustantimes", "business-standard",
    "businessstandard", "moneycontrol", "timesofindia", "indiatimes", "medium", "pinterest", "tracxn", "crunchbase",
}
_LISTICLE = re.compile(r"\b(best|top\s*\d*|list of|vs\.?|review|reviews|ranking|ranked|guide|compared|market overview|"
                       r"industry|report|news|how to|what is)\b", re.IGNORECASE)
_SUFFIXES = {"pvt", "private", "ltd", "limited", "llp", "inc", "llc", "co", "company", "official", "store", "shop",
             "online", "the", "www", "com", "in", "net", "org", "example", "uk", "ae"}


def brand_key(name: str | None) -> str | None:
    """Normalise a merchant/brand name or domain to a comparison key.

    "Kaapi Trail Official Store" -> "kaapitrail", "https://www.kaapitrail.example/x" -> "kaapitrail",
    "Amazon.in - Seller" -> "amazon".
    """
    if not name:
        return None
    s = name.lower().strip()
    if "://" in s or s.startswith("www."):
        s = domain_of(s if "://" in s else "https://" + s) or s
    s = re.sub(r"\s+-\s+.*$", "", s)  # "Amazon.in - Seller" -> "amazon.in"
    s = re.sub(r"\.(co\.in|co\.uk|com|in|co|ae|net|org|store|shop|example|io)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    tokens = [t for t in s.split() if t not in _SUFFIXES]
    key = "".join(tokens)
    return key or None


def is_marketplace(key: str | None) -> bool:
    return bool(key) and any(key == m or key.startswith(m) for m in MARKETPLACES)


# ------------------------------------------------------------------- listings
def build_listings(observations: Iterable[Observation], market_currency: str | None) -> list[Listing]:
    listings: list[Listing] = []
    for obs in observations:
        if obs.kind not in {"product_listing", "marketplace_listing"}:
            continue
        n = obs.normalized
        price = n.get("extracted_price")
        currency, currency_status = detect_currency(n.get("price_text"), market_currency)
        flags: list[str] = []
        if price is None:
            flags.append("missing_price")
        if currency_status == "missing":
            flags.append("missing_currency")
        elif currency_status == "mismatch":
            flags.append("currency_mismatch")
        qty = parse_quantity(obs.title)
        if qty.status == "ambiguous":
            flags.append("ambiguous_size")
        elif qty.status == "missing":
            flags.append("unverified_size")
        old = n.get("extracted_old_price")
        tags = " ".join(n.get("tags") or []).lower()
        promotion = bool(old and price and old > price) or bool(re.search(r"\bsale\b|% off|\bdeal\b|discount", tags))
        if promotion:
            flags.append("promotion")
        if n.get("second_hand"):
            flags.append("second_hand")
        merchant = n.get("merchant")
        key = brand_key(merchant)
        marketplace = obs.kind == "marketplace_listing" or is_marketplace(key)
        up, basis = unit_price(price, qty)
        included = (price is not None and currency_status in {"detected", "inferred_from_market"}
                    and "second_hand" not in flags)
        listings.append(Listing(
            evidence_ref=obs.ref, focus=obs.focus or "unknown", country=obs.country or "??", engine=obs.engine,
            title=obs.title, merchant=merchant, merchant_key=key, product_id=n.get("product_id") or n.get("asin"),
            price_text=n.get("price_text"), price=price, currency=currency, currency_status=currency_status,
            old_price=old, promotion=promotion, quantity=qty, unit_price=up if included else None,
            unit_price_basis=basis if included else None, rating=n.get("rating"), reviews=n.get("reviews"),
            delivery=n.get("delivery"), source_url=obs.source_url, retrieved_at=obs.retrieved_at, flags=flags,
            is_marketplace=marketplace, included_in_stats=included,
        ))
    return listings


def price_stats(listings: list[Listing], focus: str, focus_label: str, country: str,
                market_currency: str | None) -> PriceGroupStats:
    group = [l for l in listings if l.focus == focus and l.country == country]
    excluded = [{"ref": l.evidence_ref, "reason": ", ".join(f for f in l.flags if f in
                {"missing_price", "missing_currency", "currency_mismatch", "second_hand"}) or "excluded"}
                for l in group if not l.included_in_stats]
    included = [l for l in group if l.included_in_stats]
    stats = PriceGroupStats(focus=focus, focus_label=focus_label, country=country, currency=market_currency,
                            sample_size=len(group), included_count=len(included), excluded=excluded,
                            promotion_count=sum(1 for l in group if l.promotion))
    warnings: list[str] = []
    if not included:
        warnings.append("No listings with a verified price and currency – price statistics unavailable.")
        stats.warnings = warnings
        return stats
    currencies = {l.currency for l in included}
    if len(currencies) > 1:  # should not happen because mismatches are excluded – guard anyway
        warnings.append(f"Mixed currencies {sorted(c or '?' for c in currencies)}; statistics withheld.")
        stats.warnings = warnings
        return stats
    stats.currency = currencies.pop()

    df = pd.DataFrame([{"ref": l.evidence_ref, "price": l.price} for l in included])
    q = df["price"].quantile([0.25, 0.5, 0.75])
    stats.min, stats.max = round(float(df["price"].min()), 2), round(float(df["price"].max()), 2)
    stats.p25, stats.median, stats.p75 = (round(float(q.loc[p]), 2) for p in (0.25, 0.5, 0.75))
    if len(df) >= 4:
        iqr = stats.p75 - stats.p25
        lo, hi = stats.p25 - 1.5 * iqr, stats.p75 + 1.5 * iqr
        stats.outlier_refs = df.loc[(df["price"] < lo) | (df["price"] > hi), "ref"].tolist()

    # Unit prices: only the dominant, unambiguous basis (never mix g with ml or count)
    unit_rows = [l for l in included if l.unit_price is not None]
    if unit_rows:
        basis_counts = pd.Series([l.unit_price_basis for l in unit_rows]).value_counts()
        basis = str(basis_counts.index[0])
        values = pd.Series([l.unit_price for l in unit_rows if l.unit_price_basis == basis])
        stats.unit_basis = basis
        stats.unit_sample_size = int(values.size)
        stats.unit_min, stats.unit_median, stats.unit_max = (round(float(v), 2) for v in (values.min(), values.median(), values.max()))
        stats.unit_p25, stats.unit_p75 = (round(float(values.quantile(q)), 2) for q in (0.25, 0.75))
        other = len(unit_rows) - int(values.size)
        if other:
            warnings.append(f"{other} listing(s) use a different unit basis and were not mixed into {basis} statistics.")
    unverified = sum(1 for l in included if l.unit_price is None)
    if unverified:
        warnings.append(f"{unverified} listing(s) have unverified or ambiguous pack sizes; excluded from unit-price comparison.")
    if len(included) < 8:
        warnings.append(f"Small sample (n={len(included)}). Figures describe sampled listings only, not the whole market.")
    if stats.outlier_refs:
        warnings.append(f"{len(stats.outlier_refs)} price outlier(s) flagged by the 1.5×IQR rule.")
    if stats.promotion_count:
        warnings.append(f"{stats.promotion_count} listing(s) show promotional pricing; advertised prices may be temporary.")
    stats.warnings = warnings
    return stats


# ---------------------------------------------------------------- competitors
def _classify_web(obs: Observation, focus_terms: list[str]) -> tuple[str, str]:
    n = obs.normalized
    key = brand_key(n.get("domain"))
    text = f"{obs.title} {n.get('snippet') or ''}".lower()
    if is_marketplace(key):
        return "marketplace", "Marketplace page returned by web search."
    if key and any(key.startswith(d) for d in REFERENCE_DOMAINS):
        return "reference", "Editorial, social or directory site – a reference, not a seller."
    if _LISTICLE.search(obs.title):
        return "reference", "Listicle/review page – may mention competitors but is not itself a seller."
    if any(t in text for t in focus_terms):
        return "direct", f"Website returned for '{obs.query}' and its title/snippet mentions the product focus."
    return "reference", f"Website returned for '{obs.query}' without a clear product-focus match."


def build_competitors(listings: list[Listing], observations: list[Observation], focus_terms: dict[str, list[str]],
                      price_groups: dict[str, PriceGroupStats]) -> list[CompetitorEntry]:
    entries: dict[str, CompetitorEntry] = {}

    def entry_for(key: str, name: str, relation: str, reason: str) -> CompetitorEntry:
        existing = entries.get(key)
        if existing is None:
            existing = CompetitorEntry(key=key, name=name, relation=relation, relation_reason=reason)
            entries[key] = existing
        elif relation == "direct" and existing.relation == "reference":
            existing.relation, existing.relation_reason = relation, reason
        return existing

    def add_unique(lst: list, value: Any) -> None:
        if value is not None and value not in lst:
            lst.append(value)

    known_names: dict[str, str] = {}
    for l in listings:
        if l.merchant_key and l.merchant:
            known_names.setdefault(l.merchant_key, l.merchant)

    # 1) Listings (Shopping / Amazon)
    for l in listings:
        key = l.merchant_key
        name = l.merchant
        if not key and l.engine == "amazon":
            # Brand not provided: match a known merchant name inside the title (labelled in reason)
            title_key = brand_key(l.title) or ""
            match = next((k for k in known_names if k and len(k) > 4 and k in title_key), None)
            key, name = (match, known_names[match]) if match else ("amazon", "Amazon")
        if not key:
            continue
        if is_marketplace(key):
            e = entry_for(key, name or key, "marketplace", "Marketplace or multi-brand retailer listing comparable products.")
        else:
            e = entry_for(key, name or key, "direct",
                          f"Advertises a comparable product in the sampled {l.focus.replace('_', ' ')} listings.")
        add_unique(e.engines, l.engine)
        add_unique(e.countries, l.country)
        add_unique(e.focuses, l.focus)
        add_unique(e.evidence_refs, l.evidence_ref)
        add_unique(e.listing_refs, l.evidence_ref)
        if len(e.product_examples) < 4:
            add_unique(e.product_examples, l.title)
        if l.included_in_stats and l.price is not None:
            e.currency = l.currency
            e.price_min = l.price if e.price_min is None else min(e.price_min, l.price)
            e.price_max = l.price if e.price_max is None else max(e.price_max, l.price)
        if l.rating is not None and (e.reviews or 0) <= (l.reviews or 0):
            e.rating, e.reviews = l.rating, l.reviews

    # 2) Web search results & 3) Maps results
    for obs in observations:
        if obs.kind == "competitor_page":
            key = brand_key(obs.normalized.get("domain"))
            if not key:
                continue
            terms = focus_terms.get(obs.focus or "", []) or [t for ts in focus_terms.values() for t in ts]
            relation, reason = _classify_web(obs, terms)
            if key in entries:
                e = entries[key]
                if relation == "direct" and e.relation == "reference":
                    e.relation, e.relation_reason = relation, reason
            else:
                name = known_names.get(key) or obs.normalized.get("source") or obs.title.split(" - ")[0].split(" | ")[0][:60]
                e = entry_for(key, name, relation, reason)
            add_unique(e.websites, obs.source_url)
            add_unique(e.engines, obs.engine)
            add_unique(e.countries, obs.country)
            add_unique(e.evidence_refs, obs.ref)
            if obs.focus:
                add_unique(e.focuses, obs.focus)
            if not e.snippet:
                e.snippet = obs.normalized.get("snippet")
        elif obs.kind == "local_business":
            n = obs.normalized
            key = brand_key(n.get("title"))
            if not key:
                continue
            e = entry_for(key, n.get("title"), "direct",
                          f"Local business returned by Google Maps for '{obs.query}'.")
            add_unique(e.engines, obs.engine)
            add_unique(e.countries, obs.country)
            add_unique(e.evidence_refs, obs.ref)
            if obs.focus:
                add_unique(e.focuses, obs.focus)
            if n.get("website"):
                add_unique(e.websites, n.get("website"))
            e.address = e.address or n.get("address")
            if n.get("rating") is not None:
                e.rating, e.reviews = n.get("rating"), n.get("reviews")

    # 4) Evidence-backed positioning tags
    unit_by_merchant: dict[str, list[tuple[float, str, str]]] = defaultdict(list)
    for l in listings:
        if l.merchant_key and l.unit_price is not None:
            unit_by_merchant[l.merchant_key].append((l.unit_price, l.focus, l.evidence_ref))
    for e in entries.values():
        tags: list[PositioningTag] = []
        rows = unit_by_merchant.get(e.key, [])
        for up, focus, ref in rows[:3]:
            group = price_groups.get(focus)
            if not group or not group.unit_median:
                continue
            ratio = up / group.unit_median
            if ratio >= 1.25:
                tags.append(PositioningTag(tag="premium_priced", basis="observed",
                                           detail=f"Unit price {ratio:.2f}× the sampled median ({group.unit_basis}).",
                                           evidence_refs=[ref]))
            elif ratio <= 0.8:
                tags.append(PositioningTag(tag="value_priced", basis="observed",
                                           detail=f"Unit price {ratio:.2f}× the sampled median ({group.unit_basis}).",
                                           evidence_refs=[ref]))
            break
        if e.rating is not None and e.rating >= 4.5 and (e.reviews or 0) >= 50:
            tags.append(PositioningTag(tag="highly_rated", basis="observed",
                                       detail=f"Rated {e.rating} from {e.reviews} reviews in the sampled result.",
                                       evidence_refs=e.evidence_refs[:1]))
        promo_refs = [l.evidence_ref for l in listings if l.merchant_key == e.key and l.promotion]
        if promo_refs:
            tags.append(PositioningTag(tag="promotional_pricing", basis="observed",
                                       detail="At least one sampled listing shows a reduced/sale price.",
                                       evidence_refs=promo_refs[:2]))
        if len(e.engines) >= 2 and e.relation == "direct":
            tags.append(PositioningTag(tag="multi_channel_presence", basis="observed",
                                       detail=f"Found via {', '.join(e.engines)}.", evidence_refs=e.evidence_refs[:3]))
        if e.relation == "direct" and e.websites and e.listing_refs:
            tags.append(PositioningTag(tag="likely_d2c_brand", basis="interpretation",
                                       detail="Own website plus product listings suggest direct-to-consumer selling; "
                                              "not verified on the destination site.",
                                       evidence_refs=e.evidence_refs[:2]))
        e.tags = tags

    order = {"direct": 0, "marketplace": 1, "reference": 2}
    return sorted(entries.values(), key=lambda c: (order[c.relation], -len(c.evidence_refs), c.name.lower()))
