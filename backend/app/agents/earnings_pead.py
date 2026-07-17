"""
Earnings PEAD (Post-Earnings-Announcement Drift) strategy runner — zero LLM calls.

Deterministic, event-driven rule: enter long the first tradeable session after a
watchlist ticker reports a large positive EPS surprise, hold up to N trading days,
ATR-scaled stop / fixed R:R target. Fires only a handful of times a month per user
(quarterly earnings), so unlike the intraday engine it rides the existing scheduled
scan cadence (market open + midday) rather than a dedicated loop — see scanner.py's
strategy_mode dispatch.

Parameters mirror the validated walk-forward research (docs/research/earnings-drift-
walkforward-2026-07-16.md, refit on a 105-ticker universe, checked clean against a
fourth unrelated universe): surprise >=10%, gap-up confirmed, 3.5x ATR stop, 3:1 R:R,
10-day hold. Same honest-signal semantics as research/earnings.py's `_entry_day_index`
(pre-market report -> same session's open, after-close/midday -> next session's open)
— evaluated live "as of now" instead of against a historical array.

Runs through the exact same lifecycle as the agent/quant pipelines — AgentRun row,
WS events on run:{id}, and _place_order_if_approved for execution (native gtc bracket
order — the day-TIF bug fixed elsewhere this session doesn't apply to multi-day
holds) — so trades, track record, and Strategy Lab comparisons are apples-to-apples.
AgentRun rows are tagged llm_model=EARNINGS_MODEL_LABEL.
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, time as dtime, UTC
from zoneinfo import ZoneInfo

import structlog

from app.agents.contracts import Decision, RiskAssessment, RiskLevel, FinalDecision
from app.agents.structured_runner import (
    _fetch_market_data, _inject_live_price, _emit, _place_order_if_approved,
)
from app.core.postgres import AsyncSessionLocal
from app.db.models.agent_run import AgentRun

log = structlog.get_logger()

EARNINGS_MODEL_LABEL = "earnings-pead"
ET = ZoneInfo("America/New_York")

# Defaults = the validated 105-ticker-refit winner from the walk-forward research.
# position_size_pct replaces the research module's risk_pct/stop-distance sizing —
# _place_order_if_approved sizes by % of equity, matching every other live engine.
EARNINGS_PARAM_DEFAULTS = {
    "earnings_surprise_min_pct": 10.0,
    "earnings_require_gap_up": True,
    "earnings_stop_atr_mult": 3.5,
    "earnings_rr_ratio": 3.0,
    "earnings_hold_days": 10,
    "earnings_position_size_pct": 5.0,
}
STOP_MIN_PCT, STOP_MAX_PCT = 3.0, 15.0


async def _load_params(user_id: int | None) -> dict:
    """The user's earnings policy profile: settings overrides on the defaults."""
    from app.db.models.user_settings import get_user_setting
    params = {}
    for key, default in EARNINGS_PARAM_DEFAULTS.items():
        v = await get_user_setting(user_id, key, default)
        if isinstance(default, bool):
            params[key] = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes")
        else:
            params[key] = float(v)
    return params


def _entry_day(report_ts, pre_market: bool):
    """First tradeable session at/after the news was public (weekend-aware)."""
    report_day = (report_ts.tz_localize(None) if report_ts.tzinfo else report_ts).date()
    if pre_market:
        return report_day
    entry_day = report_day + timedelta(days=1)
    while entry_day.weekday() >= 5:  # Sat/Sun -> next trading day
        entry_day += timedelta(days=1)
    return entry_day


def check_recent_earnings_surprise(ticker: str, params: dict) -> dict | None:
    """
    Sync (executor) — is TODAY the actionable session for a qualifying earnings
    surprise on this ticker? Returns None (no signal) or a dict with surprise/gap
    context. Cheap: last 4 quarters only, not the research module's full history.
    """
    import yfinance as yf

    try:
        t = yf.Ticker(ticker)
        ed = t.get_earnings_dates(limit=4)
    except Exception as e:
        log.debug("earnings_pead.fetch_failed", ticker=ticker, error=str(e)[:120])
        return None
    if ed is None or ed.empty:
        return None
    ed = ed.dropna(subset=["Reported EPS", "Surprise(%)"]).sort_index()
    if ed.empty:
        return None

    report_ts = ed.index[-1]
    surprise_pct = float(ed.iloc[-1]["Surprise(%)"])
    if surprise_pct < params["earnings_surprise_min_pct"]:
        return None

    pre_market = report_ts.time() < dtime(12, 0)
    entry_day = _entry_day(report_ts, pre_market)
    today = datetime.now(ET).date()
    if today != entry_day:
        return None  # too early, or the actionable window already passed

    gap_pct = None
    if params["earnings_require_gap_up"]:
        hist = t.history(period="5d", interval="1d")
        if len(hist) < 2:
            return None
        prior_close = float(hist["Close"].iloc[-2])
        today_open = float(hist["Open"].iloc[-1])
        gap_pct = round((today_open - prior_close) / prior_close * 100, 2)
        if gap_pct <= 0:
            return None

    return {"surprise_pct": round(surprise_pct, 1), "report_date": str(report_ts.date()),
            "gap_pct": gap_pct}


