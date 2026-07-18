"""
Cross-sectional momentum rotation — walk-forward tournament.

A genuinely different bet than the per-ticker rule family in engine.py:
instead of asking "is this chart a buy", it asks "which of these N names
have been strongest, relative to each other" and rotates the portfolio
into the top ranks on a fixed schedule. The academic factor (Jegadeesh &
Titman 12-1 momentum) is one point in this grid.

Execution honesty matches engine.py:
- Ranks are computed on day t's CLOSE; the rebalance fills at day t+1's OPEN.
- 5bps slippage on every dollar traded (both sides of the rotation).
- No shorting; the strategy is long top-N or (partially) in cash.

Benchmarks that matter here: SPY buy&hold AND the equal-weight universe —
rotation only earns its keep if it beats holding the same names statically.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
import structlog

from app.research.data import UNIVERSE, MARKET_TICKERS, load_history, regime_series
from app.research.engine import Panel, REGIME_SCALE, compute_metrics
from app.research.walkforward import _folds

log = structlog.get_logger()

MIN_EPISODES_PER_FOLD = 6


@dataclass(frozen=True)
class MomPolicy:
    lookback_days: int = 126     # ranking window (63/126/252 ≈ 3/6/12 months)
    skip_days: int = 21          # skip most recent month (classic 12-1 shape)
    top_n: int = 8
    rebalance_days: int = 21     # trading days between rotations (5=weekly, 21=monthly)
    weighting: str = "equal"     # equal | inv_vol (1/63d-return-stddev)
    market_filter: str = "none"  # none | spy200 (all-cash while SPY < MA200)
    regime_mode: str = "off"     # off | scale (REGIME_SCALE shrinks exposure)
    exposure_pct: float = 95.0   # target invested fraction when fully on

    def label(self) -> str:
        return (f"mom[{self.lookback_days}-{self.skip_days}]"
                f" top{self.top_n} rb{self.rebalance_days}d {self.weighting}"
                f"{' spy200' if self.market_filter == 'spy200' else ''}"
                f" {self.regime_mode}")


def default_grid() -> list[MomPolicy]:
    import itertools
    combos = itertools.product(
        (63, 126, 252),      # lookback_days
        (0, 21),             # skip_days
        (4, 8, 12),          # top_n
        (5, 21),             # rebalance_days
        ("equal", "inv_vol"),
        ("none", "spy200"),
        ("off", "scale"),
    )
    return [MomPolicy(lookback_days=lb, skip_days=sk, top_n=n, rebalance_days=rb,
                      weighting=w, market_filter=mf, regime_mode=rm)
            for lb, sk, n, rb, w, mf, rm in combos]


def quick_grid() -> list[MomPolicy]:
    return [MomPolicy(lookback_days=lb, skip_days=21, top_n=n)
            for lb in (126, 252) for n in (4, 8)]


def latest_target_weights(close: pd.DataFrame, lookback_days: int, skip_days: int,
                          top_n: int, weighting: str = "inv_vol",
                          vol_window: int = 63) -> dict[str, float]:
    """
    Target weights at the most recent close — the LIVE engine's entry point
    (agents/momentum_rotation.py). Same math as MomData/simulate_momentum:
    momentum = close[t-skip] / close[t-skip-lookback] - 1, inverse-vol weights
    from the 63d daily-return stddev. Keeping it in this module is what keeps
    live and backtest from drifting apart.
    Weights sum to 1.0 — the caller applies exposure scaling.
    """
    shifted = close.shift(skip_days)
    mom = (shifted / shifted.shift(lookback_days) - 1).iloc[-1].dropna()
    if mom.empty:
        return {}
    top = mom.nlargest(min(top_n, len(mom))).index
    if weighting == "inv_vol":
        vol = close[top].pct_change().rolling(vol_window).std().iloc[-1]
        iv = 1.0 / vol.where(vol > 0)
        fill = iv.mean() if np.isfinite(iv.mean()) else 1.0
        iv = iv.fillna(fill)
        w = iv / iv.sum()
    else:
        w = pd.Series(1.0 / len(top), index=top)
    return {str(t): float(w[t]) for t in top}


class MomData:
    """Per-day ranking inputs derived from a Panel, all shifted correctly."""

    def __init__(self, p: Panel, spy: pd.DataFrame):
        self.p = p
        close = pd.DataFrame(p.close, index=p.dates, columns=range(len(p.tickers)))
        # momentum[t] = close[t-skip] / close[t-skip-lookback] - 1, per policy —
        # precompute per unique (lookback, skip) pair lazily
        self._close = close
        self._mom_cache: dict[tuple[int, int], np.ndarray] = {}
        # 63-day daily-return volatility for inv_vol weighting
        self.vol = close.pct_change().rolling(63).std().to_numpy()
        spy_close = spy["Close"].reindex(p.dates).ffill()
        self.spy_risk_on = (spy_close > spy_close.rolling(200).mean()).to_numpy()

    def momentum(self, lookback: int, skip: int) -> np.ndarray:
        key = (lookback, skip)
        if key not in self._mom_cache:
            shifted = self._close.shift(skip)
            self._mom_cache[key] = (shifted / shifted.shift(lookback) - 1).to_numpy()
        return self._mom_cache[key]


def simulate_momentum(md: MomData, pol: MomPolicy, start: pd.Timestamp,
                      end: pd.Timestamp, starting_cash: float = 100_000.0,
                      slippage_bps: float = 5.0):
    p = md.p
    mom = md.momentum(pol.lookback_days, pol.skip_days)
    day_idx = np.where((p.dates >= start) & (p.dates <= end))[0]
    slip = slippage_bps / 10_000.0

    cash = starting_cash
    shares = np.zeros(len(p.tickers))
    # episode bookkeeping for win-rate style metrics
    entry_px = np.full(len(p.tickers), np.nan)
    entry_day = np.zeros(len(p.tickers), dtype=int)
    trades: list[dict] = []
    equity_curve = []
    traded_notional = 0.0

    target_w: np.ndarray | None = None   # set at rebalance close, executed next open

    for step, d in enumerate(day_idx):
        px_open = p.open[d]
        # ── Execute yesterday's rebalance decision at today's open ──
        if target_w is not None:
            valid_px = ~np.isnan(px_open)
            equity_open = cash + float(np.nansum(shares * np.where(valid_px, px_open, 0.0)))
            target_shares = np.where(
                valid_px & (px_open > 0), target_w * equity_open / np.where(px_open > 0, px_open, 1.0), shares)
            delta = target_shares - shares
            # sells first (add cash), then buys
            for j in np.where(delta < -1e-9)[0]:
                fill = px_open[j] * (1 - slip)
                qty = -delta[j]
                cash += qty * fill
                traded_notional += qty * fill
                shares[j] = target_shares[j]
                if target_shares[j] <= 1e-9 and not np.isnan(entry_px[j]):
                    trades.append({
                        "ticker": p.tickers[j], "entry_date": p.dates[entry_day[j]],
                        "exit_date": p.dates[d], "entry": entry_px[j], "exit": fill,
                        "pnl_pct": (fill / entry_px[j] - 1) * 100, "reason": "rotation",
                        "setup": "momentum", "regime": p.regime[entry_day[j]],
                    })
                    entry_px[j] = np.nan
            buy_idx = np.where(delta > 1e-9)[0]
            need = float(np.sum(delta[buy_idx] * px_open[buy_idx] * (1 + slip))) if len(buy_idx) else 0.0
            scale = min(1.0, cash / need) if need > 0 else 1.0
            for j in buy_idx:
                fill = px_open[j] * (1 + slip)
                qty = delta[j] * scale
                cash -= qty * fill
                traded_notional += qty * fill
                was_flat = shares[j] <= 1e-9
                shares[j] += qty
                if was_flat:
                    entry_px[j], entry_day[j] = fill, d
            target_w = None

        # ── Mark to market at close ──
        px_close = p.close[d]
        pos_val = float(np.nansum(shares * np.where(np.isnan(px_close), 0.0, px_close)))
        equity_curve.append(cash + pos_val)

        # ── Rank at close on rebalance days; execute tomorrow ──
        if step % pol.rebalance_days == 0 and step < len(day_idx) - 1:
            m = mom[d].copy()
            eligible = ~np.isnan(m) & ~np.isnan(px_close)
            risk_on = True
            if pol.market_filter == "spy200" and not md.spy_risk_on[d]:
                risk_on = False
            w = np.zeros(len(p.tickers))
            # Hold top-k of whatever is eligible — a fixed >= top_n gate would
            # leave the portfolio permanently flat when one universe member
            # hasn't IPO'd yet (bit the equal-weight benchmark via DOW, 2019)
            k = min(pol.top_n, int(eligible.sum()))
            if risk_on and k >= 1:
                m[~eligible] = -np.inf
                top = np.argsort(m)[::-1][:k]
                if pol.weighting == "inv_vol":
                    iv = 1.0 / np.where(np.isnan(md.vol[d, top]) | (md.vol[d, top] <= 0),
                                        np.nan, md.vol[d, top])
                    iv = np.where(np.isnan(iv), np.nanmean(iv) if np.isfinite(np.nanmean(iv)) else 1.0, iv)
                    w[top] = iv / iv.sum()
                else:
                    w[top] = 1.0 / k
                exposure = pol.exposure_pct / 100.0
                if pol.regime_mode == "scale":
                    exposure *= REGIME_SCALE.get(p.regime[d], 0.5)
                w *= exposure
            target_w = w

    eq = pd.Series(equity_curve, index=p.dates[day_idx], name="equity")
    trades_df = pd.DataFrame(trades)
    metrics = compute_metrics(eq, trades_df, p)
    years = max(len(eq) / 252, 1e-9)
    metrics["turnover_x_per_year"] = round(traded_notional / starting_cash / years, 1)
    return eq, trades_df, metrics


def _equal_weight_benchmark(md: MomData, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Buy the whole universe equal-weight at start, hold. The bar rotation must clear."""
    # Quarterly re-equal-weight so names that IPO mid-window get picked up
    pol = MomPolicy(lookback_days=1, skip_days=0, top_n=len(md.p.tickers),
                    rebalance_days=63, weighting="equal", market_filter="none",
                    regime_mode="off")
    _, _, m = simulate_momentum(md, pol, start, end)
    return {k: m[k] for k in ("total_return_pct", "cagr_pct", "sharpe", "max_drawdown_pct")}


