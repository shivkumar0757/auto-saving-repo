"""
utils/parser.py -- Ceiling and remanent calculation using NumPy vectorized ops.

ceiling(amounts_array)  -> numpy array of ceilings
remanent(amounts_array, ceilings_array) -> numpy array of remanents

parse(expenses) -> list[TransactionData]
  Converts a list of Expense objects into TransactionData with ceiling/remanent.
  Dates are already datetime objects (parsed by Pydantic). No strptime here.
"""
from __future__ import annotations

import numpy as np

from app.models import Expense, TransactionData


def ceiling(amounts: np.ndarray) -> np.ndarray:
    """Return the next multiple of 100 for each amount (numpy vectorized)."""
    return np.ceil(amounts / 100.0) * 100.0


def remanent(amounts: np.ndarray, ceilings: np.ndarray) -> np.ndarray:
    """Return ceiling - amount for each element (numpy vectorized)."""
    return ceilings - amounts


def parse(expenses: list[Expense]) -> list[TransactionData]:
    """
    Convert a list of Expense objects into TransactionData with ceiling/remanent.

    Uses numpy for bulk arithmetic -- O(n) with no Python loops over math.
    Date parsing already happened in Pydantic models; no strptime called here.
    """
    if not expenses:
        return []

    amounts_arr = np.array([e.amount for e in expenses], dtype=np.float64)
    ceilings_arr = ceiling(amounts_arr)
    remanents_arr = remanent(amounts_arr, ceilings_arr)

    return [
        TransactionData(
            date=e.date,
            amount=float(amounts_arr[i]),
            ceiling=float(ceilings_arr[i]),
            remanent=float(remanents_arr[i]),
        )
        for i, e in enumerate(expenses)
    ]
