# TradingAgents Platform

**A multi-tenant paper-trading platform that runs six different strategy engines head-to-head — a 7-agent LLM debate pipeline against five deterministic, zero-cost rule engines — and proves which one actually works with real walk-forward research, not backtested marketing claims.**

Every decision any engine makes is recorded immutably and published on a public, unauthenticated track record. Nothing is claimed that can't be checked.

> **Paper trading only, enforced server-side.** `broker_connections.base_url` is hardcoded to Alpaca's paper API in `db/models/broker_connection.py` — not a config flag, a code-level guarantee. Live trading is a deliberate future decision, not something that can be flipped on by accident.

---

## Why this is different from another "AI trading bot"

Most AI-trading projects run one backtest, like the result, and ship it. This platform is built around **disproving its own ideas before they go live**:

- The momentum-rotation engine looked like a clean winner by raw return in its own tournament — until an out-of-universe validation showed the extra return was concentration, not risk-adjusted edge (test-era Sharpe ~0.93 vs. 0.91 for an equal-weight benchmark). Shipped anyway, but explicitly labeled a forward experiment, not a proven strategy.
- An insider-buying signal tournament found the pattern that looked strongest *by eye* — multiple executives buying the same stock the same week — actually **lost** to the simplest possible signal (one large purchase) once tested out-of-sample. The eye-catching hypothesis was noise; the boring one wasn't.
- Two independent walk-forward rounds on a 5-minute intraday rule engine found **no robust edge at all**, on a bigger and better search the second time. It's still in the codebase, but shelved — not deployed on any live account.
- The one signal that *did* survive three separate validations (5-fold walk-forward, an 18-month one-shot holdout, and two independent out-of-universe checks on completely unrelated ticker sets) is post-earnings-announcement drift — a 60-year-old, well-documented academic anomaly, not a novel discovery. The platform's edge is discipline, not a secret alpha source.

Every strategy has a documented, honest verdict in [`GRADUATION.md`](GRADUATION.md) — a live scorecard of what's actually proven versus what's still a forward experiment, with hard criteria (beats the deterministic baseline out-of-sample, Sharpe ≥ 1.0, survives a real drawdown untouched, enough trades to not be luck) so "prove it out longer" has a real finish line instead of being an open-ended vibe.

---

## Six strategy engines, racing in production

| Engine | Approach | Cost | Status |
|---|---|---|---|
| **Agents** | 7-agent LLM debate (technical/sentiment/news/fundamental analysts → bull/bear researcher debate → risk manager veto → portfolio construction) | LLM inference | Forward-tested vs. the Quant baseline |
| **Quant Baseline** | Deterministic trend + mean-reversion rules, regime-gated | Free | The control group — if Agents can't beat this, the product is explainability, not alpha |
| **Intraday Rules** | 5-minute-bar momentum/ORB/VWAP-reversion, flat by close | Free | **Proven to have no edge** across two walk-forward rounds — kept in the repo, not deployed |
| **Momentum Rotation** | Monthly top-4 relative-momentum rotation, no stops by design | Free | Live forward experiment — tournament found the extra return is concentration, not alpha |
| **Earnings Drift (PEAD)** | Long-only entry on qualifying EPS surprises, held for days | Free | The most validated signal here — survived 3 independent out-of-sample checks |
| **Earnings Drift — Options** | Same PEAD trigger, expressed as a defined-risk long call instead of stock | LLM-free, uses live options chain | Live, risk capped at premium paid |

Every engine shares the same infrastructure: typed Pydantic contracts, the same broker integration, the same position monitor, the same public track record. Nothing gets a special code path that skips the discipline.

---

## The agent pipeline

```
POST /api/v1/agents/run { ticker, debate_rounds, model }
                          │
    ┌─────────────────────┼─────────────────────┐
    │           │           │                    │
Technical   Sentiment      News            Fundamental
Analyst     Analyst      Analyst            Analyst
[Wyckoff,   [Options flow, [Earnings risk,  [CANSLIM, PEAD,
 ICT, Turtle, inst. flow]   macro events]    AQR Quality]
 SMC]
    │           │           │                    │
    └───────────┴───────────┴────────────────────┘
                          │  AnalystBundle (typed)
                          ▼
                  Researcher Debate
                  (Bull vs Bear, N rounds)
                          │
                          ▼
                   Risk Manager
                  (Kelly-sized, ATR stops, veto power)
                          │
                          ▼
                 Portfolio Manager
              → BUY / HOLD / SELL + order params
                          │
              ┌───────────┴────────────┐
              │                        │
       Bracket order              Broadcast WS
       submitted to Alpaca        → frontend animates
       (native stop + target)     the debate live
```

Every agent's output is a strict Pydantic schema — no free-form text parsing between stages. Every step streams a WebSocket event the frontend renders in real time.

**Hardcoded discipline that cannot be overridden by settings:** 5% max position size, 2:1 minimum reward/risk, confidence gates that scale from 65% (bull trending) to 85% (high volatility), 3-of-4 analyst consensus required, VIX > 30 suppresses new buys, -5% daily drawdown halts all scanning.

---

## Production engineering, not just a model prompt

This is the part that doesn't show up in a demo GIF. A sample of real incidents found and fixed, documented in [`INCIDENTS.md`](INCIDENTS.md):

