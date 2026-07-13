"""
Walk-forward policy tournament.

Timeline discipline (the whole point):
    |── fold 1 train ──|─ fold 1 test ─|
         |── fold 2 train ──|─ fold 2 test ─|
              ...                                |── HOLDOUT ──|

- Chronological folds: optimize on `train_years`, evaluate on the following
  `test_years`, roll forward by `test_years`. Never shuffled.
- The final `holdout_months` are excluded from every fold. Only the single
  policy that wins the walk-forward is ever run on the holdout — one shot,
  no second guesses. That number is the honest one.
- Ranking uses TEST results averaged across folds (a policy that only wins
  one era is not "universally applicable"). Policies with too few trades
  are excluded — a 3-trade fluke can top any leaderboard.
"""
from __future__ import annotations

import itertools
import time

import numpy as np
import pandas as pd
import structlog

from app.research.data import UNIVERSE, MARKET_TICKERS, load_history, regime_series
from app.research.engine import Panel, Policy, simulate

log = structlog.get_logger()

MIN_TRADES_PER_FOLD = 15


def default_grid() -> list[Policy]:
    """~200 policies spanning the quant rule family, live baseline included."""
    combos = itertools.product(
        (40.0, 45.0, 50.0),          # trend_rsi_min
        (65.0, 70.0),                # trend_rsi_max
        (True, False),               # require_macd
        (28.0, 32.0, 36.0),          # meanrev_rsi_max
        (1.5, 2.0, 3.0),             # stop_atr_mult
        (1.5, 2.0, 3.0),             # rr_ratio
        (True, False),               # regime_gate
    )
    grid = [Policy(trend_rsi_min=a, trend_rsi_max=b, require_macd=c,
                   meanrev_rsi_max=d, stop_atr_mult=e, rr_ratio=f, regime_gate=g)
            for a, b, c, d, e, f, g in combos]
    # Single-setup ablations: is each entry family pulling its weight?
    grid += [Policy(allow_meanrev=False), Policy(allow_trend=False)]
    return grid


def build_panel(start: str, end: str) -> Panel:
    hist = load_history(UNIVERSE, start, end)
    market = load_history(MARKET_TICKERS, start, end)
    regimes = regime_series(market["SPY"], market["^VIX"])
    return Panel(hist, regimes)


def _folds(dates: pd.DatetimeIndex, train_years: int, test_years: int,
           holdout_months: int) -> tuple[list[tuple], tuple]:
    """Chronological (train_start, train_end, test_start, test_end) windows."""
    usable_end = dates.max() - pd.DateOffset(months=holdout_months)
    holdout = (usable_end + pd.Timedelta(days=1), dates.max())
    folds = []
    # First year of data is indicator warmup (MA200), never traded
    cursor = dates.min() + pd.DateOffset(years=1)
    while True:
        tr_end = cursor + pd.DateOffset(years=train_years)
        te_end = tr_end + pd.DateOffset(years=test_years)
        if te_end > usable_end:
            break
        folds.append((cursor, tr_end, tr_end + pd.Timedelta(days=1), te_end))
        cursor = cursor + pd.DateOffset(years=test_years)
    return folds, holdout


