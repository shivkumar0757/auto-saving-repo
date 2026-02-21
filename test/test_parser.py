# Test type: unit
# Validation: ceiling and remanent calculation via numpy vectorized parser
# Command: pytest test/test_parser.py -v

from datetime import datetime

import numpy as np
import pytest

from app.models import Expense
from app.utils.parser import ceiling, parse, remanent


# ---------------------------------------------------------------------------
# ceiling() tests
# ---------------------------------------------------------------------------

class TestCeiling:
    def test_normal_case(self):
        arr = np.array([250.0])
        assert ceiling(arr)[0] == 300.0

    def test_exact_multiple(self):
        """Exact multiple of 100: ceil(300/100)*100 = 300, not 400."""
        arr = np.array([300.0])
        assert ceiling(arr)[0] == 300.0

    def test_large_amount(self):
        arr = np.array([1519.0])
        assert ceiling(arr)[0] == 1600.0

    def test_375(self):
        arr = np.array([375.0])
        assert ceiling(arr)[0] == 400.0

    def test_620(self):
        arr = np.array([620.0])
        assert ceiling(arr)[0] == 700.0

    def test_480(self):
        arr = np.array([480.0])
        assert ceiling(arr)[0] == 500.0

    def test_bulk(self):
        arr = np.array([250.0, 375.0, 620.0, 480.0])
        result = ceiling(arr)
        assert list(result) == [300.0, 400.0, 700.0, 500.0]

    def test_negative_amount(self):
        """Negative amounts: ceiling should still work mathematically."""
        arr = np.array([-10.0])
        # ceil(-10/100)*100 = ceil(-0.1)*100 = 0*100 = 0
        assert ceiling(arr)[0] == 0.0


# ---------------------------------------------------------------------------
# remanent() tests
# ---------------------------------------------------------------------------

class TestRemanent:
    def test_basic(self):
        amounts = np.array([250.0])
        ceilings = np.array([300.0])
        assert remanent(amounts, ceilings)[0] == 50.0

    def test_exact_multiple_remanent_is_zero(self):
        """Exact multiple of 100 -> remanent must be 0."""
        amounts = np.array([300.0])
        ceilings = np.array([300.0])
        assert remanent(amounts, ceilings)[0] == 0.0

    def test_375(self):
        amounts = np.array([375.0])
        ceilings = np.array([400.0])
        assert remanent(amounts, ceilings)[0] == 25.0

    def test_480(self):
        amounts = np.array([480.0])
        ceilings = np.array([500.0])
        assert remanent(amounts, ceilings)[0] == 20.0


# ---------------------------------------------------------------------------
# parse() tests (integration of ceiling + remanent)
# ---------------------------------------------------------------------------

class TestParse:
    def _make_expense(self, date_str: str, amount: float) -> Expense:
        return Expense(date=date_str, amount=amount)

    def test_parse_250(self):
        expenses = [self._make_expense("2023-10-12 20:15:30", 250)]
        txns = parse(expenses)
        assert len(txns) == 1
        assert txns[0].ceiling == 300.0
        assert txns[0].remanent == 50.0

    def test_parse_exact_multiple(self):
        """amount=300 -> ceiling=300, remanent=0"""
        expenses = [self._make_expense("2023-10-12 20:15:30", 300)]
        txns = parse(expenses)
        assert txns[0].ceiling == 300.0
        assert txns[0].remanent == 0.0

    def test_parse_480(self):
        expenses = [self._make_expense("2023-12-17 08:09:45", 480)]
        txns = parse(expenses)
        assert txns[0].ceiling == 500.0
        assert txns[0].remanent == 20.0

    def test_parse_empty(self):
        assert parse([]) == []

    def test_parse_preserves_date(self):
        expenses = [self._make_expense("2023-02-28 15:49:20", 375)]
        txns = parse(expenses)
        assert txns[0].date == datetime(2023, 2, 28, 15, 49, 20)

    def test_parse_multiple(self):
        expenses = [
            self._make_expense("2023-10-12 20:15:30", 250),
            self._make_expense("2023-02-28 15:49:20", 375),
            self._make_expense("2023-07-01 21:59:00", 620),
            self._make_expense("2023-12-17 08:09:45", 480),
        ]
        txns = parse(expenses)
        assert [t.ceiling for t in txns] == [300.0, 400.0, 700.0, 500.0]
        assert [t.remanent for t in txns] == [50.0, 25.0, 80.0, 20.0]
