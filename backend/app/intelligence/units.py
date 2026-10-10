"""Pack-size parsing and unit-price normalisation.

Products are only compared on a per-unit basis when the pack size is parsed
unambiguously. Ambiguous or missing sizes are flagged as unverified and excluded
from unit-price statistics.
"""
from __future__ import annotations

import re

from app.schemas.analysis import Quantity

_MASS = {"kg": 1000.0, "kgs": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0, "g": 1.0, "gm": 1.0, "gms": 1.0,
         "gram": 1.0, "grams": 1.0, "gr": 1.0, "mg": 0.001, "oz": 28.3495, "lb": 453.592, "lbs": 453.592}
_VOLUME = {"l": 1000.0, "ltr": 1000.0, "litre": 1000.0, "liter": 1000.0, "litres": 1000.0, "liters": 1000.0,
           "ml": 1.0, "fl oz": 29.5735, "floz": 29.5735}
_UNIT_ALT = "|".join(sorted({*_MASS, *_VOLUME}, key=len, reverse=True)).replace(" ", r"\s?")
_SIZE_RE = re.compile(rf"(\d+(?:\.\d+)?)\s*({_UNIT_ALT})\b", re.IGNORECASE)
_MULTI_RE = re.compile(rf"(\d+)\s*[x×\*]\s*(\d+(?:\.\d+)?)\s*({_UNIT_ALT})\b", re.IGNORECASE)
_MULTI_REV_RE = re.compile(rf"(\d+(?:\.\d+)?)\s*({_UNIT_ALT})\s*[x×\*]\s*(\d+)\b", re.IGNORECASE)
_PACK_OF_RE = re.compile(r"\b(?:pack|set|combo|box|case)\s+of\s+(\d+)\b", re.IGNORECASE)
_COUNT_RE = re.compile(
    r"\b(\d+)\s*(?:pcs|pieces|piece|count|ct|sachets|sachet|bars|bar|units|capsules|tablets|tea\s?bags|pods|cans|bottles|jars|packs)\b",
    re.IGNORECASE,
)


def _to_base(value: float, unit: str) -> tuple[float, str]:
    unit = unit.lower().replace(" ", "")
    if unit in _MASS:
        return value * _MASS[unit], "g"
    key = "fl oz" if unit == "floz" else unit
    return value * _VOLUME.get(key, _VOLUME.get(unit, 1.0)), "ml"


def parse_quantity(title: str | None) -> Quantity:
    if not title:
        return Quantity(status="missing")
    text = title.replace(",", "")

    m = _MULTI_RE.search(text)
    if m:
        count, size, unit = int(m.group(1)), float(m.group(2)), m.group(3)
        amount, base = _to_base(size, unit)
        if count > 0 and amount > 0:
            return Quantity(status="parsed", amount=round(amount * count, 4), base_unit=base, pack_count=count, raw=m.group(0))
    m = _MULTI_REV_RE.search(text)
    if m:
        size, unit, count = float(m.group(1)), m.group(2), int(m.group(3))
        amount, base = _to_base(size, unit)
        if count > 0 and amount > 0:
            return Quantity(status="parsed", amount=round(amount * count, 4), base_unit=base, pack_count=count, raw=m.group(0))

    sizes = [(_to_base(float(v), u), f"{v}{u}") for v, u in _SIZE_RE.findall(text)]
    distinct = {(round(a, 3), b) for (a, b), _ in sizes}
    pack = _PACK_OF_RE.search(text)
    pack_count = int(pack.group(1)) if pack else 1

    if len(distinct) == 1:
        (amount, base), raw = sizes[0]
        if amount <= 0:
            return Quantity(status="ambiguous", raw=raw)
        return Quantity(status="parsed", amount=round(amount * pack_count, 4), base_unit=base,
                        pack_count=pack_count, raw=raw if pack_count == 1 else f"{pack_count} x {raw}")
    if len(distinct) > 1:
        bases = {b for _, b in distinct}
        # "Assorted 250g & 500g" or mixed g/ml => cannot normalise reliably
        return Quantity(status="ambiguous", raw=", ".join(r for _, r in sizes)[:80],
                        base_unit=bases.pop() if len(bases) == 1 else None)

    count = _COUNT_RE.search(text)
    if count:
        n = int(count.group(1)) * pack_count
        if n > 0:
            return Quantity(status="parsed", amount=float(n), base_unit="count", pack_count=pack_count, raw=count.group(0))
    if pack:
        return Quantity(status="parsed", amount=float(pack_count), base_unit="count", pack_count=pack_count, raw=pack.group(0))
    return Quantity(status="missing")


def unit_price(price: float | None, qty: Quantity) -> tuple[float | None, str | None]:
    """Returns (unit_price, basis). Only computed for unambiguously parsed sizes."""
    if price is None or qty.status != "parsed" or not qty.amount or qty.amount <= 0:
        return None, None
    if qty.base_unit == "g":
        return round(price / qty.amount * 100, 2), "per_100g"
    if qty.base_unit == "ml":
        return round(price / qty.amount * 100, 2), "per_100ml"
    if qty.base_unit == "count":
        return round(price / qty.amount, 2), "per_unit"
    return None, None
