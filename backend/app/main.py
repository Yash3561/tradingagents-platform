from contextlib import asynccontextmanager
import asyncio
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.postgres import init_db
# Import all models so SQLAlchemy registers them before create_all
import app.db.models.agent_run       # noqa: F401
import app.db.models.trade            # noqa: F401
import app.db.models.equity_snapshot  # noqa: F401
import app.db.models.notification     # noqa: F401
import app.db.models.activity_log     # noqa: F401
import app.db.models.settings         # noqa: F401
import app.db.models.user            # noqa: F401
import app.db.models.user_settings    # noqa: F401
import app.db.models.broker_connection  # noqa: F401
import app.db.models.invite_code      # noqa: F401
import app.db.models.analytics_event  # noqa: F401
from app.core.redis_client import get_redis
from app.api.router import api_router

log = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", env=settings.environment)
    if settings.environment == "production" and settings.secret_key == "change_this_in_production":
        raise RuntimeError(
            "SECRET_KEY is still the default — set a real one before running in production "
            "(it signs JWTs and encrypts stored broker keys)."
        )
    await init_db()

    # Seed default settings on first startup (no-op if already seeded)
    from app.db.models.settings import seed_defaults
    await seed_defaults()

    # One-time single-tenant → multi-tenant adoption (no-op once migrated)
    from app.core.legacy_adoption import adopt_legacy_data
    try:
        await adopt_legacy_data()
    except Exception as e:
        log.warning("legacy_adoption.failed", error=str(e))

    # Start background workers as asyncio tasks
    from app.workers.position_monitor import run_position_monitor
    from app.workers.scheduler import run_scheduler
    from app.workers.overnight_agent import run_overnight_agent
    from app.workers.circuit_breakers import check_circuit_breakers  # noqa: F401 — warm import
    from app.workers.price_feed import run_price_feed

    tasks = [
        asyncio.create_task(run_position_monitor()),
        asyncio.create_task(run_scheduler()),
        asyncio.create_task(run_overnight_agent()),
    ]
    workers = ["position_monitor", "scheduler", "overnight_agent"]

    if settings.price_feed_enabled:
        tasks.append(asyncio.create_task(run_price_feed()))
        workers.append("price_feed")

    # Single-container deploys (no separate worker service): the loops the
    # worker container would own run here instead. Never enable this while
    # the worker container is also running — loops must not run twice.
    if settings.run_all_workers:
        from app.workers.trade_sync import run_trade_sync
        from app.workers.equity_tracker import run_equity_tracker
        tasks.append(asyncio.create_task(run_trade_sync()))
        tasks.append(asyncio.create_task(run_equity_tracker()))
        workers += ["trade_sync", "equity_tracker"]

    log.info("background_workers.started", workers=workers)

    yield

    # Cancel background tasks on shutdown
    for t in tasks:
        t.cancel()
    log.info("shutdown")


app = FastAPI(
    title="TradingAgents Platform",
    version="1.0.0",
    description="Professional multi-agent trading platform powered by Claude",
    lifespan=lifespan,
)

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    # Vercel preview URLs
    "https://*.vercel.app",
    # Your production domain (set via env var)
    *([settings.frontend_url] if hasattr(settings, "frontend_url") and settings.frontend_url else []),
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

# System status router
from fastapi import Depends
from app.core.auth import require_user
from app.api.v1.system import router as system_router
app.include_router(system_router, prefix="/api/v1/system", tags=["system"],
                   dependencies=[Depends(require_user)])


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.environment}
