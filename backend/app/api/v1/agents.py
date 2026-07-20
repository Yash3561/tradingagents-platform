import uuid
from datetime import datetime, UTC
import structlog
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, field_validator

from app.core.postgres import get_db
from app.core.auth import require_user
from app.core.rate_limit import enforce_rate_limit
from app.db.models.agent_run import AgentRun
from app.db.models.settings import ALLOWED_LLM_MODELS
from app.agents.structured_runner import run_structured_agent_analysis
from app.agents.contracts import get_all_schemas, get_contract_schema
from app.core.websocket_manager import ws_manager

router = APIRouter()
log = structlog.get_logger()

# Per-user quotas on LLM-spending endpoints (sliding 1h window)
RUNS_PER_HOUR = 30
SCANS_PER_HOUR = 6
OPTIONS_PER_HOUR = 30

TICKER_PATTERN = r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$"


def _check_model(v: str | None) -> str | None:
    if v is not None and v not in ALLOWED_LLM_MODELS:
        raise ValueError(f"model must be one of {sorted(ALLOWED_LLM_MODELS)}")
    return v


class RunRequest(BaseModel):
    ticker: str = Field(pattern=TICKER_PATTERN)
    date: str | None = None        # defaults to today
    debate_rounds: int = Field(default=2, ge=0, le=3)
    model: str = "deepseek-ai/deepseek-v4-flash"
    # flash produces skeleton debates on the senior prompts — pro fills them
    senior_model: str | None = "deepseek-ai/deepseek-v4-pro"
    strategy: str | None = None    # "agents" | "quant" | "intraday" | "earnings"; None = user's strategy_mode setting

    _models_ok = field_validator("model", "senior_model")(_check_model)


class RunResponse(BaseModel):
    run_id: str
    ticker: str
    status: str
    created_at: str


@router.post("/run", response_model=RunResponse)
async def trigger_run(
    body: RunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_user),
):
    await enforce_rate_limit(f"agent_run:{user.id}", RUNS_PER_HOUR, 3600)

    run_id = str(uuid.uuid4())
    analysis_date = body.date or datetime.now(UTC).strftime("%Y-%m-%d")

    from app.db.models.user_settings import get_user_setting
    from app.agents.quant_baseline import run_quant_baseline_analysis, QUANT_MODEL_LABEL
    from app.agents.earnings_pead import run_earnings_pead_analysis, EARNINGS_MODEL_LABEL
    strategy = body.strategy or await get_user_setting(user.id, "strategy_mode", "agents")
    use_quant = strategy == "quant"
    use_earnings = strategy == "earnings"

    model_label = body.model
    if use_quant:
        model_label = QUANT_MODEL_LABEL
    elif use_earnings:
        model_label = EARNINGS_MODEL_LABEL

    run = AgentRun(
        id=run_id,
        user_id=user.id,
        ticker=body.ticker.upper(),
        analysis_date=analysis_date,
        status="pending",
        llm_model=model_label,
        debate_rounds=0 if (use_quant or use_earnings) else body.debate_rounds,
    )
    db.add(run)
    await db.commit()

    if use_quant:
        background_tasks.add_task(
            run_quant_baseline_analysis, run_id, body.ticker.upper(), analysis_date, user.id,
        )
    elif use_earnings:
        background_tasks.add_task(
            run_earnings_pead_analysis, run_id, body.ticker.upper(), analysis_date, user.id,
        )
    else:
        background_tasks.add_task(
            run_structured_agent_analysis, run_id, body.ticker.upper(), analysis_date,
            body.debate_rounds, body.model, body.senior_model, user.id,
        )

    from app.core.analytics import track
    await track("agent_run", user.id, ticker=body.ticker.upper())

    return RunResponse(
        run_id=run_id,
        ticker=body.ticker.upper(),
        status="pending",
        created_at=run.created_at.isoformat(),
    )


