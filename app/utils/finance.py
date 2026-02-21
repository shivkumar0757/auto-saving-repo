"""
utils/finance.py -- Financial calculations for returns endpoints.

calc_tax(income)                    -> progressive slab tax (simplified regime)
nps_deduction(invested, annual_inc) -> min(invested, 10% of annual_inc, 200000)
calc_returns(k_sums, age, wage, inflation, config) -> list of SavingResult dicts

Config dict pattern (Strategy pattern):
  NPS_CONFIG   = {"rate": 0.0711, "use_tax": True}
  INDEX_CONFIG = {"rate": 0.1449, "use_tax": False}

Rules:
  t            = max(60 - age, 5)          -- never let t be zero
  future_value = principal * (1 + r)^t
  real_value   = future_value / (1 + inflation/100)^t
  profit       = real_value - principal
  wage input is monthly; annual_income = wage * 12
"""
from __future__ import annotations

from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Tax slabs -- simplified new regime (from HTML spec)
# ---------------------------------------------------------------------------

def calc_tax(income: float) -> float:
    """
    Progressive slab tax under the simplified new regime.

      <= 7,00,000  ->  0
      <= 10,00,000 ->  (income - 7,00,000) * 0.10
      <= 12,00,000 ->  30,000 + (income - 10,00,000) * 0.15
      <= 15,00,000 ->  60,000 + (income - 12,00,000) * 0.20
      > 15,00,000 ->  1,20,000 + (income - 15,00,000) * 0.30
    """
    if income <= 700_000:
        return 0.0
    elif income <= 1_000_000:
        return (income - 700_000) * 0.10
    elif income <= 1_200_000:
        return 30_000 + (income - 1_000_000) * 0.15
    elif income <= 1_500_000:
        return 60_000 + (income - 1_200_000) * 0.20
    else:
        return 120_000 + (income - 1_500_000) * 0.30


# ---------------------------------------------------------------------------
# NPS deduction
# ---------------------------------------------------------------------------

def nps_deduction(invested: float, annual_income: float) -> float:
    """
    Eligible NPS deduction:
      min(invested, 10% of annual_income, INR2,00,000)
    """
    return min(invested, 0.10 * annual_income, 200_000.0)


# ---------------------------------------------------------------------------
# Shared returns calculator (NPS + Index Fund via config dict)
# ---------------------------------------------------------------------------

NPS_CONFIG: dict[str, Any] = {"rate": 0.0711, "use_tax": True}
INDEX_CONFIG: dict[str, Any] = {"rate": 0.1449, "use_tax": False}


def calc_returns(
    k_sums: list[dict],
    age: int,
    wage: float,
    inflation: float,
    config: dict[str, Any],
) -> list[dict]:
    """
    Calculate compound + inflation-adjusted returns for each k window.

    k_sums  -- list of {"start": datetime, "end": datetime, "amount": float}
    age     -- investor age in years
    wage    -- monthly wage in INR
    inflation -- annual inflation rate in %
    config  -- {"rate": float, "use_tax": bool}

    Returns list of dicts matching SavingResult shape.
    """
    if not k_sums:
        return []

    rate = config["rate"]
    use_tax = config["use_tax"]

    # t = years to retirement, minimum 5
    t = max(60 - age, 5)

    # annual income for NPS tax benefit
    annual_income = wage * 12.0

    # Vectorised compound interest + inflation adjustment
    principal = np.array([ks["amount"] for ks in k_sums], dtype=np.float64)
    future_value = principal * (1.0 + rate) ** t
    real_value = future_value / (1.0 + inflation / 100.0) ** t
    profit_arr = real_value - principal

    results = []
    for i, ks in enumerate(k_sums):
        p_val = float(principal[i])
        profit = round(float(profit_arr[i]), 2)

        tax_benefit = 0.0
        if use_tax:
            deduction = nps_deduction(p_val, annual_income)
            tax_before = calc_tax(annual_income)
            tax_after = calc_tax(annual_income - deduction)
            tax_benefit = round(tax_before - tax_after, 2)

        results.append(
            {
                "start": ks["start"],
                "end": ks["end"],
                "amount": round(p_val, 2),
                "profit": profit,
                "taxBenefit": tax_benefit,
            }
        )

    return results
