"""
utils/periods.py -- Period-based remanent adjustment using IntervalTree.

build_tree(periods)         -> IntervalTree  (built ONCE per request)
apply_q(transactions, tree) -> modifies remanent; latest-start q wins
apply_p(transactions, tree) -> adds to remanent; ALL matching p summed
tag_k(transactions, k_list) -> drops no-match txns, sets inkPeriod=True
sum_by_k(transactions, k_list) -> [{start, end, amount}] in input order

IntervalTree stores (start_ts, end_ts+1us, (index, period)) so that
inclusive end-point queries work correctly with half-open intervals.

Timestamps are converted to float (posix) for the tree to avoid
datetime hashability issues inside intervaltree.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from intervaltree import IntervalTree

from app.models import KPeriod, PPeriod, QPeriod, TransactionData

# Small epsilon to convert inclusive [start, end] to half-open [start, end+eps)
_EPS = timedelta(microseconds=1)


def _ts(dt: datetime) -> float:
    """Convert datetime to float timestamp for IntervalTree."""
    return dt.timestamp()


def build_tree(periods: List[Any]) -> IntervalTree:
    """
    Build an IntervalTree from a list of QPeriod, PPeriod, or KPeriod objects.

    Each interval stores (original_index, period_object) as data so callers
    can resolve tie-breaking by insertion order.

    The tree uses half-open intervals [start_ts, end_ts + 1us) so that
    inclusive end dates are matched by overlap queries.
    """
    tree: IntervalTree = IntervalTree()
    for idx, period in enumerate(periods):
        begin = _ts(period.start)
        end = _ts(period.end + _EPS)
        if begin < end:  # guard against zero-width intervals
            tree.addi(begin, end, (idx, period))
    return tree


def apply_q(
    transactions: List[TransactionData],
    q_tree: IntervalTree,
) -> List[TransactionData]:
    """
    Apply q-period overrides to remanent.

    For each transaction that falls in one or more q intervals:
      - Select the interval with the latest start date.
      - On a tie (same start date), select the one with the smallest original index
        (i.e. the one that appeared first in the input list).
      - Set remanent = q.fixed of the winning period.

    Returns the same list (mutated in-place) for pipeline chaining.
    """
    for txn in transactions:
        ts = _ts(txn.date)
        matches = q_tree.overlap(ts, ts + _EPS.total_seconds())
        if not matches:
            continue

        # Pick winner: latest start -> then earliest index on tie
        winner = min(
            matches,
            key=lambda iv: (-iv.begin, iv.data[0]),
        )
        _, qp = winner.data
        txn.remanent = float(qp.fixed)

    return transactions


def apply_p(
    transactions: List[TransactionData],
    p_tree: IntervalTree,
) -> List[TransactionData]:
    """
    Apply p-period additions to remanent.

    For each transaction that falls in one or more p intervals:
      - Sum ALL matching p.extra values.
      - Add the total to the current remanent (which may already be q-adjusted).

    Returns the same list (mutated in-place) for pipeline chaining.
    """
    for txn in transactions:
        ts = _ts(txn.date)
        matches = p_tree.overlap(ts, ts + _EPS.total_seconds())
        if not matches:
            continue

        extra_total = sum(iv.data[1].extra for iv in matches)
        txn.remanent += float(extra_total)

    return transactions


def tag_k(
    transactions: List[TransactionData],
    k_periods: List[KPeriod],
) -> List[TransactionData]:
    """
    Tag transactions with inkPeriod=True if they fall in ANY k window.
    Transactions that fall in NO k window are silently dropped.

    Returns a new list containing only the transactions that match at least
    one k period, all with inkPeriod=True.
    """
    if not k_periods:
        # No k periods -> drop everything (EP3 spec: dropped silently)
        return []

    k_tree = build_tree(k_periods)
    result: List[TransactionData] = []
    eps_s = _EPS.total_seconds()

    for txn in transactions:
        ts = _ts(txn.date)
        if k_tree.overlap(ts, ts + eps_s):
            txn.inkPeriod = True
            result.append(txn)
        # else: silently dropped

    return result


def sum_by_k(
    transactions: List[TransactionData],
    k_periods: List[KPeriod],
) -> List[Dict]:
    """
    Sum remanents per k window. Each transaction may appear in multiple k windows.

    Returns a list of dicts (one per k period, same order as input):
      {"start": datetime, "end": datetime, "amount": float}

    Note: this does NOT drop transactions -- every valid transaction is checked
    against every k window independently (EP4 semantics).
    """
    results = []
    eps_s = _EPS.total_seconds()

    for kp in k_periods:
        k_start_ts = _ts(kp.start)
        k_end_ts = _ts(kp.end + _EPS)
        total = 0.0
        for txn in transactions:
            ts = _ts(txn.date)
            if k_start_ts <= ts < k_end_ts:
                total += txn.remanent
        results.append({"start": kp.start, "end": kp.end, "amount": total})

    return results
