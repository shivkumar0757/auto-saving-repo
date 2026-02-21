"""
app/main.py -- FastAPI application entry point.

START_TIME and PROCESS are set at module level (singleton pattern).
All routes registered under /blackrock/challenge/v1.
Server runs on port 5477.
"""
from __future__ import annotations

from datetime import datetime, timezone

import psutil
import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from routes import filter as _filter_route
from routes import parse as _parse_route
from routes import performance as _perf_route
from routes import returns as _returns_route
from routes import validator as _validator_route

# Singleton performance tracking -- captured once at boot
START_TIME: datetime = datetime.now(timezone.utc)
PROCESS: psutil.Process = psutil.Process()

# FastAPI app
app = FastAPI(
    title="BlackRock Auto-Savings API",
    version="1.0.0",
    description="Micro-savings round-up API for retirement planning.",
)

# ---------------------------------------------------------------------------
# Custom validation error handler -- return 400 with clean message
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    if errors:
        # Pydantic v2 stores the message in "msg"
        msg = errors[0].get("msg", "Validation error")
        # Strip "Value error, " prefix added by Pydantic v2 for ValueError
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
    else:
        msg = "Validation error"
    return JSONResponse(status_code=400, content={"detail": msg})


# ---------------------------------------------------------------------------
# Register routes
# ---------------------------------------------------------------------------

BASE = "/blackrock/challenge/v1"

app.include_router(_parse_route.router, prefix=BASE)
app.include_router(_validator_route.router, prefix=BASE)
app.include_router(_filter_route.router, prefix=BASE)
app.include_router(_returns_route.router, prefix=BASE)
app.include_router(_perf_route.router, prefix=BASE)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=5477, reload=False)
