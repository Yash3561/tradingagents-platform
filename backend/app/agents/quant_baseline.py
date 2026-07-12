"""
Quant Baseline strategy runner — zero LLM calls.

Deterministic, regime-filtered rules on the same market data the agents see:

  ENTRY (BUY):
    trend_follow    — price > MA50 > MA200, MACD bullish, RSI 45-70.
                      Only in BULL_TRENDING / SIDEWAYS regimes.
    mean_reversion  — price > MA200 (long-term uptrend intact) and RSI <= 32
                      after a down week. Only in BULL_TRENDING / SIDEWAYS.
  EXIT (SELL):
    trend_break     — price closes below MA200.
    overbought      — RSI >= 78.
  Everything else → HOLD. No BUYs in BEAR_TRENDING or HIGH_VOLATILITY.

  Risk: stop = 2×ATR14 (clamped 3-8%), take-profit = 2× stop (2:1 R:R),
  position size capped by the regime's max_position_pct.

Runs through the exact same lifecycle as the agent pipeline — AgentRun row,
WS events on run:{id}, and _place_order_if_approved for execution — so trades,
track record, and Strategy Lab comparisons are apples-to-apples. AgentRun rows
are tagged llm_model=QUANT_MODEL_LABEL.

This is the control group: if the LLM agents can't beat these rules, the
product story is explainability, not alpha.
"""

from __future__ import annotations
import asyncio
from datetime import datetime, UTC

import structlog

from app.agents.contracts import Decision, RiskAssessment, RiskLevel, FinalDecision
from app.agents.structured_runner import (
    _fetch_market_data, _inject_live_price, _emit, _place_order_if_approved,
)
from app.core.postgres import AsyncSessionLocal
from app.db.models.agent_run import AgentRun

log = structlog.get_logger()

QUANT_MODEL_LABEL = "quant-baseline"

# Rule thresholds — change deliberately; these define the strategy
TREND_RSI_MIN = 45.0
TREND_RSI_MAX = 70.0
MEANREV_RSI_MAX = 32.0
MEANREV_RSI_DEEP = 27.0
EXIT_RSI = 78.0
STOP_ATR_MULT = 2.0
STOP_MIN_PCT, STOP_MAX_PCT = 3.0, 8.0
RR_RATIO = 2.0
NO_BUY_REGIMES = {"BEAR_TRENDING", "HIGH_VOLATILITY"}


