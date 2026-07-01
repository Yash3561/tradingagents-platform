import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  TrendingUp, TrendingDown, Minus, Activity, Shield,
  Target, Brain, Zap, RefreshCw, AlertTriangle, CheckCircle2
} from "lucide-react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { TermTooltip } from "../../components/ui/Tooltip";

interface RegimeData {
  regime: "BULL_TRENDING" | "BEAR_TRENDING" | "HIGH_VOLATILITY" | "SIDEWAYS" | "UNKNOWN";
  confidence: number;
  spy_price: number;
  spy_ma50: number;
  spy_ma200: number;
  spy_rsi: number;
  vix: number;
  breadth_score: number;
  mom_1m_pct: number;
  mom_3m_pct: number;
  atr_pct: number;
  strategy: {
    primary: string;
    description: string;
    bias: string;
    max_position_pct: number;
    stop_multiplier: number;
    min_confidence: number;
  };
  computed_at: string;
}

const REGIME_CONFIG = {
  BULL_TRENDING: {
    color: "text-gain", bg: "bg-gain/10", border: "border-gain/30",
    icon: TrendingUp, label: "Bull Trending",
    desc: "Markets in uptrend — momentum strategies, buy breakouts, ride sector leaders",
  },
  BEAR_TRENDING: {
    color: "text-loss", bg: "bg-loss/10", border: "border-loss/30",
    icon: TrendingDown, label: "Bear Trending",
    desc: "Markets in downtrend — reduce exposure, tight stops, defensive positioning",
  },
  HIGH_VOLATILITY: {
    color: "text-warn", bg: "bg-warn/10", border: "border-warn/30",
    icon: AlertTriangle, label: "High Volatility",
    desc: "VIX elevated — stay in cash, only highest-conviction trades, smaller sizes",
  },
  SIDEWAYS: {
    color: "text-accent", bg: "bg-accent/10", border: "border-accent/30",
    icon: Minus, label: "Sideways / Range",
    desc: "Range-bound market — buy oversold, sell overbought, mean reversion setups",
  },
  UNKNOWN: {
    color: "text-slate-400", bg: "bg-slate-400/10", border: "border-slate-400/30",
    icon: Activity, label: "Unknown",
    desc: "Could not determine regime — proceeding with default settings",
  },
};

const FRAMEWORKS = [
  {
    name: "Wyckoff Method",
    source: "Richard Wyckoff, 1930s",
    active: true,
    description: "Tracks accumulation and distribution phases of institutional 'smart money'. Identifies springs (false breakdowns) and upthrusts before the real move begins.",
    signals: ["Accumulation phase detection", "Volume confirms price", "Spring/Upthrust identification"],
  },
  {
    name: "ICT Concepts",
    source: "Inner Circle Trader",
    active: true,
    description: "Fair Value Gaps, Order Blocks, and Liquidity Sweeps — maps where institutional orders are hidden and where price is likely to be drawn.",
    signals: ["Fair Value Gap fill targets", "Order block entry zones", "Liquidity sweep reversals"],
  },
  {
    name: "Turtle Trader Rules",
    source: "Richard Dennis, 1983",
    active: true,
    description: "Systematic trend-following with ATR-based position sizing. Buy 20-day breakouts, pyramid into winners, cut losers immediately at 2×ATR stops.",
    signals: ["ATR-based stop placement", "Breakout entry signals", "Position pyramid rules"],
  },
  {
    name: "CANSLIM",
    source: "William O'Neil / IBD",
    active: true,
    description: "Current earnings, Annual growth, New products, Supply/demand, Leader in sector, Institutional support, Market direction. The framework behind the biggest stock winners.",
    signals: ["Earnings acceleration", "Sector leadership", "Institutional ownership"],
  },
  {
    name: "Kelly Criterion",
    source: "John Kelly, Bell Labs 1956",
    active: true,
    description: "Mathematically optimal position sizing based on win rate and reward/risk ratio. Platform uses Half-Kelly to reduce volatility while preserving most of the edge.",
    signals: ["Optimal bet sizing", "Risk/reward calculation", "Portfolio-level risk control"],
  },
  {
    name: "AQR Factor Model",
    source: "AQR Capital Management",
    active: true,
    description: "Combines Momentum (12-1 month), Value (P/E vs sector), Quality (margins, stability), and Low-Volatility factors — all academically proven to generate alpha.",
    signals: ["Momentum factor", "Value factor", "Quality factor", "Low-vol factor"],
  },
  {
    name: "PEAD Strategy",
    source: "Academic research (Ball & Brown, 1968)",
    active: true,
    description: "Post-Earnings Announcement Drift — stocks that beat earnings estimates continue to drift upward for 60+ days. One of the most persistent market anomalies.",
    signals: ["Earnings beat detection", "Drift continuation", "Analyst revision tracking"],
  },
  {
    name: "Smart Money Concepts",
    source: "Institutional trading research",
    active: true,
    description: "Tracks where large institutions must hide orders — at round numbers, prior swing highs/lows, and areas with stop-loss clusters. Trades WITH the institutions.",
    signals: ["Liquidity pool mapping", "Stop hunt identification", "Premium/discount zones"],
  },
];

