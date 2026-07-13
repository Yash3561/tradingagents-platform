# TradingAgents Platform — Session Checkpoint

> Rally race co-driver notes. Read this before touching anything.
> Last updated: 2026-07-12 (quant baseline engine, MACD fix, security hardening ×2, refresh-token auth, research engine + first tournament)

---

## What This Is

A **multi-tenant paper-trading SaaS** — a professional-grade multi-agent trading platform where each user signs up, connects their own Alpaca **paper** account, and the AI agents analyze + trade in *their* account.

**Not a toy.** Architecture is production-grade: typed agent contracts, WebSocket streaming, per-user Alpaca integration, market regime detection, Kelly Criterion position sizing, ATR-based stops.

**Paper-only, enforced server-side.** `broker_connections.base_url` is forced to
the paper API in code (`PAPER_BASE_URL` in `db/models/broker_connection.py`).
Live trading is a deliberate future product/legal decision — do not soften this.

## Current State & The Working Loop (★ orient here first — keep this section current)

**Live in production**: Vercel (frontend) + Render free (backend, `RUN_ALL_WORKERS=true`) + Neon + Upstash. Invite-gated signup. Admin = ygc2@njit.edu. Security-hardened (see Security Hardening) with 30-min JWTs + rotating refresh tokens, enforced CSP, per-user LLM quotas.

**Two strategy engines** selectable per user via `strategy_mode` setting:
- `agents` — the 7-agent LLM debate pipeline (`structured_runner.py`)
- `quant` — deterministic regime-filtered rules, zero LLM cost (`quant_baseline.py`). The control group: if agents can't beat it, the product story is explainability, not alpha.

**The research → deploy → race loop** (the current operating model):
1. **Research**: walk-forward policy tournament over the deterministic rule family (`app/research/`, Admin page → Research, or `docker exec tap_backend python -m app.research.run`). Time-ordered train/test folds, one-shot holdout, leaderboard by out-of-sample Sharpe. Reports land in `docs/research/`.
2. **Deploy**: the winning policy's parameters become the live quant account's settings.
3. **Forward race**: agents account vs quant-winner account, compared in Admin → Strategy Lab. LLM strategies can NOT be backtested (model training data contains historical outcomes = lookahead by construction) — agents are judged forward-only against the tournament winner.
4. Repeat as data accrues. Never re-run the holdout on more than the single winner.

**Round-1 tournament results (2026-07-12**, `docs/research/walkforward-2026-07-12.json`): 650 policies, 7 folds, 2013–2026. Live baseline ranked **492/650**. Winning plateau: wide stops (3×ATR), 3:1 R:R, regime gate OFF, trend+meanrev blend — near-zero overfit gap across ranks 1-6 (robust plateau, not a spike). Holdout (one shot): +1.96%, maxDD −3.5%, vs SPY +22.4% — capital-preserving, not alpha; exposure capped ~40% (8×5%). Regime slice: mean reversion wins in SIDEWAYS, trend entries lost in late BULL.

**Forward race is LIVE (2026-07-13)**: two prod accounts — **Yash** (agents engine, admin, fresh Alpaca `PA3D6AOC1NYN` reset) and **Quant** (quanttest@example.com, quant engine, Alpaca `PA37ZVR2KZ0T`). Both have scan_enabled=true (scheduler: market open + midday). Quant's first trade: 22 AAPL @ 316.45, stop −5.56%/target +11.12%. Yash's first decisions: disciplined HOLDs. Old Yash Alpaca losses were dev-era junk — the account was reset; prod platform never traded it before 7/13.

**LLM ops findings (2026-07-13, all fixed — do not regress)**: DeepSeek **flash produces empty skeleton debates** on the senior prompts (rounds=[], NEUTRAL 0.5) — senior_model default is now **deepseek-v4-pro everywhere** (agents.py RunRequest/ScanRequest, scanner run_market_scan — was claude-opus-4-6 which would 404, NIM has no Anthropic routing). Runner hardening in `_nim_structured`: 2s global call pacing (free-tier RPM), 429s honor Retry-After (15/30/45s), transient 5xx retries, max_tokens 4096, prose-JSON fallback picks best schema-overlap object (≥3 fields), empty-thesis debates raise instead of flowing through as fake NEUTRAL HOLDs. NIM free tier also has a deeper quota — heavy scan days can exhaust it (429s that outlast backoff); scan_max_candidates on Yash set to 5.

**NEXT UP (agreed with user, not yet built) — round-2 grid**: exits (trailing stops, time-based exits, partial profit-taking), portfolio construction sweep (10–20 slots, 5–10% sizes, regime-scaled exposure), regime-conditional parameters; make quant policy params settings-driven so tournament winners deploy without code changes. Then flip the live quant account to the round-2 winner. Parallel low-effort: SMTP env vars on Render, scheduled Neon pg_dump backups, weekly tournament re-run cron, strip model chain-of-thought leaking into risk rejection_reason text.

## Multi-Tenancy (★ read this first)

