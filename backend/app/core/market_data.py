"""
Server-side market data core — Alpaca-first, Yahoo-last.

Born 2026-07-17: Yahoo rate-limited Render's shared egress IP (429s on every
yfinance call), silently starving every engine of data — scans "found nothing",
runs failed with "Market data unavailable". yfinance is a scrape API; from a
datacenter IP it can die at any moment. Everything trade-critical therefore
goes through here:

- Daily OHLCV bars:    Alpaca /v2/stocks/bars (keyed, our own quota) -> yfinance
- Live snapshot / gap: Alpaca /v2/stocks/{sym}/snapshot            -> yfinance
- Earnings surprises:  NASDAQ /api/company/{sym}/earnings-surprise  -> yfinance
- Report timing (pre/post market): NASDAQ earnings calendar (per-date cached)

yfinance remains acceptable for non-trade-critical enrichment (fundamentals,
news, VIX) where a failure degrades quality instead of blocking trades.
All functions are sync (called from thread executors) and fail soft: None
instead of raising.
"""
from __future__ import annotations

from datetime import datetime, timedelta, date as date_t, UTC

import structlog

log = structlog.get_logger()

_NASDAQ_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_ALPACA_TIMEOUT = 20.0
_YF_TIMEOUT = 15.0


def _yf_bounded(fn, timeout: float = _YF_TIMEOUT):
    """
    Run a yfinance call under a hard wall-clock timeout. yfinance is a scrape
    API that sets none of its own — under Render's shared-IP Yahoo throttling
    a single call can hang far longer than any caller expects (this stalled a
    live whole-market earnings scan for 6+ minutes on 2026-07-21, one ticker
    at a time, even with the 6-way prescreen parallelism). Returns None on
    timeout or any other failure; the stuck thread is abandoned rather than
    joined so the caller is never blocked past `timeout`.
    """
    import concurrent.futures
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        return ex.submit(fn).result(timeout=timeout)
    except Exception:
        return None
    finally:
        ex.shutdown(wait=False)

# per-process cache: calendar date -> raw rows. Fetched while the date is
# CURRENT, rows carry the report timing; NASDAQ strips it from past dates
# ("time-not-supplied"), so a warm cache is also our timing memory.
_calendar_rows_cache: dict[str, list[dict]] = {}


def _alpaca_creds() -> tuple[str, str, str] | None:
    from app.config import get_settings
    s = get_settings()
    key = getattr(s, "alpaca_api_key", "") or ""
    sec = getattr(s, "alpaca_api_secret", "") or ""
    if not (key and sec):
        return None
    return key, sec, getattr(s, "alpaca_data_url", "https://data.alpaca.markets")


# ── Daily bars ───────────────────────────────────────────────────────────────

def _alpaca_daily_bars(ticker: str, days: int):
    import pandas as pd
    import requests

    creds = _alpaca_creds()
    if creds is None:
        return None
    key, sec, data_url = creds
    start = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}
    rows: list = []
    page = None
    try:
        while True:
            params = {"symbols": ticker, "timeframe": "1Day", "start": start,
                      "limit": 10_000, "adjustment": "all", "feed": "iex"}
            if page:
                params["page_token"] = page
            r = requests.get(f"{data_url}/v2/stocks/bars", headers=headers,
                             params=params, timeout=_ALPACA_TIMEOUT)
            r.raise_for_status()
            j = r.json()
            rows.extend((j.get("bars") or {}).get(ticker) or [])
            page = j.get("next_page_token")
            if not page:
                break
    except Exception as e:
        log.debug("market_data.alpaca_bars_failed", ticker=ticker, error=str(e)[:120])
        return None
    if not rows:
        return None
    df = pd.DataFrame(rows).rename(columns={
        "o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
    df.index = pd.to_datetime(df["t"], utc=True).dt.tz_convert(None).dt.normalize()
    return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)


def _yf_daily_bars(ticker: str, days: int):
    try:
        import yfinance as yf
        period = "1y" if days > 240 else "6mo"
        hist = _yf_bounded(lambda: yf.Ticker(ticker).history(period=period, interval="1d"))
        if hist is None or hist.empty:
            return None
        hist.index = hist.index.tz_localize(None)
        return hist[["Open", "High", "Low", "Close", "Volume"]]
    except Exception as e:
        log.debug("market_data.yf_bars_failed", ticker=ticker, error=str(e)[:120])
        return None


def get_daily_bars(ticker: str, days: int = 400):
    """Daily OHLCV DataFrame (Open/High/Low/Close/Volume) or None. Alpaca-first."""
    df = _alpaca_daily_bars(ticker, days)
    if df is not None and len(df) >= 30:
        return df
    return _yf_daily_bars(ticker, days)


# ── Snapshot (live-ish price, today's open, prior close) ─────────────────────

def get_snapshot(ticker: str) -> dict | None:
    """{price, today_open, prev_close} or None. Alpaca snapshot -> yfinance."""
    import requests

    creds = _alpaca_creds()
    if creds is not None:
        key, sec, data_url = creds
        try:
            r = requests.get(f"{data_url}/v2/stocks/{ticker}/snapshot",
                             headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec},
                             params={"feed": "iex"}, timeout=_ALPACA_TIMEOUT)
            r.raise_for_status()
            j = r.json()
            daily = j.get("dailyBar") or {}
            prev = j.get("prevDailyBar") or {}
            trade = j.get("latestTrade") or {}
            out = {
                "price": trade.get("p") or daily.get("c"),
                "today_open": daily.get("o"),
                "prev_close": prev.get("c"),
            }
            if out["today_open"] and out["prev_close"]:
                return out
        except Exception as e:
            log.debug("market_data.snapshot_failed", ticker=ticker, error=str(e)[:120])

    try:
        import yfinance as yf
        hist = _yf_bounded(lambda: yf.Ticker(ticker).history(period="5d", interval="1d"))
        if hist is None or len(hist) < 2:
            return None
        return {"price": float(hist["Close"].iloc[-1]),
                "today_open": float(hist["Open"].iloc[-1]),
                "prev_close": float(hist["Close"].iloc[-2])}
    except Exception:
        return None