NASDAQ_CALENDAR_URL = "https://api.nasdaq.com/api/calendar/earnings"


def fetch_earnings_reporters(min_market_cap: float = 2e9,
                             max_symbols: int = 150) -> list[str]:
    """
    Sync (executor) — every US ticker that reported today or the prior trading
    day, from NASDAQ's public earnings calendar, largest market caps first.
    Whole-market candidate pool for scanner.py's earnings prescreen (setting
    `earnings_whole_market`) instead of the user's watchlist.

    check_recent_earnings_surprise remains the authoritative per-ticker gate
    (surprise size, entry-day timing, gap confirmation) — a calendar row can
    never place a trade by itself. max_symbols caps the yfinance verification
    loop; largest caps first keeps the pool closest to the validated universe.
    """
    import httpx

    today = datetime.now(ET).date()
    prev = today - timedelta(days=1)
    while prev.weekday() >= 5:  # Sat/Sun -> prior Friday
        prev -= timedelta(days=1)

    caps: dict[str, float] = {}
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    with httpx.Client(timeout=15.0, headers=headers) as client:
        for day in (today, prev):
            try:
                r = client.get(NASDAQ_CALENDAR_URL, params={"date": day.isoformat()})
                r.raise_for_status()
                rows = ((r.json().get("data") or {}).get("rows")) or []
            except Exception as e:
                log.warning("earnings_pead.calendar_failed", date=str(day),
                            error=str(e)[:120])
                continue
            for row in rows:
                sym = (row.get("symbol") or "").strip().upper()
                if not sym.isalnum():
                    continue  # preferred shares / units — skip
                try:
                    cap = float((row.get("marketCap") or "")
                                .replace("$", "").replace(",", ""))
                except ValueError:
                    continue
                if cap >= min_market_cap:
                    caps[sym] = max(cap, caps.get(sym, 0.0))

    ranked = sorted(caps, key=lambda s: caps[s], reverse=True)
    return ranked[:max_symbols]


def _evaluate(md: dict, signal: dict | None, params: dict) -> dict:
    """Pure rules evaluation. Returns decision, confidence, risk params, audit trail."""
    if signal is None:
        return {"decision": Decision.HOLD, "confidence": 0.50, "setup": "no_signal",
                "reason": "No qualifying earnings surprise today.",
                "stop_loss_pct": 7.0, "take_profit_pct": 21.0,
                "position_size_pct": 0.0, "surprise_pct": None, "report_date": None}

    price = md.get("current_price")
    atr_pct = md.get("atr_pct")
    if price is None or atr_pct is None:
        return {"decision": Decision.HOLD, "confidence": 0.50, "setup": "insufficient_data",
                "reason": "Missing price/ATR data — no trade without data.",
                "stop_loss_pct": 7.0, "take_profit_pct": 21.0,
                "position_size_pct": 0.0, "surprise_pct": signal["surprise_pct"],
                "report_date": signal["report_date"]}

    stop_pct = round(min(max(params["earnings_stop_atr_mult"] * atr_pct, STOP_MIN_PCT),
                         STOP_MAX_PCT), 2)
    tp_pct = round(params["earnings_rr_ratio"] * stop_pct, 2)

    conf = 0.62
    if signal["surprise_pct"] >= 20:
        conf += 0.05
    if signal.get("gap_pct") and signal["gap_pct"] >= 3:
        conf += 0.05
    conf = round(min(conf, 0.75), 2)

    gap_note = f", gap +{signal['gap_pct']:.1f}%" if signal.get("gap_pct") else ""
    return {
        "decision": Decision.BUY, "confidence": conf, "setup": "pead_entry",
        "reason": f"EPS surprise +{signal['surprise_pct']:.1f}% on {signal['report_date']}"
                  f"{gap_note} — post-earnings drift entry, hold up to "
                  f"{int(params['earnings_hold_days'])} trading days.",
        "stop_loss_pct": stop_pct, "take_profit_pct": tp_pct,
        "position_size_pct": params["earnings_position_size_pct"],
        "surprise_pct": signal["surprise_pct"], "report_date": signal["report_date"],
    }


