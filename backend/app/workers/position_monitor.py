"""
Position Monitor — enforces stop-loss and take-profit on every open trade.

Runs every 60 seconds.
Logic:
  - Fetch all Alpaca positions (live P&L)
  - Cross-reference with Trade DB rows to get agent-set stop/TP thresholds
  - If breached → close position on Alpaca, mark trade closed in DB
  - Broadcast WS event to room "alerts" and save a Notification
"""
from __future__ import annotations
import asyncio
import uuid
from datetime import datetime, UTC
import structlog

log = structlog.get_logger()

# Default thresholds used when no agent-set value exists
DEFAULT_STOP_LOSS_PCT = 7.0    # -7% → close
DEFAULT_TAKE_PROFIT_PCT = 20.0  # +20% → take profits


def _fetch_alpaca_positions() -> list[dict]:
    from app.broker.alpaca_client import get_positions
    return get_positions()


def _close_alpaca_position(ticker: str) -> dict | None:
    from app.broker.alpaca_client import close_position
    return close_position(ticker)


async def _load_open_trades() -> dict[str, dict]:
    """
    Return a map of ticker → trade row for all non-closed trades.
    Takes the most recent open trade per ticker (by submitted_at).
    """
    from sqlalchemy import select, desc
    from app.db.models.trade import Trade
    from app.core.postgres import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Trade).where(
                Trade.status.in_(["submitted", "filled", "partial"]),
                Trade.closed_at.is_(None),
            ).order_by(desc(Trade.submitted_at))
        )
        trades = result.scalars().all()

    # Most recent open trade per ticker wins
    seen: dict[str, dict] = {}
    for t in trades:
        if t.ticker not in seen:
            seen[t.ticker] = {
                "id": t.id,
                "side": t.side,
                "stop_loss_pct": t.stop_loss_pct or DEFAULT_STOP_LOSS_PCT,
                "take_profit_pct": t.take_profit_pct or DEFAULT_TAKE_PROFIT_PCT,
            }
    return seen


async def _mark_trade_closed(trade_id: str, reason: str, pnl: float):
    from app.db.models.trade import Trade
    from app.core.postgres import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        trade = await db.get(Trade, trade_id)
        if trade:
            trade.status = "closed"
            trade.closed_reason = reason
            trade.pnl = round(pnl, 2)
            trade.closed_at = datetime.now(UTC)
            await db.commit()


async def _save_close_notification(ticker: str, reason: str, pnl_dollar: float, pnl_pct: float):
    from app.db.models.notification import Notification
    from app.core.postgres import AsyncSessionLocal

    notif_type = "stop_loss_hit" if reason == "stop_loss" else "take_profit_hit"
    pnl_sign = "+" if pnl_dollar >= 0 else ""
    title = f"{'Stop-loss' if reason == 'stop_loss' else 'Take-profit'} hit — {ticker}"
    body = (
        f"{ticker} position automatically closed via {reason.replace('_', '-')}. "
        f"P&L: {pnl_sign}${pnl_dollar:,.2f} ({pnl_pct:+.2f}%)"
    )
    async with AsyncSessionLocal() as db:
        notif = Notification(
            id=str(uuid.uuid4()),
            type=notif_type,
            title=title,
            body=body,
            ticker=ticker,
            pnl=round(pnl_dollar, 2),
        )
        db.add(notif)
        await db.commit()


async def check_positions_once():
    """
    Single check cycle — compare all live Alpaca positions against thresholds.
    Returns list of closed positions.
    """
    from app.core.websocket_manager import ws_manager

    loop = asyncio.get_running_loop()

    try:
        positions = await loop.run_in_executor(None, _fetch_alpaca_positions)
    except Exception as e:
        log.warning("monitor.fetch_failed", error=str(e))
        return []

    if not positions:
        return []

    open_trades = await _load_open_trades()
    closed = []

    for pos in positions:
        ticker = pos.get("symbol") or pos.get("ticker")
        if not ticker:
            continue

        try:
            avg_entry = float(pos.get("avg_entry_price", 0))
            current = float(pos.get("current_price", 0))
            qty = float(pos.get("qty", 0))

            if avg_entry <= 0 or current <= 0:
                continue

            pnl_pct = (current - avg_entry) / avg_entry * 100
            pnl_dollar = (current - avg_entry) * qty

            trade_info = open_trades.get(ticker, {})
            stop = -(trade_info.get("stop_loss_pct") or DEFAULT_STOP_LOSS_PCT)
            tp = trade_info.get("take_profit_pct") or DEFAULT_TAKE_PROFIT_PCT

            reason = None
            if pnl_pct <= stop:
                reason = "stop_loss"
                log.warning("monitor.stop_loss_triggered",
                            ticker=ticker, pnl_pct=round(pnl_pct, 2),
                            threshold=stop)
            elif pnl_pct >= tp:
                reason = "take_profit"
                log.info("monitor.take_profit_triggered",
                         ticker=ticker, pnl_pct=round(pnl_pct, 2),
                         threshold=tp)

            log.info("monitor.position_check",
                     ticker=ticker, pnl_pct=round(pnl_pct, 2),
                     stop=stop, tp=tp, will_close=reason is not None)

            if reason:
                try:
                    await loop.run_in_executor(None, _close_alpaca_position, ticker)
                    log.info("monitor.position_closed",
                             ticker=ticker, reason=reason, pnl_pct=round(pnl_pct, 2))

                    # Update DB if we have a trade record
                    if ticker in open_trades:
                        await _mark_trade_closed(open_trades[ticker]["id"], reason, pnl_dollar)

                    # Save notification
                    await _save_close_notification(ticker, reason, pnl_dollar, pnl_pct)

                    # Broadcast WS event
                    await ws_manager.broadcast("alerts", {
                        "type": "position_closed",
                        "ticker": ticker,
                        "reason": reason,
                        "pnl": round(pnl_dollar, 2),
                        "pnl_pct": round(pnl_pct, 2),
                    })

                    closed.append({
                        "ticker": ticker,
                        "reason": reason,
                        "pnl_pct": round(pnl_pct, 2),
                        "pnl_dollar": round(pnl_dollar, 2),
                    })
                except Exception as e:
                    log.error("monitor.close_failed", ticker=ticker, error=str(e))

        except Exception as e:
            log.error("monitor.position_check_failed", ticker=ticker, error=str(e))

    return closed


async def run_position_monitor():
    """
    Continuously check positions every 60 seconds.
    Called from main.py lifespan — runs forever as an asyncio background task.
    """
    log.info("position_monitor.started")
    CHECK_INTERVAL = 60  # 60 seconds

    while True:
        try:
            closed = await check_positions_once()
            if closed:
                log.info("monitor.cycle.closed_positions", count=len(closed), detail=closed)
            else:
                log.debug("monitor.cycle.ok")
        except Exception as e:
            log.error("monitor.cycle.error", error=str(e))

        await asyncio.sleep(CHECK_INTERVAL)
