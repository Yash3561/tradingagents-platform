"""
Intraday engine — deterministic 5-minute rule trading, zero LLM calls.

Runs as a background loop during regular trading hours for every user whose
strategy_mode setting is "intraday" (and scan_enabled=true + broker connected).

Lifecycle per entry mirrors the other engines: an AgentRun row tagged
llm_model="intraday-rules" plus a Trade row, so Strategy Lab / track record
compare apples-to-apples.

Execution model:
- Signals come from app.research.intraday (the SAME code the walk-forward
  tournament validates — no live/backtest drift). Signal on a completed 5m
  bar → entry at market with a native Alpaca bracket (day TIF is correct
  here: intraday positions never survive the close by design).
- This loop adds what brackets can't do: time exits, 15:55 ET force-flat,
  and a daily loss halt (realized+unrealized) that flattens and disables
  entries for the rest of the session.
- Only positions opened BY this engine are ever touched — swing positions
  held by the same account (agents/quant arms) are invisible to it.

Seatbelts (non-negotiable):
- max trades/day, max concurrent, per-position notional cap 25% equity,
  gross cap 100% equity (no leverage), no entries after 15:00 ET,
  daily loss halt, EOD flat. Fails closed on data errors (skip cycle).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, time as dtime, timedelta, UTC
from zoneinfo import ZoneInfo

import structlog

log = structlog.get_logger()

ET = ZoneInfo("America/New_York")
INTRADAY_MODEL_LABEL = "intraday-rules"

POLL_SECONDS = 10          # position-management cadence
BAR_SECONDS = 300          # signal cadence (new completed 5m bar)
MAX_NOTIONAL_PCT = 25.0
MAX_GROSS_PCT = 100.0
NO_ENTRY_AFTER = dtime(15, 0)
EOD_FLAT_AT = dtime(15, 55)

# Per-user overridable via intraday_* settings (deploy tournament winners as
# settings, no code change). Defaults = the most robust round-1 profile at
# conservative risk. See docs/research/intraday-walkforward-*.json.
INTRADAY_PARAM_DEFAULTS = {
    "intraday_setup": "mom",            # orb | vwaprev | mom
    "intraday_or_minutes": 30,
    "intraday_vol_ratio_min": 1.0,
    "intraday_above_vwap": True,
    "intraday_dev_entry_atr": 1.5,
    "intraday_rsi_max": 100.0,
    "intraday_stop_atr_mult": 1.5,
    "intraday_rr": 2.0,
    "intraday_max_hold_bars": 0,        # 0 = hold to EOD
    "intraday_risk_pct": 0.5,
    "intraday_max_trades_day": 6,
    "intraday_max_concurrent": 3,
    "intraday_daily_loss_halt_pct": 0.5,
}

UNIVERSE_CAP = 30


async def _load_params(user_id: int) -> dict:
    from app.db.models.user_settings import get_user_setting
    params = {}
    for key, default in INTRADAY_PARAM_DEFAULTS.items():
        v = await get_user_setting(user_id, key, default)
        if isinstance(default, bool):
            params[key] = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes")
        elif isinstance(default, str):
            params[key] = str(v)
        else:
            params[key] = float(v)
    return params


def _policy_from(params: dict):
    from app.research.intraday import IntradayPolicy
    hold = int(params["intraday_max_hold_bars"])
    return IntradayPolicy(
        setup=params["intraday_setup"],
        or_minutes=int(params["intraday_or_minutes"]),
        vol_ratio_min=params["intraday_vol_ratio_min"],
        above_vwap=params["intraday_above_vwap"],
        dev_entry_atr=params["intraday_dev_entry_atr"],
        rsi_max=params["intraday_rsi_max"],
        stop_atr_mult=params["intraday_stop_atr_mult"],
        rr=params["intraday_rr"],
        max_hold_bars=hold or None,
        risk_pct=params["intraday_risk_pct"],
        max_trades_day=int(params["intraday_max_trades_day"]),
        max_concurrent=int(params["intraday_max_concurrent"]),
    )


# ── Per-user session state (reset each trading day) ──────────────────────────

class UserSession:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.day: str | None = None
        self.trades_today = 0
        self.halted = False
        self.last_bar_scan: datetime | None = None
        # ticker → {trade_id, run_id, qty, entry, opened_bar_at, order_id}
        self.open: dict[str, dict] = {}

    def roll_day(self, today: str):
        if self.day != today:
            self.day = today
            self.trades_today = 0
            self.halted = False
            self.last_bar_scan = None
            self.open = {}


_sessions: dict[int, UserSession] = {}


# ── Market data (per-user keys, IEX feed) ────────────────────────────────────

def _fetch_bars(broker, symbols: list[str], lookback_days: int = 5) -> dict:
    """Recent 5m bars per symbol via Alpaca data API. Sync (executor)."""
    import httpx

    start = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    out: dict[str, list] = {}
    page = None
    with httpx.Client(timeout=20.0) as client:
        while True:
            params = {"symbols": ",".join(symbols), "timeframe": "5Min",
                      "start": start, "limit": 10_000, "feed": "iex",
                      "adjustment": "raw"}
            if page:
                params["page_token"] = page
            r = client.get("https://data.alpaca.markets/v2/stocks/bars",
                           headers=broker.headers(), params=params)
            r.raise_for_status()
            j = r.json()
            for sym, bars in (j.get("bars") or {}).items():
                out.setdefault(sym, []).extend(bars)
            page = j.get("next_page_token")
            if not page:
                return out


def _bars_to_series(bars: dict) -> dict:
    """Alpaca bar lists → research TickerSeries (RTH only, ET index)."""
    import pandas as pd
    from app.research.intraday import TickerSeries

    series = {}
    for sym, rows in bars.items():
        if len(rows) < 40:
            continue
        df = pd.DataFrame(rows)
        df["t"] = pd.to_datetime(df["t"], utc=True)
        df = df.set_index("t").tz_convert(ET).sort_index()
        df = df.rename(columns={"o": "Open", "h": "High", "l": "Low",
                                "c": "Close", "v": "Volume"})
        df = df[(df.index.time >= dtime(9, 30)) & (df.index.time < dtime(16, 0))]
        # drop the still-forming bar — signals only ever fire on completed bars
        cutoff = datetime.now(ET) - timedelta(seconds=BAR_SECONDS)
        df = df[df.index <= cutoff]
        if len(df) >= 40:
            series[sym] = TickerSeries(df[["Open", "High", "Low", "Close", "Volume"]])
    return series


async def _universe(user_id: int) -> list[str]:
    """User watchlist if set, else the research universe. Capped."""
    from app.db.models.user_settings import get_user_setting
    from app.research.intraday import UNIVERSE
    wl = await get_user_setting(user_id, "custom_watchlist", None)
    if isinstance(wl, str) and wl.strip():
        symbols = [s.strip().upper() for s in wl.split(",") if s.strip()]
        if symbols:
            return symbols[:UNIVERSE_CAP]
    return UNIVERSE[:UNIVERSE_CAP]


# ── Persistence (AgentRun + Trade rows, same shape as other engines) ─────────

async def _record_entry(user_id: int, ticker: str, qty: int, entry_ref: float,
                        stop_px: float, target_px: float, setup: str,
                        order: dict, policy_label: str) -> tuple[str, str]:
    from app.core.postgres import AsyncSessionLocal
    from app.db.models.agent_run import AgentRun
    from app.db.models.trade import Trade

    run_id = str(uuid.uuid4())
    trade_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    stop_pct = round((entry_ref - stop_px) / entry_ref * 100, 2)
    tp_pct = round((target_px - entry_ref) / entry_ref * 100, 2)
    summary = (f"[Intraday Rules] {setup} entry on {ticker}: {qty} shares, "
               f"stop {stop_pct}% / target {tp_pct}%, flat by 15:55 ET. "
               f"Policy: {policy_label}")

    async with AsyncSessionLocal() as db:
        db.add(AgentRun(
            id=run_id, ticker=ticker, user_id=user_id,
            analysis_date=now.strftime("%Y-%m-%d"), status="completed",
            decision="BUY", confidence=0.65, summary=summary,
            debate_log=[{"agent": "Intraday Engine", "role": "quant",
                         "content": summary, "signal": "BUY", "confidence": 0.65}],
            reasoning_json={"engine": INTRADAY_MODEL_LABEL, "setup": setup,
                            "policy": policy_label, "stop_px": stop_px,
                            "target_px": target_px},
            llm_model=INTRADAY_MODEL_LABEL, debate_rounds=0,
            created_at=now, completed_at=now,
        ))
        db.add(Trade(
            id=trade_id, user_id=user_id, agent_run_id=run_id,
            alpaca_order_id=order.get("id"), ticker=ticker, side="buy",
            qty=qty, order_type="market", status="submitted",
            stop_loss_pct=stop_pct, take_profit_pct=tp_pct,
            reasoning_json={"engine": INTRADAY_MODEL_LABEL, "setup": setup,
                            "policy": policy_label,
                            "alpaca_order": {"id": order.get("id"),
                                             "status": order.get("status")}},
        ))
        await db.commit()
    return run_id, trade_id


async def _mark_closed(trade_id: str, reason: str, pnl: float | None):
    from app.core.postgres import AsyncSessionLocal
    from app.db.models.trade import Trade
    async with AsyncSessionLocal() as db:
        t = await db.get(Trade, trade_id)
        if t and t.closed_at is None:
            t.status = "closed"
            t.closed_reason = reason
            if pnl is not None:
                t.pnl = round(pnl, 2)
            t.closed_at = datetime.now(UTC)
            await db.commit()


async def _restore_open(sess: UserSession):
    """After a restart, re-adopt this engine's still-open trades from the DB."""
    from sqlalchemy import select
    from app.core.postgres import AsyncSessionLocal
    from app.db.models.trade import Trade

    async with AsyncSessionLocal() as db:
        q = select(Trade).where(
            Trade.user_id == sess.user_id,
            Trade.closed_at.is_(None),
            Trade.status.in_(["submitted", "filled", "partial"]),
        )
        for t in (await db.execute(q)).scalars():
            rj = t.reasoning_json or {}
            if rj.get("engine") == INTRADAY_MODEL_LABEL:
                sess.open[t.ticker] = {
                    "trade_id": t.id, "qty": float(t.qty),
                    "entry": float(t.filled_price or 0) or None,
                    "opened_at": t.submitted_at,
                    "order_id": t.alpaca_order_id,
                }
                sess.trades_today += 1


