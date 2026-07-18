import asyncio
import uuid
from datetime import datetime, UTC
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, update

import structlog

from app.core.postgres import get_db
from app.core.auth import require_user
from app.db.models.notification import Notification

log = structlog.get_logger()

router = APIRouter()

# Money events also go out by EMAIL (when SMTP is configured and the user
# hasn't turned off the email_trade_notifications setting). Scan chatter and
# briefs stay in-app only — the inbox should only ring when money moved.
EMAIL_TYPES = {"trade_placed", "stop_loss_hit", "take_profit_hit", "circuit_breaker"}


async def _email_notification(user_id: int, title: str, body: str,
                              ticker: str | None, pnl: float | None) -> None:
    """Fire-and-forget email mirror of a money-event notification."""
    try:
        from app.core.postgres import AsyncSessionLocal
        from app.db.models.user import User
        from app.db.models.user_settings import get_user_setting
        from app.core.mailer import send_email

        enabled = await get_user_setting(user_id, "email_trade_notifications", True)
        if str(enabled).lower() not in ("1", "true", "yes"):
            return
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
        if not user or not user.email:
            return
        pnl_line = f"\nP&L: ${pnl:+,.2f}" if pnl is not None else ""
        subject = f"[TradingAgents] {title}" + (f" ({ticker})" if ticker else "")
        await send_email(
            user.email, subject,
            f"{body}{pnl_line}\n\n— TradingAgents · paper trading, simulated money",
        )
    except Exception as e:
        log.warning("notification.email_failed", user_id=user_id, error=str(e)[:150])


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

    # Email mirror for money events — never blocks or fails the caller
    # (this sits on the order-placement path).
    if user_id is not None and type in EMAIL_TYPES:
        asyncio.create_task(_email_notification(user_id, title, body, ticker, pnl))