def run_walkforward(start: str = "2013-01-01", end: str | None = None,
                    train_years: int = 4, test_years: int = 1,
                    holdout_months: int = 12,
                    grid: list[Policy] | None = None,
                    top_k: int = 10) -> dict:
    t0 = time.time()
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    panel = build_panel(start, end)
    grid = grid or default_grid()
    folds, holdout = _folds(panel.dates, train_years, test_years, holdout_months)
    if not folds:
        raise ValueError("Not enough history for a single train/test fold")

    log.info("research.walkforward.start", policies=len(grid), folds=len(folds),
             span=f"{panel.dates.min().date()}..{panel.dates.max().date()}",
             holdout=f"{holdout[0].date()}..{holdout[1].date()}")

    # label -> per-fold test metrics
    test_scores: dict[str, list[dict]] = {}
    train_scores: dict[str, list[dict]] = {}
    policies_by_label = {pol.label(): pol for pol in grid}

    for fi, (tr_s, tr_e, te_s, te_e) in enumerate(folds):
        for pol in grid:
            lab = pol.label()
            tr = simulate(panel, pol, tr_s, tr_e)
            if tr.metrics.get("n_trades", 0) < MIN_TRADES_PER_FOLD:
                continue
            te = simulate(panel, pol, te_s, te_e)
            train_scores.setdefault(lab, []).append(tr.metrics)
            test_scores.setdefault(lab, []).append(te.metrics)
        log.info("research.walkforward.fold_done", fold=fi + 1, of=len(folds),
                 elapsed_s=round(time.time() - t0, 1))

    # Aggregate: mean TEST sharpe across folds; require presence in every fold
    leaderboard = []
    for lab, scores in test_scores.items():
        if len(scores) < len(folds):
            continue  # didn't trade enough in some era — not universal
        tr_sh = float(np.mean([s["sharpe"] for s in train_scores[lab]]))
        te_sh = float(np.mean([s["sharpe"] for s in scores]))
        leaderboard.append({
            "label": lab,
            "policy": policies_by_label[lab].__dict__,
            "train_sharpe": round(tr_sh, 2),
            "test_sharpe": round(te_sh, 2),
            "overfit_gap": round(tr_sh - te_sh, 2),
            "test_cagr_pct": round(float(np.mean([s["cagr_pct"] for s in scores])), 2),
            "test_maxdd_pct": round(float(np.mean([s["max_drawdown_pct"] for s in scores])), 2),
            "test_trades_per_fold": round(float(np.mean([s["n_trades"] for s in scores])), 1),
            "test_win_rate_pct": round(float(np.mean(
                [s["win_rate_pct"] for s in scores if s["win_rate_pct"] is not None])), 1),
        })
    leaderboard.sort(key=lambda r: r["test_sharpe"], reverse=True)

    # Baselines for context: buy&hold SPY, and the live default policy
    market = load_history(["SPY"], start, end)["SPY"]["Close"]
    full_test_start = folds[0][2]
    spy_span = market[(market.index >= full_test_start) & (market.index <= holdout[0])]
    spy_ret = float(spy_span.iloc[-1] / spy_span.iloc[0] - 1) * 100 if len(spy_span) > 1 else None

    # One-shot holdout on the winner only
    holdout_result = None
    if leaderboard:
        winner = policies_by_label[leaderboard[0]["label"]]
        ho = simulate(panel, winner, holdout[0], holdout[1])
        spy_ho = market[(market.index >= holdout[0]) & (market.index <= holdout[1])]
        holdout_result = {
            "policy": leaderboard[0]["label"],
            "metrics": ho.metrics,
            "spy_return_pct": round(float(spy_ho.iloc[-1] / spy_ho.iloc[0] - 1) * 100, 2)
            if len(spy_ho) > 1 else None,
        }

    return {
        "meta": {
            "span": f"{panel.dates.min().date()}..{panel.dates.max().date()}",
            "universe_size": len(panel.tickers),
            "policies_tested": len(grid),
            "policies_qualified": len(leaderboard),
            "folds": [f"{a.date()}..{b.date()} / test {c.date()}..{d.date()}"
                      for a, b, c, d in folds],
            "holdout": f"{holdout[0].date()}..{holdout[1].date()}",
            "spy_test_period_return_pct": spy_ret,
            "elapsed_s": round(time.time() - t0, 1),
            "caveats": [
                "survivorship-biased universe (picked today) — rankings are meaningful, absolute returns optimistic",
                "daily bars, 5bps slippage, stops fill at stop price (conservative within-bar assumption)",
                "LLM agent strategies are NOT backtestable (model knowledge contaminates history); this tournament covers the deterministic policy family only",
            ],
        },
        "leaderboard": leaderboard[:top_k],
        "live_baseline_rank": next((i + 1 for i, r in enumerate(leaderboard)
                                    if r["label"] == Policy().label()), None),
        "holdout": holdout_result,
    }
