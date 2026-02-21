"""
routes/returns.py -- EP4: Returns endpoints
  POST /returns:nps   -- NPS returns with tax benefit
  POST /returns:index -- NIFTY 50 index fund returns (no tax benefit)

Both endpoints share identical input and almost identical logic.
The only difference is the config dict (rate + use_tax flag).
"""
from __future__ import annotations

from fastapi import APIRouter

from app.models import (
    ReturnsRequest,
    ReturnsResponse,
    SavingResult,
)
from app.pipeline import process
from app.utils.finance import INDEX_CONFIG, NPS_CONFIG, calc_returns
from app.utils.periods import sum_by_k

router = APIRouter()

DATE_FMT = "%Y-%m-%d %H:%M:%S"


def _run_returns(body: ReturnsRequest, config: dict) -> ReturnsResponse:
    """
    Shared logic for both returns endpoints.

    EP4 rules:
    - Negatives and duplicates are silently dropped (not returned in output).
    - totalTransactionAmount and totalCeiling include ALL valid transactions
      (not filtered by k windows -- k is grouping only).
    - sum_by_k groups valid transactions per k window independently.
    - calc_returns applies compound interest + inflation adjustment.
    """
    # Run full pipeline (q/p/k applied), but we DON'T use tag_k for EP4
    # because k-tagging in EP4 is grouping only, not filtering.
    # We pass k=[] to process() so tag_k is skipped, then do sum_by_k manually.
    valid_txns, _ = process(
        expenses=body.transactions,
        q=body.q,
        p=body.p,
        k=[],          # don't tag_k here; EP4 never silently drops transactions
        wage=body.wage,
        check_wage=False,
    )

    # totalTransactionAmount and totalCeiling = ALL valid transactions
    total_amount = round(sum(t.amount for t in valid_txns), 2)
    total_ceiling = round(sum(t.ceiling for t in valid_txns), 2)

    # Group by k windows (each k window independently sums remanents)
    k_sums = sum_by_k(valid_txns, body.k)

    # Calculate returns
    savings = calc_returns(
        k_sums=k_sums,
        age=body.age,
        wage=body.wage,
        inflation=body.inflation,
        config=config,
    )

    return ReturnsResponse(
        totalTransactionAmount=total_amount,
        totalCeiling=total_ceiling,
        savingsByDates=[
            SavingResult(
                start=s["start"].strftime(DATE_FMT),
                end=s["end"].strftime(DATE_FMT),
                amount=s["amount"],
                profit=s["profit"],
                taxBenefit=s["taxBenefit"],
            )
            for s in savings
        ],
    )


@router.post("/returns:nps", response_model=ReturnsResponse)
def returns_nps(body: ReturnsRequest) -> ReturnsResponse:
    """EP4a -- NPS returns. Rate = 7.11%, tax benefit applied."""
    return _run_returns(body, NPS_CONFIG)


@router.post("/returns:index", response_model=ReturnsResponse)
def returns_index(body: ReturnsRequest) -> ReturnsResponse:
    """EP4b -- NIFTY 50 index fund returns. Rate = 14.49%, no tax benefit."""
    return _run_returns(body, INDEX_CONFIG)
