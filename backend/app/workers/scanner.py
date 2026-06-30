"""
Market Scanner — the aggressive opportunity hunter.

Flow:
1. Fetch real price/technical data for 40+ stocks (yfinance, free, fast)
2. Score each stock with a momentum + technical pre-screen
3. Top scorers get full 7-agent AI pipeline
4. Approved trades execute automatically on Alpaca paper

Cost: only top N stocks hit Claude API. Pre-screen is free.
"""

from __future__ import annotations
import asyncio
from datetime import datetime, UTC
from typing import Any
import structlog

log = structlog.get_logger()

# ── Watchlist — 40 high-liquidity stocks across sectors ──────────────────────
WATCHLIST = [
    # Mega-cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA", "AMD",
    # Tech / growth
    "CRM", "ORCL", "NFLX", "ADBE", "SNOW", "PLTR", "UBER", "MELI",
    # Finance
    "JPM", "GS", "V", "MA", "BAC", "COIN",
    # Healthcare / biotech
    "UNH", "LLY", "ABBV", "MRNA",
    # Energy
    "XOM", "CVX",
    # Consumer
    "WMT", "COST", "HD", "MCD", "NKE",
    # Semis
    "QCOM", "MU", "AVGO", "TSM", "ASML",
    # ETFs for broad signals
    "SPY", "QQQ", "IWM",
]

# Max stocks to send through full AI pipeline per scan (cost control)
MAX_AI_CANDIDATES = 8