- **Auth**: every endpoint except `/auth/*` and `/ws` requires JWT (`require_user` dependency added at router level in `api/router.py`).
- **Broker**: users paste their Alpaca paper keys in Settings → verified live against Alpaca → Fernet-encrypted (key derived from `SECRET_KEY` in `core/crypto.py`) → stored in `broker_connections`. Rotating `SECRET_KEY` invalidates stored creds.
- **Per-user client**: `app/broker/credentials.py` — `get_client_for_user(user_id)` (120s TTL cache), FastAPI deps `optional_broker` (None → endpoints return empties) and `required_broker` (409 `broker_not_connected`).
- **AlpacaClient class**: `app/broker/alpaca_client.py` — instance-scoped creds. Module-level functions = legacy env-key path (market clock, price feed, circuit breakers, overnight agent, dev fallback).
- **Data isolation**: `user_id` column (nullable = legacy rows) on trades, agent_runs, equity_snapshots, notifications, activity_logs. All API queries filter by it. Added via idempotent `ALTER TABLE ... IF NOT EXISTS` in `core/postgres.py::init_db` (no Alembic needed).
- **Per-user settings**: `user_settings` table; `get_user_setting(user_id, key, default)` falls back to platform_settings. Watchlist is per-user (`custom_watchlist` key).
- **Workers**: trade_sync groups trades by user; position_monitor / equity_tracker / intraday monitor loop `connected_user_ids()` + legacy env account; scheduled scans run **only for users with explicit `scan_enabled=true` user setting** (LLM cost control).
- **Order flow**: `run_structured_agent_analysis(..., user_id)` → `_place_order_if_approved` uses the user's client; no broker connected → emits `order_skipped` WS event, analysis-only.
- **Verified 2026-07-02**: two-user isolation test passed (401 unauth, cross-user trade fetch 404, watchlist isolation, fake Alpaca keys rejected with 400).

## Real-User Readiness (added 2026-07-03)

- **Rate limiting**: `core/rate_limit.py` — Redis sliding window, fails OPEN if Redis is down.
  login 10/15min per IP + 5/15min per email; signup 5/hr per IP; forgot-password 3/hr per email + 10/hr per IP; resend-verify 3/hr per user.
- **Password reset**: `POST /auth/forgot-password` (never reveals if email exists) → token in Redis (`pwreset:{sha256}`, 30min TTL) → `POST /auth/reset-password`. Reset revokes ALL sessions.
- **Email verification (soft)**: signup sends verify link (`verify:{sha256}` in Redis, 48h). `users.email_verified` — banner in Shell until verified, never blocks usage.
- **Mailer**: `core/mailer.py` — SMTP via env (`SMTP_HOST` etc.); unset host = link logged at WARNING (dev mode). Links use `FRONTEND_URL` (fallback localhost:5173).
- **Session revocation**: JWTs carry `iat`; `users.password_changed_at` (stored with microsecond=0 — iat is second-granularity) rejects older tokens in `get_current_user`. `POST /auth/change-password` returns a fresh token. Legacy tokens without iat die on first password change.
- **Admin**: `users.is_admin` — bootstrap via `ADMIN_EMAIL` env (auto-promoted on signup/login). `api/v1/admin.py`: users list, toggle-active (guards: not self, not other admins), invite CRUD, stats. `require_admin` dep in `core/auth.py`.
- **DB invite codes**: `invite_codes` table — max_uses/used_count/expires_at/revoked; signup accepts env `SIGNUP_INVITE_CODE` (master gate) OR a usable DB code. Invite links: `/?invite=CODE` pre-fills signup. Env code unset = open signup (DB codes then optional).
- **Frontend**: `pages/Auth/` (ForgotPassword, ResetPassword, VerifyEmail share AuthCard), `pages/Admin/`, Settings → Account Security (change password), `VerifyEmailBanner` in Shell (refreshes `/auth/me` → updates cached user incl. is_admin). Unauthed URL handling in App.tsx maps `/reset-password` + `/verify-email` + `/?invite=` to views (auth pages live outside the router).
- **Verified 2026-07-03**: full e2e via curl — signup→verify link logged→verify (reuse rejected), forgot→reset→old token 401→old password 401, change-password revokes prior tokens (same-second tokens survive by design), invite create→consume→reuse 403→bogus 403→revoke, disabled user login 403, self-disable 400, login rate limit tripped at 6th attempt, forgot-password 429 at 4th.

## Launch Prep (added 2026-07-03, same night)

- **Free-tier deploy** ($0/mo): Vercel (frontend) + Render free web service (backend) + Neon (Postgres) + Upstash (Redis) + UptimeRobot keep-awake. Full walkthrough in **DEPLOY.md**; `render.yaml` blueprint + `frontend/vercel.json` (SPA rewrites) committed.
  - `RUN_ALL_WORKERS=true` → trade_sync + equity_tracker run inside the API process (Render free has no worker services). NEVER set while the worker container also runs.
  - `PRICE_FEED_ENABLED=false` on free deploys — the tick stream's per-tick Redis SET would burn Upstash's 500K/mo quota.
  - Backend Dockerfile now has a CMD honoring `$PORT` (compose overrides it).
  - Production guard: `ENVIRONMENT=production` + default SECRET_KEY → refuses to start.
