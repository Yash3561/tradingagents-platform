import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
} from "recharts";
import PnLBadge from "../../components/data-display/PnLBadge";
import { fmt } from "../../lib/formatters";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { RefreshCw, Loader2, ChevronDown, ChevronRight } from "lucide-react";
import CandlestickChart from "../../components/charts/CandlestickChart";
import PnLCalendar from "../../components/data-display/PnLCalendar";

const PIE_COLORS = ["#2D7DD2", "#4A9AEF", "#00E676", "#FFB740", "#FF3D57", "#7C5CBF", "#4D6080"];

interface Position {
  ticker: string;
  qty: number;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  current_price: number;
  avg_entry_price: number;
  side: string;
}

interface RiskMetrics {
  equity: number;
  cash: number;
  long_market_value: number;
  day_pnl: number;
  day_pnl_pct: number;
  buying_power: number;
  cash_pct: number;
  invested_pct: number;
  sharpe: number | null;
  max_drawdown: number | null;
  total_return: number | null;
  snapshot_count: number;
}

interface EquityPoint {
  timestamp: string;
  equity: number;
  cash: number;
  day_pnl: number;
}

function StatCard({ label, value, sub, color }: {
  label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div className="card p-4">
      <p className="metric-label">{label}</p>
      <p className={cn("metric-value mt-1", color ?? "text-text-primary")}>{value}</p>
      {sub && <p className="text-xs text-text-muted mt-0.5">{sub}</p>}
    </div>
  );
}

