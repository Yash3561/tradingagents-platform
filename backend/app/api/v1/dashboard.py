from fastapi import APIRouter
from datetime import datetime, UTC
import httpx
import structlog

from app.config import get_settings

router = APIRouter()
log = structlog.get_logger()
settings = get_settings()


@router.get("/summary")
async def get_summary():
    """Portfolio summary — real data from Alpaca, fallback to mock."""
    if settings.alpaca_api_key and settings.alpaca_api_key != "your_alpaca_key":
        try:
            headers = {
                "APCA-API-KEY-ID": settings.alpaca_api_key,
                "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
            }
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{settings.alpaca_base_url}/v2/account", headers=headers)
            if r.status_code == 200:
                acct = r.json()
                equity = float(acct.get("equity", 0))
                last_equity = float(acct.get("last_equity", equity))
                day_pnl = equity - last_equity
                day_pnl_pct = (day_pnl / last_equity * 100) if last_equity else 0
                return {
                    "equity": round(equity, 2),
                    "day_pnl": round(day_pnl, 2),
                    "day_pnl_pct": round(day_pnl_pct, 2),
                    "unrealized_pnl": round(float(acct.get("unrealized_pl", 0)), 2),
                    "realized_pnl": round(float(acct.get("realized_pl", 0)), 2),
                    "buying_power": round(float(acct.get("buying_power", 0)), 2),
                    "as_of": datetime.now(UTC).isoformat(),
                }
        except Exception as e:
            log.warning("alpaca.account_fetch_failed", error=str(e))

    # Mock fallback (no Alpaca keys or fetch failed)
    return {
        "equity": 100000.00,
        "day_pnl": 0.0,
        "day_pnl_pct": 0.0,
        "unrealized_pnl": 0.0,
        "realized_pnl": 0.0,
        "buying_power": 100000.00,
        "as_of": datetime.now(UTC).isoformat(),
    }


@router.get("/market-pulse")
async def market_pulse():
    """Real-time market indices using yfinance."""
    import yfinance as yf

    symbols = [
        ("SPY", "S&P 500"),
        ("QQQ", "NASDAQ"),
        ("^VIX", "VIX"),
        ("BTC-USD", "BTC"),
        ("^TNX", "10Y"),
    ]

    result = []
    for symbol, label in symbols:
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="2d", interval="1d")
            if len(hist) >= 2:
                prev = float(hist["Close"].iloc[-2])
                curr = float(hist["Close"].iloc[-1])
                change_pct = (curr - prev) / prev * 100
                result.append({
                    "label": label,
                    "ticker": symbol,
                    "value": round(curr, 2),
                    "change_pct": round(change_pct, 2),
                })
            elif len(hist) == 1:
                curr = float(hist["Close"].iloc[-1])
                result.append({
                    "label": label,
                    "ticker": symbol,
                    "value": round(curr, 2),
                    "change_pct": 0.0,
                })
        except Exception as e:
            log.warning("market_pulse.fetch_error", symbol=symbol, error=str(e))

    return result


@router.get("/market-brief")
async def get_market_brief_dashboard():
    """Proxy to analytics market brief — cached for dashboard use."""
    from app.api.v1.analytics import get_market_brief
    return await get_market_brief()


@router.get("/agent-activity")
async def agent_activity():
    """Recent agent runs from DB."""
    try:
        from sqlalchemy import select, desc
        from app.core.postgres import AsyncSessionLocal
        from app.db.models.agent_run import AgentRun

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AgentRun)
                .where(AgentRun.status == "completed")
                .order_by(desc(AgentRun.created_at))
                .limit(10)
            )
            runs = result.scalars().all()
            return [
                {
                    "ticker": r.ticker,
                    "decision": r.decision,
                    "confidence": r.confidence,
                    "model": r.llm_model,
                    "created_at": r.created_at.isoformat(),
                }
                for r in runs
            ]
    except Exception as e:
        log.warning("agent_activity.fetch_error", error=str(e))
        return []
