"""
Scenario planner calculation functions for Alaska Air Group FP&A dashboard.
All functions: scalars/dicts in → dict out. No I/O, no Streamlit.

Baseline inputs are quarterly figures; annual cash impact annualizes by ×4.
"""

from dataclasses import dataclass


@dataclass
class Baseline:
    """All quarterly figures pulled from the latest complete quarter."""
    fuel_cost_per_gallon: float   # $/gallon (economic, after hedging)
    fuel_gallons: float           # total gallons consumed (raw units)
    asm: float                    # available seat miles
    yield_cents: float            # cents per RPM
    load_factor: float            # % (e.g. 84.5)
    rasm: float                   # cents per ASM
    casm_ex_fuel: float           # cents per ASM, ex-fuel
    operating_income_m: float     # $M
    revenue_m: float              # $M


@dataclass
class ScenarioResult:
    delta_fuel_spend_m: float
    delta_revenue_m: float
    delta_operating_income_m: float
    delta_ebitda_m: float
    annual_cash_impact_m: float
    new_rasm: float
    new_casm: float
    new_casm_ex_fuel: float       # explicitly unchanged
    new_load_factor: float
    fuel_contribution_m: float    # sign: positive = P&L benefit
    load_factor_contribution_m: float


# Incremental passenger cost: ~25% of incremental revenue (fuel, catering, fees).
# Crew and aircraft costs are fixed at the margin.
MARGINAL_COST_RATE = 0.25


def run_scenario(
    baseline: Baseline,
    fuel_price_change_pct: float,   # e.g. +20 means fuel 20% more expensive
    load_factor_delta_pts: float,   # e.g. +2 means LF goes from 84 → 86
    hedge_ratio: float,             # 0–1; fraction of consumption locked at baseline price
) -> ScenarioResult:
    """
    Compute P&L impact of simultaneous fuel price and load factor shocks.
    Hedge ratio: hedged gallons see no price change; only unhedged gallons
    are exposed to fuel_price_change_pct.
    """
    # ── Fuel shock ─────────────────────────────────────────────────────────────
    unhedged = 1.0 - hedge_ratio
    delta_fuel_spend_m = (
        baseline.fuel_cost_per_gallon
        * baseline.fuel_gallons
        * unhedged
        * fuel_price_change_pct / 100
    ) / 1e6

    baseline_casm_fuel = (
        baseline.fuel_cost_per_gallon * baseline.fuel_gallons / baseline.asm * 100
    )  # cents per ASM
    delta_casm_fuel = (
        baseline.fuel_cost_per_gallon
        * baseline.fuel_gallons
        * unhedged
        * fuel_price_change_pct / 100
    ) / baseline.asm * 100

    # ── Load factor shock ──────────────────────────────────────────────────────
    # RASM = Yield × (LF/100), so delta_RASM = Yield × delta_LF / 100
    delta_rasm = baseline.yield_cents * load_factor_delta_pts / 100
    delta_revenue_m = delta_rasm / 100 * baseline.asm / 1e6
    delta_contribution_m = delta_revenue_m * (1 - MARGINAL_COST_RATE)

    # ── Combined ───────────────────────────────────────────────────────────────
    delta_operating_income_m = delta_contribution_m - delta_fuel_spend_m
    annual_cash_impact_m = delta_operating_income_m * 4

    return ScenarioResult(
        delta_fuel_spend_m=delta_fuel_spend_m,
        delta_revenue_m=delta_revenue_m,
        delta_operating_income_m=delta_operating_income_m,
        delta_ebitda_m=delta_operating_income_m,
        annual_cash_impact_m=annual_cash_impact_m,
        new_rasm=baseline.rasm + delta_rasm,
        new_casm=baseline.casm_ex_fuel + baseline_casm_fuel + delta_casm_fuel,
        new_casm_ex_fuel=baseline.casm_ex_fuel,
        new_load_factor=baseline.load_factor + load_factor_delta_pts,
        fuel_contribution_m=-delta_fuel_spend_m,
        load_factor_contribution_m=delta_contribution_m,
    )
