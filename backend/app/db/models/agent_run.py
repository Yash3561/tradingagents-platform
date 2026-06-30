from datetime import datetime, UTC
from sqlalchemy import String, DateTime, JSON, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.postgres import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    analysis_date: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | running | completed | failed | cancelled
    decision: Mapped[str | None] = mapped_column(String(10))  # BUY | SELL | HOLD
    confidence: Mapped[float | None] = mapped_column()
    summary: Mapped[str | None] = mapped_column(Text)
    debate_log: Mapped[list | None] = mapped_column(JSON)       # full structured debate
    reasoning_json: Mapped[dict | None] = mapped_column(JSON)   # per-agent reports
    llm_model: Mapped[str] = mapped_column(String(60), default="claude-sonnet-4-6")
    debate_rounds: Mapped[int] = mapped_column(Integer, default=2)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
