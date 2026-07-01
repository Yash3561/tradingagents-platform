"""
Settings API — functional CRUD for platform configuration.
All values stored in PostgreSQL platform_settings table as JSON-encoded strings.
"""
import json
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.postgres import get_db
from app.db.models.settings import PlatformSettings

router = APIRouter()


def _decode(row: PlatformSettings) -> object:
    """Decode JSON-encoded value back to Python type."""
    try:
        return json.loads(row.value)
    except Exception:
        return row.value


@router.get("/")
async def list_settings(db: AsyncSession = Depends(get_db)):
    """Return all settings as a flat key→value dict."""
    result = await db.execute(select(PlatformSettings))
    rows = result.scalars().all()
    return {r.key: _decode(r) for r in rows}


@router.post("/")
async def upsert_settings(body: dict, db: AsyncSession = Depends(get_db)):
    """
    Accept a dict of key→value pairs and upsert each one.
    Values can be any JSON-serialisable type.
    """
    if not body:
        raise HTTPException(status_code=400, detail="Request body must be a non-empty dict")

    updated: list[str] = []
    for key, val in body.items():
        row = await db.get(PlatformSettings, key)
        if row is None:
            row = PlatformSettings(key=key, value=json.dumps(val))
            db.add(row)
        else:
            row.value = json.dumps(val)
            row.updated_at = datetime.now(UTC)
        updated.append(key)

    await db.commit()
    return {"ok": True, "updated": updated}


@router.get("/{key}")
async def get_setting_by_key(key: str, db: AsyncSession = Depends(get_db)):
    """Return a single setting value by key."""
    row = await db.get(PlatformSettings, key)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    return {"key": key, "value": _decode(row), "updated_at": row.updated_at.isoformat() if row.updated_at else None}


# ── Watchlist management ────────────────────────────────────────────────────────

DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD",
    "AVGO", "ORCL", "ASML", "TSM", "NFLX", "ADBE", "CRM", "COIN",
    "PLTR", "SNOW", "UBER", "SHOP", "JPM", "GS", "BAC", "V", "MA",
    "UNH", "LLY", "JNJ", "XOM", "CVX", "SMCI", "ARM", "QCOM", "TXN",
    "INTC", "PYPL", "SQ", "ADBE", "MSTR", "HOOD",
]


@router.get("/watchlist")
async def get_watchlist(db: AsyncSession = Depends(get_db)):
    """Return current watchlist. Falls back to default if not customized."""
    from app.db.models.settings import get_setting
    custom = await get_setting(db, "custom_watchlist")
    if custom:
        import json
        try:
            tickers = json.loads(custom) if isinstance(custom, str) else custom
            return {"tickers": tickers, "is_custom": True, "count": len(tickers)}
        except Exception:
            pass
    return {"tickers": DEFAULT_WATCHLIST, "is_custom": False, "count": len(DEFAULT_WATCHLIST)}


@router.post("/watchlist")
async def update_watchlist(body: dict, db: AsyncSession = Depends(get_db)):
    """
    Replace entire watchlist.
    Body: {"tickers": ["AAPL", "MSFT", ...]}
    """
    import json
    from app.db.models.settings import PlatformSettings
    from sqlalchemy import select
    from datetime import datetime, UTC

    tickers = body.get("tickers", [])
    # Validate: uppercase, strip, deduplicate, max 100
    clean = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))[:100]

    result = await db.execute(select(PlatformSettings).where(PlatformSettings.key == "custom_watchlist"))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = json.dumps(clean)
        setting.updated_at = datetime.now(UTC)
    else:
        db.add(PlatformSettings(key="custom_watchlist", value=json.dumps(clean)))
    await db.commit()
    return {"tickers": clean, "count": len(clean)}


@router.post("/watchlist/add")
async def add_to_watchlist(body: dict, db: AsyncSession = Depends(get_db)):
    """Add a single ticker to watchlist. Body: {"ticker": "HOOD"}"""
    import json
    from app.db.models.settings import get_setting, PlatformSettings
    from sqlalchemy import select
    from datetime import datetime, UTC

    ticker = body.get("ticker", "").strip().upper()
    if not ticker or len(ticker) > 10:
        raise HTTPException(400, "Invalid ticker")

    custom_raw = await get_setting(db, "custom_watchlist")
    if custom_raw:
        try:
            current = json.loads(custom_raw) if isinstance(custom_raw, str) else custom_raw
        except Exception:
            current = list(DEFAULT_WATCHLIST)
    else:
        current = list(DEFAULT_WATCHLIST)

    if ticker not in current:
        current.append(ticker)

    result = await db.execute(select(PlatformSettings).where(PlatformSettings.key == "custom_watchlist"))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = json.dumps(current)
        setting.updated_at = datetime.now(UTC)
    else:
        db.add(PlatformSettings(key="custom_watchlist", value=json.dumps(current)))
    await db.commit()
    return {"tickers": current, "count": len(current), "added": ticker}


@router.delete("/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str, db: AsyncSession = Depends(get_db)):
    """Remove a ticker from watchlist."""
    import json
    from app.db.models.settings import get_setting, PlatformSettings
    from sqlalchemy import select
    from datetime import datetime, UTC

    ticker = ticker.strip().upper()
    custom_raw = await get_setting(db, "custom_watchlist")
    if custom_raw:
        try:
            current = json.loads(custom_raw) if isinstance(custom_raw, str) else custom_raw
        except Exception:
            current = list(DEFAULT_WATCHLIST)
    else:
        current = list(DEFAULT_WATCHLIST)

    current = [t for t in current if t != ticker]

    result = await db.execute(select(PlatformSettings).where(PlatformSettings.key == "custom_watchlist"))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = json.dumps(current)
        setting.updated_at = datetime.now(UTC)
    else:
        db.add(PlatformSettings(key="custom_watchlist", value=json.dumps(current)))
    await db.commit()
    return {"tickers": current, "count": len(current), "removed": ticker}


@router.post("/watchlist/reset")
async def reset_watchlist(db: AsyncSession = Depends(get_db)):
    """Reset to default watchlist by clearing custom setting."""
    from app.db.models.settings import PlatformSettings
    from sqlalchemy import select

    result = await db.execute(select(PlatformSettings).where(PlatformSettings.key == "custom_watchlist"))
    setting = result.scalar_one_or_none()
    if setting:
        await db.delete(setting)
        await db.commit()
    return {"tickers": DEFAULT_WATCHLIST, "count": len(DEFAULT_WATCHLIST), "reset": True}
