# Test type: unit + integration
# Validation: full pipeline (EP3/EP4 flows) and performance endpoint response shape
# Command: pytest test/test_pipeline.py -v

import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Expense, KPeriod, PPeriod, QPeriod
from app.pipeline import process

_client = TestClient(app)


def _expense(date_str: str, amount: float) -> Expense:
    return Expense(date=date_str, amount=amount)


def _qp(fixed: float, start: str, end: str) -> QPeriod:
    return QPeriod(fixed=fixed, start=start, end=end)


def _pp(extra: float, start: str, end: str) -> PPeriod:
    return PPeriod(extra=extra, start=start, end=end)


def _kp(start: str, end: str) -> KPeriod:
    return KPeriod(start=start, end=end)


# ---------------------------------------------------------------------------
# Basic pipeline (no periods)
# ---------------------------------------------------------------------------

class TestPipelineNoPeriods:
    def test_all_valid(self):
        expenses = [
            _expense("2023-01-15 10:30:00", 2000),
            _expense("2023-03-20 14:45:00", 3500),
        ]
        valid, invalid = process(expenses)
        assert len(valid) == 2
        assert len(invalid) == 0

    def test_negative_caught(self):
        expenses = [
            _expense("2023-01-15 10:30:00", 250),
            _expense("2023-07-10 09:15:00", -10),
        ]
        valid, invalid = process(expenses)
        assert len(valid) == 1
        assert len(invalid) == 1

    def test_duplicate_caught(self):
        expenses = [
            _expense("2023-10-12 20:15:30", 250),
            _expense("2023-10-12 20:15:30", 250),
        ]
        valid, invalid = process(expenses)
        assert len(valid) == 1
        assert len(invalid) == 1

    def test_empty(self):
        valid, invalid = process([])
        assert valid == []
        assert invalid == []


# ---------------------------------------------------------------------------
# Pipeline with q/p/k -- EP3 spec example
# ---------------------------------------------------------------------------

class TestPipelineWithPeriods:
    def _run_ep3_spec(self):
        expenses = [
            _expense("2023-02-28 15:49:20", 375),
            _expense("2023-07-15 10:30:00", 620),
            _expense("2023-10-12 20:15:30", 250),
            _expense("2023-10-12 20:15:30", 250),  # duplicate
            _expense("2023-12-17 08:09:45", -480),  # negative
        ]
        q = [_qp(0, "2023-07-01 00:00:00", "2023-07-31 23:59:59")]
        p = [_pp(30, "2023-10-01 00:00:00", "2023-12-31 23:59:59")]
        k = [_kp("2023-01-01 00:00:00", "2023-12-31 23:59:59")]
        return process(expenses, q=q, p=p, k=k, wage=50000, check_wage=False)

    def test_ep3_valid_count(self):
        valid, invalid = self._run_ep3_spec()
        assert len(valid) == 3

    def test_ep3_invalid_count(self):
        valid, invalid = self._run_ep3_spec()
        assert len(invalid) == 2

    def test_ep3_all_valid_have_inkPeriod(self):
        valid, _ = self._run_ep3_spec()
        assert all(t.inkPeriod is True for t in valid)

    def test_ep3_q_applied(self):
        """Jul 15 (620) should have remanent=0 after q match."""
        valid, _ = self._run_ep3_spec()
        jul_txn = next(t for t in valid if t.date == datetime(2023, 7, 15, 10, 30, 0))
        assert jul_txn.remanent == 0.0

    def test_ep3_p_applied(self):
        """Oct 12 (250): base remanent=50, p extra=30 -> 80"""
        valid, _ = self._run_ep3_spec()
        oct_txn = next(t for t in valid if t.date == datetime(2023, 10, 12, 20, 15, 30))
        assert oct_txn.remanent == 80.0


# ---------------------------------------------------------------------------
# EP4 spec example -- full trace
# ---------------------------------------------------------------------------

