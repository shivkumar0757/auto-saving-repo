# BlackRock Auto-Savings API

A stateless REST API that automates micro-savings by rounding up every expense to the next ₹100 and investing the difference toward retirement.

## Stack
- **Python 3.12** + **FastAPI** + **Uvicorn**
- **NumPy** — vectorized ceiling/remanent math
- **IntervalTree** — O(n log p) period matching
- **Pydantic v2** — request/response models with date parsing
- **psutil** — performance metrics

---

## Quick Start

```bash
# Create and activate virtual environment
python3.12 -m venv venv
source venv/bin/activate         # Linux/Mac
# or: venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn app.main:app --host 0.0.0.0 --port 5477
```

Server runs on **port 5477**:  
`http://localhost:5477/blackrock/challenge/v1`

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/transactions:parse` | Round up expenses → ceiling + remanent |
| POST | `/transactions:validator` | Validate transactions (negatives, duplicates, wage) |
| POST | `/transactions:filter` | Apply q/p/k period rules, return valid/invalid |
| POST | `/returns:nps` | NPS retirement returns + tax benefit |
| POST | `/returns:index` | NIFTY 50 index fund returns |
| GET  | `/performance` | Uptime, memory, threads |

---

## Docker

```bash
# Build
docker build -t blk-hacking-ind-shiv-kumar .

# Run
docker run -d -p 5477:5477 blk-hacking-ind-shiv-kumar
```

---

## Testing

```bash
pytest test/ -v
```

Individual test files:
```bash
pytest test/test_parser.py -v
pytest test/test_validator.py -v
pytest test/test_periods.py -v
pytest test/test_finance.py -v
pytest test/test_pipeline.py -v
```

---

## Project Structure

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
  parse.py          — EP1
  validator.py      — EP2
  filter.py         — EP3
  returns.py        — EP4a + EP4b
  performance.py    — EP5
test/
  test_parser.py
  test_validator.py
  test_periods.py
  test_finance.py
  test_pipeline.py
```

---

## Key Design Decisions

1. **Date parsing once** — All date strings → `datetime` in Pydantic models. No `strptime` in loops.
2. **IntervalTree built once per request** — Not per transaction. O(n log p) total.
3. **Duplicate key = date only** — Per spec, timestamps are globally unique.
4. **q + p stack** — p always runs after q and adds on top.
5. **k windows in EP4 = grouping only** — Transactions are never dropped; `totalTransactionAmount` includes all valid.
6. **t = max(60 − age, 5)** — Never zero.
7. **Wage is monthly** — `annual_income = wage × 12` for tax calculations.