- **Product analytics**: `analytics_events` table + `core/analytics.py::track()` (fire-and-forget, never raises). Events: signup, login, broker_connected, agent_run, scan_run, manual_order — keep this list in the module docstring current. `GET /admin/analytics` → daily series (zero-filled), 7d event mix, funnel (from source-of-truth tables so pre-analytics users count), WAU. Charts on Admin page.
- **Landing page** (`pages/Landing/`): renders at `/` for logged-out visitors (App.tsx `initialUnauthedView`; deep links still go to login, `?invite=` to signup). Animated hero, cycling 7-agent pipeline, typewriter debate terminal, live stats from the public track-record endpoint, framework marquee (`animate-marquee` keyframes in tailwind.config), features/steps/CTA/disclaimer footer. Login/Signup logos link back to `/`.
- **Public AI track record**: `GET /api/v1/track-record/` — UNAUTHENTICATED by design (the shareable proof page). Anonymized aggregates only: decision mix, win rate on closed AI trades (agent_run_id set), monthly series, recent 20 calls (ticker/decision/confidence, no user data). Redis-cached 5 min. Frontend `/track-record` renders standalone (public, with signup CTA) when logged out and inside the Shell when logged in; sidebar under Intelligence.

## Post-Launch (added 2026-07-04)

- **Strategy Lab** (`GET /admin/strategy-lab`, section on Admin page): compares all broker-connected accounts side by side — equity curve as **% change from each account's first snapshot in range** (downsampled to ~200 pts), trade stats, agent run count, and the strategy-relevant per-user settings (`STRATEGY_KEYS` in `admin.py`: confidence gate, sizing, stops, scan flags, watchlist). Built for running multiple paper accounts with different strategy profiles to see which policies actually work. Overlaid % curves + comparison table in `pages/Admin/index.tsx`.
- **Mobile responsiveness**: Sidebar becomes a drawer below `lg` (hamburger in Header, overlay in Shell); Header/StatusBar condense on small screens. Page grids (Dashboard, AgentHub, Portfolio, Scanner, Alerts, Backtesting) stack below `lg` instead of crushing columns — keep new pages following this pattern.
- **Chart timezones**: `CandlestickChart.tsx` formats bar times in the viewer's local timezone (was rendering exchange/UTC times).
- **Quant Baseline engine** (added 2026-07-12): `app/agents/quant_baseline.py` — deterministic, zero-LLM control strategy (trend-follow + mean-reversion entries, MA200-break/RSI≥78 exits, 2×ATR stops, 2:1 R:R, regime-gated). Selected per user via `strategy_mode` setting (`"agents"` | `"quant"`, in `DEFAULTS`) or explicit `strategy` in `POST /agents/run`; scheduled scans respect it (`scanner.py`). Same lifecycle as the agent pipeline (AgentRun row, `run:{id}` WS events, `_place_order_if_approved`), tagged `llm_model="quant-baseline"` so Strategy Lab (Engine column) compares apples-to-apples. Purpose: if agents can't beat these rules, the product story is explainability, not alpha. Settings → AI Model has the engine dropdown.
- **MACD signal-line fix** (2026-07-12): `structured_runner._fetch_market_data`, `scanner.py`, `backtest.py` computed the signal line as EMA9 of *price* instead of EMA9 of the MACD series — `macd_bullish` was effectively always false (agents got bad data; quant trend rule could never fire). All three now match the correct implementations in `market.py`/`agents.py`. `overnight_agent.py` intentionally uses `ema12 > ema26` (MACD>0), left as-is.

## Security Hardening (added 2026-07-12)

