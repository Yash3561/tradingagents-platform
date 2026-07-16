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
    # "agents" = LLM pipeline, "quant" = deterministic baseline (no LLM cost),
    # "intraday" = 5-minute rule engine, flat by the close (no LLM cost)
    "strategy_mode": "agents",
    # Intraday policy profile — deploy walk-forward tournament winners here
    # (defaults mirror INTRADAY_PARAM_DEFAULTS in workers/intraday_engine.py)
    "intraday_setup": "mom",
    "intraday_or_minutes": 30,
    "intraday_vol_ratio_min": 1.0,
    "intraday_above_vwap": True,
    "intraday_dev_entry_atr": 1.5,
    "intraday_rsi_max": 100.0,
    "intraday_stop_atr_mult": 1.5,
    "intraday_rr": 2.0,
    "intraday_max_hold_bars": 0,
    "intraday_risk_pct": 0.5,
    "intraday_max_trades_day": 6,
    "intraday_max_concurrent": 3,
    "intraday_daily_loss_halt_pct": 0.5,
    # Earnings PEAD policy profile — deploy walk-forward tournament winners here
    # (defaults mirror EARNINGS_PARAM_DEFAULTS in agents/earnings_pead.py; validated
    # against docs/research/earnings-drift-walkforward-2026-07-16.md)
    "earnings_surprise_min_pct": 10.0,
    "earnings_require_gap_up": True,
    "earnings_stop_atr_mult": 3.5,
    "earnings_rr_ratio": 3.0,
    "earnings_hold_days": 10,
    "earnings_position_size_pct": 5.0,
    # Quant policy profile — deploy walk-forward tournament winners here
    # (defaults mirror QUANT_PARAM_DEFAULTS in agents/quant_baseline.py)
    "quant_trend_rsi_min": 45.0,
    "quant_trend_rsi_max": 70.0,
    "quant_require_macd": True,
    "quant_meanrev_rsi_max": 32.0,
    "quant_exit_rsi": 78.0,
    "quant_stop_atr_mult": 2.0,
    "quant_rr_ratio": 2.0,
    "quant_regime_gate": True,
}

# The only model ids users may select — anything else is rejected. The platform
# pays for inference, so arbitrary model strings must never reach the LLM client.
# NIM-served models only: the runner has no Anthropic routing, so claude ids
# would 404 at the NVIDIA endpoint — re-add them only when routing exists.
ALLOWED_LLM_MODELS = {
    "deepseek-ai/deepseek-v4-flash",
    "deepseek-ai/deepseek-v4-pro",
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
