from datetime import datetime, UTC
from sqlalchemy import String, DateTime, JSON, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.postgres import Base


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)  # NULL = legacy single-tenant rows
    agent_run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    alpaca_order_id: Mapped[str | None] = mapped_column(String(36), index=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    side: Mapped[str] = mapped_column(String(10))           # buy | sell
    qty: Mapped[float] = mapped_column(Float)
    order_type: Mapped[str] = mapped_column(String(20), default="market")
    limit_price: Mapped[float | None] = mapped_column(Float)
    filled_price: Mapped[float | None] = mapped_column(Float)
    filled_qty: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | submitted | partial | filled | cancelled | rejected
    pnl: Mapped[float | None] = mapped_column(Float)
    stop_loss_pct: Mapped[float | None] = mapped_column(Float)    # e.g. 7.0 means -7%
    take_profit_pct: Mapped[float | None] = mapped_column(Float)  # e.g. 15.0 means +15%
    closed_reason: Mapped[str | None] = mapped_column(String(20)) # stop_loss | take_profit | manual | expired
    reasoning_json: Mapped[dict | None] = mapped_column(JSON)  # full agent debate stored here
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
