import uuid
from datetime import datetime, UTC
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
    senior_model: str | None = "deepseek-ai/deepseek-v4-flash"
    strategy: str | None = None    # "agents" | "quant"; None = user's strategy_mode setting

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
    strategy = body.strategy or await get_user_setting(user.id, "strategy_mode", "agents")
    use_quant = strategy == "quant"

    run = AgentRun(
        id=run_id,
        user_id=user.id,
        ticker=body.ticker.upper(),
        analysis_date=analysis_date,
        status="pending",
        llm_model=QUANT_MODEL_LABEL if use_quant else body.model,
        debate_rounds=0 if use_quant else body.debate_rounds,
    )
    db.add(run)
    await db.commit()

    if use_quant:
        background_tasks.add_task(
            run_quant_baseline_analysis, run_id, body.ticker.upper(), analysis_date, user.id,
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
    senior_model: str | None = "deepseek-ai/deepseek-v4-flash"
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


@router.post("/options/analyze")
async def analyze_options(body: OptionsRequest, background_tasks: BackgroundTasks,
                          user=Depends(require_user)):
    """
    Options analysis endpoint.
    Fetches market data (yfinance), then runs a structured AI analysis via NIM/DeepSeek
    to recommend CALL, PUT, or NO_PLAY with full risk/greek details.
    """
    await enforce_rate_limit(f"options_analyze:{user.id}", OPTIONS_PER_HOUR, 3600)
    import json as _json
    import math
    from concurrent.futures import ThreadPoolExecutor
    from app.config import get_settings

    ticker = body.ticker.strip().upper()
    if not ticker:
        raise HTTPException(400, "ticker is required")

    settings = get_settings()

    # ── Fetch market data synchronously in thread executor ─────────────────────
    def _fetch_market_data():
        import yfinance as yf
        import numpy as np

        t = yf.Ticker(ticker)
        hist = t.history(period="3mo")
        if hist.empty:
            raise ValueError(f"No price data for {ticker}")

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

        # Historical vol → IV estimate
        log_returns = np.log(closes / closes.shift(1)).dropna()
        hist_vol = float(log_returns.rolling(20).std().iloc[-1] * math.sqrt(252) * 100)

        # Options chain IV
        iv_estimate = hist_vol  # fallback
        expiries = []
        try:
            expiries = list(t.options)
            if expiries:
                chain = t.option_chain(expiries[0])
                atm_calls = chain.calls.copy()
                atm_calls["dist"] = (atm_calls["strike"] - current_price).abs()
                atm_row = atm_calls.sort_values("dist").iloc[0]
                if atm_row.get("impliedVolatility", 0) > 0:
                    iv_estimate = float(atm_row["impliedVolatility"]) * 100
        except Exception:
            pass

        return {
            "current_price": current_price,
            "rsi_14": round(rsi, 1),
            "macd_bullish": macd_bullish,
            "macd_value": round(macd_val, 4),
            "macd_signal": round(macd_sig, 4),
            "week1_return_pct": round(week1_return, 2),
            "month1_return_pct": round(month1_return, 2),
            "hist_vol_pct": round(hist_vol, 1),
            "iv_estimate_pct": round(iv_estimate, 1),
            "nearest_expiries": expiries[:5],
        }

    loop = __import__("asyncio").get_running_loop()
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            mkt = await loop.run_in_executor(ex, _fetch_market_data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Market data fetch failed: {e}")

    # ── Build AI prompt ────────────────────────────────────────────────────────
    strategy_desc = {
        "directional": "directional momentum (bet on the trend continuing)",
        "earnings": "earnings play (position around upcoming earnings event)",
        "hedge": "hedge an existing long position (buy protective puts or collar)",
    }.get(body.strategy, "directional momentum")

    expiry_map = {"1week": "~7 days", "2weeks": "~14 days", "1month": "~30 days", "3months": "~90 days"}
    expiry_desc = expiry_map.get(body.expiry_preference, "~14 days")

    system_prompt = (
        "You are an expert options trader with 20 years of experience. "
        "Analyze whether to buy a CALL, PUT, or avoid options entirely (NO_PLAY). "
        "Base your recommendation on technical momentum, implied volatility, and risk/reward. "
        "Always prefer defined-risk strategies (buying options only — never naked selling). "
        "Be specific: give a real strike price and expiry date. "
        "If IV is elevated (>40%), reduce position sizing and widen strikes. "
        "If the setup is unclear or risk/reward is poor, recommend NO_PLAY."
    )

    user_content = (
        f"Analyze options for {ticker}.\n\n"
        f"Strategy requested: {strategy_desc}\n"
        f"Preferred expiry: {expiry_desc}\n\n"
        f"Market data:\n"
        f"- Current price: ${mkt['current_price']:.2f}\n"
        f"- RSI-14: {mkt['rsi_14']}\n"
        f"- MACD: {'Bullish crossover' if mkt['macd_bullish'] else 'Bearish crossover'} "
        f"(MACD={mkt['macd_value']}, Signal={mkt['macd_signal']})\n"
        f"- 1-week return: {mkt['week1_return_pct']:+.2f}%\n"
        f"- 1-month return: {mkt['month1_return_pct']:+.2f}%\n"
        f"- Historical volatility (20d annualized): {mkt['hist_vol_pct']:.1f}%\n"
        f"- Implied volatility estimate: {mkt['iv_estimate_pct']:.1f}%\n"
        f"- Available expiries: {', '.join(mkt['nearest_expiries'][:3]) if mkt['nearest_expiries'] else 'unknown'}\n\n"
        "Provide your structured recommendation."
    )

    # ── Tool schema ────────────────────────────────────────────────────────────
    tool_schema = {
        "name": "options_recommendation",
        "description": "Structured options trading recommendation",
        "input_schema": {
            "type": "object",
            "required": [
                "recommendation", "strike_price", "expiry_date",
                "max_risk_pct", "target_return_pct", "reasoning",
                "delta_estimate", "iv_estimate", "risk_warnings"
            ],
            "properties": {
                "recommendation": {
                    "type": "string",
                    "enum": ["CALL", "PUT", "NO_PLAY"],
                    "description": "Whether to buy a CALL, PUT, or avoid options entirely"
                },
                "strike_price": {
                    "type": "number",
                    "description": "Recommended strike price (use current price if NO_PLAY)"
                },
                "expiry_date": {
                    "type": "string",
                    "description": "Recommended expiry date as YYYY-MM-DD string"
                },
                "max_risk_pct": {
                    "type": "number",
                    "description": "Option premium as % of stock price (the max you can lose)"
                },
                "target_return_pct": {
                    "type": "number",
                    "description": "Expected % return on the option premium if thesis plays out"
                },
                "reasoning": {
                    "type": "string",
                    "description": "Detailed AI reasoning for the recommendation (3-5 sentences)"
                },
                "delta_estimate": {
                    "type": "number",
                    "description": "Estimated delta for the recommended option (0-1 for calls, -1-0 for puts)"
                },
                "gamma_estimate": {
                    "type": "number",
                    "description": "Estimated gamma (optional)"
                },
                "theta_estimate": {
                    "type": "number",
                    "description": "Estimated daily theta decay in $ per contract (optional, negative)"
                },
                "iv_estimate": {
                    "type": "number",
                    "description": "Implied volatility estimate as a decimal (e.g. 0.35 = 35%)"
                },
                "risk_warnings": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of 2-5 specific risk warnings for this trade"
                },
            },
        },
    }

    # ── Call NIM/DeepSeek ──────────────────────────────────────────────────────
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
            max_tokens=1024,
            temperature=0.3,
        )

        msg = response.choices[0].message
        if msg.tool_calls:
            result = _json.loads(msg.tool_calls[0].function.arguments)
        else:
            # Fallback: parse JSON from content if tool_calls is empty
            import re
            raw = msg.content or ""
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if not m:
                raise ValueError("No structured output from model")
            result = _json.loads(m.group())

    except Exception as e:
        raise HTTPException(502, f"AI analysis failed: {e}")

    # Normalise iv_estimate — ensure it's a decimal fraction (not %)
    iv_raw = float(result.get("iv_estimate", mkt["iv_estimate_pct"] / 100))
    if iv_raw > 5:  # was passed as % like 35.0 instead of 0.35
        iv_raw = iv_raw / 100
    result["iv_estimate"] = round(iv_raw, 4)

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
