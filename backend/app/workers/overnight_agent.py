"""
Overnight Agent — "Night Owl"

Fires at 4:30 PM ET every weekday. Does deep research while the market sleeps:
  1. Fetch current Alpaca positions
  2. News sweep for each held ticker
  3. Earnings calendar check (next 7 days)
  4. Today's P&L summary
  5. Pre-screen tomorrow's candidates (top 5 BUY setups)
  6. Build a morning brief via AI (DeepSeek via NVIDIA NIM)
  7. Save as notification + activity log

Runs as a continuous asyncio loop — sleeps until the next 4:30 PM ET window.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta
import structlog

log = structlog.get_logger()

# UTC offsets for ET: -4 (EDT summer), -5 (EST winter).
# We compute dynamically using Python's datetime DST logic.
_FIRE_HOUR_ET = 16       # 4 PM
_FIRE_MINUTE_ET = 30     # :30


def _et_now() -> datetime:
    """Return current datetime in US/Eastern (handles DST automatically)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        # Fallback: assume EDT (UTC-4) — close enough for daily scheduling
        return datetime.now(timezone(timedelta(hours=-4)))


def _seconds_until_next_fire() -> float:
    """Seconds until next 4:30 PM ET on a weekday."""
    now = _et_now()
    today = now.replace(hour=_FIRE_HOUR_ET, minute=_FIRE_MINUTE_ET, second=0, microsecond=0)

    # If we're already past 4:30 PM today, schedule for next weekday
    if now >= today:
        today += timedelta(days=1)

    # Skip weekends
    while today.weekday() >= 5:  # 5=Saturday, 6=Sunday
        today += timedelta(days=1)

    delta = (today - now).total_seconds()
    return max(delta, 0)


def _fetch_positions_sync() -> list[dict]:
    from app.broker.alpaca_client import get_positions
    return get_positions()


def _fetch_account_sync() -> dict:
    from app.broker.alpaca_client import get_account
    return get_account()


def _fetch_ticker_news(ticker: str) -> list[str]:
    """Fetch top 5 headlines for a ticker."""
    try:
        import yfinance as yf
        news = yf.Ticker(ticker).news or []
        headlines = []
        for n in news[:5]:
            content = n.get("content", {})
            title = content.get("title", "") if isinstance(content, dict) else n.get("title", "")
            if not title:
                title = n.get("title", "")
            if title:
                headlines.append(title)
        return headlines
    except Exception as e:
        log.warning("overnight.news_fetch_failed", ticker=ticker, error=str(e))
        return []


def _check_earnings_7d(ticker: str) -> str | None:
    """Returns earnings date string if within 7 days, else None."""
    import datetime as _dt
    try:
        import yfinance as yf
        cal = yf.Ticker(ticker).calendar
        if cal is None:
            return None

        if isinstance(cal, dict):
            dates = cal.get("Earnings Date", [])
            if not isinstance(dates, (list, tuple)):
                dates = [dates]
        elif hasattr(cal, "columns") or hasattr(cal, "index"):
            try:
                if "Earnings Date" in cal.index:
                    val = cal.loc["Earnings Date"]
                    dates = list(val) if hasattr(val, "__iter__") else [val]
                elif "Earnings Date" in cal.columns:
                    dates = list(cal["Earnings Date"])
                else:
                    dates = []
            except Exception:
                dates = []
        else:
            return None

        today = _dt.date.today()
        cutoff = today + _dt.timedelta(days=7)

        for ed in dates:
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
                    return ed_date.isoformat()
            except Exception:
                continue
    except Exception as e:
        log.warning("overnight.earnings_check_failed", ticker=ticker, error=str(e))
    return None