def run_tournament(start: str = "2013-01-01", end: str | None = None,
                   train_years: int = 4, test_years: int = 1,
                   holdout_months: int = 12, quick: bool = False,
                   tickers: list[str] | None = None, top_k: int = 12) -> dict:
    t0 = time.time()
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    universe = tickers or UNIVERSE
    hist = load_history(universe, start, end)
    market = load_history(MARKET_TICKERS, start, end)
    regimes = regime_series(market["SPY"], market["^VIX"])
    panel = Panel(hist, regimes)
    md = MomData(panel, market["SPY"])
    grid = quick_grid() if quick else default_grid()
    folds, holdout = _folds(panel.dates, train_years, test_years, holdout_months)
    if not folds:
        raise ValueError("Not enough history for a single train/test fold")

    log.info("research.momentum.start", policies=len(grid), folds=len(folds),
             universe=len(panel.tickers),
             holdout=f"{holdout[0].date()}..{holdout[1].date()}")

    test_scores: dict[str, list[dict]] = {}
    train_scores: dict[str, list[dict]] = {}
    by_label = {pol.label(): pol for pol in grid}

    for fi, (tr_s, tr_e, te_s, te_e) in enumerate(folds):
        for pol in grid:
            lab = pol.label()
            _, tr_trades, tr_m = simulate_momentum(md, pol, tr_s, tr_e)
            if tr_m.get("n_trades", 0) < MIN_EPISODES_PER_FOLD:
                continue
            _, _, te_m = simulate_momentum(md, pol, te_s, te_e)
            train_scores.setdefault(lab, []).append(tr_m)
            test_scores.setdefault(lab, []).append(te_m)
        log.info("research.momentum.fold_done", fold=fi + 1, of=len(folds),
                 elapsed_s=round(time.time() - t0, 1))

    leaderboard = []
    for lab, scores in test_scores.items():
        if len(scores) < len(folds):
            continue
        tr_sh = float(np.mean([s["sharpe"] for s in train_scores[lab]]))
        te_sh = float(np.mean([s["sharpe"] for s in scores]))
        leaderboard.append({
            "label": lab,
            "policy": asdict(by_label[lab]),
            "train_sharpe": round(tr_sh, 2),
            "test_sharpe": round(te_sh, 2),
            "overfit_gap": round(tr_sh - te_sh, 2),
            "test_cagr_pct": round(float(np.mean([s["cagr_pct"] for s in scores])), 2),
            "test_maxdd_pct": round(float(np.mean([s["max_drawdown_pct"] for s in scores])), 2),
            "test_turnover_x": round(float(np.mean([s["turnover_x_per_year"] for s in scores])), 1),
            "all_folds_positive": bool(all(s["sharpe"] > 0 for s in scores)),
        })
    leaderboard.sort(key=lambda r: r["test_sharpe"], reverse=True)

    # Benchmarks over the combined test era (first test start → holdout start)
    bench_start, bench_end = folds[0][2], holdout[0]
    spy = market["SPY"]["Close"]
    spy_span = spy[(spy.index >= bench_start) & (spy.index <= bench_end)]
    spy_ret = round(float(spy_span.iloc[-1] / spy_span.iloc[0] - 1) * 100, 2) \
        if len(spy_span) > 1 else None
    ew_bench = _equal_weight_benchmark(md, bench_start, bench_end)

    holdout_result = None
    # Quick mode is a smoke test — never let it touch the holdout, that shot
    # belongs to the full tournament's winner only.
    if leaderboard and not quick:
        winner = by_label[leaderboard[0]["label"]]
        _, ho_trades, ho_m = simulate_momentum(md, winner, holdout[0], holdout[1])
        spy_ho = spy[(spy.index >= holdout[0]) & (spy.index <= holdout[1])]
        holdout_result = {
            "policy": leaderboard[0]["label"],
            "metrics": ho_m,
            "spy_return_pct": round(float(spy_ho.iloc[-1] / spy_ho.iloc[0] - 1) * 100, 2)
            if len(spy_ho) > 1 else None,
            "equal_weight_universe": _equal_weight_benchmark(md, holdout[0], holdout[1]),
        }

    return {
        "meta": {
            "family": "cross-sectional momentum rotation (long-only top-N)",
            "span": f"{panel.dates.min().date()}..{panel.dates.max().date()}",
            "universe_size": len(panel.tickers),
            "policies_tested": len(grid),
            "policies_qualified": len(leaderboard),
            "folds": [f"{a.date()}..{b.date()} / test {c.date()}..{d.date()}"
                      for a, b, c, d in folds],
            "holdout": f"{holdout[0].date()}..{holdout[1].date()}",
            "spy_test_period_return_pct": spy_ret,
            "equal_weight_universe_test_period": ew_bench,
            "elapsed_s": round(time.time() - t0, 1),
            "caveats": [
                "survivorship-biased universe (picked today) — momentum rotation on survivors is FLATTERED more than most families, because losers that would have ranked high before dying are absent",
                "daily bars, 5bps slippage per dollar traded; weekly variants churn hard — check turnover_x_per_year before believing a Sharpe",
                "rotation must beat the equal-weight universe benchmark, not just SPY, to prove the ranking adds value over the universe itself",
            ],
        },
        "leaderboard": leaderboard[:top_k],
        "holdout": holdout_result,
    }


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", default="/tmp/momentum_report.json")
    args = ap.parse_args()

    report = run_tournament(quick=args.quick)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({"meta": report["meta"],
                      "top3": report["leaderboard"][:3],
                      "holdout": report["holdout"]}, indent=2, default=str))