- **Platform LLM keys are admin-only**: `POST /settings/` rejects `PLATFORM_KEY_ENV_MAP` keys (anthropic/nvidia) with 403 for non-admins — previously ANY user could overwrite them + os.environ. Reads were already blocked.
- **Server-side setting bounds**: `NUMERIC_BOUNDS` + `ENUM_VALUES` in `api/v1/settings.py` clamp cost/risk settings at write (debate_rounds ≤3, scan_max_candidates ≤10, confidence 0-1, etc.); `strategy_mode` must be agents|quant. Scanner also hard-caps `max_candidates` to 10 at read. Add new cost-sensitive settings to NUMERIC_BOUNDS.
- **Per-user quotas on LLM endpoints** (sliding 1h, Redis, fails open): `/agents/run` 30/hr, `/agents/scan` 6/hr, `/agents/options/analyze` 30/hr. Constants at top of `agents.py`. Ticker inputs validated against `TICKER_PATTERN`; ScanRequest max_candidates ≤10, watchlist ≤60.
- **WS run-room ownership**: `/ws/runs/{run_id}` closes 4403 unless the token's user owns the run (legacy NULL-user runs stay open). `_authenticate_ws` now returns the user id.
- **CORS**: production allows ONLY `FRONTEND_URL` — the `*.vercel.app` wildcard regex is dev-only unless `CORS_ALLOW_VERCEL_PREVIEWS=true` (it admits any Vercel-hosted site). Dead literal `"https://*.vercel.app"` removed.
- **API docs disabled in production** (`/docs`, `/redoc`, `/openapi.json` → 404 when `ENVIRONMENT=production`).
- **Security headers**: backend middleware (nosniff, X-Frame-Options DENY, Referrer-Policy, Permissions-Policy, HSTS in prod, `Cache-Control: no-store` on /api). `vercel.json` adds the same + enforced CSP subset (frame-ancestors/object-src/base-uri) + full CSP in **Report-Only** — check browser console for violations, then promote it to enforced.
- Verified 2026-07-12 via curl/websockets: non-admin platform-key write 403, clamps applied, 422 on out-of-range run/scan params + bad tickers, WS attacker/no-token rejected + owner connects, 31st run in an hour → 429, `npm audit --omit=dev` clean.
- **Refresh-token auth** (same day, second pass): access JWTs now live **30 min**; sessions persist via rotating refresh tokens — `db/models/refresh_token.py` (SHA-256 stored, `family_id`, single-use rotation, **replay of a rotated token revokes the whole family**), `POST /auth/refresh`, real `POST /auth/logout` (revokes family), password change/reset revokes all user refresh tokens. Frontend: `tap_refresh` in localStorage, axios 401 interceptor does single-flight refresh + one retry (`api.ts`), `saveAuth(token, user, refresh)`. Legacy 30-day JWTs stay valid until they expire. Table auto-created by `init_db` create_all (import registered in main.py). Verified: rotation, replay→family-kill, logout, pw-change revocation, browser test (corrupt access token + valid refresh → dashboard self-heals, parallel queries share one refresh).
- **Model allowlist**: `ALLOWED_LLM_MODELS` in `db/models/settings.py` — enforced on `/agents/run`, `/agents/scan` (Pydantic validator) and the `llm_model` setting (ENUM_VALUES). Add new models THERE when the Settings dropdown grows.
- **Tracebacks** no longer stored in `agent_runs.error` (message only; full trace goes to server logs) — structured_runner, quant_baseline, legacy runner.
- **CSP enforced** on Vercel (was Report-Only): `script-src 'self'`, fonts from Google, `connect-src` **pinned to the Render backend URL** — vercel.json must be updated if the backend moves. Bundle statically verified: no inline scripts / eval / workers; tradingview+alpaca strings are plain `<a href>` links.

## Research Engine (added 2026-07-12)

- **Purpose**: the user's "hundreds of accounts" experiment idea, done right — instead of hundreds of real Alpaca accounts, a **walk-forward policy tournament** over the deterministic quant rule family (`app/research/`). Train/test split by TIME (never shuffled), rolling folds, final N-month **holdout that only the tournament winner ever touches, once**.
- `research/data.py` — daily OHLCV via yfinance (pickle cache in /tmp/research_cache), ~60-ticker universe (survivorship-biased — rankings meaningful, absolute returns optimistic), vectorized historical regime series (port of regime_detector scoring, rolling windows only).
- `research/engine.py` — `Policy` dataclass (defaults = live quant baseline; grid varies RSI bands, MACD requirement, stops/RR, regime gate, setup ablations), matrix `Panel`, honest simulator: signal on close t → fill at open t+1, stops/TP intraday with stop-first assumption, 5bps slippage.
- `research/walkforward.py` — fold machinery, MIN_TRADES filter, leaderboard ranked by mean TEST Sharpe across folds (must qualify in EVERY fold — the "universally applicable" bar), overfit gap (train−test), regime/setup-sliced metrics, SPY benchmark, one-shot holdout.
- Run: `docker exec tap_backend python -m app.research.run [--quick]` (writes /tmp/research_report.json) or `POST /admin/research/run` + `GET /admin/research/latest` (report cached in Redis `research:report`).
- **★ LLM strategies can NOT be backtested** — the models' training data contains the historical outcomes (lookahead by construction). The tournament covers deterministic policies only; agents are evaluated forward against the tournament winner as baseline.

---

## Stack at a Glance

| Layer | Tech |
|---|---|
| Agent framework | Custom structured runner (Claude tool_use + Pydantic contracts) |
| Backend | FastAPI + asyncpg + SQLAlchemy async |
| Message queue | Redis pub/sub |
| Relational DB | PostgreSQL 16 (trades, agent runs, settings, equity curve) |
| Cache / pub-sub | Redis 7 |
| Broker | Alpaca (paper by default) |
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| Animations | Framer Motion |
| Charts | Recharts (portfolio/backtest) |
| State | Zustand + TanStack Query |
| Infra | Docker Compose (9 services) |

---

## Repository Layout

