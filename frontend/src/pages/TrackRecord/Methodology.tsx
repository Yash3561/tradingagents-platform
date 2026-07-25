import { TrendingUp, ArrowLeft } from "lucide-react";

const SECTIONS: { title: string; body: string }[] = [
  {
    title: "\"Total Analyses\"",
    body: "Every completed analysis across all six strategy engines this platform runs — the 7-agent LLM debate pipeline, and five deterministic, zero-LLM engines (a regime-filtered quant baseline, a 5-minute intraday rule engine, two post-earnings-drift engines for stock and options, and a monthly momentum rotation). This is a platform-wide count, not exclusively the AI debate engine — a deterministic rule firing counts the same as a full agent debate here.",
  },
  {
    title: "Decision Mix (BUY / HOLD / SELL)",
    body: "Tallied across every completed analysis that recorded a decision, all six engines combined. A disciplined system says HOLD most of the time by design — the AI Agents engine specifically requires 3-of-4 analyst consensus, at least 70% confidence, and a minimum 2:1 reward-to-risk before a trade is even eligible to place.",
  },
  {
    title: "Avg Confidence",
    body: "The average confidence score across every analysis that reported one (the deterministic engines report a fixed confidence tied to their rule strength, not a probabilistic estimate). Only analyses at or above 70% confidence are permitted to actually place a trade — this number will always sit below that threshold since it includes every HOLD and every low-conviction pass, not just the trades that fired.",
  },
  {
    title: "Closed Trades, Win Rate, Total P&L",
    body: "The most important rule on this page: only trades that have actually CLOSED — exited the position, with a realized profit or loss — are counted here. An open position is excluded entirely, whether it's currently up or down, until it closes. That's deliberate: it means this number can never be inflated by screenshotting a lucky moment on a position still in flight, and can't be unfairly deflated by counting a loss on a trade that hasn't been given the time its own strategy calls for (a multi-day earnings-drift hold, a monthly rotation, etc.). \"Win\" means realized P&L greater than zero on that closed trade.",
  },
  {
    title: "Monthly Activity & Win Rate",
    body: "Analyses are grouped by the month they ran. Win rate is grouped by the month a trade actually CLOSED, not the month it opened — a position opened in July and closed in August counts toward August's win rate. Months with zero closed trades show no win-rate point rather than a misleading 0%.",
  },
  {
    title: "Recent AI Calls",
    body: "The 20 most recent completed analyses across the entire platform — ticker, decision, and confidence only. No account, no user identity, no dollar amounts. This list is a display window (capped at 20) — it is not used anywhere internally to determine whether the platform is running correctly on a given day; a separate, uncapped daily count handles that.",
  },
  {
    title: "What's deliberately NOT shown here",
    body: "Unrealized P&L on open positions — the same reasoning as closed-trades-only above. Per-account or per-user breakdowns — this page is platform-wide and anonymized. Which specific paper account or strategy variant produced which trade.",
  },
  {
    title: "Update cadence",
    body: "This data is cached for 5 minutes (Redis) to keep the public page cheap to serve — it is not a real-time tick-by-tick feed. A fresh page load may be looking at numbers up to 5 minutes old.",
  },
  {
    title: "The one disclaimer that matters most",
    body: "Every account behind these numbers is an Alpaca paper-trading account — simulated fills against real market prices, zero real money. Nothing here is investment advice, and nothing here should be read as a promise about what real capital would do.",
  },
];

export default function TrackRecordMethodology({ standalone = false }: { standalone?: boolean }) {
  const body = (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-text-primary">How These Numbers Are Computed</h1>
        <p className="text-sm text-text-muted mt-1">
          Every figure on the Track Record page, defined precisely — so nothing there has to be taken on faith.
        </p>
      </div>
      <div className="space-y-4">
        {SECTIONS.map((s) => (
          <div key={s.title} className="card p-5">
            <h2 className="text-sm font-semibold text-text-primary mb-2">{s.title}</h2>
            <p className="text-sm text-text-secondary leading-relaxed">{s.body}</p>
          </div>
        ))}
      </div>
    </div>
  );

  if (!standalone) {
    return (
      <div className="space-y-6">
        <a
          href="/track-record"
          className="flex items-center gap-1.5 text-sm text-text-muted hover:text-text-primary transition-colors w-fit"
        >
          <ArrowLeft size={14} /> Back to Track Record
        </a>
        {body}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg-base">
      <header className="border-b border-border bg-bg-surface">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-accent rounded-lg flex items-center justify-center">
              <TrendingUp size={16} className="text-white" />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">TradingAgents</p>
              <p className="text-2xs text-slate-500">Track Record Methodology</p>
            </div>
          </div>
          <a
            href="/track-record"
            className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-white transition-colors"
          >
            <ArrowLeft size={14} /> Back to Track Record
          </a>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-6 py-8">{body}</main>
    </div>
  );
}