# ── Core cycle ────────────────────────────────────────────────────────────────

async def _flatten(sess: UserSession, broker, reason: str):
    loop = asyncio.get_running_loop()
    for ticker, p in list(sess.open.items()):
        try:
            # cancel bracket legs first so DELETE /positions isn't rejected
            open_orders = await loop.run_in_executor(None, broker.get_orders, "open", 100)
            for o in open_orders:
                if o.get("symbol") == ticker:
                    await loop.run_in_executor(None, broker.cancel_order, o["id"])
            pos = await loop.run_in_executor(None, broker.get_position, ticker)
            pnl = None
            if pos:
                await loop.run_in_executor(None, broker.close_position, ticker)
                pnl = float(pos.get("unrealized_pl", 0) or 0)
            await _mark_closed(p["trade_id"], reason, pnl)
            log.info("intraday.flattened", user_id=sess.user_id, ticker=ticker,
                     reason=reason, pnl=pnl)
        except Exception as e:
            log.error("intraday.flatten_failed", user_id=sess.user_id,
                      ticker=ticker, error=str(e))
        finally:
            sess.open.pop(ticker, None)


async def _day_pnl(sess: UserSession, broker) -> float:
    """Realized (closed intraday trades today) + unrealized on open ones."""
    from sqlalchemy import select, func
    from app.core.postgres import AsyncSessionLocal
    from app.db.models.trade import Trade

    today_start = datetime.now(ET).replace(hour=0, minute=0, second=0,
                                           microsecond=0).astimezone(UTC)
    async with AsyncSessionLocal() as db:
        q = select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(
            Trade.user_id == sess.user_id,
            Trade.closed_at >= today_start,
            Trade.reasoning_json["engine"].as_string() == INTRADAY_MODEL_LABEL,
        )
        realized = float((await db.execute(q)).scalar() or 0.0)

    unrealized = 0.0
    if sess.open:
        loop = asyncio.get_running_loop()
        positions = await loop.run_in_executor(None, broker.get_positions)
        held = {p.get("symbol"): p for p in positions}
        for ticker in sess.open:
            if ticker in held:
                unrealized += float(held[ticker].get("unrealized_pl", 0) or 0)
    return realized + unrealized


