# Cross-Sectional Momentum Rotation — Walk-Forward Tournament (2026-07-18)

**Question:** does rotating into the strongest names (relative momentum, top-N,
fixed rebalance) clear the out-of-sample bar that the intraday rule family failed
twice? New module: `app/research/momentum.py` (grid of 288 policies: lookback
63/126/252d, skip 0/21d, top 4/8/12, weekly/monthly rebalance, equal/inverse-vol
weighting, optional SPY-MA200 filter and regime scaling). Same honesty rules as
`engine.py`: rank on close t, fill at open t+1, 5bps per dollar traded.

**Answer: real selection ability on broad universes, but the risk-adjusted edge
over simply holding the universe is ~zero in the test era — the extra return is
concentration, and survivorship bias flatters this family more than any other.
Status: forward-paper-trade candidate, NOT a validated edge.**

## Tournament (59-ticker fitting universe, 2016–2026, 4 folds, 12mo holdout)

- Winner: `mom[126-0] top4 rb21d inv_vol` — 6-month lookback, no skip, top-4,
  monthly rebalance, inverse-vol weights, no market filter.
- Mean TEST Sharpe across folds **1.29** (all 4 folds positive), overfit gap 0.20,
  test CAGR 34.4%, maxDD −14.6%, turnover 12.8×/yr.
- The top of the leaderboard is a broad plateau (rank-2 `mom[63-21] top12 rb5d
  inv_vol` has gap 0.01) — not a single lucky spike. Market filters and regime
  scaling *hurt* in this era (they mostly cost upside).
- Holdout (12mo, one shot): **+132.7%, Sharpe 1.97, maxDD −23.7%** vs equal-weight
  universe +35.4% (Sharpe 1.93) and SPY +19.8%.
- Process note: an early `--quick` smoke run also executed the holdout path for a
  4-policy subset before the full tournament ran (bug, fixed the same hour —
  quick mode can no longer touch the holdout). The grid was not modified after
  that peek; the full tournament used the identical grid designed beforehand.

## Validation 1 — disjoint defensive universe (76 names, no overlap): FAIL

Winner unmodified on banks/insurers/REITs/energy/materials/biotech/utilities/
transport/staples:

| Window | Winner | Equal-weight same universe |
|---|---|---|
| 2017–2025 | Sharpe 0.28, CAGR 3.8%, maxDD −37% | Sharpe 0.68, CAGR 10.9% |
| 2025–2026 | **+2.1%**, Sharpe 0.20, maxDD −18.5% | **+26.4%**, Sharpe 2.36 |

On a universe without strong trenders, top-4 momentum whipsaws and destroys value
outright.

## Validation 2 — union universe (135 names, winner must find the leaders): PASS

| Window | Winner | Equal-weight union |
|---|---|---|
| 2017–2025 | **+606%**, CAGR 25.8%, Sharpe 0.93, maxDD −40.5% | +238%, CAGR 15.4%, Sharpe 0.91 |
| 2025–2026 | **+127%**, Sharpe 1.97 | +25.2%, Sharpe 2.43 |

Given the full mixed opportunity set, the ranking rediscovers the strong names by
itself — the defensive-universe failure is "no leaders to pick," not "ranking is
noise." Turnover rises to ~54×/yr on the wide universe (≈0.5%/yr at 5bps; more at
real spreads).

## Honest read

1. **Selection is real, risk-adjusted alpha is not (yet).** Test-era Sharpe 0.93
   vs 0.91 for holding the union universe — the return amplification comes from
   concentration (top-4 ≈ a leverage knob, echoing round-2's "sizing is leverage
   not alpha"). The holdout year's massive excess (+127% vs +25%) is one year of
   riding the era's monsters — exactly what survivorship-biased backtests
   overstate.
2. **Survivorship bias is worst-case for this family.** The universe was picked
   today; names that ranked top-4 and then died are absent by construction. Treat
   every absolute number above as an upper bound.
3. **Deployment posture:** worth a forward paper arm (zero LLM cost, one decision
   per month) sized modestly, judged against an equal-weight benchmark of the same
   universe — NOT worth believing the +132% holdout. If forward months keep
   beating the equal-weight benchmark, size up gradually.

Reports: `momentum-walkforward-2026-07-18.json` (full tournament).
Reproduce: `python -m app.research.momentum` (PYTHONPATH=backend, needs Alpaca
data keys or falls back to yfinance).
