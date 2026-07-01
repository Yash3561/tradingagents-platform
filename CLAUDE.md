# TradingAgents Platform — Session Checkpoint

> Rally race co-driver notes. Read this before touching anything.
> Last updated: 2026-07-01

---

## What This Is

A **professional-grade multi-agent trading platform** built on top of
[TradingAgents](https://github.com/tauricresearch/tradingagents) (LangGraph-based).

**Not a toy.** Architecture is production-grade: Kafka, TimescaleDB, typed agent contracts,
WebSocket streaming, Alpaca paper trading integration.

**Always paper trading by default.** `ALPACA_BASE_URL` defaults to paper API.
Never switch to live without explicit user confirmation.

---

## Stack at a Glance

| Layer | Tech |
|---|---|
| Agent framework | TradingAgents (LangGraph) + Claude API |
| Backend | FastAPI + asyncpg + SQLAlchemy async |
| Message queue | Redis pub/sub (Kafka removed for free tier — add back on paid infra) |
| Time-series DB | PostgreSQL (TimescaleDB removed for free tier — add back on paid infra) |
| Relational DB | PostgreSQL 16 (trades, agent runs, settings) |
| Cache / pub-sub | Redis 7 |
| Broker | Alpaca (paper by default) |
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| Animations | Framer Motion |
| Charts | Recharts (portfolio/backtest) — TradingView Lightweight Charts (candlestick, planned) |
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
│   │   ├── api/v1/              ← REST endpoints (agents, dashboard, portfolio, trades, market, backtest, settings, ws)
│   │   ├── agents/
│   │   │   ├── contracts.py     ← ★ AGENT CONTRACTS (Pydantic schemas for all 7 agents)
│   │   │   ├── structured_runner.py ← ★ MAIN RUNNER (uses contracts + Claude tool_use)
│   │   │   └── runner.py        ← Legacy runner (TradingAgents graph wrapper + mock fallback)
│   │   ├── core/
│   │   │   ├── postgres.py      ← Async SQLAlchemy engine + Base
│   │   │   ├── redis_client.py  ← Redis async client
│   │   │   └── websocket_manager.py ← Room-based WS broadcast
│   │   ├── db/models/
│   │   │   ├── agent_run.py     ← AgentRun ORM (stores full debate_log + reasoning_json JSONB)
│   │   │   └── trade.py         ← Trade ORM (reasoning_json = full audit trail per trade)
│   │   └── workers/main.py      ← Background worker entry point
│   └── requirements.txt
│
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── layout/          ← Shell, Sidebar, Header (market clock, indices), StatusBar
│       │   ├── agent/           ← AgentFlow (animated pipeline), DebateTimeline
│       │   └── data-display/    ← MetricCard, PnLBadge
│       ├── pages/
│       │   ├── Dashboard/       ← KPIs, market pulse, live positions, agent activity
│       │   ├── AgentHub/        ← Main feature: run analysis, watch debate live
│       │   ├── Portfolio/       ← Positions, allocation pie, sector bars, risk metrics
│       │   ├── TradeHistory/    ← Table + slide-out audit drawer with full reasoning
│       │   ├── Backtesting/     ← Form + equity curve vs benchmark
│       │   └── Settings/        ← Model selector, risk sliders, API key fields
│       ├── lib/                 ← api.ts, cn.ts, formatters.ts, queryClient.ts
│       └── index.css            ← Tailwind base + component layer (.card, .badge-gain, etc.)
│
└── scripts/
    └── init_timescale.sql       ← TimescaleDB hypertable setup (auto-runs on container start)
```

---

## Agent Pipeline (The Core)

```
User triggers: POST /api/v1/agents/run { ticker, debate_rounds, model }
                          │
                          ▼
          structured_runner.py: run_structured_agent_analysis()
                          │
          ┌───────────────┼───────────────────────────────────┐
          │               │               │                   │
    Technical         Sentiment        News             Fundamental
    Analyst           Analyst          Analyst          Analyst
    → TechnicalReport → SentimentReport → NewsReport → FundamentalReport
          │               │               │                   │
          └───────────────┴───────────────┴───────────────────┘
                          │  AnalystBundle (typed aggregate)
                          ▼
                   Researcher Debate
                   (Bull vs Bear, N rounds)
                   → ResearcherDebate
                          │
                          ▼
                   Risk Manager
                   → RiskAssessment (has veto power — approved: bool)
                          │
                          ▼
                   Portfolio Manager
                   → FinalDecision (BUY / HOLD / SELL + order params)
                          │
              ┌───────────┴────────────┐
              │                        │
       Save to DB               Broadcast WS
       (reasoning_json           room: run:{id}
       = full typed log)         → frontend animates
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

**API endpoint:** `GET /api/v1/agents/contracts` — returns all schemas as JSON.
**Per-agent:** `GET /api/v1/agents/contracts/{agent_name}`

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

**Fonts:**
- UI text: `Inter`
- Numbers/prices/tickers: `JetBrains Mono` (class: `font-mono`)

**Reusable CSS classes (index.css):**
- `.card` — standard card surface + border + shadow
- `.card-hover` — adds hover shadow + border highlight
- `.metric-label` — small caps label for KPI cards
- `.metric-value` — large mono number display
- `.badge-gain` / `.badge-loss` / `.badge-neutral` — colored P&L badges
- `.sidebar-item` / `.sidebar-item-active` — nav item states
- `.price` — mono tabular-nums for price display

---

## Database Schema

### PostgreSQL (relational)

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
reasoning_json (JSONB — full audit trail), submitted_at, filled_at
```

### TimescaleDB (time-series)

**`ohlcv_bars`** — hypertable on `time`. Columns: ticker, timeframe, open/high/low/close, volume, vwap
**`tick_data`** — hypertable on `time`. Columns: ticker, price, size, bid, ask
**`equity_curve`** — hypertable on `time`. Columns: equity, cash, day_pnl

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
TS_USER=tap / TS_PASSWORD=tap_secret / TS_DB=market_data

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
# → Kafka UI: http://localhost:8080

# Local dev (no Docker)
make frontend           # npm install + vite dev server
make backend            # uvicorn --reload
```

---

## What's Done ✅

- Full Docker Compose infra + JWT auth (register/login, 30-day tokens)
- 7 AI agent pipeline (TechnicalReport → FinalDecision) with Pydantic contracts
- NIM/DeepSeek V4 Flash inference — `tool_choice="required"`, 60s timeout, JSON fallback parser
- WebSocket live streaming of agent debate to frontend
- All 7 DB models with JSONB audit trails + Alembic migrations
- **Dashboard**: KPIs, AI market brief (Redis 15min cache), system status, live position prices (8s flash)
- **Markets**: any-stock charts (150+ autocomplete), indices strip, sector heatmap, top movers
- **Agent Hub**: animated pipeline, live debate, ?ticker= URL pre-fill
- **Options Desk**: AI CALL/PUT/NO_PLAY + live options chain (calls/puts, IV, OI, ITM) — fixed hang
- **Portfolio**: live positions, equity curve (15min snapshots + Alpaca 30-day backfill), P&L calendar
- **Trade History**: virtualized table + full reasoning audit drawer + CSV export
- **Backtesting**: RSI/MACD/MA signal simulation, equity curve vs SPY, trade log
- **Analytics**: AI performance grade A-F, correlation matrix, sector exposure
- **Alerts**: 5 smart alert types (concentration, drawdown, take-profit, RSI, stale positions)
- **Scanner**: pre-screen with live progress, results table
- **Settings**: model selector, risk sliders, watchlist CRUD, API key fields
- **Notifications**: bell → slide-in drawer, unread badge, mark-read/all-read
- Background workers: position monitor, equity tracker, scheduler, price feed (Alpaca WS → Redis)
- Error boundary, bundle splitting (202KB main)

## Known Issues / Watch Out

- `structured_runner.py` uses `asyncio.run_coroutine_threadsafe` for WS emit from thread executor
- `tool_choice="required"` used for NIM/DeepSeek — do NOT change to named function format
- Alembic not auto-run on startup — run `docker exec tap_backend alembic upgrade head` after schema changes
- Settings API key fields save to DB settings table but backend reads from `.env` at startup — not hot-reloaded
- Recharts bundle is large (573KB) — already split via Vite manualChunks
- bcrypt: NEVER use passlib `pwd_context` — use `import bcrypt; bcrypt.hashpw/checkpw` directly (see core/auth.py)

## Agent Discipline Rules (hardcoded — do not soften)

| Rule | Value | Enforced? |
|---|---|---|
| Min confidence to signal | 0.60 | Yes |
| Min confidence for trade | 0.70 | Yes |
| Min consensus for BUY/SELL | 3 of 4 analysts | Yes |
| Max position size | 5% portfolio | Yes |
| Mandatory stop-loss | 7% default | Yes |
| HIGH risk → auto-reject | always | Yes |

**Philosophy:** "Being wrong on a HOLD costs opportunity. Being wrong on a BUY costs real money."
