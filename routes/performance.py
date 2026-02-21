"""
routes/performance.py -- EP5: Performance Report (GET /performance)

Reads START_TIME and PROCESS from app.main (set once at module load).
Returns uptime, memory usage (MB, no unit suffix), and thread count.

Memory format: "XX.XX" -- no "MB" suffix in the value string.
Time format:   "YYYY-MM-DD HH:mm:ss.SSS" -- milliseconds, no microseconds.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone  # datetime used for now()

from fastapi import APIRouter

from app.models import PerformanceResponse

router = APIRouter()


def _format_uptime(uptime: timedelta) -> str:
    """Format a timedelta as 'HH:mm:ss.SSS' (time-only, no date prefix)."""
    total_seconds = int(uptime.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    ms = uptime.microseconds // 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"


@router.get("/performance", response_model=PerformanceResponse)
def performance() -> PerformanceResponse:
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
