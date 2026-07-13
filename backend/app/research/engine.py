"""
Policy simulator — the quant baseline rule family, parameterized and run
against history with honest execution mechanics:

- Signals are computed on day t's CLOSE; entries fill at day t+1's OPEN
  (no lookahead — you cannot trade a close you haven't seen).
- Stops / take-profits trigger intraday off the day's High/Low; when both
  are inside one bar the STOP is assumed to fill first (conservative).
- Slippage charged on every fill; commissions are zero (Alpaca).

The rule shapes mirror app/agents/quant_baseline.py so that whatever wins
here is directly deployable as live settings.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass(frozen=True)
class Policy:
    """One experiment arm. Defaults = the live quant baseline."""
    trend_rsi_min: float = 45.0
    trend_rsi_max: float = 70.0
    require_macd: bool = True
    meanrev_rsi_max: float = 32.0
    allow_trend: bool = True
    allow_meanrev: bool = True
    exit_rsi: float = 78.0
    exit_on_ma200_break: bool = True
    stop_atr_mult: float = 2.0
    rr_ratio: float = 2.0
    regime_gate: bool = True          # no new BUYs in BEAR_TRENDING / HIGH_VOLATILITY
    position_pct: float = 5.0         # % of equity per position
    max_positions: int = 8

    def label(self) -> str:
        return (f"trend[{self.trend_rsi_min:.0f}-{self.trend_rsi_max:.0f}"
                f"{',macd' if self.require_macd else ''}]"
                f"{'' if self.allow_trend else 'OFF'}"
                f" mr[<={self.meanrev_rsi_max:.0f}]{'' if self.allow_meanrev else 'OFF'}"
                f" exit[rsi>={self.exit_rsi:.0f}] stop[{self.stop_atr_mult:.1f}xATR"
                f",rr{self.rr_ratio:.1f}] {'gate' if self.regime_gate else 'nogate'}"
                f" pos{self.position_pct:.0f}%x{self.max_positions}")


class Panel:
    """All price/indicator data as [day, ticker] float matrices."""

    def __init__(self, history: dict[str, pd.DataFrame], regimes: pd.Series):
        self.tickers = sorted(history)
        # Union calendar of all tickers, aligned; NaN where a ticker didn't trade
        idx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in history.values()])))
        self.dates = idx

        def mat(col: str) -> np.ndarray:
            return np.column_stack([
                history[t][col].reindex(idx).to_numpy() for t in self.tickers
            ])

        self.open, self.high = mat("Open"), mat("High")
        self.low, self.close = mat("Low"), mat("Close")

        c = pd.DataFrame(self.close, index=idx)
        self.ma50 = c.rolling(50).mean().to_numpy()
        self.ma200 = c.rolling(200).mean().to_numpy()

        delta = c.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        self.rsi = (100 - 100 / (1 + gain / loss.replace(0, np.nan))).fillna(50.0).to_numpy()

        macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
        self.macd_bull = (macd > macd.ewm(span=9, adjust=False).mean()).to_numpy()

        h = pd.DataFrame(self.high, index=idx)
        low_df = pd.DataFrame(self.low, index=idx)
        # Simplified ATR (H-L mean), matching the live data fetcher
        atr = (h - low_df).rolling(14).mean().to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            self.atr_pct = np.where(self.close > 0, atr / self.close * 100, np.nan)

        self.chg_1w = c.pct_change(5).to_numpy() * 100

        self.regime = regimes.reindex(idx).ffill().fillna("SIDEWAYS").to_numpy()
        self.no_buy = np.isin(self.regime, ["BEAR_TRENDING", "HIGH_VOLATILITY"])
        # Regime-scaled position caps, mirroring regime_detector strategy blocks
        caps = {"BULL_TRENDING": 5.0, "SIDEWAYS": 3.0,
                "BEAR_TRENDING": 2.0, "HIGH_VOLATILITY": 1.5}
        self.regime_cap = np.vectorize(caps.get)(self.regime).astype(float)


def entry_signals(p: Panel, pol: Policy) -> np.ndarray:
    """Boolean [day, ticker] — a BUY signal at that day's close."""
    valid = ~np.isnan(p.close) & ~np.isnan(p.ma200) & ~np.isnan(p.rsi)
    above50 = p.close > p.ma50
    above200 = p.close > p.ma200
    trend = (above50 & (p.ma50 > p.ma200)
             & (p.rsi >= pol.trend_rsi_min) & (p.rsi <= pol.trend_rsi_max))
    if pol.require_macd:
        trend &= p.macd_bull
    meanrev = above200 & (p.rsi <= pol.meanrev_rsi_max) & (p.chg_1w < 0)

    sig = np.zeros_like(p.close, dtype=bool)
    if pol.allow_trend:
        sig |= trend
    if pol.allow_meanrev:
        sig |= meanrev
    if pol.regime_gate:
        sig &= ~p.no_buy[:, None]
    return sig & valid


@dataclass
class SimResult:
    policy: dict
    label: str
    equity: pd.Series = field(repr=False)
    trades: pd.DataFrame = field(repr=False)
    metrics: dict = field(default_factory=dict)


