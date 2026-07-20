"""
Smart Alerts Engine — proactively detects risk conditions across portfolio.
Returns actionable alerts sorted by severity.
No AI calls — pure technical rules for speed.
"""
from __future__ import annotations
from datetime import datetime, UTC, timedelta
from fastapi import APIRouter, Depends
import structlog

from app.core.auth import require_user
from app.broker.alpaca_client import AlpacaClient
from app.broker.credentials import optional_broker

router = APIRouter()
log = structlog.get_logger()


def _severity_order(a: dict) -> int:
    return {"critical": 0, "warning": 1, "info": 2}.get(a["severity"], 3)


@router.get("/")
async def get_alerts(user=Depends(require_user),
                     broker: AlpacaClient | None = Depends(optional_broker)):
    """
    Scan the user's portfolio for risk conditions and return prioritized alerts.
    Checks: position concentration, stop-loss proximity, momentum divergence,
    earnings proximity, large drawdowns, overextended positions (RSI>75).
    """
    import asyncio
    import yfinance as yf
    from app.core.postgres import AsyncSessionLocal
    from app.db.models.trade import Trade
    from sqlalchemy import select

    alerts = []
    _empty_counts = {"critical": 0, "warning": 0, "info": 0}

    if broker is None:
        return {"alerts": [], "scanned_at": datetime.now(UTC).isoformat(),
                "positions_checked": 0, "equity": 0, "alert_counts": _empty_counts}

    # ── Fetch positions from the user's Alpaca account ──────────────────────
    positions = []
    account = {}
    try:
        loop = asyncio.get_running_loop()
        positions, account = await asyncio.gather(
            loop.run_in_executor(None, broker.get_positions),
            loop.run_in_executor(None, broker.get_account),
        )
    except Exception as e:
        log.warning("alerts.alpaca_failed", error=str(e))
        return {"alerts": [], "scanned_at": datetime.now(UTC).isoformat(),
                "positions_checked": 0, "equity": 0, "alert_counts": _empty_counts,
                "error": str(e)}

    if not positions:
        equity = float(account.get("equity", 0)) if account else 0
        return {"alerts": [], "scanned_at": datetime.now(UTC).isoformat(),
                "positions_checked": 0, "equity": equity, "alert_counts": _empty_counts}

    equity = float(account.get("equity", 100_000))
    total_market_value = sum(float(p.get("market_value", 0)) for p in positions)

    # ── 1. Concentration alerts ─────────────────────────────────────────────
    # Threshold scales with what this account's OWN strategy actually targets
    # per position — a flat 20% for everyone flags every single successful
    # entry on accounts deliberately sized bigger (earnings aggression at
    # 25%, momentum rotation up to ~38% on a top-4 book) as "critical" even
    # when the position is exactly hitting its intended size. That's noise,
    # not signal — a concentration alert should mean "bigger than intended",
    # not "bigger than some other account's default".
    from app.db.models.user_settings import get_user_setting
    strategy_mode = await get_user_setting(user.id, "strategy_mode", "agents")
    if strategy_mode == "earnings":
        target_pct = float(await get_user_setting(user.id, "earnings_position_size_pct", 5.0))
    elif strategy_mode == "momentum":
        target_pct = 40.0  # matches the per-name weight cap in momentum_rotation.py
    else:
        target_pct = float(await get_user_setting(user.id, "max_position_pct", 20.0))
    critical_threshold = target_pct * 1.25   # meaningfully past intended size, not just price drift
    warning_threshold = target_pct * 1.05

    for p in positions:
        ticker = p.get("symbol", "")
        market_value = float(p.get("market_value", 0))
        pct_of_portfolio = market_value / equity * 100 if equity else 0

        if pct_of_portfolio > critical_threshold:
            alerts.append({
                "id": f"concentration_{ticker}",
                "type": "concentration",
                "severity": "critical",
                "ticker": ticker,
                "title": f"{ticker} is {pct_of_portfolio:.1f}% of portfolio",
                "message": f"Position exceeds this account's {target_pct:.0f}% target size by more than 25%. "
                          f"Consider trimming to reduce single-stock risk.",
                "value": round(pct_of_portfolio, 1),
                "threshold": round(critical_threshold, 1),
            })
        elif pct_of_portfolio > warning_threshold:
            alerts.append({
                "id": f"concentration_{ticker}",
                "type": "concentration",
                "severity": "warning",
                "ticker": ticker,
                "title": f"{ticker} at {pct_of_portfolio:.1f}% of portfolio",
                "message": f"Above this account's {target_pct:.0f}% target position size. Monitor closely.",
                "value": round(pct_of_portfolio, 1),
                "threshold": round(warning_threshold, 1),
            })

    # ── 2. Stop-loss proximity + large unrealized loss ──────────────────────
    for p in positions:
        ticker = p.get("symbol", "")
        unrealized_pnl_pct = float(p.get("unrealized_plpc", 0)) * 100
        avg_entry = float(p.get("avg_entry_price", 0))
        current_price = float(p.get("current_price", avg_entry))

        if unrealized_pnl_pct < -5:
            severity = "critical" if unrealized_pnl_pct < -6.5 else "warning"
            alerts.append({
                "id": f"drawdown_{ticker}",
                "type": "drawdown",
                "severity": severity,
                "ticker": ticker,
                "title": f"{ticker} down {abs(unrealized_pnl_pct):.1f}% — approaching stop",
                "message": f"Entry: ${avg_entry:.2f}, Current: ${current_price:.2f}. Default stop-loss at -7%.",
                "value": round(unrealized_pnl_pct, 2),
                "threshold": -7.0,
            })

    # ── 3. Large unrealized gains — consider taking profit ──────────────────
    for p in positions:
        ticker = p.get("symbol", "")
        unrealized_pnl_pct = float(p.get("unrealized_plpc", 0)) * 100
        unrealized_pnl = float(p.get("unrealized_pl", 0))

        if unrealized_pnl_pct > 18:
            alerts.append({
                "id": f"take_profit_{ticker}",
                "type": "take_profit",
                "severity": "info",
                "ticker": ticker,
                "title": f"{ticker} up {unrealized_pnl_pct:.1f}% — near take-profit target",
                "message": f"Unrealized gain: ${unrealized_pnl:+.2f}. Default take-profit at +20%. Consider locking in gains.",
                "value": round(unrealized_pnl_pct, 2),
                "threshold": 20.0,
            })

    # ── 4. RSI overbought/oversold for each position ────────────────────────
    def _check_rsi(tickers_list):
        results = {}
        for ticker in tickers_list:
            try:
                hist = yf.Ticker(ticker).history(period="2mo", interval="1d")
                if len(hist) < 15:
                    continue
                closes = hist["Close"]
                delta = closes.diff().dropna()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain / loss.replace(0, float("nan"))
                rsi = float((100 - 100 / (1 + rs)).iloc[-1])
                results[ticker] = round(rsi, 1)
            except Exception:
                pass
        return results

    loop = asyncio.get_running_loop()
    ticker_list = [p.get("symbol", "") for p in positions]
    rsi_map = await loop.run_in_executor(None, _check_rsi, ticker_list)

    for ticker, rsi in rsi_map.items():
        if rsi > 75:
            alerts.append({
                "id": f"rsi_overbought_{ticker}",
                "type": "rsi",
                "severity": "warning",
                "ticker": ticker,
                "title": f"{ticker} RSI = {rsi} (overbought)",
                "message": f"RSI above 75 suggests the position may be overextended. Momentum often reverts.",
                "value": rsi,
                "threshold": 75,
            })
        elif rsi < 30:
            alerts.append({
                "id": f"rsi_oversold_{ticker}",
                "type": "rsi",
                "severity": "info",
                "ticker": ticker,
                "title": f"{ticker} RSI = {rsi} (oversold)",
                "message": f"RSI below 30 may indicate a mean-reversion opportunity or continued weakness.",
                "value": rsi,
                "threshold": 30,
            })

    # ── 5. Check for stale positions (held >30 days, not profitable) ────────
    async with AsyncSessionLocal() as db:
        cutoff = datetime.now(UTC) - timedelta(days=30)
        result = await db.execute(
            select(Trade)
            .where(Trade.user_id == user.id)
            .where(Trade.status.in_(["filled", "submitted"]))
            .where(Trade.submitted_at <= cutoff)
            .where(Trade.closed_at.is_(None))
        )
        stale_trades = result.scalars().all()

    position_tickers = {p.get("symbol", "") for p in positions}
    for trade in stale_trades:
        if trade.ticker in position_tickers:
            pos = next((p for p in positions if p.get("symbol") == trade.ticker), None)
            if pos:
                pnl_pct = float(pos.get("unrealized_plpc", 0)) * 100
                if pnl_pct < 2:  # Been held 30+ days, barely profitable or underwater
                    alerts.append({
                        "id": f"stale_{trade.ticker}",
                        "type": "stale_position",
                        "severity": "info",
                        "ticker": trade.ticker,
                        "title": f"{trade.ticker} held 30+ days with {pnl_pct:+.1f}% return",
                        "message": "Position has been held over a month with minimal gain. Consider if the thesis still holds.",
                        "value": round(pnl_pct, 2),
                        "threshold": 0,
                    })

    # Sort: critical first, then warning, then info
    alerts.sort(key=_severity_order)

    return {
        "alerts": alerts,
        "scanned_at": datetime.now(UTC).isoformat(),
        "positions_checked": len(positions),
        "equity": round(equity, 2),
        "alert_counts": {
            "critical": len([a for a in alerts if a["severity"] == "critical"]),
            "warning": len([a for a in alerts if a["severity"] == "warning"]),
            "info": len([a for a in alerts if a["severity"] == "info"]),
        },
    }


@router.get("/summary")
async def get_alert_summary(user=Depends(require_user),
                            broker: AlpacaClient | None = Depends(optional_broker)):
    """Quick alert count check — used by header/dashboard for badge."""
    try:
        full = await get_alerts(user=user, broker=broker)
        counts = full.get("alert_counts", {})
        return {
            "total": len(full.get("alerts", [])),
            "critical": counts.get("critical", 0),
            "warning": counts.get("warning", 0),
            "info": counts.get("info", 0),
            "scanned_at": full.get("scanned_at"),
        }
    except Exception as e:
        return {"total": 0, "critical": 0, "warning": 0, "info": 0, "error": str(e)}
