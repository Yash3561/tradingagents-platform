"""
JWT authentication utilities.

Access tokens are short-lived (30 min); sessions persist via rotating refresh
tokens (db/models/refresh_token.py, exchanged at POST /auth/refresh). Tokens
issued before this change carried 30-day lifetimes and stay valid until expiry.
"""
from datetime import datetime, timedelta, UTC
from typing import Optional
import secrets as _secrets
from jose import JWTError, jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.core.postgres import get_db

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


def hash_password(password: str) -> str:
    # Use bcrypt directly — passlib 1.7.4 is incompatible with bcrypt 4+/5+
    import bcrypt
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    import bcrypt
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: int, email: str) -> str:
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "email": email, "iat": now, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """
    Dependency that validates JWT and returns User ORM object.
    Returns None if no token provided (used for optional auth).
    Raises 401 if token is invalid.
    """
    from app.db.models.user import User

    if not token:
        return None

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", 0))
        issued_at = float(payload.get("iat", 0))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Tokens issued before the last password change are revoked
    # (pre-iat legacy tokens have iat=0 and die on first password change).
    if user.password_changed_at is not None:
        changed = user.password_changed_at
        if changed.tzinfo is None:
            changed = changed.replace(tzinfo=UTC)
        if issued_at < changed.timestamp():
            raise HTTPException(
                status_code=401,
                detail="Session expired — please sign in again",
                headers={"WWW-Authenticate": "Bearer"},
            )
    return user


async def require_user(user=Depends(get_current_user)):
    """Strict version — raises 401 if no token at all."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_admin(user=Depends(require_user)):
    """Admin-only endpoints."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_monitoring_key(x_monitoring_key: Optional[str] = Header(default=None)):
    """
    Read-only automated-monitoring endpoints — no user login involved, for
    unattended cloud agents that don't and shouldn't hold anyone's password.
    Fails closed: unset MONITORING_API_KEY means the whole surface is 403,
    never accidentally open. Constant-time compare against timing attacks.
    """
    key = (settings.monitoring_api_key or "").strip()
    if not key or not x_monitoring_key or not _secrets.compare_digest(x_monitoring_key, key):
        raise HTTPException(status_code=403, detail="Invalid or missing monitoring key")
    return True
