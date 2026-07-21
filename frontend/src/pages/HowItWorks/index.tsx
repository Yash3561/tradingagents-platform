import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import {
  Workflow, ScanLine, BrainCircuit, ShieldCheck, Send, Eye, CheckCircle2,
  BarChart2, Newspaper, LineChart, TrendingUp, Swords, Shield, PieChart,
  Compass, ArrowRight, Sparkles,
} from "lucide-react";
import { EASE, DUR } from "../../lib/motion";
import { OPEN_TOUR_EVENT } from "../../components/onboarding/GuidedTour";

const AGENT_STEPS = [
  {
    icon: BarChart2,
    color: "text-accent", bg: "bg-accent/10", border: "border-accent/20",
    name: "Technical Analyst",
    frameworks: "Wyckoff Method, ICT Concepts, Turtle Trader Rules, Smart Money Concepts",
    desc: "Reads price action for accumulation/distribution phases, fair value gaps and order blocks, ATR-based breakout levels, and where institutional stop hunts are likely — outputs trend, signal, and support/resistance.",
  },
  {
    icon: LineChart,
    color: "text-warn", bg: "bg-warn/10", border: "border-warn/20",
    name: "Sentiment Analyst",
    frameworks: "Options Flow Analysis, Institutional Flow",
    desc: "Reads unusual options activity and put/call skew, and separates dumb-money from smart-money positioning — outputs a sentiment score and institutional-flow read.",
  },
  {
    icon: Newspaper,
    color: "text-accent", bg: "bg-accent/10", border: "border-accent/20",
    name: "News Analyst",
    frameworks: "Catalyst & risk-event screening",
    desc: "Scans headlines for material news, upcoming catalysts (earnings, guidance, macro events), and risk events that could invalidate a setup regardless of what the chart says.",
  },
  {
    icon: TrendingUp,
    color: "text-warn", bg: "bg-warn/10", border: "border-warn/20",
    name: "Fundamental Analyst",
    frameworks: "CANSLIM, PEAD Strategy, AQR Quality Factor",
    desc: "Checks earnings acceleration, sector leadership and institutional ownership, post-earnings drift setups, and margin/ROE quality versus the sector.",
  },
  {
    icon: Swords,
    color: "text-gain", bg: "bg-gain/10", border: "border-gain/20",
    name: "Researcher Debate",
    frameworks: "Bull vs. Bear, multi-round",
    desc: "The four analyst reports feed a structured bull-vs-bear debate — a CANSLIM-style bull case argued against a value-trap bear case — before anything reaches risk management.",
  },
  {
    icon: Shield,
    color: "text-loss", bg: "bg-loss/10", border: "border-loss/20",
    name: "Risk Manager",
    frameworks: "Half-Kelly sizing, ATR stops, portfolio VaR",
    desc: "Has veto power over every trade. Sizes the position with half-Kelly, sets a stop off ATR(14), and checks it against sector-concentration and drawdown limits before it can pass through.",
  },
  {
    icon: PieChart,
    color: "text-gain", bg: "bg-gain/10", border: "border-gain/20",
    name: "Portfolio Manager",
    frameworks: "Position pyramid, 3-target exit",
    desc: "Turns an approved idea into an order: entry size, a staged pyramid for adding to winners, and a 3-target exit plan. This is the only step that actually writes BUY / HOLD / SELL.",
  },
];

const ENGINES = [
  {
    key: "agents", name: "AI Agents", cost: "LLM pipeline",
    desc: "The full 7-agent debate above, run end to end on every candidate. The most expensive and the most explainable — every decision carries its own reasoning trail.",
  },
  {
    key: "quant", name: "Quant Baseline", cost: "zero LLM cost",
    desc: "Deterministic, regime-filtered trend and mean-reversion rules with no model in the loop. The control group — if the agents can't beat this, the story is explainability, not alpha.",
  },
  {
    key: "intraday", name: "Intraday Rules", cost: "zero LLM cost",
    desc: "A 5-minute-bar rule engine that trades during market hours and is always flat by the close. Runs a dedicated always-on loop instead of riding the scheduled scans.",
  },
  {
    key: "earnings", name: "Earnings Drift", cost: "zero LLM cost",
    desc: "Post-earnings-announcement-drift: enters long the first session after a qualifying EPS surprise, holds for days, exits by stop, target, or a time-based hold-days limit.",
  },
  {
    key: "momentum", name: "Momentum Rotation", cost: "zero LLM cost",
    desc: "A concentrated monthly top-N relative-momentum rotation with no stops — exits only happen when a name rotates out of the ranks. Needs its own dedicated account, since it manages every position it sees.",
  },
  {
    key: "earnings_options", name: "Earnings Drift — Options", cost: "zero LLM cost",
    desc: "The same earnings-surprise trigger as Earnings Drift, expressed as a defined-risk long call instead of stock — loss capped at the premium paid, exits on a target premium gain, a max premium loss, or a time exit.",
  },
];

