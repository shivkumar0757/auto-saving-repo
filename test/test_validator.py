# Test type: unit
# Validation: transaction validation rules -- negatives, duplicates, wage check
# Command: pytest test/test_validator.py -v

from datetime import datetime

import pytest

from app.models import TransactionData
from app.utils.validator import (
    MSG_DUPLICATE,
    MSG_NEGATIVE,
    MSG_WAGE,
    validate,
)


def _txn(date_str: str, amount: float, ceiling: float = 100.0, remanent: float = 0.0):
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    return TransactionData(date=dt, amount=amount, ceiling=ceiling, remanent=remanent)


class TestValidateNegative:
    def test_negative_goes_to_invalid(self):
        txns = [_txn("2023-07-10 09:15:00", -250)]
        valid, invalid = validate(txns)
        assert len(valid) == 0
        assert len(invalid) == 1
        assert invalid[0][1] == MSG_NEGATIVE

    def test_positive_stays_valid(self):
        txns = [_txn("2023-01-15 10:30:00", 2000)]
        valid, invalid = validate(txns)
        assert len(valid) == 1
        assert len(invalid) == 0

    def test_zero_amount_is_valid(self):
        """Zero is not negative."""
        txns = [_txn("2023-01-15 10:30:00", 0)]
        valid, invalid = validate(txns)
        assert len(valid) == 1


class TestValidateDuplicate:
    def test_duplicate_date_second_goes_invalid(self):
        """First occurrence stays valid; second is a duplicate."""
        txns = [
            _txn("2023-10-12 20:15:30", 250),
            _txn("2023-10-12 20:15:30", 250),  # same date -> duplicate
        ]
        valid, invalid = validate(txns)
        assert len(valid) == 1
        assert len(invalid) == 1
        assert invalid[0][1] == MSG_DUPLICATE

    def test_different_dates_both_valid(self):
        txns = [
            _txn("2023-10-12 20:15:30", 250),
            _txn("2023-10-13 20:15:30", 250),
        ]
        valid, invalid = validate(txns)
        assert len(valid) == 2
        assert len(invalid) == 0

    def test_negative_before_duplicate_check(self):
        """Negative check comes BEFORE duplicate check."""
        txns = [
            _txn("2023-10-12 20:15:30", -250),
            _txn("2023-10-12 20:15:30", -250),  # same date, also negative
        ]
        valid, invalid = validate(txns)
        # First gets MSG_NEGATIVE; second also gets MSG_NEGATIVE (not duplicate)
        # because the negative was never added to 'seen'
        assert len(valid) == 0
        assert len(invalid) == 2
        assert invalid[0][1] == MSG_NEGATIVE
        assert invalid[1][1] == MSG_NEGATIVE


class TestValidateWage:
    def test_amount_exceeds_wage(self):
        txns = [_txn("2023-01-15 10:30:00", 60000)]
        valid, invalid = validate(txns, wage=50000, check_wage=True)
        assert len(valid) == 0
        assert invalid[0][1] == MSG_WAGE

    def test_amount_equals_wage_is_valid(self):
        txns = [_txn("2023-01-15 10:30:00", 50000)]
        valid, invalid = validate(txns, wage=50000, check_wage=True)
        assert len(valid) == 1

    def test_wage_not_checked_when_flag_off(self):
        txns = [_txn("2023-01-15 10:30:00", 60000)]
        valid, invalid = validate(txns, wage=50000, check_wage=False)
        assert len(valid) == 1
        assert len(invalid) == 0

    def test_negative_takes_priority_over_wage(self):
        """Negative amount should fail before wage check."""
        txns = [_txn("2023-01-15 10:30:00", -100)]
        valid, invalid = validate(txns, wage=50000, check_wage=True)
        assert invalid[0][1] == MSG_NEGATIVE  # not MSG_WAGE


class TestValidateAllValid:
    def test_three_valid_transactions(self):
        txns = [
            _txn("2023-01-15 10:30:00", 2000),
            _txn("2023-03-20 14:45:00", 3500),
            _txn("2023-06-10 09:15:00", 1500),
        ]
        valid, invalid = validate(txns, wage=50000, check_wage=True)
        assert len(valid) == 3
        assert len(invalid) == 0
