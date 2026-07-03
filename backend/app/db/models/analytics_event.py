from datetime import datetime, UTC
from sqlalchemy import String, DateTime, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.postgres import Base


class AnalyticsEvent(Base):
    """Product analytics — one row per tracked event (signup, agent_run, ...)."""
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=True, index=True)
    properties: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
