"""routes/filter.py -- EP3: Temporal Constraints Filter (POST /transactions:filter)"""
from __future__ import annotations

from fastapi import APIRouter

from app.models import (
    FilteredTransactionOut,
    FilterRequest,
    FilterResponse,
    InvalidTransactionOut,
)
from app.pipeline import process

router = APIRouter()


@router.post(
    "/transactions:filter",
    response_model=FilterResponse,
    response_model_exclude_none=True,
)
def filter_transactions(body: FilterRequest):
    """
    EP3 -- Receives raw expenses (not pre-parsed).
    Applies all period rules internally.
    Returns valid (k-tagged) and invalid (negatives + duplicates) lists.

    Valid transactions include inkPeriod=True.
    Invalid transactions include only date, amount, message (no ceiling/remanent).
    Transactions outside all k windows are silently dropped.
    """
    valid_txns, invalid_pairs = process(
        expenses=body.transactions,
        q=body.q,
        p=body.p,
        k=body.k,
        wage=body.wage,
        check_wage=False,  # EP3 does NOT check amount > wage
    )

    return FilterResponse(
        valid=[FilteredTransactionOut.from_txn(t) for t in valid_txns],
        invalid=[
            InvalidTransactionOut.from_ep3(t, msg) for t, msg in invalid_pairs
        ],
    )
