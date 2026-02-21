"""
pipeline.py -- Master orchestration function.

process(expenses, q=[], p=[], k=[], wage=None, check_wage=False)
  Runs: parse -> validate -> apply_q -> apply_p -> tag_k (EP3/EP4 path)
  Or:   parse -> validate                             (EP2 path)

Critical rules implemented here:
  - IntervalTree is built ONCE per request (at top of process).
  - EP4 does NOT drop transactions from totals; tag_k is only for EP3.
  - EP3 valid list contains ONLY k-tagged transactions.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from app.models import Expense, KPeriod, PPeriod, QPeriod, TransactionData
from app.utils.parser import parse
from app.utils.periods import apply_p, apply_q, build_tree, tag_k
from app.utils.validator import validate


def process(
    expenses: List[Expense],
    q: Optional[List[QPeriod]] = None,
    p: Optional[List[PPeriod]] = None,
    k: Optional[List[KPeriod]] = None,
    wage: Optional[float] = None,
    check_wage: bool = False,
) -> Tuple[List[TransactionData], List[Tuple[TransactionData, str]]]:
    """
    Full processing pipeline.

    Steps:
      1. parse: compute ceiling + remanent (numpy vectorized)
      2. validate: negative -> duplicate -> wage (hash set O(n))
      3. apply_q: IntervalTree lookup, latest-start q wins
      4. apply_p: IntervalTree lookup, ALL matching p summed
      5. tag_k:  drop transactions not in any k window, set inkPeriod=True

    IntervalTrees for q and p are built ONCE here, then passed down.
    tag_k builds its own tree internally (small, bounded cost).

    When q/p/k are empty lists, the corresponding steps are no-ops.

    Returns:
        valid   -- processed and filtered TransactionData list
        invalid -- list of (TransactionData, error_message)
    """
    q = q or []
    p = p or []
    k = k or []

    # Step 1: parse
    transactions = parse(expenses)

    # Step 2: validate
    valid, invalid = validate(transactions, wage=wage, check_wage=check_wage)

    # If no period processing needed, return early
    if not q and not p and not k:
        return valid, invalid

    # Build IntervalTrees ONCE per request
    q_tree = build_tree(q) if q else None
    p_tree = build_tree(p) if p else None

    # Step 3: apply q
    if q_tree is not None:
        valid = apply_q(valid, q_tree)

    # Step 4: apply p
    if p_tree is not None:
        valid = apply_p(valid, p_tree)

    # Step 5: tag k (and drop non-matching) -- only when k is provided
    if k:
        valid = tag_k(valid, k)

    return valid, invalid
