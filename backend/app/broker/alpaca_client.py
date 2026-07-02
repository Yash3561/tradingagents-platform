"""
Alpaca trading client.

Multi-tenant: each user connects their own Alpaca *paper* account, and all
account-touching calls go through an AlpacaClient instance built from that
user's stored credentials (see app.broker.credentials).

The module-level functions at the bottom are the legacy single-tenant path:
they use the env-configured keys (ALPACA_API_KEY/SECRET) and remain for
market-wide plumbing (market clock, price feed) and dev fallback.
Always paper by default — never point base_url at live without explicit user confirmation.
"""

import json
import math

import httpx
import structlog

from app.config import get_settings

log = structlog.get_logger()


class AlpacaClient:
    """Thin sync HTTP client bound to one Alpaca account's credentials."""

    def __init__(self, api_key: str, api_secret: str, base_url: str | None = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = (base_url or get_settings().alpaca_base_url).rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def headers(self) -> dict:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
            "Content-Type": "application/json",
        }

    # ── Account / positions ────────────────────────────────────────────────

    def get_account(self) -> dict:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{self.base_url}/v2/account", headers=self.headers())
            r.raise_for_status()
            return r.json()

    def get_positions(self) -> list:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{self.base_url}/v2/positions", headers=self.headers())
            r.raise_for_status()
            return r.json()

    def get_position(self, ticker: str) -> dict | None:
        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.get(f"{self.base_url}/v2/positions/{ticker}", headers=self.headers())
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.json()
        except Exception:
            return None

    def close_position(self, ticker: str) -> dict | None:
        pos = self.get_position(ticker)
        if not pos:
            return None
        with httpx.Client(timeout=10.0) as client:
            r = client.delete(f"{self.base_url}/v2/positions/{ticker}", headers=self.headers())
            r.raise_for_status()
            return r.json()

    # ── Orders ─────────────────────────────────────────────────────────────

    def get_order(self, order_id: str) -> dict | None:
        try:
            with httpx.Client(timeout=8.0) as client:
                r = client.get(f"{self.base_url}/v2/orders/{order_id}", headers=self.headers())
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.json()
        except Exception as e:
            log.warning("alpaca.fetch_order_failed", order_id=order_id, error=str(e))
            return None

    def get_orders(self, status: str = "open", limit: int = 50) -> list[dict]:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(
                f"{self.base_url}/v2/orders",
                headers=self.headers(),
                params={"status": status, "limit": limit, "direction": "desc"},
            )
            r.raise_for_status()
            return r.json()

    def cancel_order(self, order_id: str) -> bool:
        with httpx.Client(timeout=8.0) as client:
            r = client.delete(f"{self.base_url}/v2/orders/{order_id}", headers=self.headers())
            return r.status_code == 204

    def cancel_all_orders(self) -> list:
        with httpx.Client(timeout=8.0) as client:
            r = client.delete(f"{self.base_url}/v2/orders", headers=self.headers())
            if r.status_code in (200, 207):
                return r.json() if r.text else []
            r.raise_for_status()
            return []

    def submit_order(
        self,
        ticker: str,
        side: str,           # "buy" | "sell"
        qty: float,
        order_type: str = "market",   # "market" | "limit"
        time_in_force: str = "day",   # "day" | "gtc"
        limit_price: float | None = None,
    ) -> dict:
        # Always use whole shares — cleaner and avoids Alpaca fractional edge cases
        final_qty = str(max(1, math.floor(qty)))

        payload = {
            "symbol": ticker.upper(),
            "qty": final_qty,
            "side": side.lower(),
            "type": order_type,
            "time_in_force": time_in_force,
        }
        if order_type == "limit":
            if limit_price is None:
                raise ValueError("limit_price is required for limit orders")
            payload["limit_price"] = str(round(limit_price, 2))
        log.info("alpaca.order.submit", ticker=ticker, side=side, qty=qty, type=order_type)
        with httpx.Client(timeout=10.0) as client:
            r = client.post(f"{self.base_url}/v2/orders", headers=self.headers(), json=payload)
            r.raise_for_status()
            order = r.json()
            log.info("alpaca.order.accepted", order_id=order.get("id"), status=order.get("status"))
            return order

    def submit_bracket_order(
        self,
        ticker: str,
        qty: int,
        stop_loss_pct: float,
        take_profit_pct: float,
        current_price: float,
    ) -> dict:
        """
        Place a market BUY with attached stop-loss and take-profit orders.
        Alpaca bracket orders: type=market, order_class=bracket,
        stop_loss.stop_price and take_profit.limit_price attached.
        Returns the main order dict.
        """
        stop_price = round(current_price * (1 - stop_loss_pct / 100), 2)
        take_price = round(current_price * (1 + take_profit_pct / 100), 2)

        payload = {
            "symbol": ticker.upper(),
            "qty": str(int(qty)),
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
            "order_class": "bracket",
            "stop_loss": {"stop_price": str(stop_price)},
            "take_profit": {"limit_price": str(take_price)},
        }
        with httpx.Client(timeout=15.0) as client:
            r = client.post(f"{self.base_url}/v2/orders", headers=self.headers(), json=payload)
            r.raise_for_status()
            order = r.json()
            log.info("alpaca.bracket_order.accepted", order_id=order.get("id"),
                     ticker=ticker, stop=stop_price, take=take_price)
            return order

    # ── History / clock ────────────────────────────────────────────────────

    def get_portfolio_history(self, period: str = "1M", timeframe: str = "1D") -> dict | None:
        try:
            with httpx.Client(timeout=8.0) as client:
                r = client.get(
                    f"{self.base_url}/v2/account/portfolio/history",
                    headers=self.headers(),
                    params={"period": period, "timeframe": timeframe, "extended_hours": "false"},
                )
                if r.status_code != 200:
                    return None
                return r.json()
        except Exception:
            return None

    def get_clock(self) -> dict:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{self.base_url}/v2/clock", headers=self.headers())
            r.raise_for_status()
            return r.json()

    def calculate_order_qty(self, position_pct: float, current_price: float) -> float:
        """
        Calculate how many shares to buy given a position size percentage.
        position_pct: e.g. 2.0 means 2% of portfolio equity
        """
        try:
            account = self.get_account()
            equity = float(account.get("equity", 100_000))
            dollar_amount = equity * (position_pct / 100.0)
            qty = dollar_amount / current_price
            return round(max(qty, 0.0001), 4)
        except Exception as e:
            log.warning("alpaca.qty_calc_failed", error=str(e))
            return round((1000.0 / current_price), 4)


