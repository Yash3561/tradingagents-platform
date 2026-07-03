import { useEffect, useRef, useState } from "react";
import { motion, useInView, animate } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import {
  TrendingUp,
  BrainCircuit,
  Newspaper,
  BarChart3,
  Landmark,
  Scale,
  ShieldCheck,
  Briefcase,
  ScrollText,
  Radar,
  GitBranch,
  ArrowRight,
  Lock,
  CheckCircle2,
} from "lucide-react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

interface Props {
  onGetStarted: () => void;
  onSignIn: () => void;
}

// ── Hooks ─────────────────────────────────────────────────────────────────────

function useCountUp(target: number, start: boolean, duration = 1.4) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (!start) return;
    const controls = animate(0, target, {
      duration,
      ease: "easeOut",
      onUpdate: (v) => setValue(Math.round(v)),
    });
    return () => controls.stop();
  }, [target, start, duration]);
  return value;
}

const DEBATE_SCRIPT = [
  { who: "bull", text: "CANSLIM setup: earnings +42% YoY, breaking out of a 7-week base on 2.1x volume." },
  { who: "bear", text: "Breakout into VIX 24? Institutional flow is net negative — this smells like a stop hunt." },
  { who: "bull", text: "Wyckoff Phase D confirmed. Spring held, last point of support is in. Composite man is loading." },
  { who: "bear", text: "Forward P/E at 38 vs sector 22. One guidance miss and you're catching knives." },
  { who: "risk", text: "RISK MANAGER: approved 3.2% position — half-Kelly, stop at 2×ATR(14), R:R 2.4:1." },
] as const;

