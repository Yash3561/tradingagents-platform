# UI Redesign Brief — TradingAgents Platform

> The working brief for the full visual overhaul. Read CLAUDE.md first for
> platform context; this file is the design mandate. Kick off a session with:
> "Read docs/UI_REDESIGN.md and execute the redesign, phase by phase."

## Goal

The platform works but reads "vibe coded." The redesign target is the feel of
Linear / Vanta / modern fintech (Alpaca's own dashboard): calm, dense but
breathable, deliberate motion, zero layout jank. **Trust is the product** —
users hand over API keys and watch AI trade; every sloppy pixel costs
credibility. Retention comes from the product feeling engineered.

## What already exists (don't rebuild, refine)

- Dark theme tokens in `tailwind.config.ts`: bg-base `#0A0E1A`, bg-surface
  `#0F1629`, bg-card `#141D30`, bg-elevated `#1A2540`, accent `#2D7DD2`,
  gain `#00E676`, loss `#FF3D57`, warn `#FFB740`.
- Fonts (2026-07-13): **Space Grotesk** h1–h3 (tracking −0.02em), **Inter**
  body (cv02/03/04/11 enabled), **JetBrains Mono** for all numbers/tickers.
  `font-display` utility exists in tailwind config.
- Component classes in `index.css`: `.card`, `.card-hover`, `.metric-label`,
  `.metric-value`, `.badge-gain/loss/neutral`, `.price`, `.sidebar-item`.
- Framer Motion is installed and used ad hoc (inconsistent timings — unify).
- Mobile: sidebar drawer below `lg`, grids stack below `lg` — keep working.

## Hard constraints (violating these breaks production)

1. **CSP is enforced** on Vercel: `script-src 'self'`, styles/fonts only from
   self + Google Fonts, `connect-src` pinned to the Render backend. No new
   CDNs, no inline `<script>`, no runtime-injected external resources.
   New Google Fonts weights/families must be added to the SINGLE existing
   `fonts.googleapis.com` link in index.html.
2. **Sticky elements inside the Shell scroll container**: `<main>` has
   `p-4 md:p-6`; browsers inset sticky constraints by that padding. Pattern
   (see `pages/Learn/index.tsx`): root gets `-m-4 md:-m-6`, sticky gets
   `-top-4 md:-top-6`. Audit any page that adds sticky UI.
3. **Docker frontend on Windows does NOT hot-reload** — after changes:
   `docker compose restart frontend` + hard-refresh. Verify with the browser,
   not by assumption.
4. `npm run build` must stay green (tsc strict). Keep the manualChunks split.
5. Don't touch auth/api plumbing (`lib/api.ts` has the refresh-token
   interceptor), WS wiring (`wsUrl()`), or any backend contract.
6. Test pages logged-out via http://127.0.0.1:5173 (different origin = no
   stored token).

## Design system pass (Phase 0 — do this before touching pages)

- **Motion tokens**: one spring + two durations (fast 150ms, base 250ms),
  ease `[0.16, 1, 0.3, 1]`. Respect `prefers-reduced-motion` globally.
  Standardize page-enter (fade + 8px rise, stagger 40ms) as a shared
  `<PageTransition>` / `motion` variants module in `src/lib/motion.ts`.
- **Elevation scale**: card → hover → modal; consistent shadow + border-bright
  combos (exists partially as `.card-hover`).
- **Spacing rhythm**: audit to a 4px grid; section gaps `space-y-6`.
- **Loading states**: build `<Skeleton>` (shimmer) and use it EVERYWHERE data
  loads — no empty white/black voids, no spinner-only pages.
- **Empty states**: every list/table gets an icon + one-line explanation +
  action button (e.g., Trade History empty → "No trades yet — run a scan").
- **Number animation**: count-up on KPI values (already flash on price ticks —
  unify the flash style: 300ms bg pulse gain/loss).

## Page sweep, in priority order

1. **Landing** (`pages/Landing/`) — first impression, currently the strongest
   page; align it with the new tokens, tighten hero typography (Space
   Grotesk), make the live-stats section skeleton-load.
2. **Dashboard** — the daily screen. KPI cards: consistent heights, count-up
   numbers, sparklines if cheap. Market brief card needs a proper loading
   skeleton (currently text pops in).
3. **Agent Hub** — the product's soul. The debate timeline deserves the most
   motion polish: agents "come alive" (avatar pulse while running, message
   slide-in, confidence bars animating to value). Keep WS logic untouched.
4. **Scanner** — progress UX during scans (per-candidate pipeline status is
   already streamed via WS — surface it beautifully; currently feels dead
   while scanning for minutes).
5. **Portfolio / Trade History / Orders** — table polish: row hover, sticky
   table headers (see constraint 2), aligned mono columns, P&L color logic
   audit, CSV button placement.
6. **Strategy Lab + Research (Admin)** — the investor-demo pages. The
   tournament leaderboard and equity-curve comparison should look like a
   quant fund's internal tooling. Worth real attention.
7. **Settings** — group into cards with section descriptions; add the
   `quant_*` policy profile fields (backend accepts them already — see
   CLAUDE.md; sliders/selects with the NUMERIC_BOUNDS ranges, plus a
   "deploy tournament winner" preset button).
8. **Learn / Strategy / Analytics / Options / News / Calendar / Watchlist /
   Markets** — consistency pass: same header pattern, same card grid, same
   empty/loading states.
9. **Auth pages + VerifyEmailBanner** — AuthCard polish, form focus states,
   error shake (subtle), password-strength hint.

## Known broken/ugly (fix while passing through)

- Risk manager `rejection_reason` sometimes contains model chain-of-thought
  rambling — truncate display to first sentence in UI (backend cleanup is a
  separate task).
- Header market clock + indices strip crowds on ~1280px widths.
- Recharts tooltips are default-styled — theme them (dark bg-elevated,
  border, mono numbers).
- Favicon is a generic SVG — worth a proper mark.

## Definition of done, per page

- No layout shift on data load (skeletons reserve space).
- Works at 375px, 768px, 1280px, 1920px.
- `npm run build` green; page screenshot reviewed in browser at desktop +
  mobile width; logged-out state checked where applicable.
- No new CSP violations (check DevTools console on the prod preview).

## Suggested kickoff prompt for the redesign session

"Read CLAUDE.md, then docs/UI_REDESIGN.md. Execute Phase 0 (motion tokens,
Skeleton component, empty-state component), then sweep pages in the priority
order listed, verifying each in the browser at desktop and mobile widths
before moving on. Commit per phase. Ship Landing + Dashboard + Agent Hub
before anything else."
