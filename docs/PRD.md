# PRD — BlackRock Auto-Savings API
**Version:** 1.0  | **Delivery:** 2–3 hours | **Stack:** FastAPI + Docker

---

## 1. Overview

### Problem Statement
People in India consistently under-save for retirement. This system automates micro-savings by **rounding up every expense to the next ₹100** and investing the difference. It is the "round-up" model applied to retirement planning at scale.

### What We're Building
A stateless REST API — **5 endpoints** — that runs inside Docker on port **5477**:

| # | Endpoint | Job |
|---|----------|-----|
| 1 | `POST /transactions:parse` | Round up expenses → ceiling + remanent |
| 2 | `POST /transactions:validator` | Validate transactions against business rules |
| 3 | `POST /transactions:filter` | Apply q/p/k period rules, return valid/invalid |
| 4a | `POST /returns:nps` | Calculate NPS retirement returns + tax benefit |
| 4b | `POST /returns:index` | Calculate NIFTY 50 index fund returns |
| 5 | `GET /performance` | Report system uptime, memory, threads |

### Core Mental Model
```
Expense ₹480
  └─► ceiling  = ₹500        (next multiple of 100)
  └─► remanent = ₹20         (ceiling - amount → money invested)
        └─► q period?  → override remanent with fixed value
        └─► p period?  → add extra on top (always, even after q)
        └─► k period?  → which evaluation windows include this transaction
              └─► compound interest applied per k window
              └─► inflation-adjusted
              └─► = real retirement value
```

---

## 2. Resolved Decisions (from HTML source of truth)

All previously open questions resolved:

| Question | Resolution | Source |
|----------|-----------|--------|
| Does p stack on top of q? | **Yes** — "p is an addition to q rules, if transaction falls in q then p, we apply both" | HTML spec |
| Is `wage` monthly or annual? | **Monthly input** — multiply by 12 for annual. Example: ₹50,000/mo → ₹6,00,000/yr | HTML example |
| Exact multiples of 100 (e.g. 300)? | `ceil(300/100)*100 = 300` → ceiling=300, remanent=**0**. No special case needed. | Math + spec |
| Empty transaction list response? | **200 with empty arrays** — spec never mandates 400 for empty input | Spec inference |
| Does EP3 check `amount > wage`? | **No** — EP3 only checks negatives + duplicates. Wage check is EP2 only. | HTML output example |
| Tax slabs? | **New simplified regime** as listed in HTML (0% up to ₹7L) | HTML spec |

---

## 3. Core Business Logic

### 3.1 Ceiling & Remanent
```
ceiling  = ceil(amount / 100) * 100
remanent = ceiling - amount
```

| amount | ceiling | remanent |
|--------|---------|---------|
| 250 | 300 | 50 |
| 375 | 400 | 25 |
| 620 | 700 | 80 |
| 480 | 500 | 20 |
| 1519 | 1600 | 81 |
| 300 | 300 | 0 ← exact multiple → remanent is 0 |

### 3.2 Period Rules

#### q Period — Fixed Override
- If transaction date falls **within** a q period (start and end **inclusive**), **replace** remanent with `q.fixed`
- If **multiple q periods** match → use the one with the **latest `start` date**
- If two q periods share the same start date → use the **first one in the list**
- `q.fixed = 0` → transaction contributes ₹0 to savings (stays in valid list, just contributes zero)

#### p Period — Extra Addition
- If transaction date falls within a p period (inclusive), **add** `p.extra` to remanent
- **p always runs after q** — even if q already set the remanent. They stack.
- If **multiple p periods** match → **add ALL their extras together**
- Final remanent when in both q and p = `q.fixed + sum(all matching p.extra)`

#### k Period — Evaluation Window
- Defines time windows for return calculation and output grouping
- Each k period independently sums the remanent of all transactions within its date range
- **A transaction can belong to multiple k periods** — each k window counts it independently
- Transactions **outside all k periods** → silently dropped (not in valid, not in invalid)
- `savingsByDates` output order = same order as `k` array in input

### 3.3 Period Processing Order (strict — must follow this)
```
Step 1: Calculate ceiling and remanent  (ceiling - amount)
Step 2: Apply q period rules            (if match → remanent = q.fixed)
Step 3: Apply p period rules            (if match → remanent += p.extra, always)
Step 4: Group transactions by k periods (independent sum per k window)
Step 5: Calculate returns per k window
```

