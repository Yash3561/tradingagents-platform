import json
from datetime import datetime, UTC
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.postgres import Base


class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)          # JSON-encoded value
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


# Default settings seeded on first startup
DEFAULTS: dict = {
    "position_size_pct": 5.0,
    "position_size_high_conf": 7.0,
    "stop_loss_pct": 7.0,
    "take_profit_pct": 15.0,
    "max_position_pct": 20.0,
    "daily_loss_limit_pct": 3.0,
    "vix_warning_threshold": 30.0,
    "vix_block_threshold": 40.0,
    "scan_max_candidates": 8,
    "debate_rounds": 2,
    "llm_model": "deepseek-ai/deepseek-v4-flash",
    "scan_enabled": True,
    "intraday_monitor_enabled": True,
    "overnight_agent_enabled": True,
    "long_only": True,
    "min_confidence_to_trade": 0.48,
    "earnings_blackout_days": 5,
    # "agents" = LLM pipeline, "quant" = deterministic baseline (no LLM cost)
    "strategy_mode": "agents",
}

# The only model ids users may select — anything else is rejected. The platform
# pays for inference, so arbitrary model strings must never reach the LLM client.
ALLOWED_LLM_MODELS = {
    "deepseek-ai/deepseek-v4-flash",
    "deepseek-ai/deepseek-v4-pro",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
}


async def get_setting(key: str, default=None):
    """Read a single setting from DB. Returns Python-typed value or default."""
    from app.core.postgres import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as db:
            row = await db.get(PlatformSettings, key)
            if row is None:
                return default
            return json.loads(row.value)
    except Exception:
        return default


async def seed_defaults() -> None:
    """Insert defaults only for keys that don't already exist."""
    import structlog
    log = structlog.get_logger()
    from app.core.postgres import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        inserted = 0
        for key, val in DEFAULTS.items():
            existing = await db.get(PlatformSettings, key)
            if existing is None:
                db.add(PlatformSettings(key=key, value=json.dumps(val)))
                inserted += 1
        if inserted:
            await db.commit()
            log.info("settings.defaults_seeded", count=inserted)
