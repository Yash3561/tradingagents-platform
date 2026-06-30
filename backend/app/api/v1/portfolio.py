from fastapi import APIRouter
import httpx
import structlog
from app.config import get_settings

router = APIRouter()
log = structlog.get_logger()
settings = get_settings()


def _alpaca_headers():
    return {
        "APCA-API-KEY-ID": settings.alpaca_api_key,
        "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
    }


@router.get("/positions")
async def get_positions():
    """Live positions from Alpaca paper account."""
    if not settings.alpaca_api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{settings.alpaca_base_url}/v2/positions",
                headers=_alpaca_headers(),
            )
            if r.status_code != 200:
                return []
        return [
            {
                "ticker": p["symbol"],
                "qty": float(p["qty"]),
                "market_value": float(p["market_value"]),
                "cost_basis": float(p["cost_basis"]),
                "unrealized_pnl": float(p["unrealized_pl"]),
                "unrealized_pnl_pct": round(float(p["unrealized_plpc"]) * 100, 2),
                "current_price": float(p["current_price"]),
                "avg_entry_price": float(p["avg_entry_price"]),
                "side": p["side"],
            }
            for p in r.json()
        ]
    except Exception as e:
        log.warning("portfolio.positions_failed", error=str(e))
        return []


@router.get("/allocation")
async def get_allocation():
    """Position allocation breakdown."""
    positions = await get_positions()
    total = sum(p["market_value"] for p in positions)
    if not total:
        return []
    return [
        {
            "ticker": p["ticker"],
            "market_value": p["market_value"],
            "pct": round(p["market_value"] / total * 100, 1),
        }
        for p in positions
    ]


@router.get("/risk-metrics")
async def risk_metrics():
    """Basic portfolio metrics from Alpaca account."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{settings.alpaca_base_url}/v2/account",
                headers=_alpaca_headers(),
            )
        if r.status_code != 200:
            raise Exception("Alpaca account fetch failed")
        acct = r.json()
        equity = float(acct.get("equity", 100000))
        last_equity = float(acct.get("last_equity", equity))
        long_mv = float(acct.get("long_market_value", 0))
        cash = float(acct.get("cash", equity))
        day_pnl = equity - last_equity
        return {
            "equity": round(equity, 2),
            "cash": round(cash, 2),
            "long_market_value": round(long_mv, 2),
            "day_pnl": round(day_pnl, 2),
            "day_pnl_pct": round(day_pnl / last_equity * 100, 2) if last_equity else 0,
            "buying_power": round(float(acct.get("buying_power", equity)), 2),
            "cash_pct": round(cash / equity * 100, 1) if equity else 100,
            "invested_pct": round(long_mv / equity * 100, 1) if equity else 0,
            # Placeholder ratios — need historical equity curve to compute properly
            "sharpe": None,
            "max_drawdown": None,
        }
    except Exception as e:
        log.warning("portfolio.metrics_failed", error=str(e))
        return {
            "equity": 100000, "cash": 100000, "long_market_value": 0,
            "day_pnl": 0, "day_pnl_pct": 0, "buying_power": 100000,
            "cash_pct": 100, "invested_pct": 0, "sharpe": None, "max_drawdown": None,
        }