```
tradingagents-platform/
├── CLAUDE.md                    ← YOU ARE HERE
├── docker-compose.yml           ← 9 services, all wired
├── .env.example                 ← Copy to .env, fill keys
├── Makefile                     ← make up / make frontend / make backend
│
├── backend/
│   ├── app/
│   │   ├── main.py              ← FastAPI app, lifespan, CORS
│   │   ├── config.py            ← All env vars (Pydantic Settings)
│   │   ├── api/v1/              ← REST endpoints:
│   │   │   ├── agents.py        ←   POST /agents/run, GET /agents/contracts, ScanCriteria
│   │   │   ├── market.py        ←   /market/chart, /market/names, /market/news, /market/calendar, /market/regime
│   │   │   ├── orders.py        ←   GET/DELETE /orders/ (Alpaca order management)
│   │   │   ├── trades.py        ←   GET /trades/
│   │   │   ├── portfolio.py     ←   positions, equity curve
│   │   │   ├── dashboard.py     ←   KPIs, market brief
│   │   │   ├── settings.py      ←   API key hot-reload, watchlist CRUD
│   │   │   ├── backtest.py      ←   RSI/MACD/MA simulation
│   │   │   └── ws.py            ←   WebSocket endpoint
│   │   ├── agents/
│   │   │   ├── contracts.py     ← ★ AGENT CONTRACTS (Pydantic schemas for all 7 agents)
│   │   │   ├── structured_runner.py ← ★ MAIN RUNNER — world-class frameworks in every prompt
│   │   │   └── quant_baseline.py ← deterministic control strategy (strategy_mode="quant", no LLM)
│   │   ├── research/            ← ★ WALK-FORWARD TOURNAMENT (data.py, engine.py, walkforward.py, run.py)
│   │   ├── core/
│   │   │   ├── postgres.py      ← Async SQLAlchemy engine + Base
│   │   │   ├── redis_client.py  ← Redis async client
│   │   │   └── websocket_manager.py ← Room-based WS broadcast
│   │   ├── db/models/
│   │   │   ├── agent_run.py     ← AgentRun ORM (stores full debate_log + reasoning_json JSONB)
│   │   │   ├── trade.py         ← Trade ORM (reasoning_json = full audit trail per trade)
│   │   │   └── refresh_token.py ← rotating refresh tokens (families, replay = revoke family)
│   │   └── workers/
│   │       ├── main.py          ← Entry point: runs 4 async loops
│   │       ├── scanner.py       ← Market scanner with ATR/BB/Stoch/PEAD/custom criteria
│   │       ├── regime_detector.py ← Market regime (BULL/BEAR/HIGH_VOL/SIDEWAYS), 15min cache
│   │       ├── position_monitor.py ← Stop-loss / take-profit enforcement (every 5 min)
│   │       ├── trade_sync.py    ← Alpaca fill reconciliation → DB (every 2 min)
│   │       ├── equity_tracker.py ← Portfolio equity snapshots (every 15 min)
│   │       ├── scheduler.py     ← Auto-scan at market open + midday
│   │       └── circuit_breakers.py ← VIX gate, earnings blackout, drawdown halt
│   └── requirements.txt
│
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── layout/          ← Shell, Sidebar, Header (market clock, indices), StatusBar
│       │   ├── agent/           ← AgentFlow (animated pipeline), DebateTimeline
│       │   ├── data-display/    ← MetricCard, PnLBadge
│       │   └── ui/Tooltip.tsx   ← TermTooltip — 20 pre-built financial term tooltips
│       ├── pages/
│       │   ├── Dashboard/       ← KPIs, market pulse, live positions, agent activity
│       │   ├── AgentHub/        ← Run analysis, watch debate live, custom scan criteria
│       │   ├── Markets/         ← Any-stock charts, indices, sector heatmap, top movers
│       │   ├── Watchlist/       ← Live price grid, 8s polling, 52w range, add/remove
│       │   ├── News/            ← Per-ticker news (Alpaca primary, yfinance fallback)
│       │   ├── Calendar/        ← FOMC/CPI/NFP 2026 dates + earnings via yfinance
│       │   ├── Scanner/         ← Pre-screen with progress, advanced filter panel, company names
│       │   ├── Options/         ← AI CALL/PUT/NO_PLAY + live chain (calls/puts, IV, OI, ITM)
│       │   ├── Portfolio/       ← Positions, equity curve, P&L calendar
│       │   ├── TradeHistory/    ← Virtualized table + full reasoning audit drawer + CSV
│       │   ├── Orders/          ← Open orders (10s poll) + history, cancel single/all
│       │   ├── Backtesting/     ← RSI/MACD/MA simulation, equity curve vs SPY
│       │   ├── Analytics/       ← AI performance grade A-F, correlation matrix, sector exposure
│       │   ├── Alerts/          ← 5 smart alert types
│       │   ├── Strategy/        ← Live regime card, 8 frameworks, 12 risk rules, philosophy
│       │   ├── Learn/           ← 47-term glossary, 6 categories, real-time search
│       │   └── Settings/        ← Model selector, risk sliders, API key hot-reload
│       ├── lib/                 ← api.ts, cn.ts, formatters.ts, queryClient.ts, auth.ts
│       └── index.css            ← Tailwind base + component layer (.card, .badge-gain, etc.)
│
├── docs/research/               ← committed tournament reports (walkforward-YYYY-MM-DD.json)
│
└── scripts/
    └── init_timescale.sql       ← TimescaleDB hypertable setup
```

