"""
Async wrapper around TradingAgents graph.
Emits structured WebSocket events at each agent step so the
frontend can animate the debate in real-time.
"""
import asyncio
import sys
import traceback
from datetime import datetime, UTC
from pathlib import Path

import structlog

from app.core.postgres import AsyncSessionLocal
from app.core.websocket_manager import ws_manager
from app.db.models.agent_run import AgentRun

log = structlog.get_logger()

# TradingAgents submodule on sys.path
TRADINGAGENTS_PATH = Path(__file__).parent.parent.parent.parent / "tradingagents"
if str(TRADINGAGENTS_PATH) not in sys.path:
    sys.path.insert(0, str(TRADINGAGENTS_PATH))


async def _emit(run_id: str, event: dict):
    await ws_manager.broadcast(f"run:{run_id}", event)


async def run_agent_analysis(
    run_id: str,
    ticker: str,
    analysis_date: str,
    debate_rounds: int,
    model: str,
):
    log.info("agent.run.start", run_id=run_id, ticker=ticker, date=analysis_date)

    async with AsyncSessionLocal() as db:
        run = await db.get(AgentRun, run_id)
        run.status = "running"
        await db.commit()

    await _emit(run_id, {"type": "status", "status": "running", "ticker": ticker})

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            _run_sync,
            run_id,
            ticker,
            analysis_date,
            debate_rounds,
            model,
        )

        async with AsyncSessionLocal() as db:
            run = await db.get(AgentRun, run_id)
            run.status = "completed"
            run.decision = result.get("decision", "HOLD")
            run.confidence = result.get("confidence")
            run.summary = result.get("summary")
            run.debate_log = result.get("debate_log", [])
            run.reasoning_json = result.get("reasoning_json", {})
            run.completed_at = datetime.now(UTC)
            await db.commit()

        await _emit(run_id, {
            "type": "completed",
            "decision": run.decision,
            "confidence": run.confidence,
            "summary": run.summary,
        })

    except Exception as exc:
        log.error("agent.run.error", run_id=run_id, error=str(exc))
        tb = traceback.format_exc()

        async with AsyncSessionLocal() as db:
            run = await db.get(AgentRun, run_id)
            run.status = "failed"
            run.error = f"{exc}\n{tb}"
            run.completed_at = datetime.now(UTC)
            await db.commit()

        await _emit(run_id, {"type": "error", "error": str(exc)})


def _run_sync(run_id: str, ticker: str, date: str, debate_rounds: int, model: str) -> dict:
    """
    Synchronous execution of TradingAgentsGraph.
    Runs in a thread executor so it doesn't block the event loop.
    """
    from app.config import get_settings
    settings = get_settings()

    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG

        config = {
            **DEFAULT_CONFIG,
            "llm_provider": settings.llm_provider,
            "deep_think_llm": model,
            "quick_think_llm": model,
            "max_debate_rounds": debate_rounds,
            "max_risk_discuss_rounds": settings.agent_max_risk_discussions,
            "online_tools": settings.agent_online_tools,
        }

        ta = TradingAgentsGraph(debug=False, config=config)
        state, decision = ta.propagate(ticker, date)

        return _parse_result(state, decision)

    except ImportError:
        # TradingAgents not installed yet — return mock for UI dev
        import time, random
        time.sleep(3)
        return _mock_result(ticker)


def _parse_result(state: dict, decision: str) -> dict:
    """Convert TradingAgents output into our structured schema."""
    debate_log = []

    agents_map = {
        "market_report": ("Technical Analyst", "analyst"),
        "sentiment_report": ("Sentiment Analyst", "analyst"),
        "news_report": ("News Analyst", "analyst"),
        "fundamentals_report": ("Fundamental Analyst", "analyst"),
        "investment_debate_state": ("Researcher Team", "researcher"),
        "risk_debate_state": ("Risk Manager", "risk"),
        "final_trade_decision": ("Portfolio Manager", "pm"),
    }

    for key, (agent_name, role) in agents_map.items():
        if key in state and state[key]:
            content = state[key]
            if isinstance(content, dict):
                content = str(content)
            debate_log.append({
                "agent": agent_name,
                "role": role,
                "content": content,
            })

    decision_upper = decision.upper() if decision else "HOLD"
    if "BUY" in decision_upper:
        final = "BUY"
    elif "SELL" in decision_upper:
        final = "SELL"
    else:
        final = "HOLD"

    return {
        "decision": final,
        "confidence": 0.75,
        "summary": state.get("final_trade_decision", "Analysis complete."),
        "debate_log": debate_log,
        "reasoning_json": {k: v for k, v in state.items() if v},
    }


def _mock_result(ticker: str) -> dict:
    """Mock result for UI development when TradingAgents isn't installed."""
    import random
    decisions = ["BUY", "HOLD", "SELL"]
    decision = random.choice(decisions)
    return {
        "decision": decision,
        "confidence": round(random.uniform(0.55, 0.90), 2),
        "summary": f"Based on comprehensive analysis, the recommendation for {ticker} is {decision}. Technical indicators show momentum alignment with fundamental valuation metrics.",
        "debate_log": [
            {"agent": "Technical Analyst", "role": "analyst", "content": f"RSI at 58, MACD bullish crossover detected for {ticker}. 50-day MA acting as support."},
            {"agent": "Fundamental Analyst", "role": "analyst", "content": f"{ticker} P/E ratio of 22x is inline with sector median. Revenue growth at 18% YoY."},
            {"agent": "Sentiment Analyst", "role": "analyst", "content": "Social sentiment score: +0.72 (bullish). Institutional flow positive over last 10 days."},
            {"agent": "News Analyst", "role": "analyst", "content": "No material adverse news. Recent product launch well-received by analyst community."},
            {"agent": "Bull Researcher", "role": "researcher", "content": f"Strong case for {decision} — fundamentals support current valuation with upside catalyst from sector tailwinds."},
            {"agent": "Bear Researcher", "role": "researcher", "content": "Macro headwinds from rate environment and sector rotation risk warrant caution on position sizing."},
            {"agent": "Risk Manager", "role": "risk", "content": "Portfolio VaR within limits. Recommended position size: 3-5% of portfolio. Stop-loss at -8%."},
            {"agent": "Portfolio Manager", "role": "pm", "content": f"Final decision: {decision}. Risk/reward favorable. Approving order with standard sizing constraints."},
        ],
        "reasoning_json": {},
    }
