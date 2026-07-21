"""
Alpaca-native options data layer.

Distinct from core/market_data.py's yfinance-chain fallback used by Options
Desk (api/v1/agents.py) — that one exists because Alpaca's free STOCK data
tier doesn't cover every price-history need cheaply, but Alpaca's OPTIONS
data API is genuinely first-class and doesn't need a fallback: real listed
contracts, real bid/ask, and — for liquid strikes — real computed delta and
implied volatility straight from Alpaca's own feed, no Black-Scholes needed
on our side for those two numbers. Confirmed live 2026-07-21 against MSFT's
real chain before writing this.

All functions are sync (called from thread executors, matching the rest of
the codebase's broker/market_data convention) and fail soft: [] / None
instead of raising, since a scan cycle degrading is better than one bad
ticker killing the whole cycle.
"""
from __future__ import annotations

from datetime import date as _date, timedelta

import httpx
import structlog

log = structlog.get_logger()

_TRADING_BASE = "https://paper-api.alpaca.markets"  # contracts live on the trading API
_DATA_BASE = "https://data.alpaca.markets"
_TIMEOUT = 20.0


def _headers(api_key: str, api_secret: str) -> dict:
    return {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}


def list_option_contracts(api_key: str, api_secret: str, underlying: str,
                          expiration_gte: str, expiration_lte: str,
                          option_type: str = "call") -> list[dict]:
    """
    Real listed, tradable contracts for `underlying` expiring in
    [expiration_gte, expiration_lte] (YYYY-MM-DD), with proper OCC symbols
    ready to submit as an order (e.g. "MSFT260722C00410000"). option_type:
    "call" | "put".
    """
    out: list[dict] = []
    page_token = None
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            while True:
                params = {
                    "underlying_symbols": underlying.upper(),
                    "status": "active",
                    "expiration_date_gte": expiration_gte,
                    "expiration_date_lte": expiration_lte,
                    "type": option_type,
                    "limit": 100,
                }
                if page_token:
                    params["page_token"] = page_token
                r = client.get(f"{_TRADING_BASE}/v2/options/contracts",
                               headers=_headers(api_key, api_secret), params=params)
                r.raise_for_status()
                j = r.json()
                out.extend(j.get("option_contracts") or [])
                page_token = j.get("next_page_token")
                if not page_token:
                    break
    except Exception as e:
        log.warning("alpaca_options.contracts_failed", underlying=underlying, error=str(e)[:200])
        return []
    return out


def get_option_snapshots(api_key: str, api_secret: str, underlying: str,
                         strike_gte: float | None = None,
                         strike_lte: float | None = None) -> dict[str, dict]:
    """
    {occ_symbol: snapshot} for `underlying`'s contracts — real bid/ask,
    last trade, and for liquid strikes real greeks + impliedVolatility
    straight from Alpaca. Optional strike bounds keep the response small
    (an underlying can have hundreds of contracts across all expiries).
    """
    params = {"feed": "indicative", "limit": 100}
    if strike_gte is not None:
        params["strike_price_gte"] = strike_gte
    if strike_lte is not None:
        params["strike_price_lte"] = strike_lte

    out: dict[str, dict] = {}
    page_token = None
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            while True:
                p = dict(params)
                if page_token:
                    p["page_token"] = page_token
                r = client.get(f"{_DATA_BASE}/v1beta1/options/snapshots/{underlying.upper()}",
                               headers=_headers(api_key, api_secret), params=p)
                r.raise_for_status()
                j = r.json()
                out.update(j.get("snapshots") or {})
                page_token = j.get("next_page_token")
                if not page_token:
                    break
    except Exception as e:
        log.warning("alpaca_options.snapshots_failed", underlying=underlying, error=str(e)[:200])
        return {}
    return out


def pick_contract(api_key: str, api_secret: str, underlying: str, current_price: float,
                  target_days: int, is_call: bool, target_delta: float = 0.35,
                  min_bid: float = 0.05) -> dict | None:
    """
    The actual selection logic: real listed expiry closest to target_days
    out, real liquid contracts only (bid > 0 above min_bid, some quoted
    size), closest to target_delta using Alpaca's own computed delta.
    Returns None if nothing liquid qualifies — caller should treat that as
    NO_PLAY, never fall back to inventing a contract.
    """
    today = _date.today()
    window_end = (today + timedelta(days=target_days * 3 + 14)).isoformat()
    option_type = "call" if is_call else "put"

    contracts = list_option_contracts(api_key, api_secret, underlying,
                                      today.isoformat(), window_end, option_type)
    if not contracts:
        return None

    expiries = sorted({c["expiration_date"] for c in contracts})
    chain_expiry = min(expiries, key=lambda e: abs((_date.fromisoformat(e) - today).days - target_days))

    # Strike band around spot generous enough to contain a ~0.35-delta strike
    # without pulling in the whole chain (hundreds of far strikes otherwise).
    band = max(current_price * 0.15, 5.0)
    snaps = get_option_snapshots(api_key, api_secret, underlying,
                                 strike_gte=round(current_price - band, 2),
                                 strike_lte=round(current_price + band, 2))
    if not snaps:
        return None

    same_expiry_symbols = {c["symbol"] for c in contracts if c["expiration_date"] == chain_expiry}
    by_symbol = {c["symbol"]: c for c in contracts}

    best_symbol, best_diff = None, None
    for sym, snap in snaps.items():
        if sym not in same_expiry_symbols:
            continue
        quote = snap.get("latestQuote") or {}
        bid, ask = quote.get("bp") or 0, quote.get("ap") or 0
        if bid < min_bid or ask <= 0:
            continue  # exactly the "no real buyer" filter that matters
        greeks = snap.get("greeks") or {}
        delta = greeks.get("delta")
        if delta is None:
            continue  # illiquid enough that Alpaca didn't compute greeks — skip
        diff = abs(abs(delta) - target_delta)
        if best_diff is None or diff < best_diff:
            best_symbol, best_diff = sym, diff

    if best_symbol is None:
        return None

    snap = snaps[best_symbol]
    quote = snap["latestQuote"]
    contract = by_symbol[best_symbol]
    return {
        "symbol": best_symbol,
        "strike": float(contract["strike_price"]),
        "expiry": chain_expiry,
        "bid": quote.get("bp"),
        "ask": quote.get("ap"),
        "delta": snap["greeks"]["delta"],
        "iv": snap.get("impliedVolatility"),
        "open_interest": contract.get("open_interest"),
        "multiplier": int(contract.get("multiplier", 100)),
    }
