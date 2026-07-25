# Incident Notes

Operational landmines that aren't obvious from reading the code — the kind of
thing you want to know about *before* it bites you, not while debugging it
at 2am. This is not a changelog (see CLAUDE.md's session checkpoints for
that) — just the sharp edges.

## Rotating SECRET_KEY breaks every stored broker connection

`SECRET_KEY` isn't just a JWT-signing secret — `core/crypto.py` derives the
Fernet encryption key for `broker_connections` (every user's Alpaca API
keys) from it. Rotate `SECRET_KEY` for any reason and every stored broker
connection becomes undecryptable garbage. Every single user, across every
account, has to re-paste their Alpaca keys in Settings. There is no
migration path — old ciphertext encrypted under the old key cannot be
recovered.

**If you ever need to rotate it:** treat it as equivalent to "every user's
broker gets disconnected," not a routine secret rotation. Warn before doing
it, don't do it silently.

## The scheduler dies when Render's free tier spins the process down

`RUN_ALL_WORKERS=true` runs the scanner, position-monitor, equity-tracker,
and intraday loop as asyncio background tasks *inside the same process*
that serves the API — not as separate always-on workers. If Render's free
tier spins that process down after ~15 minutes of no inbound traffic, those
loops stop too, not just the website. This isn't hypothetical — it's the
root of the 2026-07-15/16 outage.

UptimeRobot pings every 5 minutes specifically to prevent the spin-down
condition from ever triggering — but per DEPLOY.md's own note, this is
**not a hard guarantee**. Don't treat "the scheduler is definitely running"
as something you can assume; treat it as something the scan-watchdog GitHub
Action verifies for you once a day.

## The scan-watchdog has a real false-positive pattern — check before panicking

Two watchdog failures (2026-07-17, 2026-07-20) turned out to be false
alarms, not real outages, for two different reasons:

- **2026-07-17**: a genuine early-launch bug (fixed same day) — the
  scheduler really had been silently dead since 7/15.
- **2026-07-20**: not a real outage at all. The watchdog was checking
  `track-record.recent`, a list hard-capped at 20 rows across the entire
  platform for the public page's display. A busy Agents-engine day (up to
  ~20 analyses on its own) pushed a real same-day trade from a *different*
  account out of that window before the evening check ran. Confirmed via
  that account's own trade history — a real trade existed. Fixed
  2026-07-25 by adding `analyses_today` (an uncapped full-day count) to the
  public payload and switching the watchdog to check that instead.

**If the watchdog fails:** check the flagged account's actual trade/agent-run
history before assuming the backend is down. A failure email means
"investigate," not "the scheduler is definitely dead."

## Yahoo/yfinance rate-limits Render's shared egress IP, unpredictably

Not a bug you can fix once — Render's free tier shares an egress IP across
many tenants, and Yahoo Finance rate-limits at the IP level. It self-resolves
(the block isn't permanent) but recurs without warning. `core/market_data.py`
is Alpaca-first specifically because of this (2026-07-17); yfinance is
fallback-only for non-trade-critical data, and every yfinance call added
since then carries a hard timeout (`_yf_bounded`, 2026-07-22) after an
untimed one stalled a live scan for 6+ minutes under exactly this condition.

**If a scan or analysis seems to hang or come back empty with no error:**
suspect this before suspecting the scheduler or the strategy logic.
