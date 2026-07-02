from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, UTC

from app.core.postgres import get_db
from app.core.auth import require_user
from app.db.models.trade import Trade

router = APIRouter()


@router.post("/sync")
async def force_sync(user=Depends(require_user)):
    """Manually trigger a trade fill sync from Alpaca for this user."""
    from app.workers.trade_sync import sync_trades_once
    updated = await sync_trades_once(user_id=user.id)
    return {"updated": updated}


@router.get("/")
async def list_trades(limit: int = 50, offset: int = 0,
                      db: AsyncSession = Depends(get_db), user=Depends(require_user)):
    result = await db.execute(
        select(Trade).where(Trade.user_id == user.id)
        .order_by(desc(Trade.submitted_at)).limit(limit).offset(offset)
    )
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
async def get_trade(trade_id: str, db: AsyncSession = Depends(get_db), user=Depends(require_user)):
    trade = await db.get(Trade, trade_id)
    if not trade or trade.user_id != user.id:
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


@router.post("/{trade_id}/journal")
async def generate_trade_journal(trade_id: str, db: AsyncSession = Depends(get_db),
                                 user=Depends(require_user)):
    """
    Generate an AI-written journal entry for a specific trade.
    Pulls the trade's reasoning_json (full agent audit trail) and summarizes it
    into a human-readable journal entry.
    """
    import json
    import asyncio
    from openai import OpenAI
    from app.config import get_settings

    trade = await db.get(Trade, trade_id)
    if not trade or trade.user_id != user.id:
        raise HTTPException(404, "Trade not found")

    settings = get_settings()

    reasoning = trade.reasoning_json or {}
    decision = reasoning.get("final_decision", {})
    risk = reasoning.get("risk_assessment", {})
    debate = reasoning.get("researcher_debate", {})

    context = f"""
Trade: {trade.side.upper()} {trade.qty} shares of {trade.ticker}
Status: {trade.status}
P&L: ${trade.pnl:+.2f} if trade.pnl else "Open"
Stop loss: {trade.stop_loss_pct}% | Take profit: {trade.take_profit_pct}%

AI Decision: {decision.get('decision', 'N/A')} at {decision.get('confidence', 0):.0%} confidence
Risk level: {risk.get('risk_level', 'N/A')} | Approved: {risk.get('approved', False)}
Debate winner: {debate.get('debate_winner', 'N/A')}

Bull thesis: {debate.get('bull_thesis', 'N/A')}
Bear thesis: {debate.get('bear_thesis', 'N/A')}
Key risks: {', '.join(debate.get('key_risks', [])[:3])}
Key catalysts: {', '.join(debate.get('key_catalysts', [])[:3])}
"""

    def _call_ai():
        client = OpenAI(api_key=settings.nvidia_api_key, base_url=settings.nvidia_base_url)
        response = client.chat.completions.create(
            model="deepseek-ai/deepseek-v4-flash",
            max_tokens=512,
            temperature=0.4,
            messages=[
                {"role": "system", "content": "You are a trading journal writer. Write clear, concise trade journal entries that capture the thesis, reasoning, and outcome. 3-5 sentences max. First-person. Professional tone."},
                {"role": "user", "content": f"Write a trade journal entry for this trade:\n{context}"},
            ],
        )
        return response.choices[0].message.content or ""

    loop = asyncio.get_running_loop()
    try:
        journal_text = await loop.run_in_executor(None, _call_ai)
    except Exception as e:
        journal_text = f"Journal generation failed: {e}"

    return {
        "trade_id": trade_id,
        "ticker": trade.ticker,
        "journal": journal_text,
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.get("/export-csv")
async def export_trades_csv(db: AsyncSession = Depends(get_db), user=Depends(require_user)):
    """Download the user's trades as CSV for tax reporting."""
    from fastapi.responses import StreamingResponse
    from sqlalchemy import select, asc
    import csv
    import io

    result = await db.execute(
        select(Trade).where(Trade.user_id == user.id).order_by(asc(Trade.submitted_at))
    )
    trades = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Ticker", "Side", "Qty", "Order Type",
        "Entry Price", "Exit Price", "P&L ($)", "Stop Loss %",
        "Take Profit %", "Status", "Alpaca Order ID",
    ])
    for t in trades:
        writer.writerow([
            t.submitted_at.date().isoformat() if t.submitted_at else "",
            t.ticker, t.side, t.qty, t.order_type,
            t.filled_price or "", "",
            round(float(t.pnl), 2) if t.pnl else "",
            t.stop_loss_pct or "", t.take_profit_pct or "",
            t.status, t.alpaca_order_id or "",
        ])

    output.seek(0)
    filename = f"trades_{datetime.now(UTC).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
