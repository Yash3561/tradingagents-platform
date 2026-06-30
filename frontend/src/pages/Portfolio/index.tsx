import { motion } from "framer-motion";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import MetricCard from "../../components/data-display/MetricCard";
import PnLBadge from "../../components/data-display/PnLBadge";
import { fmt } from "../../lib/formatters";
import { Shield, Activity, TrendingDown, TrendingUp } from "lucide-react";

const POSITIONS = [
  { ticker: "AAPL", name: "Apple Inc.", qty: 50, price: 229.87, cost: 198.30, value: 11493.50, weight: 9.21, pct: 15.92, sector: "Technology" },
  { ticker: "NVDA", name: "NVIDIA Corp.", qty: 20, price: 131.38, cost: 110.00, value: 2627.60, weight: 2.11, pct: 19.44, sector: "Technology" },
  { ticker: "MSFT", name: "Microsoft Corp.", qty: 30, price: 432.01, cost: 415.50, value: 12960.30, weight: 10.38, pct: 3.97, sector: "Technology" },
  { ticker: "TSLA", name: "Tesla Inc.", qty: 15, price: 253.18, cost: 280.00, value: 3797.70, weight: 3.04, pct: -9.58, sector: "Consumer Disc." },
  { ticker: "AMZN", name: "Amazon.com Inc.", qty: 25, price: 196.98, cost: 185.40, value: 4924.50, weight: 3.95, pct: 6.25, sector: "Consumer Disc." },
  { ticker: "SCHD", name: "Schwab US Dividend", qty: 200, price: 82.14, cost: 78.40, value: 16428.00, weight: 13.16, pct: 4.77, sector: "ETF" },
  { ticker: "TLT", name: "iShares 20Y Treasury", qty: 100, price: 94.80, cost: 97.20, value: 9480.00, weight: 7.60, pct: -2.47, sector: "Fixed Income" },
];

const ALLOCATION = [
  { name: "Technology", value: 42, color: "#2D7DD2" },
  { name: "ETF", value: 22, color: "#4A9AEF" },
  { name: "Fixed Income", value: 18, color: "#00E676" },
  { name: "Consumer Disc.", value: 12, color: "#FFB740" },
  { name: "Cash", value: 6, color: "#4D6080" },
];

const RISK_METRICS = [
  { label: "Sharpe Ratio", value: "1.42", accent: "accent" as const },
  { label: "Sortino Ratio", value: "1.87", accent: "gain" as const },
  { label: "Max Drawdown", value: "-8.4%", accent: "loss" as const },
  { label: "Portfolio Beta", value: "0.92", accent: "accent" as const },
  { label: "Daily VaR (95%)", value: "$1,248", accent: "warn" as const },
  { label: "Calmar Ratio", value: "2.31", accent: "gain" as const },
];

export default function Portfolio() {
  return (
    <motion.div
      key="portfolio"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-6"
    >
      <div>
        <h1 className="text-xl font-semibold text-text-primary">Portfolio</h1>
        <p className="text-sm text-text-muted mt-0.5">Positions, allocation &amp; risk metrics</p>
      </div>

      {/* Risk metrics grid */}
      <div className="grid grid-cols-6 gap-3">
        {RISK_METRICS.map(({ label, value, accent }) => (
          <MetricCard key={label} label={label} value={value} accent={accent} />
        ))}
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Allocation pie */}
        <div className="card p-5">
          <h2 className="text-sm font-semibold text-text-primary mb-4">Allocation</h2>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={ALLOCATION} cx="50%" cy="50%" innerRadius={55} outerRadius={80} paddingAngle={3} dataKey="value">
                {ALLOCATION.map((entry, i) => (
                  <Cell key={i} fill={entry.color} strokeWidth={0} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: "#141D30", border: "1px solid #1E2D45", borderRadius: 8, fontSize: 12 }}
                formatter={(v: number) => [`${v}%`, ""]}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="space-y-2 mt-2">
            {ALLOCATION.map(({ name, value, color }) => (
              <div key={name} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
                  <span className="text-xs text-text-secondary">{name}</span>
                </div>
                <span className="text-xs font-mono text-text-primary">{value}%</span>
              </div>
            ))}
          </div>
        </div>

        {/* Sector exposure horizontal bars */}
        <div className="card p-5 col-span-2">
          <h2 className="text-sm font-semibold text-text-primary mb-4">Sector Exposure</h2>
          <div className="space-y-3">
            {ALLOCATION.map(({ name, value, color }) => (
              <div key={name}>
                <div className="flex justify-between mb-1">
                  <span className="text-xs text-text-secondary">{name}</span>
                  <span className="text-xs font-mono text-text-primary">{value}%</span>
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
        </div>
      </div>

      {/* Positions table */}
      <div className="card p-5">
        <h2 className="text-sm font-semibold text-text-primary mb-4">Positions</h2>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                {["Ticker", "Name", "Qty", "Price", "Cost", "Market Value", "Weight", "P&L", "Sector"].map(h => (
                  <th key={h} className="metric-label text-left pb-3 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {POSITIONS.map(({ ticker, name, qty, price, cost, value, weight, pct, sector }) => (
                <tr key={ticker} className="hover:bg-bg-elevated/50 transition-colors group">
                  <td className="py-3 pr-4">
                    <span className="font-mono font-bold text-sm text-text-primary group-hover:text-accent-bright transition-colors">{ticker}</span>
                  </td>
                  <td className="py-3 pr-4 text-xs text-text-secondary max-w-[140px] truncate">{name}</td>
                  <td className="py-3 pr-4 font-mono text-sm text-text-secondary">{qty}</td>
                  <td className="py-3 pr-4 font-mono text-sm text-text-primary">{fmt.price(price)}</td>
                  <td className="py-3 pr-4 font-mono text-sm text-text-muted">{fmt.price(cost)}</td>
                  <td className="py-3 pr-4 font-mono text-sm text-text-primary">{fmt.usd(value)}</td>
                  <td className="py-3 pr-4 font-mono text-sm text-text-secondary">{weight.toFixed(1)}%</td>
                  <td className="py-3 pr-4"><PnLBadge value={pct} /></td>
                  <td className="py-3 text-xs text-text-muted">{sector}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </motion.div>
  );
}
