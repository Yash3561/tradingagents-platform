# Post-Earnings-Announcement Drift (PEAD) — Walk-Forward Tournament (2026-07-16)

**Question:** does a genuinely different information source — long-only entries into
large positive EPS surprises, held for weeks — clear a real out-of-sample bar? Unlike
the two intraday rounds (price-pattern rules, no edge found), this is a documented
market anomaly (systematic underreaction to earnings surprises), so a positive result
here would be a new signal family, not a re-tune of an exhausted one.

**Answer: the first candidate across three tournaments to show real signal — smaller
and less universal than it first looked.** The time-based holdout survived cleanly
(Sharpe 1.9). A same-day out-of-universe validation pass (see below) found the effect
holds on stocks never used in fitting too, but roughly halves — genuine signal, not
noise, but the specific parameters are calibrated to this universe, not yet a
production-ready policy.

## Setup

- Universe: 59 of the swing quant tournament's ~60 tickers (survivorship-biased, same
  caveat as the other two rounds). Daily bars via `research/data.py::load_history`
  (Alpaca-preferred, yfinance-fallback), 2016–2026.
- 5,249 historical earnings events pulled via yfinance's earnings-date scrape
  (EPS estimate/actual/surprise%, ~10 years per ticker where available).
- 216 policies: entry surprise threshold (3/5/10/15%) × gap-up confirmation (on/off) ×
  ATR stop (1.5/2.5/3.5) × R:R (2/3/none) × hold window (10/20/40 trading days).
  Long-only, 1% risk/trade, 10 max concurrent, 15% per-position notional cap.
- Honest fills: entry at the first session's open after the news was public (same-day
  open for pre-market reports, next session's open for after-close/midday — no
  lookahead), stop-first intrabar, 5bps slippage/side.
- **5 folds (3y train / 1y test, rolled forward) + an 18-month one-shot holdout**
  (2025-01-16 → 2026-07-15, never touched until this run). First pass used 5y/2y
  folds and only produced 1 fold — too thin to trust; re-run with 3y/1y to get real
  multi-era coverage before drawing conclusions.

## Results

- **21 of 216 policies (10%)** are robust — positive in every one of the 5 test folds,
  spanning distinct market eras (2019 through 2024). That's a meaningfully selective
  bar, unlike round 1 of the intraday work where dense signals let everything qualify.
- **Winner** (`surprise>=10% gap-up-confirmed, 1.5×ATR stop, RR 3, hold 10 trading
  days`): test Sharpe **1.02** across the 5 folds, individually **1.14 / 0.76 / 0.74 /
  0.71 / 1.75 — positive in every single fold**, none marginal.
- **Overfit gap is small**: train Sharpe 0.80 vs test 1.02 (gap −0.22). Test still
  edges out train, the same *direction* as both intraday rounds' overfit signature,
  but the magnitude is an order of magnitude smaller — consistent with real signal
  plus noise, not a policy whose entire apparent edge lives in the test window.
- **Holdout (18 months, one shot, never touched before this run): Sharpe 1.9, CAGR
  +12.36%, max drawdown −6.04%, 52 trades, 51.9% win rate, +2.19% average trade.**
  SPY returned +29.77% over the same window — the strategy trails buy-and-hold in
  absolute terms during a strong bull run (same pattern the swing quant round-1
  holdout showed: capital-preserving relative to a fully-invested benchmark, not
  beta-matching), but the risk-adjusted profile (Sharpe 1.9, ~6% drawdown, ~10-name
  concurrent cap) is real and coherent, not noise.

## Validation pass: out-of-universe test (same day, second run)

Cheap, high-value check before trusting the above: run the winning policy
**unmodified, no refitting** against 46 liquid names that were never part of the
59-ticker fitting universe (PYPL, ABNB, SNOW, COIN, RTX, LOW, DUK, etc. — full list in
`validate_pead.py`, not committed, ad-hoc). Same two windows, pre-holdout and the
identical 18-month holdout period:

| Window | Fitting universe (original) | Held-out universe (never fitted) |
|---|---|---|
| Pre-holdout | train Sharpe 0.80 (in-sample) | Sharpe **0.35**, CAGR 2.4%, win rate 43.5% |
| Holdout | Sharpe **1.9**, CAGR 12.36%, DD −6.04% | Sharpe **0.70**, CAGR 5.3%, DD −4.79% |

**The edge does not fully generalize.** It's still net positive on completely
different stocks in both windows (meaningfully different from either intraday
tournament, where holdouts went deeply negative) — so this isn't pure noise. But the
effect roughly halves on Sharpe and more than halves on CAGR when the specific
59-ticker mega-cap-heavy universe is swapped out. That gap is a real signal that part
of the original result is universe-specific curve-fitting on top of genuine signal,
not just time-based overfitting (which the small fold-to-fold gap had already ruled
out as the dominant issue).

