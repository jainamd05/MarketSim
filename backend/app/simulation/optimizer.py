"""Budget-constrained product-mix (inventory) allocation via mixed-integer linear programming.

maximise   Σ contribution_i · units_i
subject to Σ unit_cost_i · units_i ≤ inventory budget   (never exceeds known capital)
           0 ≤ units_i ≤ max_monthly_units_i,  units_i integer

If capital is unknown, exact optimisation is disabled and the missing amount is requested.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from app.schemas.analysis import OptimizationResult, ProductMixItem


def optimize_mix(items: list[ProductMixItem], inventory_budget: float | None, *, variable_cost_pct: float = 0.0,
                 currency: str = "INR") -> OptimizationResult:
    if inventory_budget is None:
        return OptimizationResult(
            status="disabled_capital_unknown",
            message="Exact capital is unknown, so inventory optimisation is disabled. Enter the capital available for "
                    "inventory (What-If → Capital) to enable it.",
        )
    usable = [i for i in items if i.unit_cost and i.target_price and i.max_monthly_units]
    if not usable:
        return OptimizationResult(status="not_applicable", budget=inventory_budget,
                                  message="Product mix lacks unit costs, prices or unit caps; nothing to optimise.")
    cost = np.array([i.unit_cost for i in usable], dtype=float)
    contrib = np.array([i.target_price * (1 - variable_cost_pct / 100) - i.unit_cost for i in usable], dtype=float)
    caps = np.array([i.max_monthly_units for i in usable], dtype=float)
    res = milp(
        c=-contrib,  # milp minimises
        constraints=[LinearConstraint(cost.reshape(1, -1), lb=0, ub=inventory_budget)],
        integrality=np.ones(len(usable)),
        bounds=Bounds(np.zeros(len(usable)), caps),
    )
    if not res.success or res.x is None:
        return OptimizationResult(status="infeasible", budget=inventory_budget, method="scipy.optimize.milp (HiGHS)",
                                  message=f"Optimiser did not find a feasible allocation: {res.message}")
    units = np.floor(res.x + 1e-6).astype(int)  # floor never pushes the cost above the budget
    total_cost = float((units * cost).sum())
    if total_cost > inventory_budget + 1e-6:  # pragma: no cover - defensive
        return OptimizationResult(status="infeasible", budget=inventory_budget, method="scipy.optimize.milp (HiGHS)",
                                  message="Rounded allocation exceeded the budget; no allocation returned.")
    allocations = [{
        "name": item.name, "focus": item.focus, "units": int(u), "unit_cost": item.unit_cost,
        "cost": round(float(u * c), 2), "contribution_per_unit": round(float(m), 2),
        "expected_contribution": round(float(u * m), 2), "cap": int(cap),
    } for item, u, c, m, cap in zip(usable, units, cost, contrib, caps)]
    return OptimizationResult(
        status="optimal", budget=inventory_budget, method="scipy.optimize.milp (HiGHS, integer units)",
        allocations=allocations, total_cost=round(total_cost, 2),
        total_expected_contribution=round(float((units * contrib).sum()), 2),
        message=(f"Allocates {currency} {total_cost:,.0f} of the {currency} {inventory_budget:,.0f} inventory budget "
                 "to maximise modelled contribution within the assumed monthly unit caps. Items with non-positive "
                 "contribution receive zero units."),
    )
