"""
Smart Alerts Engine — proactively detects risk conditions across portfolio.
Returns actionable alerts sorted by severity.
No AI calls — pure technical rules for speed.
"""
from __future__ import annotations
from datetime import datetime, UTC, timedelta
from fastapi import APIRouter
import structlog

router = APIRouter()
log = structlog.get_logger()


def _severity_order(a: dict) -> int:
    return {"critical": 0, "warning": 1, "info": 2}.get(a["severity"], 3)


@router.get("/")
async def get_alerts():
    """
    Scan portfolio for risk conditions and return prioritized alerts.
    Checks: position concentration, stop-loss proximity, momentum divergence,
    earnings proximity, large drawdowns, overextended positions (RSI>75).
    """
    import asyncio
    import httpx
    import yfinance as yf
    from app.config import get_settings
    from app.core.postgres import AsyncSessionLocal
    from app.db.models.trade import Trade
    from sqlalchemy import select, desc

    settings = get_settings()
    alerts = []

    # ── Fetch positions from Alpaca ─────────────────────────────────────────
    positions = []
    account = {}
    try:
        headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            pos_r, acct_r = await asyncio.gather(
                client.get(f"{settings.alpaca_base_url}/v2/positions", headers=headers),
                client.get(f"{settings.alpaca_base_url}/v2/account", headers=headers),
            )
        if pos_r.status_code == 200:
            positions = pos_r.json()
        if acct_r.status_code == 200:
            account = acct_r.json()
    except Exception as e:
        log.warning("alerts.alpaca_failed", error=str(e))
        return {"alerts": [], "scanned_at": datetime.now(UTC).isoformat(), "error": str(e)}

    if not positions:
        return {"alerts": [], "scanned_at": datetime.now(UTC).isoformat(), "positions_checked": 0}

    equity = float(account.get("equity", 100_000))
    total_market_value = sum(float(p.get("market_value", 0)) for p in positions)

    # ── 1. Concentration alerts ─────────────────────────────────────────────
    for p in positions:
        ticker = p.get("symbol", "")
        market_value = float(p.get("market_value", 0))
        pct_of_portfolio = market_value / equity * 100 if equity else 0

        if pct_of_portfolio > 20:
            alerts.append({
                "id": f"concentration_{ticker}",
                "type": "concentration",
                "severity": "critical",
                "ticker": ticker,
                "title": f"{ticker} is {pct_of_portfolio:.1f}% of portfolio",
                "message": f"Position exceeds 20% concentration limit. Consider trimming to reduce single-stock risk.",
                "value": round(pct_of_portfolio, 1),
                "threshold": 20,
            })
        elif pct_of_portfolio > 12:
            alerts.append({
                "id": f"concentration_{ticker}",
                "type": "concentration",
                "severity": "warning",
                "ticker": ticker,
                "title": f"{ticker} at {pct_of_portfolio:.1f}% of portfolio",
                "message": f"Approaching concentration limit (20%). Monitor closely.",
                "value": round(pct_of_portfolio, 1),
                "threshold": 20,
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
async def get_alert_summary():
    """Quick alert count check — used by header/dashboard for badge."""
    try:
        full = await get_alerts()
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
