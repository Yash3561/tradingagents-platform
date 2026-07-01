import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Play, Loader2, AlertTriangle, TrendingUp, TrendingDown, Minus, ChevronDown } from "lucide-react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

// ── Types ─────────────────────────────────────────────────────────────────────

interface OptionsResult {
  recommendation: "CALL" | "PUT" | "NO_PLAY";
  strike_price: number;
  expiry_date: string;
  max_risk_pct: number;
  target_return_pct: number;
  reasoning: string;
  delta_estimate: number;
  gamma_estimate?: number;
  theta_estimate?: number;
  iv_estimate: number;
  risk_warnings: string[];
}

// ── Sub-components ────────────────────────────────────────────────────────────

function RecommendationBadge({ rec }: { rec: "CALL" | "PUT" | "NO_PLAY" }) {
  if (rec === "CALL") {
    return (
      <div className="flex items-center gap-2 px-4 py-2 bg-gain/10 border border-gain/40 rounded-xl">
        <TrendingUp size={20} className="text-gain" />
        <span className="text-xl font-bold font-mono text-gain">CALL</span>
      </div>
    );
  }
  if (rec === "PUT") {
    return (
      <div className="flex items-center gap-2 px-4 py-2 bg-loss/10 border border-loss/40 rounded-xl">
        <TrendingDown size={20} className="text-loss" />
        <span className="text-xl font-bold font-mono text-loss">PUT</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-bg-elevated border border-border rounded-xl">
      <Minus size={20} className="text-text-muted" />
      <span className="text-xl font-bold font-mono text-text-muted">NO PLAY</span>
    </div>
  );
}

function GreekCard({ label, value, format = "dec2" }: { label: string; value: number | undefined; format?: "dec2" | "pct" | "neg" }) {
  if (value === undefined || value === null) return null;

  let display: string;
  if (format === "pct") display = `${(value * 100).toFixed(1)}%`;
  else if (format === "neg") display = value.toFixed(4);
  else display = value.toFixed(3);

  return (
    <div className="flex flex-col items-center p-3 bg-bg-elevated rounded-lg border border-border min-w-[80px]">
      <span className="text-xs text-text-muted uppercase tracking-wider mb-1">{label}</span>
      <span className="text-base font-mono font-semibold text-text-primary">{display}</span>
    </div>
  );
}

// ── Options Chain Table ────────────────────────────────────────────────────────

interface ChainRow {
  strike: number; lastPrice: number; bid: number; ask: number;
  volume: number; openInterest: number; impliedVolatility: number;
  inTheMoney: boolean; kind: string;
}
interface ChainData {
  expiries: string[]; selected_expiry: string | null;
  current_price: number | null; calls: ChainRow[]; puts: ChainRow[];
}

function OptionsChain({ ticker }: { ticker: string }) {
  const [chain, setChain] = useState<ChainData | null>(null);
  const [loading, setLoading] = useState(false);
  const [expiryIdx, setExpiryIdx] = useState(0);
  const [tab, setTab] = useState<"calls" | "puts">("calls");

  const load = (idx: number) => {
    setLoading(true);
    api.get(`/agents/options/chain/${ticker}?expiry_index=${idx}`)
      .then(r => setChain(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { if (ticker) { setExpiryIdx(0); load(0); } }, [ticker]);

  if (!chain && !loading) return null;

  const rows = tab === "calls" ? chain?.calls ?? [] : chain?.puts ?? [];

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-semibold text-white">Live Options Chain</h3>
          {chain?.current_price && (
            <span className="text-xs font-mono text-slate-400">
              {ticker} @ <span className="text-white font-bold">${chain.current_price.toFixed(2)}</span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {/* Expiry selector */}
          {chain && chain.expiries.length > 0 && (
            <div className="relative">
              <select
                value={expiryIdx}
                onChange={e => { const idx = Number(e.target.value); setExpiryIdx(idx); load(idx); }}
                className="appearance-none pl-3 pr-7 py-1.5 bg-bg-elevated border border-border rounded-lg text-xs text-white font-mono focus:outline-none focus:border-accent"
              >
                {chain.expiries.map((exp, i) => (
                  <option key={exp} value={i}>{exp}</option>
                ))}
              </select>
              <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
            </div>
          )}
          {/* Calls / Puts tab */}
          <div className="flex bg-bg-elevated rounded-lg border border-border p-0.5">
            {(["calls", "puts"] as const).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  "px-3 py-1 rounded-md text-xs font-semibold transition-colors capitalize",
                  tab === t ? (t === "calls" ? "bg-gain/20 text-gain" : "bg-loss/20 text-loss") : "text-slate-400 hover:text-white"
                )}
              >{t}</button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-24"><Loader2 size={18} className="animate-spin text-accent" /></div>
      ) : rows.length === 0 ? (
        <p className="text-xs text-slate-500 text-center py-6">No chain data available for this expiry</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left border-b border-border">
                {["Strike", "Last", "Bid", "Ask", "Volume", "OI", "IV"].map(h => (
                  <th key={h} className="pb-2 pr-4 text-slate-500 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/30">
              {rows.map((row, i) => (
                <tr key={i} className={cn(
                  "hover:bg-bg-elevated transition-colors",
                  row.inTheMoney ? (tab === "calls" ? "text-gain" : "text-loss") : "text-slate-300"
                )}>
                  <td className="py-1.5 pr-4 font-mono font-bold">
                    ${row.strike.toFixed(2)}
                    {row.inTheMoney && <span className="ml-1 text-2xs opacity-60">ITM</span>}
                  </td>
                  <td className="py-1.5 pr-4 font-mono">${row.lastPrice.toFixed(2)}</td>
                  <td className="py-1.5 pr-4 font-mono text-slate-400">${row.bid.toFixed(2)}</td>
                  <td className="py-1.5 pr-4 font-mono text-slate-400">${row.ask.toFixed(2)}</td>
                  <td className="py-1.5 pr-4 font-mono">{row.volume.toLocaleString()}</td>
                  <td className="py-1.5 pr-4 font-mono">{row.openInterest.toLocaleString()}</td>
                  <td className="py-1.5 font-mono">{row.impliedVolatility.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-2xs text-slate-600 mt-3">Showing ~10 strikes nearest ATM. ITM = in the money.</p>
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

type Strategy = "directional" | "earnings" | "hedge";
type Expiry = "1week" | "2weeks" | "1month" | "3months";

const STRATEGY_LABELS: Record<Strategy, string> = {
  directional: "Directional Momentum",
  earnings: "Earnings Play",
  hedge: "Hedge Existing Position",
};

const EXPIRY_LABELS: Record<Expiry, string> = {
  "1week": "1 week",
  "2weeks": "2 weeks",
  "1month": "1 month",
  "3months": "3 months",
};

export default function OptionsDesk() {
  const [ticker, setTicker] = useState("AAPL");
  const [activeTicker, setActiveTicker] = useState("AAPL");
  const [strategy, setStrategy] = useState<Strategy>("directional");
  const [expiry, setExpiry] = useState<Expiry>("2weeks");
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [result, setResult] = useState<OptionsResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");

  const handleRun = async () => {
    if (status === "loading") return;
    const t = ticker.trim().toUpperCase();
    if (!t) return;

    setStatus("loading");
    setResult(null);
    setErrorMsg("");

    try {
      const { data } = await api.post("/agents/options/analyze", {
        ticker: t,
        strategy,
        expiry_preference: expiry,
      }, { timeout: 90000 });
      setResult(data);
      setActiveTicker(t);
      setStatus("done");
    } catch (err: any) {
      const isTimeout = err?.code === "ECONNABORTED" || err?.message?.includes("timeout");
      setErrorMsg(
        isTimeout
          ? "Request timed out — the AI model is busy. Try again in a moment."
          : (err?.response?.data?.detail ?? "Analysis failed. Check that the backend is running.")
      );
      setStatus("error");
    }
  };

  return (
    <motion.div
      key="options-desk"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-6 max-w-5xl"
    >
      {/* Page header */}
      <div>
        <h1 className="text-xl font-semibold text-text-primary">Options Desk</h1>
        <p className="text-sm text-text-muted mt-0.5">AI-driven options analysis — CALL, PUT, or no play</p>
      </div>

      {/* Controls card */}
      <div className="card p-5 flex flex-wrap items-end gap-4">
        {/* Ticker */}
        <div className="flex-1 min-w-[120px] max-w-[160px]">
          <label className="metric-label block mb-2">Ticker</label>
          <input
            value={ticker}
            onChange={e => setTicker(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === "Enter" && handleRun()}
            placeholder="AAPL"
            maxLength={6}
            className="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg
                       text-text-primary font-mono font-semibold text-sm placeholder:text-text-muted
                       focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 transition-colors"
          />
        </div>

        {/* Strategy */}
        <div>
          <label className="metric-label block mb-2">Strategy</label>
          <select
            value={strategy}
            onChange={e => setStrategy(e.target.value as Strategy)}
            className="px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary
                       focus:outline-none focus:border-accent transition-colors"
          >
            {Object.entries(STRATEGY_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>

        {/* Expiry */}
        <div>
          <label className="metric-label block mb-2">Expiry Preference</label>
          <select
            value={expiry}
            onChange={e => setExpiry(e.target.value as Expiry)}
            className="px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary
                       focus:outline-none focus:border-accent transition-colors"
          >
            {Object.entries(EXPIRY_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>

        {/* Run button */}
        <button
          onClick={handleRun}
          disabled={status === "loading"}
          className={cn(
            "flex items-center gap-2 px-5 py-2 rounded-lg font-semibold text-sm transition-all duration-200",
            status === "loading"
              ? "bg-accent/20 text-accent cursor-not-allowed"
              : "bg-accent hover:bg-accent/80 text-white shadow-[0_0_20px_rgba(45,125,210,0.35)]"
          )}
        >
          {status === "loading" ? (
            <><Loader2 size={16} className="animate-spin" /> Analyzing...</>
          ) : (
            <><Play size={16} /> Run Analysis</>
          )}
        </button>
      </div>

      {/* Error state */}
      <AnimatePresence>
        {status === "error" && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="card p-4 border-loss/30 bg-loss/5 flex items-start gap-3"
          >
            <AlertTriangle size={16} className="text-loss shrink-0 mt-0.5" />
            <p className="text-sm text-loss">{errorMsg}</p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Results */}
      <AnimatePresence>
        {status === "done" && result && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="space-y-4"
          >
            {/* Recommendation card */}
            <div className="card p-6 space-y-5">
              <h2 className="text-sm font-semibold text-text-primary border-b border-border pb-3">
                Recommendation — {ticker.toUpperCase()}
              </h2>

              <div className="flex flex-wrap items-center gap-4">
                <RecommendationBadge rec={result.recommendation} />

                {result.recommendation !== "NO_PLAY" && (
                  <div className="flex flex-wrap gap-4 text-sm">
                    <div>
                      <p className="text-xs text-text-muted mb-0.5">Strike Price</p>
                      <p className="font-mono font-semibold text-text-primary">
                        ${result.strike_price.toFixed(2)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-text-muted mb-0.5">Expiry</p>
                      <p className="font-mono font-semibold text-text-primary">{result.expiry_date}</p>
                    </div>
                    <div>
                      <p className="text-xs text-text-muted mb-0.5">Max Risk (premium)</p>
                      <p className="font-mono font-semibold text-loss">
                        {result.max_risk_pct.toFixed(1)}% of stock price
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-text-muted mb-0.5">Target Return</p>
                      <p className="font-mono font-semibold text-gain">
                        +{result.target_return_pct.toFixed(0)}%
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* Greeks */}
              {result.recommendation !== "NO_PLAY" && (
                <div>
                  <p className="text-xs text-text-muted uppercase tracking-wider mb-2">Greeks & IV</p>
                  <div className="flex flex-wrap gap-2">
                    <GreekCard label="Delta" value={result.delta_estimate} format="dec2" />
                    {result.gamma_estimate !== undefined && (
                      <GreekCard label="Gamma" value={result.gamma_estimate} format="neg" />
                    )}
                    {result.theta_estimate !== undefined && (
                      <GreekCard label="Theta" value={result.theta_estimate} format="neg" />
                    )}
                    <GreekCard label="IV" value={result.iv_estimate} format="pct" />
                  </div>
                </div>
              )}
            </div>

            {/* Thesis card */}
            <div className="card p-6">
              <h2 className="text-sm font-semibold text-text-primary border-b border-border pb-3 mb-4">
                AI Reasoning
              </h2>
              <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">
                {result.reasoning}
              </p>
            </div>

            {/* Risk warnings */}
            {result.risk_warnings.length > 0 && (
              <div className="card p-6 border-warn/20 bg-warn/5">
                <h2 className="text-sm font-semibold text-warn border-b border-warn/20 pb-3 mb-4 flex items-center gap-2">
                  <AlertTriangle size={14} />
                  Risk Warnings
                </h2>
                <ul className="space-y-2">
                  {result.risk_warnings.map((w, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                      <span className="text-warn mt-0.5 shrink-0">•</span>
                      {w}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Live options chain — always visible once a ticker is set */}
      <OptionsChain ticker={activeTicker} />

      {/* Idle state hint */}
      {status === "idle" && (
        <div className="card p-10 flex flex-col items-center justify-center text-center gap-3">
          <TrendingUp size={32} className="text-text-muted opacity-40" />
          <p className="text-sm text-text-muted">
            Enter a ticker and click <span className="text-text-secondary font-medium">Run Analysis</span> to get an options recommendation.
          </p>
          <p className="text-xs text-text-muted opacity-60">
            The AI analyzes momentum, IV, and strategy type to recommend CALL, PUT, or no play.
          </p>
        </div>
      )}
    </motion.div>
  );
}