function useDebateLoop() {
  const [lines, setLines] = useState<{ who: string; text: string }[]>([]);
  const [typed, setTyped] = useState("");
  useEffect(() => {
    let line = 0;
    let char = 0;
    let alive = true;
    const tick = () => {
      if (!alive) return;
      const current = DEBATE_SCRIPT[line];
      if (char <= current.text.length) {
        setTyped(current.text.slice(0, char));
        char += 2;
        setTimeout(tick, 24);
      } else {
        setLines((prev) => [...prev.slice(-3), current]);
        setTyped("");
        line = (line + 1) % DEBATE_SCRIPT.length;
        if (line === 0) setLines([]);
        char = 0;
        setTimeout(tick, 900);
      }
    };
    const t = setTimeout(tick, 600);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, []);
  const currentWho = DEBATE_SCRIPT[(lines.length) % DEBATE_SCRIPT.length].who;
  return { lines, typed, currentWho };
}

// ── Pieces ────────────────────────────────────────────────────────────────────

const TICKER_TAPE = [
  { t: "NVDA", p: "+2.41%", up: true },
  { t: "AAPL", p: "+0.83%", up: true },
  { t: "SPY", p: "+0.35%", up: true },
  { t: "TSLA", p: "-1.27%", up: false },
  { t: "MSFT", p: "+1.02%", up: true },
  { t: "AMD", p: "+3.18%", up: true },
  { t: "META", p: "-0.44%", up: false },
  { t: "GOOGL", p: "+0.67%", up: true },
  { t: "AMZN", p: "+1.55%", up: true },
  { t: "QQQ", p: "+0.58%", up: true },
  { t: "PLTR", p: "-2.03%", up: false },
  { t: "AVGO", p: "+1.89%", up: true },
];

function TickerTape() {
  const items = [...TICKER_TAPE, ...TICKER_TAPE];
  return (
    <div className="relative overflow-hidden border-y border-border-subtle bg-bg-surface/60 backdrop-blur-sm">
      <div className="flex w-max animate-marquee gap-8 py-2 px-4">
        {items.map((x, i) => (
          <span key={i} className="flex items-center gap-2 text-xs font-mono whitespace-nowrap">
            <span className="text-text-secondary">{x.t}</span>
            <span className={x.up ? "text-gain" : "text-loss"}>{x.p}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

const AGENTS = [
  { icon: BarChart3, label: "Technical", sub: "Wyckoff · ICT" },
  { icon: Radar, label: "Sentiment", sub: "Options flow" },
  { icon: Newspaper, label: "News", sub: "Catalysts" },
  { icon: Landmark, label: "Fundamental", sub: "CANSLIM" },
  { icon: GitBranch, label: "Debate", sub: "Bull vs Bear" },
  { icon: Scale, label: "Risk Manager", sub: "Veto power" },
  { icon: Briefcase, label: "Portfolio Mgr", sub: "Final call" },
];

function PipelineAnimation() {
  const [stage, setStage] = useState(-1);
  const [decision, setDecision] = useState<"BUY" | "HOLD" | "SELL">("BUY");
  useEffect(() => {
    const seq = setInterval(() => {
      setStage((s) => {
        if (s >= AGENTS.length) {
          setDecision((d) => (d === "BUY" ? "HOLD" : d === "HOLD" ? "SELL" : "BUY"));
          return -1;
        }
        return s + 1;
      });
    }, 700);
    return () => clearInterval(seq);
  }, []);

  const decided = stage >= AGENTS.length;
  const decisionColor =
    decision === "BUY" ? "text-gain border-gain/40 bg-gain-bg shadow-gain-glow"
    : decision === "SELL" ? "text-loss border-loss/40 bg-loss-bg shadow-loss-glow"
    : "text-warn border-warn/40 bg-warn-bg";

  return (
    <div className="card p-6 md:p-8 overflow-x-auto">
      <div className="flex items-center gap-2 md:gap-3 min-w-[720px]">
        {AGENTS.map((a, i) => {
          const active = stage === i;
          const done = stage > i;
          return (
            <div key={a.label} className="flex items-center gap-2 md:gap-3 flex-1">
              <div
                className={cn(
                  "flex flex-col items-center gap-1.5 rounded-xl border px-3 py-3 w-full transition-all duration-300",
                  active
                    ? "border-accent bg-accent-muted/30 shadow-accent-glow scale-105"
                    : done
                    ? "border-accent/40 bg-bg-elevated"
                    : "border-border bg-bg-elevated/50 opacity-60"
                )}
              >
                <a.icon size={16} className={active || done ? "text-accent-bright" : "text-text-muted"} />
                <span className="text-2xs font-medium text-text-primary whitespace-nowrap">{a.label}</span>
                <span className="text-2xs text-text-muted whitespace-nowrap hidden md:block">{a.sub}</span>
              </div>
              {i < AGENTS.length - 1 && (
                <div className="h-px w-3 md:w-5 shrink-0 bg-gradient-to-r from-border to-border relative overflow-hidden">
                  {done && <div className="absolute inset-0 bg-accent" />}
                </div>
              )}
            </div>
          );
        })}
        <div className="h-px w-3 md:w-5 shrink-0 bg-border" />
        <motion.div
          animate={decided ? { scale: [0.9, 1.06, 1] } : {}}
          className={cn(
            "shrink-0 rounded-xl border px-4 py-4 font-mono text-sm font-bold transition-colors duration-300",
            decided ? decisionColor : "border-border text-text-muted"
          )}
        >
          {decided ? decision : "···"}
        </motion.div>
      </div>
      <p className="text-2xs text-text-muted mt-4 text-center">
        Live pipeline — every analysis streams to your dashboard in real time over WebSockets
      </p>
    </div>
  );
}

function DebateTerminal() {
  const { lines, typed } = useDebateLoop();
  const activeIdx = lines.length % DEBATE_SCRIPT.length;
  const who = DEBATE_SCRIPT[activeIdx].who;
  const color = (w: string) =>
    w === "bull" ? "text-gain" : w === "bear" ? "text-loss" : "text-warn";
  const prefix = (w: string) => (w === "bull" ? "BULL ▲" : w === "bear" ? "BEAR ▼" : "RISK ⚖");
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-border bg-bg-surface">
        <span className="w-2.5 h-2.5 rounded-full bg-loss/70" />
        <span className="w-2.5 h-2.5 rounded-full bg-warn/70" />
        <span className="w-2.5 h-2.5 rounded-full bg-gain/70" />
        <span className="ml-2 text-2xs text-text-muted font-mono">researcher_debate — NVDA · round 2</span>
      </div>
      <div className="p-4 md:p-5 font-mono text-xs md:text-sm space-y-2.5 min-h-[180px]">
        {lines.map((l, i) => (
          <p key={i} className="leading-relaxed">
            <span className={cn("font-bold mr-2", color(l.who))}>{prefix(l.who)}</span>
            <span className="text-text-secondary">{l.text}</span>
          </p>
        ))}
        <p className="leading-relaxed">
          <span className={cn("font-bold mr-2", color(who))}>{prefix(who)}</span>
          <span className="text-text-primary">{typed}</span>
          <span className="inline-block w-2 h-4 bg-accent-bright align-middle ml-0.5 animate-pulse" />
        </p>
      </div>
    </div>
  );
}

function LiveStats() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  const { data } = useQuery({
    queryKey: ["track-record"],
    queryFn: () => api.get("/track-record/").then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });

  const analyses = useCountUp(data?.total_analyses ?? 0, inView && !!data);
  const holds = data?.decisions?.HOLD ?? 0;
  const total = data ? Object.values(data.decisions as Record<string, number>).reduce((a, b) => a + b, 0) : 0;
  const discipline = useCountUp(total ? Math.round((holds / total) * 100) : 0, inView && !!data);
  const confidence = useCountUp(data?.avg_confidence ? Math.round(data.avg_confidence * 100) : 0, inView && !!data);

  // A fresh platform bragging about zeros undermines the pitch — show nothing
  // until there's a real number to stand behind.
  if (!data || data.total_analyses === 0) return <div ref={ref} />;

  return (
    <div ref={ref} className="grid grid-cols-1 gap-8 sm:grid-cols-3 sm:gap-6">
      {[
        { v: analyses.toLocaleString(), label: "Multi-agent analyses run", suffix: "" },
        { v: discipline, label: "of calls are HOLD — discipline, not gambling", suffix: "%" },
        { v: confidence, label: "avg. AI confidence (70%+ required to trade)", suffix: "%" },
      ].map((s, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 16 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ delay: i * 0.12, duration: 0.5 }}
          className="text-center"
        >
          <p className="font-mono text-3xl md:text-5xl font-bold text-text-primary">
            {s.v}
            <span className="text-accent-bright">{s.suffix}</span>
          </p>
          <p className="text-xs md:text-sm text-text-muted mt-2 max-w-[220px] mx-auto">{s.label}</p>
        </motion.div>
      ))}
    </div>
  );
}

const FEATURES = [
  {
    icon: BrainCircuit,
    title: "Seven agents, one decision",
    body: "Technical, sentiment, news and fundamental analysts feed a bull-vs-bear debate. A risk manager with veto power gets the last word before anything trades.",
  },
  {
    icon: ScrollText,
    title: "Every trade fully explained",
    body: "The complete reasoning chain — every analyst report, every debate round, every risk check — is stored with each trade. Click any position and read exactly why.",
  },
  {
    icon: Scale,
    title: "Institutional risk discipline",
    body: "Half-Kelly position sizing, 2×ATR stops, 3-of-4 analyst consensus, VIX gates, earnings blackouts, daily drawdown halts. Hardcoded. The AI can't override them.",
  },
  {
    icon: Radar,
    title: "Market regime awareness",
    body: "A live regime detector classifies the tape — bull trend, bear trend, high volatility, sideways — and resizes every position accordingly.",
  },
  {
    icon: Lock,
    title: "Your account, your keys",
    body: "Connect your own Alpaca paper account. Keys are encrypted at rest, trades stay 100% simulated — enforced server-side, not by a promise.",
  },
  {
    icon: TrendingUp,
    title: "A public track record",
    body: "Every call the AI makes is on the record — decision mix, win rate, confidence — on a page anyone can inspect. No cherry-picking possible.",
  },
];

function Features() {
  return (
    <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-5">
      {FEATURES.map((f, i) => (
        <motion.div
          key={f.title}
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ delay: (i % 3) * 0.1, duration: 0.5 }}
          className="card card-hover p-6"
        >
          <div className="w-9 h-9 rounded-lg bg-accent-muted/40 border border-accent/30 flex items-center justify-center mb-4">
            <f.icon size={16} className="text-accent-bright" />
          </div>
          <h3 className="text-sm font-semibold text-text-primary mb-2">{f.title}</h3>
          <p className="text-sm text-text-secondary leading-relaxed">{f.body}</p>
        </motion.div>
      ))}
    </div>
  );
}

