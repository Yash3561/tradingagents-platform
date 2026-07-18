"""
Momentum Rotation engine — zero LLM calls, one decision per ~month.

Live expression of the 2026-07-18 walk-forward winner (see
docs/research/momentum-walkforward-2026-07-18.md): rank the research universe
by 6-month relative momentum at the close, hold the top-N inverse-vol
weighted, rotate on a fixed trading-day schedule. No stops, no take-profits —
exits happen ONLY when a name drops out of the top ranks at a rebalance
(position_monitor explicitly skips positions this engine owns).

Verdict from the research: selection is real, but the excess return over
equal-weight is concentration, not risk-adjusted alpha — this arm exists to
find out whether the effect survives forward, judged against an equal-weight
benchmark of the same universe, NOT against its +132% survivorship-flattered
holdout.

Deployment assumptions (documented, enforced softly):
- Runs on a DEDICATED paper account: at each rebalance it sells any held
  position in its universe that is no longer a target. It never touches
  tickers outside its universe.
- Rides the normal scheduled scans (market open + midday). A Redis marker
  records the last rebalance; scans between rebalances no-op. The marker is
  only advanced after a successful rotation, so a failed attempt retries on
  the next scan window instead of burning the cycle.

Same lifecycle as every other engine: AgentRun row per order decision
(llm_model="momentum-rotation"), WS events, _place_order_if_approved for
execution (which knows this engine takes plain market orders, no bracket).
"""

from __future__ import annotations
import asyncio
import uuid
from datetime import datetime, UTC

import structlog

from app.agents.contracts import Decision, RiskAssessment, RiskLevel, FinalDecision
from app.core.postgres import AsyncSessionLocal
from app.db.models.agent_run import AgentRun

log = structlog.get_logger()

MOMENTUM_MODEL_LABEL = "momentum-rotation"

# Tournament-winner defaults; per-user overridable via momentum_* settings
# (NUMERIC_BOUNDS/ENUM_VALUES-clamped in api/v1/settings.py).
MOMENTUM_PARAM_DEFAULTS = {
    "momentum_lookback_days": 126,
    "momentum_skip_days": 0,
    "momentum_top_n": 4,
    "momentum_rebalance_days": 21,     # trading days between rotations
    "momentum_weighting": "inv_vol",   # equal | inv_vol
    "momentum_exposure_pct": 95.0,     # total target exposure across the book
}

HISTORY_CALENDAR_DAYS = 460   # ≥ ~310 trading days: lookback+skip+vol window+buffer
CONFIDENCE = 0.75             # fixed — clears the min_confidence_to_trade gate
REDIS_LAST_RB = "momentum:last_rebalance:{user_id}"


async def _load_params(user_id: int | None) -> dict:
    from app.db.models.user_settings import get_user_setting
    params = {}
    for key, default in MOMENTUM_PARAM_DEFAULTS.items():
        v = await get_user_setting(user_id, key, default)
        if isinstance(default, bool):
            params[key] = bool(v)
        elif isinstance(default, (int, float)) and not isinstance(default, bool):
            params[key] = type(default)(float(v))
        else:
            params[key] = str(v)
    return params


