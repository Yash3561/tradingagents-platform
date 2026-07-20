from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    environment: str = "development"
    secret_key: str = "change_this_in_production"
    log_level: str = "INFO"
    # When set, new signups must supply this code (gate a public deployment).
    # DB-backed invite codes (admin-issued) are accepted as an alternative.
    signup_invite_code: str = ""
    # User with this email is auto-promoted to admin on signup/login
    admin_email: str = ""

    # Error alerting — Sentry backend DSN; empty = disabled
    sentry_dsn: str = ""

    # Read-only automated-monitoring endpoints (api/v1/monitor.py) — a static
    # key, not a user login, for unattended cloud-agent health checks.
    # Empty = the whole /monitor surface 403s (fail closed, never accidentally open).
    monitoring_api_key: str = ""

    # Email. Render blocks outbound SMTP ports — set BREVO_API_KEY there
    # (HTTPS API, smtp_from must be a Brevo-verified sender). SMTP_* works
    # locally / on SMTP-friendly hosts. Neither set = links logged only.
    brevo_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://tap:tap_secret@localhost:5432/trading"
    timescale_url: str = "postgresql+asyncpg://tap:tap_secret@localhost:5433/market_data"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:29092"

    # Alpaca
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_url: str = "https://data.alpaca.markets"

    # LLM
    anthropic_api_key: str = ""
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_provider: str = "nvidia"
    llm_model: str = "deepseek-ai/deepseek-v4-flash"

    # Agent
    agent_debate_rounds: int = 2
    agent_max_risk_discussions: int = 2
    agent_online_tools: bool = True

    # CORS
    frontend_url: str = ""    # e.g. https://your-app.vercel.app
    # Allow any *.vercel.app origin in production (preview deploys).
    # Off by default — the wildcard admits every Vercel-hosted site.
    cors_allow_vercel_previews: bool = False

    # Deployment shape
    # True = run trade_sync + equity_tracker inside the API process too
    # (single-container free-tier deploys with no separate worker service)
    run_all_workers: bool = False
    # False = skip the Alpaca tick stream (protects Upstash free-tier Redis
    # quota — one SET per tick adds up fast; frontend price polling still works)
    price_feed_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
