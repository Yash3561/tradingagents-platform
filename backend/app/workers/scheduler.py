"""
Market Scheduler — triggers scans at optimal market times.

Schedule (ET):
  09:35  Morning scan — top opportunities at open
  13:00  Midday scan — momentum continuation setups
  15:45  EOD equity snapshot before close

All times use Alpaca's /v2/clock to verify market is actually open.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import structlog

log = structlog.get_logger()

# ET timezone offset (UTC-4 in EDT, UTC-5 in EST)
# Use Alpaca clock for truth — don't hardcode TZ math
ET = timezone.utc  # we compare UTC times from Alpaca clock


def _get_market_clock() -> dict:
    from app.broker.alpaca_client import _headers
    from app.config import get_settings
    import httpx
    settings = get_settings()
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(
                f"{settings.alpaca_base_url}/v2/clock",
                headers=_headers(),
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log.warning("scheduler.clock_failed", error=str(e))
        return {"is_open": False, "next_open": None}


def _get_vix() -> float | None:
    """Fetch current VIX from yfinance. Returns None on failure."""
    try:
        import yfinance as yf
        vix = yf.Ticker("^VIX")
        hist = vix.history(period="1d", interval="1m")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None


class MarketScheduler:
    def __init__(self):
        self._scans_run_today: set[str] = set()   # "morning" | "midday"
        self._last_date: str = ""
        self._market_open_notified: bool = False

    def _reset_if_new_day(self, today: str):
        if today != self._last_date:
            self._scans_run_today.clear()
            self._last_date = today
            self._market_open_notified = False
            log.info("scheduler.new_day", date=today)

    async def _run_scan(self, label: str, vix: float | None):
        """
        Trigger a market scan. If VIX > 30, passes a sells-only hint to scanner.
        The scanner itself gates BUY signals when VIX is elevated.
        Broadcasts WS event and saves a Notification on start and completion.
        """
        import uuid as _uuid
        from app.workers.scanner import run_market_scan
        from app.core.websocket_manager import ws_manager
        from app.api.v1.notifications import save_notification

        scan_id = str(_uuid.uuid4())
        now_str = datetime.now(timezone.utc).isoformat()

        vix_high = vix is not None and vix > 30
        if vix_high:
            log.warning("scheduler.vix_gate_active", vix=round(vix, 1),
                        note="BUYs suppressed — only SELL candidates will pass AI pipeline")

        log.info(f"scheduler.scan.{label}", vix=vix)

        # Broadcast scan started
        await ws_manager.broadcast("alerts", {
            "type": "scheduled_scan_started",
            "label": label,
            "scan_id": scan_id,
            "time": now_str,
        })
        await save_notification(
            type="scheduled_scan",
            title=f"Scheduled {label} scan started",
            body=f"Auto-scan triggered at {now_str[:16].replace('T', ' ')} UTC. VIX: {round(vix, 1) if vix else 'N/A'}",
        )

        try:
            summary = await run_market_scan(vix_override=vix, scan_id=scan_id)
            trades_placed = summary.get("trades_placed", 0)
            candidates = summary.get("candidates_analyzed", 0)
            log.info(f"scheduler.scan.{label}.done",
                     candidates=candidates,
                     trades=trades_placed)
            await save_notification(
                type="scan_complete",
                title=f"Scheduled {label} scan completed",
                body=(
                    f"Analyzed {candidates} candidates, placed {trades_placed} trade(s). "
                    f"Screened {summary.get('screened', 0)} stocks."
                ),
            )
        except Exception as e:
            log.error(f"scheduler.scan.{label}.failed", error=str(e))

    async def tick(self):
        """
        Called every 60 seconds from the main scheduler loop.
        Decides whether to trigger a scan based on current time.
        """
        loop = asyncio.get_running_loop()
        clock = await loop.run_in_executor(None, _get_market_clock)

        now_utc = datetime.now(timezone.utc)
        today = now_utc.strftime("%Y-%m-%d")
        self._reset_if_new_day(today)

        is_open = clock.get("is_open", False)

        if not is_open:
            return

        # Fetch VIX once per tick (cached implicitly via yfinance)
        vix = await loop.run_in_executor(None, _get_vix)

        # Determine current time in ET by using Alpaca's next_close
        # We work in UTC hours to avoid pytz dependency
        # NYSE open = 13:30 UTC (9:30 ET), close = 20:00 UTC (4pm ET) in EDT
        utc_hour = now_utc.hour
        utc_minute = now_utc.minute
        utc_time = utc_hour * 60 + utc_minute  # minutes since midnight UTC

        # Morning scan: 9:35 ET = 13:35 UTC (EDT) or 14:35 UTC (EST)
        # Use a 5-min window to avoid missing it
        MORNING_UTC_MIN = 13 * 60 + 35   # 13:35
        MIDDAY_UTC_MIN = 17 * 60 + 0     # 13:00 ET = 17:00 UTC
        EOD_UTC_MIN = 19 * 60 + 45       # 15:45 ET = 19:45 UTC

        if "morning" not in self._scans_run_today:
            if MORNING_UTC_MIN <= utc_time <= MORNING_UTC_MIN + 5:
                self._scans_run_today.add("morning")
                log.info("scheduler.morning_scan_triggered")
                asyncio.create_task(self._run_scan("morning", vix))

        if "midday" not in self._scans_run_today:
            if MIDDAY_UTC_MIN <= utc_time <= MIDDAY_UTC_MIN + 5:
                self._scans_run_today.add("midday")
                log.info("scheduler.midday_scan_triggered")
                asyncio.create_task(self._run_scan("midday", vix))

        if "eod_snapshot" not in self._scans_run_today:
            if EOD_UTC_MIN <= utc_time <= EOD_UTC_MIN + 5:
                self._scans_run_today.add("eod_snapshot")
                from app.workers.equity_tracker import take_snapshot
                log.info("scheduler.eod_snapshot")
                asyncio.create_task(take_snapshot())


async def run_scheduler():
    """
    Main scheduler loop — ticks every 60 seconds.
    Called from workers/main.py — runs forever.
    """
    log.info("scheduler.started")
    sched = MarketScheduler()

    while True:
        try:
            await sched.tick()
        except Exception as e:
            log.error("scheduler.tick_error", error=str(e))
        await asyncio.sleep(60)
