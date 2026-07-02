"""
Broker connection API — each user connects their own Alpaca PAPER account.
Keys are verified against Alpaca before being encrypted and stored.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.auth import require_user
from app.core.postgres import get_db
from app.broker import credentials

router = APIRouter()
log = structlog.get_logger()


class ConnectRequest(BaseModel):
    api_key: str
    api_secret: str


@router.get("/status")
async def broker_status(user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    """Connection status + a live account snapshot when connected."""
    conn = await credentials.get_connection(db, user.id)
    if conn is None:
        return {"connected": False}

    out = {
        "connected": conn.status == "connected",
        "provider": conn.provider,
        "account_number": conn.account_number,
        "paper": True,
        "status": conn.status,
        "last_verified_at": conn.last_verified_at.isoformat() if conn.last_verified_at else None,
    }

    client = await credentials.get_client_for_user(user.id)
    if client:
        try:
            import asyncio
            acct = await asyncio.get_running_loop().run_in_executor(None, client.get_account)
            out["equity"] = round(float(acct.get("equity", 0)), 2)
            out["buying_power"] = round(float(acct.get("buying_power", 0)), 2)
            out["cash"] = round(float(acct.get("cash", 0)), 2)
        except Exception as e:
            log.warning("broker.status_account_failed", user_id=user.id, error=str(e))
    return out


@router.post("/connect")
async def connect_broker(
    body: ConnectRequest,
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify the supplied Alpaca PAPER keys and store them (encrypted)."""
    api_key = body.api_key.strip()
    api_secret = body.api_secret.strip()
    if not api_key or not api_secret:
        raise HTTPException(400, "api_key and api_secret are required")

    try:
        conn = await credentials.save_connection(db, user.id, api_key, api_secret)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "connected": True,
        "account_number": conn.account_number,
        "paper": True,
        "message": "Alpaca paper account connected. All trades stay in paper mode.",
    }


@router.delete("/disconnect")
async def disconnect_broker(user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    removed = await credentials.delete_connection(db, user.id)
    if not removed:
        raise HTTPException(404, "No broker connection to remove")
    return {"connected": False, "message": "Broker disconnected. Stored keys deleted."}


@router.post("/verify")
async def verify_broker(user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    """Re-check the stored keys against Alpaca and refresh status."""
    from datetime import datetime, UTC
    from app.core.crypto import decrypt_secret

    conn = await credentials.get_connection(db, user.id)
    if conn is None:
        raise HTTPException(404, "No broker connected")

    api_key = decrypt_secret(conn.api_key_enc)
    api_secret = decrypt_secret(conn.api_secret_enc)
    if not api_key or not api_secret:
        conn.status = "error"
        await db.commit()
        raise HTTPException(400, "Stored keys can no longer be decrypted — please reconnect.")

    try:
        account = await credentials.verify_alpaca_keys(api_key, api_secret)
        conn.status = "connected"
        conn.account_number = account.get("account_number")
        conn.last_verified_at = datetime.now(UTC)
        await db.commit()
        credentials.invalidate_client_cache(user.id)
        return {"connected": True, "account_number": conn.account_number}
    except ValueError as e:
        conn.status = "error"
        await db.commit()
        credentials.invalidate_client_cache(user.id)
        raise HTTPException(400, str(e))
