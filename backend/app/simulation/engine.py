"""Single entry point used by the Quantitative Simulation Agent and the What-If API."""
from __future__ import annotations

from app.schemas.analysis import OnlineSimInputs, PhysicalSimInputs, ProductMixItem, StrategySimulation
from app.simulation.finance import simulate
from app.simulation.montecarlo import monte_carlo
from app.simulation.optimizer import optimize_mix
from app.simulation.scenarios import run_scenarios


def variable_cost_pct(inp: OnlineSimInputs | PhysicalSimInputs) -> float:
    if isinstance(inp, OnlineSimInputs):
        return inp.platform_fee_pct + inp.return_rate_pct
    return inp.card_fee_pct + inp.shrinkage_pct


def run_simulation(strategy_key: str, revision: int, inputs: OnlineSimInputs | PhysicalSimInputs,
                   product_mix: list[ProductMixItem], *, iterations: int, seed: int,
                   inventory_budget: float | None = None) -> StrategySimulation:
    budget = inventory_budget
    if budget is None and inputs.available_capital is not None:
        budget = inputs.available_capital
    if budget is not None and inputs.available_capital is not None:
        budget = min(budget, inputs.available_capital)  # never allocate beyond known capital
    return StrategySimulation(
        strategy_key=strategy_key, revision=revision, inputs=inputs.model_dump(), base=simulate(inputs),
        scenarios=run_scenarios(inputs), monte_carlo=monte_carlo(inputs, iterations, seed),
        optimization=optimize_mix(product_mix, budget, variable_cost_pct=variable_cost_pct(inputs),
                                  currency=inputs.currency),
    )
