import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import httpx
import structlog

from app.core.auth import require_user
from app.broker.alpaca_client import AlpacaClient
from app.broker.credentials import optional_broker, required_broker

router = APIRouter()
log = structlog.get_logger()


class PlaceOrderRequest(BaseModel):
    ticker: str
    side: str                      # "buy" | "sell"
    qty: float
    order_type: str = "market"     # "market" | "limit"
    limit_price: float | None = None
    time_in_force: str = "day"     # "day" | "gtc"


@router.post("/")
async def place_order(
    body: PlaceOrderRequest,
    user=Depends(require_user),
    broker: AlpacaClient = Depends(required_broker),
):
    """
    Manual order entry — trades the user's own Alpaca paper account.
    Safety rails:
      - whole shares, qty >= 1
      - limit orders require a limit price
      - SELL is capped at shares actually held (no naked shorts, ever)
      - BUY is pre-checked against buying power for a clear error message
    """
    import math
    import uuid
    from datetime import datetime, UTC
    from app.core.postgres import AsyncSessionLocal
    from app.db.models.trade import Trade

    ticker = body.ticker.strip().upper()
    side = body.side.strip().lower()
    qty = math.floor(body.qty)

    if not ticker or len(ticker) > 10:
        raise HTTPException(400, "Invalid ticker")
    if side not in ("buy", "sell"):
        raise HTTPException(400, "side must be 'buy' or 'sell'")
    if qty < 1:
        raise HTTPException(400, "Quantity must be at least 1 whole share")
    if body.order_type not in ("market", "limit"):
        raise HTTPException(400, "order_type must be 'market' or 'limit'")
    if body.order_type == "limit" and (body.limit_price is None or body.limit_price <= 0):
        raise HTTPException(400, "Limit orders need a positive limit price")
    if body.time_in_force not in ("day", "gtc"):
        raise HTTPException(400, "time_in_force must be 'day' or 'gtc'")

    loop = asyncio.get_running_loop()

    # ── Pre-flight checks against the user's account ────────────────────────
    if side == "sell":
        position = await loop.run_in_executor(None, broker.get_position, ticker)
        held = float(position.get("qty", 0)) if position else 0
        if held < 1:
            raise HTTPException(400, f"You don't hold any {ticker} — short selling is not supported")
        if qty > held:
            raise HTTPException(400, f"You hold {held:g} shares of {ticker} — can't sell {qty}")
    else:
        try:
            account = await loop.run_in_executor(None, broker.get_account)
            buying_power = float(account.get("buying_power", 0))
            ref_price = body.limit_price
            if ref_price is None:
                from app.broker.alpaca_client import get_live_price
                ref_price = get_live_price(ticker)
            if ref_price and qty * ref_price > buying_power:
                raise HTTPException(
                    400,
                    f"Order ≈ ${qty * ref_price:,.2f} exceeds your buying power of ${buying_power:,.2f}",
                )
        except HTTPException:
            raise
        except Exception as e:
            log.warning("orders.preflight_failed", error=str(e))  # Alpaca will still validate

    # ── Submit ───────────────────────────────────────────────────────────────
    try:
        order = await loop.run_in_executor(
            None,
            lambda: broker.submit_order(
                ticker, side, qty,
                order_type=body.order_type,
                time_in_force=body.time_in_force,
                limit_price=body.limit_price,
            ),
        )
    except httpx.HTTPStatusError as e:
        detail = str(e)
        if e.response is not None:
            try:
                detail = e.response.json().get("message", e.response.text[:300])
            except Exception:
                detail = e.response.text[:300]
        raise HTTPException(422, f"Alpaca rejected the order: {detail}")
    except Exception as e:
        raise HTTPException(502, f"Order submission failed: {e}")

    # ── Record + notify ──────────────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        trade = Trade(
            id=str(uuid.uuid4()),
            user_id=user.id,
            alpaca_order_id=order.get("id"),
            ticker=ticker,
            side=side,
            qty=qty,
            order_type=body.order_type,
            limit_price=body.limit_price,
            status="submitted",
            reasoning_json={"source": "manual", "time_in_force": body.time_in_force},
            submitted_at=datetime.now(UTC),
        )
        db.add(trade)
        await db.commit()

    from app.core.analytics import track
    await track("manual_order", user.id, ticker=ticker, side=side)

    try:
        from app.api.v1.notifications import save_notification
        from app.api.v1.activity import log_activity
        await save_notification(
            type="trade_placed",
            title=f"Order placed — {side.upper()} {qty} {ticker}",
            body=f"Manual {body.order_type} order submitted. Order ID: {order.get('id', 'N/A')}",
            ticker=ticker,
            user_id=user.id,
        )
        await log_activity(
            feature="manual_trade", action="order_placed", ticker=ticker,
            details={"side": side, "qty": qty, "type": body.order_type,
                     "limit_price": body.limit_price, "order_id": order.get("id")},
            result=side.upper(), user_id=user.id,
        )
    except Exception as e:
        log.warning("orders.notify_failed", error=str(e))

    return {
        "ok": True,
        "order_id": order.get("id"),
        "status": order.get("status"),
        "ticker": ticker,
        "side": side,
        "qty": qty,
        "order_type": body.order_type,
        "limit_price": body.limit_price,
    }


def _fmt_order(o: dict) -> dict:
    return {
        "id": o.get("id"),
        "client_order_id": o.get("client_order_id"),
        "ticker": o.get("symbol"),
        "side": o.get("side"),
        "type": o.get("type"),
        "qty": float(o.get("qty") or 0),
        "filled_qty": float(o.get("filled_qty") or 0),
        "limit_price": float(o["limit_price"]) if o.get("limit_price") else None,
        "stop_price": float(o["stop_price"]) if o.get("stop_price") else None,
        "status": o.get("status"),
        "time_in_force": o.get("time_in_force"),
        "created_at": o.get("created_at"),
        "updated_at": o.get("updated_at"),
        "filled_at": o.get("filled_at"),
        "expired_at": o.get("expired_at"),
        "canceled_at": o.get("canceled_at"),
        "legs": [_fmt_order(leg) for leg in o.get("legs") or []],
    }


@router.get("/")
async def list_orders(
    status: str = "open",
    limit: int = 50,
    broker: AlpacaClient | None = Depends(optional_broker),
):
    """
    List orders from the user's Alpaca account.
    status: open | closed | all
    """
    if broker is None:
        return []
    try:
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, lambda: broker.get_orders(status, limit))
        return [_fmt_order(o) for o in raw]
    except Exception as e:
        log.warning("orders.list_error", error=str(e))
        return []


@router.delete("/{order_id}")
async def cancel_order(order_id: str, broker: AlpacaClient = Depends(required_broker)):
    """Cancel a single open order."""
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(None, broker.cancel_order, order_id)
    if ok:
        return {"cancelled": order_id}
    raise HTTPException(status_code=400, detail=f"Could not cancel order {order_id}")


@router.delete("/")
async def cancel_all_orders(broker: AlpacaClient = Depends(required_broker)):
    """Cancel all open orders."""
    loop = asyncio.get_running_loop()
    try:
        cancelled = await loop.run_in_executor(None, broker.cancel_all_orders)
        return {"cancelled_count": len(cancelled)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