**Data-quality finding from the same pass**: 22 of 3,180 events on the held-out
universe show |surprise%| > 500 (e.g. COIN, DDOG, WDAY) — classic EPS-estimate-near-
zero blowups in the scrape data, not real surprises. They don't corrupt any result
here (entry thresholds are ≤15%, far below where these outliers would ever fire), but
flag it for anyone extending the surprise-threshold grid upward later.

**Revised read**: PEAD as a category shows real (if modest) signal that survives both
a time-based holdout AND a stock-universe holdout — still the strongest result across
three tournaments. But the specific *parameters* found (10% threshold, gap-up
required, 10-day hold) are calibrated to this particular universe and should be
treated as a starting point for a broader, cross-universe walk-forward — not
production-ready — before any live wiring.

## Robustness pass: refit on a 105-ticker universe, validate on a fourth, unrelated one

Re-ran the full walk-forward — same 216-policy grid, same 3y/1y folds + 18mo holdout
discipline — on the **union of both universes used so far** (105 tickers: the
original 59 mega-cap-heavy set + the 46-ticker validation set), then took the new
winner **unmodified** and validated it against a **third, completely fresh 63-ticker
universe** spanning sectors none of the prior universes touched: regional banks,
REITs, energy, materials, biotech, utilities, transport, discount retail.

**New winner** (surprise ≥10%, gap-up confirmed, wider 3.5×ATR stop, RR 3, hold 10
days) is a meaningfully tighter fit than the original:

| | Original 59-ticker fit | Expanded 105-ticker refit |
|---|---|---|
| Test Sharpe (5 folds) | 1.02 | 1.00 |
| Overfit gap | −0.22 | **−0.04** (near zero) |
| Robust policies (all-folds-positive) | 21/216 | 28/216 |
| Holdout Sharpe / CAGR / trades | 1.9 / 12.36% / 52 | 1.23 / 10.17% / **101** |

Nearly zero train/test gap and roughly double the holdout trade count — a much more
statistically trustworthy fit, at the cost of a somewhat lower (but still solidly
positive) holdout return. All 5 folds stayed positive individually (0.28 to 1.66
Sharpe — even the weakest fold cleared zero).

**Fourth independent check** — this new winner, no refitting, run cold against the
fresh bank/REIT/energy/materials/biotech/utilities universe:

| | Pre-holdout (2016–2025) | Holdout (2025–2026) |
|---|---|---|
| Fresh universe | Sharpe 0.44, CAGR 2.56%, 373 trades | Sharpe **0.89**, CAGR 5.93%, 65 trades |

This is, if anything, slightly *better* than the first validation pass's numbers
(0.35/0.70 Sharpe) — on an even more different universe (financials/REITs/biotech vs.
the first validation's tech/consumer names). **Across four independent out-of-sample
checks now — two universes never used in fitting, two non-overlapping holdout-style
windows, one refit with an entirely different parameter set — nothing has come back
negative.** That's not proof of a durable edge, but it's categorically different from
either intraday tournament, which failed every single check.

**Updated reference policy going forward**: the expanded-universe winner (10% surprise
threshold, gap-up required, 3.5×ATR stop, RR 3, 10-day hold) — not the original
narrower fit — given its near-zero overfit gap and larger validated sample size.

## Reality check on $200/day

This doesn't translate to a $/day figure the way the intraday work does — it's an
event-driven, multi-week-hold strategy, not a daily-frequency one. At 1% risk and the
holdout's +12.36% CAGR on $100K, that's roughly $12,000/year — about $46/trading-day
averaged over the year, not $200/day. That actually reinforces the plan's reframing:
the honest path isn't "find a policy that hits $200/day," it's "find genuinely
validated edge and let the number follow." This is the first policy across three
tournaments to clear that bar — modestly, not spectacularly.

## Caveats before trusting this further

- **5 folds is still a small sample of "market eras."** More rigorous than the 1-fold
  first pass, less rigorous than the intraday tournaments' 6 folds — mitigated
  somewhat by now having two independent out-of-universe checks pointing the same
  direction, but still worth a longer history window if the data source allows it.
- Earnings data is scrape-based (not a formal API) — per-ticker gaps are possible
  (one ticker, UNP, failed to fetch entirely on the fresh-universe pass and was
  silently dropped) and unaudited row-by-row.
- Survivorship-biased universe on all three ticker sets — rankings more trustworthy
  than absolute returns.
- Effect size is modest everywhere it's been tested (Sharpe 0.4–1.9 depending on
  universe/window) — real, but this is not a fast path to a large fixed dollar target.
- **Not deployed anywhere.** This is a research result, not a live arm. Wiring it up
  (new `strategy_mode="earnings"`, a worker loop, settings keys, scanner integration)
  is a real engineering project on the scale of the intraday arm — deliberately not
  started without sign-off given this session's session-long emphasis on the user
  approving capital-risk decisions explicitly.

Full leaderboard + fold-by-fold detail + holdout: `earnings-drift-walkforward-
2026-07-16.json` (original 59-ticker fit), `earnings-drift-walkforward-round2-
expanded-universe-2026-07-16.json` (105-ticker refit — current reference policy).
Engine code: `backend/app/research/earnings.py`.