async def _resolve_bracket_exit(loop, broker, p: dict) -> tuple[float | None, str]:
    """
    Position vanished from the broker between polls — a stop or target leg
    filled it (OCO). Pull the parent bracket order and read whichever child
    leg shows status=filled for the real exit price, so pnl (and the daily
    loss halt that sums it) reflects what actually happened instead of None.
    """
    order_id = p.get("order_id")
    entry = p.get("entry")
    qty = p.get("qty")
    if order_id and entry and qty:
        order = await loop.run_in_executor(None, broker.get_order, order_id)
        for leg in (order or {}).get("legs") or []:
            if leg.get("status") == "filled" and leg.get("filled_avg_price"):
                exit_px = float(leg["filled_avg_price"])
                pnl = round((exit_px - float(entry)) * float(qty), 2)
                reason = ("stop_loss" if leg.get("type") in ("stop", "stop_limit")
                          else "take_profit")
                return pnl, reason
    return None, "bracket_exit"


async def _manage_positions(sess: UserSession, broker, policy, now_et: datetime):
    """Time exits + EOD flat + reconcile bracket-completed exits."""
    loop = asyncio.get_running_loop()
    if not sess.open:
        return

    if now_et.time() >= EOD_FLAT_AT:
        await _flatten(sess, broker, "eod_flat")
        return

    positions = await loop.run_in_executor(None, broker.get_positions)
    held = {p.get("symbol") for p in positions}

    for ticker, p in list(sess.open.items()):
        # bracket leg already closed it at the broker → resolve the real fill
        if ticker not in held:
            pnl, reason = await _resolve_bracket_exit(loop, broker, p)
            await _mark_closed(p["trade_id"], reason, pnl)
            sess.open.pop(ticker, None)
            log.info("intraday.bracket_exit", user_id=sess.user_id, ticker=ticker,
                     reason=reason, pnl=pnl)
            continue
        if policy.max_hold_bars and p.get("opened_at"):
            opened = p["opened_at"]
            if opened.tzinfo is None:
                opened = opened.replace(tzinfo=UTC)
            held_bars = (datetime.now(UTC) - opened).total_seconds() / BAR_SECONDS
            if held_bars >= policy.max_hold_bars:
                open_orders = await loop.run_in_executor(None, broker.get_orders, "open", 100)
                for o in open_orders:
                    if o.get("symbol") == ticker:
                        await loop.run_in_executor(None, broker.cancel_order, o["id"])
                pos = await loop.run_in_executor(None, broker.get_position, ticker)
                pnl = float(pos.get("unrealized_pl", 0) or 0) if pos else None
                await loop.run_in_executor(None, broker.close_position, ticker)
                await _mark_closed(p["trade_id"], "time_exit", pnl)
                sess.open.pop(ticker, None)
                log.info("intraday.time_exit", user_id=sess.user_id, ticker=ticker)


