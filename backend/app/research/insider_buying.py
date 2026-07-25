"""
Insider-buying research — SEC Form 4 open-market purchases (code 'P') as a
signal source, structurally unrelated to every other family already tested
here (price patterns in engine.py/intraday.py, earnings surprises in
earnings.py). The academic anchor (Lakonishok & Lee 2001, Jeng/Metrick/
Zeckhauser 2003) finds predictive value specifically in voluntary,
cash-out-of-pocket open-market buys by officers/directors/10%-owners —
insider_data.py already does the hard part of isolating exactly that
signal from SEC EDGAR's raw Form 4 firehose.

A 150-ticker scan (2026-07-25) surfaced the pattern worth testing:
CLUSTERING. An isolated single purchase is weak, noisy signal — but
multiple DIFFERENT named insiders buying within a short window is the
literature's actual thesis (MRVL: 4 different C-suite executives, same
day; LLY: 5 executives across one week). min_distinct_buyers is a grid
parameter, not baked in as an assumption — the walk-forward decides
whether requiring a cluster actually produces better out-of-sample edge,
including testing min_distinct_buyers=1 (a single purchase) as its own
grid point for comparison.

Honest-execution rules (same discipline as earnings.py):
- Entry fires the trading day after the CLUSTER's last qualifying purchase
  became public (filing_date, never transaction_date — a Form 4 isn't
  public until filed, so trading off transaction_date would be lookahead;
  filing lags the real transaction by up to 2 business days by law).
- Stops trigger intraday off Low; take-profit assumed to fill second
  within a bar that hits both (conservative). Slippage charged per side.
- Chronological folds + a single burned one-shot holdout — identical
  machinery to earnings.py, just re-implemented locally rather than
  imported, matching this codebase's existing per-tournament convention
  (engine.py/intraday.py/earnings.py/momentum.py each stand alone).

Known limitation, stated up front rather than discovered later: the ticker
universe here is deliberately NOT research/data.py's general 59-name
UNIVERSE — insider buying is sparse and concentrated in specific names,
and real signal names found in the scan (MRVL is the clearest example)
aren't in that curated list. Instead this defaults to the actual tickers
that showed real purchase activity in the 150-ticker scan. That means
this tournament evaluates names ALREADY KNOWN TO HAVE FIRED — a second,
sharper selection-bias layer stacked on top of the survivorship bias every
tournament here already carries. Treat a positive result as "worth
forward-testing on a real dedicated account," not as a clean validation
the way earnings.py's out-of-universe check was.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from app.research.data import MARKET_TICKERS, load_history, regime_series
from app.research.earnings import EarningsPanel  # OHLC+ATR+regime panel — identical shape needed here

CACHE = Path("/tmp/research_cache_insider")
TRADING_DAYS = 252
MIN_TRADES_PER_FOLD = 5  # inherently sparser than earnings/momentum — lower bar, stated explicitly

# The 31 tickers that showed real (post-entity-filter, post-CIK-dedup)
# purchase activity in the 2026-07-25 150-ticker/trailing-12-month scan.
# See the module docstring's selection-bias caveat.
SIGNAL_UNIVERSE = [
    "TSLA", "TSM", "LLY", "ABT", "CRM", "AVGO", "ETN", "SPGI", "MRVL", "BA",
    "VRTX", "MU", "KO", "MSFT", "CAT", "IBM", "TMUS", "DIS", "GOOGL", "JNJ",
    "INTC", "PANW", "LIN", "APH", "SCHW", "IBKR", "COP", "CB", "UBER",
    "SBUX", "LOW",
]


# ── Insider purchase event data ─────────────────────────────────────────────

def load_insider_events(tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    """Long-format: one row per qualifying open-market purchase, across all
    tickers in range. Reuses insider_data.py's existing entity/notional
    filters — this only adds the walk-forward-specific caching layer."""
    from app.research.insider_data import fetch_insider_purchases

    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / f"purchases_{len(tickers)}_{start_date}_{end_date}.pkl"
    if key.exists() and time.time() - key.stat().st_mtime < 30 * 86_400:
        return pd.read_pickle(key)

    rows = []
    t0 = time.time()
    for i, tkr in enumerate(tickers):
        try:
            purchases = fetch_insider_purchases(tkr, start_date, end_date)
        except Exception as e:
            print(f"[insider] {tkr} fetch failed: {str(e)[:120]}")
            continue
        for p in purchases:
            rows.append({
                "ticker": tkr, "owner_name": p["owner_name"],
                "transaction_date": p["transaction_date"], "filing_date": p["filing_date"],
                "shares": p["shares"], "price": p["price"],
                "notional": p["shares"] * p["price"],
            })
        print(f"[insider] {i + 1}/{len(tickers)} {tkr}: {len(purchases)} purchases "
              f"({time.time() - t0:.0f}s elapsed)")

    df = pd.DataFrame(rows)
    df.to_pickle(key)
    print(f"[insider] {len(df)} qualifying purchases across "
          f"{df['ticker'].nunique() if len(df) else 0} tickers")
    return df


def build_cluster_events(purchases: pd.DataFrame, min_distinct_buyers: int,
                         cluster_window_days: int, min_notional: float) -> pd.DataFrame:
    """
    One row per qualifying cluster: (ticker, cluster_date, n_buyers). A
    cluster is the first point, scanning each ticker's purchases in filing
    order, where >= min_distinct_buyers different named individuals have
    all filed within cluster_window_days (calendar) of the cluster's first
    purchase. Fires once per cluster at the LAST qualifying purchase's
    filing_date (everything that defines the cluster is public by then),
    then the scan resumes strictly after the consumed cluster — no
    re-firing on purchase 2, 3, 4... of an already-signaled cluster.
    min_distinct_buyers=1 degenerates to "every single purchase fires on
    its own filing date" — the isolated-purchase baseline, for comparison.
    """
    df = purchases[purchases["notional"] >= min_notional].copy()
    if df.empty:
        return pd.DataFrame(columns=["ticker", "cluster_date", "n_buyers", "n_purchases"])
    df["filing_date"] = pd.to_datetime(df["filing_date"])

    events = []
    for ticker, g in df.groupby("ticker"):
        rows = g.sort_values("filing_date").to_dict("records")
        i = 0
        while i < len(rows):
            j = i + 1
            while j < len(rows) and (rows[j]["filing_date"] - rows[i]["filing_date"]).days <= cluster_window_days:
                j += 1
            window = rows[i:j]
            distinct = len(set(r["owner_name"] for r in window))
            if distinct >= min_distinct_buyers:
                events.append({
                    "ticker": ticker, "cluster_date": window[-1]["filing_date"],
                    "n_buyers": distinct, "n_purchases": len(window),
                })
                i = j
            else:
                i += 1
    return pd.DataFrame(events)


# ── Policy ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class InsiderPolicy:
    min_distinct_buyers: int = 1     # 1 = isolated single purchase; >=2 = cluster required
    cluster_window_days: int = 10    # calendar days a cluster's purchases must fall within
    min_notional: float = 15_000.0   # per-purchase floor (matches insider_data.py's own default)
    stop_atr_mult: float = 2.5
    rr_ratio: float | None = 3.0
    hold_days: int = 20
    risk_pct: float = 1.0
    max_positions: int = 10
    max_notional_pct: float = 15.0

    def label(self) -> str:
        return (f"buyers>={self.min_distinct_buyers} win{self.cluster_window_days}d "
                f"notional{self.min_notional/1000:.0f}k stop{self.stop_atr_mult:.1f}atr"
                f"{f' rr{self.rr_ratio:.1f}' if self.rr_ratio else ''} hold{self.hold_days}d "
                f"risk{self.risk_pct:.1f}% x{self.max_positions}")


def build_grid(quick: bool = False) -> list[InsiderPolicy]:
    buyers = [1, 2, 3] if not quick else [1, 2]
    windows = [5, 10, 20] if not quick else [10]
    notionals = [15_000.0, 50_000.0] if not quick else [15_000.0]
    stops = [1.5, 2.5, 3.5] if not quick else [2.5]
    rrs = [2.0, 3.0, None] if not quick else [3.0]
    holds = [10, 20, 40] if not quick else [20]
    return [
        InsiderPolicy(min_distinct_buyers=b, cluster_window_days=w, min_notional=n,
                     stop_atr_mult=st, rr_ratio=rr, hold_days=h)
        for b, w, n, st, rr, h in product(buyers, windows, notionals, stops, rrs, holds)
    ]


# ── Entry signal ─────────────────────────────────────────────────────────────

def _entry_day_index(panel: EarningsPanel, ticker: str, cluster_date) -> int | None:
    """First tradeable session strictly AFTER the cluster's filing became
    public — never same-day (the filing could land after the close)."""
    j = panel.ticker_idx.get(ticker)
    if j is None:
        return None
    d0 = pd.Timestamp(cluster_date).tz_localize(None).normalize()
    pos = int(panel.dates.searchsorted(d0, side="right"))
    while pos < len(panel.dates) and np.isnan(panel.open[pos, j]):
        pos += 1
    return pos if pos < len(panel.dates) else None


def entry_matrix(panel: EarningsPanel, cluster_events: pd.DataFrame) -> np.ndarray:
    """Boolean [day, ticker] — True where a qualifying cluster's entry fires."""
    sig = np.zeros((len(panel.dates), len(panel.tickers)), dtype=bool)
    for row in cluster_events.itertuples(index=False):
        j = panel.ticker_idx.get(row.ticker)
        d = row.entry_idx
        if j is None or d is None:
            continue
        sig[d, j] = True
    return sig


