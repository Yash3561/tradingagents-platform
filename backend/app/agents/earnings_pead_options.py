"""
Earnings PEAD expressed via options — zero LLM calls.

Same validated trigger as agents/earnings_pead.py (identical entry gate:
check_recent_earnings_surprise), expressed as a defined-risk long call/put
instead of stock. The point of doing this at all: leverage on a signal
that's already survived walk-forward validation, with loss hard-capped at
the premium paid — never more, unlike a naked/undefined-risk position.

Built 2026-07-21 after confirming Alpaca's options API is first-class:
real listed contracts (proper OCC symbols), real bid/ask, and for liquid
strikes real computed delta + implied volatility straight from Alpaca's
own feed (core/alpaca_options.py) — no yfinance/Yahoo dependency at all
for this engine, unlike Options Desk's chain lookup.

Exit discipline (own position_monitor extension, not _place_order_if_approved
— that function is equity-only: shares, tickers, position_pct sizing, none
of which apply to a contract count against a per-contract premium):
- Time exit: same hold_days as stock PEAD.
- Target: close at a fixed gain on premium (defined below), since a long
  option's own leverage already does the amplifying — no separate ATR stop
  needed, and the loss is already capped at 100% of premium by construction.
"""
from __future__ import annotations
import asyncio
import uuid
from datetime import datetime, UTC

import structlog

from app.agents.contracts import Decision, RiskAssessment, RiskLevel, FinalDecision
from app.agents.earnings_pead import check_recent_earnings_surprise, _load_params as _load_stock_pead_params
from app.agents.structured_runner import _fetch_market_data, _inject_live_price, _emit
from app.core.postgres import AsyncSessionLocal
from app.db.models.agent_run import AgentRun
from app.db.models.trade import Trade

log = structlog.get_logger()

OPTIONS_MODEL_LABEL = "earnings-pead-options"

# Independent policy profile from the stock PEAD arm — same earnings_* entry
# gate (surprise/gap thresholds) is reused via _load_stock_pead_params, but
# risk/exit parameters are options-specific and separately tunable.
OPTIONS_PARAM_DEFAULTS = {
    "pead_options_target_days": 14,       # expiry preference: ~2 weeks out
    "pead_options_target_delta": 0.35,    # moderate OTM, defined-risk directional
    "pead_options_hold_days": 10,         # matches stock PEAD's default hold
    "pead_options_target_gain_pct": 100.0,  # close at +100% of premium paid
    "pead_options_max_loss_pct": 60.0,    # close at -60% of premium (not -100%
                                          # — exit before full decay, don't ride
                                          # a clearly-wrong thesis to worthless)
    "pead_options_position_pct": 5.0,     # % of equity risked as premium
    "pead_options_min_bid": 0.10,         # liquidity floor, real quoted bid
}
STOCK_ENTRY_GATE_KEYS = ("earnings_surprise_min_pct", "earnings_require_gap_up")


async def _load_params(user_id: int | None) -> dict:
    from app.db.models.user_settings import get_user_setting
    params = {}
    for key, default in OPTIONS_PARAM_DEFAULTS.items():
        v = await get_user_setting(user_id, key, default)
        params[key] = float(v)
    return params


def _build_result(ticker: str, analysis_date: str, verdict: dict) -> dict:
    """Shape the verdict like the other deterministic engines' result dict."""
    decision: Decision = verdict["decision"]
    is_trade = decision == Decision.BUY

    risk = RiskAssessment(
        ticker=ticker,
        risk_level=RiskLevel.MEDIUM if is_trade else RiskLevel.LOW,
        approved=is_trade,
        recommended_position_pct=verdict.get("position_size_pct") or None,
        stop_loss_pct=None,   # not price-based - see max_loss_pct on the premium instead
        take_profit_pct=None,
        rejection_reason=None if is_trade else verdict["reason"],
        risk_notes=verdict.get("risk_notes", []),
        reasoning="Mechanical: same validated earnings-surprise entry gate as "
                 "stock PEAD, expressed as a defined-risk long option instead "
                 "of stock. Loss capped at premium paid by construction.",
    )
    final = FinalDecision(
        ticker=ticker,
        analysis_date=analysis_date,
        decision=decision,
        confidence=verdict["confidence"],
        order_side="buy" if is_trade else None,
        position_size_pct=verdict.get("position_size_pct") or None,
        order_type="limit",
        primary_reason=verdict["reason"],
        supporting_factors=[f"setup: {verdict['setup']}"],
        summary=f"[PEAD Options] {verdict['reason']}",
        risk_level=risk.risk_level.value,
        risk_approved=is_trade,
    )
    debate_log = [{
        "agent": "PEAD Options Engine", "role": "quant",
        "content": final.summary, "signal": decision.value,
        "confidence": verdict["confidence"],
        "data": {"setup": verdict["setup"], "contract": verdict.get("contract")},
    }]
    return {
        "decision": decision.value,
        "confidence": verdict["confidence"],
        "summary": final.summary,
        "debate_log": debate_log,
        "reasoning_json": {
            "engine": OPTIONS_MODEL_LABEL,
            "setup": verdict["setup"],
            "contract": verdict.get("contract"),
            "risk": risk.model_dump(),
            "final": final.model_dump(),
        },
    }


