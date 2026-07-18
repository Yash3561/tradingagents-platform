import hashlib
import secrets
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr

from app.core.postgres import get_db
from app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_user,
)
from app.core.rate_limit import enforce_rate_limit, client_ip
from app.core.redis_client import get_redis
from app.core import mailer
from app.core.analytics import track
from app.db.models.user import User
from app.db.models.invite_code import InviteCode
from app.db.models.refresh_token import (
    RefreshToken,
    hash_refresh_token,
    issue_refresh_token,
    revoke_family,
    revoke_all_for_user,
    prune_expired,
)

router = APIRouter()

RESET_TOKEN_TTL = 30 * 60        # 30 minutes
VERIFY_TOKEN_TTL = 48 * 3600     # 48 hours


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""
    invite_code: str = ""


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user_id: int
    email: str
    full_name: str | None
    is_admin: bool = False
    email_verified: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str = ""


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class VerifyEmailRequest(BaseModel):
    token: str


async def _token_response(user: User, db: AsyncSession) -> TokenResponse:
    refresh = await issue_refresh_token(db, user.id)
    await prune_expired(db, user.id)
    await db.commit()
    return TokenResponse(
        access_token=create_access_token(user.id, user.email),
        refresh_token=refresh,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_admin=user.is_admin,
        email_verified=user.email_verified,
    )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _validate_password(pw: str) -> None:
    if len(pw) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")


async def _maybe_promote_admin(user: User, db: AsyncSession) -> None:
    """ADMIN_EMAIL env bootstraps the first admin account."""
    from app.config import get_settings
    admin_email = get_settings().admin_email.lower().strip()
    if admin_email and user.email == admin_email and not user.is_admin:
        user.is_admin = True
        await db.commit()
        await db.refresh(user)


async def _send_verification(user: User) -> bool:
    token = secrets.token_urlsafe(32)
    r = await get_redis()
    await r.setex(f"verify:{_hash_token(token)}", VERIFY_TOKEN_TTL, str(user.id))
    return await mailer.send_verification(user.email, token)


async def _check_invite(db: AsyncSession, supplied: str) -> InviteCode | None:
    """
    Validate the invite gate. Returns the DB invite to consume, or None when
    the env code matched / no gate is configured. Raises 403 otherwise.
    """
    from app.config import get_settings
    env_code = get_settings().signup_invite_code
    supplied = supplied.strip()

    if supplied:
        if env_code and secrets.compare_digest(supplied, env_code):
            return None
        result = await db.execute(
            select(InviteCode).where(InviteCode.code == supplied).with_for_update()
        )
        invite = result.scalar_one_or_none()
        if invite and invite.is_usable():
            return invite
        raise HTTPException(status_code=403, detail="Invalid or expired invite code")

    if env_code:
        raise HTTPException(status_code=403, detail="A valid invite code is required to sign up")
    return None


@router.get("/signup-policy")
async def signup_policy():
    """Public: tells the signup form whether an invite code is required."""
    from app.config import get_settings
    return {"invite_required": bool(get_settings().signup_invite_code)}


