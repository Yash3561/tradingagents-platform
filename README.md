# TradingAgents Platform

A professional-grade multi-agent trading platform powered by LangGraph and large language models. Features a full 7-agent AI pipeline that debates market positions, manages risk autonomously, and executes paper trades on Alpaca.

> **Paper trading only by default.** `ALPACA_BASE_URL` defaults to the Alpaca paper API. Never switch to live without explicit configuration.

---

## Features

### AI Agent Pipeline
- **7-agent debate system**: Technical → Sentiment → News → Fundamental analysts feed into a Bull vs Bear researcher debate, Risk Manager (veto power), and Portfolio Manager (final BUY/HOLD/SELL)
- **Typed agent contracts**: Every agent outputs a strict Pydantic schema — no free-form text between agents
- **Live WebSocket streaming**: Watch the debate unfold in real-time as each agent completes
- **Autonomous trade execution**: Approved signals auto-execute on Alpaca paper account

### Pages (19 total)

| Page | What it does |
|------|-------------|
| **Dashboard** | KPIs, AI market brief (Redis cached), live position prices with flash animation |
| **Markets** | TradingView candlestick charts for any stock/ETF/index, 160+ ticker autocomplete, sector heatmap, top movers |
| **Watchlist** | Live price grid for saved tickers, 52-week range bar, 8s polling with ▲/▼ flash |
| **News** | Per-ticker news feed via Alpaca News API (yfinance fallback), 5min auto-refresh |
| **Calendar** | FOMC, CPI, NFP schedule + earnings dates for watchlist tickers |
| **Scanner** | Pre-screens 40+ stocks with RSI/MACD/MA/momentum signals, custom filter criteria, runs AI on top candidates |
| **Agent Hub** | Run analysis on any ticker, watch 7-agent debate live, `?ticker=` URL pre-fill |
| **Options Desk** | AI CALL/PUT/NO_PLAY recommendation + live options chain (IV, OI, bid/ask, ITM) |
| **Portfolio** | Live positions, equity curve (15min snapshots + 30-day Alpaca backfill), P&L calendar heatmap |
| **Orders** | View/cancel open orders with live 10s polling, bracket order legs, order history |
| **Trade History** | Virtualized table with full AI reasoning audit drawer, CSV export |
| **Backtesting** | RSI/MACD/MA signal simulation, equity curve vs SPY benchmark |
| **Analytics** | AI performance grade A–F, correlation matrix, sector exposure |
| **Alerts** | 5 smart alert types: concentration, drawdown, take-profit, RSI, stale positions |
| **Settings** | Model selector, risk sliders, watchlist CRUD, API key fields (hot-reload — no restart needed) |
| **Notifications** | Slide-in drawer, unread badge, mark-read/all-read |

---

## Stack

| Layer | Tech |
|-------|------|
| Agent framework | LangGraph + LLM API |
| Backend | FastAPI + asyncpg + SQLAlchemy async |
| Message queue | Redis pub/sub |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| Broker | Alpaca (paper by default) |
| Market data | yfinance, Alpaca Data API |
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| Animations | Framer Motion |
| Charts | TradingView Lightweight Charts (candlestick), Recharts (portfolio/backtest) |
| State | Zustand + TanStack Query |
| Infra | Docker Compose (9 services) |

---

## Quick Start

### Prerequisites
- Docker + Docker Compose
- Alpaca paper trading account (free at [alpaca.markets](https://alpaca.markets))
- LLM API key (Anthropic or NVIDIA NIM)

### Setup

```bash
git clone https://github.com/Yash3561/tradingagents-platform.git
cd tradingagents-platform

cp .env.example .env
# Edit .env and fill in your API keys
```

Required `.env` values:

```bash
ANTHROPIC_API_KEY=sk-ant-...      # or use NVIDIA_API_KEY for free inference
ALPACA_API_KEY=PK...
ALPACA_API_SECRET=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets   # keep this — paper only
```

### Run

```bash
make up         # starts all 9 services
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

### Local dev (no Docker)

```bash
make frontend   # npm install + vite dev
make backend    # uvicorn --reload
```

---

## Agent Pipeline

```
POST /api/v1/agents/run { ticker, debate_rounds, model }
                │
    ┌───────────┼───────────────────┐
    │           │           │       │
Technical   Sentiment   News   Fundamental
Analyst     Analyst   Analyst   Analyst
    │           │           │       │
    └───────────┴───────────┴───────┘
                │  AnalystBundle
                ▼
        Researcher Debate
        (Bull vs Bear, N rounds)
                │
                ▼
          Risk Manager
          (veto power — approved: bool)
                │
                ▼
        Portfolio Manager
        → BUY / HOLD / SELL + order params
                │
        ┌───────┴────────┐
        │                │
    Save to DB      Broadcast WS
    (full audit)    → frontend animates
```

Every step streams a WebSocket event to the frontend in real-time.

---

## Agent Discipline Rules

| Rule | Value |
|------|-------|
| Min confidence to signal | 0.60 |
| Min confidence to trade | 0.70 |
| Min analyst consensus | 3 of 4 |
| Max position size | 5% portfolio |
| Mandatory stop-loss | 7% default |
| HIGH risk → auto-reject | always |

> "Being wrong on a HOLD costs opportunity. Being wrong on a BUY costs real money."

---

## Database Schema

**`agent_runs`** — full debate log + typed contract JSON per run

**`trades`** — every trade with complete AI reasoning audit trail (JSONB)

**`equity_snapshots`** — 15-minute equity curve snapshots

**`notifications`**, **`activity_log`**, **`settings`**, **`users`**

Run migrations after schema changes:
```bash
docker exec tap_backend alembic upgrade head
```

---

## Scanner

The scanner pre-screens 40+ stocks using free technical signals (no AI cost):
- RSI-14, MACD crossover, MA50/MA200 trend, 1W/1M/3M momentum, volume ratio
- Custom filter criteria via the UI (RSI range, volume spike, direction, MA filters)
- Top candidates run through the full 7-agent AI pipeline
- VIX gate: suppresses BUY signals when VIX > 30
- Circuit breakers: blocks scan under extreme drawdown conditions

---

## Environment Variables

See `.env.example` for the full list. Key variables:

```bash
ANTHROPIC_API_KEY        # Claude API
NVIDIA_API_KEY           # NVIDIA NIM (free tier available)
ALPACA_API_KEY           # Alpaca broker
ALPACA_API_SECRET
ALPACA_BASE_URL          # https://paper-api.alpaca.markets (default)
POSTGRES_USER/PASSWORD/DB
REDIS_URL
LLM_MODEL                # default: deepseek-ai/deepseek-v4-flash
AGENT_DEBATE_ROUNDS      # default: 2
```

---

## License

MIT