const FRAMEWORKS = [
  "Wyckoff Method", "ICT Concepts", "CANSLIM", "Kelly Criterion", "Turtle Trader Rules",
  "Smart Money Concepts", "PEAD Strategy", "AQR Quality Factor", "ATR-based Stops",
  "Options Flow Analysis", "Portfolio VaR", "Position Pyramiding", "3-Target Exits",
];

function FrameworkMarquee() {
  const items = [...FRAMEWORKS, ...FRAMEWORKS];
  return (
    <div className="relative overflow-hidden py-2">
      <div className="pointer-events-none absolute inset-y-0 left-0 w-24 bg-gradient-to-r from-bg-base to-transparent z-10" />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-bg-base to-transparent z-10" />
      <div className="flex w-max animate-marquee-slow gap-3">
        {items.map((f, i) => (
          <span
            key={i}
            className="whitespace-nowrap text-xs font-medium text-text-secondary border border-border rounded-full px-4 py-1.5 bg-bg-surface"
          >
            {f}
          </span>
        ))}
      </div>
    </div>
  );
}

const STEPS = [
  { n: "01", title: "Create your account", body: "Sign up in 30 seconds. Connect your free Alpaca paper account — virtual money, real market data." },
  { n: "02", title: "Point the agents at a stock", body: "Run a full analysis on any ticker, or let the scanner pre-screen the market and pick candidates." },
  { n: "03", title: "Watch the debate, keep the receipts", body: "See the agents argue live. If the trade passes every risk gate, it executes — with the full reasoning stored forever." },
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Landing({ onGetStarted, onSignIn }: Props) {
  return (
    <div className="min-h-screen bg-bg-base text-text-primary overflow-x-hidden">
      {/* Nav */}
      <nav className="sticky top-0 z-50 border-b border-border-subtle bg-bg-base/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-5 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-accent rounded-lg flex items-center justify-center shadow-accent-glow">
              <TrendingUp size={16} className="text-white" />
            </div>
            <span className="font-semibold text-white">TradingAgents</span>
          </div>
          <div className="flex items-center gap-2 md:gap-4">
            <a href="/track-record" className="text-sm text-text-secondary hover:text-white transition-colors hidden sm:block">
              Track Record
            </a>
            <button onClick={onSignIn} className="text-sm text-text-secondary hover:text-white transition-colors px-2">
              Sign in
            </button>
            <button
              onClick={onGetStarted}
              className="px-4 py-2 bg-accent hover:bg-accent-bright text-white text-sm font-medium rounded-lg transition-colors"
            >
              Get started
            </button>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative">
        {/* Glow field */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-[900px] h-[500px] rounded-full bg-accent/20 blur-[140px]" />
          <div className="absolute top-40 -left-40 w-[400px] h-[400px] rounded-full bg-gain/10 blur-[120px]" />
          <div className="absolute top-64 -right-40 w-[400px] h-[400px] rounded-full bg-loss/10 blur-[120px]" />
          <div
            className="absolute inset-0 opacity-[0.35]"
            style={{
              backgroundImage:
                "linear-gradient(rgba(30,45,69,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(30,45,69,0.5) 1px, transparent 1px)",
              backgroundSize: "56px 56px",
              maskImage: "radial-gradient(ellipse 70% 60% at 50% 30%, black, transparent)",
            }}
          />
        </div>

        <div className="relative max-w-6xl mx-auto px-5 pt-20 md:pt-28 pb-14 text-center">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="inline-flex items-center gap-2 text-xs text-text-secondary border border-border rounded-full px-4 py-1.5 bg-bg-surface/80 mb-8"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-gain animate-pulse-slow" />
            Paper trading · zero real money at risk · full AI audit trail
          </motion.div>

          <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.05]">
            {["Seven AI agents.", "One disciplined trader."].map((line, li) => (
              <span key={li} className="block">
                {line.split(" ").map((w, wi) => (
                  <motion.span
                    key={wi}
                    className={cn(
                      "inline-block mr-[0.25em]",
                      li === 1 && "text-transparent bg-clip-text bg-gradient-to-r from-accent-bright via-accent to-gain"
                    )}
                    initial={{ opacity: 0, y: 24 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.15 + (li * 2 + wi) * 0.08, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                  >
                    {w}
                  </motion.span>
                ))}
              </span>
            ))}
          </h1>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.7, duration: 0.6 }}
            className="mt-6 text-base md:text-lg text-text-secondary max-w-2xl mx-auto leading-relaxed"
          >
            TradingAgents runs every stock through four specialist analysts, a bull-vs-bear
            debate, and a risk manager with veto power — then trades your own paper account
            and shows you exactly why.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.85, duration: 0.6 }}
            className="mt-8 flex items-center justify-center gap-3 flex-wrap"
          >
            <button
              onClick={onGetStarted}
              className="group px-6 py-3 bg-accent hover:bg-accent-bright text-white font-medium rounded-xl transition-all shadow-accent-glow flex items-center gap-2"
            >
              Start trading free
              <ArrowRight size={16} className="transition-transform group-hover:translate-x-0.5" />
            </button>
            <a
              href="/track-record"
              className="px-6 py-3 border border-border hover:border-border-bright text-text-primary font-medium rounded-xl transition-colors bg-bg-surface/60"
            >
              See the live track record
            </a>
          </motion.div>
        </div>

        <TickerTape />

        {/* Pipeline */}
        <div className="relative max-w-6xl mx-auto px-5 mt-12 md:mt-16">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 1.0, duration: 0.7 }}
          >
            <PipelineAnimation />
          </motion.div>
        </div>
      </section>

      {/* Debate + stats */}
      <section className="max-w-6xl mx-auto px-5 py-20 md:py-28 space-y-16">
        <div className="grid lg:grid-cols-2 gap-8 items-center">
          <motion.div
            initial={{ opacity: 0, x: -24 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.6 }}
          >
            <h2 className="text-2xl md:text-4xl font-bold tracking-tight">
              The AI argues with itself
              <span className="block text-text-secondary">so you don't trade on vibes.</span>
            </h2>
            <p className="mt-4 text-text-secondary leading-relaxed">
              A bull researcher and a bear researcher tear each other's thesis apart for
              multiple rounds. Only conviction that survives the fight reaches the risk
              manager — and the risk manager can still say no.
            </p>
            <ul className="mt-6 space-y-2.5">
              {["3-of-4 analyst consensus required for any trade", "70% minimum confidence, 2:1 minimum reward-to-risk", "Rejected trades tell you exactly why"].map((x) => (
                <li key={x} className="flex items-start gap-2.5 text-sm text-text-secondary">
                  <CheckCircle2 size={15} className="text-gain mt-0.5 shrink-0" />
                  {x}
                </li>
              ))}
            </ul>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, x: 24 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.6 }}
          >
            <DebateTerminal />
          </motion.div>
        </div>

        <LiveStats />
      </section>

      {/* Frameworks */}
      <section className="py-6 border-y border-border-subtle bg-bg-surface/40">
        <p className="text-center text-2xs uppercase tracking-widest text-text-muted mb-4">
          The playbooks baked into every prompt
        </p>
        <FrameworkMarquee />
      </section>

      {/* Features */}
      <section className="max-w-6xl mx-auto px-5 py-20 md:py-28">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-12"
        >
          <h2 className="text-2xl md:text-4xl font-bold tracking-tight">
            Built like a trading desk, not a chatbot
          </h2>
          <p className="mt-3 text-text-secondary max-w-xl mx-auto">
            Typed agent contracts, real-time WebSocket streaming, and risk rules the model
            itself cannot bypass.
          </p>
        </motion.div>
        <Features />
      </section>

      {/* How it works */}
      <section className="max-w-6xl mx-auto px-5 pb-20 md:pb-28">
        <div className="grid md:grid-cols-3 gap-5">
          {STEPS.map((s, i) => (
            <motion.div
              key={s.n}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: i * 0.12, duration: 0.5 }}
              className="card p-6"
            >
              <span className="block font-mono text-3xl font-bold text-accent/30 mb-3">{s.n}</span>
              <h3 className="text-sm font-semibold text-text-primary mb-2">{s.title}</h3>
              <p className="text-sm text-text-secondary leading-relaxed">{s.body}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Final CTA */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[700px] h-[300px] rounded-full bg-accent/15 blur-[120px]" />
        </div>
        <div className="relative max-w-3xl mx-auto px-5 py-20 md:py-28 text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
          >
            <ShieldCheck size={28} className="text-accent-bright mx-auto mb-5" />
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight">
              Learn to trade like an institution.
              <span className="block text-text-secondary mt-1">Risk absolutely nothing.</span>
            </h2>
            <p className="mt-5 text-text-secondary">
              Free forever on paper. Your own simulated account, the full agent pipeline,
              every guardrail on.
            </p>
            <button
              onClick={onGetStarted}
              className="group mt-8 px-8 py-3.5 bg-accent hover:bg-accent-bright text-white font-medium rounded-xl transition-all shadow-accent-glow inline-flex items-center gap-2"
            >
              Create your account
              <ArrowRight size={16} className="transition-transform group-hover:translate-x-0.5" />
            </button>
          </motion.div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border-subtle">
        <div className="max-w-6xl mx-auto px-5 py-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-sm text-text-muted">
              <div className="w-6 h-6 bg-accent/80 rounded-md flex items-center justify-center">
                <TrendingUp size={12} className="text-white" />
              </div>
              TradingAgents
            </div>
            <a href="/terms" className="text-2xs text-text-muted hover:text-text-secondary transition-colors">Terms</a>
            <a href="/privacy" className="text-2xs text-text-muted hover:text-text-secondary transition-colors">Privacy</a>
          </div>
          <p className="text-2xs text-text-muted max-w-lg text-center md:text-right leading-relaxed">
            TradingAgents is a paper-trading simulation platform for educational purposes.
            All trades use virtual money via Alpaca's paper API. AI analysis is not
            financial advice. Simulated performance does not represent real returns.
          </p>
        </div>
      </footer>
    </div>
  );
}