const RISK_RULES = [
  { rule: "Maximum position size", value: "5% of portfolio", applies: "All regimes" },
  { rule: "ATR-based stop (2×ATR14)", value: "Dynamic per volatility", applies: "All trades" },
  { rule: "Minimum Risk/Reward", value: "2:1 (never below)", applies: "All trades" },
  { rule: "Minimum AI confidence (BULL)", value: "65%", applies: "Bull trending" },
  { rule: "Minimum AI confidence (BEAR)", value: "80%", applies: "Bear/Sideways" },
  { rule: "Minimum AI confidence (HIGH VOL)", value: "85%", applies: "High volatility" },
  { rule: "Max sector concentration", value: "25% of portfolio", applies: "Portfolio level" },
  { rule: "Cash reserve minimum", value: "20% always", applies: "Portfolio level" },
  { rule: "Daily portfolio drawdown halt", value: "-5% → pause all scans", applies: "Circuit breaker" },
  { rule: "VIX gate", value: ">30 → suppress BUY signals", applies: "Circuit breaker" },
  { rule: "Consensus requirement", value: "3 of 4 analysts agree", applies: "AI pipeline" },
  { rule: "High risk auto-reject", value: "Risk=HIGH → always rejected", applies: "Risk manager" },
];

function RegimeCard({ regime }: { regime: RegimeData }) {
  const cfg = REGIME_CONFIG[regime.regime];
  const Icon = cfg.icon;
  const spy_vs_ma200 = ((regime.spy_price - regime.spy_ma200) / regime.spy_ma200 * 100).toFixed(1);
  const spy_vs_ma50 = ((regime.spy_price - regime.spy_ma50) / regime.spy_ma50 * 100).toFixed(1);

  return (
    <div className={cn("card p-6 border-2", cfg.border)}>
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className={cn("p-2 rounded-lg", cfg.bg)}>
              <Icon size={20} className={cfg.color} />
            </div>
            <div>
              <p className="metric-label">Current Market Regime</p>
              <h2 className={cn("text-2xl font-bold", cfg.color)}>{cfg.label}</h2>
            </div>
          </div>
          <p className="text-sm text-slate-400 mt-2 max-w-lg">{cfg.desc}</p>
        </div>
        <div className="text-right">
          <p className="metric-label">Regime Confidence</p>
          <p className={cn("text-3xl font-bold font-mono", cfg.color)}>{regime.confidence}%</p>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-4">
        {[
          { label: "SPY Price", value: `$${regime.spy_price}`, mono: true },
          { label: "vs MA50", value: `${+spy_vs_ma50 >= 0 ? "+" : ""}${spy_vs_ma50}%`, color: +spy_vs_ma50 >= 0 ? "text-gain" : "text-loss" },
          { label: "vs MA200", value: `${+spy_vs_ma200 >= 0 ? "+" : ""}${spy_vs_ma200}%`, color: +spy_vs_ma200 >= 0 ? "text-gain" : "text-loss" },
          { label: "VIX", value: regime.vix?.toFixed(2) ?? "—", color: regime.vix > 30 ? "text-loss" : regime.vix > 20 ? "text-warn" : "text-gain" },
          { label: "SPY RSI", value: regime.spy_rsi?.toFixed(1) ?? "—", color: regime.spy_rsi > 70 ? "text-loss" : regime.spy_rsi < 35 ? "text-gain" : "text-slate-300" },
        ].map(({ label, value, mono, color }) => (
          <div key={label} className="bg-bg-elevated rounded-lg p-3 text-center">
            <p className="metric-label mb-1">{label}</p>
            <p className={cn("text-lg font-bold", mono && "font-mono", color ?? "text-slate-200")}>{value}</p>
          </div>
        ))}
      </div>

      <div className={cn("mt-4 p-3 rounded-lg border", cfg.bg, cfg.border)}>
        <p className="text-xs font-semibold text-slate-300 mb-1">Active Strategy → <span className={cfg.color}>{regime.strategy?.primary?.toUpperCase().replace("_", " ")}</span></p>
        <div className="flex flex-wrap gap-4 text-xs text-slate-400">
          <span>Bias: <strong className={cfg.color}>{regime.strategy?.bias}</strong></span>
          <span>Max Position: <strong className="text-slate-200">{regime.strategy?.max_position_pct}%</strong></span>
          <span>Min AI Confidence: <strong className="text-slate-200">{((regime.strategy?.min_confidence ?? 0.7) * 100).toFixed(0)}%</strong></span>
          <span>Stop Multiplier: <strong className="text-slate-200">{regime.strategy?.stop_multiplier}×ATR</strong></span>
        </div>
      </div>
    </div>
  );
}

