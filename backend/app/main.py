from contextlib import asynccontextmanager
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.postgres import init_db
from app.core.redis_client import get_redis
from app.api.router import api_router

log = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", env=settings.environment)
    await init_db()
    yield
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


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.environment}
