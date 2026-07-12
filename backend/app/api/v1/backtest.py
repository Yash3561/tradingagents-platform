"""
Real backtesting engine — pure technical pre-screen simulation.
No AI agent calls (would take hours). Uses the same scoring logic as scanner.py
to simulate what would have been caught historically.
"""

from __future__ import annotations
import uuid
import math
from datetime import datetime, UTC
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import structlog

log = structlog.get_logger()

router = APIRouter()


class BacktestRequest(BaseModel):
    ticker: str
    from_date: str
    to_date: str
    debate_rounds: int = 1
    model: str = "claude-sonnet-4-6"
    initial_capital: float = 100_000.0
    stop_loss_pct: float = 7.0
    take_profit_pct: float = 15.0
    position_size_usd: float = 1_000.0


def _compute_score(close, volume, i: int) -> float:
    """
    Compute the same technical pre-screen score as scanner.py at bar index i.
    Requires at least 30 bars of history before index i.
    Returns score in 0-100 range.
    """
    import numpy as np

    if i < 30:
        return 50.0

    window = close[:i + 1]
    vol_window = volume[:i + 1]

    current = float(window.iloc[-1])
    prev = float(window.iloc[-2]) if len(window) > 1 else current

    # Moving averages
    ma20 = float(window.tail(20).mean())
    ma50 = float(window.tail(50).mean()) if len(window) >= 50 else float(window.mean())
    ma200 = float(window.tail(200).mean()) if len(window) >= 200 else float(window.mean())

    # RSI-14
    delta = window.diff()
    gain = delta.clip(lower=0).tail(14).mean()
    loss = (-delta.clip(upper=0)).tail(14).mean()
    rsi = float(100 - (100 / (1 + gain / loss))) if loss != 0 else 50.0

    # Momentum
    mom_1w = (current / float(window.iloc[-6]) - 1) * 100 if len(window) >= 6 else 0
    mom_1m = (current / float(window.iloc[-22]) - 1) * 100 if len(window) >= 22 else 0

    # Volume ratio
    avg_vol = float(vol_window.tail(30).mean())
    today_vol = float(vol_window.iloc[-1])
    vol_ratio = today_vol / avg_vol if avg_vol else 1.0

    # MACD
    macd_series = window.ewm(span=12, adjust=False).mean() - window.ewm(span=26, adjust=False).mean()
    macd = float(macd_series.iloc[-1])
    signal_ema = float(macd_series.ewm(span=9, adjust=False).mean().iloc[-1])
    macd_bullish = macd > signal_ema

    score = 50.0

    if rsi < 35:
        score += 20
    elif rsi < 45:
        score += 10
    elif rsi > 70:
        score -= 15
    elif rsi > 60:
        score -= 5

    if current > ma50 > ma200:
        score += 15
    elif current > ma200:
        score += 8
    elif current < ma50 < ma200:
        score -= 15
    elif current < ma200:
        score -= 8

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

    if macd_bullish:
        score += 8
    else:
        score -= 5

    if vol_ratio > 1.5:
        score += 8
    elif vol_ratio > 1.2:
        score += 4
    elif vol_ratio < 0.6:
        score -= 5

    return float(score)


