import asyncio
from fastapi import APIRouter, Depends
from datetime import datetime, UTC
import structlog

from app.config import get_settings
from app.core.auth import require_user
from app.broker.alpaca_client import AlpacaClient
from app.broker.credentials import optional_broker
from app.core.pnl import compute_day_pnl

router = APIRouter()
log = structlog.get_logger()
settings = get_settings()


@router.get("/summary")
async def get_summary(broker: AlpacaClient | None = Depends(optional_broker)):
    """Portfolio summary from the user's Alpaca paper account."""
    if broker is not None:
        try:
            loop = asyncio.get_running_loop()
            acct = await loop.run_in_executor(None, broker.get_account)
            equity = float(acct.get("equity", 0))
            last_equity = float(acct.get("last_equity", 0))
            day_pnl, day_pnl_pct = compute_day_pnl(equity, last_equity)
            return {
                "equity": round(equity, 2),
                "day_pnl": round(day_pnl, 2),
                "day_pnl_pct": round(day_pnl_pct, 2),
                "unrealized_pnl": round(float(acct.get("unrealized_pl", 0)), 2),
                "realized_pnl": round(float(acct.get("realized_pl", 0)), 2),
                "buying_power": round(float(acct.get("buying_power", 0)), 2),
                "broker_connected": True,
                "as_of": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            log.warning("alpaca.account_fetch_failed", error=str(e))

    # No broker connected — zeroed summary; frontend shows the connect banner
    return {
        "equity": 0.0,
        "day_pnl": 0.0,
        "day_pnl_pct": 0.0,
        "unrealized_pnl": 0.0,
        "realized_pnl": 0.0,
        "buying_power": 0.0,
        "broker_connected": False,
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
async def agent_activity(user=Depends(require_user)):
    """Recent agent runs from DB — scoped to the requesting user."""
    try:
        from sqlalchemy import select, desc
        from app.core.postgres import AsyncSessionLocal
        from app.db.models.agent_run import AgentRun

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AgentRun)
                .where(AgentRun.status == "completed")
                .where(AgentRun.user_id == user.id)
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
