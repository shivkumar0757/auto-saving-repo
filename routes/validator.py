"""routes/validator.py -- EP2: Transaction Validator (POST /transactions:validator)"""
from __future__ import annotations

from fastapi import APIRouter

from app.models import (
    InvalidTransactionOut,
    TransactionData,
    TransactionOut,
    ValidatorRequest,
    ValidatorResponse,
)
from app.utils.validator import validate

router = APIRouter()


@router.post("/transactions:validator", response_model=ValidatorResponse)
def validate_transactions(body: ValidatorRequest):
    """
    EP2 -- Validates already-parsed transactions.
    Checks: negative -> duplicate -> wage (check_wage=True).
    Returns valid and invalid lists.
    Invalid transactions include ceiling and remanent fields.
    """
    # Convert Pydantic Transaction objects to internal TransactionData
    txns = [
        TransactionData(
            date=t.date,
            amount=t.amount,
            ceiling=t.ceiling,
            remanent=t.remanent,
        )
        for t in body.transactions
    ]

    valid_txns, invalid_pairs = validate(txns, wage=body.wage, check_wage=True)

    return ValidatorResponse(
        valid=[TransactionOut.from_txn(t) for t in valid_txns],
        invalid=[
            InvalidTransactionOut.from_ep2(t, msg) for t, msg in invalid_pairs
        ],
    )
