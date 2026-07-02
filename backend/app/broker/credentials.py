"""
Per-user broker credential service.

Keys are verified against Alpaca's paper API before being stored (Fernet-encrypted).
Every connection is forced to the paper base URL — this is the multi-tenant paper
phase; live trading is a deliberate future decision, not a config option.
"""
from __future__ import annotations

import time
from datetime import datetime, UTC

import httpx
import structlog
from fastapi import Depends, HTTPException

from app.broker.alpaca_client import AlpacaClient
from app.core.crypto import encrypt_secret, decrypt_secret
from app.db.models.broker_connection import BrokerConnection, PAPER_BASE_URL

log = structlog.get_logger()

# user_id → (AlpacaClient, cached_at). Short TTL so disconnects propagate quickly.
_client_cache: dict[int, tuple[AlpacaClient, float]] = {}
_CACHE_TTL = 120.0


def invalidate_client_cache(user_id: int) -> None:
    _client_cache.pop(user_id, None)


async def verify_alpaca_keys(api_key: str, api_secret: str) -> dict:
    """
    Check the keys against the paper API. Returns the account dict on success,
    raises ValueError with a user-facing message on failure.
    """
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{PAPER_BASE_URL}/v2/account", headers=headers)
    except Exception as e:
        raise ValueError(f"Could not reach Alpaca: {e}")

    if r.status_code in (401, 403):
        raise ValueError(
            "Alpaca rejected these keys. Make sure they are PAPER trading keys "
            "(generated at app.alpaca.markets with 'Paper' selected)."
        )
    if r.status_code != 200:
        raise ValueError(f"Alpaca returned {r.status_code}: {r.text[:200]}")
    return r.json()


async def save_connection(db, user_id: int, api_key: str, api_secret: str) -> BrokerConnection:
    """Verify keys, then upsert the (encrypted) connection for this user."""
    from sqlalchemy import select

    account = await verify_alpaca_keys(api_key, api_secret)

    result = await db.execute(
        select(BrokerConnection).where(BrokerConnection.user_id == user_id)
    )
    conn = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if conn is None:
        conn = BrokerConnection(user_id=user_id)
        db.add(conn)
    conn.provider = "alpaca_paper"
    conn.api_key_enc = encrypt_secret(api_key)
    conn.api_secret_enc = encrypt_secret(api_secret)
    conn.base_url = PAPER_BASE_URL
    conn.account_number = account.get("account_number")
    conn.status = "connected"
    conn.last_verified_at = now
    await db.commit()
    invalidate_client_cache(user_id)
    log.info("broker.connected", user_id=user_id, account=conn.account_number)
    return conn


async def delete_connection(db, user_id: int) -> bool:
    from sqlalchemy import select

    result = await db.execute(
        select(BrokerConnection).where(BrokerConnection.user_id == user_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        return False
    await db.delete(conn)
    await db.commit()
    invalidate_client_cache(user_id)
    return True


async def get_connection(db, user_id: int) -> BrokerConnection | None:
    from sqlalchemy import select

    result = await db.execute(
        select(BrokerConnection).where(BrokerConnection.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_client_for_user(user_id: int | None) -> AlpacaClient | None:
    """
    Build (or reuse) an AlpacaClient from the user's stored credentials.
    Returns None when the user hasn't connected a broker or decryption fails.
    """
    if user_id is None:
        return None

    cached = _client_cache.get(user_id)
    if cached and (time.monotonic() - cached[1]) < _CACHE_TTL:
        return cached[0]

    from app.core.postgres import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        conn = await get_connection(db, user_id)

    if conn is None or conn.status != "connected":
        return None

    api_key = decrypt_secret(conn.api_key_enc)
    api_secret = decrypt_secret(conn.api_secret_enc)
    if not api_key or not api_secret:
        log.warning("broker.decrypt_failed", user_id=user_id,
                    hint="SECRET_KEY may have changed — user must reconnect")
        return None

    client = AlpacaClient(api_key, api_secret, PAPER_BASE_URL)
    _client_cache[user_id] = (client, time.monotonic())
    return client


async def legacy_env_client():
    """
    Env-key client for the legacy single-tenant path — but None when those keys
    already belong to a user's broker connection (post-adoption), so workers
    never process the same Alpaca account twice.
    """
    from app.broker.alpaca_client import default_client

    client = default_client()
    if not client.configured:
        return None
    for uid in await connected_user_ids():
        uc = await get_client_for_user(uid)
        if uc is not None and uc.api_key == client.api_key:
            return None
    return client


async def connected_user_ids() -> list[int]:
    """All users with an active broker connection — used by background workers."""
    from sqlalchemy import select
    from app.core.postgres import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(BrokerConnection.user_id).where(BrokerConnection.status == "connected")
            )
            return [row[0] for row in result.all()]
    except Exception as e:
        log.warning("broker.connected_users_failed", error=str(e))
        return []


# ── FastAPI dependencies ────────────────────────────────────────────────────

from app.core.auth import require_user  # noqa: E402


async def optional_broker(user=Depends(require_user)) -> AlpacaClient | None:
    """Per-user client, or None when no broker is connected (data endpoints return empties)."""
    return await get_client_for_user(user.id)


async def required_broker(user=Depends(require_user)) -> AlpacaClient:
    """Per-user client — 409 with a machine-readable code when not connected."""
    client = await get_client_for_user(user.id)
    if client is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "broker_not_connected",
                    "message": "Connect your Alpaca paper account in Settings first."},
        )
    return client