---

## Agent Pipeline (The Core)

```
User triggers: POST /api/v1/agents/run { ticker, debate_rounds, model, criteria }
                          │
                          ▼
          structured_runner.py: run_structured_agent_analysis()
                          │
          ┌───────────────┼───────────────────────────────────┐
          │               │               │                   │
    Technical         Sentiment        News             Fundamental
    Analyst           Analyst          Analyst          Analyst
    [Wyckoff,ICT,     [Options flow,   [Earnings risk,  [CANSLIM,PEAD,
    Turtle,SMC]       Inst.flow,F&G]   Macro events]    AQR Quality]
    → TechnicalReport → SentimentReport → NewsReport → FundamentalReport
          │               │               │                   │
          └───────────────┴───────────────┴───────────────────┘
                          │  AnalystBundle (typed aggregate)
                          ▼
                   Researcher Debate
                   (Bull vs Bear, N rounds)
                   [CANSLIM bull, Value trap bear,
                   Momentum factor, Wyckoff phases]
                   → ResearcherDebate
                          │
                          ▼
                   Risk Manager
                   [Kelly Criterion half-Kelly sizing,
                   ATR-based stops (2×ATR14),
                   VaR controls, regime-adjusted sizing]
                   → RiskAssessment (has veto power — approved: bool)
                          │
                          ▼
                   Portfolio Manager
                   [Position pyramid 50/25/25,
                   3-target exit (T1/T2/T3),
                   Correlation-aware construction]
                   → FinalDecision (BUY / HOLD / SELL + order params)
                          │
              ┌───────────┴────────────┐
              │                        │
       Bracket order               Broadcast WS
       submitted to Alpaca         room: run:{id}
       (stop + take-profit         → frontend animates
       managed natively)
```

Every step emits a WebSocket event to `run:{run_id}` room.
Frontend `AgentHub` page subscribes and animates in real-time.

---

## Agent Contracts (★ Key Feature)

**File:** `backend/app/agents/contracts.py`

Each agent has a strict Pydantic output schema. Claude is forced to respond
using `tool_use` with the exact schema — no free-form text parsing between agents.

| Contract | Fields |
|---|---|
| `TechnicalReport` | rsi_14, macd_crossover, support/resistance, trend, signal, confidence |
| `SentimentReport` | sentiment_score, institutional_flow, put_call_ratio, short_interest |
| `NewsReport` | headline_sentiment, material_news, catalyst_upcoming, risk_events |
| `FundamentalReport` | pe_ratio, forward_pe, revenue_growth_yoy, gross_margin, vs_sector_pe |
| `AnalystBundle` | Aggregates all 4 above + helper methods (bullish_count, avg_confidence) |
| `ResearcherDebate` | rounds[], bull/bear thesis, debate_winner, key_risks/catalysts |
| `RiskAssessment` | approved, risk_level, position_pct, stop_loss_pct, rejection_reason |
| `FinalDecision` | decision (BUY/HOLD/SELL), position_size_pct, order_type, stop_loss_pct |

---

## World-Class Frameworks (baked into agent prompts)

| Framework | Agent | What it does |
|---|---|---|
| Wyckoff Method | Technical | Accumulation/distribution phases, springs, upthrusts, composite man |
| ICT Concepts | Technical | Fair Value Gaps, Order Blocks, Liquidity Sweeps, Market Structure Shifts |
| Turtle Trader Rules | Technical | 20-day breakouts, ATR stops (2×ATR14), pyramid into winners |
| Smart Money Concepts | Technical | Premium/discount zones, stop hunts, institutional hiding spots |
| Options Flow Analysis | Sentiment | PCR interpretation, UOA (unusual options activity), IV crush |
| Institutional Flow | Sentiment | 13F direction analysis, dumb vs smart money distinction |
| CANSLIM | Fundamental | C/A/N/S/L/I/M — framework behind biggest historical stock winners |
| PEAD Strategy | Fundamental | Post-earnings drift — systematic underreaction to earnings beats |
| AQR Quality Factor | Fundamental | Margin stability, ROE consistency, operating leverage |
| Kelly Criterion | Risk Manager | Half-Kelly position sizing: f* = (p×b - q)/b, capped at 5% |
| ATR-based Stops | Risk Manager | Dynamic stops = 2×ATR(14) — adapts to current volatility |
| Portfolio VaR | Risk Manager | 25% sector cap, 20% cash reserve, 5% daily drawdown circuit breaker |
| Position Pyramid | Portfolio Mgr | Initial 50%, add 25% at 1×ATR, add 25% at 2×ATR in-favor |
| 3-Target Exit | Portfolio Mgr | T1 at 1.5:1 R:R (33% off), T2 at 2.5:1 (50% off), T3 trailing |

---

## Market Regime Detector

