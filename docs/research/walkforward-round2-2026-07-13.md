# Walk-Forward Tournament — Round 2 (2026-07-13)

386 policies · 7 folds · 2013-01-02..2026-07-10 · holdout 2025-07-11..2026-07-10
Entries pinned to the round-1 winning plateau; new dimensions: **exits**
(trailing stops, 30-day time exits) and **portfolio construction** (5/8/10%
sizes, 8/16 slots, regime gate vs regime-scaled exposure vs regime-blind).

## Headline

**The round-1 winner defended its title against all 384 new variants**:
`trend[40-65] mr[<=32] exit[rsi>=78] stop[3.0xATR,rr3.0] off pos5%x8`
— mean test Sharpe **0.82** with a **0.00 overfit gap** (train 0.82 = test 0.82).

## Leaderboard (mean TEST Sharpe across 7 folds; live baseline ranked 200/386)

| # | Policy | Test Sharpe | Gap | CAGR | MaxDD | WR | Trades/fold |
|---|--------|------------|-----|------|-------|-----|------|
| 1 | 40-65 mr32 3xATR rr3 **off** 5%x8 | 0.82 | 0.00 | 4.55% | −5.3% | 36.9% | 112 |
| 2 | 40-65 mr36 rr3 **t30d scale** 5%x8 | 0.62 | −0.08 | 2.91% | −4.3% | 39.9% | 141 |
| 3 | same, 8% | 0.62 | −0.08 | 4.72% | −6.9% | 39.9% | 141 |
| 4 | same, 10% | 0.62 | −0.07 | 5.94% | −8.5% | 39.9% | 141 |
| 5 | 40-65 mr32 rr3 **scale** 5%x8 | 0.56 | 0.15 | 2.67% | −4.0% | 36.9% | 112 |
| 6 | same, 8% | 0.56 | 0.15 | 4.33% | −6.3% | 36.9% | 112 |
| 7 | same, 10% | 0.56 | 0.15 | 5.41% | −7.9% | 36.9% | 112 |
| 8 | 40-70 mr32 rr3 scale 8%x16 | 0.56 | 0.24 | 9.32% | −12.5% | 38.0% | 213 |
| 9 | 40-70 mr36 rr3 t30d gate 5%x8 | 0.56 | −0.12 | 2.41% | −4.0% | 40.1% | 131 |
| 10 | same, 8% | 0.56 | −0.12 | 2.41% | −4.0% | 40.1% | 131 |

## Findings

1. **Trailing stops hurt** — zero trailing variants in the top 10. They cut
   winners before the 3:1 target pays. This rule family needs its right tail.
2. **Time exits trade Sharpe for win rate** — 30-day exits raise WR ~3pts and
   lower Sharpe ~0.2. Not worth it.
3. **Sizing is leverage, not alpha** — ranks 2-4 and 5-7 have IDENTICAL Sharpe
   across 5/8/10% sizing; CAGR and drawdown scale together. Rank 8 shows the
   ceiling: 9.3% CAGR at −12.5% DD and the worst overfit gap (0.24).
4. **Regime-blind beat regime-scaled beat regime-gated** for this entry family
   over this span (a bull-heavy decade — treat with suspicion in bear regimes).

## Actions

- Round-1/2 winner deployed to the live Quant account via the new
  settings-driven policy profile (`quant_*` keys; see quant_baseline.py).
- If more CAGR is wanted at equal Sharpe, raising `position_size_pct` on the
  same policy is the honest lever — with proportional drawdown.

Regenerate the full JSON: `docker exec tap_backend python -m app.research.run --start 2013-01-01`
(report lands in /tmp/research_report.json inside the container — copy it out
before rebuilding the image, /tmp does not survive a rebuild).
