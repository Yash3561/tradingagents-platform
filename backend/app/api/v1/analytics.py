"""
AI Performance Analyzer — generates weekly/on-demand portfolio performance summaries
using DeepSeek via NVIDIA NIM. Analyzes closed trades, win rate, best/worst performers,
and gives actionable recommendations.
"""
from fastapi import APIRouter
from datetime import datetime, UTC, timedelta
import structlog

router = APIRouter()
log = structlog.get_logger()


def _build_perf_summary(trades: list, positions: list, metrics: dict) -> str:
    """Format trade data into a structured prompt for the AI."""
    closed = [t for t in trades if t.get("pnl") is not None]
    winners = [t for t in closed if (t.get("pnl") or 0) > 0]
    losers = [t for t in closed if (t.get("pnl") or 0) <= 0]
    total_pnl = sum(t.get("pnl", 0) or 0 for t in closed)
    win_rate = len(winners) / len(closed) if closed else 0

    # Best and worst trades
    sorted_by_pnl = sorted(closed, key=lambda t: t.get("pnl", 0) or 0, reverse=True)
    best = sorted_by_pnl[:3]
    worst = sorted_by_pnl[-3:]

    lines = [
        f"Period: last 30 days",
        f"Total closed trades: {len(closed)}",
        f"Winners: {len(winners)}, Losers: {len(losers)}",
        f"Win rate: {win_rate:.1%}",
        f"Total realized P&L: ${total_pnl:+.2f}",
        f"",
        f"Best trades:",
    ]
    for t in best:
        if t.get("pnl"):
            lines.append(f"  {t.get('ticker','?')} {t.get('side','?')} ${t.get('pnl',0):+.2f} ({t.get('pnl_pct',0):+.1f}%)")
    lines.append("Worst trades:")
    for t in worst:
        if t.get("pnl"):
            lines.append(f"  {t.get('ticker','?')} {t.get('side','?')} ${t.get('pnl',0):+.2f} ({t.get('pnl_pct',0):+.1f}%)")

    lines.append("")
    lines.append(f"Current open positions: {len(positions)}")
    for p in positions[:10]:
        lines.append(f"  {p.get('ticker','?')}: {p.get('qty',0)} shares, unrealized P&L: ${p.get('unrealized_pnl',0):+.2f} ({p.get('unrealized_pnl_pct',0):+.1f}%)")

    if metrics:
        lines.append(f"")
        lines.append(f"Account equity: ${metrics.get('equity', 0):,.2f}")
        lines.append(f"Day P&L: ${metrics.get('day_pnl', 0):+.2f} ({metrics.get('day_pnl_pct', 0):+.2f}%)")

    return "\n".join(lines)


