"""
Admin endpoints: user management + invite codes.
Router is registered with require_admin — only is_admin users get through.
"""
import secrets
from datetime import datetime, timedelta, UTC

import structlog
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field

from app.core.postgres import get_db
from app.core.auth import require_admin
from app.db.models.user import User
from app.db.models.invite_code import InviteCode
from app.db.models.broker_connection import BrokerConnection
from app.db.models.analytics_event import AnalyticsEvent
from app.db.models.agent_run import AgentRun
from app.db.models.trade import Trade
from app.db.models.equity_snapshot import EquitySnapshot
from app.db.models.user_settings import UserSettings
from app.db.models.settings import PlatformSettings

router = APIRouter()


class CreateInviteRequest(BaseModel):
    max_uses: int = Field(default=1, ge=1, le=1000)
    expires_days: int | None = Field(default=None, ge=1, le=365)
    note: str = ""


@router.get("/users")
async def list_users(admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    users = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    broker_user_ids = set(
        (await db.execute(select(BrokerConnection.user_id))).scalars().all()
    )
    return [
        {
            "user_id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "is_active": u.is_active,
            "is_admin": u.is_admin,
            "email_verified": u.email_verified,
            "broker_connected": u.id in broker_user_ids,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


@router.post("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Disable/enable an account. Disabled users fail auth on their next request."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot disable your own account")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_admin:
        raise HTTPException(status_code=400, detail="Cannot disable another admin")
    user.is_active = not user.is_active
    await db.commit()
    return {"ok": True, "user_id": user.id, "is_active": user.is_active}


@router.get("/invites")
async def list_invites(admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    invites = (
        (await db.execute(select(InviteCode).order_by(InviteCode.created_at.desc())))
        .scalars()
        .all()
    )
    return [
        {
            "id": i.id,
            "code": i.code,
            "note": i.note,
            "max_uses": i.max_uses,
            "used_count": i.used_count,
            "expires_at": i.expires_at.isoformat() if i.expires_at else None,
            "revoked": i.revoked,
            "usable": i.is_usable(),
            "created_at": i.created_at.isoformat(),
        }
        for i in invites
    ]


@router.post("/invites")
async def create_invite(
    body: CreateInviteRequest, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    invite = InviteCode(
        code=secrets.token_urlsafe(9),  # 12 chars, URL-safe
        note=body.note.strip() or None,
        created_by=admin.id,
        max_uses=body.max_uses,
        expires_at=(
            datetime.now(UTC) + timedelta(days=body.expires_days)
            if body.expires_days
            else None
        ),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return {"ok": True, "id": invite.id, "code": invite.code}


@router.delete("/invites/{invite_id}")
async def revoke_invite(
    invite_id: int, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    invite = (
        await db.execute(select(InviteCode).where(InviteCode.id == invite_id))
    ).scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    invite.revoked = True
    await db.commit()
    return {"ok": True}


@router.get("/trading-halt")
async def get_trading_halt(admin=Depends(require_admin)):
    """Current state of the platform-wide kill switch."""
    from app.db.models.settings import get_setting
    return {"halted": bool(await get_setting("trading_halted", False))}


@router.post("/trading-halt")
async def set_trading_halt(body: dict, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """
    The human big-red-button: halted=true stops every new scan and order
    across every account, immediately (checked at scan start, at order
    placement, and inside the intraday loop's entry gate — three separate
    call sites, same platform_settings row). Does NOT touch stop-loss/exit
    enforcement, which must keep protecting capital regardless.
    """
    import json
    halted = bool(body.get("halted", False))
    row = await db.get(PlatformSettings, "trading_halted")
    if row is None:
        db.add(PlatformSettings(key="trading_halted", value=json.dumps(halted)))
    else:
        row.value = json.dumps(halted)
    await db.commit()
    structlog.get_logger().warning("admin.trading_halt_set", halted=halted, admin_id=admin.id)
    return {"ok": True, "halted": halted}


@router.get("/analytics")
async def product_analytics(
    days: int = 14, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Daily activity series + acquisition funnel for the admin dashboard."""
    days = max(1, min(days, 90))
    since = datetime.now(UTC) - timedelta(days=days)
    day = func.date_trunc("day", AnalyticsEvent.created_at).label("day")

    # Daily: distinct active users + signups + total events
    rows = (
        await db.execute(
            select(
                day,
                func.count(func.distinct(AnalyticsEvent.user_id)).label("active_users"),
                func.count(AnalyticsEvent.id).label("events"),
                func.count(AnalyticsEvent.id)
                .filter(AnalyticsEvent.event == "signup")
                .label("signups"),
            )
            .where(AnalyticsEvent.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
    ).all()
    by_day = {
        r.day.date().isoformat(): {
            "active_users": r.active_users,
            "events": r.events,
            "signups": r.signups,
        }
        for r in rows
    }
    # Zero-fill so charts show the quiet days too
    daily = []
    for i in range(days - 1, -1, -1):
        d = (datetime.now(UTC) - timedelta(days=i)).date().isoformat()
        daily.append({"date": d, **by_day.get(d, {"active_users": 0, "events": 0, "signups": 0})})

    # Event mix (last 7 days)
    week_ago = datetime.now(UTC) - timedelta(days=7)
    event_rows = (
        await db.execute(
            select(AnalyticsEvent.event, func.count(AnalyticsEvent.id))
            .where(AnalyticsEvent.created_at >= week_ago)
            .group_by(AnalyticsEvent.event)
            .order_by(func.count(AnalyticsEvent.id).desc())
        )
    ).all()

    # Funnel from source-of-truth tables (covers users predating analytics)
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    broker_users = (
        await db.execute(select(func.count(func.distinct(BrokerConnection.user_id))))
    ).scalar() or 0
    analysis_users = (
        await db.execute(
            select(func.count(func.distinct(AgentRun.user_id))).where(
                AgentRun.user_id.is_not(None)
            )
        )
    ).scalar() or 0
    trading_users = (
        await db.execute(
            select(func.count(func.distinct(Trade.user_id))).where(Trade.user_id.is_not(None))
        )
    ).scalar() or 0
    # Active in the last 7 days (any tracked event)
    wau = (
        await db.execute(
            select(func.count(func.distinct(AnalyticsEvent.user_id))).where(
                AnalyticsEvent.created_at >= week_ago, AnalyticsEvent.user_id.is_not(None)
            )
        )
    ).scalar() or 0

    return {
        "daily": daily,
        "events_7d": [{"event": e, "count": c} for e, c in event_rows],
        "funnel": {
            "signed_up": total_users,
            "connected_broker": broker_users,
            "ran_analysis": analysis_users,
            "placed_trade": trading_users,
        },
        "wau": wau,
    }


STRATEGY_KEYS = [
    "strategy_mode",
    "scan_enabled", "long_only", "min_confidence_to_trade",
    "position_size_pct", "stop_loss_pct", "take_profit_pct",
    "scan_max_candidates", "custom_watchlist",
    "quant_trend_rsi_min", "quant_trend_rsi_max", "quant_require_macd",
    "quant_meanrev_rsi_max", "quant_exit_rsi", "quant_stop_atr_mult",
    "quant_rr_ratio", "quant_regime_gate",
    "intraday_setup", "intraday_stop_atr_mult", "intraday_rr",
    "intraday_risk_pct", "intraday_max_trades_day", "intraday_max_concurrent",
    "intraday_daily_loss_halt_pct",
    "earnings_surprise_min_pct", "earnings_require_gap_up", "earnings_stop_atr_mult",
    "earnings_rr_ratio", "earnings_hold_days", "earnings_position_size_pct",
    "momentum_lookback_days", "momentum_skip_days", "momentum_top_n",
    "momentum_rebalance_days", "momentum_weighting", "momentum_exposure_pct",
    "max_orders_per_day", "max_order_notional_pct",
    "pead_options_target_days", "pead_options_target_delta", "pead_options_hold_days",
    "pead_options_target_gain_pct", "pead_options_max_loss_pct", "pead_options_position_pct",
]


@router.get("/strategy-lab")
async def strategy_lab(
    days: int = 60, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """
    Compare all broker-connected accounts side by side: equity curve
    (% change from each account's first snapshot in range), trade stats,
    and the strategy-relevant settings each account runs with.
    """
    days = max(7, min(days, 365))
    since = datetime.now(UTC) - timedelta(days=days)

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
                select(EquitySnapshot.timestamp, EquitySnapshot.equity)
                .where(EquitySnapshot.user_id == u.id, EquitySnapshot.timestamp >= since)
                .order_by(EquitySnapshot.timestamp)
            )
        ).all()
        base = snaps[0].equity if snaps and snaps[0].equity else None
        # Downsample to ~200 points so charts stay light with 15-min snapshots
        step = max(1, len(snaps) // 200)
        curve = [
            {
                "t": s.timestamp.isoformat(),
                "pct": round((s.equity / base - 1) * 100, 3) if base else 0.0,
                "equity": round(s.equity, 2),
            }
            for s in snaps[::step]
        ]

        tstats = (
            await db.execute(
                select(
                    func.count(Trade.id).label("total"),
                    func.count(Trade.id).filter(Trade.closed_at.is_not(None)).label("closed"),
                    func.count(Trade.id)
                    .filter(Trade.pnl.is_not(None), Trade.pnl > 0)
                    .label("wins"),
                    func.coalesce(func.sum(Trade.pnl), 0).label("pnl"),
                ).where(Trade.user_id == u.id)
            )
        ).one()
        runs = (
            await db.execute(
                select(func.count(AgentRun.id)).where(AgentRun.user_id == u.id)
            )
        ).scalar() or 0

        srows = (
            await db.execute(
                select(UserSettings.key, UserSettings.value).where(
                    UserSettings.user_id == u.id, UserSettings.key.in_(STRATEGY_KEYS)
                )
            )
        ).all()
        import json as _json
        settings_map = {}
        for k, v in srows:
            try:
                settings_map[k] = _json.loads(v)
            except Exception:
                settings_map[k] = v
        watchlist = settings_map.pop("custom_watchlist", None)

        accounts.append(
            {
                "user_id": u.id,
                "email": u.email,
                "label": (u.full_name or u.email.split("@")[0]),
                "curve": curve,
                "return_pct": curve[-1]["pct"] if curve else None,
                "equity": curve[-1]["equity"] if curve else None,
                "trades_total": tstats.total,
                "trades_closed": tstats.closed,
                "wins": tstats.wins,
                "win_rate": round(tstats.wins / tstats.closed, 3) if tstats.closed else None,
                "total_pnl": round(float(tstats.pnl), 2),
                "agent_runs": runs,
                "settings": settings_map,
                "watchlist_size": len(watchlist) if isinstance(watchlist, list) else None,
            }
        )

    return {"days": days, "accounts": accounts}


@router.get("/stats")
async def platform_stats(admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count(User.id)))).scalar() or 0
    active = (
        await db.execute(select(func.count(User.id)).where(User.is_active.is_(True)))
    ).scalar() or 0
    verified = (
        await db.execute(select(func.count(User.id)).where(User.email_verified.is_(True)))
    ).scalar() or 0
    connected = (
        await db.execute(select(func.count(func.distinct(BrokerConnection.user_id))))
    ).scalar() or 0
    return {
        "total_users": total,
        "active_users": active,
        "verified_users": verified,
        "broker_connected": connected,
    }


# ── Research: walk-forward policy tournament (see app/research/) ────────────

class ResearchRunRequest(BaseModel):
    start: str = "2013-01-01"
    train_years: int = Field(default=4, ge=1, le=8)
    test_years: int = Field(default=1, ge=1, le=3)
    holdout_months: int = Field(default=12, ge=3, le=24)
    quick: bool = False


@router.post("/research/run")
async def launch_research(
    body: ResearchRunRequest,
    background_tasks: BackgroundTasks,
    admin=Depends(require_admin),
):
    """
    Launch a walk-forward tournament over the deterministic policy grid.
    CPU-bound, minutes to ~an hour — runs in a worker thread; poll
    GET /admin/research/latest for status + report.
    """
    from app.core.redis_client import get_redis
    r = await get_redis()
    if await r.get("research:status") == "running":
        raise HTTPException(status_code=409, detail="A research run is already in progress")
    await r.set("research:status", "running")
    await r.set("research:started_at", datetime.now(UTC).isoformat())

    async def _run():
        import asyncio
        import json as _json
        from app.research.walkforward import run_walkforward
        from app.research.engine import Policy

        grid = None
        start = body.start
        if body.quick:
            grid = [Policy(), Policy(regime_mode="off"), Policy(require_macd=False),
                    Policy(allow_meanrev=False), Policy(allow_trend=False)]
            start = "2019-01-01"
        loop = asyncio.get_running_loop()
        try:
            report = await loop.run_in_executor(None, lambda: run_walkforward(
                start=start, train_years=body.train_years, test_years=body.test_years,
                holdout_months=body.holdout_months, grid=grid,
            ))
            await r.set("research:report", _json.dumps(report, default=str))
            await r.set("research:status", "completed")
        except Exception as e:
            await r.set("research:status", f"failed: {e}")

    background_tasks.add_task(_run)
    return {"status": "started"}


@router.get("/research/latest")
async def research_latest(admin=Depends(require_admin)):
    """Status + most recent tournament report."""
    import json as _json
    from app.core.redis_client import get_redis
    r = await get_redis()
    status = await r.get("research:status")
    report = await r.get("research:report")
    return {
        "status": status or "never_run",
        "started_at": await r.get("research:started_at"),
        "report": _json.loads(report) if report else None,
    }