def simulate(p: Panel, pol: Policy, start: pd.Timestamp, end: pd.Timestamp,
             starting_cash: float = 100_000.0, slippage_bps: float = 5.0) -> SimResult:
    sig = entry_signals(p, pol)
    day_idx = np.where((p.dates >= start) & (p.dates <= end))[0]
    slip = slippage_bps / 10_000.0

    cash = starting_cash
    # ticker_index -> [qty, entry_px, stop_px, tp_px, entry_day, setup_meanrev]
    positions: dict[int, list] = {}
    equity_curve, trades = [], []

    for d in day_idx:
        # ── Exits first: stops / take-profits intraday, rule exits at close ──
        for j in list(positions):
            qty, entry_px, stop_px, tp_px, e_day, is_mr = positions[j]
            if np.isnan(p.close[d, j]):
                continue
            exit_px, reason = None, None
            lo, hi = p.low[d, j], p.high[d, j]
            if lo <= stop_px:                      # stop assumed to fill first
                exit_px, reason = stop_px * (1 - slip), "stop"
            elif hi >= tp_px:
                exit_px, reason = tp_px * (1 - slip), "take_profit"
            elif pol.exit_on_ma200_break and not np.isnan(p.ma200[d, j]) \
                    and p.close[d, j] < p.ma200[d, j]:
                exit_px, reason = p.close[d, j] * (1 - slip), "trend_break"
            elif p.rsi[d, j] >= pol.exit_rsi:
                exit_px, reason = p.close[d, j] * (1 - slip), "overbought"
            if exit_px is not None:
                cash += qty * exit_px
                trades.append({
                    "ticker": p.tickers[j], "entry_date": p.dates[e_day],
                    "exit_date": p.dates[d], "entry": entry_px, "exit": exit_px,
                    "pnl_pct": (exit_px / entry_px - 1) * 100, "reason": reason,
                    "setup": "mean_reversion" if is_mr else "trend_follow",
                    "regime": p.regime[e_day],
                })
                del positions[j]

        # Mark to market
        pos_val = sum(q * p.close[d, j] for j, (q, *_ ) in positions.items()
                      if not np.isnan(p.close[d, j]))
        equity = cash + pos_val
        equity_curve.append(equity)

        # ── Entries: yesterday's signals fill at today's open ──
        if d == day_idx[0]:
            continue
        yd = d - 1
        if len(positions) >= pol.max_positions:
            continue
        candidates = np.where(sig[yd])[0]
        # Strongest dips first for mean reversion, then lowest RSI generally
        candidates = candidates[np.argsort(p.rsi[yd, candidates])]
        for j in candidates:
            if len(positions) >= pol.max_positions:
                break
            if j in positions or np.isnan(p.open[d, j]):
                continue
            atr_pct = p.atr_pct[yd, j]
            stop_pct = float(np.clip(pol.stop_atr_mult * atr_pct, 3.0, 8.0)) \
                if not np.isnan(atr_pct) else 7.0
            tp_pct = pol.rr_ratio * stop_pct

            cap = min(pol.position_pct, p.regime_cap[yd]) if pol.regime_gate \
                else pol.position_pct
            is_mr = bool(p.close[yd, j] > p.ma200[yd, j] and p.rsi[yd, j] <= pol.meanrev_rsi_max
                         and p.chg_1w[yd, j] < 0)
            if is_mr:
                cap /= 2  # counter-trend entries get half size, as in live rules
            budget = equity * cap / 100
            px = p.open[d, j] * (1 + slip)
            qty = int(budget // px)
            if qty <= 0 or qty * px > cash:
                continue
            cash -= qty * px
            positions[j] = [qty, px, px * (1 - stop_pct / 100),
                            px * (1 + tp_pct / 100), d, is_mr]

    eq = pd.Series(equity_curve, index=p.dates[day_idx], name="equity")
    return SimResult(policy=asdict(pol), label=pol.label(), equity=eq,
                     trades=pd.DataFrame(trades), metrics=compute_metrics(eq, pd.DataFrame(trades), p))


def compute_metrics(eq: pd.Series, trades: pd.DataFrame, p: Panel) -> dict:
    if len(eq) < 2:
        return {"error": "no data"}
    rets = eq.pct_change().dropna()
    years = len(eq) / TRADING_DAYS
    total = eq.iloc[-1] / eq.iloc[0] - 1
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 else 0.0
    sharpe = float(rets.mean() / rets.std() * np.sqrt(TRADING_DAYS)) if rets.std() > 0 else 0.0
    dd = float((eq / eq.cummax() - 1).min())

    out = {
        "total_return_pct": round(total * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown_pct": round(dd * 100, 2),
        "n_trades": int(len(trades)),
        "win_rate_pct": round(float((trades["pnl_pct"] > 0).mean() * 100), 1) if len(trades) else None,
        "avg_trade_pct": round(float(trades["pnl_pct"].mean()), 2) if len(trades) else None,
    }

    # Universality check: performance sliced by the regime each trade was opened in
    if len(trades):
        by_regime = {}
        for reg, grp in trades.groupby("regime"):
            by_regime[reg] = {
                "n": int(len(grp)),
                "win_rate_pct": round(float((grp["pnl_pct"] > 0).mean() * 100), 1),
                "avg_trade_pct": round(float(grp["pnl_pct"].mean()), 2),
            }
        out["by_regime"] = by_regime
        by_setup = {}
        for s, grp in trades.groupby("setup"):
            by_setup[s] = {
                "n": int(len(grp)),
                "win_rate_pct": round(float((grp["pnl_pct"] > 0).mean() * 100), 1),
                "avg_trade_pct": round(float(grp["pnl_pct"].mean()), 2),
            }
        out["by_setup"] = by_setup
    return out