async def _scan_and_enter(sess: UserSession, broker, policy, params: dict,
                          now_et: datetime):
    from app.research.intraday import entry_signal

    if (sess.halted or now_et.time() >= NO_ENTRY_AFTER
            or sess.trades_today >= policy.max_trades_day
            or len(sess.open) >= policy.max_concurrent):
        return

    loop = asyncio.get_running_loop()
    symbols = await _universe(sess.user_id)
    try:
        bars = await loop.run_in_executor(None, _fetch_bars, broker, symbols)
        series = _bars_to_series(bars)
    except Exception as e:
        log.warning("intraday.data_failed", user_id=sess.user_id, error=str(e))
        return  # fail closed: no data, no trades

    account = await loop.run_in_executor(None, broker.get_account)
    equity = float(account.get("equity", 100_000))
    risk_dollars = equity * policy.risk_pct / 100
    max_notional = equity * MAX_NOTIONAL_PCT / 100
    gross = 0.0
    positions = await loop.run_in_executor(None, broker.get_positions)
    for p in positions:
        if p.get("symbol") in sess.open:
            gross += abs(float(p.get("market_value", 0) or 0))

    candidates = []
    for sym, ts in series.items():
        if sym in sess.open:
            continue
        # only act on a bar completed within the last poll window — signals
        # older than one bar were either taken already or are stale
        last_ts = ts.index[-1]
        age = (now_et - last_ts.to_pydatetime()).total_seconds()
        if age > BAR_SECONDS + 60:
            continue
        sig = entry_signal(ts, policy)
        if sig[-1]:
            candidates.append((sym, ts))

    for sym, ts in candidates:
        if (sess.trades_today >= policy.max_trades_day
                or len(sess.open) >= policy.max_concurrent):
            break
        # existing broker position in this ticker (swing arm) → hands off
        existing = await loop.run_in_executor(None, broker.get_position, sym)
        if existing and float(existing.get("qty", 0)) != 0:
            continue
        price = float(ts.close[-1])
        atr = float(ts.atr[-1])
        if not (price > 0 and atr > 0):
            continue
        stop_dist = policy.stop_atr_mult * atr
        notional = min(risk_dollars / stop_dist * price, max_notional,
                       equity * MAX_GROSS_PCT / 100 - gross)
        qty = int(notional / price)
        if qty < 1:
            continue
        stop_px = round(price - stop_dist, 2)
        target_px = round(price + stop_dist * policy.rr, 2)
        try:
            order = await loop.run_in_executor(
                None, lambda s=sym: broker.submit_bracket_order(
                    s, qty, round(stop_dist / price * 100, 2),
                    round(stop_dist * policy.rr / price * 100, 2), price,
                    time_in_force="day"))
        except Exception as e:
            log.error("intraday.order_failed", user_id=sess.user_id,
                      ticker=sym, error=str(e))
            continue
        run_id, trade_id = await _record_entry(
            sess.user_id, sym, qty, price, stop_px, target_px,
            policy.setup, order, policy.label())
        sess.open[sym] = {"trade_id": trade_id, "qty": qty, "entry": price,
                          "opened_at": datetime.now(UTC),
                          "order_id": order.get("id")}
        sess.trades_today += 1
        gross += qty * price
        log.info("intraday.entry", user_id=sess.user_id, ticker=sym, qty=qty,
                 stop=stop_px, target=target_px, setup=policy.setup)

        from app.api.v1.notifications import save_notification
        await save_notification(
            type="trade_placed",
            title=f"Intraday entry — BUY {sym}",
            body=f"{policy.setup} setup: {qty} shares, stop ${stop_px}, "
                 f"target ${target_px}, flat by close.",
            ticker=sym, user_id=sess.user_id)


