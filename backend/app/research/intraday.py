"""
Intraday policy research — 5-minute bars, walk-forward, portfolio-level P&L.

The question this answers: does any deterministic intraday rule family clear
a target daily dollar expectancy (default $200/day on $100K) OUT OF SAMPLE,
after slippage, long-only, flat by the close?

Honest-execution rules (mirrors research/engine.py):
- Signals computed on bar t's CLOSE; entries fill at bar t+1's OPEN.
- Stops/targets trigger intrabar off High/Low; stop fills FIRST when both
  are inside one bar (conservative).
- Slippage charged per side on every fill.
- All positions force-closed at the 15:55 ET bar (no overnight risk).

Data caveats (do not oversell results):
- yfinance 5m bars reach back only ~60 trading days — ONE market regime.
- Universe is today's liquid large-caps (survivorship-biased).
- Absolute dollars are optimistic; relative ranking is the signal.

Setups (long-only, matching platform constraints):
- orb:     opening-range breakout (range of first N minutes, break above)
- vwaprev: mean reversion — price stretched k ATRs BELOW session VWAP
- mom:     20-bar-high momentum continuation with volume confirmation
"""
from __future__ import annotations

import json
import pickle
import time
from dataclasses import dataclass, asdict
from datetime import time as dtime
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path("/tmp/research_cache_intraday")
EQUITY = 100_000.0
SLIPPAGE_BPS = 3.0          # per side
TARGET_DOLLARS_PER_DAY = 200.0
MAX_NOTIONAL_PCT = 25.0     # per-position cap, % of equity
MAX_GROSS_PCT = 100.0       # total exposure cap (no leverage — robustness first)
NO_ENTRY_AFTER = dtime(15, 0)   # ET
EOD_FLAT_AT = dtime(15, 55)     # ET

UNIVERSE = [
    "SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA",
    "AMD", "AVGO", "NFLX", "CRM", "COST", "MU", "INTC", "ORCL", "ADBE",
    "QCOM", "TXN", "JPM", "BAC", "XOM", "CVX", "UNH", "HD", "WMT", "DIS",
    "CAT", "GE",
]


# ── Data ─────────────────────────────────────────────────────────────────────

