from fastapi import APIRouter, Depends
import httpx
import structlog
from datetime import datetime, UTC
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.postgres import get_db
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
    """Portfolio metrics from Alpaca account + computed Sharpe/drawdown from equity curve."""
    from app.workers.equity_tracker import compute_performance_metrics

    # Fetch live account data
    acct_data = {}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{settings.alpaca_base_url}/v2/account",
                headers=_alpaca_headers(),
            )
        if r.status_code == 200:
            acct_data = r.json()
    except Exception as e:
        log.warning("portfolio.metrics_alpaca_failed", error=str(e))

    equity = float(acct_data.get("equity", 100000))
    last_equity = float(acct_data.get("last_equity", equity))
    long_mv = float(acct_data.get("long_market_value", 0))
    cash = float(acct_data.get("cash", equity))
    day_pnl = equity - last_equity

    # Compute Sharpe + drawdown from historical snapshots
    perf = await compute_performance_metrics(days=90)

    return {
        "equity": round(equity, 2),
        "cash": round(cash, 2),
        "long_market_value": round(long_mv, 2),
        "day_pnl": round(day_pnl, 2),
        "day_pnl_pct": round(day_pnl / last_equity * 100, 2) if last_equity else 0,
        "buying_power": round(float(acct_data.get("buying_power", equity)), 2),
        "cash_pct": round(cash / equity * 100, 1) if equity else 100,
        "invested_pct": round(long_mv / equity * 100, 1) if equity else 0,
        "sharpe": perf.get("sharpe"),
        "max_drawdown": perf.get("max_drawdown"),
        "total_return": perf.get("total_return"),
        "snapshot_count": perf.get("snapshot_count", 0),
    }


@router.get("/equity-curve")
async def equity_curve(limit: int = 200):
    """Historical equity curve for charting."""
    from app.workers.equity_tracker import get_equity_curve
    return await get_equity_curve(limit=limit)


@router.get("/pnl-calendar")
async def get_pnl_calendar(db: AsyncSession = Depends(get_db)):
    """
    Daily P&L for the last 90 days.
    Returns list of {date, pnl, trades} for calendar heatmap.
    """
    from sqlalchemy import select, desc, func
    from app.db.models.trade import Trade
    from datetime import timedelta
    import httpx
    from app.config import get_settings

    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(days=90)

    # Get closed trades with P&L grouped by date
    result = await db.execute(
        select(Trade)
        .where(Trade.submitted_at >= cutoff)
        .where(Trade.pnl.isnot(None))
        .order_by(Trade.submitted_at)
    )
    trades = result.scalars().all()

    # Group by date
    by_date: dict = {}
    for t in trades:
        if t.submitted_at:
            date_str = t.submitted_at.date().isoformat()
            if date_str not in by_date:
                by_date[date_str] = {"date": date_str, "pnl": 0.0, "trades": 0}
            by_date[date_str]["pnl"] += float(t.pnl or 0)
            by_date[date_str]["trades"] += 1

    # Also try to get daily P&L from Alpaca account history
    try:
        headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{settings.alpaca_base_url}/v2/account/portfolio/history",
                headers=headers,
                params={"period": "3M", "timeframe": "1D"},
            )
        if r.status_code == 200:
            hist = r.json()
            timestamps = hist.get("timestamp", [])
            profit_loss = hist.get("profit_loss", [])
            for ts, pl in zip(timestamps, profit_loss):
                if pl is not None:
                    from datetime import datetime, timezone
                    date_str = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
                    if date_str not in by_date:
                        by_date[date_str] = {"date": date_str, "pnl": 0.0, "trades": 0}
                    # Use Alpaca P&L if we don't have trade-level data for that day
                    if by_date[date_str]["trades"] == 0:
                        by_date[date_str]["pnl"] = round(float(pl), 2)
    except Exception:
        pass

    calendar = sorted(by_date.values(), key=lambda x: x["date"])
    for c in calendar:
        c["pnl"] = round(c["pnl"], 2)

    return calendar
