import { useState } from "react";
import { motion } from "framer-motion";
import { Play, Loader2, AlertCircle } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import MetricCard from "../../components/data-display/MetricCard";
import { api } from "../../lib/api";
import { fmt } from "../../lib/formatters";
import { cn } from "../../lib/cn";

interface BacktestMetrics {
  total_return_pct: number;
  sharpe: number;
  max_drawdown_pct: number;
  win_rate: number;
  cagr_pct: number;
  profit_factor: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  final_equity: number;
  initial_capital: number;
  spy_return_pct: number;
}

interface EquityPoint {
  date: string;
  equity: number;
  benchmark: number | null;
}

interface TradeRecord {
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  qty: number;
  pnl: number;
  pnl_pct: number;
  exit_reason: string;
}

interface BacktestResult {
  job_id: string;
  ticker: string;
  metrics: BacktestMetrics;
  equity_curve: EquityPoint[];
  trades: TradeRecord[];
}

export default function Backtesting() {
  const [ticker, setTicker] = useState("AAPL");
  const [from, setFrom] = useState("2024-01-01");
  const [to, setTo] = useState("2025-01-01");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runBacktest = async () => {
    if (!ticker || !from || !to) return;
    setRunning(true);
    setError(null);
    setResult(null);

    try {
      const { data } = await api.post("/backtest/jobs", {
        ticker: ticker.toUpperCase(),
        from_date: from,
        to_date: to,
      });
      setResult(data);
    } catch (err: any) {
      const msg = err.response?.data?.detail ?? err.message ?? "Backtest failed";
      setError(msg);
    } finally {
      setRunning(false);
    }
  };

  const m = result?.metrics;

  // Format equity curve — pick every Nth point for chart performance
  const chartData = result?.equity_curve
    ? (() => {
        const curve = result.equity_curve;
        const step = Math.max(1, Math.floor(curve.length / 120));
        return curve.filter((_, i) => i % step === 0);
      })()
    : [];

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
        <p className="text-sm text-text-muted mt-0.5">
          Historical simulation using technical pre-screen signals (RSI, MACD, MA crossovers)
        </p>
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
                         ${mono ? "font-mono font-semibold uppercase" : ""}`}
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
          {running
            ? <><Loader2 size={16} className="animate-spin" /> Running...</>
            : <><Play size={16} /> Run Backtest</>}
        </button>
      </div>

      {/* Running state */}
      {running && (
        <div className="card p-8 flex items-center justify-center gap-3 text-text-secondary">
          <Loader2 size={20} className="animate-spin text-accent" />
          <span className="text-sm">Simulating technical signals over historical data...</span>
        </div>
      )}

      {/* Error state */}
      {error && !running && (
        <div className="card p-5 flex items-center gap-3 border-loss/30 bg-loss/5">
          <AlertCircle size={18} className="text-loss shrink-0" />
          <div>
            <p className="text-sm font-semibold text-text-primary">Backtest failed</p>
            <p className="text-xs text-text-muted mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Results */}
      {result && !running && m && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">

          {/* vs SPY callout */}
          <div className="flex items-center gap-3 px-5 py-3 rounded-xl bg-bg-elevated border border-border">
            <span className="text-sm text-text-secondary">Strategy vs SPY (same period):</span>
            <span className={cn(
              "font-mono font-semibold text-sm",
              m.total_return_pct >= m.spy_return_pct ? "text-gain" : "text-loss"
            )}>
              {m.total_return_pct >= 0 ? "+" : ""}{m.total_return_pct.toFixed(2)}%
            </span>
            <span className="text-text-muted text-sm">vs</span>
            <span className={cn(
              "font-mono font-semibold text-sm",
              m.spy_return_pct >= 0 ? "text-gain" : "text-loss"
            )}>
              {m.spy_return_pct >= 0 ? "+" : ""}{m.spy_return_pct.toFixed(2)}% SPY
            </span>
            <span className="text-text-muted text-xs ml-auto">
              {m.total_trades} trades · {m.winning_trades}W/{m.losing_trades}L
            </span>
          </div>

          {/* Metrics */}
          <div className="grid grid-cols-6 gap-3">
            <MetricCard
              label="Total Return"
              value={`${m.total_return_pct >= 0 ? "+" : ""}${m.total_return_pct.toFixed(2)}%`}
              accent={m.total_return_pct >= 0 ? "gain" : "loss"}
            />
            <MetricCard
              label="Sharpe Ratio"
              value={m.sharpe.toFixed(2)}
              accent="accent"
            />
            <MetricCard
              label="Max Drawdown"
              value={`${m.max_drawdown_pct.toFixed(2)}%`}
              accent="loss"
            />
            <MetricCard
              label="Win Rate"
              value={`${(m.win_rate * 100).toFixed(1)}%`}
              accent={m.win_rate >= 0.5 ? "gain" : "loss"}
            />
            <MetricCard
              label="CAGR"
              value={`${m.cagr_pct >= 0 ? "+" : ""}${m.cagr_pct.toFixed(2)}%`}
              accent="accent"
            />
            <MetricCard
              label="Profit Factor"
              value={m.profit_factor.toFixed(2)}
              accent={m.profit_factor >= 1 ? "gain" : "loss"}
            />
          </div>

          {/* Equity curve */}
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-text-primary">
                Equity Curve vs SPY — {result.ticker}
              </h2>
              <div className="flex items-center gap-4 text-2xs">
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-0.5 bg-accent rounded" />
                  <span className="text-text-secondary">Strategy</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-0.5 bg-border-bright rounded" />
                  <span className="text-text-secondary">Benchmark (SPY)</span>
                </div>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={chartData} margin={{ top: 5, right: 5, bottom: 0, left: 0 }}>
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
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10, fill: "#4D6080" }}
                  axisLine={false}
                  tickLine={false}
                  interval={Math.max(1, Math.floor(chartData.length / 8))}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: "#4D6080" }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  contentStyle={{ background: "#141D30", border: "1px solid #1E2D45", borderRadius: 8, fontSize: 11 }}
                  formatter={(v: number, name: string) => [
                    `$${v?.toLocaleString() ?? "—"}`,
                    name === "equity" ? "Strategy" : "SPY"
                  ]}
                />
                <Area type="monotone" dataKey="benchmark" stroke="#4D6080" strokeWidth={1.5}
                      fill="url(#bmGrad)" dot={false} connectNulls />
                <Area type="monotone" dataKey="equity" stroke="#2D7DD2" strokeWidth={2}
                      fill="url(#stratGrad)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Trade log */}
          {result.trades.length > 0 && (
            <div className="card p-5">
              <h2 className="text-sm font-semibold text-text-primary mb-4">
                Trade Log ({result.trades.length} trades)
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left border-b border-border">
                      {["Entry Date", "Exit Date", "Entry $", "Exit $", "Qty", "P&L", "P&L %", "Exit Reason"].map(h => (
                        <th key={h} className="metric-label pb-3 font-medium pr-4">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {result.trades.slice(0, 50).map((t, i) => (
                      <tr key={i} className="hover:bg-bg-elevated/50 transition-colors">
                        <td className="py-2 pr-4 font-mono text-text-secondary">{t.entry_date}</td>
                        <td className="py-2 pr-4 font-mono text-text-secondary">{t.exit_date}</td>
                        <td className="py-2 pr-4 font-mono text-text-primary">{fmt.price(t.entry_price)}</td>
                        <td className="py-2 pr-4 font-mono text-text-primary">{fmt.price(t.exit_price)}</td>
                        <td className="py-2 pr-4 font-mono text-text-muted">{t.qty.toFixed(4)}</td>
                        <td className={cn("py-2 pr-4 font-mono font-semibold", t.pnl >= 0 ? "text-gain" : "text-loss")}>
                          {t.pnl >= 0 ? "+" : ""}{fmt.usd(t.pnl)}
                        </td>
                        <td className={cn("py-2 pr-4 font-mono", t.pnl_pct >= 0 ? "text-gain" : "text-loss")}>
                          {t.pnl_pct >= 0 ? "+" : ""}{t.pnl_pct.toFixed(2)}%
                        </td>
                        <td className="py-2 pr-4">
                          <span className={cn(
                            "px-2 py-0.5 rounded text-2xs font-medium",
                            t.exit_reason === "stop_loss" ? "bg-loss/10 text-loss" :
                            t.exit_reason === "take_profit" ? "bg-gain/10 text-gain" :
                            "bg-bg-elevated text-text-muted"
                          )}>
                            {t.exit_reason.replace("_", " ")}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {result.trades.length > 50 && (
                  <p className="text-2xs text-text-muted mt-3 text-center">
                    Showing first 50 of {result.trades.length} trades
                  </p>
                )}
              </div>
            </div>
          )}
        </motion.div>
      )}
    </motion.div>
  );
}