def _screen_ticker(ticker: str) -> dict | None:
    """
    Pre-screen a ticker using yfinance. No Claude calls — just math.
    Returns a scored dict or None if data unavailable.
    """
    try:
        import yfinance as yf
        import numpy as np

        t = yf.Ticker(ticker)
        hist = t.history(period="6mo", interval="1d")
        if len(hist) < 30:
            return None

        close = hist["Close"]
        volume = hist["Volume"]

        current = float(close.iloc[-1])
        prev = float(close.iloc[-2])

        # Moving averages
        ma20 = float(close.tail(20).mean())
        ma50 = float(close.tail(50).mean())
        ma200 = float(close.tail(200).mean()) if len(close) >= 200 else float(close.mean())

        # RSI-14
        delta = close.diff()
        gain = delta.clip(lower=0).tail(14).mean()
        loss = (-delta.clip(upper=0)).tail(14).mean()
        rsi = float(100 - (100 / (1 + gain / loss))) if loss != 0 else 50.0

        # Momentum
        mom_1w = (current / float(close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
        mom_1m = (current / float(close.iloc[-22]) - 1) * 100 if len(close) >= 22 else 0
        mom_3m = (current / float(close.iloc[-66]) - 1) * 100 if len(close) >= 66 else 0

        # Volume ratio
        avg_vol = float(volume.tail(30).mean())
        today_vol = float(volume.iloc[-1])
        vol_ratio = today_vol / avg_vol if avg_vol else 1.0

        # MACD
        ema12 = float(close.ewm(span=12, adjust=False).mean().iloc[-1])
        ema26 = float(close.ewm(span=26, adjust=False).mean().iloc[-1])
        macd = ema12 - ema26
        signal = float(close.ewm(span=9, adjust=False).mean().iloc[-1])
        macd_bullish = macd > signal

        # ── Scoring (0-100) ──────────────────────────────────────────────────
        score = 50.0
        direction = "NEUTRAL"

        # RSI signals (weight: 25)
        if rsi < 35:
            score += 20   # Oversold — bounce candidate
            direction = "BUY"
        elif rsi < 45:
            score += 10
            direction = "BUY"
        elif rsi > 70:
            score -= 15   # Overbought
            direction = "SELL"
        elif rsi > 60:
            score -= 5

        # Trend (weight: 20)
        if current > ma50 > ma200:
            score += 15   # Strong uptrend
        elif current > ma200:
            score += 8
        elif current < ma50 < ma200:
            score -= 15   # Strong downtrend
        elif current < ma200:
            score -= 8

        # Momentum (weight: 25)
        if mom_1w > 3:
            score += 10
        elif mom_1w > 1:
            score += 5
        elif mom_1w < -3:
            score -= 10
        elif mom_1w < -1:
            score -= 5

        if mom_1m > 8:
            score += 10
        elif mom_1m > 3:
            score += 5
        elif mom_1m < -8:
            score -= 10

        # MACD (weight: 10)
        if macd_bullish:
            score += 8
        else:
            score -= 5

        # Volume confirmation (weight: 10)
        if vol_ratio > 1.5:
            score += 8   # Strong volume confirmation
        elif vol_ratio > 1.2:
            score += 4
        elif vol_ratio < 0.6:
            score -= 5   # Low conviction

        # Price momentum direction
        if score > 60:
            direction = "BUY"
        elif score < 40:
            direction = "SELL"
        else:
            direction = "NEUTRAL"

        return {
            "ticker": ticker,
            "score": round(score, 1),
            "direction": direction,
            "current_price": round(current, 2),
            "rsi": round(rsi, 1),
            "ma50": round(ma50, 2),
            "ma200": round(ma200, 2),
            "above_ma50": current > ma50,
            "above_ma200": current > ma200,
            "macd_bullish": macd_bullish,
            "mom_1w_pct": round(mom_1w, 2),
            "mom_1m_pct": round(mom_1m, 2),
            "mom_3m_pct": round(mom_3m, 2),
            "vol_ratio": round(vol_ratio, 2),
        }
    except Exception as e:
        log.warning("scanner.screen_failed", ticker=ticker, error=str(e))
        return None


def _run_pre_screen(watchlist: list[str]) -> list[dict]:
    """Screen all tickers, return sorted by opportunity score."""
    results = []
    for ticker in watchlist:
        r = _screen_ticker(ticker)
        if r and r["direction"] != "NEUTRAL":
            results.append(r)

    # Sort: BUYs by highest score, SELLs by lowest score
    buys = sorted([r for r in results if r["direction"] == "BUY"],
                  key=lambda x: x["score"], reverse=True)
    sells = sorted([r for r in results if r["direction"] == "SELL"],
                   key=lambda x: x["score"])

    # Interleave top buys and sells
    candidates = []
    for b, s in zip(buys, sells):
        candidates.append(b)
        candidates.append(s)
    # Add remaining
    candidates.extend(buys[len(sells):])
    candidates.extend(sells[len(buys):])

    return candidates[:MAX_AI_CANDIDATES]


async def run_market_scan(
    model: str | None = None,
    senior_model: str | None = "claude-opus-4-6",
    watchlist: list[str] | None = None,
    max_candidates: int | None = None,
    vix_override: float | None = None,
    scan_id: str | None = None,
) -> dict:
    """
    Full market scan:
    0. Check circuit breakers — hard block if triggered
    1. Check VIX regime — if VIX > 30, suppress all BUY signals
    2. Pre-screen watchlist
    3. Run AI pipeline on top candidates
    4. Execute approved trades
    Returns scan summary.
    """
    from app.agents.structured_runner import run_structured_agent_analysis
    from app.core.postgres import AsyncSessionLocal
    from app.db.models.agent_run import AgentRun
    from app.api.v1.notifications import save_notification
    from app.db.models.settings import get_setting as _get_setting
    import uuid

    # Load scan parameters from DB settings (caller overrides take precedence)
    if model is None:
        model = str(await _get_setting("llm_model", "deepseek-ai/deepseek-v4-flash"))
    if max_candidates is None:
        max_candidates = int(await _get_setting("scan_max_candidates", MAX_AI_CANDIDATES))

    # Respect scan_enabled flag
    scan_enabled = await _get_setting("scan_enabled", True)
    if not scan_enabled:
        log.info("scanner.disabled", reason="scan_enabled=False in settings")
        return {
            "status": "disabled",
            "screened": 0,
            "candidates": 0,
            "trades_placed": 0,
            "duration_s": 0,
        }

    scan_watchlist = watchlist or WATCHLIST
    scan_start = datetime.now(UTC)
    debate_rounds_setting = int(await _get_setting("debate_rounds", 2))

    # ── Circuit breaker gate ───────────────────────────────────────────────────
    try:
        from app.workers.circuit_breakers import check_circuit_breakers
        cb = await check_circuit_breakers()
        if cb.get("blocked"):
            reasons = "; ".join(cb.get("reasons", ["Unknown"]))
            log.warning("scanner.circuit_breaker_blocked", reasons=reasons)
            await save_notification(
                type="scan_blocked",
                title="Scan blocked by circuit breaker",
                body=f"Market scan skipped — circuit breaker active: {reasons}",
            )
            return {
                "status": "blocked_circuit_breaker",
                "reasons": cb.get("reasons", []),
                "screened": 0,
                "candidates": 0,
                "trades_placed": 0,
                "duration_s": 0,
            }
    except Exception as e:
        log.warning("scanner.circuit_breaker_check_failed", error=str(e))

    # ── VIX regime gate ────────────────────────────────────────────────────────
    vix = vix_override
    if vix is None:
        try:
            import yfinance as yf
            loop_tmp = asyncio.get_running_loop()
            def _fetch_vix():
                hist = yf.Ticker("^VIX").history(period="1d", interval="1m")
                return float(hist["Close"].iloc[-1]) if not hist.empty else None
            vix = await loop_tmp.run_in_executor(None, _fetch_vix)
        except Exception:
            vix = None

    vix_gate = vix is not None and vix > 30
    if vix_gate:
        log.warning("scanner.vix_gate", vix=round(vix, 1),
                    action="suppressing_buy_signals")

    log.info("scanner.scan.start", watchlist_size=len(scan_watchlist), vix=vix)

    # Step 1: Pre-screen (fast, free)
    loop = asyncio.get_running_loop()
    candidates = await loop.run_in_executor(None, _run_pre_screen, scan_watchlist)

    # Apply VIX gate — drop all BUY candidates when volatility is extreme
    if vix_gate:
        before = len(candidates)
        candidates = [c for c in candidates if c["direction"] != "BUY"]
        log.warning("scanner.vix_gate.applied",
                    dropped=before - len(candidates), remaining=len(candidates))

    log.info("scanner.prescreen.done",
             candidates=len(candidates),
             tickers=[c["ticker"] for c in candidates])

    if not candidates:
        return {
            "status": "no_candidates",
            "screened": len(scan_watchlist),
            "candidates": 0,
            "trades_placed": 0,
            "duration_s": 0,
        }

    # Step 2: Run full AI pipeline on top candidates
    analysis_date = scan_start.strftime("%Y-%m-%d")
    run_ids = []

    for candidate in candidates[:max_candidates]:
        ticker = candidate["ticker"]
        run_id = str(uuid.uuid4())

        # Create AgentRun record
        async with AsyncSessionLocal() as db:
            run = AgentRun(
                id=run_id,
                ticker=ticker,
                analysis_date=analysis_date,
                status="pending",
                llm_model=model,
                debate_rounds=debate_rounds_setting,
            )
            db.add(run)
            await db.commit()

        run_ids.append((run_id, ticker, candidate["direction"]))
        log.info("scanner.queued", ticker=ticker, score=candidate["score"],
                 direction=candidate["direction"])

    # Run pipelines in batches of 3 (parallel within batch, sequential between)
    # Balances speed vs. Claude API rate limits
    from app.core.websocket_manager import ws_manager

    BATCH_SIZE = 3
    results = []

    async def _run_one(run_id: str, ticker: str, scan_id: str | None = None):
        if scan_id:
            await ws_manager.broadcast(f"scan:{scan_id}", {
                "type": "scan_progress",
                "ticker": ticker,
                "stage": "starting",
                "completed": len(results),
                "total": len(run_ids),
            })
        try:
            await run_structured_agent_analysis(
                run_id=run_id,
                ticker=ticker,
                analysis_date=analysis_date,
                debate_rounds=debate_rounds_setting,
                model=model,
                senior_model=senior_model,
            )
            r = {"ticker": ticker, "run_id": run_id, "status": "completed"}
        except Exception as e:
            log.error("scanner.pipeline_failed", ticker=ticker, error=str(e))
            r = {"ticker": ticker, "run_id": run_id, "status": "failed", "error": str(e)}

        results.append(r)
        if scan_id:
            await ws_manager.broadcast(f"scan:{scan_id}", {
                "type": "scan_progress",
                "ticker": ticker,
                "stage": "done",
                "status": r["status"],
                "completed": len(results),
                "total": len(run_ids),
            })
        return r

    for i in range(0, len(run_ids), BATCH_SIZE):
        batch = run_ids[i:i + BATCH_SIZE]
        await asyncio.gather(*[_run_one(rid, tkr, scan_id) for rid, tkr, _ in batch])

    duration = (datetime.now(UTC) - scan_start).total_seconds()

    # Count trades placed (check DB for submitted trades from this scan)
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from app.db.models.trade import Trade
        run_id_list = [r["run_id"] for r in results]
        result_db = await db.execute(
            select(Trade).where(Trade.agent_run_id.in_(run_id_list))
        )
        trades_placed = len(result_db.scalars().all())

    summary = {
        "status": "completed",
        "screened": len(scan_watchlist),
        "candidates_analyzed": len(results),
        "trades_placed": trades_placed,
        "duration_s": round(duration, 1),
        "results": results,
        "pre_screen": candidates,
    }

    log.info("scanner.scan.done", **{k: v for k, v in summary.items() if k != "results"})

    # Log activity
    try:
        from app.api.v1.activity import log_activity
        await log_activity(
            feature="scanner",
            action="scan_completed",
            ticker=None,
            details={
                "screened": summary["screened"],
                "candidates_analyzed": summary["candidates_analyzed"],
                "trades_placed": summary["trades_placed"],
                "scan_id": scan_id,
            },
            result="completed",
            duration_s=round(duration, 1),
        )
    except Exception as act_err:
        log.warning("scanner.activity_log_failed", error=str(act_err))

    return summary