@router.get("/runs")
async def list_runs(limit: int = 20, offset: int = 0,
                    db: AsyncSession = Depends(get_db), user=Depends(require_user)):
    from sqlalchemy import select, desc
    result = await db.execute(
        select(AgentRun).where(AgentRun.user_id == user.id)
        .order_by(desc(AgentRun.created_at)).limit(limit).offset(offset)
    )
    runs = result.scalars().all()
    return [
        {
            "run_id": r.id,
            "ticker": r.ticker,
            "status": r.status,
            "decision": r.decision,
            "confidence": r.confidence,
            "analysis_date": r.analysis_date,
            "created_at": r.created_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]


@router.get("/runs/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db), user=Depends(require_user)):
    run = await db.get(AgentRun, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(404, "Run not found")
    return {
        "run_id": run.id,
        "ticker": run.ticker,
        "status": run.status,
        "decision": run.decision,
        "confidence": run.confidence,
        "summary": run.summary,
        "analysis_date": run.analysis_date,
        "debate_log": run.debate_log,
        "reasoning_json": run.reasoning_json,
        "model": run.llm_model,
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "error": run.error,
    }


@router.get("/contracts")
async def list_contracts():
    """
    Returns the JSON schema for every agent's output contract.
    Frontend and agents use this to understand what each stage produces
    without reading source files.
    """
    return get_all_schemas()


@router.get("/contracts/{agent_name}")
async def get_agent_contract(agent_name: str):
    """Return the JSON schema for a specific agent contract."""
    try:
        return get_contract_schema(agent_name)
    except KeyError:
        raise HTTPException(404, f"No contract for agent: '{agent_name}'")


class ScanCriteria(BaseModel):
    """Custom filter criteria applied during pre-screen. None = no filter."""
    rsi_min: float | None = None          # e.g. 20 — only RSI above this
    rsi_max: float | None = None          # e.g. 35 — only oversold stocks
    min_volume_ratio: float | None = None # e.g. 1.5 — volume spike minimum
    min_score: float | None = None        # e.g. 60 — minimum opportunity score
    directions: list[str] | None = None  # ["BUY"] or ["SELL"] or ["BUY","SELL"]
    above_ma50: bool | None = None        # True = only stocks above 50d MA
    above_ma200: bool | None = None       # True = only stocks above 200d MA
    macd_bullish: bool | None = None      # True = only MACD bullish crossover
    min_mom_1w: float | None = None       # e.g. 2.0 — min 1-week momentum %
    max_mom_1w: float | None = None       # e.g. -2.0 — max (for oversold scans)


class ScanRequest(BaseModel):
    model: str = "deepseek-ai/deepseek-v4-flash"
    senior_model: str | None = "deepseek-ai/deepseek-v4-pro"
    max_candidates: int = Field(default=8, ge=1, le=10)
    watchlist: list[str] | None = Field(default=None, max_length=60)
    criteria: ScanCriteria | None = None

    _models_ok = field_validator("model", "senior_model")(_check_model)


@router.post("/scan")
async def trigger_scan(body: ScanRequest, background_tasks: BackgroundTasks,
                       user=Depends(require_user)):
    """
    Trigger a full market scan:
    1. Pre-screen 40+ stocks with technical analysis (free/fast)
    2. Run AI pipeline on top candidates
    3. Auto-execute approved trades on Alpaca paper account
    Returns scan_id for polling or use SSE to track progress.
    """
    await enforce_rate_limit(f"agent_scan:{user.id}", SCANS_PER_HOUR, 3600)

    import uuid as _uuid
    scan_id = str(_uuid.uuid4())

    from app.core.analytics import track
    await track("scan_run", user.id, max_candidates=body.max_candidates)

    async def _run():
        from app.workers.scanner import run_market_scan
        try:
            result = await run_market_scan(
                model=body.model,
                senior_model=body.senior_model,
                watchlist=body.watchlist,
                max_candidates=body.max_candidates,
                scan_id=scan_id,
                criteria=body.criteria.model_dump(exclude_none=True) if body.criteria else None,
                user_id=user.id,
            )
            await ws_manager.broadcast(f"scan:{scan_id}", {
                "type": "scan_completed",
                "scan_id": scan_id,
                **result,
            })
        except Exception as e:
            await ws_manager.broadcast(f"scan:{scan_id}", {
                "type": "scan_error",
                "scan_id": scan_id,
                "error": str(e),
            })

    background_tasks.add_task(_run)
    return {"scan_id": scan_id, "status": "started"}


@router.get("/scan/prescreen")
async def prescreen_only():
    """
    Run only the free technical pre-screen on all watchlist stocks.
    No Claude calls — instant results (~10s for 40 stocks).
    """
    import asyncio
    from app.workers.scanner import WATCHLIST, _screen_ticker
    loop = asyncio.get_running_loop()

    def _run_all():
        results = []
        for t in WATCHLIST:
            r = _screen_ticker(t)
            if r:
                results.append(r)
        return sorted(results, key=lambda x: x["score"], reverse=True)

    results = await loop.run_in_executor(None, _run_all)
    return results


class OptionsRequest(BaseModel):
    ticker: str = Field(pattern=TICKER_PATTERN)
    strategy: str = "directional"       # "directional", "earnings", "hedge"
    expiry_preference: str = "2weeks"   # "1week", "2weeks", "1month", "3months"


def _norm_cdf(x: float) -> float:
    import math
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_delta(spot: float, strike: float, t_years: float, r: float, sigma: float, is_call: bool) -> float:
    """Black-Scholes delta. yfinance's chain has no delta column, and every
    other field here (strike, premium, IV) is real chain data — this is the
    one number that's genuinely computed rather than invented, from real
    inputs, not asked of an LLM."""
    import math
    if t_years <= 0 or sigma <= 0:
        return 1.0 if (is_call and spot > strike) else (-1.0 if not is_call and spot < strike else 0.0)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma ** 2) * t_years) / (sigma * math.sqrt(t_years))
    return _norm_cdf(d1) if is_call else _norm_cdf(d1) - 1.0


def _bs_price(spot: float, strike: float, t_years: float, r: float, sigma: float, is_call: bool) -> float:
    import math
    if t_years <= 0:
        return max(0.0, spot - strike) if is_call else max(0.0, strike - spot)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma ** 2) * t_years) / (sigma * math.sqrt(t_years))
    d2 = d1 - sigma * math.sqrt(t_years)
    if is_call:
        return spot * _norm_cdf(d1) - strike * math.exp(-r * t_years) * _norm_cdf(d2)
    return strike * math.exp(-r * t_years) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


