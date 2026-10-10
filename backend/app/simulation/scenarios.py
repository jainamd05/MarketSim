"""Bear / base / bull scenarios with explicit, bounded adjustments."""
from __future__ import annotations

from app.schemas.analysis import OnlineSimInputs, PhysicalSimInputs, ScenarioResult
from app.simulation.finance import simulate

ONLINE_ADJUSTMENTS = {
    "bear": {"cac": 1.35, "selling_price": 0.95, "unit_cost": 1.10, "return_rate_pct": +3.0,
             "organic_orders": 0.5, "repeat_orders": 0.5},
    "bull": {"cac": 0.80, "selling_price": 1.00, "unit_cost": 0.95, "return_rate_pct": -1.0,
             "organic_orders": 1.5, "repeat_orders": 1.5},
}
PHYSICAL_ADJUSTMENTS = {
    "bear": {"daily_footfall": 0.75, "conversion_rate_pct": 0.85, "cogs_pct": +3.0},
    "bull": {"daily_footfall": 1.20, "conversion_rate_pct": 1.10, "cogs_pct": -2.0},
}
_ADDITIVE = {"return_rate_pct", "cogs_pct"}


def _describe(field: str, factor: float) -> str:
    if field in _ADDITIVE:
        return f"{factor:+.0f} percentage points"
    return "unchanged" if factor == 1 else f"×{factor:.2f}"


def apply_adjustments(inp: OnlineSimInputs | PhysicalSimInputs, scenario: str):
    table = ONLINE_ADJUSTMENTS if isinstance(inp, OnlineSimInputs) else PHYSICAL_ADJUSTMENTS
    if scenario == "base":
        return inp, {"all": "stated central assumptions"}
    adj = table[scenario]
    data = inp.model_dump()
    for field, factor in adj.items():
        if field in _ADDITIVE:
            data[field] = min(100.0, max(0.0, data[field] + factor))
        else:
            data[field] = data[field] * factor
    return type(inp)(**data), {f: _describe(f, v) for f, v in adj.items()}


def run_scenarios(inp: OnlineSimInputs | PhysicalSimInputs) -> list[ScenarioResult]:
    results = []
    for name in ("bear", "base", "bull"):
        adjusted, description = apply_adjustments(inp, name)
        results.append(ScenarioResult(scenario=name, adjustments=description, inputs=adjusted.model_dump(),
                                      result=simulate(adjusted)))
    return results
