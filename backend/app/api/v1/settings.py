"""
Settings API — per-user configuration on top of platform defaults.

Reads return platform defaults merged with the user's overrides.
Writes go to the user's own settings rows — one user's risk sliders can never
affect another user. Platform-level LLM keys can still be hot-reloaded (operator).
Alpaca keys are NOT handled here anymore — use /api/v1/broker/connect.
"""
import json
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.postgres import get_db
from app.core.auth import require_user
from app.db.models.settings import PlatformSettings, DEFAULTS
from app.db.models.user_settings import UserSettings, set_user_setting

router = APIRouter()

# Keys every user may override for themselves
USER_SETTING_KEYS = set(DEFAULTS.keys()) | {"custom_watchlist"}

# Platform-level keys (operator only): LLM credentials hot-reloaded into env
PLATFORM_KEY_ENV_MAP = {
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "nvidia_api_key": "NVIDIA_API_KEY",
}


def _decode(value: str) -> object:
    try:
        return json.loads(value)
    except Exception:
        return value


@router.get("/")
async def list_settings(db: AsyncSession = Depends(get_db), user=Depends(require_user)):
    """Platform defaults merged with this user's overrides."""
    result = await db.execute(select(PlatformSettings))
    merged = {r.key: _decode(r.value) for r in result.scalars().all()}

    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user.id))
    for r in result.scalars().all():
        merged[r.key] = _decode(r.value)

    # Never expose stored platform secrets to arbitrary users
    for secret_key in PLATFORM_KEY_ENV_MAP:
        merged.pop(secret_key, None)
    return merged


@router.post("/")
async def upsert_settings(body: dict, db: AsyncSession = Depends(get_db),
                          user=Depends(require_user)):
    """
    Accept a dict of key→value pairs.
    Known user keys → this user's settings. LLM keys → platform (hot-reloaded).
    Unknown keys are stored per-user too (forward compatible).
    """
    if not body:
        raise HTTPException(status_code=400, detail="Request body must be a non-empty dict")

    updated: list[str] = []
    hot_reloaded = False

    for key, val in body.items():
        if key in PLATFORM_KEY_ENV_MAP:
            row = await db.get(PlatformSettings, key)
            if row is None:
                db.add(PlatformSettings(key=key, value=json.dumps(val)))
            else:
                row.value = json.dumps(val)
                row.updated_at = datetime.now(UTC)
            if isinstance(val, str) and val.strip():
                import os
                os.environ[PLATFORM_KEY_ENV_MAP[key]] = val.strip()
                hot_reloaded = True
        elif key in ("alpaca_api_key", "alpaca_api_secret", "alpaca_base_url"):
            # Broker keys moved to /broker/connect — ignore silently so old UI payloads don't error
            continue
        else:
            await set_user_setting(db, user.id, key, val)
        updated.append(key)

    await db.commit()

    if hot_reloaded:
        from app.config import get_settings
        get_settings.cache_clear()

    return {"ok": True, "updated": updated, "hot_reloaded": hot_reloaded}


# ── Watchlist management (per user) ────────────────────────────────────────────

DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD",
    "AVGO", "ORCL", "ASML", "TSM", "NFLX", "ADBE", "CRM", "COIN",
    "PLTR", "SNOW", "UBER", "SHOP", "JPM", "GS", "BAC", "V", "MA",
    "UNH", "LLY", "JNJ", "XOM", "CVX", "SMCI", "ARM", "QCOM", "TXN",
    "INTC", "PYPL", "XYZ", "MSTR", "HOOD",  # XYZ = Block (formerly SQ, delisted 2025)
]


async def _load_user_watchlist(db: AsyncSession, user_id: int) -> list[str] | None:
    row = await db.get(UserSettings, (user_id, "custom_watchlist"))
    if row is None:
        return None
    try:
        tickers = _decode(row.value)
        return tickers if isinstance(tickers, list) else None
    except Exception:
        return None


@router.get("/watchlist")
async def get_watchlist(db: AsyncSession = Depends(get_db), user=Depends(require_user)):
    """Return this user's watchlist. Falls back to default if not customized."""
    custom = await _load_user_watchlist(db, user.id)
    if custom is not None:
        return {"tickers": custom, "is_custom": True, "count": len(custom)}
    return {"tickers": DEFAULT_WATCHLIST, "is_custom": False, "count": len(DEFAULT_WATCHLIST)}


@router.post("/watchlist")
async def update_watchlist(body: dict, db: AsyncSession = Depends(get_db),
                           user=Depends(require_user)):
    """Replace this user's entire watchlist. Body: {"tickers": ["AAPL", ...]}"""
    tickers = body.get("tickers", [])
    clean = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))[:100]
    await set_user_setting(db, user.id, "custom_watchlist", clean)
    await db.commit()
    return {"tickers": clean, "count": len(clean)}


@router.post("/watchlist/add")
async def add_to_watchlist(body: dict, db: AsyncSession = Depends(get_db),
                           user=Depends(require_user)):
    """Add a single ticker to this user's watchlist. Body: {"ticker": "HOOD"}"""
    ticker = body.get("ticker", "").strip().upper()
    if not ticker or len(ticker) > 10:
        raise HTTPException(400, "Invalid ticker")

    current = await _load_user_watchlist(db, user.id)
    if current is None:
        current = list(DEFAULT_WATCHLIST)
    if ticker not in current:
        current.append(ticker)

    await set_user_setting(db, user.id, "custom_watchlist", current)
    await db.commit()
    return {"tickers": current, "count": len(current), "added": ticker}


@router.delete("/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str, db: AsyncSession = Depends(get_db),
                                user=Depends(require_user)):
    """Remove a ticker from this user's watchlist."""
    ticker = ticker.strip().upper()
    current = await _load_user_watchlist(db, user.id)
    if current is None:
        current = list(DEFAULT_WATCHLIST)
    current = [t for t in current if t != ticker]

    await set_user_setting(db, user.id, "custom_watchlist", current)
    await db.commit()
    return {"tickers": current, "count": len(current), "removed": ticker}


@router.post("/watchlist/reset")
async def reset_watchlist(db: AsyncSession = Depends(get_db), user=Depends(require_user)):
    """Reset to default watchlist by clearing the user's custom setting."""
    row = await db.get(UserSettings, (user.id, "custom_watchlist"))
    if row is not None:
        await db.delete(row)
        await db.commit()
    return {"tickers": DEFAULT_WATCHLIST, "count": len(DEFAULT_WATCHLIST), "reset": True}


# NOTE: keep this LAST — "/{key}" would otherwise shadow "/watchlist" above.
@router.get("/{key}")
async def get_setting_by_key(key: str, db: AsyncSession = Depends(get_db),
                             user=Depends(require_user)):
    """Return a single setting value (user override first, then platform)."""
    if key in PLATFORM_KEY_ENV_MAP:
        raise HTTPException(status_code=403, detail="Secret keys are not readable")

    row = await db.get(UserSettings, (user.id, key))
    if row is not None:
        return {"key": key, "value": _decode(row.value),
                "updated_at": row.updated_at.isoformat() if row.updated_at else None}

    prow = await db.get(PlatformSettings, key)
    if prow is None:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    return {"key": key, "value": _decode(prow.value),
            "updated_at": prow.updated_at.isoformat() if prow.updated_at else None}