# ── Intraday volume imbalance (order-flow proxy) ──────────────────────────────

def intraday_volume_imbalance(ticker: str) -> dict | None:
    """
    Today's up-volume vs down-volume from 5-minute bars — a lightweight,
    tick-classification-free proxy for "are people net buying or net
    selling right now" (uptick/downtick volume rule: a bar that closed
    above the prior bar's close counts its volume as buying pressure, below
    counts as selling). Not true trade-level order flow (Alpaca's free/IEX
    tier doesn't expose that), but it's real traded volume, not a guess —
    unlike the Sentiment analyst's institutional_flow/put_call_ratio fields,
    which stay null with no data source behind them.

    Returns {"imbalance": float in [-1, 1], "up_volume": int,
    "down_volume": int, "bars": int} or None (pre-market, no Alpaca keys,
    fetch failure, or under 6 bars — too little signal to trust).
    """
    import requests

    creds = _alpaca_creds()
    if creds is None:
        return None
    key, sec, data_url = creds
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        r = requests.get(
            f"{data_url}/v2/stocks/bars",
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec},
            params={"symbols": ticker, "timeframe": "5Min", "start": f"{today}T00:00:00Z",
                   "limit": 500, "adjustment": "raw", "feed": "iex"},
            timeout=_ALPACA_TIMEOUT,
        )
        r.raise_for_status()
        bars = (r.json().get("bars") or {}).get(ticker) or []
    except Exception as e:
        log.debug("market_data.intraday_imbalance_failed", ticker=ticker, error=str(e)[:120])
        return None

    if len(bars) < 6:
        return None

    up_vol = down_vol = 0.0
    prev_close = bars[0]["c"]
    for b in bars[1:]:
        v = b.get("v") or 0
        if b["c"] > prev_close:
            up_vol += v
        elif b["c"] < prev_close:
            down_vol += v
        prev_close = b["c"]

    total = up_vol + down_vol
    if total <= 0:
        return None
    return {
        "imbalance": round((up_vol - down_vol) / total, 3),
        "up_volume": int(up_vol),
        "down_volume": int(down_vol),
        "bars": len(bars),
    }


# ── Earnings surprises (NASDAQ-first) ────────────────────────────────────────

def nasdaq_calendar_rows(day: date_t) -> list[dict]:
    """Raw NASDAQ earnings-calendar rows for a date, cached per process."""
    import requests

    key = day.isoformat()
    if key in _calendar_rows_cache:
        return _calendar_rows_cache[key]
    rows: list[dict] = []
    try:
        r = requests.get("https://api.nasdaq.com/api/calendar/earnings",
                         params={"date": key}, headers=_NASDAQ_HEADERS, timeout=15)
        r.raise_for_status()
        rows = ((r.json().get("data") or {}).get("rows")) or []
    except Exception as e:
        log.debug("market_data.nasdaq_calendar_failed", date=key, error=str(e)[:120])
    _calendar_rows_cache[key] = rows
    return rows


# per-process cache: "YYYY-MM-DD" -> ranked ticker list (refreshes once per day)
_market_universe_cache: dict[str, list[str]] = {}


