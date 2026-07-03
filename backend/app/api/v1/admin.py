"""
Admin endpoints: user management + invite codes.
Router is registered with require_admin — only is_admin users get through.
"""
import secrets
from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field

from app.core.postgres import get_db
from app.core.auth import require_admin
from app.db.models.user import User
from app.db.models.invite_code import InviteCode
from app.db.models.broker_connection import BrokerConnection

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