def default_client() -> AlpacaClient:
    """Client built from env keys — legacy single-tenant / platform-level use only."""
    s = get_settings()
    return AlpacaClient(s.alpaca_api_key, s.alpaca_api_secret, s.alpaca_base_url)


# ── Legacy module-level API (env keys) — kept for market clock / price feed / dev ──

def _headers() -> dict:
    return default_client().headers()


def get_account() -> dict:
    return default_client().get_account()


def get_positions() -> list:
    return default_client().get_positions()


def get_position(ticker: str) -> dict | None:
    return default_client().get_position(ticker)


def submit_order(ticker: str, side: str, qty: float,
                 order_type: str = "market", time_in_force: str = "day") -> dict:
    return default_client().submit_order(ticker, side, qty, order_type, time_in_force)


def close_position(ticker: str) -> dict | None:
    return default_client().close_position(ticker)


def submit_bracket_order(ticker: str, qty: int, stop_loss_pct: float,
                         take_profit_pct: float, current_price: float) -> dict:
    return default_client().submit_bracket_order(
        ticker, qty, stop_loss_pct, take_profit_pct, current_price
    )


def calculate_order_qty(position_pct: float, current_price: float) -> float:
    return default_client().calculate_order_qty(position_pct, current_price)


def get_live_price(ticker: str) -> float | None:
    """Get latest price from Redis cache, falls back to None if not found."""
    import redis as redis_sync
    s = get_settings()
    try:
        r = redis_sync.from_url(s.redis_url)
        raw = r.get(f"price:{ticker}")
        if raw:
            return json.loads(raw)["price"]
    except Exception:
        pass
    return None  # caller should fall back to yfinance