def _fetch_close_panel() -> "pd.DataFrame":
    """Daily closes for the research universe, Alpaca-first (sync — run in executor)."""
    import pandas as pd
    from app.research.data import UNIVERSE, load_history
    end = datetime.now(UTC)
    start = end - pd.Timedelta(days=HISTORY_CALENDAR_DAYS)
    hist = load_history(UNIVERSE, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    if not hist:
        raise RuntimeError("No price history available for the momentum universe")
    return pd.DataFrame({t: df["Close"] for t, df in hist.items()}).sort_index()


def _trading_days_since(close_index, last_date_iso: str | None) -> int | None:
    """Trading days elapsed since the recorded rebalance date (None = never)."""
    import pandas as pd
    if not last_date_iso:
        return None
    last = pd.Timestamp(last_date_iso)
    return int((close_index > last).sum())


def _build_result(ticker: str, decision: Decision, weight_pct: float,
                  reason: str, snapshot: dict) -> dict:
    """Shape one rotation action like the other engines' result dicts."""
    is_trade = decision != Decision.HOLD
    risk = RiskAssessment(
        ticker=ticker,
        risk_level=RiskLevel.MEDIUM if is_trade else RiskLevel.LOW,
        approved=is_trade,
        recommended_position_pct=weight_pct or None,
        stop_loss_pct=None,
        take_profit_pct=None,
        rejection_reason=None,
        risk_notes=[
            "No stop / take-profit by design — exits only at rotation",
            f"Target weight {weight_pct:.1f}% of equity" if weight_pct else "Full liquidation",
            "Judge vs the equal-weight universe benchmark, not absolute return",
        ],
        reasoning="Mechanical monthly rotation — relative-momentum rank decides "
                  "membership, inverse-vol decides weight. No discretion.",
    )
    analysis_date = datetime.now(UTC).strftime("%Y-%m-%d")
    final = FinalDecision(
        ticker=ticker,
        analysis_date=analysis_date,
        decision=decision,
        confidence=CONFIDENCE,
        order_side="buy" if decision == Decision.BUY else ("sell" if decision == Decision.SELL else None),
        position_size_pct=weight_pct or None,
        order_type="market",
        stop_loss_pct=None,
        take_profit_pct=None,
        primary_reason=reason,
        supporting_factors=[f"rank snapshot: {snapshot.get('top_ranks')}"],
        summary=f"[Momentum Rotation] {reason}",
        risk_level=risk.risk_level.value,
        risk_approved=is_trade,
    )
    debate_log = [{
        "agent": "Momentum Engine",
        "role": "quant",
        "content": final.summary,
        "signal": decision.value,
        "confidence": CONFIDENCE,
        "data": snapshot,
    }]
    return {
        "decision": decision.value,
        "confidence": CONFIDENCE,
        "summary": final.summary,
        "debate_log": debate_log,
        "reasoning_json": {
            "engine": MOMENTUM_MODEL_LABEL,
            "market_data": {"current_price": snapshot.get("prices", {}).get(ticker)},
            "rotation": snapshot,
            "risk": risk.model_dump(),
            "final": final.model_dump(),
        },
    }


async def _run_action(user_id: int | None, ticker: str, decision: Decision,
                      weight_pct: float, reason: str, snapshot: dict) -> str:
    """One AgentRun per rotation order — keeps Strategy Lab / track record honest."""
    from app.agents.structured_runner import _emit, _place_order_if_approved

    run_id = str(uuid.uuid4())
    result = _build_result(ticker, decision, weight_pct, reason, snapshot)
    async with AsyncSessionLocal() as db:
        db.add(AgentRun(
            id=run_id,
            user_id=user_id,
            ticker=ticker,
            analysis_date=datetime.now(UTC).strftime("%Y-%m-%d"),
            status="completed",
            decision=result["decision"],
            confidence=result["confidence"],
            summary=result["summary"],
            debate_log=result["debate_log"],
            reasoning_json=result["reasoning_json"],
            llm_model=MOMENTUM_MODEL_LABEL,
            debate_rounds=0,
            completed_at=datetime.now(UTC),
        ))
        await db.commit()

    await _emit(run_id, {
        "type": "completed",
        "decision": result["decision"],
        "confidence": result["confidence"],
        "summary": result["summary"],
        "debate_log": result["debate_log"],
    })
    await _place_order_if_approved(run_id, ticker, result, user_id=user_id)
    return run_id


async def run_momentum_scan(user_id: int | None) -> dict:
    """
    Called by the scheduled scan for strategy_mode="momentum" users.
    Rebalances when due, otherwise no-ops cheaply.
    """
    from app.core.redis_client import get_redis
    from app.research.data import UNIVERSE
    from app.research.momentum import latest_target_weights

    t0 = datetime.now(UTC)
    params = await _load_params(user_id)
    r = await get_redis()
    rb_key = REDIS_LAST_RB.format(user_id=user_id)

    loop = asyncio.get_running_loop()
    try:
        close = await loop.run_in_executor(None, _fetch_close_panel)
    except Exception as e:
        log.error("momentum.data_failed", user_id=user_id, error=str(e)[:200])
        return {"status": "momentum_data_failed", "error": str(e)[:200],
                "screened": 0, "candidates": 0, "trades_placed": 0, "duration_s": 0}

    # A thin panel means the data layer is degraded — do not rotate on bad data
    if close.shape[1] < max(params["momentum_top_n"] * 3, 12):
        log.warning("momentum.panel_too_thin", user_id=user_id, tickers=close.shape[1])
        return {"status": "momentum_panel_too_thin", "tickers": close.shape[1],
                "screened": 0, "candidates": 0, "trades_placed": 0, "duration_s": 0}

    last_rb = await r.get(rb_key)
    if isinstance(last_rb, bytes):
        last_rb = last_rb.decode()
    elapsed_td = _trading_days_since(close.index, last_rb)
    if elapsed_td is not None and elapsed_td < params["momentum_rebalance_days"]:
        return {"status": "momentum_not_due",
                "trading_days_since_rebalance": elapsed_td,
                "due_in_trading_days": params["momentum_rebalance_days"] - elapsed_td,
                "screened": 0, "candidates": 0, "trades_placed": 0, "duration_s": 0}

    weights = latest_target_weights(
        close,
        lookback_days=params["momentum_lookback_days"],
        skip_days=params["momentum_skip_days"],
        top_n=params["momentum_top_n"],
        weighting=params["momentum_weighting"],
    )
    if not weights:
        log.warning("momentum.no_ranks", user_id=user_id)
        return {"status": "momentum_no_ranks",
                "screened": close.shape[1], "candidates": 0,
                "trades_placed": 0, "duration_s": 0}

    # Cap any single name at 40% of the book — inverse-vol weights can skew
    # hard when one holding is much calmer than the rest, and 0.40 × 95%
    # exposure = 38% of equity, inside the contracts' le=40 schema bound.
    weights = {t: min(w, 0.40) for t, w in weights.items()}
    exposure = params["momentum_exposure_pct"]
    targets = {t: round(w * exposure, 2) for t, w in weights.items()}

    # Current holdings inside the universe (dedicated-account assumption)
    held: set[str] = set()
    broker = None
    if user_id is not None:
        from app.broker.credentials import get_client_for_user
        broker = await get_client_for_user(user_id)
    if broker is not None:
        try:
            positions = await loop.run_in_executor(None, broker.get_positions)
            held = {p.get("symbol") for p in positions
                    if p.get("symbol") in set(UNIVERSE) and float(p.get("qty", 0)) > 0}
        except Exception as e:
            # Can't see the book → can't rotate safely; retry next scan window
            log.error("momentum.positions_failed", user_id=user_id, error=str(e)[:200])
            return {"status": "momentum_positions_failed", "error": str(e)[:200],
                    "screened": close.shape[1], "candidates": 0,
                    "trades_placed": 0, "duration_s": 0}

    exits = sorted(held - set(targets))
    entries = sorted(set(targets) - held)
    keeps = sorted(held & set(targets))

    # Audit snapshot shared by every run this rotation creates
    shifted = close.shift(params["momentum_skip_days"])
    mom_row = (shifted / shifted.shift(params["momentum_lookback_days"]) - 1).iloc[-1].dropna()
    top10 = mom_row.nlargest(10)
    snapshot = {
        "as_of": str(close.index[-1].date()),
        "params": params,
        "targets": targets,
        "held_before": sorted(held),
        "entries": entries, "exits": exits, "keeps": keeps,
        "top_ranks": {t: round(float(v) * 100, 1) for t, v in top10.items()},
        "prices": {t: round(float(close[t].iloc[-1]), 2)
                   for t in set(list(targets) + exits) if t in close.columns},
    }

    log.info("momentum.rotation", user_id=user_id, entries=entries, exits=exits,
             keeps=keeps, first=elapsed_td is None)

    trades_attempted = 0
    # Exits first — they free the cash the entries need
    for ticker in exits:
        await _run_action(
            user_id, ticker, Decision.SELL, 0.0,
            f"{ticker} dropped out of the top-{params['momentum_top_n']} momentum ranks "
            f"— rotating out.", snapshot)
        trades_attempted += 1
    for ticker in entries:
        await _run_action(
            user_id, ticker, Decision.BUY, targets[ticker],
            f"{ticker} entered the top-{params['momentum_top_n']} momentum ranks "
            f"({params['momentum_lookback_days']}d lookback) — target weight "
            f"{targets[ticker]:.1f}%.", snapshot)
        trades_attempted += 1

    # Mark the cycle complete only now — failures above raise and leave the
    # marker unset, so the next scan window retries the same rotation.
    await r.set(rb_key, str(close.index[-1].date()))

    if trades_attempted:
        try:
            from app.api.v1.notifications import save_notification
            await save_notification(
                type="scan_complete",
                title="Momentum rotation executed",
                body=(f"Rotation as of {snapshot['as_of']}: "
                      f"in {', '.join(entries) or '—'}; out {', '.join(exits) or '—'}; "
                      f"holding {', '.join(keeps) or '—'}."),
                user_id=user_id,
            )
        except Exception:
            pass

    return {
        "status": "momentum_rebalanced" if trades_attempted else "momentum_in_position",
        "entries": entries, "exits": exits, "keeps": keeps,
        "screened": close.shape[1],
        "candidates": len(targets),
        "trades_placed": trades_attempted,
        "duration_s": round((datetime.now(UTC) - t0).total_seconds(), 1),
    }