# ── Simulation (mirrors earnings.py::simulate's honest-fill mechanics) ──────

@dataclass
class SimResult:
    policy: dict
    label: str
    equity: pd.Series = field(repr=False)
    trades: pd.DataFrame = field(repr=False)
    metrics: dict = field(default_factory=dict)


def simulate(panel: EarningsPanel, sig: np.ndarray, pol: InsiderPolicy,
             start: pd.Timestamp, end: pd.Timestamp,
             starting_cash: float = 100_000.0, slippage_bps: float = 5.0) -> SimResult:
    day_idx = np.where((panel.dates >= start) & (panel.dates <= end))[0]
    slip = slippage_bps / 10_000.0
    cash = starting_cash
    positions: dict[int, list] = {}
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

def _folds(dates: pd.DatetimeIndex, train_years: float, test_years: float,
           holdout_months: int) -> tuple[list[tuple], tuple]:
    usable_end = dates.max() - pd.DateOffset(months=holdout_months)
    holdout = (usable_end + pd.Timedelta(days=1), dates.max())
    folds = []
    cursor = dates.min() + pd.DateOffset(years=1)  # ATR warmup
    while True:
        tr_end = cursor + pd.DateOffset(months=int(train_years * 12))
        te_end = tr_end + pd.DateOffset(months=int(test_years * 12))
        if te_end > usable_end:
            break
        folds.append((cursor, tr_end, tr_end + pd.Timedelta(days=1), te_end))
        cursor = cursor + pd.DateOffset(months=int(test_years * 12))
    return folds, holdout