class TestPipelineEP4:
    """
    EP4 example from spec:
      transactions: 375, 620, 250, 480, -10
      q: fixed=0 for Jul
      p: extra=25 for Oct-Dec
      k1: full year (Jan-Dec)  -> sum = 25+0+75+45 = 145
      k2: Mar-Nov               -> sum = 0+75 = 75
      totalTransactionAmount   = 1725
      totalCeiling             = 1900
    """

    def _run(self):
        expenses = [
            _expense("2023-02-28 15:49:20", 375),
            _expense("2023-07-01 21:59:00", 620),
            _expense("2023-10-12 20:15:30", 250),
            _expense("2023-12-17 08:09:45", 480),
            _expense("2023-12-17 08:09:45", -10),  # negative → caught by rule 1 before duplicate check
        ]
        q = [_qp(0, "2023-07-01 00:00:00", "2023-07-31 23:59:59")]
        p = [_pp(25, "2023-10-01 08:00:00", "2023-12-31 19:59:59")]
        # No k passed -- EP4 handles k separately via sum_by_k
        return process(expenses, q=q, p=p, k=[], wage=50000, check_wage=False)

    def test_valid_count(self):
        valid, invalid = self._run()
        # -10 is invalid; all others valid
        assert len(valid) == 4
        assert len(invalid) == 1

    def test_total_transaction_amount(self):
        valid, _ = self._run()
        total = sum(t.amount for t in valid)
        assert total == pytest.approx(1725.0)

    def test_total_ceiling(self):
        valid, _ = self._run()
        total = sum(t.ceiling for t in valid)
        assert total == pytest.approx(1900.0)

    def test_feb_remanent(self):
        """Feb 28 (375): no q/p match -> remanent = 25"""
        valid, _ = self._run()
        feb = next(t for t in valid if t.date == datetime(2023, 2, 28, 15, 49, 20))
        assert feb.remanent == 25.0

    def test_jul_remanent_q_zero(self):
        """Jul 01 (620): q match fixed=0 -> remanent=0"""
        valid, _ = self._run()
        jul = next(t for t in valid if t.date == datetime(2023, 7, 1, 21, 59, 0))
        assert jul.remanent == 0.0

    def test_oct_remanent_p(self):
        """Oct 12 (250): p match extra=25 -> 50+25=75"""
        valid, _ = self._run()
        oct_txn = next(t for t in valid if t.date == datetime(2023, 10, 12, 20, 15, 30))
        assert oct_txn.remanent == 75.0

    def test_dec_remanent_p(self):
        """Dec 17 (480): p match extra=25 -> 20+25=45"""
        valid, _ = self._run()
        dec = next(t for t in valid if t.date == datetime(2023, 12, 17, 8, 9, 45))
        assert dec.remanent == 45.0


# ---------------------------------------------------------------------------
# EP5 -- Performance endpoint (integration, uses TestClient)
# ---------------------------------------------------------------------------

class TestPerformanceEndpoint:
    def test_response_shape(self):
        """Response must have exactly the three keys: time, memory, threads."""
        response = _client.get("/blackrock/challenge/v1/performance")
        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {"time", "memory", "threads"}

    def test_time_format(self):
        """time field must match YYYY-MM-DD HH:mm:ss.SSS (millisecond precision)."""
        response = _client.get("/blackrock/challenge/v1/performance")
        time_str = response.json()["time"]
        pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}$"
        assert re.match(pattern, time_str), f"Bad time format: {time_str!r}"

    def test_memory_is_string_without_unit(self):
        """memory is a string like '25.11' -- no 'MB' suffix, must be float-parseable."""
        response = _client.get("/blackrock/challenge/v1/performance")
        memory = response.json()["memory"]
        assert isinstance(memory, str)
        assert "MB" not in memory
        float(memory)  # must be parseable as float without error

    def test_threads_is_positive_int(self):
        """threads must be a positive integer."""
        response = _client.get("/blackrock/challenge/v1/performance")
        threads = response.json()["threads"]
        assert isinstance(threads, int)
        assert threads > 0
