"""
Post-Earnings-Announcement Drift (PEAD) research — a different information
source than the price-pattern rule families in engine.py / intraday.py.

The question: does buying long-only into a large positive EPS surprise and
holding for weeks produce an edge OUT OF SAMPLE, after slippage and honest
fills? PEAD is a real, decades-documented anomaly (systematic underreaction
to earnings surprises) — structurally different from "price crossed a
moving average," so a null result here doesn't just re-confirm the two
intraday rounds; a positive result would be a genuinely new signal source.

Honest-execution rules (same discipline as engine.py / intraday.py):
- Entry fills at the first session's OPEN after the earnings news was
  public (same-day open if reported pre-market, next session's open if
  reported after-close/midday) — never the report day's close.
- Stops trigger intraday off Low; assumed to fill first when a bar also
  hits the take-profit (conservative). Slippage charged per side.
- Chronological folds + a single burned one-shot holdout, exactly like
  walkforward.py / intraday.py. Round 2 of the intraday tournament showed
  that "all folds positive" must be checked over the FULL grid, not just
  the top-K export — this module does the same.

Data caveats:
- Earnings dates/EPS/surprise% come from yfinance's scrape-based
  `get_earnings_dates` (not a formal API) — flaky per-ticker, cached hard,
  skips failures rather than raising.
- Daily bars via research/data.py::load_history (Alpaca-preferred,
  yfinance-fallback, already used by the swing quant tournament).
- Survivorship-biased universe — same caveat as the other two tournaments.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from datetime import time as dtime
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from app.research.data import UNIVERSE, MARKET_TICKERS, load_history, regime_series

CACHE = Path("/tmp/research_cache_earnings")
TRADING_DAYS = 252
MIN_TRADES_PER_FOLD = 10


# ── Earnings event data ─────────────────────────────────────────────────────

def load_earnings_events(tickers: list[str]) -> pd.DataFrame:
    """
    Long-format: one row per historical earnings report (ticker, date, EPS
    estimate/actual, surprise%, pre_market flag). Scrape-based and flaky —
    fetched per ticker with graceful skip, cached 30 days (this data barely
    changes; only next quarter's print adds a row).
    """
    import yfinance as yf

    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / f"events_{len(tickers)}.pkl"
    if key.exists() and time.time() - key.stat().st_mtime < 30 * 86_400:
        return pd.read_pickle(key)

    rows = []
    for i, tkr in enumerate(tickers):
        try:
            ed = yf.Ticker(tkr).get_earnings_dates(limit=80)
        except Exception as e:
            print(f"[earnings] {tkr} fetch failed: {str(e)[:120]}")
            continue
        if ed is None or ed.empty:
            continue
        ed = ed.dropna(subset=["Reported EPS", "Surprise(%)"])
        for dt, r in ed.iterrows():
            rows.append({
                "ticker": tkr, "earnings_date": dt,
                "eps_estimate": r.get("EPS Estimate"),
                "eps_actual": r.get("Reported EPS"),
                "surprise_pct": r.get("Surprise(%)"),
                "pre_market": dt.time() < dtime(12, 0),
            })
        if (i + 1) % 10 == 0:
            print(f"[earnings] {i + 1}/{len(tickers)} tickers fetched")
        time.sleep(0.3)  # polite pacing against the scrape endpoint

    df = pd.DataFrame(rows)
    df.to_pickle(key)
    n_t = df["ticker"].nunique() if len(df) else 0
    print(f"[earnings] {len(df)} historical earnings events across {n_t} tickers")
    return df


# ── Policy ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EarningsPolicy:
    surprise_min_pct: float = 5.0    # min EPS surprise% to trigger entry
    require_gap_up: bool = False     # confirm market agrees: entry open > prior close
    stop_atr_mult: float = 2.5
    rr_ratio: float | None = 3.0     # None = no fixed take-profit, hold_days only
    hold_days: int = 20              # forced time exit after N trading days
    risk_pct: float = 1.0            # % of equity risked per trade
    max_positions: int = 10
    max_notional_pct: float = 15.0

    def label(self) -> str:
        return (f"surprise>={self.surprise_min_pct:.0f}%"
                f"{' gap+' if self.require_gap_up else ''}"
                f" stop{self.stop_atr_mult:.1f}atr"
                f"{f' rr{self.rr_ratio:.1f}' if self.rr_ratio else ''}"
                f" hold{self.hold_days}d risk{self.risk_pct:.1f}% x{self.max_positions}")


def build_grid(quick: bool = False) -> list[EarningsPolicy]:
    surprises = [3.0, 5.0, 10.0, 15.0] if not quick else [5.0]
    gaps = [True, False] if not quick else [False]
    stops = [1.5, 2.5, 3.5] if not quick else [2.5]
    rrs = [2.0, 3.0, None] if not quick else [3.0]
    holds = [10, 20, 40] if not quick else [20]
    return [EarningsPolicy(surprise_min_pct=s, require_gap_up=g, stop_atr_mult=st,
                           rr_ratio=rr, hold_days=h)
            for s, g, st, rr, h in product(surprises, gaps, stops, rrs, holds)]


# ── Panel ────────────────────────────────────────────────────────────────────

class EarningsPanel:
    """[day, ticker] float matrices, aligned to a union daily calendar."""

    def __init__(self, history: dict[str, pd.DataFrame], regimes: pd.Series):
        self.tickers = sorted(history)
        self.ticker_idx = {t: i for i, t in enumerate(self.tickers)}
        idx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in history.values()])))
        self.dates = idx

        def mat(col: str) -> np.ndarray:
            return np.column_stack([history[t][col].reindex(idx).to_numpy() for t in self.tickers])

        self.open, self.high = mat("Open"), mat("High")
        self.low, self.close = mat("Low"), mat("Close")

        h = pd.DataFrame(self.high, index=idx)
        low_df = pd.DataFrame(self.low, index=idx)
        atr = (h - low_df).rolling(14).mean().to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            self.atr_pct = np.where(self.close > 0, atr / self.close * 100, np.nan)

        self.regime = regimes.reindex(idx).ffill().fillna("SIDEWAYS").to_numpy()


def _entry_day_index(panel: EarningsPanel, ticker: str, earnings_date, pre_market: bool) -> int | None:
    """
    First tradeable session AT OR AFTER the news was public — never earlier
    (no lookahead). Pre-market reports fill the same session's open; reports
    after close (or unspecified/midday) push to the next session's open.
    """
    j = panel.ticker_idx.get(ticker)
    if j is None:
        return None
    d0 = pd.Timestamp(earnings_date).tz_localize(None).normalize()
    pos = int(panel.dates.searchsorted(d0, side="left"))
    if pos >= len(panel.dates):
        return None
    if not pre_market:
        pos += 1
    while pos < len(panel.dates) and np.isnan(panel.open[pos, j]):
        pos += 1
    return pos if pos < len(panel.dates) else None


def entry_matrix(panel: EarningsPanel, events: pd.DataFrame, pol: EarningsPolicy) -> np.ndarray:
    """Boolean [day, ticker] — True where this policy's entry fires."""
    sig = np.zeros((len(panel.dates), len(panel.tickers)), dtype=bool)
    qualifying = events[events["surprise_pct"] >= pol.surprise_min_pct]
    for row in qualifying.itertuples(index=False):
        j = panel.ticker_idx.get(row.ticker)
        d = row.entry_idx
        if j is None or d is None:
            continue
        if pol.require_gap_up:
            if d == 0 or np.isnan(panel.close[d - 1, j]) or np.isnan(panel.open[d, j]):
                continue
            if panel.open[d, j] <= panel.close[d - 1, j]:
                continue
        sig[d, j] = True
    return sig


# ── Simulation (mirrors engine.py::simulate's honest-fill mechanics) ────────

@dataclass
class SimResult:
    policy: dict
    label: str
    equity: pd.Series = field(repr=False)
    trades: pd.DataFrame = field(repr=False)
    metrics: dict = field(default_factory=dict)


def simulate(panel: EarningsPanel, sig: np.ndarray, pol: EarningsPolicy,
             start: pd.Timestamp, end: pd.Timestamp,
             starting_cash: float = 100_000.0, slippage_bps: float = 5.0) -> SimResult:
    day_idx = np.where((panel.dates >= start) & (panel.dates <= end))[0]
    slip = slippage_bps / 10_000.0
    cash = starting_cash
    positions: dict[int, list] = {}  # j -> [qty, entry_px, stop_px, tp_px, entry_day]
    equity_curve, trades = [], []

    for d in day_idx:
        for j in list(positions):
            qty, entry_px, stop_px, tp_px, e_day = positions[j]
            if np.isnan(panel.close[d, j]):
                continue
            lo, hi = panel.low[d, j], panel.high[d, j]
            exit_px, reason = None, None
            if lo <= stop_px:
                exit_px = min(stop_px, panel.open[d, j]) * (1 - slip)
                reason = "stop"
            elif tp_px is not None and hi >= tp_px:
                exit_px, reason = tp_px * (1 - slip), "take_profit"
            elif (d - e_day) >= pol.hold_days:
                exit_px, reason = panel.close[d, j] * (1 - slip), "time_exit"
            if exit_px is not None:
                cash += qty * exit_px
                trades.append({
                    "ticker": panel.tickers[j], "entry_date": panel.dates[e_day],
                    "exit_date": panel.dates[d], "entry": entry_px, "exit": exit_px,
                    "pnl_pct": (exit_px / entry_px - 1) * 100, "reason": reason,
                    "regime": panel.regime[e_day],
                })
                del positions[j]

        pos_val = sum(q * panel.close[d, j] for j, (q, *_r) in positions.items()
                      if not np.isnan(panel.close[d, j]))
        equity = cash + pos_val
        equity_curve.append(equity)

        if len(positions) < pol.max_positions:
            for j in np.where(sig[d])[0]:
                if len(positions) >= pol.max_positions:
                    break
                if j in positions or np.isnan(panel.open[d, j]):
                    continue
                atr_pct = panel.atr_pct[d, j]
                if np.isnan(atr_pct) or atr_pct <= 0:
                    continue
                stop_pct = float(np.clip(pol.stop_atr_mult * atr_pct, 3.0, 15.0))
                px = panel.open[d, j] * (1 + slip)
                risk_dollars = equity * pol.risk_pct / 100
                max_notional = equity * pol.max_notional_pct / 100
                notional = min(risk_dollars / (stop_pct / 100), max_notional)
                qty = int(notional // px)
                if qty <= 0 or qty * px > cash:
                    continue
                stop_px = px * (1 - stop_pct / 100)
                tp_px = px * (1 + pol.rr_ratio * stop_pct / 100) if pol.rr_ratio else None
                cash -= qty * px
                positions[j] = [qty, px, stop_px, tp_px, d]

    eq = pd.Series(equity_curve, index=panel.dates[day_idx], name="equity")
    trades_df = pd.DataFrame(trades)
    return SimResult(policy=asdict(pol), label=pol.label(), equity=eq,
                     trades=trades_df, metrics=compute_metrics(eq, trades_df))


def compute_metrics(eq: pd.Series, trades: pd.DataFrame) -> dict:
    if len(eq) < 2:
        return {"error": "no data", "n_trades": 0}
    rets = eq.pct_change().dropna()
    years = len(eq) / TRADING_DAYS
    total = eq.iloc[-1] / eq.iloc[0] - 1
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 else 0.0
    sharpe = float(rets.mean() / rets.std() * np.sqrt(TRADING_DAYS)) if rets.std() > 0 else 0.0
    dd = float((eq / eq.cummax() - 1).min())
    return {
        "total_return_pct": round(total * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown_pct": round(dd * 100, 2),
        "n_trades": int(len(trades)),
        "win_rate_pct": round(float((trades["pnl_pct"] > 0).mean() * 100), 1) if len(trades) else None,
        "avg_trade_pct": round(float(trades["pnl_pct"].mean()), 2) if len(trades) else None,
    }


# ── Walk-forward ─────────────────────────────────────────────────────────────

def _folds(dates: pd.DatetimeIndex, train_years: int, test_years: int,
           holdout_months: int) -> tuple[list[tuple], tuple]:
    """Chronological (train_start, train_end, test_start, test_end) windows."""
    usable_end = dates.max() - pd.DateOffset(months=holdout_months)
    holdout = (usable_end + pd.Timedelta(days=1), dates.max())
    folds = []
    cursor = dates.min() + pd.DateOffset(years=1)  # ATR warmup
    while True:
        tr_end = cursor + pd.DateOffset(years=train_years)
        te_end = tr_end + pd.DateOffset(years=test_years)
        if te_end > usable_end:
            break
        folds.append((cursor, tr_end, tr_end + pd.Timedelta(days=1), te_end))
        cursor = cursor + pd.DateOffset(years=test_years)
    return folds, holdout


def run_tournament(quick: bool = False, start: str = "2013-01-01", end: str | None = None,
                   train_years: int = 5, test_years: int = 2, holdout_months: int = 24,
                   top_k: int = 25, tickers: list[str] | None = None) -> dict:
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    if tickers is None:
        tickers = UNIVERSE[:15] if quick else UNIVERSE
    elif quick:
        tickers = tickers[:15]

    hist = load_history(tickers, start, end)
    market = load_history(MARKET_TICKERS, start, end)
    regimes = regime_series(market["SPY"], market["^VIX"])
    panel = EarningsPanel(hist, regimes)

    events = load_earnings_events(panel.tickers)
    events = events[events["ticker"].isin(panel.tickers)].copy()
    events["entry_idx"] = [
        _entry_day_index(panel, r.ticker, r.earnings_date, r.pre_market)
        for r in events.itertuples(index=False)
    ]
    events = events.dropna(subset=["entry_idx", "surprise_pct"]).copy()
    events["entry_idx"] = events["entry_idx"].astype(int)

    folds, holdout = _folds(panel.dates, train_years, test_years, holdout_months)
    if not folds:
        raise ValueError("Not enough history for a single train/test fold")

    grid = build_grid(quick)
    print(f"[earnings] {len(panel.tickers)} tickers, {len(events)} qualifying earnings "
          f"events, {len(grid)} policies, {len(folds)} folds "
          f"({train_years}y train/{test_years}y test) + {holdout_months}mo holdout")

    rows = []
    t0 = time.time()
    for gi, pol in enumerate(grid):
        sig = entry_matrix(panel, events, pol)
        fold_train, fold_test = [], []
        qualified = True
        for tr_s, tr_e, te_s, te_e in folds:
            tr = simulate(panel, sig, pol, tr_s, tr_e)
            te = simulate(panel, sig, pol, te_s, te_e)
            if te.metrics.get("n_trades", 0) < MIN_TRADES_PER_FOLD:
                qualified = False
                break
            fold_train.append(tr.metrics)
            fold_test.append(te.metrics)
        if not qualified:
            continue
        mean_train_sh = float(np.mean([m["sharpe"] for m in fold_train]))
        mean_test_sh = float(np.mean([m["sharpe"] for m in fold_test]))
        win_rates = [m["win_rate_pct"] for m in fold_test if m["win_rate_pct"] is not None]
        rows.append({
            "label": pol.label(), "policy": asdict(pol),
            "train_sharpe": round(mean_train_sh, 2),
            "test_sharpe": round(mean_test_sh, 2),
            "overfit_gap": round(mean_train_sh - mean_test_sh, 2),
            "all_folds_positive": all(m["cagr_pct"] > 0 for m in fold_test),
            "test_cagr_pct": round(float(np.mean([m["cagr_pct"] for m in fold_test])), 2),
            "test_maxdd_pct": round(float(np.mean([m["max_drawdown_pct"] for m in fold_test])), 2),
            "test_win_rate_pct": round(float(np.mean(win_rates)), 1) if win_rates else None,
            "test_trades_per_fold": round(float(np.mean([m["n_trades"] for m in fold_test])), 1),
            "folds": fold_test,
        })
        if (gi + 1) % 25 == 0:
            print(f"  {gi + 1}/{len(grid)} policies, {time.time() - t0:.0f}s")

    rows.sort(key=lambda r: r["test_sharpe"], reverse=True)

    # Robustness bar checked over the FULL grid, not just the top-K export
    # (round-2 intraday lesson: a top-25-only check can silently miss this).
    robust = [r for r in rows if r["all_folds_positive"]] or rows
    winner = robust[0] if robust else None
    holdout_result = None
    if winner:
        pol = EarningsPolicy(**winner["policy"])
        sig = entry_matrix(panel, events, pol)
        ho = simulate(panel, sig, pol, holdout[0], holdout[1])
        holdout_result = {"label": winner["label"], **ho.metrics}

    market_spy = market["SPY"]["Close"]
    ho_spy = market_spy[(market_spy.index >= holdout[0]) & (market_spy.index <= holdout[1])]
    holdout_spy_pct = (round(float(ho_spy.iloc[-1] / ho_spy.iloc[0] - 1) * 100, 2)
                       if len(ho_spy) > 1 else None)

    report = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "data_source": "yfinance_earnings_dates + data.py::load_history (alpaca/yfinance daily bars)",
        "universe": panel.tickers,
        "span": f"{panel.dates.min().date()}..{panel.dates.max().date()}",
        "n_events_qualifying": len(events),
        "n_policies": len(grid),
        "n_qualified": len(rows),
        "n_robust_all_folds_positive": len([r for r in rows if r["all_folds_positive"]]),
        "caveats": [
            "yfinance earnings-date scrape — per-ticker gaps possible, not a formal API",
            "survivorship-biased universe (picked today) — rankings meaningful, absolute returns optimistic",
            "daily bars, 5bps slippage, stop assumed to fill before take-profit within a bar",
            "LLM agent strategies are NOT backtestable; this covers the deterministic PEAD rule only",
        ],
        "leaderboard": rows[:top_k],
        "winner": winner["label"] if winner else None,
        "holdout": holdout_result,
        "holdout_spy_return_pct": holdout_spy_pct,
        "holdout_span": f"{holdout[0].date()}..{holdout[1].date()}",
    }
    out = Path("/tmp/earnings_report.json")
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"[earnings] report -> {out}")
    if winner:
        print(f"[earnings] WINNER {winner['label']} | test_sharpe {winner['test_sharpe']} "
              f"| gap {winner['overfit_gap']} | holdout sharpe "
              f"{holdout_result.get('sharpe')} cagr {holdout_result.get('cagr_pct')}% "
              f"maxdd {holdout_result.get('max_drawdown_pct')}% (SPY {holdout_spy_pct}%)")
    return report


if __name__ == "__main__":
    import sys
    run_tournament(quick="--quick" in sys.argv)