async def run_earnings_pead_options_analysis(
    run_id: str,
    ticker: str,
    analysis_date: str,
    user_id: int | None = None,
):
    """Same lifecycle contract as the other deterministic engines: marks the
    AgentRun running/completed/failed, emits WS events, places a real order
    on approval."""
    log.info("pead_options.run.start", run_id=run_id, ticker=ticker, user_id=user_id)

    async with AsyncSessionLocal() as db:
        run = await db.get(AgentRun, run_id)
        run.status = "running"
        await db.commit()
    await _emit(run_id, {"type": "status", "status": "running", "ticker": ticker})

    try:
        loop = asyncio.get_running_loop()
        stock_params = await _load_stock_pead_params(user_id)
        opt_params = await _load_params(user_id)

        signal = await loop.run_in_executor(None, check_recent_earnings_surprise, ticker, stock_params)

        def _fetch():
            md = _fetch_market_data(ticker)
            return _inject_live_price(md, ticker)
        md = await loop.run_in_executor(None, _fetch)

        current_price = md.get("current_price")
        if signal is None or current_price is None:
            verdict = {"decision": Decision.HOLD, "confidence": 0.50, "setup": "no_signal",
                      "reason": "No qualifying earnings surprise today.", "risk_notes": []}
        else:
            from app.broker.credentials import get_client_for_user
            from app.broker.alpaca_client import default_client
            broker = await get_client_for_user(user_id) if user_id is not None else default_client()
            if broker is None or not getattr(broker, "configured", False):
                verdict = {"decision": Decision.HOLD, "confidence": 0.50, "setup": "no_broker",
                          "reason": "No broker connected.", "risk_notes": []}
            else:
                from app.core.alpaca_options import pick_contract

                def _pick():
                    return pick_contract(
                        broker.api_key, broker.api_secret, ticker, current_price,
                        target_days=int(opt_params["pead_options_target_days"]),
                        is_call=True, target_delta=opt_params["pead_options_target_delta"],
                        min_bid=opt_params["pead_options_min_bid"],
                    )
                contract = await loop.run_in_executor(None, _pick)

                if contract is None:
                    verdict = {"decision": Decision.HOLD, "confidence": 0.55, "setup": "no_liquid_contract",
                              "reason": f"EPS surprise +{signal['surprise_pct']:.1f}% on "
                                       f"{signal['report_date']} qualifies, but no liquid options "
                                       f"contract near {opt_params['pead_options_target_delta']:.2f} "
                                       f"delta was found — no real contract to trade, so no trade.",
                              "risk_notes": ["No liquid contract found — thesis may be right, "
                                           "no clean way to express it with real liquidity."]}
                else:
                    verdict = {
                        "decision": Decision.BUY, "confidence": 0.62, "setup": "pead_options_entry",
                        "reason": f"EPS surprise +{signal['surprise_pct']:.1f}% on {signal['report_date']} "
                                 f"— long {contract['symbol']} (${contract['strike']:.2f} strike, "
                                 f"exp {contract['expiry']}, delta {contract['delta']:.2f}), "
                                 f"target +{opt_params['pead_options_target_gain_pct']:.0f}% on premium "
                                 f"or {int(opt_params['pead_options_hold_days'])}-day time exit.",
                        "position_size_pct": opt_params["pead_options_position_pct"],
                        "contract": contract,
                        "risk_notes": [f"Premium ${contract['ask']:.2f} x {contract['multiplier']} "
                                      f"= max loss per contract if held to zero",
                                      f"Real IV {contract['iv']*100:.1f}%" if contract.get("iv") else "IV unavailable"],
                    }

        result = _build_result(ticker, analysis_date, verdict)

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
        await _emit(run_id, {"type": "completed", "decision": result["decision"],
                             "confidence": result["confidence"], "summary": result["summary"],
                             "debate_log": result["debate_log"]})

        if verdict["decision"] == Decision.BUY:
            await _place_options_order(run_id, ticker, verdict, opt_params, user_id)

    except Exception as exc:
        import traceback
        log.error("pead_options.run.error", run_id=run_id, error=str(exc),
                  traceback=traceback.format_exc())
        async with AsyncSessionLocal() as db:
            run = await db.get(AgentRun, run_id)
            run.status = "failed"
            run.error = str(exc)
            run.completed_at = datetime.now(UTC)
            await db.commit()
        await _emit(run_id, {"type": "error", "error": str(exc)})


