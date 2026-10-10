"""Deterministic unit-economics formulas. No LLM is involved in any calculation here.

Online (advertising-driven) model
---------------------------------
    AOV                     = selling_price × units_per_order
    ad-acquired orders      = monthly_ad_budget / CAC
    total orders            = ad-acquired + organic + repeat
    revenue                 = total orders × AOV
    variable cost / order   = product cost + packaging + shipping + platform fee + refund allowance
    contribution / order    = AOV − variable cost / order
    operating result        = total orders × contribution / order − ad budget − fixed costs
    break-even orders       = ceil((ad budget + fixed costs) / contribution)   (only if contribution > 0)

The advertising budget is subtracted once, as a total. CAC is only used to convert
the budget into modelled ad-acquired orders and is never deducted per order again.
"""
from __future__ import annotations

import math

from app.schemas.analysis import CapitalCheck, FinancialResult, OnlineSimInputs, PhysicalSimInputs

_EPS = 1e-9


def _r(x: float, nd: int = 2) -> float:
    return round(float(x), nd)


def _capital_check(available: float | None, initial_investment: float | None, currency: str) -> CapitalCheck:
    if available is None:
        return CapitalCheck(status="unknown", available=None, required=initial_investment,
                            note="Available capital is unknown; investment cannot be checked against it.")
    if initial_investment is None:
        return CapitalCheck(status="unknown", available=available, required=None,
                            note="Initial investment (inventory + setup) is not specified.")
    status = "within" if initial_investment <= available + _EPS else "exceeds"
    note = (f"Initial investment {currency} {initial_investment:,.0f} is "
            f"{'within' if status == 'within' else 'ABOVE'} available capital {currency} {available:,.0f}.")
    return CapitalCheck(status=status, available=available, required=initial_investment, note=note)


def _runway(operating: float, available: float | None, initial_investment: float | None) -> tuple[float | None, str]:
    if operating >= 0:
        return None, "Operating result is not negative in this scenario, so there is no monthly cash burn."
    if available is None:
        return None, "Cash runway needs the available capital, which is unknown."
    remaining = available - (initial_investment or 0.0)
    if remaining <= 0:
        return 0.0, "No capital remains after the initial investment."
    months = remaining / -operating
    return _r(months, 1), (f"Approximation: capital remaining after initial investment divided by the monthly loss "
                           f"({months:.1f} months). Ignores working-capital timing and taxes.")


def _break_even(fixed_like: float, contribution: float, current: float, label: str) -> tuple[int | None, str, str]:
    if contribution <= _EPS:
        return None, "not_achievable_negative_contribution", (
            f"Each {label} has zero or negative contribution, so no volume reaches break-even.")
    needed = math.ceil(fixed_like / contribution - 1e-9) if fixed_like > 0 else 0
    status = "already_met" if current + 1e-9 >= needed else "achievable"
    return needed, status, f"{needed:,} {label}s per month cover the monthly advertising and fixed costs."


