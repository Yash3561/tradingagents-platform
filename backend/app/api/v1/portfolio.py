import asyncio
from fastapi import APIRouter, Depends
import structlog
from datetime import datetime, UTC
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postgres import get_db
from app.core.auth import require_user
from app.broker.alpaca_client import AlpacaClient
from app.broker.credentials import optional_broker

router = APIRouter()
log = structlog.get_logger()


@router.get("/positions")
async def get_positions(broker: AlpacaClient | None = Depends(optional_broker)):
    """Live positions from the user's Alpaca paper account."""
    if broker is None:
        return []
    try:
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, broker.get_positions)
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
            for p in raw
        ]
    except Exception as e:
        log.warning("portfolio.positions_failed", error=str(e))
        return []


@router.get("/allocation")
async def get_allocation(broker: AlpacaClient | None = Depends(optional_broker)):
    """Position allocation breakdown."""
    positions = await get_positions(broker)
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
async def risk_metrics(
    user=Depends(require_user),
    broker: AlpacaClient | None = Depends(optional_broker),
):
    """Portfolio metrics from Alpaca account + computed Sharpe/drawdown from equity curve."""
    from app.workers.equity_tracker import compute_performance_metrics

    acct_data = {}
    if broker is not None:
        try:
            loop = asyncio.get_running_loop()
            acct_data = await loop.run_in_executor(None, broker.get_account)
        except Exception as e:
            log.warning("portfolio.metrics_alpaca_failed", error=str(e))

    equity = float(acct_data.get("equity", 100000))
    last_equity = float(acct_data.get("last_equity", equity))
    long_mv = float(acct_data.get("long_market_value", 0))
    cash = float(acct_data.get("cash", equity))
    day_pnl = equity - last_equity

    perf = await compute_performance_metrics(days=90, user_id=user.id)

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
        "broker_connected": broker is not None,
    }


@router.get("/equity-curve")
async def equity_curve(
    limit: int = 200,
    user=Depends(require_user),
    broker: AlpacaClient | None = Depends(optional_broker),
):
    """
    Historical equity curve for charting.
    Primary source: local equity_snapshots (taken every 15 min, per user).
    Fallback/backfill: Alpaca portfolio history API (daily, 30 days) when <10 local points.
    """
    from app.workers.equity_tracker import get_equity_curve
    local = await get_equity_curve(limit=limit, user_id=user.id)

    if len(local) >= 10:
        return local

    alpaca_points = []
    if broker is not None:
        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, broker.get_portfolio_history)
            if data:
                timestamps = data.get("timestamp", [])
                equities = data.get("equity", [])
                profit_loss = data.get("profit_loss", [])
                for ts, eq, pl in zip(timestamps, equities, profit_loss):
                    if eq and eq > 0:
                        alpaca_points.append({
                            "timestamp": datetime.fromtimestamp(ts, UTC).isoformat(),
                            "equity": round(float(eq), 2),
                            "cash": 0.0,
                            "day_pnl": round(float(pl or 0), 2),
                        })
        except Exception:
            pass

    if not alpaca_points:
        return local

    # Merge: Alpaca history first, then local snapshots (more granular, more recent)
    local_ts_set = {p["timestamp"][:10] for p in local}  # date portion
    filtered_alpaca = [p for p in alpaca_points if p["timestamp"][:10] not in local_ts_set]
    merged = sorted(filtered_alpaca + local, key=lambda x: x["timestamp"])
    return merged[-limit:]


@router.get("/pnl-calendar")
async def get_pnl_calendar(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_user),
    broker: AlpacaClient | None = Depends(optional_broker),
):
    """
    Daily P&L for the last 90 days.
    Returns list of {date, pnl, trades} for calendar heatmap.
    """
    from sqlalchemy import select
    from app.db.models.trade import Trade
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(days=90)

    result = await db.execute(
        select(Trade)
        .where(Trade.user_id == user.id)
        .where(Trade.submitted_at >= cutoff)
        .where(Trade.pnl.isnot(None))
        .order_by(Trade.submitted_at)
    )
    trades = result.scalars().all()

    by_date: dict = {}
    for t in trades:
        if t.submitted_at:
            date_str = t.submitted_at.date().isoformat()
            if date_str not in by_date:
                by_date[date_str] = {"date": date_str, "pnl": 0.0, "trades": 0}
            by_date[date_str]["pnl"] += float(t.pnl or 0)
            by_date[date_str]["trades"] += 1

    # Also try to get daily P&L from the user's Alpaca account history
    if broker is not None:
        try:
            loop = asyncio.get_running_loop()
            hist = await loop.run_in_executor(
                None, lambda: broker.get_portfolio_history(period="3M", timeframe="1D")
            )
            if hist:
                timestamps = hist.get("timestamp", [])
                profit_loss = hist.get("profit_loss", [])
                for ts, pl in zip(timestamps, profit_loss):
                    if pl is not None:
                        date_str = datetime.fromtimestamp(ts, tz=UTC).date().isoformat()
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
