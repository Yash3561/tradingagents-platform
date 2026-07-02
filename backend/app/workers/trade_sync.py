"""
Trade Sync — reconciles Alpaca order fills back to the DB.

Runs every 2 minutes. Multi-tenant: pending trades are grouped by user and
each group is checked against that user's Alpaca account. Legacy trades
without a user_id fall back to the env-configured account.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, UTC
import structlog

log = structlog.get_logger()

# Alpaca status → our status
_STATUS_MAP = {
    "filled": "filled",
    "partially_filled": "partial",
    "cancelled": "cancelled",
    "expired": "cancelled",
    "rejected": "rejected",
    "accepted": "submitted",
    "pending_new": "submitted",
    "new": "submitted",
}

_PENDING_STATUSES = ["pending", "submitted", "partial", "pending_new", "new", "accepted"]


async def _broker_for(user_id: int | None):
    """Per-user client, or the env-configured default for legacy rows."""
    from app.broker.credentials import get_client_for_user
    from app.broker.alpaca_client import default_client

    if user_id is not None:
        return await get_client_for_user(user_id)
    client = default_client()
    return client if client.configured else None


async def sync_trades_once(user_id: int | None = None) -> int:
    """
    Single sync cycle. When user_id is given, only that user's trades are synced.
    Returns count of updated trades.
    """
    from sqlalchemy import select
    from app.db.models.trade import Trade
    from app.core.postgres import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        q = select(Trade).where(
            Trade.status.in_(_PENDING_STATUSES),
            Trade.alpaca_order_id.isnot(None),
        )
        if user_id is not None:
            q = q.where(Trade.user_id == user_id)
        result = await db.execute(q)
        pending_trades = result.scalars().all()

    if not pending_trades:
        return 0

    loop = asyncio.get_running_loop()
    updated = 0
    brokers: dict[int | None, object] = {}

    for trade in pending_trades:
        try:
            uid = trade.user_id
            if uid not in brokers:
                brokers[uid] = await _broker_for(uid)
            broker = brokers[uid]
            if broker is None:
                continue

            order = await loop.run_in_executor(None, broker.get_order, trade.alpaca_order_id)
            if not order:
                continue

            alpaca_status = order.get("status", "")
            filled_qty = float(order.get("filled_qty") or 0)
            filled_avg_price = float(order.get("filled_avg_price") or 0)
            new_status = _STATUS_MAP.get(alpaca_status, trade.status)

            filled_at = None
            if order.get("filled_at"):
                try:
                    filled_at = datetime.fromisoformat(
                        order["filled_at"].replace("Z", "+00:00")
                    )
                except Exception:
                    pass

            async with AsyncSessionLocal() as db:
                t = await db.get(Trade, trade.id)
                if t:
                    t.status = new_status
                    if filled_qty > 0:
                        t.filled_qty = filled_qty
                    if filled_avg_price > 0:
                        t.filled_price = round(filled_avg_price, 4)
                    if filled_at:
                        t.filled_at = filled_at
                    await db.commit()
                    updated += 1

            log.debug("trade_sync.updated",
                      trade_id=trade.id, ticker=trade.ticker,
                      status=new_status, filled_price=filled_avg_price)

        except Exception as e:
            log.error("trade_sync.trade_failed", trade_id=trade.id, error=str(e))

    return updated


async def run_trade_sync():
    """
    Continuously sync trade fills every 2 minutes.
    Called from workers/main.py — runs forever.
    """
    log.info("trade_sync.started")
    SYNC_INTERVAL = 120  # 2 minutes

    while True:
        try:
            updated = await sync_trades_once()
            if updated:
                log.info("trade_sync.cycle.done", updated=updated)
        except Exception as e:
            log.error("trade_sync.cycle.error", error=str(e))

        await asyncio.sleep(SYNC_INTERVAL)
