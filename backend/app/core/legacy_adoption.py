"""
One-time legacy adoption for single-tenant → multi-tenant upgrades.

Before multi-tenancy, Alpaca keys lived in env vars and all data rows had no
owner (user_id NULL). If this deployment has exactly ONE user, that person is
the original operator — adopt everything into their account:

  1. Create a broker_connection for them from the env ALPACA keys (encrypted).
  2. Assign all user_id-NULL trades, agent_runs, equity_snapshots,
     notifications, and activity_logs to them.

Runs at startup; a no-op once a broker connection exists or if there are
multiple users (ambiguous — operator must resolve manually).
"""
import structlog
from sqlalchemy import select, func, text

log = structlog.get_logger()

_ADOPT_TABLES = ["trades", "agent_runs", "equity_snapshots", "notifications", "activity_logs"]


async def adopt_legacy_data() -> None:
    from app.config import get_settings
    from app.core.postgres import AsyncSessionLocal
    from app.core.crypto import encrypt_secret
    from app.db.models.user import User
    from app.db.models.broker_connection import BrokerConnection, PAPER_BASE_URL

    settings = get_settings()

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(func.count()).select_from(BrokerConnection))
        if existing.scalar_one() > 0:
            return  # already migrated (or users have connected themselves)

        result = await db.execute(select(User))
        users = result.scalars().all()
        if len(users) != 1:
            if users:
                log.info("legacy_adoption.skipped", reason="multiple users — ambiguous owner")
            return
        owner = users[0]

        # 1. Adopt the env-configured Alpaca keys as the owner's broker connection
        if settings.alpaca_api_key and settings.alpaca_api_secret:
            from datetime import datetime, UTC
            db.add(BrokerConnection(
                user_id=owner.id,
                provider="alpaca_paper",
                api_key_enc=encrypt_secret(settings.alpaca_api_key),
                api_secret_enc=encrypt_secret(settings.alpaca_api_secret),
                base_url=PAPER_BASE_URL,
                status="connected",
                last_verified_at=datetime.now(UTC),
            ))
            log.info("legacy_adoption.broker_connected", user_id=owner.id, email=owner.email)

        # 2. Assign all ownerless rows to the owner
        for table in _ADOPT_TABLES:
            r = await db.execute(
                text(f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL"),
                {"uid": owner.id},
            )
            if r.rowcount:
                log.info("legacy_adoption.rows_adopted", table=table, rows=r.rowcount)

        await db.commit()
        log.info("legacy_adoption.done", user_id=owner.id, email=owner.email)
