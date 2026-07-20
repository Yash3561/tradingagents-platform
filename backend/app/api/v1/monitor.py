"""
Read-only automated-monitoring endpoints.

Distinct from admin.py on purpose: admin routes need a real logged-in admin
user (JWT). This router is for unattended cloud/cron agents that shouldn't
hold, cache, or type in anyone's password — auth is a single static header
key (require_monitoring_key), checked once, fails closed if unset.

Never expose: broker credentials (even encrypted), password hashes, refresh
tokens. Everything here is data an admin can already see in Strategy Lab —
this just makes it reachable without a browser session.
"""
from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.core.postgres import get_db
from app.core.auth import require_monitoring_key
from app.db.models.user import User
from app.db.models.broker_connection import BrokerConnection
from app.db.models.equity_snapshot import EquitySnapshot
from app.db.models.agent_run import AgentRun
from app.db.models.user_settings import UserSettings

router = APIRouter()


@router.get("/accounts-summary")
async def accounts_summary(db: AsyncSession = Depends(get_db), _=Depends(require_monitoring_key)):
    """
    Per broker-connected account: latest equity + 24h change, strategy mode,
    scan_enabled, and today's AgentRun health (completed/failed/pending
    counts + the most recent failed run's error) — enough to answer "does
    this account look healthy" without a login session or a live broker call
    (equity comes from the existing equity_tracker snapshots, ~15min cadence).
    """
    now = datetime.now(UTC)
    since_24h = now - timedelta(hours=24)
    today = now.strftime("%Y-%m-%d")

    connected = (
        await db.execute(
            select(User)
            .join(BrokerConnection, BrokerConnection.user_id == User.id)
            .order_by(User.id)
        )
    ).scalars().all()

    accounts = []
    for u in connected:
        snaps = (
            await db.execute(
                select(EquitySnapshot.timestamp, EquitySnapshot.equity,
                      EquitySnapshot.positions_count, EquitySnapshot.day_pnl)
                .where(EquitySnapshot.user_id == u.id, EquitySnapshot.timestamp >= since_24h)
                .order_by(EquitySnapshot.timestamp)
            )
        ).all()
        latest_equity = snaps[-1].equity if snaps else None
        base_equity = snaps[0].equity if snaps else None
        change_24h_pct = (
            round((latest_equity / base_equity - 1) * 100, 3)
            if latest_equity and base_equity else None
        )
        last_snapshot_at = snaps[-1].timestamp.isoformat() if snaps else None
        positions_count = snaps[-1].positions_count if snaps else None
        day_pnl = round(snaps[-1].day_pnl, 2) if snaps else None

        mode_row = await db.get(UserSettings, (u.id, "strategy_mode"))
        scan_row = await db.get(UserSettings, (u.id, "scan_enabled"))
        import json as _json
        def _decode(row, default=None):
            if row is None:
                return default
            try:
                return _json.loads(row.value)
            except Exception:
                return row.value
        strategy_mode = _decode(mode_row, "agents")
        scan_enabled = _decode(scan_row, True)

        today_stats = (
            await db.execute(
                select(
                    func.count(AgentRun.id).label("total"),
                    func.count(AgentRun.id).filter(AgentRun.status == "completed").label("completed"),
                    func.count(AgentRun.id).filter(AgentRun.status == "failed").label("failed"),
                    func.count(AgentRun.id).filter(AgentRun.status.in_(("pending", "running"))).label("pending"),
                ).where(AgentRun.user_id == u.id, AgentRun.analysis_date == today)
            )
        ).one()

        last_failed = (
            await db.execute(
                select(AgentRun.ticker, AgentRun.error, AgentRun.created_at)
                .where(AgentRun.user_id == u.id, AgentRun.status == "failed",
                      AgentRun.created_at >= since_24h)
                .order_by(desc(AgentRun.created_at))
                .limit(1)
            )
        ).first()

        accounts.append({
            "user_id": u.id,
            "email": u.email,
            "label": u.full_name or u.email.split("@")[0],
            "strategy_mode": strategy_mode,
            "scan_enabled": bool(scan_enabled),
            "equity": round(latest_equity, 2) if latest_equity else None,
            "change_24h_pct": change_24h_pct,
            "day_pnl": day_pnl,
            "positions_count": positions_count,
            "last_equity_snapshot_at": last_snapshot_at,
            "runs_today": {
                "total": today_stats.total,
                "completed": today_stats.completed,
                "failed": today_stats.failed,
                "pending_or_running": today_stats.pending,
            },
            "last_failed_run_24h": (
                {"ticker": last_failed.ticker, "error": (last_failed.error or "")[:300],
                 "at": last_failed.created_at.isoformat()}
                if last_failed else None
            ),
        })

    return {"generated_at": now.isoformat(), "accounts": accounts}
