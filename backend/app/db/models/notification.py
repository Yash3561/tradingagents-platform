from datetime import datetime, UTC
from sqlalchemy import String, DateTime, Float, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.postgres import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    type: Mapped[str] = mapped_column(String(40))
    # "trade_placed" | "position_closed" | "scan_complete" | "stop_loss_hit"
    # "take_profit_hit" | "scheduled_scan"
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
