# Test type: unit
# Validation: q/p period override and addition, k period tagging and grouping
# Command: pytest test/test_periods.py -v

from datetime import datetime

import pytest

from app.models import KPeriod, PPeriod, QPeriod, TransactionData
from app.utils.periods import apply_p, apply_q, build_tree, sum_by_k, tag_k


def _txn(date_str: str, amount: float = 100.0, remanent: float = 50.0):
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    return TransactionData(date=dt, amount=amount, ceiling=amount + remanent, remanent=remanent)


def _qp(fixed: float, start: str, end: str) -> QPeriod:
    return QPeriod(fixed=fixed, start=start, end=end)


def _pp(extra: float, start: str, end: str) -> PPeriod:
    return PPeriod(extra=extra, start=start, end=end)


def _kp(start: str, end: str) -> KPeriod:
    return KPeriod(start=start, end=end)


# ---------------------------------------------------------------------------
# apply_q tests
# ---------------------------------------------------------------------------

class TestApplyQ:
    def test_single_match_overrides_remanent(self):
        txn = _txn("2023-07-15 10:30:00", remanent=80.0)
        q = [_qp(fixed=0.0, start="2023-07-01 00:00:00", end="2023-07-31 23:59:59")]
        tree = build_tree(q)
        result = apply_q([txn], tree)
        assert result[0].remanent == 0.0

    def test_q_fixed_zero_not_skipped(self):
        """q.fixed=0 still overrides -- transaction is valid with remanent=0."""
        txn = _txn("2023-07-01 21:59:00", amount=620, remanent=80.0)
        q = [_qp(fixed=0.0, start="2023-07-01 00:00:00", end="2023-07-31 23:59:59")]
        tree = build_tree(q)
        result = apply_q([txn], tree)
        assert result[0].remanent == 0.0

    def test_no_match_leaves_remanent_unchanged(self):
        txn = _txn("2023-02-28 15:49:20", remanent=25.0)
        q = [_qp(fixed=0.0, start="2023-07-01 00:00:00", end="2023-07-31 23:59:59")]
        tree = build_tree(q)
        result = apply_q([txn], tree)
        assert result[0].remanent == 25.0

    def test_multiple_q_latest_start_wins(self):
        """When multiple q periods match, the one with latest start wins."""
        txn = _txn("2023-07-15 10:30:00", remanent=80.0)
        q = [
            _qp(fixed=10.0, start="2023-07-01 00:00:00", end="2023-07-31 23:59:59"),
            _qp(fixed=99.0, start="2023-07-10 00:00:00", end="2023-07-31 23:59:59"),  # later start
        ]
        tree = build_tree(q)
        result = apply_q([txn], tree)
        assert result[0].remanent == 99.0

    def test_multiple_q_tie_first_in_list_wins(self):
        """Same start date -> first in the original list wins."""
        txn = _txn("2023-07-15 10:30:00", remanent=80.0)
        q = [
            _qp(fixed=42.0, start="2023-07-01 00:00:00", end="2023-07-31 23:59:59"),  # idx 0
            _qp(fixed=99.0, start="2023-07-01 00:00:00", end="2023-07-31 23:59:59"),  # idx 1
        ]
        tree = build_tree(q)
        result = apply_q([txn], tree)
        assert result[0].remanent == 42.0  # first in list wins on tie

    def test_q_on_boundary_inclusive_end(self):
        """Inclusive end date: transaction exactly at end should still match."""
        txn = _txn("2023-07-31 23:59:59", remanent=80.0)
        q = [_qp(fixed=5.0, start="2023-07-01 00:00:00", end="2023-07-31 23:59:59")]
        tree = build_tree(q)
        result = apply_q([txn], tree)
        assert result[0].remanent == 5.0


# ---------------------------------------------------------------------------
# apply_p tests
# ---------------------------------------------------------------------------

class TestApplyP:
    def test_single_match_adds_extra(self):
        txn = _txn("2023-10-12 20:15:30", amount=250, remanent=50.0)
        p = [_pp(extra=25.0, start="2023-10-01 00:00:00", end="2023-12-31 23:59:59")]
        tree = build_tree(p)
        result = apply_p([txn], tree)
        assert result[0].remanent == 75.0

    def test_no_match_leaves_remanent_unchanged(self):
        txn = _txn("2023-02-28 15:49:20", remanent=25.0)
        p = [_pp(extra=25.0, start="2023-10-01 00:00:00", end="2023-12-31 23:59:59")]
        tree = build_tree(p)
        result = apply_p([txn], tree)
        assert result[0].remanent == 25.0

    def test_multiple_p_all_summed(self):
        """ALL matching p extras are summed."""
        txn = _txn("2023-10-12 20:15:30", remanent=50.0)
        p = [
            _pp(extra=10.0, start="2023-10-01 00:00:00", end="2023-12-31 23:59:59"),
            _pp(extra=15.0, start="2023-09-01 00:00:00", end="2023-11-30 23:59:59"),
        ]
        tree = build_tree(p)
        result = apply_p([txn], tree)
        assert result[0].remanent == 75.0  # 50 + 10 + 15

    def test_p_on_boundary_inclusive_end(self):
        """Inclusive end date: transaction exactly at end should match."""
        txn = _txn("2023-12-31 23:59:59", remanent=20.0)
        p = [_pp(extra=25.0, start="2023-10-01 00:00:00", end="2023-12-31 23:59:59")]
        tree = build_tree(p)
        result = apply_p([txn], tree)
        assert result[0].remanent == 45.0


# ---------------------------------------------------------------------------
# q + p stacking tests
# ---------------------------------------------------------------------------

