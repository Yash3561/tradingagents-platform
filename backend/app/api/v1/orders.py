import asyncio

from fastapi import APIRouter, Depends, HTTPException
import structlog

from app.broker.alpaca_client import AlpacaClient
from app.broker.credentials import optional_broker, required_broker

router = APIRouter()
log = structlog.get_logger()


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
