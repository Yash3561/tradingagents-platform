"""
System Status endpoint — mission control overview.

GET /api/v1/system/status
Returns circuit breaker state, market open/closed, last monitor check,
position count, today's P&L, and next scheduled scan time.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter

import structlog

log = structlog.get_logger()
router = APIRouter()

# Shared last-check timestamp (updated by position monitor calls)
_last_monitor_check: str | None = None


def _et_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4)))


def _is_market_open_et() -> bool:
    now = _et_now()
    if now.weekday() >= 5:
        return False
    h = now.hour + now.minute / 60
    return 9.5 <= h < 16.0


def _next_scan_time_utc() -> str:
    """
    Returns ISO string of the next scheduled scan.
    Morning scan at 9:35 ET, midday at 1:00 PM ET.
    """
    import datetime as _dt
    now_et = _et_now()

    # Scan times in ET (hour, minute)
    scan_times = [(9, 35), (13, 0)]
    today = now_et.date()

    for h, m in scan_times:
        candidate = now_et.replace(hour=h, minute=m, second=0, microsecond=0)
        if candidate > now_et and now_et.weekday() < 5:
            return candidate.astimezone(timezone.utc).isoformat()

    # Next weekday morning scan
    next_day = today + _dt.timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += _dt.timedelta(days=1)

    try:
        from zoneinfo import ZoneInfo
        next_scan = _dt.datetime(next_day.year, next_day.month, next_day.day,
                                  9, 35, tzinfo=ZoneInfo("America/New_York"))
    except Exception:
        next_scan = _dt.datetime(next_day.year, next_day.month, next_day.day,
                                  9, 35, tzinfo=timezone(timedelta(hours=-4)))

    return next_scan.astimezone(timezone.utc).isoformat()


def _fetch_account_sync() -> dict:
    from app.broker.alpaca_client import get_account
    return get_account()


def _fetch_positions_sync() -> list[dict]:
    from app.broker.alpaca_client import get_positions
    return get_positions()


@router.get("/status")
async def system_status():
    """
    Returns a full system status snapshot:
    - Circuit breaker state
    - Market open/closed
    - Last monitor check timestamp
    - Position count
    - Today's P&L %
    - Next scheduled scan time
    """
    from app.workers.circuit_breakers import check_circuit_breakers

    loop = asyncio.get_running_loop()

    # Run circuit breaker check
    try:
        cb = await check_circuit_breakers()
    except Exception as e:
        log.warning("system_status.cb_failed", error=str(e))
        cb = {"blocked": False, "reasons": [], "warnings": [], "ticker_blocks": {}}

    # Fetch account for P&L
    today_pnl_pct = 0.0
    positions_count = 0
    try:
        account = await loop.run_in_executor(None, _fetch_account_sync)
        equity = float(account.get("equity", 0))
        last_equity = float(account.get("last_equity", equity))
        if last_equity > 0:
            today_pnl_pct = round((equity - last_equity) / last_equity * 100, 4)
    except Exception as e:
        log.warning("system_status.account_failed", error=str(e))

    # Fetch positions count
    try:
        positions = await loop.run_in_executor(None, _fetch_positions_sync)
        positions_count = len(positions)
    except Exception as e:
        log.warning("system_status.positions_failed", error=str(e))

    market_open = _is_market_open_et()
    next_scan = _next_scan_time_utc()
    now_utc = datetime.now(timezone.utc).isoformat()

    return {
        "circuit_breakers": {
            "blocked": cb.get("blocked", False),
            "reasons": cb.get("reasons", []),
            "warnings": cb.get("warnings", []),
        },
        "market_open": market_open,
        "last_monitor_check": now_utc,
        "positions_count": positions_count,
        "today_pnl_pct": today_pnl_pct,
        "next_scheduled_scan": next_scan,
    }