### 3.4 Investment Returns

**Years to retirement:**
```
t = (60 - age)  if age < 60
t = 5           if age >= 60
```

**Compound interest:**
```
A = P × (1 + r)^t
```

**Inflation adjustment:**
```
A_real = A / (1 + inflation/100)^t
```

**Profit:**
```
profit = A_real - P
```

| Instrument | Rate (r) | Tax Benefit |
|------------|---------|-------------|
| NPS | 7.11% | Yes (see §3.5) |
| NIFTY 50 Index | 14.49% | No — always 0.0 |

### 3.5 NPS Tax Benefit Calculation

**Annual wage:** `annual_income = wage × 12`  (wage input is monthly)

**Eligible deduction:**
```
NPS_Deduction = min(invested_amount, 10% of annual_income, ₹2,00,000)
```

**Tax benefit:**
```
Tax_Benefit = Tax(annual_income) - Tax(annual_income - NPS_Deduction)
```

**Tax function — simplified slabs (from HTML spec):**
```
Tax(income):
  if income <= 7,00,000:    return 0
  if income <= 10,00,000:   return (income - 7,00,000) × 0.10
  if income <= 12,00,000:   return 30,000 + (income - 10,00,000) × 0.15
  if income <= 15,00,000:   return 60,000 + (income - 12,00,000) × 0.20
  else:                     return 1,20,000 + (income - 15,00,000) × 0.30
```

**Worked example from spec:**
```
wage = ₹50,000/mo → annual_income = ₹6,00,000
invested = 145
NPS_Deduction = min(145, 60,000, 2,00,000) = 145
Tax(6,00,000) = 0  (below ₹7L threshold)
Tax_Benefit   = 0 - 0 = 0
```

> ⚠️ Note: For the spec's worked example, `min(invested, 10% of income, ₹2L)` and `min(invested, 10% of invested, ₹2L)` produce the same result since income < ₹7L (tax = 0 either way). The formula implemented uses `10% of annual_income` as written in the spec text.

> Tax benefit is returned **separately** from profit. It does NOT generate interest.

---

## 4. API Specification

**Base path:** `/blackrock/challenge/v1`
**Full base URL:** `http://localhost:5477/blackrock/challenge/v1`
**Content-Type:** `application/json`
**Date format:** `"YYYY-MM-DD HH:mm:ss"` for all inputs and outputs
**Number output:** doubles rounded to 2 decimal places

---

### EP1 — Transaction Builder
```
POST /blackrock/challenge/v1/transactions:parse
```

Receives raw expenses, returns enriched transactions with `ceiling` and `remanent`.

**Input:**
```json
[
  {"date": "2023-10-12 20:15:30", "amount": 250},
  {"date": "2023-02-28 15:49:20", "amount": 375},
  {"date": "2023-07-01 21:59:00", "amount": 620},
  {"date": "2023-12-17 08:09:45", "amount": 480}
]
```

**Output:**
```json
[
  {"date": "2023-10-12 20:15:30", "amount": 250.0, "ceiling": 300.0, "remanent": 50.0},
  {"date": "2023-02-28 15:49:20", "amount": 375.0, "ceiling": 400.0, "remanent": 25.0},
  {"date": "2023-07-01 21:59:00", "amount": 620.0, "ceiling": 700.0, "remanent": 80.0},
  {"date": "2023-12-17 08:09:45", "amount": 480.0, "ceiling": 500.0, "remanent": 20.0}
]
```

**Validations:**

| Code | Rule | Message | Behaviour |
|------|------|---------|-----------|
| E001 | `date` missing or null | `"Date is required"` | HTTP 400 |
| E002 | `date` wrong format | `"Invalid date format. Expected: YYYY-MM-DD HH:mm:ss"` | HTTP 400 |
| E003 | `amount` missing or null | `"Amount is required"` | HTTP 400 |

> EP1 does **not** reject negatives — it just computes ceiling/remanent. Negative validation is EP2's job.

---

### EP2 — Transaction Validator
```
POST /blackrock/challenge/v1/transactions:validator
```

Validates already-parsed transactions. Returns `valid` and `invalid` lists.

