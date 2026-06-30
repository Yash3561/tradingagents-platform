"""
Position Monitor — enforces stop-loss and take-profit on every open trade.

Runs every 5 minutes during market hours.
Logic:
  - Fetch all Alpaca positions (live P&L)
  - Cross-reference with Trade DB rows to get agent-set stop/TP thresholds
  - If breached → close position on Alpaca, mark trade closed in DB
"""
from __future__ import annotations
import asyncio
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
    Only returns BUY-side trades (we're long-only for now).
    """
    from sqlalchemy import select
    from app.db.models.trade import Trade
    from app.core.postgres import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Trade).where(
                Trade.side == "buy",
                Trade.status.in_(["submitted", "filled", "partial"]),
                Trade.closed_at.is_(None),
            )
        )
        trades = result.scalars().all()

    return {
        t.ticker: {
            "id": t.id,
            "stop_loss_pct": t.stop_loss_pct or DEFAULT_STOP_LOSS_PCT,
            "take_profit_pct": t.take_profit_pct or DEFAULT_TAKE_PROFIT_PCT,
        }
        for t in trades
    }


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


async def check_positions_once():
    """
    Single check cycle — compare all live Alpaca positions against thresholds.
    Returns list of closed positions.
    """
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

            if reason:
                try:
                    await loop.run_in_executor(None, _close_alpaca_position, ticker)
                    log.info("monitor.position_closed",
                             ticker=ticker, reason=reason, pnl_pct=round(pnl_pct, 2))

                    # Update DB if we have a trade record
                    if ticker in open_trades:
                        await _mark_trade_closed(open_trades[ticker]["id"], reason, pnl_dollar)

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
    Continuously check positions every 5 minutes.
    Called from workers/main.py — runs forever.
    """
    log.info("position_monitor.started")
    CHECK_INTERVAL = 300  # 5 minutes

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
