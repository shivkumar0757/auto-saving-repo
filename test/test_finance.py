# Test type: unit
# Validation: tax slabs, NPS deduction cap, compound returns, inflation adjustment
# Command: pytest test/test_finance.py -v

from datetime import datetime

import pytest

from app.utils.finance import (
    INDEX_CONFIG,
    NPS_CONFIG,
    calc_returns,
    calc_tax,
    nps_deduction,
)


# ---------------------------------------------------------------------------
# calc_tax tests -- progressive slab
# ---------------------------------------------------------------------------

class TestCalcTax:
    def test_below_threshold(self):
        """income <= 7L -> tax = 0"""
        assert calc_tax(600_000) == 0.0
        assert calc_tax(700_000) == 0.0

    def test_slab_7l_to_10l(self):
        """income = 8L -> (8L-7L) * 0.10 = 10000"""
        assert calc_tax(800_000) == 10_000.0

    def test_slab_10l_boundary(self):
        """income = 10L -> (10L-7L) * 0.10 = 30000"""
        assert calc_tax(1_000_000) == 30_000.0

    def test_slab_10l_to_12l(self):
        """income = 11L -> 30000 + (11L-10L)*0.15 = 30000 + 15000 = 45000"""
        assert calc_tax(1_100_000) == 45_000.0

    def test_slab_12l_to_15l(self):
        """income = 13L -> 60000 + (13L-12L)*0.20 = 60000 + 20000 = 80000"""
        assert calc_tax(1_300_000) == 80_000.0

    def test_slab_above_15l(self):
        """income = 16L -> 120000 + (16L-15L)*0.30 = 120000+30000=150000"""
        assert calc_tax(1_600_000) == 150_000.0

    def test_zero_income(self):
        assert calc_tax(0) == 0.0


# ---------------------------------------------------------------------------
# nps_deduction tests
# ---------------------------------------------------------------------------

class TestNpsDeduction:
    def test_invested_is_smallest(self):
        """invested < 10% of income and < 2L -> deduction = invested"""
        result = nps_deduction(145, 600_000)
        assert result == 145.0

    def test_ten_percent_cap(self):
        """If 10% of annual income is smallest, use that."""
        # 10% of 100k = 10k; invested = 50k; cap 2L
        result = nps_deduction(50_000, 100_000)
        assert result == 10_000.0

    def test_200k_cap(self):
        """If invested > 2L and income * 10% > 2L, deduction = 2L."""
        result = nps_deduction(300_000, 5_000_000)
        assert result == 200_000.0

    def test_all_below_2l(self):
        """invested = 1000, annual_income = 1_200_000 -> 10% = 120k -> min is 1000"""
        result = nps_deduction(1_000, 1_200_000)
        assert result == 1_000.0


# ---------------------------------------------------------------------------
# calc_returns tests
# ---------------------------------------------------------------------------

def _ksums(amounts):
    """Helper: build k_sums list from a list of amounts."""
    base = datetime(2023, 1, 1)
    end = datetime(2023, 12, 31)
    return [{"start": base, "end": end, "amount": a} for a in amounts]


class TestCalcReturns:
    def test_nps_spec_example_k1(self):
        """
        Spec example: P=145, age=29, wage=50000, inflation=5.5, NPS
        t = 60-29 = 31
        A     = 145 * (1.0711)^31
        A_real = A / (1.055)^31
        profit = A_real - 145 ~= 86.88
        taxBenefit = 0 (income 600k < 7L threshold)
        """
        k_sums = _ksums([145.0])
        results = calc_returns(k_sums, age=29, wage=50_000, inflation=5.5, config=NPS_CONFIG)
        assert len(results) == 1
        assert results[0]["profit"] == pytest.approx(86.88, abs=0.01)
        assert results[0]["taxBenefit"] == 0.0

    def test_nps_spec_example_k2(self):
        """
        Spec example: P=75, age=29, wage=50000, inflation=5.5, NPS
        profit ~= 44.94
        """
        k_sums = _ksums([75.0])
        results = calc_returns(k_sums, age=29, wage=50_000, inflation=5.5, config=NPS_CONFIG)
        assert results[0]["profit"] == pytest.approx(44.94, abs=0.01)
        assert results[0]["taxBenefit"] == 0.0

    def test_index_tax_benefit_always_zero(self):
        """Index fund: taxBenefit must always be 0."""
        k_sums = _ksums([1000.0])
        results = calc_returns(k_sums, age=29, wage=500_000, inflation=5.5, config=INDEX_CONFIG)
        assert results[0]["taxBenefit"] == 0.0

    def test_t_floor_age_60(self):
        """age=60 -> t = max(0, 5) = 5."""
        k_sums = _ksums([1000.0])
        r60 = calc_returns(k_sums, age=60, wage=50_000, inflation=5.5, config=NPS_CONFIG)
        r65 = calc_returns(k_sums, age=65, wage=50_000, inflation=5.5, config=NPS_CONFIG)
        # Both should produce the same result (t=5 for both)
        assert r60[0]["profit"] == r65[0]["profit"]

    def test_t_age_younger(self):
        """age=29 -> t=31; more years -> more profit than age=55 (t=5)."""
        k_sums = _ksums([1000.0])
        r29 = calc_returns(k_sums, age=29, wage=50_000, inflation=5.5, config=NPS_CONFIG)
        r55 = calc_returns(k_sums, age=55, wage=50_000, inflation=5.5, config=NPS_CONFIG)
        assert r29[0]["profit"] > r55[0]["profit"]

    def test_nps_tax_benefit_above_threshold(self):
        """
        wage=100000/mo -> annual=1200000 -> tax(1200000) = 30000+(1200000-1000000)*0.15=60000
        invested=5000 -> deduction=min(5000, 120000, 200000)=5000
        tax(1200000-5000) = 30000+(1195000-1000000)*0.15 = 30000+29250 = 59250
        taxBenefit = 60000 - 59250 = 750
        """
        k_sums = _ksums([5000.0])
        results = calc_returns(
            k_sums, age=29, wage=100_000, inflation=5.5, config=NPS_CONFIG
        )
        assert results[0]["taxBenefit"] == pytest.approx(750.0, abs=1.0)

    def test_empty_k_sums(self):
        result = calc_returns([], age=29, wage=50_000, inflation=5.5, config=NPS_CONFIG)
        assert result == []

    def test_compound_interest_correctness(self):
        """Manual check: P=100, r=7.11%, t=10, inflation=0 -> profit = 100*(1.0711^10 - 1)"""
        import math
        k_sums = _ksums([100.0])
        results = calc_returns(k_sums, age=50, wage=50_000, inflation=0.0, config=NPS_CONFIG)
        expected = 100.0 * ((1.0711 ** 10) - 1.0)
        assert results[0]["profit"] == pytest.approx(expected, abs=0.01)
