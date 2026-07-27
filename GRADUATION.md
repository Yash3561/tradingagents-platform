# Engine Graduation Scorecard

Living tracker for one question only: **is a strategy proven enough to trust
with real capital, or is it still a forward experiment?** Not a changelog
(see CLAUDE.md), not an incident log (see INCIDENTS.md) — just the scoreboard.

## Why this exists

2026-07-27: after finding and fixing a real production bug live, the
conversation drifted toward "let's make the base principal max by end of
month." That's the wrong frame — a calendar return deadline is exactly the
pressure that makes people override stops, oversize positions, and abandon
the discipline this platform hardcodes on purpose (5% max position, min
confidence gates, no forced trades). This file exists so "prove it out
longer" has a real finish line instead of turning into either an open-ended
wait or, worse, a deadline-driven risk override.

**Everything below runs on Alpaca paper money.** No engine graduates to real
capital from a number in this file alone — graduating is a separate,
deliberate decision, not an automatic unlock.

## The five criteria (all five must hold, not just one)

1. **Minimum live duration** — at least one full cycle of the engine's own
   rhythm: ~90 days for return/Sharpe-based engines in general; Momentum
   additionally needs ≥3 completed monthly rotations (not just 3 months
   elapsed, since a skipped rotation doesn't count).
2. **Beats the live Quant baseline, out-of-sample, in the same window** —
   not backtest, not vs. SPY. If an engine can't beat the zero-cost
   deterministic control group actually running in parallel, it hasn't
   proven anything beyond noise. (Quant itself is graded against SPY/EW
   benchmarks instead, since it has no baseline of its own.)
3. **Sharpe ≥ 1.0, sustained** — raw return alone is not enough; several of
   this platform's own tournaments (Momentum, insider-buying) found real
   return that was concentration or survivorship, not risk-adjusted edge.
4. **Survived at least one real drawdown untouched** — no operator
   intervention, no manual stop, no rule override mid-drawdown. A strategy
   that only ever ran through calm markets hasn't been tested.
5. **Enough independent trades to not be luck** — a handful of trades or a
   single walk-forward fold cannot be told apart from variance. Rough bar:
   ≥20 independent trade outcomes, or ≥3 non-overlapping walk-forward folds
   for anything not yet live.

Update this table monthly (or on request) by pulling current numbers from
Admin → Strategy Lab. Criteria 2 and 3 need a manual same-window pull —
Strategy Lab doesn't compute the paired comparison automatically yet.

## Scorecard (as of 2026-07-27)

| Engine | Live since | Days live | (1) Duration | (2) Beats Quant live | (3) Sharpe ≥1.0 | (4) Untouched drawdown | (5) Sample size | Status |
|---|---|---|---|---|---|---|---|---|
| Agents (Yash) | 2026-07-13 | 14 | ✗ (need ~90d) | not yet measured | not yet measured | not yet tested | 0 closed / 2 open — too early | **Forward experiment** |
| Quant | 2026-07-13 | 14 | ✗ (need ~90d) | n/a (is the baseline) | not yet measured | not yet tested | 0 closed / 15 open | **Forward experiment** |
| Earnings/PEAD (seemplyai) | 2026-07-17 | 10 | ✗ (need ~90d) | not yet measured | not yet measured | not yet tested | too early | **Forward experiment** — but strongest research pedigree (3 tournaments incl. 2 out-of-universe validations) of any engine here |
| Momentum | 2026-07-20 | 7 | ✗ (need ≥3 rotations, 1 done) | not yet measured | not yet measured | ✓ cleared once (-9.59% maxDD, left untouched 2026-07-2x) | too early | **Forward experiment** — own tournament already found alpha ≈ 0 vs equal-weight; return so far is concentration, treat with extra skepticism |
| PEAD Aggro (earnings, 25% sizing) | 2026-07-20 | 7 | ✗ | not yet measured | not yet measured | not yet tested | 0 closed / 1 open | **Forward experiment** |
| PEAD Options | 2026-07-21 | 6 | ✗ | not yet measured | not yet measured | not yet tested | 1 closed (bug-affected loss, bug now fixed — don't count this sample) | **Forward experiment**, effectively 0 clean samples |
| Intraday Rules | not currently live | — | — | — | — | — | — | **Failed** — two independent walk-forward rounds found no robust edge; correctly shelved, not deployed on any account |
| Insider-buying | research only | — | ✗ | n/a | not yet measured | untested | 1 walk-forward fold — explicitly "can't distinguish from luck" per its own report | **Not yet a live engine** — widening the historical window for a real multi-fold test is the next step before this even starts the clock |

## Ground rules while these are running

- No account gets a bigger position, a looser stop, or a lower confidence
  gate to "help" it hit a number. If a criterion isn't met, the answer is
  "wait," not "adjust the rule."
- A drawdown is data, not an emergency — don't manually close a position
  just because the account is behind. (See Momentum, 2026-07-2x.)
- Small sample sizes are not evidence. A good week is not graduation.
- If a strategy fails criterion 2 or 3 over a full window, that's a real
  result — retire it from live paper trading rather than letting it run
  indefinitely for no reason.
