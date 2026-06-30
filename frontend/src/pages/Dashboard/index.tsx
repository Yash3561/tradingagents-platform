import { motion } from "framer-motion";
import { DollarSign, TrendingUp, BarChart2, Activity, ArrowUpRight, ArrowDownRight } from "lucide-react";
import MetricCard from "../../components/data-display/MetricCard";
import PnLBadge from "../../components/data-display/PnLBadge";
import { fmt } from "../../lib/formatters";

const POSITIONS = [
  { ticker: "AAPL", qty: 50, price: 229.87, cost: 198.30, pct: 15.92 },
  { ticker: "NVDA", qty: 20, price: 131.38, cost: 110.00, pct: 19.44 },
  { ticker: "MSFT", qty: 30, price: 432.01, cost: 415.50, pct: 3.97 },
  { ticker: "TSLA", qty: 15, price: 253.18, cost: 280.00, pct: -9.58 },
  { ticker: "AMZN", qty: 25, price: 196.98, cost: 185.40, pct: 6.25 },
];

const ACTIVITY = [
  { ticker: "NVDA", decision: "BUY", time: "10:32 AM", confidence: 0.84, agent: "Portfolio Manager" },
  { ticker: "TSLA", decision: "HOLD", time: "09:15 AM", confidence: 0.61, agent: "Portfolio Manager" },
  { ticker: "AAPL", decision: "BUY", time: "Yesterday", confidence: 0.79, agent: "Portfolio Manager" },
];

const MARKET_PULSE = [
  { label: "S&P 500", value: 5801.21, change: +0.48 },
  { label: "NASDAQ", value: 18439.17, change: +0.82 },
  { label: "DOW", value: 43385.60, change: +0.31 },
  { label: "VIX", value: 14.31, change: -3.21 },
  { label: "BTC", value: 67420, change: +2.14 },
  { label: "10Y", value: 4.21, change: +0.02 },
];

const FADE_UP = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.4 },
};

export default function Dashboard() {
  return (
    <motion.div
      key="dashboard"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-6"
    >
      <div>
        <h1 className="text-xl font-semibold text-text-primary">Dashboard</h1>
        <p className="text-sm text-text-muted mt-0.5">Sunday, June 29, 2025</p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-4 gap-4">
        <MetricCard
          label="Portfolio Value"
          value="$124,831.50"
          delta={1.24}
          icon={<DollarSign size={16} />}
          accent="gain"
        />
        <MetricCard
          label="Day P&L"
          value="+$1,532.18"
          delta={1.24}
          icon={<TrendingUp size={16} />}
          accent="gain"
        />
        <MetricCard
          label="Unrealized P&L"
          value="+$8,420.33"
          delta={7.24}
          icon={<BarChart2 size={16} />}
          accent="gain"
        />
        <MetricCard
          label="Sharpe Ratio"
          value="1.42"
          icon={<Activity size={16} />}
          accent="accent"
        />
      </div>

      {/* Market Pulse */}
      <motion.div {...FADE_UP} transition={{ delay: 0.1, duration: 0.4 }} className="card p-5">
        <h2 className="text-sm font-semibold text-text-primary mb-4">Market Pulse</h2>
        <div className="grid grid-cols-6 gap-3">
          {MARKET_PULSE.map(({ label, value, change }) => (
            <div key={label} className="flex flex-col gap-1 p-3 rounded-lg bg-bg-elevated border border-border">
              <span className="text-2xs text-text-muted font-medium">{label}</span>
              <span className="text-sm font-mono font-semibold text-text-primary">
                {label === "10Y" ? `${value}%` : label === "VIX" ? value.toFixed(2) : fmt.price(value)}
              </span>
              <span className={`text-2xs font-mono ${change >= 0 ? "text-gain" : "text-loss"}`}>
                {change >= 0 ? "+" : ""}{change.toFixed(2)}{label === "10Y" ? "" : "%"}
              </span>
            </div>
          ))}
        </div>
      </motion.div>

      <div className="grid grid-cols-5 gap-4">
        {/* Live Positions */}
        <motion.div {...FADE_UP} transition={{ delay: 0.15, duration: 0.4 }} className="card p-5 col-span-3">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-text-primary">Live Positions</h2>
            <a href="/portfolio" className="text-xs text-accent-bright hover:underline">View all →</a>
          </div>
          <table className="w-full">
            <thead>
              <tr className="text-left">
                {["Ticker", "Qty", "Price", "Cost Basis", "P&L"].map(h => (
                  <th key={h} className="metric-label pb-3 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {POSITIONS.map(({ ticker, qty, price, cost, pct }) => (
                <tr key={ticker} className="hover:bg-bg-elevated/50 transition-colors">
                  <td className="py-3">
                    <span className="font-mono font-semibold text-sm text-text-primary">{ticker}</span>
                  </td>
                  <td className="py-3 font-mono text-sm text-text-secondary">{qty}</td>
                  <td className="py-3 font-mono text-sm text-text-primary">{fmt.price(price)}</td>
                  <td className="py-3 font-mono text-sm text-text-secondary">{fmt.price(cost)}</td>
                  <td className="py-3">
                    <PnLBadge value={pct} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </motion.div>

        {/* Agent Activity Feed */}
        <motion.div {...FADE_UP} transition={{ delay: 0.2, duration: 0.4 }} className="card p-5 col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-text-primary">Agent Activity</h2>
            <a href="/agents" className="text-xs text-accent-bright hover:underline">Agent Hub →</a>
          </div>
          <div className="space-y-3">
            {ACTIVITY.map(({ ticker, decision, time, confidence, agent }) => (
              <div key={`${ticker}-${time}`} className="flex items-start gap-3 p-3 rounded-lg bg-bg-elevated border border-border">
                <div className={`mt-0.5 w-2 h-2 rounded-full shrink-0 ${decision === "BUY" ? "bg-gain" : decision === "SELL" ? "bg-loss" : "bg-warn"}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-semibold text-sm text-text-primary">{ticker}</span>
                    <span className={`text-xs font-semibold ${decision === "BUY" ? "text-gain" : decision === "SELL" ? "text-loss" : "text-warn"}`}>
                      {decision}
                    </span>
                  </div>
                  <p className="text-2xs text-text-muted mt-0.5">{agent} · {Math.round(confidence * 100)}% confidence</p>
                </div>
                <span className="text-2xs text-text-muted shrink-0">{time}</span>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}
