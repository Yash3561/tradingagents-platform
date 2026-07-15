# Intraday Round 1 — 5-Minute Walk-Forward Tournament (2026-07-14)

**Question:** does any deterministic intraday rule family clear **$200/day on $100K**
out-of-sample, long-only, flat by the close, after slippage?

**Answer: NO.** Not in this family, on this data, at 1% risk with no leverage.

## Setup

- Data: yfinance 5m bars, 60 trading days (2026-04-17 → 2026-07-14), 30 liquid
  large-caps. **One market regime** — treat everything below as provisional.
- 378 policies: ORB (15/30m), VWAP mean-reversion (1.5–2.5 ATR stretch),
  20-bar-high momentum × stops (1–2.5 ATR) × R:R (1.5–3) × time exits.
- Honest fills: signal on close → next bar open, stop-first intrabar, 3bps/side,
  entries stop after 15:00 ET, force-flat 15:55 ET, max 6 trades/day,
  3 concurrent, 25% notional cap, 100% gross cap (no leverage).
- 4 time-ordered folds + 10-day one-shot holdout (winner only).

## Results

- Top test-fold performer: `mom20 stop1.0atr rr3.0 holdEOD risk1.0%` at
  **+$106/day** across test folds… then **−$133/day on the holdout**,
  max drawdown −$2,062, 40% winning days. The holdout is burned for this round.
- Overfit gaps are large and NEGATIVE across the leaderboard (train much worse
  than test) — test-fold outperformance was **period luck, not edge**.
- Every leaderboard row hit the 6-trades/day cap: signals are dense, so results
  are ~"buy momentum 6× a day" — no selectivity advantage.
- Most robust-looking profiles (all folds positive, low gap, Sharpe > 2):
  `mom20 stop1.5atr rr2.0 holdEOD` (~$63/day test) and
  `vwaprev 1.5atr rr1.5 hold≤12` (~$52/day test, 55% win days). **Unvalidated**
  — holdout was already spent on the failed #1.

## Implications

1. **$200/day is not honestly reachable** from this family at 1% risk / no
   leverage. Scaling risk 4× to force the number also scales the −$2K holdout
   drawdowns to −$8K — fails the robustness requirement.
2. The live intraday engine ships with the robust-profile defaults at 0.5% risk
   and a 0.5% daily loss halt — as a **forward experiment arm**, not an income
   promise.
3. The real unlock is **years of minute bars from Alpaca** (needs working API
   keys; local .env keys are stale/401). yfinance's 60-day window cannot
   distinguish edge from regime luck. Rerun this tournament on 2+ years before
   trusting any intraday policy.

Full leaderboard + holdout dailies: `intraday-walkforward-2026-07-14.json`.
Engine/protocol code: `backend/app/research/intraday.py` (same signal code the
live engine imports — no live/backtest drift).