**Input:**
```json
{
  "wage": 50000,
  "transactions": [
    {"date": "2023-01-15 10:30:00", "amount": 2000, "ceiling": 300,  "remanent": 50},
    {"date": "2023-03-20 14:45:00", "amount": 3500, "ceiling": 400,  "remanent": 70},
    {"date": "2023-06-10 09:15:00", "amount": 1500, "ceiling": 200,  "remanent": 30},
    {"date": "2023-07-10 09:15:00", "amount": -250, "ceiling": 200,  "remanent": 30}
  ]
}
```

**Output:**
```json
{
  "valid": [
    {"date": "2023-01-15 10:30:00", "amount": 2000.0, "ceiling": 300.0, "remanent": 50.0},
    {"date": "2023-03-20 14:45:00", "amount": 3500.0, "ceiling": 400.0, "remanent": 70.0},
    {"date": "2023-06-10 09:15:00", "amount": 1500.0, "ceiling": 200.0, "remanent": 30.0}
  ],
  "invalid": [
    {
      "date": "2023-07-10 09:15:00", "amount": -250.0, "ceiling": 200.0, "remanent": 30.0,
      "message": "Negative amounts are not allowed"
    }
  ]
}
```

**Request-level validations (fail fast → HTTP 400):**

| Code | Rule | Message |
|------|------|---------|
| E010 | `wage` missing or null | `"Wage is required"` |
| E011 | `wage` <= 0 | `"Wage must be a positive number"` |
| E012 | `transactions` missing | `"Transactions list is required"` |

**Per-transaction validations (first failing rule wins → invalid list):**

| Code | Check Order | Rule | Message |
|------|-------------|------|---------|
| E013 | 1st | `amount < 0` | `"Negative amounts are not allowed"` |
| E014 | 2nd | Same `date` AND same `amount` as a prior transaction | `"Duplicate transaction"` |
| E015 | 3rd | `amount > wage` | `"Amount exceeds monthly wage"` |

> First occurrence of a duplicate stays **valid**. The second occurrence → invalid with E014.

---

### EP3 — Temporal Constraints Filter
```
POST /blackrock/challenge/v1/transactions:filter
```

Receives **raw expenses** (not pre-parsed). Applies all period rules internally. Returns valid/invalid.

**Input:**
```json
{
  "q": [{"fixed": 0,  "start": "2023-07-01 00:00:00", "end": "2023-07-31 23:59:59"}],
  "p": [{"extra": 30, "start": "2023-10-01 00:00:00", "end": "2023-12-31 23:59:59"}],
  "k": [{"start": "2023-01-01 00:00:00", "end": "2023-12-31 23:59:59"}],
  "wage": 50000,
  "transactions": [
    {"date": "2023-02-28 15:49:20", "amount": 375},
    {"date": "2023-07-15 10:30:00", "amount": 620},
    {"date": "2023-10-12 20:15:30", "amount": 250},
    {"date": "2023-10-12 20:15:30", "amount": 250},
    {"date": "2023-12-17 08:09:45", "amount": -480}
  ]
}
```

**Output:**
```json
{
  "valid": [
    {"date": "2023-02-28 15:49:20", "amount": 375.0, "ceiling": 400.0, "remanent": 25.0, "inkPeriod": true},
    {"date": "2023-07-15 10:30:00", "amount": 620.0, "ceiling": 700.0, "remanent": 0.0,  "inkPeriod": true},
    {"date": "2023-10-12 20:15:30", "amount": 250.0, "ceiling": 300.0, "remanent": 80.0, "inkPeriod": true}
  ],
  "invalid": [
    {"date": "2023-10-12 20:15:30", "amount": 250.0, "message": "Duplicate transaction"},
    {"date": "2023-12-17 08:09:45", "amount": -480.0, "message": "Negative amounts are not allowed"}
  ]
}
```

**Processing flow per transaction (strict order):**
```
1. amount < 0?               → invalid (E013), stop processing this transaction
2. duplicate (date+amount)?  → invalid (E014), stop processing this transaction
3. compute ceiling, remanent
4. match q periods           → remanent = q.fixed  (latest-start q wins if multiple)
5. match p periods           → remanent += p.extra  (ALL matching p periods summed)
6. in any k period?
     YES → inkPeriod = true, add to valid list
     NO  → silently drop (not in valid, not in invalid)
```