def _prescreen_ticker(ticker: str) -> dict | None:
    """Lightweight technical pre-screen. Returns scored dict or None."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period="6mo", interval="1d")
        if len(hist) < 30:
            return None

        close = hist["Close"]
        current = float(close.iloc[-1])
        ma20 = float(close.tail(20).mean())
        ma50 = float(close.tail(50).mean()) if len(close) >= 50 else ma20

        delta = close.diff()
        gain = delta.clip(lower=0).tail(14).mean()
        loss = (-delta.clip(upper=0)).tail(14).mean()
        rsi = float(100 - (100 / (1 + gain / loss))) if loss != 0 else 50.0

        ema12 = float(close.ewm(span=12, adjust=False).mean().iloc[-1])
        ema26 = float(close.ewm(span=26, adjust=False).mean().iloc[-1])
        macd_bullish = ema12 > ema26

        mom_1w = (current / float(close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
        mom_1m = (current / float(close.iloc[-22]) - 1) * 100 if len(close) >= 22 else 0

        score = 50.0
        if rsi < 35:
            score += 20
        elif rsi < 45:
            score += 10
        elif rsi > 70:
            score -= 15

        if current > ma50 > ma20:
            score += 10
        elif current > ma20:
            score += 5
        elif current < ma50:
            score -= 10

        if mom_1w > 3:
            score += 10
        elif mom_1w < -3:
            score -= 10

        if mom_1m > 8:
            score += 8
        elif mom_1m < -8:
            score -= 8

        if macd_bullish:
            score += 7
        else:
            score -= 4

        return {
            "ticker": ticker,
            "score": round(score, 1),
            "rsi": round(rsi, 1),
            "mom_1w": round(mom_1w, 2),
            "mom_1m": round(mom_1m, 2),
            "macd_bullish": macd_bullish,
            "above_ma50": current > ma50,
            "current_price": round(current, 2),
        }
    except Exception as e:
        log.warning("overnight.prescreen_failed", ticker=ticker, error=str(e))
        return None


OVERNIGHT_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AMD",
    "ASML", "TSM", "AVGO", "ORCL", "CRM", "ADBE", "NFLX", "NOW",
    "PANW", "SNOW", "COIN", "PLTR", "UNH", "LLY", "JPM", "GS",
    "V", "MA", "WMT", "COST", "HD", "SPY",
]


def _run_overnight_research(positions: list[dict], account: dict) -> dict:
    """
    Synchronous research block — runs in thread executor.
    Returns structured research dict.
    """
    # ── News sweep ─────────────────────────────────────────────────────────────
    position_news: dict[str, list[str]] = {}
    earnings_risks: dict[str, str] = {}

    for pos in positions:
        ticker = pos.get("symbol") or pos.get("ticker", "")
        if not ticker:
            continue
        position_news[ticker] = _fetch_ticker_news(ticker)
        ed = _check_earnings_7d(ticker)
        if ed:
            earnings_risks[ticker] = ed

    # ── Today's P&L ────────────────────────────────────────────────────────────
    from app.core.pnl import compute_day_pnl
    equity = float(account.get("equity", 0))
    last_equity = float(account.get("last_equity", 0))
    day_pnl, day_pnl_pct = compute_day_pnl(equity, last_equity)

    # ── Pre-screen tomorrow's candidates ───────────────────────────────────────
    screened = []
    for ticker in OVERNIGHT_WATCHLIST:
        result = _prescreen_ticker(ticker)
        if result and result["score"] > 60:
            screened.append(result)

    screened.sort(key=lambda x: x["score"], reverse=True)
    top_5 = screened[:5]

    return {
        "positions": positions,
        "position_count": len(positions),
        "position_news": position_news,
        "earnings_risks": earnings_risks,
        "day_pnl": round(day_pnl, 2),
        "day_pnl_pct": round(day_pnl_pct, 2),
        "equity": round(equity, 2),
        "top_tomorrow": top_5,
    }


def _build_morning_brief(research: dict, date_str: str) -> str:
    """Call DeepSeek via NIM for a concise morning brief."""
    from openai import OpenAI
    from app.config import get_settings

    settings = get_settings()
    client = OpenAI(
        base_url=settings.nvidia_base_url,
        api_key=settings.nvidia_api_key,
    )

    positions_summary = ", ".join(
        p.get("symbol") or p.get("ticker", "?") for p in research["positions"]
    ) or "None"

    earnings_str = ", ".join(
        f"{t} ({d})" for t, d in research["earnings_risks"].items()
    ) or "None"

    top_buys = ", ".join(
        f"{s['ticker']} (score {s['score']}, RSI {s['rsi']})"
        for s in research["top_tomorrow"]
    ) or "None identified"

    prompt = f"""You are a professional trading morning brief writer. Write a concise 3-4 sentence morning brief for {date_str}.

