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
from app.core.redis_client import get_redis
from app.api.router import api_router

log = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", env=settings.environment)
    await init_db()

    # Seed default settings on first startup (no-op if already seeded)
    from app.db.models.settings import seed_defaults
    await seed_defaults()

    # Start background workers as asyncio tasks
    from app.workers.position_monitor import run_position_monitor
    from app.workers.scheduler import run_scheduler
    from app.workers.overnight_agent import run_overnight_agent
    from app.workers.circuit_breakers import check_circuit_breakers  # noqa: F401 — warm import
    from app.workers.price_feed import run_price_feed

    monitor_task = asyncio.create_task(run_position_monitor())
    scheduler_task = asyncio.create_task(run_scheduler())
    overnight_task = asyncio.create_task(run_overnight_agent())
    price_feed_task = asyncio.create_task(run_price_feed())
    log.info("background_workers.started",
             workers=["position_monitor", "scheduler", "overnight_agent", "price_feed"])

    yield

    # Cancel background tasks on shutdown
    monitor_task.cancel()
    scheduler_task.cancel()
    overnight_task.cancel()
    price_feed_task.cancel()
    log.info("shutdown")


app = FastAPI(
    title="TradingAgents Platform",
    version="1.0.0",
    description="Professional multi-agent trading platform powered by Claude",
    lifespan=lifespan,
)

ALLOWED_ORIGINS = [
    "http://localhost:5173",
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
from app.api.v1.system import router as system_router
app.include_router(system_router, prefix="/api/v1/system", tags=["system"])


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.environment}
