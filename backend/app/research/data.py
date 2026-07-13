"""
Research data layer — historical daily OHLCV + reconstructed market regimes.

Caveats that apply to every result produced downstream:
- Daily bars only (free yfinance data). No intraday, no options history.
- The universe below is picked TODAY, which bakes in survivorship bias:
  these are companies that survived and stayed liquid. Treat absolute
  returns as optimistic; policy RANKINGS are far less affected because
  every policy trades the same biased universe.
- yfinance auto-adjusts for splits/dividends (auto_adjust=True).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger()

CACHE_DIR = Path("/tmp/research_cache")

# ~60 liquid names across sectors, mirroring the platform's scanner watchlist
# plus enough breadth to make regime slicing meaningful.
UNIVERSE = [
    # Mega-cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA", "AMD",
    # Tech / growth
    "CRM", "ORCL", "NFLX", "ADBE", "NOW", "INTU", "UBER", "SHOP",
    # Semis
    "QCOM", "MU", "AVGO", "TSM", "ASML", "TXN", "INTC", "LRCX",
    # Finance
    "JPM", "GS", "V", "MA", "BAC", "MS", "BLK", "AXP",
    # Healthcare
    "UNH", "LLY", "ABBV", "JNJ", "MRK", "TMO", "PFE",
    # Energy / industrial
    "XOM", "CVX", "CAT", "DE", "HON", "GE", "BA",
    # Consumer
    "WMT", "COST", "HD", "MCD", "NKE", "SBUX", "PG", "KO", "PEP",
    # Comms / media
    "DIS", "CMCSA", "T", "VZ",
]

MARKET_TICKERS = ["SPY", "^VIX"]


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{hashlib.sha256(key.encode()).hexdigest()[:24]}.pkl"


def load_history(tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    """
    Daily OHLCV per ticker, cached on disk. Returns {ticker: DataFrame with
    Open/High/Low/Close/Volume, DatetimeIndex}. Tickers with too little
    history are dropped (they simply never signal — no lookahead is created).
    """
    key = f"{','.join(sorted(tickers))}|{start}|{end}"
    path = _cache_path(key)
    if path.exists():
        return pd.read_pickle(path)

    import yfinance as yf
    log.info("research.download", tickers=len(tickers), start=start, end=end)
    raw = yf.download(tickers, start=start, end=end, interval="1d",
                      auto_adjust=True, group_by="ticker", progress=False, threads=True)

    out: dict[str, pd.DataFrame] = {}
    for t in tickers:
        try:
            df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
            df = df.dropna(subset=["Close"])
        except KeyError:
            continue
        if len(df) < 260:  # need at least ~1y for MA200 warmup
            continue
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        out[t] = df

    pd.to_pickle(out, path)
    log.info("research.download.done", kept=len(out))
    return out


def regime_series(spy: pd.DataFrame, vix: pd.DataFrame) -> pd.Series:
    """
    Historical market regime per trading day — a vectorized port of
    workers/regime_detector.py scoring, using only data available up to each
    day (rolling windows, no future leakage).
    """
    close = spy["Close"]
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    rsi = rsi.fillna(50.0)

    breadth = (close.pct_change() > 0).rolling(20).mean()
    mom_1m = close.pct_change(22) * 100
    mom_3m = close.pct_change(66) * 100

    vix_level = vix["Close"].reindex(close.index).ffill().fillna(20.0)

    n = len(close)
    scores = {k: np.zeros(n) for k in
              ("BULL_TRENDING", "BEAR_TRENDING", "HIGH_VOLATILITY", "SIDEWAYS")}

    # VIX signals
    hi_vol = (vix_level > 30).to_numpy()
    mid_vol = ((vix_level > 20) & ~ (vix_level > 30)).to_numpy()
    low_vol = (vix_level <= 20).to_numpy()
    scores["HIGH_VOLATILITY"] += 40 * hi_vol + 15 * mid_vol
    scores["SIDEWAYS"] += 10 * mid_vol
    scores["BULL_TRENDING"] += 15 * low_vol

    # Trend signals
    c, m50, m200 = close.to_numpy(), ma50.to_numpy(), ma200.to_numpy()
    strong_up = (c > m50) & (m50 > m200)
    strong_down = (c < m50) & (m50 < m200)
    above_200 = (c > m200) & ~strong_up
    below_200 = ~(c > m200) & ~strong_down
    scores["BULL_TRENDING"] += 30 * strong_up + 15 * above_200
    scores["BEAR_TRENDING"] += 30 * strong_down + 15 * below_200
    scores["SIDEWAYS"] += 10 * above_200 + 10 * below_200

    # Breadth
    b = breadth.to_numpy()
    scores["BULL_TRENDING"] += 20 * (b > 0.65)
    scores["BEAR_TRENDING"] += 20 * (b < 0.35)
    scores["SIDEWAYS"] += 15 * ((b >= 0.35) & (b <= 0.65))

    # Momentum
    m1, m3 = mom_1m.to_numpy(), mom_3m.to_numpy()
    bull_mom = (m1 > 3) & (m3 > 8)
    bear_mom = (m1 < -3) & (m3 < -8)
    scores["BULL_TRENDING"] += 15 * bull_mom
    scores["BEAR_TRENDING"] += 15 * bear_mom
    scores["SIDEWAYS"] += 10 * (~bull_mom & ~bear_mom)

    # RSI extremes
    r = rsi.to_numpy()
    scores["HIGH_VOLATILITY"] += 10 * (r > 70)
    scores["BEAR_TRENDING"] += 10 * (r < 35)

    names = list(scores)
    stacked = np.vstack([scores[k] for k in names])
    winner = np.argmax(stacked, axis=0)
    out = pd.Series([names[i] for i in winner], index=close.index, name="regime")
    # MA200 warmup period has no trustworthy trend read
    out.iloc[:200] = "SIDEWAYS"
    return out
