"""
Rotating refresh tokens — the durable half of the session.

Access JWTs are short-lived (30 min); the client exchanges its refresh token
for a fresh pair via POST /auth/refresh. Rotation is single-use: every
exchange marks the old token `used` and issues a replacement in the same
`family_id`. Presenting a used token again is treated as theft (someone
replayed a stolen token after the real client already rotated it) and the
whole family is revoked.

Only the SHA-256 of the token is stored — a DB leak exposes no usable tokens.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, UTC

from sqlalchemy import String, Boolean, DateTime, Integer, update, delete
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postgres import Base

REFRESH_TOKEN_EXPIRE_DAYS = 30


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    family_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    used: Mapped[bool] = mapped_column(Boolean, default=False)      # rotated away
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)   # killed outright


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


async def issue_refresh_token(db: AsyncSession, user_id: int,
                              family_id: str | None = None) -> str:
    """Create a refresh token row; returns the raw token (only time it exists)."""
    raw = secrets.token_urlsafe(48)
    db.add(RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(raw),
        family_id=family_id or str(uuid.uuid4()),
        expires_at=datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    return raw


async def revoke_family(db: AsyncSession, family_id: str) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id)
        .values(revoked=True)
    )


async def revoke_all_for_user(db: AsyncSession, user_id: int) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id)
        .values(revoked=True)
    )


async def prune_expired(db: AsyncSession, user_id: int) -> None:
    """Opportunistic cleanup — dead rows for this user only, so it stays cheap."""
    await db.execute(
        delete(RefreshToken)
        .where(RefreshToken.user_id == user_id,
               RefreshToken.expires_at < datetime.now(UTC))
    )
