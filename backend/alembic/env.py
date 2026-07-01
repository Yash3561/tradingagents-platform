import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# ── Alembic config object ──────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import all models so autogenerate can detect them ─────────────────────────
from app.core.postgres import Base  # noqa: F401
import app.db.models.user            # noqa: F401
import app.db.models.agent_run       # noqa: F401
import app.db.models.trade           # noqa: F401
import app.db.models.settings        # noqa: F401
import app.db.models.activity_log    # noqa: F401
import app.db.models.equity_snapshot # noqa: F401
import app.db.models.notification    # noqa: F401

target_metadata = Base.metadata

# ── DB URL from environment (sync driver for Alembic) ─────────────────────────
def get_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    # asyncpg → psycopg2 for Alembic (sync migrations only)
    return url.replace("postgresql+asyncpg://", "postgresql://")

# ── Offline mode ───────────────────────────────────────────────────────────────
def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()

# ── Online mode ────────────────────────────────────────────────────────────────
def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
