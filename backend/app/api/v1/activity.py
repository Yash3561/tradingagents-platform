import uuid
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.postgres import get_db
from app.db.models.activity_log import ActivityLog

router = APIRouter()


@router.get("/")
async def list_activity(
    limit: int = 50,
    feature: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return recent activity logs, filterable by feature."""
    q = select(ActivityLog).order_by(desc(ActivityLog.created_at)).limit(limit)
    if feature:
        q = q.where(ActivityLog.feature == feature)
    result = await db.execute(q)
    logs = result.scalars().all()
    return [_serialize(log) for log in logs]


def _serialize(log: ActivityLog) -> dict:
    return {
        "id": log.id,
        "feature": log.feature,
        "action": log.action,
        "ticker": log.ticker,
        "details": log.details,
        "result": log.result,
        "duration_s": log.duration_s,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


async def log_activity(
    feature: str,
    action: str,
    ticker: str | None = None,
    details: dict | None = None,
    result: str | None = None,
    duration_s: float | None = None,
) -> None:
    """Helper for writing activity log entries from anywhere in the backend."""
    from app.core.postgres import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        entry = ActivityLog(
            id=str(uuid.uuid4()),
            feature=feature,
            action=action,
            ticker=ticker,
            details=details or {},
            result=result,
            duration_s=duration_s,
        )
        db.add(entry)
        await db.commit()
