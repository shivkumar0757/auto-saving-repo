"""
routes/performance.py -- EP5: Performance Report (GET /performance)

Reads START_TIME and PROCESS from app.main (set once at module load).
Returns uptime, memory usage (MB, no unit suffix), and thread count.

Memory format: "XX.XX" -- no "MB" suffix in the value string.
Time format:   "YYYY-MM-DD HH:mm:ss.SSS" -- milliseconds, no microseconds.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter

from app.models import PerformanceResponse

router = APIRouter()


def _format_uptime(uptime: timedelta) -> str:
    """Format a timedelta as 'YYYY-MM-DD HH:mm:ss.SSS' using epoch as base."""
    dt = datetime(1970, 1, 1) + uptime
    ms = dt.microsecond // 1000
    return dt.strftime("%Y-%m-%d %H:%M:%S") + f".{ms:03d}"


@router.get("/performance", response_model=PerformanceResponse)
def performance():
    """
    EP5 -- Returns system uptime, memory usage, and thread count.
    START_TIME and PROCESS are imported lazily to avoid circular imports.
    """
    # Lazy import to avoid circular dependency at module load time
    import app.main as _main

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    uptime = now - _main.START_TIME.replace(tzinfo=None)

    time_str = _format_uptime(uptime)

    # Memory in MB -- "XX.XX" format, no unit suffix
    mem_info = _main.PROCESS.memory_info()
    mem_mb = mem_info.rss / (1024 * 1024)
    memory_str = f"{mem_mb:.2f}"

    # Thread count
    threads = _main.PROCESS.num_threads()

    return PerformanceResponse(
        time=time_str,
        memory=memory_str,
        threads=threads,
    )
