from fastapi import APIRouter, HTTPException
import httpx
import structlog
from app.config import get_settings

router = APIRouter()
log = structlog.get_logger()
settings = get_settings()


def _headers():
    return {
        "APCA-API-KEY-ID": settings.alpaca_api_key,
        "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
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
async def list_orders(status: str = "open", limit: int = 50):
    """
    List orders from Alpaca.
    status: open | closed | all
    """
    if not settings.alpaca_api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{settings.alpaca_base_url}/v2/orders",
                headers=_headers(),
                params={"status": status, "limit": limit, "direction": "desc"},
            )
        if r.status_code != 200:
            log.warning("orders.list_failed", status=r.status_code, body=r.text[:200])
            return []
        return [_fmt_order(o) for o in r.json()]
    except Exception as e:
        log.warning("orders.list_error", error=str(e))
        return []


@router.delete("/{order_id}")
async def cancel_order(order_id: str):
    """Cancel a single open order."""
    if not settings.alpaca_api_key:
        raise HTTPException(status_code=400, detail="Alpaca not configured")
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.delete(
            f"{settings.alpaca_base_url}/v2/orders/{order_id}",
            headers=_headers(),
        )
    if r.status_code == 204:
        return {"cancelled": order_id}
    raise HTTPException(status_code=r.status_code, detail=r.text)


@router.delete("/")
async def cancel_all_orders():
    """Cancel all open orders."""
    if not settings.alpaca_api_key:
        raise HTTPException(status_code=400, detail="Alpaca not configured")
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.delete(
            f"{settings.alpaca_base_url}/v2/orders",
            headers=_headers(),
        )
    if r.status_code in (200, 207):
        cancelled = r.json() if r.text else []
        return {"cancelled_count": len(cancelled)}
    raise HTTPException(status_code=r.status_code, detail=r.text)