- **A silent multi-day scan outage** (stale Alpaca keys read as "market closed" + no scheduler timeouts + a shared egress IP getting rate-limited by Yahoo Finance) — root-caused and fixed with a hardened scheduler (bounded catch-up windows, Redis dedupe, heartbeats) and an Alpaca-first/yfinance-fallback data layer.
- **A P&L display bug live in the admin account**: `equity - last_equity` used a naive `.get(key, default)` fallback that only fires when a key is *missing* — but Alpaca returns a real `0` for a freshly-reset account, so day P&L silently showed total equity instead. Found across 8 call sites, fixed with one shared `compute_day_pnl()` function.
- **An event-loop-blocking bug found live, minutes before market open**: a dashboard endpoint called `yfinance` synchronously with no timeout, directly in an async handler — freezing the single-threaded event loop under Yahoo rate-limiting and returning 503s on *unrelated* concurrent requests, including a bare `/health` check with zero dependencies of its own. Fixed by routing through a thread executor with the platform's existing 15-second hard-timeout helper.
- **Automated trade-close emails silently never sent, on every account, since launch** — a notification helper had been duplicated instead of reused, so the code path that fires on every stop-loss/take-profit/time-exit never called the function that actually triggers the email.

Also: a kill switch checked at three independent enforcement points (scheduler, order placement, the always-on intraday loop) that deliberately does *not* gate position monitoring — a halt should never disable the thing protecting capital already at risk. Order seatbelts (daily order cap, notional ceiling vs. equity, duplicate-run guard). Nightly encrypted DB backups verified running green. A GitHub Action that catches silent scan outages by comparing real daily activity against the platform's own public stats — which itself had a false-positive bug (comparing against a capped display list instead of the real count) found and fixed.

---

## Research discipline

`app/research/` is a proper walk-forward policy tournament, not a single backtest:

- Time-ordered train/test folds — **never shuffled**
- A held-out final period that only the single tournament winner ever touches, once
- Regime-sliced and setup-sliced metrics, overfit gap (train Sharpe − test Sharpe) reported for every candidate, not just the winner
- Out-of-universe validation on completely unrelated ticker sets as a second, independent check beyond the time-based holdout
- **LLM strategies are explicitly excluded from backtesting** — a model's training data contains the historical outcomes, so backtesting an LLM strategy is lookahead by construction. Agents are only ever evaluated forward, against the tournament-winning deterministic baseline.

Every tournament report is committed to `docs/research/` — the actual JSON leaderboards and markdown writeups, including the ones that killed a strategy, not just the ones that shipped one.

---

## Security & multi-tenancy

- JWT auth (30-min access tokens + rotating refresh tokens with family-based replay detection), invite-gated signup, per-user rate limits on every LLM endpoint
- Broker credentials Fernet-encrypted at rest; platform LLM keys are admin-only and rejected server-side if a non-admin tries to write them
- Every cost-sensitive setting (debate rounds, scan candidates, confidence thresholds) is clamped server-side, not just validated client-side
- CORS pinned to the production frontend origin in production; API docs disabled in production; full CSP enforced (not report-only)
- Data isolation verified end-to-end: cross-user trade access returns 404, WebSocket run-rooms reject non-owners with a close code, watchlists are per-user

---

## Stack

| Layer | Tech |
|---|---|
| Agent framework | Custom structured runner — Claude tool-use + strict Pydantic contracts (not LangGraph) |
| Backend | FastAPI + asyncpg + SQLAlchemy async |
| Message queue | Redis pub/sub |
| Database | PostgreSQL 16 |
| Broker | Alpaca (paper by default, enforced server-side) |
| Market data | Alpaca-first (bars, snapshots, options chain), NASDAQ public calendar, yfinance as last-resort fallback only |
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| Animations | Framer Motion |
| Charts | Recharts |
| State | Zustand + TanStack Query |
| Infra | Docker Compose locally; Vercel + Render + Neon + Upstash in production, entirely on free tiers |

---

## Quick start

```bash
git clone https://github.com/Yash3561/tradingagents-platform.git
cd tradingagents-platform
cp .env.example .env      # fill in ANTHROPIC_API_KEY (or NVIDIA_API_KEY for free inference) + Alpaca paper keys

make up                   # starts all 9 services
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

```bash
make frontend    # local dev: npm install + vite dev server
make backend     # local dev: uvicorn --reload
```

Full deploy walkthrough (Vercel/Render/Neon/Upstash, entirely free-tier) is in [`DEPLOY.md`](DEPLOY.md).

---

## Repository layout

```
backend/app/
├── agents/           # Agent contracts, the structured debate runner, momentum/PEAD/options engines
├── research/          # Walk-forward tournament engine, data layer, run scripts
├── workers/           # Scanner, scheduler, position monitor, intraday engine, circuit breakers
├── api/v1/            # REST endpoints
├── core/              # Market data (Alpaca-first), crypto, rate limiting, mailer, pnl
└── db/models/         # ORM models — trades, agent_runs, users, refresh tokens, settings

frontend/src/
├── pages/             # Dashboard, Agent Hub, Scanner, Strategy Lab, Track Record, Admin, ...
└── components/        # Agent debate visualization, data display, layout

docs/research/          # Committed walk-forward tournament reports (JSON + markdown)
GRADUATION.md           # Live scorecard: what's proven vs. what's still a forward experiment
INCIDENTS.md            # Operational landmines found in production, and how they were fixed
```

---

## Database schema (abridged)

**`agent_runs`** — full debate log + typed contract JSON per run, across all six engines
**`trades`** — every trade with a complete reasoning audit trail (JSONB), tagged by engine
**`equity_snapshots`** — 15-minute equity curve, one series per user
**`users`**, **`broker_connections`**, **`refresh_tokens`**, **`user_settings`**, **`notifications`**

---

## License

MIT