@router.get("/performance-summary")
async def get_performance_summary():
    """
    Generate an AI-written performance summary for the last 30 days.
    Uses real trade data from DB + Alpaca positions.
    Returns structured analysis with insights and recommendations.
    """
    import asyncio
    import json
    from openai import OpenAI
    from app.config import get_settings
    from app.core.postgres import AsyncSessionLocal
    from app.db.models.trade import Trade
    from sqlalchemy import select, desc
    import httpx

    settings = get_settings()

    # Fetch trades from DB
    async with AsyncSessionLocal() as db:
        cutoff = datetime.now(UTC) - timedelta(days=30)
        result = await db.execute(
            select(Trade)
            .where(Trade.submitted_at >= cutoff)
            .order_by(desc(Trade.submitted_at))
            .limit(50)
        )
        trades = result.scalars().all()

    trade_dicts = [
        {
            "ticker": t.ticker,
            "side": t.side,
            "qty": float(t.qty or 0),
            "pnl": float(t.pnl) if t.pnl else None,
            "pnl_pct": round(float(t.pnl) / max(float(t.qty or 1) * float(t.filled_price or 1), 1) * 100, 2) if t.pnl and t.filled_price else None,
            "status": t.status,
            "submitted_at": t.submitted_at.isoformat() if t.submitted_at else None,
        }
        for t in trades
    ]

    # Fetch Alpaca positions + account
    positions = []
    metrics = {}
    try:
        headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            pos_r = await client.get(f"{settings.alpaca_base_url}/v2/positions", headers=headers)
            acct_r = await client.get(f"{settings.alpaca_base_url}/v2/account", headers=headers)
        if pos_r.status_code == 200:
            positions = pos_r.json()
        if acct_r.status_code == 200:
            acct = acct_r.json()
            equity = float(acct.get("equity", 0))
            last_equity = float(acct.get("last_equity", equity))
            metrics = {
                "equity": equity,
                "day_pnl": equity - last_equity,
                "day_pnl_pct": (equity - last_equity) / last_equity * 100 if last_equity else 0,
            }
    except Exception as e:
        log.warning("analytics.alpaca_fetch_failed", error=str(e))

    perf_summary = _build_perf_summary(trade_dicts, positions, metrics)

    # Call DeepSeek via NIM
    def _call_ai():
        client = OpenAI(
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
        )
        response = client.chat.completions.create(
            model="deepseek-ai/deepseek-v4-flash",
            max_tokens=1024,
            temperature=0.3,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a quantitative trading coach reviewing a trader's recent performance. "
                        "Be direct and specific. Don't sugarcoat losses. "
                        "Identify patterns — is the trader chasing momentum? Cutting winners too early? "
                        "Give exactly 3 actionable improvement recommendations."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Here is my trading performance for the last 30 days:\n\n{perf_summary}\n\n"
                        "Provide: 1) A 2-3 sentence overall assessment, "
                        "2) What's working well, "
                        "3) What needs improvement, "
                        "4) Exactly 3 specific actionable recommendations for next week. "
                        "Be concise and data-driven."
                    ),
                },
            ],
            tools=[{
                "type": "function",
                "function": {
                    "name": "submit_analysis",
                    "description": "Submit the performance analysis",
                    "parameters": {
                        "type": "object",
                        "required": ["overall_assessment", "whats_working", "needs_improvement", "recommendations", "performance_grade"],
                        "properties": {
                            "overall_assessment": {"type": "string", "description": "2-3 sentence overall assessment"},
                            "whats_working": {"type": "array", "items": {"type": "string"}, "description": "2-3 things going well"},
                            "needs_improvement": {"type": "array", "items": {"type": "string"}, "description": "2-3 areas needing work"},
                            "recommendations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "action": {"type": "string"},
                                        "reason": {"type": "string"},
                                    },
                                    "required": ["action", "reason"],
                                },
                                "description": "Exactly 3 specific next-week recommendations",
                            },
                            "performance_grade": {
                                "type": "string",
                                "enum": ["A", "B", "C", "D", "F"],
                                "description": "Overall grade for the period",
                            },
                        },
                    },
                },
            }],
            tool_choice={"type": "function", "function": {"name": "submit_analysis"}},
        )
        msg = response.choices[0].message
        if msg.tool_calls:
            return json.loads(msg.tool_calls[0].function.arguments)
        raise RuntimeError("AI did not return structured response")

    loop = asyncio.get_running_loop()
    try:
        analysis = await loop.run_in_executor(None, _call_ai)
    except Exception as e:
        log.error("analytics.ai_failed", error=str(e))
        # Return raw data without AI analysis if NIM fails
        analysis = {
            "overall_assessment": "AI analysis unavailable — raw data shown below.",
            "whats_working": [],
            "needs_improvement": [],
            "recommendations": [],
            "performance_grade": "?",
        }

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "period_days": 30,
        "raw_stats": {
            "total_trades": len(trade_dicts),
            "closed_trades": len([t for t in trade_dicts if t["pnl"] is not None]),
            "win_rate": len([t for t in trade_dicts if (t.get("pnl") or 0) > 0]) / max(len([t for t in trade_dicts if t["pnl"] is not None]), 1),
            "total_pnl": sum(t.get("pnl", 0) or 0 for t in trade_dicts),
            "open_positions": len(positions),
            **metrics,
        },
        "analysis": analysis,
        "data_summary": perf_summary,
    }


@router.get("/watchlist-scores")
async def get_watchlist_scores():
    """
    Return current technical scores for all watchlist tickers.
    Uses the same scoring logic as the scanner pre-screen.
    Fast — no AI calls. Sorted by score descending.
    """
    import asyncio
    from app.workers.scanner import WATCHLIST, _screen_ticker

    def _run_all():
        results = []
        for ticker in WATCHLIST:
            try:
                r = _screen_ticker(ticker)
                if r:
                    results.append(r)
            except Exception:
                pass
        return sorted(results, key=lambda x: x["score"], reverse=True)

    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(None, _run_all)
    return {"scored_at": datetime.now(UTC).isoformat(), "tickers": results}
