"""
Alpaca paper trading client.
Always uses ALPACA_BASE_URL which defaults to paper-api.alpaca.markets.
Never touches live money unless explicitly reconfigured in .env.
"""

import httpx
import structlog
from app.config import get_settings

log = structlog.get_logger()
settings = get_settings()


def _headers() -> dict:
    return {
        "APCA-API-KEY-ID": settings.alpaca_api_key,
        "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
        "Content-Type": "application/json",
    }


def get_account() -> dict:
    """Fetch current paper account info."""
    with httpx.Client(timeout=10.0) as client:
        r = client.get(f"{settings.alpaca_base_url}/v2/account", headers=_headers())
        r.raise_for_status()
        return r.json()


def get_positions() -> list:
    """Fetch all open positions."""
    with httpx.Client(timeout=10.0) as client:
        r = client.get(f"{settings.alpaca_base_url}/v2/positions", headers=_headers())
        r.raise_for_status()
        return r.json()


def get_position(ticker: str) -> dict | None:
    """Fetch a specific position, returns None if not held."""
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{settings.alpaca_base_url}/v2/positions/{ticker}", headers=_headers())
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
    except Exception:
        return None


def submit_order(
    ticker: str,
    side: str,           # "buy" | "sell"
    qty: float,
    order_type: str = "market",
    time_in_force: str = "day",
) -> dict:
    """Submit a paper market order. Returns the Alpaca order object."""
    import math
    # Always use whole shares — cleaner and avoids Alpaca fractional edge cases
    final_qty = str(max(1, math.floor(qty)))

    payload = {
        "symbol": ticker.upper(),
        "qty": final_qty,
        "side": side.lower(),
        "type": order_type,
        "time_in_force": time_in_force,
    }
    log.info("alpaca.order.submit", ticker=ticker, side=side, qty=qty)
    with httpx.Client(timeout=10.0) as client:
        r = client.post(
            f"{settings.alpaca_base_url}/v2/orders",
            headers=_headers(),
            json=payload,
        )
        r.raise_for_status()
        order = r.json()
        log.info("alpaca.order.accepted", order_id=order.get("id"), status=order.get("status"))
        return order


def close_position(ticker: str) -> dict | None:
    """Close an entire position (liquidate). Returns order or None if no position."""
    pos = get_position(ticker)
    if not pos:
        return None
    with httpx.Client(timeout=10.0) as client:
        r = client.delete(
            f"{settings.alpaca_base_url}/v2/positions/{ticker}",
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()


def calculate_order_qty(position_pct: float, current_price: float) -> float:
    """
    Calculate how many shares to buy given a position size percentage.
    position_pct: e.g. 2.0 means 2% of portfolio equity
    Returns qty rounded to 4 decimal places (fractional shares supported).
    """
    try:
        account = get_account()
        equity = float(account.get("equity", 100_000))
        dollar_amount = equity * (position_pct / 100.0)
        qty = dollar_amount / current_price
        return round(max(qty, 0.0001), 4)
    except Exception as e:
        log.warning("alpaca.qty_calc_failed", error=str(e))
        # Fallback: 1% of $100k default
        return round((1000.0 / current_price), 4)