def simulate_online(inp: OnlineSimInputs) -> FinancialResult:
    aov = inp.selling_price * inp.units_per_order
    ad_orders = inp.monthly_ad_budget / inp.cac if inp.monthly_ad_budget > 0 else 0.0
    total_orders = ad_orders + inp.organic_orders + inp.repeat_orders

    product_cost = inp.unit_cost * inp.units_per_order
    platform_fee = aov * inp.platform_fee_pct / 100
    refund_allowance = aov * inp.return_rate_pct / 100
    variable = product_cost + inp.packaging_cost_per_order + inp.shipping_cost_per_order + platform_fee + refund_allowance
    contribution = aov - variable

    revenue = total_orders * aov
    total_contribution = total_orders * contribution
    operating = total_contribution - inp.monthly_ad_budget - inp.fixed_costs_monthly

    be, be_status, be_note = _break_even(inp.monthly_ad_budget + inp.fixed_costs_monthly, contribution, total_orders, "order")
    runway, runway_note = _runway(operating, inp.available_capital, inp.initial_investment)

    warnings: list[str] = []
    if contribution <= 0:
        warnings.append("Negative contribution: every order loses money before advertising and fixed costs.")
    if inp.monthly_ad_budget > 0 and inp.cac >= aov:
        warnings.append("CAC is at or above the order value; first orders cannot pay back acquisition.")
    if ad_orders and (inp.organic_orders + inp.repeat_orders) == 0:
        warnings.append("All modelled orders are ad-acquired; organic and repeat orders are assumed to be zero.")

    return FinancialResult(
        model="online", currency=inp.currency,
        orders={"ad_acquired": _r(ad_orders, 1), "organic": _r(inp.organic_orders, 1),
                "repeat": _r(inp.repeat_orders, 1), "total": _r(total_orders, 1)},
        average_order_value=_r(aov), revenue=_r(revenue),
        cost_breakdown={
            "product_cost": _r(total_orders * product_cost),
            "packaging": _r(total_orders * inp.packaging_cost_per_order),
            "fulfilment_shipping": _r(total_orders * inp.shipping_cost_per_order),
            "platform_payment_fees": _r(total_orders * platform_fee),
            "returns_refund_allowance": _r(total_orders * refund_allowance),
            "advertising": _r(inp.monthly_ad_budget),
            "fixed_operating": _r(inp.fixed_costs_monthly),
        },
        variable_cost_per_order=_r(variable), contribution_per_order=_r(contribution),
        contribution_margin_pct=_r(contribution / aov * 100 if aov else 0.0, 1),
        total_contribution=_r(total_contribution), operating_result=_r(operating),
        break_even_orders=be, break_even_status=be_status, break_even_note=be_note,
        runway_months=runway, runway_note=runway_note,
        capital_check=_capital_check(inp.available_capital, inp.initial_investment, inp.currency),
        warnings=warnings,
    )


def simulate_physical(inp: PhysicalSimInputs) -> FinancialResult:
    transactions = inp.daily_footfall * inp.conversion_rate_pct / 100 * inp.opening_days_per_month
    atv = inp.average_transaction_value
    cogs = atv * inp.cogs_pct / 100
    card = atv * inp.card_fee_pct / 100
    shrink = atv * inp.shrinkage_pct / 100
    variable = cogs + card + shrink
    contribution = atv - variable
    fixed = inp.rent + inp.staff + inp.utilities + inp.marketing + inp.other_fixed
    revenue = transactions * atv
    total_contribution = transactions * contribution
    operating = total_contribution - fixed

    be, be_status, be_note = _break_even(fixed, contribution, transactions, "transaction")
    if be is not None and inp.conversion_rate_pct > 0:
        daily = be / (inp.conversion_rate_pct / 100 * inp.opening_days_per_month)
        be_note += f" At {inp.conversion_rate_pct:g}% conversion that is ≈{daily:,.0f} visitors per opening day."
    runway, runway_note = _runway(operating, inp.available_capital, inp.initial_investment)
    warnings = []
    if contribution <= 0:
        warnings.append("Negative contribution: each transaction loses money before fixed costs.")
    return FinancialResult(
        model="physical", currency=inp.currency,
        orders={"transactions": _r(transactions, 1), "total": _r(transactions, 1)},
        average_order_value=_r(atv), revenue=_r(revenue),
        cost_breakdown={
            "cost_of_goods": _r(transactions * cogs), "card_fees": _r(transactions * card),
            "shrinkage": _r(transactions * shrink), "rent": _r(inp.rent), "staff": _r(inp.staff),
            "utilities": _r(inp.utilities), "marketing": _r(inp.marketing), "other_fixed": _r(inp.other_fixed),
        },
        variable_cost_per_order=_r(variable), contribution_per_order=_r(contribution),
        contribution_margin_pct=_r(contribution / atv * 100 if atv else 0.0, 1),
        total_contribution=_r(total_contribution), operating_result=_r(operating),
        break_even_orders=be, break_even_status=be_status, break_even_note=be_note,
        runway_months=runway, runway_note=runway_note,
        capital_check=_capital_check(inp.available_capital, inp.initial_investment, inp.currency),
        warnings=warnings,
    )


def simulate(inp: OnlineSimInputs | PhysicalSimInputs) -> FinancialResult:
    return simulate_online(inp) if isinstance(inp, OnlineSimInputs) else simulate_physical(inp)