**Request-level validations (HTTP 400):**

| Code | Rule | Message |
|------|------|---------|
| E020 | `wage` missing or <= 0 | `"Wage must be a positive number"` |
| E021 | Any q period has `start` > `end` | `"Invalid q period: start must be before end"` |
| E022 | Any p period has `start` > `end` | `"Invalid p period: start must be before end"` |
| E023 | Any k period has `start` > `end` | `"Invalid k period: start must be before end"` |
| E024 | `q.fixed` < 0 | `"q period fixed value must be non-negative"` |
| E025 | `p.extra` < 0 | `"p period extra value must be non-negative"` |

**Per-transaction validations (→ invalid list):**

| Code | Rule | Message |
|------|------|---------|
| E013 | `amount < 0` | `"Negative amounts are not allowed"` |
| E014 | Duplicate date+amount | `"Duplicate transaction"` |

> `amount > wage` is **NOT** checked in EP3. Only EP2 does this.
> Invalid transactions in EP3 output include only `date`, `amount`, `message` — no ceiling/remanent.

---

### EP4a — Returns: NPS
```
POST /blackrock/challenge/v1/returns:nps
```

### EP4b — Returns: Index Fund
```
POST /blackrock/challenge/v1/returns:index
```

Both share identical input. They run the full pipeline: parse → validate → apply periods → calculate returns.

**Input:**
```json
{
  "age": 29,
  "wage": 50000,
  "inflation": 5.5,
  "q": [{"fixed": 0,  "start": "2023-07-01 00:00:00", "end": "2023-07-31 23:59:59"}],
  "p": [{"extra": 25, "start": "2023-10-01 08:00:00", "end": "2023-12-31 19:59:59"}],
  "k": [
    {"start": "2023-01-01 00:00:00", "end": "2023-12-31 23:59:59"},
    {"start": "2023-03-01 00:00:00", "end": "2023-11-30 23:59:59"}
  ],
  "transactions": [
    {"date": "2023-02-28 15:49:20", "amount": 375},
    {"date": "2023-07-01 21:59:00", "amount": 620},
    {"date": "2023-10-12 20:15:30", "amount": 250},
    {"date": "2023-12-17 08:09:45", "amount": 480},
    {"date": "2023-12-17 08:09:45", "amount": -10}
  ]
}
```

**Output:**
```json
{
  "totalTransactionAmount": 1725.0,
  "totalCeiling": 1900.0,
  "savingsByDates": [
    {
      "start": "2023-01-01 00:00:00",
      "end": "2023-12-31 23:59:59",
      "amount": 145.0,
      "profit": 86.88,
      "taxBenefit": 0.0
    },
    {
      "start": "2023-03-01 00:00:00",
      "end": "2023-11-30 23:59:59",
      "amount": 75.0,
      "profit": 44.94,
      "taxBenefit": 0.0
    }
  ]
}
```

**Worked example — full trace:**
```
Valid transactions after negative/duplicate filter:
  Feb 28 (375)  → ceiling=400, remanent=25,  no q/p match     → final remanent = 25
  Jul 01 (620)  → ceiling=700, remanent=80,  q match fixed=0  → remanent = 0  (p range is Oct-Dec, no match)
  Oct 12 (250)  → ceiling=300, remanent=50,  p match extra=25 → remanent = 50+25 = 75
  Dec 17 (480)  → ceiling=500, remanent=20,  p match extra=25 → remanent = 20+25 = 45
  Dec 17 (-10)  → INVALID (negative) → skipped entirely

totalTransactionAmount = 375 + 620 + 250 + 480 = 1725.0
totalCeiling           = 400 + 700 + 300 + 500 = 1900.0

k1 (Jan 01 – Dec 31): 25 + 0 + 75 + 45 = 145.0
k2 (Mar 01 – Nov 30): Jul 01 (0) + Oct 12 (75) = 75.0
  (Feb 28 and Dec 17 are outside Mar–Nov range → excluded from k2)

For k1, NPS (t = 60-29 = 31 years, rate = 7.11%, inflation = 5.5%):
  A        = 145 × (1.0711)^31 = 145 × 8.41 = 1219.45
  A_real   = 1219.45 / (1.055)^31 = 1219.45 / 5.258 = 231.9
  profit   = 231.9 - 145 = 86.88  ✓ matches spec

  annual_income = 50000 × 12 = 600000
  NPS_Deduction = min(145, 60000, 200000) = 145
  Tax(600000)   = 0  (below ₹7L threshold)
  taxBenefit    = 0.0  ✓ matches spec

For k2, NPS:
  A        = 75 × (1.0711)^31 = 75 × 8.41 = 630.75
  A_real   = 630.75 / 5.258 = 119.97
  profit   = 119.97 - 75 = 44.94  ✓ matches spec
```

