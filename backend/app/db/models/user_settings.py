"""
Per-user settings — same key/value shape as PlatformSettings but scoped to a user.
Reads fall back to the platform-wide default when the user hasn't overridden a key.
"""
import json
from datetime import datetime, UTC
from sqlalchemy import String, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.postgres import Base


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)  # JSON-encoded value
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


async def get_user_setting(user_id: int | None, key: str, default=None):
    """
    Read a user's setting; falls back to the platform setting, then `default`.
    user_id=None reads platform settings directly (legacy single-tenant paths).
    """
    from app.core.postgres import AsyncSessionLocal
    from app.db.models.settings import get_setting as get_platform_setting

    if user_id is not None:
        try:
            async with AsyncSessionLocal() as db:
                row = await db.get(UserSettings, (user_id, key))
                if row is not None:
                    return json.loads(row.value)
        except Exception:
            pass
    return await get_platform_setting(key, default)


async def set_user_setting(db, user_id: int, key: str, value) -> None:
    """Upsert a single user setting inside an existing session (caller commits)."""
    row = await db.get(UserSettings, (user_id, key))
    if row is None:
        db.add(UserSettings(user_id=user_id, key=key, value=json.dumps(value)))
    else:
        row.value = json.dumps(value)
        row.updated_at = datetime.now(UTC)