def run_tournament(quick: bool = False, start: str = "2021-01-01", end: str | None = None,
                   train_years: float = 2.0, test_years: float = 1.0, holdout_months: int = 12,
                   top_k: int = 25, tickers: list[str] | None = None) -> dict:
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    if tickers is None:
        tickers = SIGNAL_UNIVERSE[:10] if quick else SIGNAL_UNIVERSE
    elif quick:
        tickers = tickers[:10]

    hist = load_history(tickers, start, end)
    market = load_history(MARKET_TICKERS, start, end)
    regimes = regime_series(market["SPY"], market["^VIX"])
    panel = EarningsPanel(hist, regimes)

    purchases = load_insider_events(panel.tickers, start, end)
    purchases = purchases[purchases["ticker"].isin(panel.tickers)].copy()

    folds, holdout = _folds(panel.dates, train_years, test_years, holdout_months)
    if not folds:
        raise ValueError("Not enough history for a single train/test fold")

    grid = build_grid(quick)
    print(f"[insider] {len(panel.tickers)} tickers, {len(purchases)} qualifying purchases, "
          f"{len(grid)} policies, {len(folds)} folds "
          f"({train_years}y train/{test_years}y test) + {holdout_months}mo holdout")

    rows = []
    t0 = time.time()
    for gi, pol in enumerate(grid):
        clusters = build_cluster_events(purchases, pol.min_distinct_buyers,
                                        pol.cluster_window_days, pol.min_notional)
        if clusters.empty:
            continue
        clusters["entry_idx"] = [
            _entry_day_index(panel, r.ticker, r.cluster_date)
            for r in clusters.itertuples(index=False)
        ]
        clusters = clusters.dropna(subset=["entry_idx"]).copy()
        clusters["entry_idx"] = clusters["entry_idx"].astype(int)
        sig = entry_matrix(panel, clusters)

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

    robust = [r for r in rows if r["all_folds_positive"]] or rows
    winner = robust[0] if robust else None
    holdout_result = None
    if winner:
        pol = InsiderPolicy(**winner["policy"])
        clusters = build_cluster_events(purchases, pol.min_distinct_buyers,
                                        pol.cluster_window_days, pol.min_notional)
        clusters["entry_idx"] = [
            _entry_day_index(panel, r.ticker, r.cluster_date)
            for r in clusters.itertuples(index=False)
        ]
        clusters = clusters.dropna(subset=["entry_idx"]).copy()
        clusters["entry_idx"] = clusters["entry_idx"].astype(int)
        sig = entry_matrix(panel, clusters)
        ho = simulate(panel, sig, pol, holdout[0], holdout[1])
        holdout_result = {"label": winner["label"], **ho.metrics}

    market_spy = market["SPY"]["Close"]
    ho_spy = market_spy[(market_spy.index >= holdout[0]) & (market_spy.index <= holdout[1])]
    holdout_spy_pct = (round(float(ho_spy.iloc[-1] / ho_spy.iloc[0] - 1) * 100, 2)
                       if len(ho_spy) > 1 else None)

    report = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "data_source": "SEC EDGAR Form 4 (insider_data.py) + data.py::load_history (alpaca/yfinance daily bars)",
        "universe": panel.tickers,
        "span": f"{panel.dates.min().date()}..{panel.dates.max().date()}",
        "n_purchases_qualifying": len(purchases),
        "n_policies": len(grid),
        "n_qualified": len(rows),
        "n_robust_all_folds_positive": len([r for r in rows if r["all_folds_positive"]]),
        "caveats": [
            "Ticker universe is the SIGNAL_UNIVERSE (names already known to have fired in a "
            "2026-07-25 scan) — NOT the platform's general 59-name UNIVERSE. This is a second, "
            "sharper selection-bias layer stacked on top of the survivorship bias every "
            "tournament here already carries. A positive result means 'worth forward-testing "
            "on a real account,' not 'clean walk-forward validation.'",
            "SEC EDGAR Form 4 data — real filings, not a scrape/estimate, but the raw feed "
            "contains real filing-agent errors (duplicate line items, punctuation-inconsistent "
            "entity names) that insider_data.py filters/dedupes on a best-effort basis.",
            "Shorter history window (2021+) and smaller MIN_TRADES_PER_FOLD than earnings.py's "
            "tournament — insider-buying clusters are inherently sparser than earnings events "
            "(quarterly, every company) or momentum signals (continuous).",
            "daily bars, 5bps slippage, stop assumed to fill before take-profit within a bar",
        ],
        "leaderboard": rows[:top_k],
        "winner": winner["label"] if winner else None,
        "holdout": holdout_result,
        "holdout_spy_return_pct": holdout_spy_pct,
        "holdout_span": f"{holdout[0].date()}..{holdout[1].date()}",
    }
    out = Path("/tmp/insider_buying_report.json")
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"[insider] report -> {out}")
    if winner:
        print(f"[insider] WINNER {winner['label']} | test_sharpe {winner['test_sharpe']} "
              f"| gap {winner['overfit_gap']} | holdout sharpe "
              f"{holdout_result.get('sharpe')} cagr {holdout_result.get('cagr_pct')}% "
              f"maxdd {holdout_result.get('max_drawdown_pct')}% (SPY {holdout_spy_pct}%)")
    else:
        print("[insider] NO POLICY QUALIFIED — signal too sparse at these thresholds "
              f"(MIN_TRADES_PER_FOLD={MIN_TRADES_PER_FOLD}) for a walk-forward verdict.")
    return report


if __name__ == "__main__":
    import sys
    run_tournament(quick="--quick" in sys.argv)
