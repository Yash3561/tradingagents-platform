# Intraday Round 2 — 5-Minute Walk-Forward Tournament on 2 Years of Alpaca Bars (2026-07-16)

**Question:** does any deterministic intraday rule family clear **$200/day on $100K**
out-of-sample, long-only, flat by the close, after slippage — now tested on real
multi-regime history instead of round 1's 60-day single-regime window?

**Answer: NO — more conclusively than round 1.** The most "robust"-looking policy in
the entire 1,134-policy grid (the only one with all 6 folds positive) still loses
**−$275.50/day** on the one-shot holdout, with a **−$13,778 max drawdown (−13.8% of
equity)** — roughly 7x worse than round 1's holdout drawdown.

## Setup

- Data: **Alpaca 5m bars via the account's own working keys**, 2 years, 30 liquid
  large-caps, 501 trading sessions, 1.17M bars. Multi-regime (bull/bear/chop/high-vol),
  fixing round 1's single-regime blind spot.
- 1,134 policies (3x round 1's grid): ORB (15/30m) / VWAP mean-reversion / 20-bar
  momentum, × stops (1–2.5 ATR) × R:R (1.5–3) × time exits × a new `entry_window`
  dimension (all-day / first-90-min / no-midday).
- Same honest-fill protocol as round 1 (signal close → next-bar open, stop-first
  intrabar, 3bps/side slippage, force-flat 15:55 ET).
- Fold sizing scaled up with the deeper data: **6 folds × 20-day test slices + a
  40-day one-shot holdout** (vs round 1's 4×5d/10d).

## Results

- **All 1,134 policies qualified** (min-trade filter easily met — signals are dense).
- Every top-25 leaderboard row has a **strongly negative overfit gap** (mean −$150.74/day,
  range −$86 to −$191): test folds outperform train folds by ~$100–190/day across the
  board — the same "period luck, not edge" signature as round 1, now on a 3-year-larger
  sample.
- The winner-selection rule picks the highest-test-return policy among those with
  **zero losing test folds** (robustness bar), searched across the full 1,134-policy
  grid (only the top 25 are exported to the leaderboard, so it's not visible whether
  others qualify further down): `orb30 vol>=1.0 vwap+ stop2.5atr rr1.5 hold<=36
  risk1.0% x3` — ranked 25th by raw test return overall, test mean $57.91/day,
  Sharpe 1.43, but still a −$174.88/day overfit gap (in line with the rest of the
  leaderboard) and wildly inconsistent fold-to-fold ($1–130/day test, always negative
  train).
- **That policy is the round-2 winner by construction** (all-folds-positive is the
  tournament's robustness bar) — and it's the one burned on the holdout:
  **−$275.50/day mean, Sharpe −5.50, 35% winning days, −$13,778 max drawdown, P(day ≥
  $200) = 0.20.**
- Top-raw-return policies (not selected as winner — `first90`-window ORB variants,
  ~$96–98/day test) have gaps just as negative and were never holdout-tested; they're
  shown for context only, not validated.

## Implications

1. **This isn't a data-quantity problem anymore.** Round 1 could be waved off as "60
   days, one regime, inconclusive." Round 2 used 2 years across regimes, 3x the grid,
   and the single most conservatively-selected policy in the whole family still
   produced the worst tail result seen yet. The evidence now points at **no exploitable
   edge in this deterministic 5m rule family**, not insufficient sample size.
2. **The live intraday engine is NOT running this round's "winner."** Its current
   defaults (`mom20 stop1.5atr rr2 holdEOD` at 0.5% risk) come from round 1, not this
   ORB30 policy — so nothing needs to change mechanically. But round 2's holdout
   drawdown (−13.8% of equity at 1% risk) is a materially worse worst-case than round 1
   surfaced, and it comes from the *most* robust-looking candidate in a 3x larger
   search. That raises the bar for trusting any policy from this family, including the
   one currently live.
3. **Recommendation: do not deploy any round-2 parameter set live.** The honest
   takeaway across two independent tournaments is that this rule family (ORB / VWAP
   mean-reversion / momentum continuation on 5m bars, long-only, flat-by-close) doesn't
   clear $200/day out of sample — Round 2's answer is more confident, not less, than
   Round 1's. Worth a real conversation about whether the intraday arm continues as a
   small forward-only experiment at current conservative risk, or is paused pending a
   genuinely different edge source (order flow, alt data, faster execution) rather than
   further re-tuning within the same family.

Full leaderboard + holdout dailies: `intraday-walkforward-round2-2026-07-16.json`.
Engine/protocol code: `backend/app/research/intraday.py` (same signal code the live
engine imports — no live/backtest drift). Round 1: `intraday-walkforward-2026-07-14.md`.
