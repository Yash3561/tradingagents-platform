"""
Public AI track record — anonymized platform-wide aggregates.

No auth: this is the shareable proof-of-performance page. Nothing user-scoped
leaves this endpoint — tickers/decisions/confidence only, never accounts or
user ids. Redis-cached 5 minutes so it stays cheap under public traffic.
"""
import json
from datetime import datetime, UTC

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.postgres import get_db
from app.core.redis_client import get_redis
from app.db.models.agent_run import AgentRun
from app.db.models.trade import Trade

router = APIRouter()

CACHE_KEY = "track_record:v1"
CACHE_TTL = 300


@router.get("/")
async def track_record(db: AsyncSession = Depends(get_db)):
    try:
        r = await get_redis()
        cached = await r.get(CACHE_KEY)
        if cached:
            return json.loads(cached)
    except Exception:
        r = None

    completed = AgentRun.status == "completed"

    total_analyses = (
        await db.execute(select(func.count(AgentRun.id)).where(completed))
    ).scalar() or 0

    decision_rows = (
        await db.execute(
            select(AgentRun.decision, func.count(AgentRun.id))
            .where(completed, AgentRun.decision.is_not(None))
            .group_by(AgentRun.decision)
        )
    ).all()

    avg_confidence = (
        await db.execute(
            select(func.avg(AgentRun.confidence)).where(completed, AgentRun.confidence.is_not(None))
        )
    ).scalar()

    # Closed AI-placed trades (agent_run_id set = the pipeline placed it)
    closed_ai = (
        Trade.agent_run_id.is_not(None),
        Trade.closed_at.is_not(None),
        Trade.pnl.is_not(None),
    )
    trade_stats = (
        await db.execute(
            select(
                func.count(Trade.id).label("closed"),
                func.count(Trade.id).filter(Trade.pnl > 0).label("wins"),
                func.coalesce(func.sum(Trade.pnl), 0).label("total_pnl"),
                func.avg(Trade.pnl).filter(Trade.pnl > 0).label("avg_win"),
                func.avg(Trade.pnl).filter(Trade.pnl < 0).label("avg_loss"),
            ).where(*closed_ai)
        )
    ).one()

    # Monthly series: analyses run + trade win rate
    month = func.date_trunc("month", AgentRun.created_at).label("month")
    monthly_runs = (
        await db.execute(
            select(month, func.count(AgentRun.id)).where(completed).group_by(month).order_by(month)
        )
    ).all()
    tmonth = func.date_trunc("month", Trade.closed_at).label("month")
    monthly_trades = {
        row.month.date().isoformat()[:7]: {"closed": row.closed, "wins": row.wins}
        for row in (
            await db.execute(
                select(
                    tmonth,
                    func.count(Trade.id).label("closed"),
                    func.count(Trade.id).filter(Trade.pnl > 0).label("wins"),
                )
                .where(*closed_ai)
                .group_by(tmonth)
            )
        ).all()
    }
    monthly = []
    for m, count in monthly_runs:
        key = m.date().isoformat()[:7]
        t = monthly_trades.get(key, {"closed": 0, "wins": 0})
        monthly.append(
            {
                "month": key,
                "analyses": count,
                "closed_trades": t["closed"],
                "win_rate": round(t["wins"] / t["closed"], 3) if t["closed"] else None,
            }
        )

    # Recent AI calls — ticker/decision/confidence only, no user attribution
    recent = [
        {
            "ticker": run.ticker,
            "decision": run.decision,
            "confidence": run.confidence,
            "date": run.created_at.date().isoformat(),
        }
        for run in (
            await db.execute(
                select(AgentRun)
                .where(completed, AgentRun.decision.is_not(None))
                .order_by(AgentRun.created_at.desc())
                .limit(20)
            )
        ).scalars()
    ]

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_analyses": total_analyses,
        "decisions": {d: c for d, c in decision_rows},
        "avg_confidence": round(float(avg_confidence), 3) if avg_confidence else None,
        "trades": {
            "closed": trade_stats.closed,
            "wins": trade_stats.wins,
            "win_rate": round(trade_stats.wins / trade_stats.closed, 3)
            if trade_stats.closed
            else None,
            "total_pnl": round(float(trade_stats.total_pnl), 2),
            "avg_win": round(float(trade_stats.avg_win), 2) if trade_stats.avg_win else None,
            "avg_loss": round(float(trade_stats.avg_loss), 2) if trade_stats.avg_loss else None,
        },
        "monthly": monthly,
        "recent": recent,
        "disclaimer": "Paper trading only. Simulated results do not represent real returns and are not financial advice.",
    }

    if r is not None:
        try:
            await r.setex(CACHE_KEY, CACHE_TTL, json.dumps(payload))
        except Exception:
            pass
    return payload