@router.post("/signup", response_model=TokenResponse)
async def signup(body: SignupRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Register a new account. Gated by SIGNUP_INVITE_CODE (env) and/or
    admin-issued invite codes when configured.
    """
    await enforce_rate_limit(f"signup:ip:{client_ip(request)}", limit=5, window_seconds=3600)

    invite = await _check_invite(db, body.invite_code)

    email = body.email.lower().strip()
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    _validate_password(body.password)

    user = User(
        email=email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name.strip() or None,
    )
    db.add(user)
    if invite is not None:
        invite.used_count += 1
    await db.commit()
    await db.refresh(user)

    await _maybe_promote_admin(user, db)
    await _send_verification(user)
    await track("signup", user.id, invited=invite is not None)
    return await _token_response(user, db)


async def _login(email: str, password: str, request: Request, db: AsyncSession) -> TokenResponse:
    email = email.lower().strip()
    await enforce_rate_limit(f"login:ip:{client_ip(request)}", limit=10, window_seconds=900)
    await enforce_rate_limit(f"login:email:{email}", limit=5, window_seconds=900)

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    await _maybe_promote_admin(user, db)
    await track("login", user.id)
    return await _token_response(user, db)


@router.post("/token", response_model=TokenResponse)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Login with email + password (OAuth2 form). Returns JWT."""
    return await _login(form.username, form.password, request, db)


@router.post("/login", response_model=TokenResponse)
async def login_json(body: SignupRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """JSON login (alternative to form-based /token). Frontend uses this."""
    return await _login(body.email, body.password, request, db)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_session(
    body: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    """
    Exchange a refresh token for a new access + refresh pair (rotation).
    A refresh token works exactly once — replaying a rotated token revokes
    its whole family (stolen-token detection).
    """
    await enforce_rate_limit(f"refresh:ip:{client_ip(request)}", limit=60, window_seconds=900)

    token_hash = hash_refresh_token(body.refresh_token.strip())
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()
    if rt is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if rt.revoked:
        raise HTTPException(status_code=401, detail="Session revoked — please sign in again")

    if rt.used:
        # Replay of a rotated token: someone else holds a copy. Kill the family.
        await revoke_family(db, rt.family_id)
        await db.commit()
        import structlog
        structlog.get_logger().warning("auth.refresh_token_reuse",
                                       user_id=rt.user_id, family_id=rt.family_id)
        raise HTTPException(status_code=401, detail="Session revoked — please sign in again")

    expires = rt.expires_at if rt.expires_at.tzinfo else rt.expires_at.replace(tzinfo=UTC)
    if expires < datetime.now(UTC):
        raise HTTPException(status_code=401, detail="Session expired — please sign in again")

    result = await db.execute(select(User).where(User.id == rt.user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Password changed after this token was minted → session is dead
    if user.password_changed_at is not None:
        changed = user.password_changed_at
        if changed.tzinfo is None:
            changed = changed.replace(tzinfo=UTC)
        created = rt.created_at if rt.created_at.tzinfo else rt.created_at.replace(tzinfo=UTC)
        if created < changed:
            raise HTTPException(status_code=401, detail="Session expired — please sign in again")

    rt.used = True
    new_refresh = await issue_refresh_token(db, user.id, family_id=rt.family_id)
    await db.commit()

    return TokenResponse(
        access_token=create_access_token(user.id, user.email),
        refresh_token=new_refresh,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_admin=user.is_admin,
        email_verified=user.email_verified,
    )


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    """
    Request a password reset link. Always returns ok — never reveals whether
    the email exists.
    """
    email = body.email.lower().strip()
    await enforce_rate_limit(f"forgot:ip:{client_ip(request)}", limit=10, window_seconds=3600)
    await enforce_rate_limit(f"forgot:email:{email}", limit=3, window_seconds=3600)

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user and user.is_active:
        token = secrets.token_urlsafe(32)
        r = await get_redis()
        await r.setex(f"pwreset:{_hash_token(token)}", RESET_TOKEN_TTL, str(user.id))
        await mailer.send_password_reset(user.email, token)

    return {"ok": True, "message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Set a new password using a reset token. Revokes all existing sessions."""
    _validate_password(body.new_password)

    r = await get_redis()
    key = f"pwreset:{_hash_token(body.token.strip())}"
    user_id = await r.get(key)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    await r.delete(key)

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user.hashed_password = hash_password(body.new_password)
    # Whole seconds: JWT iat truncates to the second, and same-second tokens must survive
    user.password_changed_at = datetime.now(UTC).replace(microsecond=0)
    await revoke_all_for_user(db, user.id)
    await db.commit()

    return {"ok": True, "message": "Password updated — sign in with your new password."}


@router.post("/change-password", response_model=TokenResponse)
async def change_password(
    body: ChangePasswordRequest,
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Change password while signed in. All other sessions are revoked;
    the returned token replaces the current one.
    """
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    _validate_password(body.new_password)

    user.hashed_password = hash_password(body.new_password)
    user.password_changed_at = datetime.now(UTC).replace(microsecond=0)
    await revoke_all_for_user(db, user.id)
    await db.commit()
    await db.refresh(user)

    return await _token_response(user, db)


@router.post("/verify-email")
async def verify_email(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    """Confirm email ownership via the emailed token."""
    r = await get_redis()
    key = f"verify:{_hash_token(body.token.strip())}"
    user_id = await r.get(key)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    await r.delete(key)

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user and not user.email_verified:
        user.email_verified = True
        await db.commit()

    return {"ok": True, "message": "Email verified"}


@router.post("/resend-verification")
async def resend_verification(user=Depends(require_user)):
    """Re-send the verification email for the signed-in user."""
    if user.email_verified:
        return {"ok": True, "message": "Email already verified"}
    await enforce_rate_limit(f"resend-verify:{user.id}", limit=3, window_seconds=3600)
    sent = await _send_verification(user)
    from app.config import get_settings
    s = get_settings()
    provider_configured = bool(getattr(s, "brevo_api_key", "") or s.smtp_host)
    if provider_configured and not sent:
        # Don't claim "sent" when the provider rejected it — the failure is in
        # the server logs ([mailer] brevo send failed)
        raise HTTPException(
            status_code=502,
            detail="The verification email could not be sent. Please try again later.",
        )
    return {"ok": True, "message": "Verification email sent"}


@router.get("/me")
async def get_me(user=Depends(get_current_user)):
    """Return current user info. Returns null if not authenticated."""
    if not user:
        return None
    return {
        "user_id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "is_admin": user.is_admin,
        "email_verified": user.email_verified,
        "created_at": user.created_at.isoformat(),
    }


@router.post("/logout")
async def logout(body: LogoutRequest | None = None, db: AsyncSession = Depends(get_db)):
    """
    Revoke the session's refresh-token family server-side. The access JWT
    stays valid until its (30 min) expiry — the client discards it.
    """
    if body and body.refresh_token.strip():
        token_hash = hash_refresh_token(body.refresh_token.strip())
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        rt = result.scalar_one_or_none()
        if rt is not None:
            await revoke_family(db, rt.family_id)
            await db.commit()
    return {"ok": True, "message": "Session revoked"}