**Output field descriptions:**

| Field | Type | Description |
|-------|------|-------------|
| `totalTransactionAmount` | double | Sum of `amount` of all valid transactions (negatives and duplicates excluded) |
| `totalCeiling` | double | Sum of `ceiling` of all valid transactions |
| `savingsByDates` | array | One entry per k period, same order as k input |
| `savingsByDates[].start` | datetime | k period start |
| `savingsByDates[].end` | datetime | k period end |
| `savingsByDates[].amount` | double | Total remanent invested within this k window |
| `savingsByDates[].profit` | double | `A_real - amount` (inflation-adjusted gain) |
| `savingsByDates[].taxBenefit` | double | NPS: tax saved. Index: always 0.0 |

**Request-level validations (HTTP 400):**

| Code | Rule | Message |
|------|------|---------|
| E030 | `age` missing or not integer | `"Age is required and must be a whole number"` |
| E031 | `age` <= 0 | `"Age must be a positive number"` |
| E032 | `wage` missing or <= 0 | `"Wage must be a positive number"` |
| E033 | `inflation` missing | `"Inflation rate is required"` |
| E034 | `inflation` < 0 | `"Inflation rate must be non-negative"` |
| E035 | `k` list empty or missing | `"At least one k period is required"` |
| E021–E025 | Same period validations as EP3 | (same messages) |

**Per-transaction handling in EP4:**
- Negative amounts → silently skipped (not returned in output)
- Duplicates (same date + same amount) → silently skipped, first occurrence kept

---

### EP5 — Performance Report
```
GET /blackrock/challenge/v1/performance
```

Returns system runtime metrics. No input.

**Output:**
```json
{
  "time": "1970-01-01 00:11:54.135",
  "memory": "25.11",
  "threads": 16
}
```

| Field | Type | Format | Description |
|-------|------|--------|-------------|
| `time` | string | `YYYY-MM-DD HH:mm:ss.SSS` | Application uptime since process start |
| `memory` | string | `"XXX.XX"` | Total memory used in MB (no "MB" unit in value) |
| `threads` | integer | — | Number of active threads |

---

## 5. Complete Validation Matrix

| Code | Endpoint(s) | Trigger | Message | Behaviour | Source |
|------|------------|---------|---------|-----------|--------|
| E001 | EP1 | `date` missing | `"Date is required"` | HTTP 400 | Defensive |
| E002 | EP1 | `date` wrong format | `"Invalid date format. Expected: YYYY-MM-DD HH:mm:ss"` | HTTP 400 | Defensive |
| E003 | EP1 | `amount` missing | `"Amount is required"` | HTTP 400 | Defensive |
| E010 | EP2 | `wage` missing | `"Wage is required"` | HTTP 400 | Defensive |
| E011 | EP2 | `wage` <= 0 | `"Wage must be a positive number"` | HTTP 400 | Defensive |
| E012 | EP2 | `transactions` missing | `"Transactions list is required"` | HTTP 400 | Defensive |
| E013 | EP2, EP3 | `amount < 0` | `"Negative amounts are not allowed"` | → invalid list | Spec-defined |
| E014 | EP2, EP3 | Duplicate date+amount | `"Duplicate transaction"` | → invalid list | Spec-defined |
| E020 | EP3, EP4 | `wage` missing or <= 0 | `"Wage must be a positive number"` | HTTP 400 | Defensive |
| E021 | EP3, EP4 | q period `start` > `end` | `"Invalid q period: start must be before end"` | HTTP 400 | Defensive |
| E022 | EP3, EP4 | p period `start` > `end` | `"Invalid p period: start must be before end"` | HTTP 400 | Defensive |
| E023 | EP3, EP4 | k period `start` > `end` | `"Invalid k period: start must be before end"` | HTTP 400 | Defensive |
| E024 | EP3, EP4 | `q.fixed` < 0 | `"q period fixed value must be non-negative"` | HTTP 400 | Defensive |
| E025 | EP3, EP4 | `p.extra` < 0 | `"p period extra value must be non-negative"` | HTTP 400 | Defensive |
| E030 | EP4 | `age` missing or not integer | `"Age is required and must be a whole number"` | HTTP 400 | Defensive |
| E031 | EP4 | `age` <= 0 | `"Age must be a positive number"` | HTTP 400 | Defensive |
| E032 | EP4 | `wage` missing or <= 0 | `"Wage must be a positive number"` | HTTP 400 | Defensive |
| E033 | EP4 | `inflation` missing | `"Inflation rate is required"` | HTTP 400 | Defensive |
| E034 | EP4 | `inflation` < 0 | `"Inflation rate must be non-negative"` | HTTP 400 | Defensive |
| E035 | EP4 | `k` list empty | `"At least one k period is required"` | HTTP 400 | Defensive |