**File:** `backend/app/workers/regime_detector.py`

Classifies market into 4 regimes using SPY + VIX data. 15-minute cache shared between scanner and API.

| Regime | Trigger | Strategy | Max Position |
|---|---|---|---|
| BULL_TRENDING | SPY > MA50 > MA200, RSI 50-70, VIX < 20 | Momentum, buy breakouts | 5% |
| BEAR_TRENDING | SPY < MA50 < MA200 | Reduce exposure, tight stops | 2% |
| HIGH_VOLATILITY | VIX > 28 | Cash, highest conviction only | 1.5% |
| SIDEWAYS | Mixed signals | Mean reversion, buy oversold | 3% |

API: `GET /api/v1/market/regime`

---

## Scanner

**File:** `backend/app/workers/scanner.py`

Multi-factor pre-screen + full AI analysis on top candidates.

Factors scored: RSI, MACD, price vs MA50/MA200, volume ratio, ATR-14, Bollinger Bands width,
Stochastic %K, ROC-10, volume trend, mean reversion setup, 52-week high proximity, PEAD signal.

Custom criteria via `ScanCriteria` (in `agents.py` POST body):
- `rsi_min`, `rsi_max`, `vol_ratio_min`, `min_score`, `direction`
- `require_above_ma50`, `require_above_ma200`, `require_macd_bullish`

Circuit breakers: VIX gate (>30 suppresses BUYs), daily drawdown halt (-5%), earnings blackout.

---

## Design System

**Colors (Tailwind tokens — all in tailwind.config.ts):**
- `bg-base` `#0A0E1A` — page background
- `bg-surface` `#0F1629` — sidebar, header, panels
- `bg-card` `#141D30` — cards
- `bg-elevated` `#1A2540` — table rows, inputs
- `accent` `#2D7DD2` — buttons, active states, WS glow
- `gain` `#00E676` — positive P&L, BUY
- `loss` `#FF3D57` — negative P&L, SELL
- `warn` `#FFB740` — HOLD, alerts, pending

**Fonts:** UI: `Inter` | Numbers/tickers: `JetBrains Mono` (class: `font-mono`)

**Reusable CSS classes (index.css):**
- `.card` — standard card surface + border + shadow
- `.card-hover` — adds hover shadow + border highlight
- `.metric-label` — small caps label for KPI cards
- `.metric-value` — large mono number display
- `.badge-gain` / `.badge-loss` / `.badge-neutral` — colored P&L badges
- `.sidebar-item` / `.sidebar-item-active` — nav item states
- `.price` — mono tabular-nums for price display

**Tooltip component:** `src/components/ui/Tooltip.tsx`
- `<TermTooltip term="rsi" />` — 20 pre-built financial term explanations
- Terms: rsi, macd, ma50, ma200, pe, beta, sharpe, drawdown, vol_ratio, vix, iv, oi, itm, momentum, score, confidence, stopLoss, buyingPower, unrealizedPnl

---

## Database Schema

**`agent_runs`**
```
id (uuid PK), ticker, analysis_date, status, decision, confidence,
summary (text), debate_log (JSON array), reasoning_json (JSON — full typed contracts),
llm_model, debate_rounds, error, created_at, completed_at
```

**`trades`**
```
id (uuid PK), agent_run_id (FK), alpaca_order_id, ticker, side, qty,
order_type, limit_price, filled_price, filled_qty, status, pnl,
stop_loss_pct, take_profit_pct, closed_reason,
reasoning_json (JSONB — full audit trail), submitted_at, filled_at, closed_at
```

---

## Environment Variables (see .env.example)

```bash
# Required to run agents
ANTHROPIC_API_KEY=sk-ant-...

# Required for broker / market data
ALPACA_API_KEY=PK...
ALPACA_API_SECRET=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets   # KEEP THIS — paper only

# DB (defaults work with docker compose)
POSTGRES_USER=tap / POSTGRES_PASSWORD=tap_secret / POSTGRES_DB=trading

# Agent defaults
LLM_MODEL=claude-sonnet-4-6
AGENT_DEBATE_ROUNDS=2
```

---

## How to Run

```bash
# Full stack (Docker)
cp .env.example .env    # fill ANTHROPIC_API_KEY + ALPACA keys
make up                 # starts all 9 services
# → Frontend: http://localhost:5173
# → Backend:  http://localhost:8000
# → API docs: http://localhost:8000/docs

# Local dev (no Docker)
make frontend           # npm install + vite dev server
make backend            # uvicorn --reload

# After schema changes
docker exec tap_backend alembic upgrade head

# Rebuild backend after Python changes
docker compose up --build backend -d
```

---

## What's Done ✅