export default function Strategy() {
  const [regime, setRegime] = useState<RegimeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchRegime = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const { data } = await api.get("/market/regime");
      setRegime(data);
    } catch {}
    setLoading(false);
    setRefreshing(false);
  };

  useEffect(() => { fetchRegime(); }, []);

  return (
    <motion.div key="strategy" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      exit={{ opacity: 0 }} transition={{ duration: 0.25 }} className="space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-100 flex items-center gap-2">
            <Target size={20} className="text-accent" />
            Strategy Intelligence
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">
            World-class frameworks powering every agent decision
          </p>
        </div>
        <button onClick={() => fetchRegime(true)} disabled={refreshing}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-700 hover:border-accent/50 text-slate-400 hover:text-slate-200 transition-all text-sm">
          <RefreshCw size={14} className={cn(refreshing && "animate-spin")} />
          Refresh Regime
        </button>
      </div>

      {/* Market Regime */}
      {loading ? (
        <div className="card p-6 animate-pulse h-48" />
      ) : regime ? (
        <RegimeCard regime={regime} />
      ) : (
        <div className="card p-6 text-center text-slate-500">Could not load regime data</div>
      )}

      {/* Active Frameworks */}
      <div>
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Brain size={14} className="text-accent" />
          Active Trading Frameworks ({FRAMEWORKS.length})
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {FRAMEWORKS.map((f, i) => (
            <motion.div key={f.name} initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
              className="card p-4">
              <div className="flex items-start justify-between mb-2">
                <div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 size={12} className="text-gain shrink-0" />
                    <h3 className="text-sm font-semibold text-slate-100">{f.name}</h3>
                  </div>
                  <p className="text-2xs text-slate-500 mt-0.5 ml-5">{f.source}</p>
                </div>
                <span className="text-2xs px-1.5 py-0.5 rounded bg-gain/10 text-gain border border-gain/20 font-medium shrink-0">
                  ACTIVE
                </span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed mb-2">{f.description}</p>
              <div className="flex flex-wrap gap-1">
                {f.signals.map(s => (
                  <span key={s} className="text-2xs px-1.5 py-0.5 rounded bg-accent/10 text-accent border border-accent/20">
                    {s}
                  </span>
                ))}
              </div>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Risk Management Rules */}
      <div>
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Shield size={14} className="text-warn" />
          Hardcoded Risk Rules — Cannot Be Overridden
        </h2>
        <div className="card overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-800">
                <th className="text-left px-4 py-2.5 text-slate-400 font-medium">Rule</th>
                <th className="text-left px-4 py-2.5 text-slate-400 font-medium">Value</th>
                <th className="text-left px-4 py-2.5 text-slate-400 font-medium">Applies When</th>
              </tr>
            </thead>
            <tbody>
              {RISK_RULES.map((r, i) => (
                <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors">
                  <td className="px-4 py-2.5 text-slate-300 font-medium">{r.rule}</td>
                  <td className="px-4 py-2.5 font-mono text-accent">{r.value}</td>
                  <td className="px-4 py-2.5 text-slate-500">{r.applies}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Philosophy */}
      <div className="card p-5 border border-accent/20 bg-accent/5">
        <div className="flex items-center gap-2 mb-3">
          <Zap size={14} className="text-accent" />
          <h3 className="text-sm font-semibold text-slate-100">Platform Philosophy</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs text-slate-400">
          <div>
            <p className="text-accent font-semibold mb-1">Consistency over home runs</p>
            <p>Small consistent gains compound into extraordinary returns. 1% per day = 1,000% per year. Preserve capital first, profits second.</p>
          </div>
          <div>
            <p className="text-warn font-semibold mb-1">Asymmetric risk/reward only</p>
            <p>Every trade must offer 2:1+ reward vs risk. We only take trades where being right pays more than being wrong costs. Never the opposite.</p>
          </div>
          <div>
            <p className="text-gain font-semibold mb-1">Process over outcomes</p>
            <p>A good decision can still lose money. A bad decision can still win. Judge the process, not individual outcomes. Follow the rules every time.</p>
          </div>
        </div>
        <p className="text-xs text-slate-500 mt-4 border-t border-slate-700 pt-3">
          <strong className="text-slate-400">Important:</strong> No system guarantees daily profits. Markets have randomness. The edge comes from consistently applying proven frameworks over hundreds of trades — not any single trade. This platform targets strong risk-adjusted returns, not guaranteed outcomes.
        </p>
      </div>
    </motion.div>
  );
}
