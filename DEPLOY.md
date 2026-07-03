# Deploying TradingAgents — $0/month stack

Four free services, ~30 minutes total:

| Piece | Service | Free tier |
|---|---|---|
| Postgres | [Neon](https://neon.tech) | 0.5 GB storage |
| Redis | [Upstash](https://upstash.com) | 500K commands/mo |
| Backend + workers | [Render](https://render.com) | 512 MB web service (sleeps when idle) |
| Frontend | [Vercel](https://vercel.com) | static hosting |
| Keep-awake ping | [UptimeRobot](https://uptimerobot.com) | 5-min interval monitor |

---

## 1. Neon (Postgres)

1. Create a project → database name `trading`.
2. Copy the connection string and convert it for asyncpg:
   ```
   postgresql+asyncpg://USER:PASS@ep-xxx.REGION.aws.neon.tech/trading?ssl=require
   ```
   (`postgresql://` → `postgresql+asyncpg://`, keep `?ssl=require`, drop any
   `&channel_binding=...` param if present.)
3. That's it — the backend creates all tables + runs schema upgrades on first boot.

## 2. Upstash (Redis)

1. Create a Redis database (region closest to your Render region).
2. Copy the **TLS** connection URL:
   ```
   rediss://default:PASSWORD@xxx.upstash.io:6379
   ```

## 3. Render (backend)

Option A — blueprint: push this repo to GitHub, then Render → **New → Blueprint**
→ pick the repo. `render.yaml` pre-fills everything; it will prompt for the
secret env vars.

Option B — manual: **New → Web Service** → repo → Root Directory `backend` →
runtime Docker → plan Free → Health Check Path `/health`, then set env vars:

| Var | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `RUN_ALL_WORKERS` | `true` — trade sync + equity tracker run in-process (no free worker services on Render) |
| `PRICE_FEED_ENABLED` | `false` — the tick stream would burn Upstash's free quota |
| `SECRET_KEY` | long random string. **Set once, never rotate** — it signs JWTs *and* encrypts users' broker keys |
| `DATABASE_URL` | the Neon URL from step 1 |
| `REDIS_URL` | the Upstash URL from step 2 |
| `FRONTEND_URL` | your Vercel URL (step 4) — CORS + emailed links |
| `ANTHROPIC_API_KEY` / `NVIDIA_API_KEY` | LLM keys |
| `ALPACA_API_KEY` / `ALPACA_API_SECRET` | platform paper keys — used for market **data** only; users connect their own accounts in Settings |
| `ADMIN_EMAIL` | your email — that account is auto-promoted to admin on login |
| `SIGNUP_INVITE_CODE` | recommended for launch — gates signups (or leave unset and issue DB invites from the Admin page… but the env code is the master gate, so unset = open signup) |

Deploy, wait for `/health` to go green, note the URL: `https://xxx.onrender.com`.

## 4. Vercel (frontend)

1. **New Project** → same repo → Root Directory `frontend` (framework: Vite).
2. Environment variables (build-time):
   - `VITE_API_URL` = `https://xxx.onrender.com`
   - `VITE_WS_URL` = `wss://xxx.onrender.com`
3. Deploy → copy the production URL → set it as `FRONTEND_URL` on Render (triggers a redeploy).

`frontend/vercel.json` already handles SPA rewrites (so `/reset-password` links work) and asset caching.

## 5. UptimeRobot (keep-awake)

Render free services sleep after 15 idle minutes — which also pauses the worker
loops (stop-loss monitoring, trade sync, scheduled scans). Add an HTTP monitor
hitting `https://xxx.onrender.com/health` every 5 minutes. This keeps the
service warm ~24/7 within free limits.

## 6. Smoke test

1. Open the Vercel URL → sign up with your `ADMIN_EMAIL` → Admin appears in the sidebar.
2. Settings → connect your Alpaca **paper** keys → dashboard populates.
3. Create an invite code in Admin → open the copied `/?invite=` link in an incognito window → signup pre-fills.

---

## Free-tier limitations (accept for launch, revisit at ~50 users)

- **Cold starts**: if the keep-awake ping lapses, first request takes ~50s.
- **512 MB RAM**: fine for the API + light worker loops; heavy scanner runs may OOM — keep `scan_max_candidates` modest.
- **No email**: password-reset/verification links are only *logged* to Render logs until you set `SMTP_*` env vars (free options: Brevo 300/day, Resend 100/day via SMTP).
- **Workers pause while asleep**: mitigated by UptimeRobot, but there's no hard guarantee — do not treat position-monitor stops as bulletproof on this tier.
- **Upstash 500K commands/mo**: rate limiting + caches are light; keep `PRICE_FEED_ENABLED=false`.

**First paid upgrade** when traction shows: Render Starter ($7/mo) — no sleep,
real worker guarantee. Everything else stays free far longer.
