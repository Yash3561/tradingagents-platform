import uuid
from datetime import datetime, UTC
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, update

from app.core.postgres import get_db
from app.core.auth import require_user
from app.db.models.notification import Notification

router = APIRouter()


@router.get("/")
async def list_notifications(limit: int = 20, db: AsyncSession = Depends(get_db),
                             user=Depends(require_user)):
    """Return the user's recent notifications, unread first then by created_at desc."""
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.read.asc(), desc(Notification.created_at))
        .limit(limit)
    )
    notifications = result.scalars().all()
    return [_serialize(n) for n in notifications]


@router.get("/unread-count")
async def unread_count(db: AsyncSession = Depends(get_db), user=Depends(require_user)):
    result = await db.execute(
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == user.id)
        .where(Notification.read == False)  # noqa: E712
    )
    count = result.scalar_one()
    return {"count": count}


@router.post("/{notification_id}/read")
async def mark_read(notification_id: str, db: AsyncSession = Depends(get_db),
                    user=Depends(require_user)):
    notif = await db.get(Notification, notification_id)
    if not notif or notif.user_id != user.id:
        from fastapi import HTTPException
        raise HTTPException(404, "Notification not found")
    notif.read = True
    await db.commit()
    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db), user=Depends(require_user)):
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id)
        .where(Notification.read == False).values(read=True)  # noqa: E712
    )
    await db.commit()
    return {"ok": True}


def _serialize(n: Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "ticker": n.ticker,
        "pnl": n.pnl,
        "read": n.read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


async def save_notification(
    type: str,
    title: str,
    body: str,
    ticker: str | None = None,
    pnl: float | None = None,
    user_id: int | None = None,
) -> None:
    """Helper for saving a notification from anywhere in the backend."""
    from app.core.postgres import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        notif = Notification(
            id=str(uuid.uuid4()),
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            ticker=ticker,
            pnl=pnl,
        )
        db.add(notif)
        await db.commit()