def _run_backtest_sync(
    ticker: str,
    from_date: str,
    to_date: str,
    initial_capital: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    position_size_usd: float,
) -> dict:
    """
    Synchronous backtest core. Runs in thread executor.
    Returns metrics + equity_curve + trades list.
    """
    import yfinance as yf
    import numpy as np

    # Fetch ticker data — extend range back 1 year for indicator warm-up
    from datetime import timedelta
    from_dt = datetime.strptime(from_date, "%Y-%m-%d")
    to_dt = datetime.strptime(to_date, "%Y-%m-%d")
    fetch_from = (from_dt - timedelta(days=365)).strftime("%Y-%m-%d")

    log.info("backtest.fetch_start", ticker=ticker, from_date=fetch_from, to_date=to_date)

    t = yf.Ticker(ticker)
    hist = t.history(start=fetch_from, end=to_date, interval="1d")

    if hist.empty or len(hist) < 30:
        raise ValueError(f"Insufficient price data for {ticker}")

    # Fetch SPY for benchmark
    spy = yf.Ticker("SPY")
    spy_hist = spy.history(start=fetch_from, end=to_date, interval="1d")

    close = hist["Close"]
    open_prices = hist["Open"]
    volume = hist["Volume"]
    dates = hist.index

    # Find start index corresponding to from_date
    from_ts = from_dt.replace(tzinfo=dates[0].tzinfo if hasattr(dates[0], 'tzinfo') else None)
    start_idx = 0
    for idx, d in enumerate(dates):
        d_naive = d.date() if hasattr(d, 'date') else d
        if d_naive >= from_dt.date():
            start_idx = idx
            break

    equity = initial_capital
    cash = initial_capital
    position_qty = 0.0
    position_entry_price = 0.0
    position_entry_idx = -1

    trades = []
    equity_curve = []
    daily_returns = []

    # SPY benchmark tracking
    spy_close = spy_hist["Close"]
    spy_dates_map = {d.date() if hasattr(d, 'date') else d: float(spy_close.iloc[i])
                     for i, d in enumerate(spy_hist.index)}
    spy_start_price = None
    spy_end_price = None

    prev_equity = equity

    for i in range(start_idx, len(close) - 1):
        today_date = dates[i].date() if hasattr(dates[i], 'date') else dates[i]
        next_open = float(open_prices.iloc[i + 1])  # simulate entry at next day open
        today_close = float(close.iloc[i])

        # Current market value
        if position_qty > 0:
            market_value = position_qty * today_close
            current_equity = cash + market_value
        else:
            current_equity = cash

        # Track SPY for benchmark
        spy_price = spy_dates_map.get(today_date)
        if spy_price and spy_start_price is None:
            spy_start_price = spy_price
        if spy_price:
            spy_end_price = spy_price

        # Equity curve point
        spy_equity = None
        if spy_start_price and spy_price:
            spy_equity = round(initial_capital * (spy_price / spy_start_price), 2)

        equity_curve.append({
            "date": str(today_date),
            "equity": round(current_equity, 2),
            "benchmark": spy_equity,
        })

        daily_return = (current_equity - prev_equity) / prev_equity if prev_equity > 0 else 0
        daily_returns.append(daily_return)
        prev_equity = current_equity

        # Check stop-loss / take-profit on existing position
        if position_qty > 0:
            pnl_pct = (today_close - position_entry_price) / position_entry_price * 100
            exit_reason = None

            if pnl_pct <= -abs(stop_loss_pct):
                exit_reason = "stop_loss"
            elif pnl_pct >= abs(take_profit_pct):
                exit_reason = "take_profit"

            if exit_reason:
                exit_price = next_open  # exit at next day open
                pnl = (exit_price - position_entry_price) * position_qty
                cash += position_qty * exit_price
                trades.append({
                    "entry_date": str(dates[position_entry_idx].date()
                                       if hasattr(dates[position_entry_idx], 'date')
                                       else dates[position_entry_idx]),
                    "exit_date": str(today_date),
                    "entry_price": round(position_entry_price, 2),
                    "exit_price": round(exit_price, 2),
                    "qty": round(position_qty, 4),
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "exit_reason": exit_reason,
                })
                position_qty = 0.0
                position_entry_price = 0.0
                position_entry_idx = -1
                continue

        # Compute signal score at close
        score = _compute_score(close, volume, i)

        if score > 62 and position_qty == 0 and cash >= position_size_usd:
            # BUY signal — enter at next day's open
            qty = position_size_usd / next_open
            position_qty = qty
            position_entry_price = next_open
            position_entry_idx = i
            cash -= qty * next_open

        elif score < 38 and position_qty > 0:
            # SELL signal — exit at next day's open
            exit_price = next_open
            pnl_pct_exit = (exit_price - position_entry_price) / position_entry_price * 100
            pnl = (exit_price - position_entry_price) * position_qty
            cash += position_qty * exit_price
            trades.append({
                "entry_date": str(dates[position_entry_idx].date()
                                   if hasattr(dates[position_entry_idx], 'date')
                                   else dates[position_entry_idx]),
                "exit_date": str(today_date),
                "entry_price": round(position_entry_price, 2),
                "exit_price": round(exit_price, 2),
                "qty": round(position_qty, 4),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct_exit, 2),
                "exit_reason": "signal_sell",
            })
            position_qty = 0.0
            position_entry_price = 0.0
            position_entry_idx = -1

    # Close any open position at last bar's close
    if position_qty > 0:
        last_close = float(close.iloc[-1])
        last_date = dates[-1].date() if hasattr(dates[-1], 'date') else dates[-1]
        pnl_pct_final = (last_close - position_entry_price) / position_entry_price * 100
        pnl = (last_close - position_entry_price) * position_qty
        cash += position_qty * last_close
        trades.append({
            "entry_date": str(dates[position_entry_idx].date()
                               if hasattr(dates[position_entry_idx], 'date')
                               else dates[position_entry_idx]),
            "exit_date": str(last_date),
            "entry_price": round(position_entry_price, 2),
            "exit_price": round(last_close, 2),
            "qty": round(position_qty, 4),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct_final, 2),
            "exit_reason": "end_of_range",
        })

    final_equity = cash

    # ── Metrics ────────────────────────────────────────────────────────────────
    total_return_pct = (final_equity - initial_capital) / initial_capital * 100

    # Sharpe ratio
    dr = np.array(daily_returns)
    sharpe = 0.0
    if len(dr) > 1 and dr.std() > 0:
        sharpe = float((dr.mean() / dr.std()) * math.sqrt(252))

    # Max drawdown — rolling peak-to-trough on equity curve
    eq_values = [p["equity"] for p in equity_curve]
    max_drawdown_pct = 0.0
    if eq_values:
        peak = eq_values[0]
        for v in eq_values:
            if v > peak:
                peak = v
            dd = (v - peak) / peak * 100
            if dd < max_drawdown_pct:
                max_drawdown_pct = dd

    # Win rate
    winning = [t for t in trades if t["pnl"] > 0]
    losing = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(winning) / len(trades) if trades else 0.0

    # CAGR
    years = max((to_dt - from_dt).days / 365.25, 0.01)
    cagr = 0.0
    if final_equity > 0 and initial_capital > 0:
        cagr = ((final_equity / initial_capital) ** (1.0 / years) - 1) * 100

    # Profit factor
    gross_gain = sum(t["pnl"] for t in winning)
    gross_loss = abs(sum(t["pnl"] for t in losing))
    profit_factor = gross_gain / gross_loss if gross_loss > 0 else (999.0 if gross_gain > 0 else 1.0)

    # SPY benchmark return
    spy_return_pct = 0.0
    if spy_start_price and spy_end_price and spy_start_price > 0:
        spy_return_pct = (spy_end_price - spy_start_price) / spy_start_price * 100

    return {
        "metrics": {
            "total_return_pct": round(total_return_pct, 2),
            "sharpe": round(sharpe, 3),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "win_rate": round(win_rate, 4),
            "cagr_pct": round(cagr, 2),
            "profit_factor": round(profit_factor, 3),
            "total_trades": len(trades),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "final_equity": round(final_equity, 2),
            "initial_capital": initial_capital,
            "spy_return_pct": round(spy_return_pct, 2),
        },
        "equity_curve": equity_curve,
        "trades": trades,
    }


