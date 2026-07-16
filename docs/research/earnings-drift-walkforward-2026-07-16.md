# Post-Earnings-Announcement Drift (PEAD) — Walk-Forward Tournament (2026-07-16)

**Question:** does a genuinely different information source — long-only entries into
large positive EPS surprises, held for weeks — clear a real out-of-sample bar? Unlike
the two intraday rounds (price-pattern rules, no edge found), this is a documented
market anomaly (systematic underreaction to earnings surprises), so a positive result
here would be a new signal family, not a re-tune of an exhausted one.

**Answer: the first candidate across three tournaments to survive its holdout cleanly.**
Not proof of a durable edge yet — five folds and one holdout window is a start, not a
verdict — but this is qualitatively different from both intraday rounds, which failed
at every stage.

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
  first pass, less rigorous than the intraday tournaments' 6 folds. Worth another
  pass with a longer history window or a second, non-overlapping universe before
  treating the Sharpe-1.9 holdout as durable.
- Earnings data is scrape-based (not a formal API) — per-ticker gaps are possible and
  unaudited row-by-row.
- Survivorship-biased universe, same as both other tournaments — rankings more
  trustworthy than absolute returns.
- **Not deployed anywhere.** This is a research result, not a live arm. Wiring it up
  (new `strategy_mode="earnings"`, a worker loop, settings keys, scanner integration)
  is a real engineering project on the scale of the intraday arm — deliberately not
  started without sign-off given this session's session-long emphasis on the user
  approving capital-risk decisions explicitly.

Full leaderboard + fold-by-fold detail + holdout: `earnings-drift-walkforward-
2026-07-16.json`. Engine code: `backend/app/research/earnings.py`.
