import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { DollarSign, TrendingUp, BarChart2, Activity, Loader2, RefreshCw } from "lucide-react";
import MetricCard from "../../components/data-display/MetricCard";
import PnLBadge from "../../components/data-display/PnLBadge";
import { fmt } from "../../lib/formatters";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

const FADE_UP = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.4 },
};

export default function Dashboard() {
  const [summary, setSummary] = useState<any>(null);
  const [pulse, setPulse] = useState<any[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [activity, setActivity] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setRefreshing(true);
    try {
      const [s, p, pos, act] = await Promise.all([
        api.get("/portfolio/risk-metrics"),
        api.get("/dashboard/market-pulse"),
        api.get("/portfolio/positions"),
        api.get("/activity/?limit=10").catch(() => api.get("/dashboard/agent-activity")),
      ]);
      setSummary(s.data);
      setPulse(p.data);
      setPositions(pos.data);
      setActivity(act.data);
    } catch (e) {
      console.error("Dashboard load failed", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 30000); // refresh every 30s
    return () => clearInterval(interval);
  }, []);

  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={24} className="animate-spin text-accent" />
      </div>
    );
  }

  return (
    <motion.div
      key="dashboard"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-6"
    >
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Dashboard</h1>
          <p className="text-sm text-text-muted mt-0.5">{today}</p>
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

      {/* KPI Row */}
      <div className="grid grid-cols-4 gap-4">
        <MetricCard
          label="Portfolio Value"
          value={summary ? fmt.usd(summary.equity) : "—"}
          delta={summary?.day_pnl_pct}
          icon={<DollarSign size={16} />}
          accent={summary?.day_pnl >= 0 ? "gain" : "loss"}
        />
        <MetricCard
          label="Day P&L"
          value={summary ? `${summary.day_pnl >= 0 ? "+" : ""}${fmt.usd(summary.day_pnl)}` : "—"}
          delta={summary?.day_pnl_pct}
          icon={<TrendingUp size={16} />}
          accent={summary?.day_pnl >= 0 ? "gain" : "loss"}
        />
        <MetricCard
          label="Unrealized P&L"
          value={positions.length > 0
            ? `${positions.reduce((s: number, p: any) => s + p.unrealized_pnl, 0) >= 0 ? "+" : ""}${fmt.usd(positions.reduce((s: number, p: any) => s + p.unrealized_pnl, 0))}`
            : "No positions"}
          icon={<BarChart2 size={16} />}
          accent={positions.reduce((s: number, p: any) => s + p.unrealized_pnl, 0) >= 0 ? "gain" : "loss"}
        />
        <MetricCard
          label="Sharpe Ratio"
          value={summary?.sharpe != null ? summary.sharpe.toFixed(2) : "Building..."}
          icon={<Activity size={16} />}
          accent="accent"
        />
      </div>

      {/* Market Pulse */}
      <motion.div {...FADE_UP} transition={{ delay: 0.1, duration: 0.4 }} className="card p-5">
        <h2 className="text-sm font-semibold text-text-primary mb-4">Market Pulse</h2>
        {pulse.length > 0 ? (
          <div className="grid grid-cols-6 gap-3">
            {pulse.map(({ label, value, change }: any) => (
              <div key={label} className="flex flex-col gap-1 p-3 rounded-lg bg-bg-elevated border border-border">
                <span className="text-2xs text-text-muted font-medium">{label}</span>
                <span className="text-sm font-mono font-semibold text-text-primary">
                  {label === "10Y" ? `${value?.toFixed(2)}%` : label === "VIX" ? value?.toFixed(2) : fmt.price(value ?? 0)}
                </span>
                <span className={cn("text-2xs font-mono", (change ?? 0) >= 0 ? "text-gain" : "text-loss")}>
                  {(change ?? 0) >= 0 ? "+" : ""}{(change ?? 0).toFixed(2)}{label === "10Y" ? "" : "%"}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-text-muted">Market data unavailable</p>
        )}
      </motion.div>

      <div className="grid grid-cols-5 gap-4">
        {/* Live Positions */}
        <motion.div {...FADE_UP} transition={{ delay: 0.15, duration: 0.4 }} className="card p-5 col-span-3">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-text-primary">Live Positions</h2>
            <a href="/portfolio" className="text-xs text-accent-bright hover:underline">View all →</a>
          </div>
          {positions.length > 0 ? (
            <table className="w-full">
              <thead>
                <tr className="text-left">
                  {["Ticker", "Qty", "Price", "Entry", "P&L"].map(h => (
                    <th key={h} className="metric-label pb-3 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {positions.slice(0, 5).map((p: any) => (
                  <tr key={p.ticker} className="hover:bg-bg-elevated/50 transition-colors">
                    <td className="py-3">
                      <span className="font-mono font-semibold text-sm text-text-primary">{p.ticker}</span>
                    </td>
                    <td className="py-3 font-mono text-sm text-text-secondary">{p.qty.toFixed(2)}</td>
                    <td className="py-3 font-mono text-sm text-text-primary">{fmt.price(p.current_price)}</td>
                    <td className="py-3 font-mono text-sm text-text-muted">{fmt.price(p.avg_entry_price)}</td>
                    <td className="py-3">
                      <PnLBadge value={p.unrealized_pnl_pct} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <p className="text-sm text-text-muted">No open positions</p>
              <p className="text-xs text-text-muted mt-1">Run a scan to auto-build positions</p>
              <a href="/scanner" className="mt-3 text-xs text-accent-bright hover:underline">Go to Scanner →</a>
            </div>
          )}
        </motion.div>

        {/* Agent Activity Feed */}
        <motion.div {...FADE_UP} transition={{ delay: 0.2, duration: 0.4 }} className="card p-5 col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-text-primary">Agent Activity</h2>
            <a href="/agents" className="text-xs text-accent-bright hover:underline">Agent Hub →</a>
          </div>
          {activity.length > 0 ? (
            <div className="space-y-2">
              {activity.slice(0, 6).map((r: any, i: number) => {
                // Support both activity log format and legacy agent-activity format
                const decision = r.result ?? r.decision ?? "HOLD";
                const ticker = r.ticker ?? "—";
                const label = r.action ? r.action.replace(/_/g, " ") : (r.confidence != null ? `${Math.round(r.confidence * 100)}% confidence` : "");
                const feature = r.feature ?? "agent_hub";
                const featureColor = feature === "scanner" ? "bg-warn" : feature === "backtest" ? "bg-accent" : (decision === "BUY" ? "bg-gain" : decision === "SELL" ? "bg-loss" : "bg-warn");
                return (
                  <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-bg-elevated border border-border">
                    <div className={cn("mt-0.5 w-2 h-2 rounded-full shrink-0", featureColor)} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-semibold text-sm text-text-primary">{ticker}</span>
                        <span className={cn(
                          "text-xs font-semibold",
                          decision === "BUY" ? "text-gain" : decision === "SELL" ? "text-loss" :
                          decision === "completed" ? "text-accent" : "text-warn"
                        )}>
                          {decision}
                        </span>
                      </div>
                      <p className="text-2xs text-text-muted mt-0.5">{label}</p>
                    </div>
                    <span className="text-2xs text-text-muted shrink-0">
                      {new Date(r.created_at).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-text-muted text-center py-8">No activity yet</p>
          )}
        </motion.div>
      </div>
    </motion.div>
  );
}