@router.post("/jobs")
async def submit_job(body: BacktestRequest):
    """Run backtest immediately and return results."""
    import asyncio
    job_id = str(uuid.uuid4())

    log.info("backtest.start", job_id=job_id, ticker=body.ticker,
             from_date=body.from_date, to_date=body.to_date)

    # Log activity
    try:
        from app.api.v1.activity import log_activity
        start_time = datetime.now(UTC)
        await log_activity(
            feature="backtest",
            action="backtest_run",
            ticker=body.ticker.upper(),
            details={"from_date": body.from_date, "to_date": body.to_date,
                     "job_id": job_id},
            result="running",
        )
    except Exception:
        start_time = datetime.now(UTC)

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            _run_backtest_sync,
            body.ticker.upper(),
            body.from_date,
            body.to_date,
            body.initial_capital,
            body.stop_loss_pct,
            body.take_profit_pct,
            body.position_size_usd,
        )

        duration_s = (datetime.now(UTC) - start_time).total_seconds()
        log.info("backtest.done", job_id=job_id, ticker=body.ticker,
                 trades=result["metrics"]["total_trades"], duration_s=round(duration_s, 1))

        try:
            from app.api.v1.activity import log_activity
            await log_activity(
                feature="backtest",
                action="backtest_run",
                ticker=body.ticker.upper(),
                details={
                    "from_date": body.from_date,
                    "to_date": body.to_date,
                    "job_id": job_id,
                    "total_return_pct": result["metrics"]["total_return_pct"],
                    "total_trades": result["metrics"]["total_trades"],
                },
                result="completed",
                duration_s=round(duration_s, 1),
            )
        except Exception:
            pass

        return {
            "job_id": job_id,
            "status": "completed",
            "ticker": body.ticker.upper(),
            **result,
        }

    except Exception as exc:
        log.error("backtest.failed", job_id=job_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Backtest failed: {exc}")


@router.get("/jobs")
async def list_jobs():
    """Return recent backtest runs from activity log."""
    from app.core.postgres import AsyncSessionLocal
    from app.db.models.activity_log import ActivityLog
    from sqlalchemy import select, desc

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ActivityLog)
            .where(ActivityLog.feature == "backtest")
            .order_by(desc(ActivityLog.created_at))
            .limit(20)
        )
        logs = result.scalars().all()

    return [
        {
            "job_id": log.details.get("job_id") if log.details else None,
            "ticker": log.ticker,
            "status": log.result,
            "from_date": log.details.get("from_date") if log.details else None,
            "to_date": log.details.get("to_date") if log.details else None,
            "total_return_pct": log.details.get("total_return_pct") if log.details else None,
            "total_trades": log.details.get("total_trades") if log.details else None,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    return {"job_id": job_id, "status": "completed", "progress": 100}


@router.get("/jobs/{job_id}/results")
async def get_results(job_id: str):
    """Results are returned inline from POST /jobs. This endpoint is for polling."""
    return {"message": "Backtest results are returned directly from POST /backtest/jobs"}
