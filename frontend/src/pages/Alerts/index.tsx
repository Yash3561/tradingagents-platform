import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, ShieldAlert, Info, RefreshCw, Loader2, Bell, TrendingDown, TrendingUp, Clock, Activity } from "lucide-react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

interface Alert {
  id: string;
  type: string;
  severity: "critical" | "warning" | "info";
  ticker: string | null;
  title: string;
  message: string;
  value: number;
  threshold: number;
}

interface AlertsResponse {
  alerts: Alert[];
  scanned_at: string;
  positions_checked: number;
  equity: number;
  alert_counts: { critical: number; warning: number; info: number };
}

const SEVERITY_CONFIG = {
  critical: {
    icon: ShieldAlert,
    color: "text-loss",
    bg: "bg-loss/10 border-loss/30",
    label: "Critical",
    dot: "bg-loss",
  },
  warning: {
    icon: AlertTriangle,
    color: "text-warn",
    bg: "bg-warn/10 border-warn/20",
    label: "Warning",
    dot: "bg-warn",
  },
  info: {
    icon: Info,
    color: "text-accent",
    bg: "bg-accent/10 border-accent/20",
    label: "Info",
    dot: "bg-accent",
  },
};

const TYPE_ICON: Record<string, React.ComponentType<any>> = {
  concentration: TrendingUp,
  drawdown: TrendingDown,
  take_profit: TrendingUp,
  rsi: Activity,
  stale_position: Clock,
};

function AlertCard({ alert }: { alert: Alert }) {
  const cfg = SEVERITY_CONFIG[alert.severity];
  const Icon = TYPE_ICON[alert.type] ?? Bell;
  const SevIcon = cfg.icon;

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      className={cn("card p-4 border", cfg.bg)}
    >
      <div className="flex items-start gap-3">
        <div className={cn("mt-0.5 shrink-0", cfg.color)}>
          <SevIcon size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={cn("text-sm font-semibold", cfg.color)}>{alert.title}</span>
            {alert.ticker && (
              <span className="font-mono text-xs bg-bg-elevated px-1.5 py-0.5 rounded text-slate-300">
                {alert.ticker}
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400 mt-1 leading-relaxed">{alert.message}</p>
        </div>
        <div className="shrink-0 text-right">
          <Icon size={14} className="text-slate-500" />
        </div>
      </div>
    </motion.div>
  );
}

export default function Alerts() {
  const [data, setData] = useState<AlertsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data: res } = await api.get("/alerts/");
      setData(res);
    } catch (e: any) {
      setError(e.response?.data?.detail ?? "Failed to load alerts");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const critical = data?.alerts.filter(a => a.severity === "critical") ?? [];
  const warnings = data?.alerts.filter(a => a.severity === "warning") ?? [];
  const infos = data?.alerts.filter(a => a.severity === "info") ?? [];

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Bell size={22} className="text-accent" />
          <div>
            <h1 className="text-xl font-bold text-white">Smart Alerts</h1>
            <p className="text-sm text-slate-400">
              {data ? `${data.positions_checked} positions scanned` : "Scanning portfolio for risk conditions..."}
            </p>
          </div>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-accent/10 hover:bg-accent/20 border border-accent/30 text-accent rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Rescan
        </button>
      </div>

      {/* Summary row */}
      {data && (
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Critical", count: data.alert_counts.critical, color: "text-loss", bg: "bg-loss/10 border-loss/20" },
            { label: "Warning", count: data.alert_counts.warning, color: "text-warn", bg: "bg-warn/10 border-warn/20" },
            { label: "Info", count: data.alert_counts.info, color: "text-accent", bg: "bg-accent/10 border-accent/20" },
          ].map(c => (
            <div key={c.label} className={cn("card p-4 border text-center", c.bg)}>
              <p className={cn("text-3xl font-black font-mono", c.color)}>{c.count}</p>
              <p className="text-xs text-slate-400 mt-1">{c.label}</p>
            </div>
          ))}
        </div>
      )}

      {loading && !data && (
        <div className="flex items-center justify-center h-48 gap-3">
          <Loader2 size={24} className="text-accent animate-spin" />
          <span className="text-slate-400 text-sm">Scanning positions...</span>
        </div>
      )}

      {error && (
        <div className="card p-4 border border-loss/30 bg-loss/5 text-loss text-sm">{error}</div>
      )}

      {data?.alerts.length === 0 && !loading && (
        <div className="flex flex-col items-center justify-center h-48 gap-2 text-slate-500">
          <ShieldAlert size={40} className="text-gain opacity-50" />
          <p className="text-gain font-medium">All clear</p>
          <p className="text-sm">No risk conditions detected across {data?.positions_checked} positions</p>
        </div>
      )}

      {/* Alert groups */}
      {critical.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-xs font-semibold text-loss uppercase tracking-wider flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-loss animate-pulse inline-block" />
            Critical ({critical.length})
          </h2>
          {critical.map(a => <AlertCard key={a.id} alert={a} />)}
        </div>
      )}

      {warnings.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-xs font-semibold text-warn uppercase tracking-wider flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-warn inline-block" />
            Warnings ({warnings.length})
          </h2>
          {warnings.map(a => <AlertCard key={a.id} alert={a} />)}
        </div>
      )}

      {infos.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-xs font-semibold text-accent uppercase tracking-wider flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-accent inline-block" />
            Informational ({infos.length})
          </h2>
          {infos.map(a => <AlertCard key={a.id} alert={a} />)}
        </div>
      )}

      {data && (
        <p className="text-xs text-slate-600 text-center">
          Last scanned: {new Date(data.scanned_at).toLocaleTimeString()}
        </p>
      )}
    </div>
  );
}