def nasdaq_market_universe(max_symbols: int = 150) -> list[str]:
    """
    The whole US equity market (NASDAQ's public screener, common stocks on
    NASDAQ/NYSE/AMEX), ranked by market cap, largest first, capped to
    max_symbols. This is the general-purpose "don't restrict me to a curated
    watchlist" universe for the agents/quant scanners — distinct from
    fetch_earnings_reporters() in earnings_pead.py, which additionally
    requires a fresh earnings surprise.

    Capped rather than truly unbounded: thousands of illiquid/OTC tickers
    would blow the scan's time budget for _run_pre_screen's per-ticker bar
    fetch and add mostly untradeable noise. 150 matches the platform's
    existing custom_watchlist hard cap and the earnings whole-market pool —
    at 95%+ percentile market cap this already covers every name that could
    plausibly take a meaningful position size.
    """
    import requests

    key = datetime.now(UTC).strftime("%Y-%m-%d")
    if key in _market_universe_cache:
        return _market_universe_cache[key]

    ranked: list[str] = []
    try:
        r = requests.get(
            "https://api.nasdaq.com/api/screener/stocks",
            params={"tableonly": "true", "limit": "0", "download": "true"},
            headers=_NASDAQ_HEADERS, timeout=20,
        )
        r.raise_for_status()
        rows = (r.json().get("data") or {}).get("rows") or []
        caps: dict[str, float] = {}
        for row in rows:
            sym = (row.get("symbol") or "").strip().upper()
            if not sym or not sym.isalnum():
                continue  # preferred shares / units / warrants — skip
            try:
                cap = float((row.get("marketCap") or "0").replace("$", "").replace(",", ""))
            except ValueError:
                continue
            if cap > 0:
                caps[sym] = max(cap, caps.get(sym, 0.0))
        ranked = sorted(caps, key=lambda s: caps[s], reverse=True)[:max_symbols]
    except Exception as e:
        log.warning("market_data.nasdaq_universe_failed", error=str(e)[:200])

    if ranked:
        _market_universe_cache[key] = ranked
    return ranked


def _report_timing(ticker: str, report_date: date_t) -> bool | None:
    """True=pre-market, False=after-hours, None=unknown."""
    t = ""
    for row in nasdaq_calendar_rows(report_date):
        if (row.get("symbol") or "").strip().upper() == ticker.upper():
            t = row.get("time") or ""
            break
    if t == "time-pre-market":
        return True
    if t == "time-after-hours":
        return False
    # NASDAQ strips timing from past dates — rescue via yfinance's timestamp
    # (timing only; if Yahoo is rate-limited we stay unknown).
    try:
        from datetime import time as dtime
        import yfinance as yf
        ed = _yf_bounded(lambda: yf.Ticker(ticker).get_earnings_dates(limit=4))
        if ed is not None and not ed.empty:
            for ts in ed.index:
                if ts.date() == report_date:
                    return ts.time() < dtime(12, 0)
    except Exception:
        pass
    return None


def get_latest_earnings_surprise(ticker: str) -> dict | None:
    """
    Most recent REPORTED quarter for a ticker:
    {report_date: date, surprise_pct: float, pre_market: bool|None}
    NASDAQ earnings-surprise endpoint first; yfinance get_earnings_dates fallback.
    pre_market=None means report timing unknown (callers should treat it as
    after-hours, i.e. actionable the NEXT session — conservative, no lookahead).
    """
    import requests

    try:
        r = requests.get(f"https://api.nasdaq.com/api/company/{ticker}/earnings-surprise",
                         headers=_NASDAQ_HEADERS, timeout=15)
        r.raise_for_status()
        rows = (((r.json().get("data") or {}).get("earningsSurpriseTable") or {})
                .get("rows")) or []
        if rows:
            top = rows[0]  # most recent first
            rep = datetime.strptime(top["dateReported"], "%m/%d/%Y").date()
            surprise = float(top["percentageSurprise"])
            return {"report_date": rep, "surprise_pct": surprise,
                    "pre_market": _report_timing(ticker, rep), "source": "nasdaq"}
    except Exception as e:
        log.debug("market_data.nasdaq_surprise_failed", ticker=ticker, error=str(e)[:120])

    # yfinance fallback — the pre-2026-07-17 primary path
    try:
        from datetime import time as dtime
        import yfinance as yf
        ed = _yf_bounded(lambda: yf.Ticker(ticker).get_earnings_dates(limit=4))
        if ed is None or ed.empty:
            return None
        ed = ed.dropna(subset=["Reported EPS", "Surprise(%)"]).sort_index()
        if ed.empty:
            return None
        ts = ed.index[-1]
        return {"report_date": ts.date(), "surprise_pct": float(ed.iloc[-1]["Surprise(%)"]),
                "pre_market": ts.time() < dtime(12, 0), "source": "yfinance"}
    except Exception as e:
        log.debug("market_data.yf_surprise_failed", ticker=ticker, error=str(e)[:120])
        return None