- Full Docker Compose infra + JWT auth (30-min access tokens + rotating refresh tokens; legacy 30-day JWTs valid until expiry)
- 7 AI agent pipeline (TechnicalReport → FinalDecision) with Pydantic contracts
- World-class frameworks in every agent prompt (see table above)
- Market regime detector with 4-regime classification + 15min cache
- NIM/OpenAI-compatible inference — `tool_choice="required"`, 60s timeout, JSON fallback parser
- WebSocket live streaming of agent debate to frontend
- Settings API key hot-reload: saves to DB + updates `os.environ` + clears settings cache
- **Dashboard**: KPIs, AI market brief (Redis 15min cache), system status, live position prices (8s flash)
- **Markets**: any-stock charts (150+ autocomplete), indices strip, sector heatmap, top movers
- **Watchlist**: live price grid, 8s polling, 52w range bar, add/remove
- **News**: per-ticker news via Alpaca News API (yfinance fallback), 5min auto-refresh
- **Calendar**: FOMC/CPI/NFP 2026 dates + earnings via yfinance, "Soon" warnings within 3 days
- **Scanner**: pre-screen with live progress, multi-factor scoring, advanced filter panel, company names, TermTooltips
- **Agent Hub**: animated pipeline, live debate, ?ticker= URL pre-fill, custom scan criteria
- **Options Desk**: AI CALL/PUT/NO_PLAY + live options chain (calls/puts, IV, OI, ITM)
- **Portfolio**: live positions, equity curve (15min snapshots + Alpaca 30-day backfill), P&L calendar
- **Trade History**: virtualized table + full reasoning audit drawer + CSV export + company names
- **Orders**: open orders (10s auto-poll), order history, cancel single/all with confirmation
- **Backtesting**: RSI/MACD/MA signal simulation, equity curve vs SPY, trade log
- **Analytics**: AI performance grade A-F, correlation matrix, sector exposure
- **Alerts**: 5 smart alert types (concentration, drawdown, take-profit, RSI, stale positions)
- **Strategy**: live regime card with color coding, 8 active frameworks display, 12 hardcoded risk rules, platform philosophy
- **Learn**: 47-term glossary, 6 categories, real-time search, staggered animations
- **Settings**: model selector, risk sliders, watchlist CRUD, API key hot-reload
- **Notifications**: bell → slide-in drawer, unread badge, mark-read/all-read
- Background workers: position monitor, equity tracker, scheduler, price feed, trade sync
- Error boundary, bundle splitting (202KB main chunk)
- Company names throughout platform via batch `/market/names` endpoint (50+ hardcoded + yfinance fallback)
- Git history cleaned — no AI attribution in commit history

---

## Known Issues / Watch Out (multi-tenant additions)

- market.py / backtest.py / price_feed use platform env Alpaca keys for market DATA (fine — data is not account-scoped)
- ALL FIXED 2026-07-02: export-csv shadowing, WS auth (JWT via ?token=, frontend `wsUrl()`),
  worker double-run (worker container = trade_sync + equity_tracker ONLY; backend lifespan
  = position_monitor, scheduler, overnight, price_feed — never start a loop in both),
  per-user circuit breakers, legacy env account deduped via `legacy_env_client()`
- Settings keys are 1:1 frontend↔backend now (scan_enabled, long_only,
  min_confidence_to_trade, intraday_monitor_enabled, overnight_agent_enabled,
  scan_max_candidates, max_position_pct, daily_loss_limit_pct) — keep them in sync
- long_only=false → SELL signals liquidate existing longs only; naked shorts are never placed

## Known Issues / Watch Out

- Docker frontend on Windows does NOT hot-reload: bind-mount file events don't reach
  Vite in the container. After frontend changes, `docker compose restart frontend`
  (and hard-refresh the browser). To preview logged-out pages with a logged-in browser,
  open http://127.0.0.1:5173 — different origin, no stored token (CORS-allowed in main.py).
- `structured_runner.py` uses `asyncio.run_coroutine_threadsafe` for WS emit from thread executor
- `tool_choice="required"` used for NIM — do NOT change to named function format
- Alembic not auto-run on startup — run `docker exec tap_backend alembic upgrade head` after schema changes
- Recharts bundle is large (573KB) — already split via Vite manualChunks
- bcrypt: NEVER use passlib `pwd_context` — use `import bcrypt; bcrypt.hashpw/checkpw` directly (see core/auth.py)
- Trade sync: new trades save as `"submitted"` status; sync worker polls all pre-fill statuses (pending_new, new, accepted, submitted, partial) every 2 min

---

## Agent Discipline Rules (hardcoded — do not soften)

| Rule | Value | Enforced? |
|---|---|---|
| Min confidence to signal | 0.60 | Yes |
| Min confidence for trade | 0.70 | Yes |
| Min consensus for BUY/SELL | 3 of 4 analysts | Yes |
| Max position size | 5% portfolio | Yes |
| Mandatory stop-loss | 7% default (or 2×ATR if data available) | Yes |
| Min Risk/Reward ratio | 2:1 | Yes |
| VIX gate | VIX > 30 → suppress BUY signals | Yes |
| Daily drawdown halt | -5% portfolio → pause all scans | Yes |
| Earnings blackout | Within 3 days of earnings → block trade | Yes |

**Philosophy:** "Consistency over home runs. 1% per day compounded = 1,000% per year. Preserve capital first, profits second."
