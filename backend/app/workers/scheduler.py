"""
Market Scheduler — triggers scans at optimal market times.

Schedule (ET):
  09:35  Morning scan — top opportunities at open
  13:00  Midday scan — momentum continuation setups
  15:45  EOD equity snapshot before close
  every 15 min (market hours)  Intraday position reviewer

All times use Alpaca's /v2/clock to verify market is actually open.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta
import structlog

log = structlog.get_logger()

# ET timezone offset (UTC-4 in EDT, UTC-5 in EST)
# Use Alpaca clock for truth — don't hardcode TZ math
ET = timezone.utc  # we compare UTC times from Alpaca clock

# Track last circuit breaker warnings so we only notify on NEW ones
_last_cb_warnings: set[str] = set()


def _get_market_clock(broker=None) -> dict:
    """Market clock via any configured Alpaca client (env default or a user's)."""
    from app.broker.alpaca_client import default_client
    try:
        client = broker or default_client()
        if not client.configured:
            return {"is_open": False, "next_open": None}
        return client.get_clock()
    except Exception as e:
        log.warning("scheduler.clock_failed", error=str(e))
        return {"is_open": False, "next_open": None}


async def _any_broker():
    """First available Alpaca client: env default, else any connected user's."""
    from app.broker.alpaca_client import default_client
    from app.broker.credentials import connected_user_ids, get_client_for_user

    client = default_client()
    if client.configured:
        return client
    for uid in await connected_user_ids():
        c = await get_client_for_user(uid)
        if c is not None:
            return c
    return None


async def _autoscan_user_ids() -> list[int]:
    """Users who explicitly opted in to scheduled auto-scans (scan_enabled user setting)."""
    import json
    from sqlalchemy import select
    from app.core.postgres import AsyncSessionLocal
    from app.db.models.user_settings import UserSettings
    from app.broker.credentials import connected_user_ids

    connected = set(await connected_user_ids())
    if not connected:
        return []
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UserSettings).where(UserSettings.key == "scan_enabled")
            )
            rows = result.scalars().all()
        enabled = set()
        for r in rows:
            try:
                if json.loads(r.value) is True:
                    enabled.add(r.user_id)
            except Exception:
                pass
        return sorted(enabled & connected)
    except Exception as e:
        log.warning("scheduler.autoscan_users_failed", error=str(e))
        return []


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
        Trigger scheduled scans — one per user who opted in (scan_enabled=true
        in their settings and a connected broker). Each scan trades in that
        user's own paper account.
        """
        import uuid as _uuid
        from app.workers.scanner import run_market_scan
        from app.core.websocket_manager import ws_manager
        from app.api.v1.notifications import save_notification

        now_str = datetime.now(timezone.utc).isoformat()

        vix_high = vix is not None and vix > 30
        if vix_high:
            log.warning("scheduler.vix_gate_active", vix=round(vix, 1),
                        note="BUYs suppressed — only SELL candidates will pass AI pipeline")

        user_ids = await _autoscan_user_ids()
        if not user_ids:
            log.info(f"scheduler.scan.{label}.no_optin_users")
            return

        log.info(f"scheduler.scan.{label}", vix=vix, users=len(user_ids))

        for uid in user_ids:
            scan_id = str(_uuid.uuid4())
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
                user_id=uid,
            )

            try:
                summary = await run_market_scan(vix_override=vix, scan_id=scan_id, user_id=uid)
                trades_placed = summary.get("trades_placed", 0)
                candidates = summary.get("candidates_analyzed", 0)
                log.info(f"scheduler.scan.{label}.done", user_id=uid,
                         candidates=candidates, trades=trades_placed)
                await save_notification(
                    type="scan_complete",
                    title=f"Scheduled {label} scan completed",
                    body=(
                        f"Analyzed {candidates} candidates, placed {trades_placed} trade(s). "
                        f"Screened {summary.get('screened', 0)} stocks."
                    ),
                    user_id=uid,
                )
            except Exception as e:
                log.error(f"scheduler.scan.{label}.failed", user_id=uid, error=str(e))

    async def tick(self):
        """
        Called every 60 seconds from the main scheduler loop.
        Decides whether to trigger a scan based on current time.
        """
        loop = asyncio.get_running_loop()
        broker = await _any_broker()
        clock = await loop.run_in_executor(None, _get_market_clock, broker)

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


def _et_now() -> datetime:
    """Return current datetime in US/Eastern (handles DST automatically)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4)))


def _is_market_hours_et() -> bool:
    """True if current ET time is between 9:30 AM and 4:00 PM on a weekday."""
    now = _et_now()
    if now.weekday() >= 5:
        return False
    h = now.hour + now.minute / 60
    return 9.5 <= h < 16.0


async def _all_accounts() -> list[tuple[int | None, object]]:
    """(user_id, broker) pairs for every connected user + the legacy env account."""
    from app.broker.credentials import connected_user_ids, get_client_for_user
    from app.broker.alpaca_client import default_client

    accounts: list[tuple[int | None, object]] = []
    for uid in await connected_user_ids():
        client = await get_client_for_user(uid)
        if client is not None:
            accounts.append((uid, client))
    legacy = default_client()
    if legacy.configured:
        accounts.append((None, legacy))
    return accounts


async def _take_equity_snapshot():
    """Snapshot every account's equity (delegates to the per-user equity tracker)."""
    try:
        from app.workers.equity_tracker import take_snapshot
        taken = await take_snapshot()
        log.info("scheduler.equity_snapshot", accounts=taken)
    except Exception as e:
        log.warning("scheduler.snapshot_failed", error=str(e))


