from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.postgres import get_db
from app.db.models.trade import Trade

router = APIRouter()


@router.post("/sync")
async def force_sync():
    """Manually trigger a trade fill sync from Alpaca."""
    from app.workers.trade_sync import sync_trades_once
    updated = await sync_trades_once()
    return {"updated": updated}


@router.get("/")
async def list_trades(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Trade).order_by(desc(Trade.submitted_at)).limit(limit).offset(offset))
    trades = result.scalars().all()
    return [
        {
            "id": t.id,
            "agent_run_id": t.agent_run_id,
            "ticker": t.ticker,
            "side": t.side,
            "qty": t.qty,
            "filled_price": t.filled_price,
            "status": t.status,
            "pnl": t.pnl,
            "stop_loss_pct": t.stop_loss_pct,
            "take_profit_pct": t.take_profit_pct,
            "closed_reason": t.closed_reason,
            "submitted_at": t.submitted_at.isoformat() if t.submitted_at else None,
            "filled_at": t.filled_at.isoformat() if t.filled_at else None,
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        }
        for t in trades
    ]


@router.get("/{trade_id}")
async def get_trade(trade_id: str, db: AsyncSession = Depends(get_db)):
    trade = await db.get(Trade, trade_id)
    if not trade:
        from fastapi import HTTPException
        raise HTTPException(404, "Trade not found")
    return {
        "id": trade.id,
        "ticker": trade.ticker,
        "side": trade.side,
        "qty": trade.qty,
        "filled_price": trade.filled_price,
        "status": trade.status,
        "pnl": trade.pnl,
        "reasoning_json": trade.reasoning_json,
        "submitted_at": trade.submitted_at.isoformat() if trade.submitted_at else None,
        "filled_at": trade.filled_at.isoformat() if trade.filled_at else None,
    }