async def _enrolled_users() -> list[int]:
    from app.broker.credentials import connected_user_ids
    from app.db.models.user_settings import get_user_setting

    users = []
    for uid in await connected_user_ids():
        mode = await get_user_setting(uid, "strategy_mode", "agents")
        enabled = await get_user_setting(uid, "scan_enabled", False)
        if str(mode) == "intraday" and str(enabled).lower() in ("1", "true", "yes"):
            users.append(uid)
    return users


def _is_rth(now_et: datetime) -> bool:
    return (now_et.weekday() < 5
            and dtime(9, 30) <= now_et.time() < dtime(16, 0))


async def _cycle():
    from app.broker.credentials import get_client_for_user

    now_et = datetime.now(ET)
    if not _is_rth(now_et):
        return

    for uid in await _enrolled_users():
        broker = await get_client_for_user(uid)
        if broker is None:
            continue
        sess = _sessions.setdefault(uid, UserSession(uid))
        fresh_day = sess.day != now_et.strftime("%Y-%m-%d")
        sess.roll_day(now_et.strftime("%Y-%m-%d"))
        if fresh_day:
            await _restore_open(sess)

        params = await _load_params(uid)
        policy = _policy_from(params)

        await _manage_positions(sess, broker, policy, now_et)

        # daily loss halt — flatten and stand down for the session
        if not sess.halted and (sess.open or sess.trades_today):
            equity_halt = None
            broker_day_pnl = None
            try:
                loop = asyncio.get_running_loop()
                account = await loop.run_in_executor(None, broker.get_account)
                equity_now = float(account.get("equity", 100_000))
                equity_halt = equity_now * params["intraday_daily_loss_halt_pct"] / 100
                # backstop: whole-account equity delta vs prior close catches
                # this engine's real day P&L even if a trade's pnl wasn't
                # recorded yet (e.g. bracket-exit reconciliation lag)
                last_equity = account.get("last_equity")
                if last_equity is not None:
                    broker_day_pnl = equity_now - float(last_equity)
            except Exception:
                pass
            if equity_halt:
                pnl = await _day_pnl(sess, broker)
                if broker_day_pnl is not None:
                    pnl = min(pnl, broker_day_pnl)
                if pnl <= -equity_halt:
                    log.warning("intraday.daily_loss_halt", user_id=uid,
                                pnl=round(pnl, 2), halt_at=-equity_halt)
                    await _flatten(sess, broker, "daily_loss_halt")
                    sess.halted = True
                    from app.api.v1.notifications import save_notification
                    await save_notification(
                        type="stop_loss_hit",
                        title="Intraday engine halted for the day",
                        body=f"Daily loss limit hit (${pnl:,.0f}). All intraday "
                             f"positions closed; no more entries today.",
                        user_id=uid)

        # signal scan only when a new 5m bar should exist
        due = (sess.last_bar_scan is None
               or (now_et - sess.last_bar_scan).total_seconds() >= BAR_SECONDS)
        if due and not sess.halted:
            sess.last_bar_scan = now_et
            await _scan_and_enter(sess, broker, policy, params, now_et)


async def run_intraday_engine():
    """Forever loop — started from main.py lifespan (backend role)."""
    log.info("intraday_engine.started", poll_seconds=POLL_SECONDS)
    while True:
        try:
            await _cycle()
        except Exception as e:
            log.error("intraday_engine.cycle_error", error=str(e))
        await asyncio.sleep(POLL_SECONDS)