def _build_result(ticker: str, analysis_date: str, md: dict, verdict: dict,
                  params: dict) -> dict:
    """Shape the verdict exactly like the other deterministic engines' result dict."""
    decision: Decision = verdict["decision"]
    is_trade = decision == Decision.BUY

    risk = RiskAssessment(
        ticker=ticker,
        risk_level=RiskLevel.MEDIUM if is_trade else RiskLevel.LOW,
        approved=is_trade,
        recommended_position_pct=verdict["position_size_pct"] or None,
        stop_loss_pct=verdict["stop_loss_pct"],
        take_profit_pct=verdict["take_profit_pct"],
        rejection_reason=None if is_trade else verdict["reason"],
        risk_notes=[f"Stop = {verdict['stop_loss_pct']}% (ATR-scaled, clamped "
                    f"{STOP_MIN_PCT:.0f}-{STOP_MAX_PCT:.0f}%)",
                    f"Take-profit = {verdict['take_profit_pct']}%",
                    f"Time exit after {int(params['earnings_hold_days'])} trading days"],
        reasoning="Mechanical risk parameters — volatility-scaled stop, fixed "
                  "reward:risk ratio, fixed position size. No discretion.",
    )

    final = FinalDecision(
        ticker=ticker,
        analysis_date=analysis_date,
        decision=decision,
        confidence=verdict["confidence"],
        order_side="buy" if is_trade else None,
        position_size_pct=verdict["position_size_pct"] or None,
        order_type="market",
        stop_loss_pct=verdict["stop_loss_pct"],
        take_profit_pct=verdict["take_profit_pct"],
        primary_reason=verdict["reason"],
        supporting_factors=[f"setup: {verdict['setup']}"],
        summary=f"[Earnings PEAD] {verdict['reason']} "
                f"Stop {verdict['stop_loss_pct']}%, target {verdict['take_profit_pct']}%.",
        risk_level=risk.risk_level.value,
        risk_approved=is_trade,
    )

    debate_log = [{
        "agent": "Earnings PEAD Engine", "role": "quant",
        "content": final.summary, "signal": decision.value,
        "confidence": verdict["confidence"],
        "data": {"setup": verdict["setup"], "surprise_pct": verdict["surprise_pct"],
                 "report_date": verdict["report_date"]},
    }]

    return {
        "decision": decision.value,
        "confidence": verdict["confidence"],
        "summary": final.summary,
        "debate_log": debate_log,
        "reasoning_json": {
            "engine": EARNINGS_MODEL_LABEL,
            "market_data": md,
            "setup": verdict["setup"],
            "surprise_pct": verdict["surprise_pct"],
            "report_date": verdict["report_date"],
            "hold_days": int(params["earnings_hold_days"]),
            "risk": risk.model_dump(),
            "final": final.model_dump(),
            "params": params,
        },
    }


async def run_earnings_pead_analysis(
    run_id: str,
    ticker: str,
    analysis_date: str,
    user_id: int | None = None,
):
    """
    Async entry point — same lifecycle contract as run_quant_baseline_analysis:
    marks the AgentRun running/completed/failed, emits WS events on run:{run_id},
    and routes approved trades through _place_order_if_approved.
    """
    log.info("earnings_pead.run.start", run_id=run_id, ticker=ticker, user_id=user_id)

    async with AsyncSessionLocal() as db:
        run = await db.get(AgentRun, run_id)
        run.status = "running"
        await db.commit()

    await _emit(run_id, {"type": "status", "status": "running", "ticker": ticker})

    try:
        await _emit(run_id, {"type": "status_update",
                             "message": f"Checking {ticker} for a recent earnings surprise..."})
        loop = asyncio.get_running_loop()
        params = await _load_params(user_id)

        signal = await loop.run_in_executor(None, check_recent_earnings_surprise, ticker, params)

        def _fetch():
            md = _fetch_market_data(ticker)
            return _inject_live_price(md, ticker)

        md = await loop.run_in_executor(None, _fetch)
        if md.get("error"):
            raise RuntimeError(f"Market data unavailable: {md['error']}")

        await _emit(run_id, {"type": "agent_start", "agent": "Earnings PEAD Engine", "role": "quant"})
        verdict = _evaluate(md, signal, params)
        result = _build_result(ticker, analysis_date, md, verdict, params)

        await _emit(run_id, {"type": "debate_event", "agent": "Earnings PEAD Engine", "role": "quant",
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
        log.error("earnings_pead.run.error", run_id=run_id, error=str(exc),
                  traceback=traceback.format_exc())
        async with AsyncSessionLocal() as db:
            run = await db.get(AgentRun, run_id)
            run.status = "failed"
            run.error = str(exc)
            run.completed_at = datetime.now(UTC)
            await db.commit()
        await _emit(run_id, {"type": "error", "error": str(exc)})
