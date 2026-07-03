# TradingAgents Platform — Session Checkpoint

> Rally race co-driver notes. Read this before touching anything.
> Last updated: 2026-07-03 (real-user readiness: password reset, email verify, admin, rate limits)

---

## What This Is

A **multi-tenant paper-trading SaaS** — a professional-grade multi-agent trading platform where each user signs up, connects their own Alpaca **paper** account, and the AI agents analyze + trade in *their* account.

**Not a toy.** Architecture is production-grade: typed agent contracts, WebSocket streaming, per-user Alpaca integration, market regime detection, Kelly Criterion position sizing, ATR-based stops.

**Paper-only, enforced server-side.** `broker_connections.base_url` is forced to
the paper API in code (`PAPER_BASE_URL` in `db/models/broker_connection.py`).
Live trading is a deliberate future product/legal decision — do not soften this.

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
│   │   │   └── structured_runner.py ← ★ MAIN RUNNER — world-class frameworks in every prompt
│   │   ├── core/
│   │   │   ├── postgres.py      ← Async SQLAlchemy engine + Base
│   │   │   ├── redis_client.py  ← Redis async client
│   │   │   └── websocket_manager.py ← Room-based WS broadcast
│   │   ├── db/models/
│   │   │   ├── agent_run.py     ← AgentRun ORM (stores full debate_log + reasoning_json JSONB)
│   │   │   └── trade.py         ← Trade ORM (reasoning_json = full audit trail per trade)
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

- Full Docker Compose infra + JWT auth (register/login, 30-day tokens)
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
