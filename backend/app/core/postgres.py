from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()


def normalize_database_url(url: str) -> str:
    """
    Accept connection strings as hosted Postgres providers hand them out
    (Neon, Heroku, etc.) and translate to what SQLAlchemy+asyncpg expects:
    scheme postgresql+asyncpg://, ssl= instead of libpq's sslmode=, and no
    channel_binding (asyncpg raises TypeError on unknown kwargs).
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]

    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "sslmode":
            query.append(("ssl", value))
        elif key == "channel_binding":
            continue
        else:
            query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


engine = create_async_engine(
    normalize_database_url(settings.database_url),
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
    # Real-user readiness (2026-07-03)
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ",
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
