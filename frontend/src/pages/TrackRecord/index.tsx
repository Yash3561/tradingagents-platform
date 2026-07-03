import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { TrendingUp, Brain, Target, Percent, Loader2 } from "lucide-react";
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

interface TrackRecordData {
  total_analyses: number;
  decisions: Record<string, number>;
  avg_confidence: number | null;
  trades: {
    closed: number;
    wins: number;
    win_rate: number | null;
    total_pnl: number;
    avg_win: number | null;
    avg_loss: number | null;
  };
  monthly: { month: string; analyses: number; closed_trades: number; win_rate: number | null }[];
  recent: { ticker: string; decision: string; confidence: number | null; date: string }[];
  disclaimer: string;
}

function Kpi({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: any;
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} className="text-accent" />
        <p className="metric-label">{label}</p>
      </div>
      <p className="metric-value text-2xl">{value}</p>
      {sub && <p className="text-xs text-text-muted mt-1">{sub}</p>}
    </div>
  );
}

function decisionBadge(d: string) {
  if (d === "BUY") return "badge-gain";
  if (d === "SELL") return "badge-loss";
  return "badge-neutral";
}

export default function TrackRecord({ standalone = false }: { standalone?: boolean }) {
  const { data, isLoading } = useQuery<TrackRecordData>({
    queryKey: ["track-record"],
    queryFn: () => api.get("/track-record/").then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });

  const body = isLoading ? (
    <div className="flex items-center justify-center py-24 text-text-muted gap-2">
      <Loader2 size={16} className="animate-spin" /> Loading track record…
    </div>
  ) : !data ? (
    <div className="text-center py-24 text-text-muted">Track record unavailable</div>
  ) : (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi
          icon={Brain}
          label="AI Analyses"
          value={data.total_analyses.toLocaleString()}
          sub="full multi-agent debates"
        />
        <Kpi
          icon={Target}
          label="Closed AI Trades"
          value={data.trades.closed.toLocaleString()}
          sub={`${data.trades.wins} winners`}
        />
        <Kpi
          icon={Percent}
          label="Win Rate"
          value={data.trades.win_rate != null ? `${Math.round(data.trades.win_rate * 100)}%` : "—"}
          sub={
            data.trades.avg_win != null && data.trades.avg_loss != null
              ? `avg win $${data.trades.avg_win} / avg loss $${data.trades.avg_loss}`
              : undefined
          }
        />
        <Kpi
          icon={TrendingUp}
          label="Avg Confidence"
          value={data.avg_confidence != null ? `${Math.round(data.avg_confidence * 100)}%` : "—"}
          sub="only ≥70% may trade"
        />
      </div>

      {/* Decision mix */}
      <div className="card p-6">
        <h2 className="text-sm font-semibold text-text-primary mb-4">Decision Mix</h2>
        <div className="flex gap-3 flex-wrap">
          {["BUY", "HOLD", "SELL"].map((d) => {
            const count = data.decisions[d] ?? 0;
            const total = Object.values(data.decisions).reduce((a, b) => a + b, 0) || 1;
            return (
              <div key={d} className="flex-1 min-w-[140px] bg-bg-elevated rounded-lg p-4 border border-border">
                <div className="flex items-center justify-between mb-2">
                  <span className={cn("text-xs px-2 py-0.5 rounded-full", decisionBadge(d))}>{d}</span>
                  <span className="font-mono text-sm text-text-primary">{count}</span>
                </div>
                <div className="h-1.5 bg-bg-card rounded-full overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded-full",
                      d === "BUY" ? "bg-gain" : d === "SELL" ? "bg-loss" : "bg-warn"
                    )}
                    style={{ width: `${Math.round((count / total) * 100)}%` }}
                  />
                </div>
                <p className="text-2xs text-text-muted mt-1">{Math.round((count / total) * 100)}% of calls</p>
              </div>
            );
          })}
        </div>
        <p className="text-xs text-text-muted mt-4">
          A disciplined AI says HOLD most of the time — trades need 3-of-4 analyst consensus,
          ≥70% confidence, and a 2:1 reward/risk minimum.
        </p>
      </div>

      {/* Monthly */}
      {data.monthly.length > 0 && (
        <div className="card p-6">
          <h2 className="text-sm font-semibold text-text-primary mb-4">Monthly Activity & Win Rate</h2>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data.monthly} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1A2540" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 10, fill: "#64748b" }} axisLine={false} tickLine={false} />
                <YAxis yAxisId="left" allowDecimals={false} tick={{ fontSize: 10, fill: "#64748b" }} axisLine={false} tickLine={false} />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  domain={[0, 1]}
                  tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                  tick={{ fontSize: 10, fill: "#64748b" }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{ background: "#141D30", border: "1px solid #1A2540", borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: "#94a3b8" }}
                  formatter={(value: any, name: string) =>
                    name === "Win rate" ? [`${Math.round(value * 100)}%`, name] : [value, name]
                  }
                />
                <Bar yAxisId="left" dataKey="analyses" name="Analyses" fill="#2D7DD2" radius={[3, 3, 0, 0]} />
                <Line
                  yAxisId="right"
                  dataKey="win_rate"
                  name="Win rate"
                  stroke="#00E676"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  connectNulls
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Recent calls */}
      <div className="card p-6">
        <h2 className="text-sm font-semibold text-text-primary mb-4">Recent AI Calls</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-text-muted border-b border-border">
                <th className="py-2 pr-4 font-medium">Date</th>
                <th className="py-2 pr-4 font-medium">Ticker</th>
                <th className="py-2 pr-4 font-medium">Decision</th>
                <th className="py-2 font-medium">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {data.recent.map((r, i) => (
                <tr key={i} className="border-b border-border/50">
                  <td className="py-2 pr-4 text-xs text-text-muted">{r.date}</td>
                  <td className="py-2 pr-4 font-mono text-text-primary">{r.ticker}</td>
                  <td className="py-2 pr-4">
                    <span className={cn("text-xs px-2 py-0.5 rounded-full", decisionBadge(r.decision))}>
                      {r.decision}
                    </span>
                  </td>
                  <td className="py-2 font-mono text-xs">
                    {r.confidence != null ? `${Math.round(r.confidence * 100)}%` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <p className="text-xs text-text-muted">{data.disclaimer}</p>
    </div>
  );

  if (!standalone) {
    return (
      <motion.div
        key="track-record"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.25 }}
        className="space-y-6"
      >
        <div>
          <h1 className="text-xl font-semibold text-text-primary">AI Track Record</h1>
          <p className="text-sm text-text-muted mt-0.5">
            Every decision the agents make, on the record — this page is public
          </p>
        </div>
        {body}
      </motion.div>
    );
  }

  // Public standalone view (shareable link, no login)
  return (
    <div className="min-h-screen bg-bg-base">
      <header className="border-b border-border bg-bg-surface">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-accent rounded-lg flex items-center justify-center">
              <TrendingUp size={16} className="text-white" />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">TradingAgents</p>
              <p className="text-2xs text-slate-500">AI Track Record — live, unedited</p>
            </div>
          </div>
          <a
            href="/"
            className="px-4 py-2 bg-accent hover:bg-accent/90 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Try it free
          </a>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-6 py-8">{body}</main>
    </div>
  );
}
