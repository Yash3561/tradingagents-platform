from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    environment: str = "development"
    secret_key: str = "change_this_in_production"
    log_level: str = "INFO"
    # When set, new signups must supply this code (gate a public deployment)
    signup_invite_code: str = ""

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