Data:
- Open positions: {positions_summary}
- Today's P&L: ${research['day_pnl']:+,.2f} ({research['day_pnl_pct']:+.2f}%)
- Earnings risks in next 7 days: {earnings_str}
- Top BUY setups for tomorrow: {top_buys}

Write a professional, actionable brief covering: (1) portfolio health today, (2) earnings risks to watch, (3) top tomorrow setups. Be direct, no fluff. 3-4 sentences max."""

    try:
        response = client.chat.completions.create(
            model="deepseek-ai/deepseek-v4-flash",
            max_tokens=300,
            temperature=0.3,
            messages=[
                {"role": "system", "content": "You are a professional trading floor analyst writing concise morning briefs."},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log.warning("overnight.ai_brief_failed", error=str(e))
        # Fallback to template brief
        return (
            f"Portfolio update for {date_str}: {research['position_count']} open positions, "
            f"day P&L {research['day_pnl_pct']:+.2f}%. "
            f"Earnings caution: {earnings_str}. "
            f"Tomorrow's top setups: {top_buys}."
        )


async def _run_once():
    """Execute one overnight research cycle."""
    from app.api.v1.notifications import save_notification

    loop = asyncio.get_running_loop()
    now_et = _et_now()
    date_str = now_et.strftime("%Y-%m-%d")

    log.info("overnight_agent.firing", date=date_str)

    # Fetch account + positions
    try:
        positions = await loop.run_in_executor(None, _fetch_positions_sync)
        account = await loop.run_in_executor(None, _fetch_account_sync)
    except Exception as e:
        log.error("overnight_agent.fetch_failed", error=str(e))
        return

    # Run research in thread (yfinance is sync)
    try:
        research = await loop.run_in_executor(None, _run_overnight_research, positions, account)
    except Exception as e:
        log.error("overnight_agent.research_failed", error=str(e))
        return

    # Build AI brief
    try:
        brief = await loop.run_in_executor(None, _build_morning_brief, research, date_str)
    except Exception as e:
        log.error("overnight_agent.brief_failed", error=str(e))
        brief = f"Research complete. {research['position_count']} positions. Day P&L: {research['day_pnl_pct']:+.2f}%."

    # Save notification
    try:
        await save_notification(
            type="morning_brief",
            title=f"Morning Brief — {date_str}",
            body=brief,
        )
        log.info("overnight_agent.brief_saved", date=date_str)
    except Exception as e:
        log.error("overnight_agent.save_failed", error=str(e))

    # Save activity log
    try:
        from app.api.v1.activity import log_activity
        await log_activity(
            feature="overnight_agent",
            action="morning_brief_generated",
            details={
                "date": date_str,
                "positions": research["position_count"],
                "day_pnl_pct": research["day_pnl_pct"],
                "earnings_risks": list(research["earnings_risks"].keys()),
                "top_tomorrow": [s["ticker"] for s in research["top_tomorrow"]],
            },
            result="completed",
        )
    except Exception as e:
        log.warning("overnight_agent.activity_log_failed", error=str(e))


async def run_overnight_agent():
    """
    Continuous loop — fires at 4:30 PM ET every weekday.
    Called from main.py lifespan — runs forever as an asyncio background task.
    """
    log.info("overnight_agent.started")

    while True:
        secs = _seconds_until_next_fire()
        log.info("overnight_agent.sleeping",
                 next_fire_in_hours=round(secs / 3600, 2))
        await asyncio.sleep(secs)

        try:
            from app.db.models.settings import get_setting
            if bool(await get_setting("overnight_agent_enabled", True)):
                await _run_once()
            else:
                log.info("overnight_agent.disabled_by_setting")
        except Exception as e:
            log.error("overnight_agent.run_failed", error=str(e))

        # Sleep 2 minutes to avoid double-firing within the same minute window
        await asyncio.sleep(120)
