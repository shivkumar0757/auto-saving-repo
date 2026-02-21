# LLD — BlackRock Auto-Savings API

---

## 1. System Nature

This is a **stateless computation pipeline**, not a domain system.
No database, no auth, no sessions. Every request is self-contained.

The entire system is one shared pipeline of pure functions,
called by thin route handlers. Complexity lives in the pipeline,
not in the routes.

---

## 2. Core Architecture — The Pipeline

Every endpoint that touches transactions runs the **same ordered steps**.
The only difference between endpoints is which steps they run and with what flags.

```
Raw Expenses (input)
       │
       ▼
  ┌─────────┐
  │  PARSE  │  ceiling + remanent (numpy vectorized)
  └────┬────┘
       │
       ▼
  ┌──────────┐
  │ VALIDATE │  negatives → duplicates → wage (hash set, O(n))
  └────┬─────┘
       │
       ▼
  ┌─────────┐
  │ APPLY Q │  intervaltree lookup, latest-start wins
  └────┬────┘
       │
       ▼
  ┌─────────┐
  │ APPLY P │  intervaltree lookup, sum ALL matches
  └────┬────┘
       │
       ▼
  ┌─────────┐
  │  TAG K  │  flag inkPeriod, drop if no k match
  └────┬────┘
       │
       ▼
  valid[], invalid[]
```

**Which endpoints run which steps:**

| Step | EP1 parse | EP2 validator | EP3 filter | EP4 returns |
|------|:---------:|:-------------:|:----------:|:-----------:|
| Parse | ✅ | ✅ (pre-parsed input) | ✅ | ✅ |
| Validate (neg + dup) | ❌ | ✅ | ✅ | ✅ (silent skip) |
| Wage check | ❌ | ✅ | ❌ | ❌ |
| Apply Q | ❌ | ❌ | ✅ | ✅ |
| Apply P | ❌ | ❌ | ✅ | ✅ |
| Tag K | ❌ | ❌ | ✅ | ✅ |
| Finance | ❌ | ❌ | ❌ | ✅ |

---

## 3. Design Patterns

### 3.1 Pipeline Pattern — Core Architecture

The entire system is a sequential pipeline of pure functions.
Each step takes the output of the previous step.
Steps are independently testable and reusable.

```python
# pipeline.py — the only place that orchestrates steps
def process(expenses, q=[], p=[], k=[],
            wage=None, check_wage=False):
    txns            = parse(expenses)
    valid, invalid  = validate(txns, wage, check_wage)
    valid           = apply_q(valid, build_tree(q))
    valid           = apply_p(valid, build_tree(p))
    valid, dropped  = tag_k(valid, k)
    return valid, invalid
```

Every route calls `process()` — zero logic duplication across endpoints.

---

### 3.2 Strategy Pattern — Returns Calculation

NPS and Index Fund are identical logic.
The only difference is the rate and whether tax is calculated.
One function, one config dict, two callers.

```python
NPS_CONFIG   = {"rate": 0.0711, "use_tax": True}
INDEX_CONFIG = {"rate": 0.1449, "use_tax": False}

def calc_returns(k_sums, age, wage, inflation, config):
    # same formula, config drives the difference
```

`returns:nps`   → `calc_returns(..., NPS_CONFIG)`
`returns:index` → `calc_returns(..., INDEX_CONFIG)`

---

### 3.3 Singleton — Performance Tracking

Server start time and process handle are captured **once at boot**.
Every call to `/performance` reads from that single instance.

```python
# main.py — at module level, runs once
START_TIME = datetime.utcnow()
PROCESS    = psutil.Process()
```

---

## 4. Entities

### 4.1 Expense (input to EP1, EP3, EP4)
```
Expense
  date:    datetime   — parsed once at request entry
  amount:  float
```

### 4.2 Transaction (output of parse step)
```
Transaction
  date:     datetime
  amount:   float
  ceiling:  float     — ceil(amount / 100) * 100
  remanent: float     — ceiling - amount
```

### 4.3 FilteredTransaction (output of EP3)
```
FilteredTransaction extends Transaction
  inkPeriod: bool     — true if date falls in any k window
```

### 4.4 InvalidTransaction (output of EP2, EP3)
```
InvalidTransaction
  date:     datetime
  amount:   float
  ceiling:  float     — present in EP2, absent in EP3
  remanent: float     — present in EP2, absent in EP3
  message:  str       — exact error message
```

### 4.5 Period Types (input to EP3, EP4)
```
QPeriod
  fixed: float        — overrides remanent when matched
  start: datetime
  end:   datetime

PPeriod
  extra: float        — added to remanent when matched
  start: datetime
  end:   datetime

KPeriod
  start: datetime
  end:   datetime     — defines an evaluation window
```

### 4.6 KSummary (internal, used in EP4)
```
KSummary
  start:  datetime
  end:    datetime
  amount: float       — sum of remanents in this k window
```

### 4.7 SavingResult (output of EP4)
```
SavingResult
  start:      datetime
  end:        datetime
  amount:     float
  profit:     float   — A_real - amount
  taxBenefit: float   — 0.0 for index, calc_tax() for NPS
```

---

## 5. Key Data Structures

### 5.1 IntervalTree — Period Matching

**Problem:** With up to 10⁶ transactions and 10⁶ q/p periods,
naive O(n × p) matching = 10¹² ops. Unusable.

**Solution:** Build an `IntervalTree` from periods once per request.
Query it per transaction in O(log p).
Total complexity: O(n log p) — handles 10⁶ × 10⁶ comfortably.