async def _place_options_order(run_id: str, ticker: str, verdict: dict, opt_params: dict,
                               user_id: int | None):
    """Options-specific order placement — deliberately NOT
    structured_runner._place_order_if_approved, which is hardcoded to
    equity shares/tickers/position_pct-of-equity-in-shares math throughout."""
    from app.broker.credentials import get_client_for_user
    from app.broker.alpaca_client import default_client
    from app.db.models.user_settings import get_user_setting
    from app.agents.structured_runner import _order_seatbelt_blocked

    broker = await get_client_for_user(user_id) if user_id is not None else default_client()
    contract = verdict["contract"]

    seatbelt_reason = await _order_seatbelt_blocked(run_id, user_id)
    if seatbelt_reason:
        log.warning("pead_options.seatbelt_blocked", run_id=run_id, ticker=ticker, reason=seatbelt_reason)
        await _emit(run_id, {"type": "order_skipped", "reason": "seatbelt_blocked",
                             "message": f"Order blocked by a safety limit: {seatbelt_reason}."})
        return

    # Already holding this exact contract? Don't stack.
    existing = broker.get_options_position(contract["symbol"])
    if existing and float(existing.get("qty", 0)) > 0:
        log.info("pead_options.already_positioned", run_id=run_id, symbol=contract["symbol"])
        return

    account = broker.get_account()
    equity = float(account.get("equity", 100_000))
    premium_per_contract = contract["ask"] * contract["multiplier"]
    budget = equity * opt_params["pead_options_position_pct"] / 100.0
    qty = max(1, int(budget // premium_per_contract))
    notional = qty * premium_per_contract

    # Hard notional ceiling independent of the sizing math above, same
    # reasoning as structured_runner's order seatbelts — options premium
    # is the ENTIRE amount at risk (unlike stock, there's no partial-loss
    # assumption), so this cap matters even more here.
    max_notional_pct = float(await get_user_setting(user_id, "max_order_notional_pct", 40.0))
    if notional / equity * 100 > max_notional_pct:
        log.error("pead_options.seatbelt_blocked", run_id=run_id, ticker=ticker,
                 reason=f"notional {notional/equity*100:.1f}% exceeds cap {max_notional_pct:.0f}%")
        await _emit(run_id, {"type": "order_skipped", "reason": "seatbelt_blocked",
                             "message": "Order blocked: premium notional exceeds the account's safety cap."})
        return

    try:
        order = await asyncio.get_running_loop().run_in_executor(
            None, broker.submit_options_order, contract["symbol"], "buy", qty, contract["ask"])
    except Exception as e:
        log.error("pead_options.order_failed", run_id=run_id, symbol=contract["symbol"], error=str(e))
        await _emit(run_id, {"type": "order_failed", "error": str(e)})
        return

    trade_reasoning_json = {
        "engine": OPTIONS_MODEL_LABEL,
        "occ_symbol": contract["symbol"],
        "underlying": ticker,
        "strike": contract["strike"],
        "expiry": contract["expiry"],
        "delta_at_entry": contract["delta"],
        "iv_at_entry": contract.get("iv"),
        "entry_premium": contract["ask"],
        "multiplier": contract["multiplier"],
        "hold_days": int(opt_params["pead_options_hold_days"]),
        "target_gain_pct": opt_params["pead_options_target_gain_pct"],
        "max_loss_pct": opt_params["pead_options_max_loss_pct"],
        "alpaca_order": order,
    }
    async with AsyncSessionLocal() as db:
        trade = Trade(
            id=str(uuid.uuid4()), user_id=user_id, agent_run_id=run_id,
            alpaca_order_id=order.get("id"), ticker=contract["symbol"], side="buy", qty=qty,
            order_type="limit", limit_price=contract["ask"], status="submitted",
            reasoning_json=trade_reasoning_json,
        )
        db.add(trade)
        await db.commit()

    log.info("pead_options.order_placed", run_id=run_id, symbol=contract["symbol"], qty=qty)
    await _emit(run_id, {"type": "order_placed", "ticker": contract["symbol"], "side": "buy",
                         "qty": qty, "order_id": order.get("id"), "status": order.get("status")})

    try:
        from app.api.v1.notifications import save_notification
        await save_notification(
            type="trade_placed",
            title=f"Options trade placed — BUY {contract['symbol']}",
            body=f"PEAD-options: {qty} contract(s) of {ticker} ${contract['strike']:.2f} call "
                f"exp {contract['expiry']} @ ${contract['ask']:.2f}.",
            ticker=ticker, user_id=user_id,
        )
    except Exception:
        pass