RISK_FREE_RATE = 0.045  # approximate — this tool is a screener, not a pricing engine


@router.post("/options/analyze")
async def analyze_options(body: OptionsRequest, background_tasks: BackgroundTasks,
                          user=Depends(require_user)):
    """
    Options analysis: technicals decide direction (LLM's job — pattern
    recognition from price action), then a REAL listed contract is selected
    from the live chain and every number reported (strike, expiry, premium,
    max risk, delta, IV) comes from that real contract or is computed from
    it via Black-Scholes — never invented by the LLM.

    2026-07-20 incident: the previous version asked the LLM to also invent
    strike_price/max_risk_pct/delta_estimate/target_return_pct as free-form
    "estimates" with no real chain data in its prompt at all. It produced a
    MSFT $410C 2026-07-24 recommendation with "Max Risk 0.0%" — the real
    listed contract's actual ask was $0.01 (a deep-OTM, 4-days-to-expiry
    near-worthless option, correctly cheap but not a clean 1%-risk play).
    A user nearly acted on it. max_risk_pct=0.0 is impossible for any real
    long option position — that was the tell.
    """
    await enforce_rate_limit(f"options_analyze:{user.id}", OPTIONS_PER_HOUR, 3600)
    import json as _json
    import math
    from datetime import date as _date
    from concurrent.futures import ThreadPoolExecutor
    from app.config import get_settings

    ticker = body.ticker.strip().upper()
    if not ticker:
        raise HTTPException(400, "ticker is required")

    settings = get_settings()
    target_days = {"1week": 7, "2weeks": 14, "1month": 30, "3months": 90}.get(body.expiry_preference, 14)

    # ── Fetch market data + the REAL options chain synchronously ───────────────
    def _fetch_market_data():
        import yfinance as yf
        import numpy as np
        from app.core.market_data import get_daily_bars

        # Alpaca-first, yfinance-fallback — same data layer the rest of the
        # platform uses since the 2026-07-17 outage post-mortem (Yahoo rate
        # limits Render's shared egress IP). Only the options CHAIN itself
        # still has to go through yfinance below (Alpaca's free tier has no
        # options data) — that dependency can't be removed the same way.
        hist = get_daily_bars(ticker, days=90)
        if hist is None or hist.empty:
            raise ValueError(f"No price data for {ticker}")

        t = yf.Ticker(ticker)
        current_price = float(hist["Close"].iloc[-1])

        # RSI-14
        closes = hist["Close"]
        delta = closes.diff().dropna()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi = float((100 - 100 / (1 + rs)).iloc[-1])

        # MACD
        ema12 = closes.ewm(span=12).mean()
        ema26 = closes.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9).mean()
        macd_val = float(macd_line.iloc[-1])
        macd_sig = float(signal_line.iloc[-1])
        macd_bullish = macd_val > macd_sig

        # Momentum
        week1_return = float((closes.iloc[-1] / closes.iloc[-5] - 1) * 100) if len(closes) >= 5 else 0.0
        month1_return = float((closes.iloc[-1] / closes.iloc[-21] - 1) * 100) if len(closes) >= 21 else 0.0

        # Historical vol (used for the LLM's context only, not for pricing)
        log_returns = np.log(closes / closes.shift(1)).dropna()
        hist_vol = float(log_returns.rolling(20).std().iloc[-1] * math.sqrt(252) * 100)

        # Soft-fail: this is the one call in this function still on yfinance
        # (no Alpaca options data on the free tier). Yahoo rate-limits
        # Render's shared egress IP periodically (same root cause as the
        # 2026-07-17 outage) - when it does, the directional judgment below
        # (now running on reliable Alpaca price data) can still complete;
        # only real-contract selection has to sit out. A hard failure here
        # used to take the whole analysis down with it.
        expiries: list[str] = []
        chain_expiry = None
        try:
            expiries = list(t.options)
            if expiries:
                today = _date.today()
                chain_expiry = min(
                    expiries,
                    key=lambda e: abs((_date.fromisoformat(e) - today).days - target_days))
        except Exception as e:
            log.warning("options.chain_expiry_unavailable", ticker=ticker, error=str(e)[:150])

        return {
            "current_price": current_price,
            "rsi_14": round(rsi, 1),
            "macd_bullish": macd_bullish,
            "macd_value": round(macd_val, 4),
            "macd_signal": round(macd_sig, 4),
            "week1_return_pct": round(week1_return, 2),
            "month1_return_pct": round(month1_return, 2),
            "hist_vol_pct": round(hist_vol, 1),
            "nearest_expiries": expiries[:5],
            "chain_expiry": chain_expiry,
        }

    loop = __import__("asyncio").get_running_loop()
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            mkt = await loop.run_in_executor(ex, _fetch_market_data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Market data fetch failed: {e}")

    # No hard-fail here: chain_expiry can legitimately be unavailable (Yahoo
    # rate-limiting Render's IP) while the Alpaca-sourced technicals below
    # are still perfectly good — the LLM can still give a directional read.
    # Contract selection just gets skipped further down if this is None.

    # ── Ask the LLM ONLY for direction — the thing it can actually judge ───────
    strategy_desc = {
        "directional": "directional momentum (bet on the trend continuing)",
        "earnings": "earnings play (position around upcoming earnings event)",
        "hedge": "hedge an existing long position (buy protective puts or collar)",
    }.get(body.strategy, "directional momentum")

    system_prompt = (
        "You are an options trading analyst. Judge ONLY the directional thesis — "
        "whether the technical setup supports a CALL (bullish), PUT (bearish), or "
        "NO_PLAY (unclear/poor setup). Do NOT estimate strike prices, premiums, "
        "greeks, or returns — you have not been given the options chain, and "
        "guessing those numbers is how a past version of this tool nearly caused "
        "a user to buy a near-worthless contract it invented a fake 0% risk for. "
        "A separate step selects the real listed contract and computes real "
        "risk numbers from it. Your job is direction and reasoning only."
    )
    user_content = (
        f"Judge the directional setup for {ticker}.\n\n"
        f"Strategy requested: {strategy_desc}\n\n"
        f"Market data:\n"
        f"- Current price: ${mkt['current_price']:.2f}\n"
        f"- RSI-14: {mkt['rsi_14']}\n"
        f"- MACD: {'Bullish crossover' if mkt['macd_bullish'] else 'Bearish crossover'} "
        f"(MACD={mkt['macd_value']}, Signal={mkt['macd_signal']})\n"
        f"- 1-week return: {mkt['week1_return_pct']:+.2f}%\n"
        f"- 1-month return: {mkt['month1_return_pct']:+.2f}%\n"
        f"- Historical volatility (20d annualized): {mkt['hist_vol_pct']:.1f}%\n\n"
        "Provide CALL/PUT/NO_PLAY with reasoning and risk warnings."
    )
    tool_schema = {
        "name": "options_direction",
        "description": "Directional judgment only — no pricing numbers",
        "input_schema": {
            "type": "object",
            "required": ["recommendation", "reasoning", "risk_warnings"],
            "properties": {
                "recommendation": {"type": "string", "enum": ["CALL", "PUT", "NO_PLAY"]},
                "reasoning": {"type": "string", "description": "3-5 sentences on the directional thesis"},
                "risk_warnings": {"type": "array", "items": {"type": "string"},
                                  "description": "2-5 risk warnings for this setup"},
            },
        },
    }

    try:
        from openai import OpenAI
        api_key = settings.nvidia_api_key or settings.anthropic_api_key
        base_url = settings.nvidia_base_url if settings.nvidia_api_key else None
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=60.0)
        model_id = settings.llm_model or "deepseek-ai/deepseek-v4-flash"

        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            tools=[{"type": "function", "function": {
                "name": tool_schema["name"],
                "description": tool_schema["description"],
                "parameters": tool_schema["input_schema"],
            }}],
            tool_choice="required",
            max_tokens=768,
            temperature=0.3,
        )
        msg = response.choices[0].message
        if msg.tool_calls:
            direction = _json.loads(msg.tool_calls[0].function.arguments)
        else:
            import re
            raw = msg.content or ""
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if not m:
                raise ValueError("No structured output from model")
            direction = _json.loads(m.group())
    except Exception as e:
        raise HTTPException(502, f"AI analysis failed: {e}")

    recommendation = direction.get("recommendation", "NO_PLAY")
    result = {
        "recommendation": recommendation,
        "reasoning": direction.get("reasoning", ""),
        "risk_warnings": direction.get("risk_warnings", []),
        "strike_price": round(mkt["current_price"], 2),
        "expiry_date": mkt["chain_expiry"],
        "max_risk_pct": 0.0,
        "target_return_pct": 0.0,
        "delta_estimate": 0.0,
        "iv_estimate": 0.0,
        "contract_source": "none — NO_PLAY",
    }
    if recommendation == "NO_PLAY":
        return result

    # ── Select a REAL listed contract and compute REAL risk numbers ────────────
    def _pick_contract():
        import yfinance as yf
        t = yf.Ticker(ticker)
        chain = t.option_chain(mkt["chain_expiry"])
        is_call = recommendation == "CALL"
        legs = (chain.calls if is_call else chain.puts).copy()
        if legs.empty:
            return None

        spot = mkt["current_price"]
        today = _date.today()
        t_years = max((_date.fromisoformat(mkt["chain_expiry"]) - today).days, 1) / 365.0

        # Liquid contracts only — bid==0 means no real buyer, that's the
        # exact "$0.01 lottery ticket" failure mode this rewrite exists to stop.
        liquid = legs[(legs["bid"] > 0) & ((legs["volume"].fillna(0) > 0) | (legs["openInterest"].fillna(0) > 0))]
        if liquid.empty:
            return None

        # Target ~0.35 delta (moderate OTM, defined-risk directional exposure) —
        # compute delta for every liquid strike from ITS OWN real IV, pick closest.
        best_row, best_diff = None, None
        for _, row in liquid.iterrows():
            iv = float(row.get("impliedVolatility") or 0)
            if iv <= 0:
                continue
            d = _bs_delta(spot, float(row["strike"]), t_years, RISK_FREE_RATE, iv, is_call)
            diff = abs(abs(d) - 0.35)
            if best_diff is None or diff < best_diff:
                best_row, best_diff = row, diff
        if best_row is None:
            return None

        premium = float(best_row["ask"]) if best_row["ask"] > 0 else float(best_row["lastPrice"])
        iv = float(best_row["impliedVolatility"])
        strike = float(best_row["strike"])
        delta = _bs_delta(spot, strike, t_years, RISK_FREE_RATE, iv, is_call)

        # Target return: reprice via Black-Scholes if spot moves by the
        # trailing 1-month return magnitude in the favorable direction —
        # a labeled scenario, not a promise.
        move_pct = abs(mkt["month1_return_pct"]) / 100.0
        scenario_spot = spot * (1 + move_pct) if is_call else spot * (1 - move_pct)
        t_at_target = max(t_years - (7 / 365.0), 1 / 365.0)  # assume ~1wk holding period
        scenario_price = _bs_price(scenario_spot, strike, t_at_target, RISK_FREE_RATE, iv, is_call)
        target_return_pct = ((scenario_price / premium) - 1) * 100 if premium > 0 else 0.0

        return {
            "strike": strike, "premium": premium, "iv": iv, "delta": delta,
            "target_return_pct": target_return_pct,
            "volume": int(best_row.get("volume") or 0),
            "open_interest": int(best_row.get("openInterest") or 0),
        }

    if mkt["chain_expiry"] is None:
        contract = None
        chain_unavailable_msg = (
            "Options chain data is temporarily unavailable (Yahoo rate-limiting "
            "Render's shared IP) — directional read only, no real contract "
            "could be selected right now. Try again shortly."
        )
    else:
        chain_unavailable_msg = None
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                contract = await loop.run_in_executor(ex, _pick_contract)
        except Exception as e:
            contract = None
            result["risk_warnings"].append(f"Real chain lookup failed ({e}); showing direction only, no contract.")

    if contract is None:
        result["recommendation"] = "NO_PLAY"
        result["risk_warnings"] = result["risk_warnings"] + [
            chain_unavailable_msg or (
                "No liquid listed contract found near the target delta for this "
                "expiry — the directional thesis may be right but there is no "
                "clean way to express it with real, tradeable liquidity right now."
            )
        ]
        result["reasoning"] += (
            " Downgraded to NO_PLAY: " + (
                chain_unavailable_msg or
                "no real contract with an actual bid and volume/open interest "
                "was found — recommending a contract nobody is actually trading "
                "is how the previous version of this tool produced a fabricated "
                "near-zero-risk number."
            )
        )
        return result

    result.update({
        "strike_price": round(contract["strike"], 2),
        "max_risk_pct": round(contract["premium"] / mkt["current_price"] * 100, 2),
        "target_return_pct": round(contract["target_return_pct"], 1),
        "delta_estimate": round(contract["delta"], 3),
        "iv_estimate": round(contract["iv"], 4),
        "premium_usd": round(contract["premium"], 2),
        "contract_volume": contract["volume"],
        "contract_open_interest": contract["open_interest"],
        "contract_source": "real listed contract — premium/IV/delta computed from live chain",
    })
    return result


