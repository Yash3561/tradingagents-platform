import { useState } from "react";
import { motion } from "framer-motion";
import { Play, Loader2 } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import MetricCard from "../../components/data-display/MetricCard";

const MOCK_EQUITY = Array.from({ length: 60 }, (_, i) => {
  const base = 100000;
  const trend = i * 180;
  const noise = Math.sin(i * 0.4) * 2200 + Math.cos(i * 0.7) * 1100;
  return {
    date: new Date(2025, 0, i + 2).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    equity: Math.round(base + trend + noise),
    benchmark: Math.round(base + i * 95 + Math.sin(i * 0.3) * 1500),
  };
});

export default function Backtesting() {
  const [ticker, setTicker] = useState("AAPL");
  const [from, setFrom] = useState("2025-01-01");
  const [to, setTo] = useState("2025-06-01");
  const [running, setRunning] = useState(false);
  const [hasResult, setHasResult] = useState(false);

  const runBacktest = async () => {
    setRunning(true);
    await new Promise(r => setTimeout(r, 2500));
    setRunning(false);
    setHasResult(true);
  };

  return (
    <motion.div
      key="backtest"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-6"
    >
      <div>
        <h1 className="text-xl font-semibold text-text-primary">Backtesting</h1>
        <p className="text-sm text-text-muted mt-0.5">Historical simulation with agent signals</p>
      </div>

      {/* Config */}
      <div className="card p-5 flex items-end gap-4 flex-wrap">
        {[
          { label: "Ticker", value: ticker, setter: setTicker, type: "text", placeholder: "AAPL", mono: true },
          { label: "From", value: from, setter: setFrom, type: "date" },
          { label: "To", value: to, setter: setTo, type: "date" },
        ].map(({ label, value, setter, type, placeholder, mono }) => (
          <div key={label}>
            <label className="metric-label block mb-2">{label}</label>
            <input
              type={type}
              value={value}
              placeholder={placeholder}
              onChange={e => setter(e.target.value)}
              className={`px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary
                         placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors
                         ${mono ? "font-mono font-semibold" : ""}`}
            />
          </div>
        ))}

        <button
          onClick={runBacktest}
          disabled={running}
          className="flex items-center gap-2 px-5 py-2 rounded-lg font-semibold text-sm
                     bg-accent hover:bg-accent-bright text-white shadow-accent-glow
                     disabled:opacity-60 disabled:cursor-not-allowed transition-all"
        >
          {running ? <><Loader2 size={16} className="animate-spin" /> Running...</> : <><Play size={16} /> Run Backtest</>}
        </button>
      </div>

      {running && (
        <div className="card p-8 flex items-center justify-center gap-3 text-text-secondary">
          <Loader2 size={20} className="animate-spin text-accent" />
          <span className="text-sm">Simulating agent decisions over historical data...</span>
        </div>
      )}

      {hasResult && !running && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          {/* Metrics */}
          <div className="grid grid-cols-6 gap-3">
            {[
              { label: "Total Return", value: "+12.4%", accent: "gain" as const },
              { label: "Sharpe Ratio", value: "1.38", accent: "accent" as const },
              { label: "Max Drawdown", value: "-6.2%", accent: "loss" as const },
              { label: "Win Rate", value: "58.3%", accent: "gain" as const },
              { label: "CAGR", value: "+24.8%", accent: "accent" as const },
              { label: "Profit Factor", value: "1.72", accent: "gain" as const },
            ].map(m => (
              <MetricCard key={m.label} {...m} />
            ))}
          </div>

          {/* Equity curve */}
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-text-primary">Equity Curve vs Benchmark</h2>
              <div className="flex items-center gap-4 text-2xs">
                <div className="flex items-center gap-1.5"><div className="w-3 h-0.5 bg-accent rounded" /><span className="text-text-secondary">Strategy</span></div>
                <div className="flex items-center gap-1.5"><div className="w-3 h-0.5 bg-border-bright rounded" /><span className="text-text-secondary">Benchmark (SPY)</span></div>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={MOCK_EQUITY} margin={{ top: 5, right: 5, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="stratGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#2D7DD2" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#2D7DD2" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="bmGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#4D6080" stopOpacity={0.1} />
                    <stop offset="95%" stopColor="#4D6080" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#4D6080" }} axisLine={false} tickLine={false} interval={9} />
                <YAxis tick={{ fontSize: 10, fill: "#4D6080" }} axisLine={false} tickLine={false} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ background: "#141D30", border: "1px solid #1E2D45", borderRadius: 8, fontSize: 11 }}
                  formatter={(v: number) => [`$${v.toLocaleString()}`, ""]}
                />
                <Area type="monotone" dataKey="benchmark" stroke="#4D6080" strokeWidth={1.5} fill="url(#bmGrad)" dot={false} />
                <Area type="monotone" dataKey="equity" stroke="#2D7DD2" strokeWidth={2} fill="url(#stratGrad)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </motion.div>
      )}
    </motion.div>
  );
}