export default function Portfolio() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [allocation, setAllocation] = useState<{ ticker: string; market_value: number; pct: number }[]>([]);
  const [metrics, setMetrics] = useState<RiskMetrics | null>(null);
  const [curve, setCurve] = useState<EquityPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
  const [chartTicker, setChartTicker] = useState<string>("SPY");

  const load = async () => {
    setRefreshing(true);
    try {
      const [posRes, allocRes, metricRes, curveRes] = await Promise.all([
        api.get("/portfolio/positions"),
        api.get("/portfolio/allocation"),
        api.get("/portfolio/risk-metrics"),
        api.get("/portfolio/equity-curve?limit=100"),
      ]);
      setPositions(posRes.data);
      setAllocation(allocRes.data);
      setMetrics(metricRes.data);
      setCurve(curveRes.data);
    } catch (e) {
      console.error("Portfolio load failed", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (positions.length > 0) setChartTicker(positions[0].ticker);
  }, [positions]);

  const pieData = allocation.slice(0, 7).map((a, i) => ({
    name: a.ticker,
    value: a.pct,
    color: PIE_COLORS[i % PIE_COLORS.length],
  }));

  const curveFormatted = curve.map(p => ({
    t: new Date(p.timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    equity: p.equity,
    pnl: p.day_pnl,
  }));

  const equityMin = curve.length ? Math.min(...curve.map(p => p.equity)) * 0.998 : 99000;
  const equityMax = curve.length ? Math.max(...curve.map(p => p.equity)) * 1.002 : 101000;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={24} className="animate-spin text-accent" />
      </div>
    );
  }

  return (
    <motion.div
      key="portfolio"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-6"
    >
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Portfolio</h1>
          <p className="text-sm text-text-muted mt-0.5">Live positions &amp; performance metrics</p>
        </div>
        <button
          onClick={load}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-text-muted hover:text-text-primary border border-border rounded-lg hover:bg-bg-elevated transition-colors"
        >
          <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Top KPIs */}
      {metrics && (
        <div className="grid grid-cols-4 gap-3">
          <StatCard
            label="Portfolio Equity"
            value={fmt.usd(metrics.equity)}
            sub={`${metrics.invested_pct}% invested`}
          />
          <StatCard
            label="Day P&L"
            value={(metrics.day_pnl >= 0 ? "+" : "") + fmt.usd(metrics.day_pnl)}
            sub={`${metrics.day_pnl_pct >= 0 ? "+" : ""}${metrics.day_pnl_pct.toFixed(2)}%`}
            color={metrics.day_pnl >= 0 ? "text-gain" : "text-loss"}
          />
          <StatCard
            label="Sharpe Ratio"
            value={metrics.sharpe != null ? metrics.sharpe.toFixed(2) : "—"}
            sub={metrics.snapshot_count < 10 ? "Building history..." : "90-day annualized"}
            color={metrics.sharpe != null && metrics.sharpe > 1 ? "text-gain" : undefined}
          />
          <StatCard
            label="Max Drawdown"
            value={metrics.max_drawdown != null ? `${metrics.max_drawdown.toFixed(1)}%` : "—"}
            sub={metrics.total_return != null ? `Total return: ${metrics.total_return > 0 ? "+" : ""}${metrics.total_return.toFixed(1)}%` : undefined}
            color={metrics.max_drawdown != null && metrics.max_drawdown < -5 ? "text-loss" : "text-warn"}
          />
        </div>
      )}

      {/* P&L Calendar */}
      <PnLCalendar />

      {/* Equity curve */}
      {curve.length > 1 && (
        <div className="card p-5">
          <h2 className="text-sm font-semibold text-text-primary mb-4">Equity Curve</h2>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={curveFormatted} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#2D7DD2" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#2D7DD2" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1E2D45" />
              <XAxis dataKey="t" tick={{ fill: "#4D6080", fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis
                domain={[equityMin, equityMax]}
                tick={{ fill: "#4D6080", fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
                width={50}
              />
              <Tooltip
                contentStyle={{ background: "#141D30", border: "1px solid #1E2D45", borderRadius: 8, fontSize: 12 }}
                formatter={(v: number) => [fmt.usd(v), "Equity"]}
              />
              <Area
                type="monotone"
                dataKey="equity"
                stroke="#2D7DD2"
                strokeWidth={2}
                fill="url(#equityGrad)"
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid grid-cols-3 gap-4">
        {/* Allocation pie */}
        <div className="card p-5">
          <h2 className="text-sm font-semibold text-text-primary mb-4">Allocation</h2>
          {pieData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={75} paddingAngle={3} dataKey="value">
                    {pieData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} strokeWidth={0} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: "#141D30", border: "1px solid #1E2D45", borderRadius: 8, fontSize: 12 }}
                    formatter={(v: number) => [`${v.toFixed(1)}%`, ""]}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-1.5 mt-2">
                {pieData.map(({ name, value, color }) => (
                  <div key={name} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} />
                      <span className="text-xs font-mono text-text-secondary">{name}</span>
                    </div>
                    <span className="text-xs font-mono text-text-primary">{value.toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-xs text-text-muted text-center py-8">No positions</p>
          )}
        </div>

        {/* Sector / allocation bars */}
        <div className="card p-5 col-span-2">
          <h2 className="text-sm font-semibold text-text-primary mb-4">Position Weights</h2>
          {pieData.length > 0 ? (
            <div className="space-y-3">
              {pieData.map(({ name, value, color }) => (
                <div key={name}>
                  <div className="flex justify-between mb-1">
                    <span className="text-xs font-mono text-text-secondary">{name}</span>
                    <span className="text-xs font-mono text-text-primary">{value.toFixed(1)}%</span>
                  </div>
                  <div className="h-2 bg-bg-elevated rounded-full overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${value}%` }}
                      transition={{ duration: 0.8, ease: "easeOut" }}
                      className="h-full rounded-full"
                      style={{ backgroundColor: color }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-text-muted">No positions — run a scan to auto-build a portfolio.</p>
          )}
        </div>
      </div>

      {/* Price Chart */}
      {positions.length > 0 && (
        <div className="mt-6 mb-6">
          <div className="flex items-center gap-3 mb-3">
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Price Chart</h2>
            <div className="flex flex-wrap gap-1">
              {positions.slice(0, 6).map(p => (
                <button
                  key={p.ticker}
                  onClick={() => setChartTicker(p.ticker)}
                  className={`px-2 py-0.5 rounded text-xs font-mono transition-colors ${
                    chartTicker === p.ticker
                      ? "bg-accent text-white"
                      : "text-slate-400 hover:text-white hover:bg-bg-elevated"
                  }`}
                >
                  {p.ticker}
                </button>
              ))}
            </div>
          </div>
          <CandlestickChart ticker={chartTicker} period="3mo" height={280} showControls={true} />
        </div>
      )}

      {/* Positions table */}
      <div className="card overflow-hidden">
        <div className="px-5 py-4 border-b border-border flex items-center justify-between">
          <h2 className="text-sm font-semibold text-text-primary">
            Open Positions
            {positions.length > 0 && (
              <span className="ml-2 text-xs text-text-muted font-normal">{positions.length}</span>
            )}
          </h2>
          {metrics && (
            <span className="text-xs text-text-muted font-mono">
              Cash: {fmt.usd(metrics.cash)} · BP: {fmt.usd(metrics.buying_power)}
            </span>
          )}
        </div>
        {positions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  {["Ticker", "Qty", "Entry", "Current", "Mkt Value", "Unrealized P&L", "Stop", "Target"].map(h => (
                    <th key={h} className="metric-label text-left px-4 py-3 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {positions.map(p => (
                  <>
                    <tr
                      key={p.ticker}
                      className="hover:bg-bg-elevated/50 transition-colors group cursor-pointer hover:bg-bg-elevated"
                      onClick={() => setExpandedTicker(prev => prev === p.ticker ? null : p.ticker)}
                    >
                      <td className="px-4 py-3 font-mono font-bold text-text-primary group-hover:text-accent-bright transition-colors">
                        {expandedTicker === p.ticker
                          ? <ChevronDown size={14} className="inline mr-1 text-accent" />
                          : <ChevronRight size={14} className="inline mr-1 text-slate-500" />}
                        {p.ticker}
                      </td>
                      <td className="px-4 py-3 font-mono text-text-secondary">{p.qty.toFixed(4)}</td>
                      <td className="px-4 py-3 font-mono text-text-muted">{fmt.price(p.avg_entry_price)}</td>
                      <td className="px-4 py-3 font-mono text-text-primary">{fmt.price(p.current_price)}</td>
                      <td className="px-4 py-3 font-mono text-text-primary">{fmt.usd(p.market_value)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <PnLBadge value={p.unrealized_pnl_pct} />
                          <span className={cn("text-xs font-mono", p.unrealized_pnl >= 0 ? "text-gain" : "text-loss")}>
                            {p.unrealized_pnl >= 0 ? "+" : ""}{fmt.usd(p.unrealized_pnl)}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs font-mono text-loss/70">—</td>
                      <td className="px-4 py-3 text-xs font-mono text-gain/70">—</td>
                    </tr>
                    {expandedTicker === p.ticker && (
                      <tr key={`${p.ticker}-chart`}>
                        <td colSpan={8} className="p-0">
                          <div className="p-4 bg-bg-card border-t border-border">
                            <CandlestickChart ticker={p.ticker} period="3mo" height={260} showControls={true} />
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="px-5 py-10 text-center">
            <p className="text-sm text-text-muted">No open positions</p>
            <p className="text-xs text-text-muted mt-1">Run a market scan to auto-execute trades</p>
          </div>
        )}
      </div>
    </motion.div>
  );
}
