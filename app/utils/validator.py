"""
utils/validator.py -- Transaction validation.

validate(transactions, wage=None, check_wage=False)
  Rule order (first failing rule wins per transaction):
    1. negative amount  -> invalid E013
    2. duplicate date   -> invalid E014  (key = date only, per spec)
    3. amount > wage    -> invalid E015  (only when check_wage=True, i.e. EP2)

  Returns: (valid: list[TransactionData], invalid: list[tuple[TransactionData, str]])

Note on duplicate key:
  The spec states timestamps are globally unique (t_i != t_j), so date alone
  is the duplicate key. We use a set of datetime objects -- O(1) lookup.
"""
from __future__ import annotations

from datetime import datetime

from app.models import TransactionData

MSG_NEGATIVE = "Negative amounts are not allowed"
MSG_DUPLICATE = "Duplicate transaction"
MSG_WAGE = "Amount exceeds monthly wage"


def validate(
    transactions: list[TransactionData],
    wage: float | None = None,
    check_wage: bool = False,
) -> tuple[list[TransactionData], list[tuple[TransactionData, str]]]:
    """
    Validate transactions in one pass using a hash set for duplicate detection.

    Returns:
        valid   -- list of TransactionData that passed all checks
        invalid -- list of (TransactionData, error_message) for failed ones
    """
    valid: list[TransactionData] = []
    invalid: list[tuple[TransactionData, str]] = []
    seen: set[datetime] = set()  # set of datetime objects (date-only key per spec)

    for txn in transactions:
        # Rule 1 -- negative amount
        if txn.amount < 0:
            invalid.append((txn, MSG_NEGATIVE))
            continue

        # Rule 2 -- duplicate (key = date)
        if txn.date in seen:
            invalid.append((txn, MSG_DUPLICATE))
            continue
        seen.add(txn.date)

        # Rule 3 -- wage check (EP2 only)
        if check_wage and wage is not None and txn.amount > wage:
            invalid.append((txn, MSG_WAGE))
            continue

        valid.append(txn)

    return valid, invalid
