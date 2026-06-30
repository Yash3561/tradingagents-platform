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