def load_bars(interval: str = "5m", period: str = "60d",
              tickers: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """Per-ticker RTH 5m OHLCV, ET-indexed. Pickle-cached (bars are static)."""
    import yfinance as yf

    tickers = tickers or UNIVERSE
    CACHE.mkdir(exist_ok=True)
    key = CACHE / f"bars_{interval}_{period}_{len(tickers)}.pkl"
    if key.exists() and time.time() - key.stat().st_mtime < 86_400:
        with open(key, "rb") as f:
            return pickle.load(f)

    raw = yf.download(tickers, interval=interval, period=period,
                      group_by="ticker", progress=False, auto_adjust=True,
                      prepost=False, threads=True)
    out: dict[str, pd.DataFrame] = {}
    for t in tickers:
        df = raw[t].dropna() if t in raw.columns.get_level_values(0) else pd.DataFrame()
        if df.empty:
            continue
        df = df.tz_convert("America/New_York")
        # RTH only; yfinance occasionally emits a 16:00 stub bar
        df = df[(df.index.time >= dtime(9, 30)) & (df.index.time < dtime(16, 0))]
        if len(df) > 500:
            out[t] = df
    with open(key, "wb") as f:
        pickle.dump(out, f)
    return out


def load_bars_alpaca(years: float = 2.0,
                     tickers: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """
    Years of 5m bars via the Alpaca data API (needs ALPACA_API_KEY/SECRET env).
    Historical SIP data is included on the free plan; falls back to IEX feed
    if SIP is rejected. Pickle-cached — the pull is ~1M+ rows.
    """
    import os
    import httpx

    api_key = os.getenv("ALPACA_API_KEY", "")
    api_secret = os.getenv("ALPACA_API_SECRET", "")
    if not (api_key and api_secret):
        raise RuntimeError("ALPACA_API_KEY/SECRET not set — cannot load deep history")

    tickers = tickers or UNIVERSE
    CACHE.mkdir(exist_ok=True)
    key = CACHE / f"alpaca_5m_{years:g}y_{len(tickers)}.pkl"
    if key.exists() and time.time() - key.stat().st_mtime < 7 * 86_400:
        with open(key, "rb") as f:
            return pickle.load(f)

    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}
    start = (pd.Timestamp.utcnow() - pd.Timedelta(days=365 * years)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    end = (pd.Timestamp.utcnow() - pd.Timedelta(minutes=20)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")

    rows: dict[str, list] = {}
    with httpx.Client(timeout=60.0) as client:
        for feed in ("sip", "iex"):
            try:
                page = None
                n_pages = 0
                while True:
                    params = {"symbols": ",".join(tickers), "timeframe": "5Min",
                              "start": start, "end": end, "limit": 10_000,
                              "feed": feed, "adjustment": "split"}
                    if page:
                        params["page_token"] = page
                    r = client.get("https://data.alpaca.markets/v2/stocks/bars",
                                   headers=headers, params=params)
                    if r.status_code == 429:
                        wait = int(r.headers.get("Retry-After", 30) or 30)
                        print(f"[intraday] 429 rate limit — sleeping {wait}s "
                              f"(page {n_pages})")
                        time.sleep(wait)
                        continue  # retry the same page
                    r.raise_for_status()
                    j = r.json()
                    for sym, bars in (j.get("bars") or {}).items():
                        rows.setdefault(sym, []).extend(bars)
                    page = j.get("next_page_token")
                    n_pages += 1
                    if n_pages % 25 == 0:
                        print(f"[intraday] {n_pages} pages, "
                              f"{sum(len(v) for v in rows.values()):,} bars")
                    if not page:
                        break
                    time.sleep(0.4)  # stay under 200 req/min
                break  # feed worked
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (402, 403) and feed == "sip":
                    rows.clear()
                    print("[intraday] SIP feed rejected — falling back to IEX")
                    continue
                raise

    out: dict[str, pd.DataFrame] = {}
    for sym, bars in rows.items():
        df = pd.DataFrame(bars)
        if df.empty:
            continue
        df["t"] = pd.to_datetime(df["t"], utc=True)
        df = df.set_index("t").tz_convert("America/New_York").sort_index()
        df = df.rename(columns={"o": "Open", "h": "High", "l": "Low",
                                "c": "Close", "v": "Volume"})
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        df = df[(df.index.time >= dtime(9, 30)) & (df.index.time < dtime(16, 0))]
        if len(df) > 2_000:
            out[sym] = df
    with open(key, "wb") as f:
        pickle.dump(out, f)
    print(f"[intraday] alpaca bars: {len(out)} tickers, "
          f"{sum(len(d) for d in out.values()):,} rows")
    return out


# ── Policy ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class IntradayPolicy:
    setup: str = "orb"              # "orb" | "vwaprev" | "mom"
    or_minutes: int = 30            # opening-range window (orb only)
    vol_ratio_min: float = 1.0      # bar volume vs 20-bar average
    above_vwap: bool = True         # orb/mom: require price above session VWAP
    dev_entry_atr: float = 2.0      # vwaprev: ATRs below VWAP to trigger
    rsi_max: float = 100.0          # vwaprev: 5m RSI ceiling
    stop_atr_mult: float = 1.5      # stop distance in 5m ATRs
    rr: float = 2.0                 # target = stop distance × rr
    max_hold_bars: int | None = 36  # time exit (5m bars); None = hold to EOD
    risk_pct: float = 1.0           # % of equity risked per trade (pre-cap)
    max_trades_day: int = 6         # portfolio-wide entries per day
    max_concurrent: int = 3
    # "all" | "first90" (entries 9:30-11:00 only) | "no_midday" (skip 11:30-14:00)
    entry_window: str = "all"

    def label(self) -> str:
        core = {"orb": f"orb{self.or_minutes}",
                "vwaprev": f"vwaprev[{self.dev_entry_atr:.1f}atr,rsi<={self.rsi_max:.0f}]",
                "mom": "mom20"}[self.setup]
        return (f"{core} vol>={self.vol_ratio_min:.1f}"
                f"{' vwap+' if self.above_vwap and self.setup != 'vwaprev' else ''}"
                f" stop{self.stop_atr_mult:.1f}atr rr{self.rr:.1f}"
                f"{f' hold<={self.max_hold_bars}' if self.max_hold_bars else ' holdEOD'}"
                f" risk{self.risk_pct:.1f}% x{self.max_concurrent}"
                f"{'' if self.entry_window == 'all' else ' ' + self.entry_window}")


def build_grid(quick: bool = False) -> list[IntradayPolicy]:
    pols: list[IntradayPolicy] = []
    stops = [1.0, 1.5, 2.5] if not quick else [1.5]
    rrs = [1.5, 2.0, 3.0] if not quick else [2.0]
    holds = [12, 36, None] if not quick else [36]
    windows = ["all", "first90", "no_midday"] if not quick else ["all"]

    for orm, vr, st, rr, hold, w in product([15, 30], [1.0, 1.5], stops, rrs,
                                            holds, windows):
        pols.append(IntradayPolicy(setup="orb", or_minutes=orm, vol_ratio_min=vr,
                                   stop_atr_mult=st, rr=rr, max_hold_bars=hold,
                                   entry_window=w))
    for dev, rmax, st, rr, hold, w in product([1.5, 2.0, 2.5], [35.0, 100.0],
                                              stops, rrs, holds, windows):
        pols.append(IntradayPolicy(setup="vwaprev", dev_entry_atr=dev, rsi_max=rmax,
                                   stop_atr_mult=st, rr=rr, max_hold_bars=hold,
                                   above_vwap=False, entry_window=w))
    for vr, av, st, rr, hold, w in product([1.0, 1.5], [True, False], stops, rrs,
                                           holds, windows):
        pols.append(IntradayPolicy(setup="mom", vol_ratio_min=vr, above_vwap=av,
                                   stop_atr_mult=st, rr=rr, max_hold_bars=hold,
                                   entry_window=w))
    return pols


# ── Per-ticker precomputation ────────────────────────────────────────────────

class TickerSeries:
    """Numpy views of one ticker's bars plus session-aware indicators."""

    def __init__(self, df: pd.DataFrame):
        self.index = df.index
        self.open = df["Open"].to_numpy(float)
        self.high = df["High"].to_numpy(float)
        self.low = df["Low"].to_numpy(float)
        self.close = df["Close"].to_numpy(float)
        self.volume = df["Volume"].to_numpy(float)
        self.date = df.index.date
        self.time = np.array([ts.time() for ts in df.index])
        # policy-independent time-of-day masks, precomputed once
        self.mask_late = np.array([t >= NO_ENTRY_AFTER for t in self.time])
        self.mask_first90 = np.array([t < dtime(11, 0) for t in self.time])
        self.mask_no_midday = np.array(
            [t < dtime(11, 30) or t >= dtime(14, 0) for t in self.time])
        self.mask_eod = np.array([t >= EOD_FLAT_AT for t in self.time])

        c = df["Close"]
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        self.rsi = (100 - 100 / (1 + gain / loss.replace(0, np.nan))).fillna(50.0).to_numpy()

        self.atr = (df["High"] - df["Low"]).rolling(14).mean().to_numpy()
        self.vol_ratio = (df["Volume"] / df["Volume"].rolling(20).mean()
                          .replace(0, np.nan)).fillna(1.0).to_numpy()
        self.hi20 = df["High"].rolling(20).max().shift(1).to_numpy()

        # Session VWAP + per-day opening ranges
        g = df.groupby(df.index.date, sort=False)
        typical = (df["High"] + df["Low"] + df["Close"]) / 3
        pv = (typical * df["Volume"]).groupby(df.index.date, sort=False).cumsum()
        vv = df["Volume"].groupby(df.index.date, sort=False).cumsum()
        self.vwap = (pv / vv.replace(0, np.nan)).ffill().to_numpy()

        self.or_high: dict[int, np.ndarray] = {}
        for n in (15, 30):
            nbars = n // 5
            orh = g["High"].transform(lambda s: s.iloc[:nbars].max())
            # NaN until the opening range is complete
            bar_in_day = g.cumcount().to_numpy()
            oh = orh.to_numpy().copy()
            oh[bar_in_day < nbars] = np.nan
            self.or_high[n] = oh

        self.day_starts: dict[object, tuple[int, int]] = {}
        dates = self.date
        start = 0
        for i in range(1, len(dates) + 1):
            if i == len(dates) or dates[i] != dates[i - 1]:
                self.day_starts[dates[start]] = (start, i)
                start = i


def entry_signal(ts: TickerSeries, pol: IntradayPolicy) -> np.ndarray:
    """Boolean per bar — signal at that bar's close (fill next bar's open)."""
    ok = ~np.isnan(ts.atr) & (ts.atr > 0) & (ts.vol_ratio >= pol.vol_ratio_min)
    ok &= ~ts.mask_late
    if pol.entry_window == "first90":
        ok &= ts.mask_first90
    elif pol.entry_window == "no_midday":
        ok &= ts.mask_no_midday
    if pol.setup == "orb":
        oh = ts.or_high[pol.or_minutes]
        sig = ok & ~np.isnan(oh) & (ts.close > oh)
        if pol.above_vwap:
            sig &= ts.close > ts.vwap
    elif pol.setup == "vwaprev":
        sig = ok & (ts.close < ts.vwap - pol.dev_entry_atr * ts.atr) \
                 & (ts.rsi <= pol.rsi_max)
    else:  # mom
        sig = ok & ~np.isnan(ts.hi20) & (ts.close > ts.hi20)
        if pol.above_vwap:
            sig &= ts.close > ts.vwap
    return sig


# ── Portfolio simulator ──────────────────────────────────────────────────────

def simulate_days(series: dict[str, TickerSeries],
                  signals: dict[str, np.ndarray],
                  days: list, pol: IntradayPolicy) -> tuple[pd.Series, int]:
    """Simulate one policy over the given session dates.
    Returns (daily net $ P&L on EQUITY, total trades)."""
    slip = SLIPPAGE_BPS / 10_000
    risk_dollars = EQUITY * pol.risk_pct / 100
    max_notional = EQUITY * MAX_NOTIONAL_PCT / 100
    daily: dict[object, float] = {}
    n_trades = 0

    for day in days:
        # bar timeline for this day, merged across tickers that traded it
        rng = {t: ts.day_starts[day] for t, ts in series.items()
               if day in ts.day_starts}
        if not rng:
            continue
        pnl = 0.0
        open_pos: dict[str, dict] = {}
        trades_today = 0
        nbars = max(e - s for s, e in rng.values())

        # sparse index: fill-bar offset k → tickers whose bar k-1 signaled
        sig_map: dict[int, list[str]] = {}
        for t, (s, e) in rng.items():
            for j in np.nonzero(signals[t][s:e - 1])[0]:
                sig_map.setdefault(j + 1, []).append(t)

        for k in range(nbars):
            # 1) exits on this bar (chronological before new entries)
            for t in list(open_pos):
                s, e = rng[t]
                if s + k >= e:
                    continue
                ts = series[t]
                i = s + k
                p = open_pos[t]
                exit_px = None
                if ts.time[i] >= EOD_FLAT_AT or i == e - 1:
                    exit_px = ts.close[i] * (1 - slip)
                elif pol.max_hold_bars and k - p["bar"] >= pol.max_hold_bars:
                    exit_px = ts.open[i] * (1 - slip)
                elif ts.low[i] <= p["stop"]:                    # stop first
                    exit_px = min(p["stop"], ts.open[i]) * (1 - slip)
                elif ts.high[i] >= p["target"]:
                    exit_px = p["target"] * (1 - slip)
                if exit_px is not None:
                    pnl += (exit_px - p["entry"]) * p["qty"]
                    del open_pos[t]

            # 2) entries: signal on bar k-1 close → fill bar k open
            if k == 0 or trades_today >= pol.max_trades_day:
                continue
            for t in sig_map.get(k, ()):
                if (t in open_pos or len(open_pos) >= pol.max_concurrent
                        or trades_today >= pol.max_trades_day):
                    continue
                ts = series[t]
                s, e = rng[t]
                i = s + k
                if ts.time[i] >= EOD_FLAT_AT:
                    continue
                entry = ts.open[i] * (1 + slip)
                stop_dist = pol.stop_atr_mult * ts.atr[i - 1]
                if not np.isfinite(stop_dist) or stop_dist <= 0:
                    continue
                gross = sum(p["entry"] * p["qty"] for p in open_pos.values())
                notional = min(risk_dollars / stop_dist * entry, max_notional)
                notional = min(notional, EQUITY * MAX_GROSS_PCT / 100 - gross)
                qty = int(notional / entry)
                if qty < 1:
                    continue
                trades_today += 1
                n_trades += 1
                stop_px = entry - stop_dist
                target_px = entry + stop_dist * pol.rr
                # entry bar's own range can hit the stop/target (stop first)
                if ts.low[i] <= stop_px:
                    pnl += (stop_px * (1 - slip) - entry) * qty
                elif ts.high[i] >= target_px:
                    pnl += (target_px * (1 - slip) - entry) * qty
                else:
                    open_pos[t] = {"entry": entry, "qty": qty, "bar": k,
                                   "stop": stop_px, "target": target_px}

        daily[day] = pnl
    return pd.Series(daily, dtype=float), n_trades


def day_metrics(daily: pd.Series, n_trades: int) -> dict:
    if daily.empty:
        return {"mean_day": 0.0, "sharpe": 0.0, "win_days": 0.0,
                "p_target": 0.0, "max_dd": 0.0, "trades_per_day": 0.0, "days": 0}
    eq = daily.cumsum()
    dd = (eq - eq.cummax()).min()
    sd = daily.std(ddof=0)
    return {
        "mean_day": round(float(daily.mean()), 2),
        "sharpe": round(float(daily.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0, 2),
        "win_days": round(float((daily > 0).mean()), 3),
        "p_target": round(float((daily >= TARGET_DOLLARS_PER_DAY).mean()), 3),
        "max_dd": round(float(dd), 2),
        "trades_per_day": round(n_trades / len(daily), 2),
        "days": int(len(daily)),
    }


# ── Walk-forward ─────────────────────────────────────────────────────────────

def run_tournament(quick: bool = False, deep: bool = False) -> dict:
    """deep=True → years of Alpaca 5m bars; else the 60d yfinance window."""
    bars = load_bars_alpaca(2.0) if deep else load_bars()
    series = {t: TickerSeries(df) for t, df in bars.items()}
    all_days = sorted(set().union(*[set(ts.day_starts) for ts in series.values()]))

    # fold sizing scales with the data: deep history earns longer test slices,
    # more folds, and a bigger burn-once holdout
    if len(all_days) >= 300:
        holdout_days, test_days, n_folds, min_trades = 40, 20, 6, 20
    else:
        holdout_days, test_days, n_folds, min_trades = 10, 5, 4, 5

    holdout = all_days[-holdout_days:]
    work = all_days[:-holdout_days]
    folds = []
    for f in range(n_folds):
        te_end = len(work) - (n_folds - 1 - f) * test_days
        te_start = te_end - test_days
        folds.append({"train": work[:te_start], "test": work[te_start:te_end]})

    grid = build_grid(quick)
    print(f"[intraday] {len(series)} tickers, {len(all_days)} sessions, "
          f"{len(grid)} policies, {n_folds} folds ({test_days}d test) "
          f"+ {holdout_days}d holdout")

    rows = []
    t0 = time.time()
    for gi, pol in enumerate(grid):
        signals = {t: entry_signal(ts, pol) for t, ts in series.items()}
        fold_tests, fold_trains, qualified = [], [], True
        for fold in folds:
            tr_d, tr_n = simulate_days(series, signals, fold["train"], pol)
            te_d, te_n = simulate_days(series, signals, fold["test"], pol)
            if te_n < min_trades:
                qualified = False
                break
            fold_trains.append(day_metrics(tr_d, tr_n))
            fold_tests.append(day_metrics(te_d, te_n))
        if not qualified:
            continue
        mean_test = float(np.mean([m["mean_day"] for m in fold_tests]))
        mean_train = float(np.mean([m["mean_day"] for m in fold_trains]))
        rows.append({
            "label": pol.label(),
            "policy": asdict(pol),
            "test_mean_day": round(mean_test, 2),
            "train_mean_day": round(mean_train, 2),
            "overfit_gap": round(mean_train - mean_test, 2),
            "all_folds_positive": all(m["mean_day"] > 0 for m in fold_tests),
            "test_sharpe": round(float(np.mean([m["sharpe"] for m in fold_tests])), 2),
            "test_win_days": round(float(np.mean([m["win_days"] for m in fold_tests])), 3),
            "test_p_target": round(float(np.mean([m["p_target"] for m in fold_tests])), 3),
            "trades_per_day": round(float(np.mean([m["trades_per_day"] for m in fold_tests])), 2),
            "folds": fold_tests,
        })
        if (gi + 1) % 25 == 0:
            print(f"  {gi + 1}/{len(grid)} policies, {time.time() - t0:.0f}s")

    rows.sort(key=lambda r: r["test_mean_day"], reverse=True)

    # One-shot holdout: winner only (robustness bar: all folds positive if any)
    robust = [r for r in rows if r["all_folds_positive"]] or rows
    winner = robust[0] if robust else None
    holdout_result = None
    if winner:
        pol = IntradayPolicy(**winner["policy"])
        signals = {t: entry_signal(ts, pol) for t, ts in series.items()}
        hd, hn = simulate_days(series, signals, holdout, pol)
        holdout_result = {"label": winner["label"], **day_metrics(hd, hn),
                          "daily": {str(d): round(v, 2) for d, v in hd.items()}}

    report = {
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "target_dollars_per_day": TARGET_DOLLARS_PER_DAY,
        "equity": EQUITY,
        "slippage_bps_per_side": SLIPPAGE_BPS,
        "universe": sorted(series),
        "sessions": len(all_days),
        "n_policies": len(grid),
        "n_qualified": len(rows),
        "data_source": "alpaca_5m_deep" if deep else "yfinance_5m_60d",
        "caveats": [
            ("2y of Alpaca 5m bars" if deep
             else "60 trading days of 5m bars — a single market regime"),
            "survivorship-biased universe",
            "long-only; paper-grade fills; absolute $ optimistic",
        ],
        "leaderboard": rows[:25],
        "winner": winner["label"] if winner else None,
        "holdout": holdout_result,
    }
    out = Path("/tmp/intraday_report_deep.json" if deep else "/tmp/intraday_report.json")
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"[intraday] report -> {out}")
    if winner:
        print(f"[intraday] WINNER {winner['label']} | test ${winner['test_mean_day']}/day "
              f"| gap {winner['overfit_gap']} | holdout ${holdout_result['mean_day']}/day "
              f"P(>=200)={holdout_result['p_target']}")
    return report


if __name__ == "__main__":
    import sys
    run_tournament(quick="--quick" in sys.argv, deep="--deep" in sys.argv)