def _evaluate(md: dict, regime_data: dict) -> dict:
    """
    Pure rules evaluation. Returns decision, confidence, setup name,
    risk params, and the full checklist of rule evaluations (for the audit trail).
    """
    regime = regime_data.get("regime", "UNKNOWN")
    strategy = regime_data.get("strategy", {}) or {}
    regime_max_pos = float(strategy.get("max_position_pct", 5.0))

    # Coerce to plain Python types — yfinance-derived values can be numpy
    # scalars, and np.bool_ is not JSON-serializable when stored to the DB
    def _f(v):
        return None if v is None else float(v)

    price = _f(md.get("current_price"))
    rsi = _f(md.get("rsi_14"))
    above_ma50 = None if md.get("above_ma50") is None else bool(md.get("above_ma50"))
    above_ma200 = None if md.get("above_ma200") is None else bool(md.get("above_ma200"))
    ma50, ma200 = _f(md.get("ma_50")), _f(md.get("ma_200"))
    macd_bullish = bool(md.get("macd_bullish"))
    vol_ratio = _f(md.get("volume_ratio")) or 1.0
    atr_pct = _f(md.get("atr_pct"))
    chg_1w = _f(md.get("change_1w_pct")) or 0.0
    pct_from_high = _f(md.get("pct_from_52w_high"))

    checks = {
        "regime": regime,
        "regime_allows_buys": regime not in NO_BUY_REGIMES,
        "above_ma50": above_ma50,
        "above_ma200": above_ma200,
        "ma50_above_ma200": bool(ma50 is not None and ma200 is not None and ma50 > ma200),
        "macd_bullish": macd_bullish,
        "rsi_14": rsi,
        "rsi_in_trend_band": bool(rsi is not None and TREND_RSI_MIN <= rsi <= TREND_RSI_MAX),
        "rsi_oversold": bool(rsi is not None and rsi <= MEANREV_RSI_MAX),
        "rsi_overbought": bool(rsi is not None and rsi >= EXIT_RSI),
        "volume_ratio": vol_ratio,
        "down_week": bool(chg_1w < 0),
        "pct_from_52w_high": pct_from_high,
    }

    # Risk params from volatility — same discipline rules as the agent pipeline
    stop_pct = round(min(max(STOP_ATR_MULT * atr_pct, STOP_MIN_PCT), STOP_MAX_PCT), 2) \
        if atr_pct else 7.0
    tp_pct = round(RR_RATIO * stop_pct, 2)

    # Data guards — no decision without the core indicators
    if price is None or rsi is None or above_ma200 is None:
        return {"decision": Decision.HOLD, "confidence": 0.50, "setup": "insufficient_data",
                "reason": "Missing price history or indicators — no trade without data.",
                "stop_loss_pct": stop_pct, "take_profit_pct": tp_pct,
                "position_size_pct": 0.0, "checks": checks}

    # ── EXIT rules first (they apply regardless of regime) ────────────────────
    if not above_ma200:
        return {"decision": Decision.SELL, "confidence": 0.70, "setup": "trend_break",
                "reason": f"Price closed below MA200 (${ma200:,.2f}) — long-term trend broken. "
                          "Rule: exit longs, no new entries.",
                "stop_loss_pct": stop_pct, "take_profit_pct": tp_pct,
                "position_size_pct": 0.0, "checks": checks}

    if checks["rsi_overbought"]:
        return {"decision": Decision.SELL, "confidence": 0.65, "setup": "overbought",
                "reason": f"RSI {rsi:.0f} >= {EXIT_RSI:.0f} — take profits into strength.",
                "stop_loss_pct": stop_pct, "take_profit_pct": tp_pct,
                "position_size_pct": 0.0, "checks": checks}

    # ── Regime gate for new entries ────────────────────────────────────────────
    if regime in NO_BUY_REGIMES:
        return {"decision": Decision.HOLD, "confidence": 0.60, "setup": "regime_gate",
                "reason": f"Regime is {regime} — new entries suppressed. Capital preservation first.",
                "stop_loss_pct": stop_pct, "take_profit_pct": tp_pct,
                "position_size_pct": 0.0, "checks": checks}

    # ── ENTRY: trend following ─────────────────────────────────────────────────
    if above_ma50 and checks["ma50_above_ma200"] and macd_bullish and checks["rsi_in_trend_band"]:
        conf = 0.65
        if regime == "BULL_TRENDING":
            conf += 0.05
        if vol_ratio >= 1.2:
            conf += 0.05
        if pct_from_high is not None and pct_from_high > -5:
            conf += 0.05  # momentum: within 5% of 52w high
        return {"decision": Decision.BUY, "confidence": round(min(conf, 0.85), 2),
                "setup": "trend_follow",
                "reason": f"Trend entry: price > MA50 > MA200, MACD bullish, RSI {rsi:.0f} "
                          f"in {TREND_RSI_MIN:.0f}-{TREND_RSI_MAX:.0f} band. Regime: {regime}.",
                "stop_loss_pct": stop_pct, "take_profit_pct": tp_pct,
                "position_size_pct": regime_max_pos, "checks": checks}

    # ── ENTRY: mean reversion dip-buy ──────────────────────────────────────────
    if checks["rsi_oversold"] and checks["down_week"]:
        conf = 0.62
        if rsi <= MEANREV_RSI_DEEP:
            conf += 0.05
        if regime == "BULL_TRENDING":
            conf += 0.05
        return {"decision": Decision.BUY, "confidence": round(min(conf, 0.80), 2),
                "setup": "mean_reversion",
                # Smaller size: counter-trend entries get half the regime cap
                "reason": f"Mean-reversion entry: RSI {rsi:.0f} oversold on a down week with "
                          f"price still above MA200. Regime: {regime}.",
                "stop_loss_pct": stop_pct, "take_profit_pct": tp_pct,
                "position_size_pct": round(regime_max_pos / 2, 2), "checks": checks}

    return {"decision": Decision.HOLD, "confidence": 0.55, "setup": "no_setup",
            "reason": "No rule fired: trend conditions incomplete and no oversold dip. "
                      "Doing nothing is a position.",
            "stop_loss_pct": stop_pct, "take_profit_pct": tp_pct,
            "position_size_pct": 0.0, "checks": checks}


