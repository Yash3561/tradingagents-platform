import { useEffect, useState, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { DollarSign, TrendingUp, BarChart2, Activity, Loader2, RefreshCw, ShieldCheck, ShieldAlert, ShieldX, Clock, Radio, Bell, Brain } from "lucide-react";
import MetricCard from "../../components/data-display/MetricCard";
import PnLBadge from "../../components/data-display/PnLBadge";
import CandlestickChart from "../../components/charts/CandlestickChart";
import { fmt } from "../../lib/formatters";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

const FADE_UP = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.4 },
};

// ── System Status types ───────────────────────────────────────────────────────

interface CircuitBreakerStatus {
  blocked: boolean;
  reasons: string[];
  warnings: string[];
}

interface SystemStatusData {
  circuit_breakers: CircuitBreakerStatus;
  market_open: boolean;
  last_monitor_check: string;
  positions_count: number;
  today_pnl_pct: number;
  next_scheduled_scan: string;
}

// ── SystemStatus card component ────────────────────────────────────────────────

function SystemStatus() {
  const [status, setStatus] = useState<SystemStatusData | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState(false);

  const fetchStatus = async () => {
    try {
      const res = await api.get("/system/status");
      setStatus(res.data);
      setLastUpdated(new Date());
      setError(false);
    } catch {
      setError(true);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 60000); // poll every 60s
    return () => clearInterval(interval);
  }, []);

  // Derive overall health level
  const healthLevel: "green" | "amber" | "red" = (() => {
    if (!status) return "green";
    if (status.circuit_breakers.blocked) return "red";
    if (status.circuit_breakers.warnings.length > 0) return "amber";
    return "green";
  })();

  const healthDot = {
    green: "bg-gain",
    amber: "bg-warn",
    red: "bg-loss",
  }[healthLevel];

  const healthText = {
    green: "text-gain",
    amber: "text-warn",
    red: "text-loss",
  }[healthLevel];

  const HealthIcon = healthLevel === "green"
    ? ShieldCheck
    : healthLevel === "amber"
    ? ShieldAlert
    : ShieldX;

  const cbLabel = (() => {
    if (!status) return "Checking...";
    if (status.circuit_breakers.blocked) {
      return `BLOCKED: ${status.circuit_breakers.reasons[0] ?? "Circuit breaker active"}`;
    }
    if (status.circuit_breakers.warnings.length > 0) {
      return `${status.circuit_breakers.warnings.length} warning(s) active`;
    }
    return "All clear";
  })();

  const lastCheckLabel = (() => {
    if (!lastUpdated) return "—";
    const diffMs = Date.now() - lastUpdated.getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return "just now";
    if (mins === 1) return "1 min ago";
    return `${mins} min ago`;
  })();

  const nextScanLabel = (() => {
    if (!status?.next_scheduled_scan) return "—";
    const d = new Date(status.next_scheduled_scan);
    const now = new Date();
    const diffMs = d.getTime() - now.getTime();
    if (diffMs <= 0) return "Soon";
    const diffH = Math.floor(diffMs / 3600000);
    const diffM = Math.floor((diffMs % 3600000) / 60000);
    if (diffH === 0) return `${diffM}m`;
    if (diffH < 20) return `${diffH}h ${diffM}m`;
    // Tomorrow or later — show time in ET
    return d.toLocaleString("en-US", {
      weekday: "short",
      hour: "numeric",
      minute: "2-digit",
      timeZone: "America/New_York",
      timeZoneName: "short",
    });
  })();

  return (
    <motion.div
      {...FADE_UP}
      transition={{ delay: 0.05, duration: 0.4 }}
      className="card p-5"
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <HealthIcon size={15} className={healthText} />
          <h2 className="text-sm font-semibold text-text-primary">System Control</h2>
        </div>
        <div className="flex items-center gap-1.5">
          <div className={cn("w-2 h-2 rounded-full animate-pulse-slow", healthDot)} />
          <span className={cn("text-xs font-semibold", healthText)}>
            {healthLevel === "green" ? "Nominal" : healthLevel === "amber" ? "Alert" : "BLOCKED"}
          </span>
        </div>
      </div>

      {error && (
        <p className="text-xs text-loss mb-3">Status unavailable — backend unreachable</p>
      )}

      <div className="grid grid-cols-2 gap-3">
        {/* Circuit Breakers */}
        <div className="p-3 rounded-lg bg-bg-elevated border border-border space-y-1">
          <p className="text-2xs text-text-muted font-medium uppercase tracking-wide">Circuit Breakers</p>
          <p className={cn("text-xs font-semibold truncate", healthText)}>{cbLabel}</p>
          {status?.circuit_breakers.warnings.map((w, i) => (
            <p key={i} className="text-2xs text-warn truncate">{w}</p>
          ))}
        </div>

        {/* Market status */}
        <div className="p-3 rounded-lg bg-bg-elevated border border-border space-y-1">
          <p className="text-2xs text-text-muted font-medium uppercase tracking-wide">Market</p>
          <div className="flex items-center gap-1.5">
            <div className={cn(
              "w-2 h-2 rounded-full",
              status?.market_open ? "bg-gain animate-pulse-slow" : "bg-text-muted"
            )} />
            <span className={cn(
              "text-xs font-semibold",
              status?.market_open ? "text-gain" : "text-text-muted"
            )}>
              {status === null ? "—" : status.market_open ? "OPEN" : "CLOSED"}
            </span>
          </div>
          <div className="flex items-center gap-1 mt-0.5">
            <Radio size={10} className="text-text-muted" />
            <span className="text-2xs text-text-muted">{status?.positions_count ?? "—"} positions</span>
          </div>
        </div>

        {/* Last check */}
        <div className="p-3 rounded-lg bg-bg-elevated border border-border space-y-1">
          <p className="text-2xs text-text-muted font-medium uppercase tracking-wide">Last Check</p>
          <div className="flex items-center gap-1.5">
            <Clock size={11} className="text-text-muted" />
            <span className="text-xs text-text-secondary font-mono">{lastCheckLabel}</span>
          </div>
          <p className="text-2xs text-text-muted">
            P&amp;L today: <span className={cn("font-semibold font-mono",
              (status?.today_pnl_pct ?? 0) >= 0 ? "text-gain" : "text-loss"
            )}>
              {status ? `${(status.today_pnl_pct ?? 0) >= 0 ? "+" : ""}${status.today_pnl_pct?.toFixed(2)}%` : "—"}
            </span>
          </p>
        </div>

        {/* Next scan */}
        <div className="p-3 rounded-lg bg-bg-elevated border border-border space-y-1">
          <p className="text-2xs text-text-muted font-medium uppercase tracking-wide">Next Scan</p>
          <span className="text-xs font-mono text-text-secondary">{nextScanLabel}</span>
          <p className="text-2xs text-text-muted">Auto-scheduled</p>
        </div>
      </div>
    </motion.div>
  );
}

