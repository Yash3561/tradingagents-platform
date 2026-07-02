from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    echo=settings.environment == "development",
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# Columns added after the initial schema. create_all only creates missing tables,
# so existing deployments need these idempotent ALTERs on startup.
_SCHEMA_UPGRADES = [
    "ALTER TABLE trades ADD COLUMN IF NOT EXISTS user_id INTEGER",
    "CREATE INDEX IF NOT EXISTS ix_trades_user_id ON trades (user_id)",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS user_id INTEGER",
    "CREATE INDEX IF NOT EXISTS ix_agent_runs_user_id ON agent_runs (user_id)",
    "ALTER TABLE equity_snapshots ADD COLUMN IF NOT EXISTS user_id INTEGER",
    "CREATE INDEX IF NOT EXISTS ix_equity_snapshots_user_id ON equity_snapshots (user_id)",
    "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS user_id INTEGER",
    "CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications (user_id)",
    "ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS user_id INTEGER",
    "CREATE INDEX IF NOT EXISTS ix_activity_logs_user_id ON activity_logs (user_id)",
]


async def init_db():
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in _SCHEMA_UPGRADES:
            await conn.execute(text(stmt))


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
