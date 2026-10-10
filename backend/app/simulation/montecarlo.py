"""Seeded Monte Carlo over explicitly stated assumption distributions (vectorised NumPy)."""
from __future__ import annotations

import numpy as np

from app.schemas.analysis import DistributionSpec, MonteCarloResult, OnlineSimInputs, PhysicalSimInputs

PERCENTILES = (5, 10, 25, 50, 75, 90, 95)


def _tri(rng: np.random.Generator, lo: float, mode: float, hi: float, n: int) -> np.ndarray:
    if hi <= lo:
        return np.full(n, mode)
    mode = min(max(mode, lo), hi)
    return rng.triangular(lo, mode, hi, n)


def _summarise(op: np.ndarray, iterations: int, seed: int, specs: list[DistributionSpec]) -> MonteCarloResult:
    pct = {f"p{p}": round(float(np.percentile(op, p)), 2) for p in PERCENTILES}
    counts, edges = np.histogram(op, bins=24)
    histogram = [{"bin_start": round(float(edges[i]), 2), "bin_end": round(float(edges[i + 1]), 2),
                  "count": int(counts[i])} for i in range(len(counts))]
    return MonteCarloResult(iterations=iterations, seed=seed, distributions=specs, percentiles=pct,
                            mean=round(float(op.mean()), 2), prob_negative=round(float((op < 0).mean()), 4),
                            histogram=histogram)


def monte_carlo_online(inp: OnlineSimInputs, iterations: int = 2000, seed: int = 20251010) -> MonteCarloResult:
    rng = np.random.default_rng(seed)
    n = iterations
    sigma_cac = 0.30
    cac = rng.lognormal(np.log(inp.cac), sigma_cac, n)
    price = np.clip(rng.normal(inp.selling_price, 0.05 * inp.selling_price, n), 0.5 * inp.selling_price, None)
    unit_cost = _tri(rng, 0.90 * inp.unit_cost, inp.unit_cost, 1.25 * inp.unit_cost, n)
    shipping = _tri(rng, 0.90 * inp.shipping_cost_per_order, inp.shipping_cost_per_order, 1.20 * inp.shipping_cost_per_order, n)
    ret = np.clip(_tri(rng, max(0.0, inp.return_rate_pct - 2), inp.return_rate_pct, inp.return_rate_pct + 4, n), 0, 100)
    nonpaid_base = inp.organic_orders + inp.repeat_orders
    nonpaid = nonpaid_base * rng.lognormal(0.0, 0.40, n) if nonpaid_base > 0 else np.zeros(n)

    aov = price * inp.units_per_order
    ad_orders = inp.monthly_ad_budget / cac if inp.monthly_ad_budget > 0 else np.zeros(n)
    orders = ad_orders + nonpaid
    variable = (unit_cost * inp.units_per_order + inp.packaging_cost_per_order + shipping
                + aov * inp.platform_fee_pct / 100 + aov * ret / 100)
    op = orders * (aov - variable) - inp.monthly_ad_budget - inp.fixed_costs_monthly

    specs = [
        DistributionSpec(parameter="cac", distribution="lognormal", parameters={"median": inp.cac, "sigma": sigma_cac},
                         description="Acquisition cost per ad-acquired order; right-skewed (costs can spike)."),
        DistributionSpec(parameter="selling_price", distribution="normal (truncated at 50%)",
                         parameters={"mean": inp.selling_price, "sd": round(0.05 * inp.selling_price, 2)},
                         description="Realised price after discounting."),
        DistributionSpec(parameter="unit_cost", distribution="triangular",
                         parameters={"low": round(0.9 * inp.unit_cost, 2), "mode": inp.unit_cost, "high": round(1.25 * inp.unit_cost, 2)},
                         description="Landed unit cost; skewed toward overruns."),
        DistributionSpec(parameter="shipping_cost_per_order", distribution="triangular",
                         parameters={"low": round(0.9 * inp.shipping_cost_per_order, 2), "mode": inp.shipping_cost_per_order,
                                     "high": round(1.2 * inp.shipping_cost_per_order, 2)},
                         description="Fulfilment cost per order."),
        DistributionSpec(parameter="return_rate_pct", distribution="triangular",
                         parameters={"low": max(0.0, inp.return_rate_pct - 2), "mode": inp.return_rate_pct, "high": inp.return_rate_pct + 4},
                         description="Refund/return allowance as % of order value."),
        DistributionSpec(parameter="organic_plus_repeat_orders", distribution="lognormal multiplier",
                         parameters={"base": nonpaid_base, "sigma": 0.40},
                         description="Non-paid orders (zero if the base assumption is zero)."),
    ]
    return _summarise(op, n, seed, specs)


def monte_carlo_physical(inp: PhysicalSimInputs, iterations: int = 2000, seed: int = 20251010) -> MonteCarloResult:
    rng = np.random.default_rng(seed)
    n = iterations
    footfall = inp.daily_footfall * rng.lognormal(0.0, 0.30, n)
    conv = np.clip(_tri(rng, 0.7 * inp.conversion_rate_pct, inp.conversion_rate_pct, 1.2 * inp.conversion_rate_pct, n), 0, 100)
    atv = np.clip(rng.normal(inp.average_transaction_value, 0.07 * inp.average_transaction_value, n), 0.3 * inp.average_transaction_value, None)
    cogs = np.clip(_tri(rng, inp.cogs_pct - 3, inp.cogs_pct, inp.cogs_pct + 5, n), 0, 100)
    tx = footfall * conv / 100 * inp.opening_days_per_month
    contribution = atv * (1 - (cogs + inp.card_fee_pct + inp.shrinkage_pct) / 100)
    fixed = inp.rent + inp.staff + inp.utilities + inp.marketing + inp.other_fixed
    op = tx * contribution - fixed
    specs = [
        DistributionSpec(parameter="daily_footfall", distribution="lognormal multiplier",
                         parameters={"base": inp.daily_footfall, "sigma": 0.30}, description="Visitors per opening day."),
        DistributionSpec(parameter="conversion_rate_pct", distribution="triangular",
                         parameters={"low": 0.7 * inp.conversion_rate_pct, "mode": inp.conversion_rate_pct, "high": 1.2 * inp.conversion_rate_pct},
                         description="Share of visitors who buy."),
        DistributionSpec(parameter="average_transaction_value", distribution="normal",
                         parameters={"mean": inp.average_transaction_value, "sd": 0.07 * inp.average_transaction_value},
                         description="Spend per transaction."),
        DistributionSpec(parameter="cogs_pct", distribution="triangular",
                         parameters={"low": inp.cogs_pct - 3, "mode": inp.cogs_pct, "high": inp.cogs_pct + 5},
                         description="Cost of goods as % of sales."),
    ]
    return _summarise(op, n, seed, specs)


def monte_carlo(inp: OnlineSimInputs | PhysicalSimInputs, iterations: int, seed: int) -> MonteCarloResult:
    if isinstance(inp, OnlineSimInputs):
        return monte_carlo_online(inp, iterations, seed)
    return monte_carlo_physical(inp, iterations, seed)
