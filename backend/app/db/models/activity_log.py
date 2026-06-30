from datetime import datetime, UTC
from sqlalchemy import String, DateTime, JSON, Float, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.postgres import Base


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    feature: Mapped[str] = mapped_column(String(40), index=True)
    # "scanner" | "agent_hub" | "backtest" | "manual_trade"
    action: Mapped[str] = mapped_column(String(60))
    # "scan_started" | "scan_completed" | "agent_run_completed" | "backtest_run" | "trade_placed"
    ticker: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    details: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # "BUY" | "SELL" | "HOLD" | "completed" | "failed"
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