// ── AI Market Brief types + component ─────────────────────────────────────────

interface BriefData {
  market_data: Record<string, { price: number; change_pct: number; trend_5d: number }>;
  brief: {
    market_mood: "RISK_ON" | "RISK_OFF" | "NEUTRAL" | "VOLATILE";
    dominant_theme: string;
    key_observations: string[];
    portfolio_impact: string;
    watch_today: string[];
  };
  generated_at: string;
}

const MOOD_CONFIG = {
  RISK_ON:  { label: "Risk On",  color: "text-gain",      bg: "bg-gain/10 border-gain/20",     dot: "bg-gain" },
  RISK_OFF: { label: "Risk Off", color: "text-loss",      bg: "bg-loss/10 border-loss/20",     dot: "bg-loss" },
  NEUTRAL:  { label: "Neutral",  color: "text-slate-300", bg: "bg-bg-elevated border-border",  dot: "bg-slate-400" },
  VOLATILE: { label: "Volatile", color: "text-warn",      bg: "bg-warn/10 border-warn/20",     dot: "bg-warn animate-pulse" },
};

function MarketBriefCard({ data, loading }: { data: BriefData | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="card p-5 flex items-center gap-3">
        <Loader2 size={18} className="text-accent animate-spin shrink-0" />
        <div>
          <p className="text-sm font-medium text-white">Generating AI Market Brief...</p>
          <p className="text-xs text-slate-500 mt-0.5">Analyzing SPY, QQQ, VIX, sectors, crypto</p>
        </div>
      </div>
    );
  }
  if (!data) return null;

  const mood = data.brief.market_mood;
  const cfg = MOOD_CONFIG[mood] ?? MOOD_CONFIG.NEUTRAL;
  const marketItems = Object.entries(data.market_data).slice(0, 5);

  return (
    <div className={`card p-5 border ${cfg.bg}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <Brain size={16} className="text-accent" />
          <span className="text-sm font-semibold text-white">AI Market Brief</span>
          <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full border ${cfg.bg}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
            <span className={`text-xs font-semibold ${cfg.color}`}>{cfg.label}</span>
          </div>
        </div>
        <span className="text-xs text-slate-500">
          {new Date(data.generated_at).toLocaleTimeString()}
        </span>
      </div>

      {/* Dominant theme */}
      <p className="text-sm text-slate-200 mb-4 leading-relaxed font-medium">
        {data.brief.dominant_theme}
      </p>

      {/* Market data pills */}
      <div className="flex flex-wrap gap-2 mb-4">
        {marketItems.map(([label, d]) => (
          <div key={label} className="flex items-center gap-1.5 bg-bg-elevated rounded-lg px-2.5 py-1.5">
            <span className="text-xs text-slate-400">{label}</span>
            <span className="text-xs font-mono font-bold text-white">${d.price.toLocaleString()}</span>
            <span className={`text-xs font-mono ${d.change_pct >= 0 ? "text-gain" : "text-loss"}`}>
              {d.change_pct >= 0 ? "+" : ""}{d.change_pct.toFixed(2)}%
            </span>
          </div>
        ))}
      </div>

      {/* Key observations */}
      <div className="space-y-1.5 mb-4">
        {data.brief.key_observations.slice(0, 3).map((obs, i) => (
          <div key={i} className="flex items-start gap-2 text-xs text-slate-300">
            <span className="text-accent mt-0.5 shrink-0">•</span>
            {obs}
          </div>
        ))}
      </div>

      {/* Portfolio impact */}
      {data.brief.portfolio_impact && (
        <div className="bg-bg-elevated rounded-lg px-3 py-2.5 mb-3">
          <p className="text-xs text-slate-500 mb-0.5">Portfolio Impact</p>
          <p className="text-xs text-slate-200">{data.brief.portfolio_impact}</p>
        </div>
      )}

      {/* Watch today */}
      {data.brief.watch_today.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          <span className="text-xs text-slate-500">Watch:</span>
          {data.brief.watch_today.map((w, i) => (
            <span key={i} className="text-xs bg-accent/10 text-accent px-2 py-0.5 rounded-full">{w}</span>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Live price hook ────────────────────────────────────────────────────────────

interface LivePrice { price: number; prev: number; flash: "up" | "down" | null; }

function useLivePrices(tickers: string[]) {
  const [prices, setPrices] = useState<Record<string, LivePrice>>({});
  const prevRef = useRef<Record<string, number>>({});

  const fetchPrices = useCallback(async () => {
    if (tickers.length === 0) return;
    const results = await Promise.allSettled(
      tickers.map(t => api.get(`/market/quote/${t}/live`))
    );
    setPrices(prev => {
      const next = { ...prev };
      results.forEach((r, i) => {
        if (r.status === "fulfilled") {
          const ticker = tickers[i];
          const newPrice = r.value.data.price as number;
          const oldPrice = prevRef.current[ticker] ?? newPrice;
          next[ticker] = {
            price: newPrice,
            prev: oldPrice,
            flash: newPrice > oldPrice ? "up" : newPrice < oldPrice ? "down" : null,
          };
          prevRef.current[ticker] = newPrice;
          // Clear flash after 800ms
          if (next[ticker].flash) {
            setTimeout(() => {
              setPrices(p => ({ ...p, [ticker]: { ...p[ticker], flash: null } }));
            }, 800);
          }
        }
      });
      return next;
    });
  }, [tickers.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (tickers.length === 0) return;
    fetchPrices();
    const t = setInterval(fetchPrices, 8000);
    return () => clearInterval(t);
  }, [fetchPrices]);

  return prices;
}

// ── Main Dashboard ─────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [summary, setSummary] = useState<any>(null);
  const [pulse, setPulse] = useState<any[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [activity, setActivity] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [chartTicker, setChartTicker] = useState("SPY");
  const [alertSummary, setAlertSummary] = useState<{total:number,critical:number,warning:number,info:number} | null>(null);
  const [brief, setBrief] = useState<BriefData | null>(null);
  const [briefLoading, setBriefLoading] = useState(false);
  const positionTickers = positions.map((p: any) => p.ticker);
  const livePrices = useLivePrices(positionTickers);

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

  useEffect(() => {
    api.get("/alerts/summary").then(r => setAlertSummary(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    setBriefLoading(true);
    api.get("/dashboard/market-brief")
      .then(r => setBrief(r.data))
      .catch(() => {})
      .finally(() => setBriefLoading(false));
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

      {/* Broker not connected banner */}
      {summary && summary.broker_connected === false && (
        <motion.div
          {...FADE_UP}
          className="flex items-center justify-between gap-4 px-4 py-3 rounded-xl border border-accent/40 bg-accent/10"
        >
          <div className="flex items-center gap-3">
            <ShieldAlert size={18} className="text-accent shrink-0" />
            <div>
              <p className="text-sm font-medium text-text-primary">Connect your Alpaca paper account to start trading</p>
              <p className="text-xs text-text-muted mt-0.5">
                Free paper account — the AI agents will trade in it with virtual money. Takes 2 minutes.
              </p>
            </div>
          </div>
          <Link
            to="/settings"
            className="shrink-0 px-3 py-1.5 text-xs font-medium text-white bg-accent hover:bg-accent/90 rounded-lg transition-colors"
          >
            Connect Broker
          </Link>
        </motion.div>
      )}

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

      {/* AI Market Brief */}
      <MarketBriefCard data={brief} loading={briefLoading} />

      {/* System Status + Market Pulse row */}
      <div className="grid grid-cols-5 gap-4">
        <div className="col-span-2">
          <SystemStatus />
        </div>

        {/* Market Pulse */}
        <motion.div {...FADE_UP} transition={{ delay: 0.1, duration: 0.4 }} className="card p-5 col-span-3">
          <h2 className="text-sm font-semibold text-text-primary mb-4">Market Pulse</h2>
          {pulse.length > 0 ? (
            <div className="grid grid-cols-3 gap-3">
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
      </div>

      {/* Active Alerts mini-card */}
      {alertSummary && alertSummary.total > 0 && (
        <div className="card p-4 border border-warn/20 bg-warn/5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bell size={16} className="text-warn" />
              <span className="text-sm font-semibold text-white">
                {alertSummary.total} Active Alert{alertSummary.total !== 1 ? "s" : ""}
              </span>
            </div>
            <a href="/alerts" className="text-xs text-accent hover:underline">View All →</a>
          </div>
          <div className="flex gap-3 mt-2">
            {alertSummary.critical > 0 && <span className="text-xs text-loss font-mono">{alertSummary.critical} critical</span>}
            {alertSummary.warning > 0 && <span className="text-xs text-warn font-mono">{alertSummary.warning} warning</span>}
            {alertSummary.info > 0 && <span className="text-xs text-slate-400 font-mono">{alertSummary.info} info</span>}
          </div>
        </div>
      )}

      {/* Price Chart */}
      <div className="mt-2">
        <div className="flex items-center gap-3 mb-3">
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
            Price Chart
          </h2>
          <div className="flex gap-2">
            {["SPY", "QQQ", "AAPL", "NVDA"].map((t) => (
              <button
                key={t}
                onClick={() => setChartTicker(t)}
                className={`px-2 py-0.5 rounded text-xs font-mono transition-colors ${
                  chartTicker === t
                    ? "bg-accent text-white"
                    : "text-slate-400 hover:text-white hover:bg-bg-elevated"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
        <CandlestickChart ticker={chartTicker} period="3mo" height={300} showControls={true} />
      </div>

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
                {positions.slice(0, 5).map((p: any) => {
                  const live = livePrices[p.ticker];
                  const displayPrice = live?.price ?? p.current_price;
                  const liveUnrealizedPct = live
                    ? ((displayPrice - p.avg_entry_price) / p.avg_entry_price) * 100
                    : p.unrealized_pnl_pct;
                  return (
                    <tr key={p.ticker} className="hover:bg-bg-elevated/50 transition-colors">
                      <td className="py-3">
                        <span className="font-mono font-semibold text-sm text-text-primary">{p.ticker}</span>
                      </td>
                      <td className="py-3 font-mono text-sm text-text-secondary">{p.qty.toFixed(2)}</td>
                      <td className="py-3">
                        <span className={cn(
                          "font-mono text-sm font-semibold transition-colors duration-300",
                          live?.flash === "up" ? "text-gain" : live?.flash === "down" ? "text-loss" : "text-text-primary"
                        )}>
                          {fmt.price(displayPrice)}
                          {live?.flash && (
                            <span className="ml-1 text-xs">{live.flash === "up" ? "▲" : "▼"}</span>
                          )}
                        </span>
                      </td>
                      <td className="py-3 font-mono text-sm text-text-muted">{fmt.price(p.avg_entry_price)}</td>
                      <td className="py-3">
                        <PnLBadge value={liveUnrealizedPct} />
                      </td>
                    </tr>
                  );
                })}
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
