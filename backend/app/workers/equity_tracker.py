"""
Equity Tracker — takes periodic snapshots of portfolio equity, per user.

Runs every 15 minutes during market hours, and once at EOD.
Snapshots power the equity curve chart and Sharpe / max-drawdown calculations.
Multi-tenant: one snapshot per connected user each cycle. The env-configured
legacy account (user_id NULL) is also snapshotted if keys are present.
"""
from __future__ import annotations
import asyncio
import math
from datetime import datetime, UTC
import structlog

log = structlog.get_logger()

SNAPSHOT_INTERVAL = 900   # 15 minutes
TRADING_DAYS_PER_YEAR = 252


def _fetch_account_snapshot(broker) -> dict | None:
    try:
        acct = broker.get_account()
        positions = broker.get_positions()
        return {
            "equity": float(acct.get("equity", 0)),
            "cash": float(acct.get("cash", 0)),
            "long_market_value": float(acct.get("long_market_value", 0)),
            "day_pnl": float(acct.get("equity", 0)) - float(acct.get("last_equity", 0)),
            "positions_count": len(positions),
        }
    except Exception as e:
        log.warning("equity_tracker.fetch_failed", error=str(e))
        return None


async def take_snapshot_for_user(user_id: int | None, broker) -> bool:
    """Take one equity snapshot for one account and store it. Returns True on success."""
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, _fetch_account_snapshot, broker)

    if not data or data["equity"] <= 0:
        return False

    from app.db.models.equity_snapshot import EquitySnapshot
    from app.core.postgres import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        snap = EquitySnapshot(
            user_id=user_id,
            equity=round(data["equity"], 2),
            cash=round(data["cash"], 2),
            long_market_value=round(data["long_market_value"], 2),
            day_pnl=round(data["day_pnl"], 2),
            positions_count=data["positions_count"],
        )
        db.add(snap)
        await db.commit()

    log.debug("equity_tracker.snapshot", user_id=user_id,
              equity=data["equity"], positions=data["positions_count"])
    return True


async def take_snapshot() -> int:
    """Snapshot every connected user (plus the legacy env account). Returns count taken."""
    from app.broker.credentials import connected_user_ids, get_client_for_user
    from app.broker.alpaca_client import default_client

    taken = 0
    for uid in await connected_user_ids():
        broker = await get_client_for_user(uid)
        if broker is not None:
            try:
                if await take_snapshot_for_user(uid, broker):
                    taken += 1
            except Exception as e:
                log.warning("equity_tracker.user_snapshot_failed", user_id=uid, error=str(e))

    legacy = default_client()
    if legacy.configured:
        try:
            if await take_snapshot_for_user(None, legacy):
                taken += 1
        except Exception as e:
            log.warning("equity_tracker.legacy_snapshot_failed", error=str(e))

    return taken


async def compute_performance_metrics(days: int = 90, user_id: int | None = None) -> dict:
    """
    Compute Sharpe ratio and max drawdown from recent equity snapshots.
    Scoped to one user's snapshots (user_id=None → legacy env account rows).
    """
    from sqlalchemy import select
    from app.db.models.equity_snapshot import EquitySnapshot
    from app.core.postgres import AsyncSessionLocal
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(days=days)

    async with AsyncSessionLocal() as db:
        q = (
            select(EquitySnapshot)
            .where(EquitySnapshot.timestamp >= cutoff)
            .order_by(EquitySnapshot.timestamp)
        )
        q = q.where(EquitySnapshot.user_id == user_id) if user_id is not None \
            else q.where(EquitySnapshot.user_id.is_(None))
        result = await db.execute(q)
        snaps = result.scalars().all()

    if len(snaps) < 5:
        return {"sharpe": None, "max_drawdown": None, "total_return": None,
                "snapshot_count": len(snaps)}

    equities = [s.equity for s in snaps]

    # Daily returns (using consecutive snapshots as proxy)
    returns = [
        (equities[i] - equities[i - 1]) / equities[i - 1]
        for i in range(1, len(equities))
        if equities[i - 1] > 0
    ]

    if not returns:
        return {"sharpe": None, "max_drawdown": None, "total_return": None,
                "snapshot_count": len(snaps)}

    # Sharpe ratio (annualized, assuming risk-free = 0 for simplicity)
    n = len(returns)
    mean_r = sum(returns) / n
    variance = sum((r - mean_r) ** 2 for r in returns) / n
    std_r = math.sqrt(variance) if variance > 0 else 0

    # Scale to daily (snapshots every 15min → ~26 per day → divide by sqrt(26))
    # But we use simple consecutive differences so treat as sub-daily
    snapshots_per_day = SNAPSHOT_INTERVAL / (6.5 * 3600)  # fraction of trading day
    annualization = math.sqrt(TRADING_DAYS_PER_YEAR / snapshots_per_day)
    sharpe = (mean_r / std_r * annualization) if std_r > 0 else None

    # Max drawdown
    peak = equities[0]
    max_dd = 0.0
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak
        if dd > max_dd:
            max_dd = dd

    total_return = (equities[-1] - equities[0]) / equities[0] * 100 if equities[0] > 0 else 0

    return {
        "sharpe": round(sharpe, 2) if sharpe is not None and not math.isnan(sharpe) else None,
        "max_drawdown": round(-max_dd * 100, 2),  # negative pct e.g. -4.2
        "total_return": round(total_return, 2),
        "snapshot_count": len(snaps),
    }


async def get_equity_curve(limit: int = 200, user_id: int | None = None) -> list[dict]:
    """Return recent equity snapshots for charting, scoped to one user."""
    from sqlalchemy import select, desc
    from app.db.models.equity_snapshot import EquitySnapshot
    from app.core.postgres import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        q = select(EquitySnapshot).order_by(desc(EquitySnapshot.timestamp)).limit(limit)
        q = q.where(EquitySnapshot.user_id == user_id) if user_id is not None \
            else q.where(EquitySnapshot.user_id.is_(None))
        result = await db.execute(q)
        snaps = result.scalars().all()

    return [
        {
            "timestamp": s.timestamp.isoformat(),
            "equity": s.equity,
            "cash": s.cash,
            "day_pnl": s.day_pnl,
        }
        for s in reversed(snaps)
    ]


async def run_equity_tracker():
    """
    Continuously snapshot equity every 15 minutes.
    Called from workers/main.py — runs forever.
    """
    log.info("equity_tracker.started")

    while True:
        try:
            await take_snapshot()
        except Exception as e:
            log.error("equity_tracker.cycle.error", error=str(e))

        await asyncio.sleep(SNAPSHOT_INTERVAL)
