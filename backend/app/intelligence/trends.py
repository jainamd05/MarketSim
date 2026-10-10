"""Simple, transparent descriptions of Google Trends series (relative interest only)."""
from __future__ import annotations

from typing import Any

import numpy as np

from app.schemas.analysis import TrendSeriesSummary

RISING_THRESHOLD_PCT = 10.0


def summarize_series(query: str, points: list[dict[str, Any]]) -> TrendSeriesSummary:
    # Partial (incomplete) periods are excluded from change calculations.
    rows = [(p.get("date", ""), p.get(query)) for p in points if not p.get("partial")]
    values = [(d, float(v)) for d, v in rows if v is not None]
    if len(values) < 6:
        return TrendSeriesSummary(query=query, points=len(values), mean=None, first_period_avg=None,
                                  last_period_avg=None, change_pct=None, peak_value=None, peak_date=None,
                                  direction="insufficient_data",
                                  description=f"Not enough Trends data points for '{query}' to describe a trend.")
    arr = np.array([v for _, v in values])
    window = max(1, len(arr) // 4)
    first, last = float(arr[:window].mean()), float(arr[-window:].mean())
    change = None if first <= 0 else (last - first) / first * 100
    peak_idx = int(arr.argmax())
    if change is None:
        direction = "rising" if last > 0 else "flat"
    elif change > RISING_THRESHOLD_PCT:
        direction = "rising"
    elif change < -RISING_THRESHOLD_PCT:
        direction = "declining"
    else:
        direction = "flat"
    change_txt = "n/a (starting value 0)" if change is None else f"{change:+.0f}%"
    desc = (f"'{query}': average relative interest {arr.mean():.0f}/100; the last quarter of the period averaged "
            f"{last:.0f} vs {first:.0f} in the first quarter ({change_txt}), described as {direction}. "
            f"Peak {arr.max():.0f} around {values[peak_idx][0]}.")
    return TrendSeriesSummary(query=query, points=len(values), mean=round(float(arr.mean()), 1),
                              first_period_avg=round(first, 1), last_period_avg=round(last, 1),
                              change_pct=None if change is None else round(change, 1),
                              peak_value=float(arr.max()), peak_date=values[peak_idx][0], direction=direction,
                              description=desc)
