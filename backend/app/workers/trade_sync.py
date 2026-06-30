"""
Trade Sync — reconciles Alpaca order fills back to the DB.

Runs every 2 minutes.
For each Trade in DB with status != filled/closed/cancelled:
  - Fetch the order from Alpaca by alpaca_order_id
  - Update filled_price, filled_qty, filled_at, status
  - For SELL-side or closed positions, compute realized PnL
"""
from __future__ import annotations
import asyncio
from datetime import datetime, UTC
import structlog

log = structlog.get_logger()


def _fetch_alpaca_order(order_id: str) -> dict | None:
    from app.broker.alpaca_client import _headers
    from app.config import get_settings
    import httpx
    settings = get_settings()
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.get(
                f"{settings.alpaca_base_url}/v2/orders/{order_id}",
                headers=_headers(),
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log.warning("trade_sync.fetch_order_failed", order_id=order_id, error=str(e))
        return None


def _fetch_all_alpaca_orders(status: str = "all", limit: int = 100) -> list[dict]:
    """Fetch recent orders from Alpaca."""
    from app.broker.alpaca_client import _headers
    from app.config import get_settings
    import httpx
    settings = get_settings()
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(
                f"{settings.alpaca_base_url}/v2/orders",
                headers=_headers(),
                params={"status": status, "limit": limit, "direction": "desc"},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log.warning("trade_sync.fetch_orders_failed", error=str(e))
        return []


async def sync_trades_once():
    """
    Single sync cycle. Returns count of updated trades.
    """
    from sqlalchemy import select
    from app.db.models.trade import Trade
    from app.core.postgres import AsyncSessionLocal

    # Load all non-terminal trades from DB
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Trade).where(
                Trade.status.in_(["pending", "submitted", "partial"]),
                Trade.alpaca_order_id.isnot(None),
            )
        )
        pending_trades = result.scalars().all()

    if not pending_trades:
        return 0

    loop = asyncio.get_running_loop()
    updated = 0

    for trade in pending_trades:
        try:
            order = await loop.run_in_executor(
                None, _fetch_alpaca_order, trade.alpaca_order_id
            )
            if not order:
                continue

            alpaca_status = order.get("status", "")
            filled_qty = float(order.get("filled_qty") or 0)
            filled_avg_price = float(order.get("filled_avg_price") or 0)

            # Map Alpaca status to our status
            status_map = {
                "filled": "filled",
                "partially_filled": "partial",
                "cancelled": "cancelled",
                "expired": "cancelled",
                "rejected": "rejected",
                "accepted": "submitted",
                "pending_new": "submitted",
                "new": "submitted",
            }
            new_status = status_map.get(alpaca_status, trade.status)

            # Parse filled_at
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