@router.get("/options/chain/{ticker}")
async def get_options_chain(ticker: str, expiry_index: int = 0):
    """
    Fetch the live options chain for a ticker from yfinance.
    Returns calls + puts for the selected expiry (default: nearest expiry).
    """
    import asyncio
    import yfinance as yf

    def _fetch():
        t = yf.Ticker(ticker.upper())
        expiries = list(t.options)
        if not expiries:
            return {"expiries": [], "selected_expiry": None, "calls": [], "puts": []}

        idx = min(expiry_index, len(expiries) - 1)
        selected = expiries[idx]
        chain = t.option_chain(selected)

        current_price = None
        try:
            hist = t.history(period="1d", interval="1m")
            if not hist.empty:
                current_price = float(hist["Close"].iloc[-1])
        except Exception:
            pass

        def _row(r, kind):
            return {
                "contractSymbol": r.get("contractSymbol", ""),
                "strike": round(float(r.get("strike", 0)), 2),
                "lastPrice": round(float(r.get("lastPrice", 0)), 2),
                "bid": round(float(r.get("bid", 0)), 2),
                "ask": round(float(r.get("ask", 0)), 2),
                "volume": int(r.get("volume", 0) or 0),
                "openInterest": int(r.get("openInterest", 0) or 0),
                "impliedVolatility": round(float(r.get("impliedVolatility", 0)) * 100, 1),
                "inTheMoney": bool(r.get("inTheMoney", False)),
                "kind": kind,
            }

        calls = [_row(r, "call") for r in chain.calls.to_dict("records")]
        puts = [_row(r, "put") for r in chain.puts.to_dict("records")]

        # Show 5 strikes above and below ATM
        if current_price:
            def _near_atm(rows):
                sorted_rows = sorted(rows, key=lambda x: abs(x["strike"] - current_price))
                atm_strikes = {r["strike"] for r in sorted_rows[:10]}
                return [r for r in rows if r["strike"] in atm_strikes]
            calls = sorted(_near_atm(calls), key=lambda x: x["strike"])
            puts = sorted(_near_atm(puts), key=lambda x: x["strike"])

        return {
            "expiries": expiries[:8],
            "selected_expiry": selected,
            "current_price": current_price,
            "calls": calls,
            "puts": puts,
        }

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _fetch)
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch options chain: {e}")


@router.delete("/runs/{run_id}")
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_db), user=Depends(require_user)):
    run = await db.get(AgentRun, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(404, "Run not found")
    if run.status not in ("pending", "running"):
        raise HTTPException(400, f"Cannot cancel run in status: {run.status}")
    run.status = "cancelled"
    await db.commit()
    await ws_manager.broadcast(f"run:{run_id}", {"type": "status", "status": "cancelled"})
    return {"ok": True}