class TestQPStacking:
    def test_q_then_p_stacks(self):
        """
        Transaction matches both q and p:
        final_remanent = q.fixed + sum(p.extra)
        """
        txn = _txn("2023-10-12 20:15:30", amount=250, remanent=50.0)
        q = [_qp(fixed=0.0, start="2023-10-01 00:00:00", end="2023-10-31 23:59:59")]
        p = [_pp(extra=25.0, start="2023-10-01 00:00:00", end="2023-12-31 23:59:59")]
        q_tree = build_tree(q)
        p_tree = build_tree(p)
        apply_q([txn], q_tree)   # remanent -> 0
        apply_p([txn], p_tree)   # remanent += 25
        assert txn.remanent == 25.0

    def test_q_non_zero_then_p_stacks(self):
        txn = _txn("2023-10-12 20:15:30", amount=250, remanent=50.0)
        q = [_qp(fixed=10.0, start="2023-10-01 00:00:00", end="2023-10-31 23:59:59")]
        p = [_pp(extra=30.0, start="2023-10-01 00:00:00", end="2023-12-31 23:59:59")]
        q_tree = build_tree(q)
        p_tree = build_tree(p)
        apply_q([txn], q_tree)   # remanent -> 10
        apply_p([txn], p_tree)   # remanent += 30
        assert txn.remanent == 40.0


# ---------------------------------------------------------------------------
# tag_k tests
# ---------------------------------------------------------------------------

class TestTagK:
    def test_in_k_period_tagged(self):
        txn = _txn("2023-02-28 15:49:20", remanent=25.0)
        k = [_kp("2023-01-01 00:00:00", "2023-12-31 23:59:59")]
        result = tag_k([txn], k)
        assert len(result) == 1
        assert result[0].inkPeriod is True

    def test_outside_all_k_dropped_silently(self):
        txn = _txn("2022-12-31 23:59:59", remanent=25.0)
        k = [_kp("2023-01-01 00:00:00", "2023-12-31 23:59:59")]
        result = tag_k([txn], k)
        assert len(result) == 0

    def test_in_multiple_k_appears_once_in_valid(self):
        """Transaction in multiple k windows is only returned once in tag_k."""
        txn = _txn("2023-07-15 10:30:00", remanent=25.0)
        k = [
            _kp("2023-01-01 00:00:00", "2023-12-31 23:59:59"),
            _kp("2023-03-01 00:00:00", "2023-11-30 23:59:59"),
        ]
        result = tag_k([txn], k)
        assert len(result) == 1
        assert result[0].inkPeriod is True

    def test_empty_k_drops_all(self):
        txn = _txn("2023-07-15 10:30:00", remanent=25.0)
        result = tag_k([txn], [])
        assert len(result) == 0


# ---------------------------------------------------------------------------
# sum_by_k tests
# ---------------------------------------------------------------------------

class TestSumByK:
    def test_single_k_full_year(self):
        """EP4 example: k1 spans full year, sum = 25+0+75+45 = 145"""
        txns = [
            _txn("2023-02-28 15:49:20", remanent=25.0),
            _txn("2023-07-01 21:59:00", remanent=0.0),
            _txn("2023-10-12 20:15:30", remanent=75.0),
            _txn("2023-12-17 08:09:45", remanent=45.0),
        ]
        k = [_kp("2023-01-01 00:00:00", "2023-12-31 23:59:59")]
        result = sum_by_k(txns, k)
        assert len(result) == 1
        assert result[0]["amount"] == 145.0

    def test_k2_subset(self):
        """EP4 example: k2 is Mar-Nov. Only Jul and Oct fall in it = 0+75 = 75"""
        txns = [
            _txn("2023-02-28 15:49:20", remanent=25.0),  # Feb -- outside Mar-Nov
            _txn("2023-07-01 21:59:00", remanent=0.0),   # Jul -- inside
            _txn("2023-10-12 20:15:30", remanent=75.0),  # Oct -- inside
            _txn("2023-12-17 08:09:45", remanent=45.0),  # Dec -- outside
        ]
        k = [_kp("2023-03-01 00:00:00", "2023-11-30 23:59:59")]
        result = sum_by_k(txns, k)
        assert result[0]["amount"] == 75.0

    def test_two_k_periods_independent(self):
        """Transactions are summed independently per k window."""
        txns = [
            _txn("2023-02-28 15:49:20", remanent=25.0),
            _txn("2023-07-01 21:59:00", remanent=0.0),
            _txn("2023-10-12 20:15:30", remanent=75.0),
            _txn("2023-12-17 08:09:45", remanent=45.0),
        ]
        k = [
            _kp("2023-01-01 00:00:00", "2023-12-31 23:59:59"),
            _kp("2023-03-01 00:00:00", "2023-11-30 23:59:59"),
        ]
        result = sum_by_k(txns, k)
        assert result[0]["amount"] == 145.0
        assert result[1]["amount"] == 75.0

    def test_output_order_matches_input_k_order(self):
        """savingsByDates order must match k input order."""
        txns = [_txn("2023-06-15 10:00:00", remanent=50.0)]
        k = [
            _kp("2023-03-01 00:00:00", "2023-11-30 23:59:59"),  # k2 first
            _kp("2023-01-01 00:00:00", "2023-12-31 23:59:59"),  # k1 second
        ]
        result = sum_by_k(txns, k)
        # k2 first in input -> first in result
        assert result[0]["start"] == datetime(2023, 3, 1, 0, 0, 0)
        assert result[1]["start"] == datetime(2023, 1, 1, 0, 0, 0)
