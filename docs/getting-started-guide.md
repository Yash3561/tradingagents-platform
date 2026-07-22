# TradingAgents — Getting Started Guide

A quick reference for anyone new to the platform. Everything below is also built into
the product itself (an interactive tour on first login, and a "How It Works" page in
the sidebar) — this doc is just a version you can read before signing in, or come back
to later.

## What this is

A multi-agent **paper-trading** platform. You connect your own free Alpaca paper
account (virtual money, real market data), and the platform analyzes the market and
places trades in it automatically — or you can run analysis by hand on any ticker.

**No real money is ever involved.** Every account is paper-only, enforced on the
server, not just by a setting you could accidentally change.

## 1. Sign up

Use the invite link/code you were given, then create your account with an email and
password.

## 2. Get free Alpaca paper keys (2 minutes)

1. Go to [app.alpaca.markets](https://app.alpaca.markets) and create a free account
   (no card, no verification needed for paper trading).
2. In the top-left of the Alpaca dashboard, make sure **"Paper"** is selected (not
   "Live").
3. Generate an API key — you'll get a **Key ID** and a **Secret Key**.

## 3. Connect your broker

In the platform, go to **Settings → Broker Connection** and paste in the Key ID and
Secret Key from step 2. That's the only place API keys ever get entered — the
platform never asks for them anywhere else.

## 4. Pick a strategy engine

Settings → AI Model → Strategy Engine. Six options, in order of "start here" to "more
specialized":

| Engine | What it does |
|---|---|
| **AI Agents** (default) | Seven AI agents — technical, sentiment, news, and fundamental analysts feed a bull-vs-bear debate, then a risk manager and portfolio manager decide. The most explainable — every trade has a full reasoning trail attached. |
| **Quant Baseline** | Deterministic rules, no AI cost. The control group — a sanity check on whether the AI agents are actually adding value over simple rules. |
| **Intraday Rules** | 5-minute-bar trading during market hours, always flat by the close. |
| **Earnings Drift** | Enters after a real earnings beat, holds for days. |
| **Momentum Rotation** | Monthly rotation into the strongest-momentum names. Needs its own dedicated account. |
| **Earnings Drift — Options** | Same earnings-beat trigger as above, expressed as a defined-risk options trade instead of stock. Needs an options-enabled Alpaca account. |

If you're not sure, leave it on **AI Agents** — it's the default and the most
explainable one to watch.

## 5. Turn on scanning

Settings → Scanner → **Scheduled Auto-Scans**. Without this on, the platform will
analyze tickers you point it at by hand (Agent Hub) but won't scan the market or trade
on its own.

## 6. Explore

- The **guided tour** shows up automatically the first time you log in — spotlights
  the sidebar and explains what each section does. Re-launch it anytime from a button
  on the Settings page.
- **How It Works** (in the sidebar, under Intelligence) is the full write-up — the
  7-agent pipeline, all six strategy engines, and exactly how a trade goes from a scan
  to a filled position.
- **Trade History** shows every trade with its full AI reasoning attached — click any
  trade to see exactly why it happened.
- **Track Record** is a public, no-login page showing the platform's real decision
  history and win rate — nothing curated or cherry-picked.

## FAQ

**Is any of this real money?**
No. Every account connects to Alpaca's paper-trading API specifically — it's virtual
money against real market prices. This is enforced server-side, not just a setting.

**What if I don't understand a term (RSI, ATR, Kelly sizing, etc.)?**
Hover any underlined term in the app for a plain-language explanation, or check the
**Learn** page (sidebar → Intelligence) — a full glossary.

**Where do I see how well it's actually doing?**
Portfolio (your own account's equity curve and positions) or Track Record (the
platform-wide public number, decision mix and win rate).

**Something looks broken or confusing — who do I ask?**
Yash — ygc2@njit.edu.