def _build_result(ticker: str, analysis_date: str, md: dict,
                  regime_data: dict, verdict: dict) -> dict:
    """Shape the verdict exactly like the agent pipeline's result dict."""
    decision: Decision = verdict["decision"]
    is_trade = decision != Decision.HOLD

    risk = RiskAssessment(
        ticker=ticker,
        risk_level=RiskLevel.MEDIUM if is_trade else RiskLevel.LOW,
        approved=is_trade,
        recommended_position_pct=verdict["position_size_pct"] or None,
        stop_loss_pct=verdict["stop_loss_pct"],
        take_profit_pct=verdict["take_profit_pct"],
        rejection_reason=None,
        risk_notes=[f"Stop = {STOP_ATR_MULT:.0f}×ATR14 clamped to "
                    f"{STOP_MIN_PCT:.0f}-{STOP_MAX_PCT:.0f}%",
                    f"Take-profit = {RR_RATIO:.0f}:1 R:R",
                    f"Size capped by regime ({verdict['checks'].get('regime')})"],
        reasoning="Mechanical risk parameters — volatility-scaled stop, fixed 2:1 "
                  "reward:risk, regime-capped sizing. No discretion.",
    )

    final = FinalDecision(
        ticker=ticker,
        analysis_date=analysis_date,
        decision=decision,
        confidence=verdict["confidence"],
        order_side="buy" if decision == Decision.BUY else ("sell" if decision == Decision.SELL else None),
        position_size_pct=verdict["position_size_pct"] or None,
        order_type="market",
        stop_loss_pct=verdict["stop_loss_pct"],
        take_profit_pct=verdict["take_profit_pct"],
        primary_reason=verdict["reason"],
        supporting_factors=[f"setup: {verdict['setup']}"],
        summary=f"[Quant Baseline] {verdict['reason']} "
                f"Stop {verdict['stop_loss_pct']}%, target {verdict['take_profit_pct']}%.",
        risk_level=risk.risk_level.value,
        risk_approved=is_trade,
    )

    debate_log = [{
        "agent": "Quant Engine",
        "role": "quant",
        "content": final.summary,
        "signal": decision.value,
        "confidence": verdict["confidence"],
        "data": {"setup": verdict["setup"], "checks": verdict["checks"]},
    }]

    return {
        "decision": decision.value,
        "confidence": verdict["confidence"],
        "summary": final.summary,
        "debate_log": debate_log,
        "reasoning_json": {
            "engine": QUANT_MODEL_LABEL,
            "market_data": md,
            "regime": {k: regime_data.get(k) for k in ("regime", "confidence", "strategy")},
            "rules": verdict["checks"],
            "setup": verdict["setup"],
            "risk": risk.model_dump(),
            "final": final.model_dump(),
        },
    }


async def run_quant_baseline_analysis(
    run_id: str,
    ticker: str,
    analysis_date: str,
    user_id: int | None = None,
):
    """
    Async entry point — same lifecycle contract as run_structured_agent_analysis:
    marks the AgentRun running/completed/failed, emits WS events on run:{run_id},
    and routes approved trades through _place_order_if_approved.
    """
    log.info("quant_baseline.run.start", run_id=run_id, ticker=ticker, user_id=user_id)

    async with AsyncSessionLocal() as db:
        run = await db.get(AgentRun, run_id)
        run.status = "running"
        await db.commit()

    await _emit(run_id, {"type": "status", "status": "running", "ticker": ticker})

    try:
        await _emit(run_id, {"type": "status_update",
                             "message": f"Fetching market data for {ticker}..."})
        loop = asyncio.get_running_loop()

        def _fetch():
            md = _fetch_market_data(ticker)
            return _inject_live_price(md, ticker)

        md = await loop.run_in_executor(None, _fetch)
        if md.get("error"):
            raise RuntimeError(f"Market data unavailable: {md['error']}")

        from app.workers.regime_detector import get_market_regime
        regime_data = await get_market_regime()

        await _emit(run_id, {"type": "agent_start", "agent": "Quant Engine", "role": "quant"})
        verdict = _evaluate(md, regime_data)
        result = _build_result(ticker, analysis_date, md, regime_data, verdict)

        await _emit(run_id, {"type": "debate_event", "agent": "Quant Engine", "role": "quant",
                             "content": result["summary"], "signal": result["decision"],
                             "confidence": result["confidence"]})

        async with AsyncSessionLocal() as db:
            run = await db.get(AgentRun, run_id)
            run.status = "completed"
            run.decision = result["decision"]
            run.confidence = result["confidence"]
            run.summary = result["summary"]
            run.debate_log = result["debate_log"]
            run.reasoning_json = result["reasoning_json"]
            run.completed_at = datetime.now(UTC)
            await db.commit()

        await _emit(run_id, {
            "type": "completed",
            "decision": result["decision"],
            "confidence": result["confidence"],
            "summary": result["summary"],
            "debate_log": result["debate_log"],
        })

        await _place_order_if_approved(run_id, ticker, result, user_id=user_id)

    except Exception as exc:
        import traceback
        log.error("quant_baseline.run.error", run_id=run_id, error=str(exc),
                  traceback=traceback.format_exc())
        async with AsyncSessionLocal() as db:
            run = await db.get(AgentRun, run_id)
            run.status = "failed"
            # Message only — tracebacks (file paths, internals) stay in server logs
            run.error = str(exc)
            run.completed_at = datetime.now(UTC)
            await db.commit()
        await _emit(run_id, {"type": "error", "error": str(exc)})