async def _run_intraday_cb_check():
    """Check circuit breakers and notify on NEW warnings."""
    global _last_cb_warnings
    from app.workers.circuit_breakers import check_circuit_breakers
    from app.api.v1.notifications import save_notification

    try:
        cb = await check_circuit_breakers()
        current_warnings = set(cb.get("warnings", []) + cb.get("reasons", []))
        new_warnings = current_warnings - _last_cb_warnings
        if new_warnings:
            for w in new_warnings:
                log.warning("intraday.cb_new_warning", warning=w)
            _last_cb_warnings = current_warnings
    except Exception as e:
        log.warning("intraday.cb_check_failed", error=str(e))


async def run_intraday_monitor():
    """
    Intraday position reviewer — runs every 15 minutes during market hours.
    Checks unrealized intraday P&L and sends alerts on big moves.
    At 3:45 PM ET sends a pre-close review.
    Also checks circuit breakers and sends notifications on new warnings.
    """
    from app.api.v1.notifications import save_notification

    log.info("intraday_monitor.started")

    # Track which 15-min windows we've already processed today
    _processed_windows: set[str] = set()
    _last_date: str = ""

    while True:
        await asyncio.sleep(60)  # check every 60 seconds, act on 15-min windows

        try:
            now_et = _et_now()
            today = now_et.strftime("%Y-%m-%d")

            # Reset daily tracking on new day
            if today != _last_date:
                _processed_windows.clear()
                _last_date = today

            if not _is_market_hours_et():
                continue

            # Build 15-minute window key: e.g. "2026-06-30T09:30"
            # Floor to 15-minute boundary
            window_minute = (now_et.minute // 15) * 15
            window_key = f"{today}T{now_et.hour:02d}:{window_minute:02d}"

            if window_key in _processed_windows:
                continue

            _processed_windows.add(window_key)
            log.info("intraday_monitor.tick", window=window_key)

            # ── Circuit breaker check ──────────────────────────────────────────
            asyncio.create_task(_run_intraday_cb_check())

            # Hourly equity snapshot during market hours
            is_market_hours = _is_market_hours_et()
            if is_market_hours and now_et.minute == 0:  # top of each hour
                await _take_equity_snapshot()

            # ── Fetch positions per account ────────────────────────────────────
            loop = asyncio.get_running_loop()
            is_preclose = False
            now_h = now_et.hour + now_et.minute / 60
            if 15.75 <= now_h < 15.92 and f"{today}T15:45_preclose" not in _processed_windows:
                _processed_windows.add(f"{today}T15:45_preclose")
                is_preclose = True

            for uid, account_broker in await _all_accounts():
                try:
                    positions = await loop.run_in_executor(None, account_broker.get_positions)
                except Exception as e:
                    log.warning("intraday_monitor.positions_fetch_failed",
                                user_id=uid, error=str(e))
                    continue

                if not positions:
                    continue

                position_summaries = []

                for pos in positions:
                    ticker = pos.get("symbol") or pos.get("ticker", "")
                    if not ticker:
                        continue

                    try:
                        # unrealized_intraday_plpc is already a string like "0.0234"
                        intraday_plpc_raw = pos.get("unrealized_intraday_plpc", "0")
                        intraday_pct = float(intraday_plpc_raw) * 100  # convert to percent

                        unrealized_pnl = float(pos.get("unrealized_pl", 0) or 0)
                        market_val = float(pos.get("market_value", 0) or 0)

                        position_summaries.append({
                            "ticker": ticker,
                            "intraday_pct": round(intraday_pct, 2),
                            "unrealized_pnl": round(unrealized_pnl, 2),
                            "market_value": round(market_val, 2),
                        })

                        # Alert on big intraday moves
                        if intraday_pct > 8 or intraday_pct < -4:
                            log.warning("intraday_monitor.big_move", user_id=uid,
                                        ticker=ticker, intraday_pct=round(intraday_pct, 2))
                            await save_notification(
                                type="intraday_alert",
                                title=f"{ticker} moved {intraday_pct:+.1f}% intraday",
                                body="Position under review — consider action",
                                ticker=ticker,
                                user_id=uid,
                            )
                    except Exception as e:
                        log.warning("intraday_monitor.position_parse_failed",
                                    ticker=ticker, error=str(e))

                # ── 3:45 PM ET pre-close review ───────────────────────────────
                if is_preclose:
                    summary_lines = [
                        f"{s['ticker']}: {s['intraday_pct']:+.1f}% intraday, P&L ${s['unrealized_pnl']:+,.2f}"
                        for s in position_summaries
                    ]
                    body = "Open positions:\n" + "\n".join(summary_lines) if summary_lines else "No open positions."

                    await save_notification(
                        type="pre_close_review",
                        title=f"Pre-close review — {now_et.strftime('%I:%M %p ET')}",
                        body=body,
                        user_id=uid,
                    )
                    log.info("intraday_monitor.preclose_review_sent", user_id=uid,
                             positions=len(position_summaries))

        except Exception as e:
            log.error("intraday_monitor.cycle_error", error=str(e))


async def run_scheduler():
    """
    Main scheduler loop — ticks every 60 seconds.
    Also starts intraday monitor as an independent asyncio task.
    Called from main.py lifespan — runs forever.
    """
    log.info("scheduler.started")
    sched = MarketScheduler()

    # Start intraday monitor as independent task
    asyncio.create_task(run_intraday_monitor())
    log.info("scheduler.intraday_monitor_started")

    while True:
        try:
            await sched.tick()
        except Exception as e:
            log.error("scheduler.tick_error", error=str(e))
        await asyncio.sleep(60)
