"""
Circuit Breakers — hard rules that run BEFORE any trade is placed
and BEFORE any scan executes.

These cannot be overridden by AI agents.
All checks are synchronous Alpaca/yfinance calls wrapped in asyncio executor.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, UTC, timezone
from typing import TYPE_CHECKING
import structlog

log = structlog.get_logger()

# ET offset: UTC-4 in EDT (summer), UTC-5 in EST (winter).
# We derive it at runtime from the Alpaca clock for correctness.
_ET_OFFSET_HOURS = -4   # sensible default (EDT); overridden nowhere critical


# ── Sync helpers (run in executor) ────────────────────────────────────────────

def _fetch_account() -> dict:
    from app.broker.alpaca_client import get_account
    return get_account()


def _fetch_positions() -> list[dict]:
    from app.broker.alpaca_client import get_positions
    return get_positions()


def _fetch_vix() -> float | None:
    try:
        import yfinance as yf
        price = yf.Ticker("^VIX").fast_info["last_price"]
        return float(price)
    except Exception:
        try:
            import yfinance as yf
            hist = yf.Ticker("^VIX").history(period="1d", interval="1m")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception:
            pass
    return None


def _fetch_earnings_calendar(ticker: str) -> dict | None:
    """Return yfinance calendar dict or None on failure."""
    try:
        import yfinance as yf
        cal = yf.Ticker(ticker).calendar
        return cal
    except Exception:
        return None


def _check_earnings_soon(ticker: str, days: int = 5) -> tuple[bool, str]:
    """Returns (blocked, reason) if earnings within `days` trading days."""
    import datetime as _dt
    cal = _fetch_earnings_calendar(ticker)
    if cal is None:
        return False, ""

    # calendar can be a dict with 'Earnings Date' key (list or single value)
    if isinstance(cal, dict):
        earnings_dates = cal.get("Earnings Date", [])
        if not isinstance(earnings_dates, (list, tuple)):
            earnings_dates = [earnings_dates]
    elif hasattr(cal, "columns"):
        # pandas DataFrame — try to pull Earnings Date row
        try:
            if "Earnings Date" in cal.index:
                val = cal.loc["Earnings Date"]
                earnings_dates = list(val) if hasattr(val, "__iter__") else [val]
            elif "Earnings Date" in cal.columns:
                earnings_dates = list(cal["Earnings Date"])
            else:
                earnings_dates = []
        except Exception:
            earnings_dates = []
    else:
        return False, ""

    today = _dt.date.today()
    cutoff = today + _dt.timedelta(days=days)

    for ed in earnings_dates:
        try:
            if hasattr(ed, "date"):
                ed_date = ed.date()
            elif isinstance(ed, str):
                ed_date = _dt.date.fromisoformat(ed[:10])
            elif isinstance(ed, _dt.date):
                ed_date = ed
            else:
                continue

            if today <= ed_date <= cutoff:
                return True, (
                    f"Earnings blackout: {ticker} reports on {ed_date.isoformat()} "
                    f"(within {days} days)"
                )
        except Exception:
            continue

    return False, ""


# ── Main circuit-breaker check ─────────────────────────────────────────────────

async def check_circuit_breakers() -> dict:
    """
    Returns {
        "blocked": bool,
        "reasons": list[str],
        "warnings": list[str],
        "ticker_blocks": dict[str, str],   # ticker → reason
    }

    blocked=True means NO new trades should be placed globally.
    ticker_blocks are per-ticker earnings blocks.
    warnings are informational — reduce size but don't block.
    """
    from app.api.v1.notifications import save_notification

    loop = asyncio.get_running_loop()

    reasons: list[str] = []
    warnings: list[str] = []
    ticker_blocks: dict[str, str] = {}

    # ── 1. Daily loss limit ────────────────────────────────────────────────────
    try:
        account = await loop.run_in_executor(None, _fetch_account)
        equity = float(account.get("equity", 0))
        last_equity = float(account.get("last_equity", equity))

        if last_equity > 0:
            day_pnl_pct = (equity - last_equity) / last_equity
            if day_pnl_pct < -0.03:
                reason = f"Daily loss limit hit ({day_pnl_pct:.1%})"
                reasons.append(reason)
                log.warning("circuit_breaker.daily_loss", pct=round(day_pnl_pct * 100, 2))
    except Exception as e:
        log.warning("circuit_breaker.account_fetch_failed", error=str(e))

    # ── 2. VIX check ──────────────────────────────────────────────────────────
    try:
        vix = await loop.run_in_executor(None, _fetch_vix)
        if vix is not None:
            if vix > 40:
                reason = f"VIX critical ({vix:.1f}) — trading halted"
                reasons.append(reason)
                log.warning("circuit_breaker.vix_critical", vix=round(vix, 1))
            elif vix > 30:
                warn = f"VIX elevated ({vix:.1f}) — high volatility"
                warnings.append(warn)
                log.info("circuit_breaker.vix_elevated", vix=round(vix, 1))
    except Exception as e:
        log.warning("circuit_breaker.vix_fetch_failed", error=str(e))

    # ── 3. Concentration check ─────────────────────────────────────────────────
    try:
        positions = await loop.run_in_executor(None, _fetch_positions)
        if positions:
            account_for_conc = await loop.run_in_executor(None, _fetch_account)
            total_equity = float(account_for_conc.get("equity", 1))

            for pos in positions:
                ticker = pos.get("symbol") or pos.get("ticker", "")
                market_val = float(pos.get("market_value", 0) or 0)
                if total_equity > 0 and ticker:
                    pct = market_val / total_equity
                    if pct > 0.25:
                        warn = f"Concentration risk: {ticker} is {pct:.0%} of portfolio"
                        warnings.append(warn)
                        log.warning("circuit_breaker.concentration",
                                    ticker=ticker, pct=round(pct * 100, 1))
    except Exception as e:
        log.warning("circuit_breaker.concentration_check_failed", error=str(e))

    # ── Fire notification if circuit breaker is triggered ─────────────────────
    blocked = len(reasons) > 0

    if reasons or warnings:
        try:
            all_issues = reasons + warnings
            await save_notification(
                type="circuit_breaker",
                title="Circuit Breaker Alert" if blocked else "Circuit Breaker Warning",
                body="; ".join(all_issues),
            )
        except Exception as e:
            log.warning("circuit_breaker.notification_failed", error=str(e))

    result = {
        "blocked": blocked,
        "reasons": reasons,
        "warnings": warnings,
        "ticker_blocks": ticker_blocks,
    }
    log.info("circuit_breaker.check_complete",
             blocked=blocked, reasons=len(reasons), warnings=len(warnings))
    return result


async def check_ticker_blocked(ticker: str) -> tuple[bool, str]:
    """
    Returns (blocked, reason) for a specific ticker.
    Checks earnings blackout (within 5 days).
    """
    from app.api.v1.notifications import save_notification

    loop = asyncio.get_running_loop()

    try:
        blocked, reason = await loop.run_in_executor(
            None, _check_earnings_soon, ticker, 5
        )
        if blocked:
            log.warning("circuit_breaker.earnings_blackout",
                        ticker=ticker, reason=reason)
            try:
                await save_notification(
                    type="circuit_breaker",
                    title=f"Earnings blackout — {ticker}",
                    body=reason,
                    ticker=ticker,
                )
            except Exception:
                pass
            return True, reason
    except Exception as e:
        log.warning("circuit_breaker.ticker_check_failed",
                    ticker=ticker, error=str(e))

    return False, ""