---

## 6. Data Types Reference

| Type | Input format | Output format | Example |
|------|-------------|---------------|---------|
| datetime | `"YYYY-MM-DD HH:mm:ss"` | `"YYYY-MM-DD HH:mm:ss"` | `"2023-10-12 20:15:30"` |
| double | any number | 2 decimal places | `145.0`, `86.88` |
| integer | whole number | whole number | `29`, `16` |
| string | UTF-8 text | UTF-8 text | `"Duplicate transaction"` |

---

## 7. Scale Constraints

| Variable | Constraint | Performance note |
|----------|-----------|-----------------|
| n (transactions) | 0 ≤ n < 10⁶ | Must not do O(n²) duplicate check — use a set |
| amount (x) | x < 5 × 10⁵ | |
| q periods | 0 ≤ q < 10⁶ | Naive O(n×q) may be too slow — sort periods, use binary search |
| p periods | 0 ≤ p < 10⁶ | Same — sort + binary search |
| k periods | 0 ≤ k < 10⁶ | Same — independent sums per k |
| fixed | fixed < 5 × 10⁵ | |
| extra | extra < 5 × 10⁵ | |
| timestamps | all unique (tᵢ ≠ tⱼ) | Guaranteed by spec — no same-timestamp different-amount confusion |
| k range | within a calendar year | No multi-year spans |

---

## 8. Deployment

### Dockerfile (FastAPI version)
```dockerfile
# docker build -t blk-hacking-ind-{name-lastname} .
FROM python:3.11-slim
# python:3.11-slim chosen: Debian-based, minimal size (~150MB), production-stable,
# good uvicorn/FastAPI support, widely used in production Python APIs
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5477
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5477"]
```

| Requirement | Value |
|-------------|-------|
| Port (internal + external) | `5477` |
| Docker run | `docker run -d -p 5477:5477 blk-hacking-ind-{name-lastname}` |
| Line 1 of Dockerfile | Build command as a comment |
| Base OS | Linux (Debian slim) |
| External services? | Use `compose.yaml` (not `docker-compose.yml`) |

---

## 9. Testing Requirements

Tests go in `/test` folder. Each test file must include as a **comment** at the top:
1. Test type (unit / integration)
2. Validation being executed
3. Run command with arguments

**Run command:** `pytest test/ -v`

**Required test coverage:**

| Area | Cases |
|------|-------|
| Ceiling | Normal case, exact multiple of 100, large amount |
| Remanent | Basic calc, exact multiple → remanent=0 |
| EP2 Validation | Negative, duplicate, amount > wage, all three valid |
| q period | Single match, multiple matches (latest start wins), no match |
| p period | Single match, multiple matches (all added), no match |
| q + p stacking | Transaction in both → `q.fixed + p.extra` |
| k period | In one k, in multiple k (counted independently), in no k (dropped) |
| Returns formula | Compound interest math, inflation adjustment |
| t calculation | age < 60 → 60-age, age >= 60 → t=5 |
| NPS tax benefit | income < ₹7L (benefit=0), income > ₹7L (benefit > 0), deduction cap |
| Index tax | Always 0.0 regardless of invested amount |
| Performance | Response shape, time format matches `YYYY-MM-DD HH:mm:ss.SSS` |