const TRADE_STEPS = [
  { icon: ScanLine, title: "Scan", desc: "Scheduled or manual — screens candidates by technical score, or by a real qualifying earnings surprise, depending on the strategy engine." },
  { icon: BrainCircuit, title: "Analyze", desc: "The 7-agent debate for the AI Agents engine, or a deterministic rule evaluation for the five zero-LLM engines." },
  { icon: ShieldCheck, title: "Risk Check", desc: "Position size, stop-loss, and reward:risk validated against hard discipline rules, order seatbelts, and the platform kill switch — any of which can block the trade outright." },
  { icon: Send, title: "Order", desc: "A bracket order (stop + target) is submitted to your own connected Alpaca paper account. No broker connected — analysis still runs, nothing is placed." },
  { icon: Eye, title: "Monitor", desc: "A background loop polls every open position, enforcing stops, targets, and time-based exits regardless of which engine opened it." },
  { icon: CheckCircle2, title: "Close", desc: "The closed trade lands in Trade History with the full reasoning trail that led to it — nothing is a black box after the fact." },
];

export default function HowItWorks() {
  const navigate = useNavigate();

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      transition={{ duration: DUR.base, ease: EASE }}
      className="space-y-8"
    >
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text-primary flex items-center gap-2">
            <Workflow size={20} className="text-accent" />
            How It Works
          </h1>
          <p className="text-sm text-text-muted mt-0.5 max-w-xl">
            The architecture behind every decision on this platform — the 7-agent pipeline,
            the six strategy engines you can choose between, and what actually happens
            between a scan and a filled trade.
          </p>
        </div>
        <button
          onClick={() => window.dispatchEvent(new Event(OPEN_TOUR_EVENT))}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border hover:border-accent/50 text-text-secondary hover:text-text-primary transition-all text-sm shrink-0"
        >
          <Compass size={14} />
          Take the tour again
        </button>
      </div>

      {/* 7-agent pipeline */}
      <div>
        <h2 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
          <BrainCircuit size={14} className="text-accent" />
          The 7-Agent Pipeline
        </h2>
        <p className="text-xs text-text-muted mb-4 max-w-2xl">
          Used in full by the AI Agents engine; the zero-LLM engines below run a
          deterministic subset of the same idea (rules instead of models) so they can
          be judged forward against it at zero cost.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {AGENT_STEPS.map((a, i) => (
            <motion.div
              key={a.name}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.04, duration: DUR.base, ease: EASE }}
              className="card p-4"
            >
              <div className="flex items-start gap-3">
                <div className={`w-8 h-8 rounded-lg ${a.bg} border ${a.border} flex items-center justify-center shrink-0`}>
                  <a.icon size={16} className={a.color} />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-sm font-semibold text-text-primary">{i + 1}. {a.name}</h3>
                  </div>
                  <p className="text-2xs text-text-muted mt-0.5">{a.frameworks}</p>
                  <p className="text-xs text-text-secondary leading-relaxed mt-2">{a.desc}</p>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Strategy engines */}
      <div>
        <h2 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
          <Sparkles size={14} className="text-accent" />
          Six Strategy Engines
        </h2>
        <p className="text-xs text-text-muted mb-4 max-w-2xl">
          Pick one per account in Settings → AI Model. Five of the six run at zero LLM
          cost by design — the AI Agents engine is judged forward against them, never
          backtested (its training data already contains the historical outcomes).
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {ENGINES.map((e, i) => (
            <motion.div
              key={e.key}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.04, duration: DUR.base, ease: EASE }}
              className="card p-4"
            >
              <div className="flex items-center justify-between mb-1.5">
                <h3 className="text-sm font-semibold text-text-primary">{e.name}</h3>
                <span className="text-2xs px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted border border-border shrink-0">
                  {e.cost}
                </span>
              </div>
              <p className="text-xs text-text-secondary leading-relaxed">{e.desc}</p>
            </motion.div>
          ))}
        </div>
      </div>

      {/* How a trade happens */}
      <div>
        <h2 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
          <ScanLine size={14} className="text-accent" />
          How a Trade Actually Happens
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {TRADE_STEPS.map((s, i) => (
            <motion.div
              key={s.title}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.04, duration: DUR.base, ease: EASE }}
              className="card p-4"
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg font-serif text-accent/60">{i + 1}</span>
                <s.icon size={15} className="text-accent" />
                <h3 className="text-sm font-semibold text-text-primary">{s.title}</h3>
              </div>
              <p className="text-xs text-text-secondary leading-relaxed">{s.desc}</p>
            </motion.div>
          ))}
        </div>
      </div>

      {/* CTA */}
      <div className="card p-5 flex items-center justify-between flex-wrap gap-3">
        <div>
          <h3 className="text-sm font-semibold text-text-primary">Want the exact numbers?</h3>
          <p className="text-xs text-text-muted mt-0.5">
            Live risk rules, current market regime, and every active framework are on the Strategy page.
          </p>
        </div>
        <button
          onClick={() => navigate("/strategy")}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold bg-accent text-white hover:bg-accent-bright transition-colors shrink-0"
        >
          View live Strategy rules <ArrowRight size={12} />
        </button>
      </div>
    </motion.div>
  );
}