```
IntervalTree (built once per request from q or p periods)
  .addi(start_ts, end_ts, period_object)
  .overlap(txn_ts, txn_ts) → set of matching intervals

Used in: apply_q(), apply_p()
Library: intervaltree
```

**q selection rule inside the tree result:**
Multiple q matches → pick the interval with the latest `.begin`.
Tie on `.begin` → pick the one that appeared first in the input list
(preserve original index when building the tree).

---

### 5.2 Hash Set — Duplicate Detection

**Problem:** Detecting duplicates across 10⁶ transactions.
Naive O(n²) nested loop is too slow.

**Solution:** Hash set of `(date, amount)` tuples. O(1) lookup per transaction.
Total: O(n).

```
seen: set of datetime values
  key = date only
  first occurrence → valid
  second occurrence → invalid, "Duplicate transaction"
```

**Note:** Duplicate key is date alone — spec constraint tᵢ ≠ tⱼ
means timestamps must be globally unique.

---

### 5.3 NumPy Array — Bulk Math

**Problem:** Python loops over 10⁶ floats for ceiling/remanent = ~0.8s.
NumPy vectorized = ~0.008s. 100× faster.

**Solution:** Collect all amounts into a numpy array at the parse step.
Do ceiling and remanent in one shot. Zip results back to objects.

```python
amounts   = np.array([e.amount for e in expenses])
ceilings  = np.ceil(amounts / 100) * 100
remanents = ceilings - amounts
```

**Also used in finance.py** for compound interest across k sums:
```python
P      = np.array([ks.amount for ks in k_sums])
A      = P * (1 + rate) ** t
A_real = A / (1 + inflation / 100) ** t
profit = A_real - P
```

---

### 5.4 Config Dict — Strategy for Returns

```python
NPS_CONFIG   = {"rate": 0.0711, "use_tax": True}
INDEX_CONFIG = {"rate": 0.1449, "use_tax": False}
```

Passed into `calc_returns()`. Drives rate and whether
`calc_tax()` is called. Zero code duplication between
the two returns endpoints.

---

## 6. File Structure

```
app/
  main.py           — FastAPI app, route registration, START_TIME, PROCESS
  models.py         — Pydantic models; date strings parsed to datetime here
  pipeline.py       — process() master function; orchestrates all steps

  utils/
    parser.py       — ceiling(), remanent() using numpy
    validator.py    — validate(); hash set dedup; negative + wage checks
    periods.py      — build_tree(), apply_q(), apply_p(), tag_k(), sum_by_k()
    finance.py      — calc_returns(), calc_tax(), nps_deduction()

  routes/
    parse.py        — EP1: calls parse() directly
    validator.py    — EP2: calls process() with check_wage=True
    filter.py       — EP3: calls process() with q, p, k
    returns.py      — EP4: calls process() then calc_returns() with config
    performance.py  — EP5: reads START_TIME, PROCESS

test/
  test_parser.py
  test_validator.py
  test_periods.py
  test_finance.py
  test_pipeline.py
```

---

## 7. Complexity Summary

| Operation | Algorithm | Data Structure | Complexity |
|-----------|-----------|---------------|------------|
| Ceiling + remanent | Vectorized math | NumPy array | O(n) |
| Duplicate detection | Hash lookup | Set of tuples | O(n) |
| Negative check | Single pass | — | O(n) |
| Wage check | Single pass | — | O(n) |
| q period matching | Interval query | IntervalTree | O(n log q) |
| p period matching | Interval query | IntervalTree | O(n log p) |
| k period tagging | Linear scan per txn | List | O(n × k) * |
| k period summing | Linear scan | List | O(n × k) * |
| Compound interest | Vectorized math | NumPy array | O(k) |
| Tax calculation | Progressive slab loop | List of tuples | O(1) |

\* k periods are bounded within a calendar year and in practice
will be small (single digits in real use). O(n × k) is fine here.
If k also reaches 10⁶, apply intervaltree to k as well.

---

## 8. Critical Implementation Rules

**1. Parse dates once.**
Pydantic models convert all date strings to `datetime` at deserialization.
No `strptime` calls inside any loop.

**2. Build IntervalTree once per request.**
Not once per transaction. Build at the top of `process()`, pass the tree down.

**3. Duplicate key is date only.**
Spec constraint tᵢ ≠ tⱼ means timestamps are the uniqueness identifier.

**4. q + p always stack.**
If a transaction matches both q and p:
`final_remanent = q.fixed + sum(all matching p.extra)`
p always runs after q, always adds on top.

**5. k-excluded transactions are silently dropped.**
Not added to valid, not added to invalid. Just gone.
EP3 invalid list only contains negatives and duplicates.

**6. EP4 invalid transactions are silently skipped.**
Unlike EP3, EP4 does not return an invalid list.
Negatives and duplicates are dropped without appearing in output.

**7. t floor at 5.**
`t = max(60 - age, 5)` — if age >= 60, use t=5, not 0.

**8. Wage is monthly. Multiply by 12 for tax.**
`annual_income = wage × 12`
NPS deduction = `min(invested, 0.10 × annual_income, 200000)`

**9. Return zeros on all-invalid input.**
Do not crash. Return `totalTransactionAmount: 0, savingsByDates: []`.

**10. Output order of savingsByDates = input order of k.**
Do not sort k periods. Preserve insertion order.

**11. EP4 k is grouping only, not filtering.**
`totalTransactionAmount` and `totalCeiling` are sums of ALL valid
transactions regardless of k windows.
tag_k / drop behavior is EP3 only.
In EP4, every valid transaction counts toward totals.
k windows only determine which transactions are summed per bucket.
