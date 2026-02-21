"""routes/parse.py -- EP1: Transaction Builder (POST /transactions:parse)"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException

from app.models import Expense, TransactionOut
from app.utils.parser import parse

router = APIRouter()


@router.post("/transactions:parse", response_model=List[TransactionOut])
def parse_transactions(expenses: List[Expense]):
    """
    EP1 -- Receives raw expenses, returns enriched transactions with
    ceiling and remanent. Does not validate negative amounts (that is EP2).
    """
    txns = parse(expenses)
    return [TransactionOut.from_txn(t) for t in txns]
