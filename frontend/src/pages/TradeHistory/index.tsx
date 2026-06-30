import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronRight, X, Loader2, RefreshCw } from "lucide-react";
import PnLBadge from "../../components/data-display/PnLBadge";
import { fmt } from "../../lib/formatters";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

interface Trade {
  id: string;
  agent_run_id: string | null;
  ticker: string;
  side: string;
  qty: number;
  filled_price: number | null;
  status: string;
  pnl: number | null;
  stop_loss_pct: number | null;
  take_profit_pct: number | null;
  closed_reason: string | null;
  submitted_at: string | null;
  filled_at: string | null;
  closed_at: string | null;
}

interface DebateEntry {
  agent: string;
  role: string;
  content: string;
}

const ROLE_META: Record<string, { color: string }> = {
  analyst: { color: "text-accent-bright" },
  researcher: { color: "text-warn" },
  risk: { color: "text-loss" },
  pm: { color: "text-gain" },
};

const STATUS_STYLE: Record<string, string> = {
  filled: "bg-gain/10 text-gain border-gain/20",
  submitted: "bg-accent/10 text-accent border-accent/20",
  pending: "bg-warn/10 text-warn border-warn/20",
  cancelled: "bg-text-muted/10 text-text-muted border-text-muted/20",
  closed: "bg-bg-elevated text-text-secondary border-border",
};

const CLOSE_REASON_STYLE: Record<string, string> = {
  stop_loss: "text-loss",
  take_profit: "text-gain",
};

function AuditPanel({ trade, onClose }: { trade: Trade; onClose: () => void }) {
  const [entries, setEntries] = useState<DebateEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!trade.agent_run_id) return;
    setLoading(true);
    api.get(`/agents/runs/${trade.agent_run_id}`)
      .then(({ data }) => {
        if (data.debate_log?.length > 0) {
          setEntries(data.debate_log.map((e: any) => ({
            agent: e.agent,
            role: e.role,
            content: e.content,
          })));
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [trade.agent_run_id]);

  const pnlPct = trade.pnl != null && trade.filled_price != null && trade.qty
    ? (trade.pnl / (trade.filled_price * trade.qty)) * 100
    : null;

  return (
    <motion.div
      initial={{ x: "100%" }}
      animate={{ x: 0 }}
      exit={{ x: "100%" }}
      transition={{ type: "spring", damping: 30, stiffness: 300 }}
      className="fixed right-0 top-0 h-full w-[480px] bg-bg-surface border-l border-border shadow-2xl z-50 flex flex-col"
    >
      <div className="flex items-center justify-between p-5 border-b border-border">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono font-bold text-lg text-text-primary">{trade.ticker}</span>
            <span className={cn("text-sm font-semibold uppercase", trade.side === "buy" ? "text-gain" : "text-loss")}>
              {trade.side}
            </span>
            {trade.closed_reason && (
              <span className={cn("text-xs font-medium px-1.5 py-0.5 rounded bg-bg-elevated border border-border",
                CLOSE_REASON_STYLE[trade.closed_reason] ?? "text-text-muted")}>
                {trade.closed_reason.replace("_", " ")}
              </span>
            )}
          </div>
          <p className="text-xs text-text-muted mt-0.5">
            {trade.submitted_at ? new Date(trade.submitted_at).toLocaleString() : "—"}
          </p>
        </div>
        <button onClick={onClose} className="p-2 rounded-lg hover:bg-bg-elevated text-text-muted hover:text-text-primary transition-colors">
          <X size={18} />
        </button>
      </div>

      <div className="flex gap-4 p-5 border-b border-border flex-wrap">
        {[
          ["Qty", trade.qty?.toFixed(4) ?? "—"],
          ["Fill Price", trade.filled_price ? fmt.price(trade.filled_price) : "—"],
          ["P&L", trade.pnl != null ? (
            <span className={cn("font-mono text-sm font-semibold", trade.pnl >= 0 ? "text-gain" : "text-loss")}>
              {trade.pnl >= 0 ? "+" : ""}{fmt.usd(trade.pnl)}
            </span>
          ) : "—"],
          ["Stop", trade.stop_loss_pct ? `${trade.stop_loss_pct}%` : "—"],
          ["Target", trade.take_profit_pct ? `${trade.take_profit_pct}%` : "—"],
        ].map(([label, val]) => (
          <div key={String(label)} className="min-w-[80px]">
            <p className="metric-label mb-1">{label}</p>
            <div className="text-sm font-mono font-semibold text-text-primary">{val}</div>
          </div>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-4">Agent Reasoning</h3>
        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 size={18} className="animate-spin text-accent" />
          </div>
        ) : entries.length > 0 ? (
          <div className="space-y-3">
            {entries.map((r, i) => (
              <div key={i} className={cn("p-3 rounded-lg border text-xs",
                r.role === "analyst" && "bg-accent/5 border-accent/15",
                r.role === "researcher" && "bg-warn/5 border-warn/15",
                r.role === "risk" && "bg-loss/5 border-loss/15",
                r.role === "pm" && "bg-gain/5 border-gain/15",
              )}>
                <span className={cn("font-semibold block mb-1", ROLE_META[r.role]?.color ?? "text-text-primary")}>
                  {r.agent}
                </span>
                <p className="text-text-secondary leading-relaxed whitespace-pre-wrap">{r.content}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-text-muted text-center py-8">
            {trade.agent_run_id ? "No reasoning available" : "No agent run linked to this trade"}
          </p>
        )}
      </div>
    </motion.div>
  );
}

export default function TradeHistory() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [selected, setSelected] = useState<Trade | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setRefreshing(true);
    try {
      const { data } = await api.get("/trades/?limit=100");
      setTrades(data);
    } catch (e) {
      console.error("Trade history load failed", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, []);

  return (
    <motion.div
      key="trades"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-6"
    >
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Trade History</h1>
          <p className="text-sm text-text-muted mt-0.5">Full audit trail with agent reasoning</p>
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

      {loading ? (
        <div className="flex items-center justify-center h-48">
          <Loader2 size={24} className="animate-spin text-accent" />
        </div>
      ) : trades.length === 0 ? (
        <div className="card p-10 text-center">
          <p className="text-sm text-text-muted">No trades yet</p>
          <p className="text-xs text-text-muted mt-1">Run a market scan to auto-execute approved trades</p>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full">
            <thead className="border-b border-border">
              <tr>
                {["Ticker", "Side", "Qty", "Fill Price", "P&L", "Stop / Target", "Status", "Closed", "Time", ""].map(h => (
                  <th key={h} className="metric-label text-left px-4 py-3 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {trades.map(trade => {
                const pnlPct = trade.pnl != null && trade.filled_price && trade.qty
                  ? (trade.pnl / (trade.filled_price * trade.qty)) * 100
                  : null;
                return (
                  <tr key={trade.id} className="hover:bg-bg-elevated/40 transition-colors">
                    <td className="px-4 py-3 font-mono font-bold text-sm text-text-primary">{trade.ticker}</td>
                    <td className="px-4 py-3">
                      <span className={cn("text-xs font-semibold uppercase", trade.side === "buy" ? "text-gain" : "text-loss")}>
                        {trade.side}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-sm text-text-secondary">{trade.qty?.toFixed(4) ?? "—"}</td>
                    <td className="px-4 py-3 font-mono text-sm text-text-primary">
                      {trade.filled_price ? fmt.price(trade.filled_price) : "—"}
                    </td>
                    <td className="px-4 py-3">
                      {trade.pnl != null ? (
                        <div className="flex items-center gap-1.5">
                          {pnlPct != null && <PnLBadge value={pnlPct} />}
                          <span className={cn("text-xs font-mono", trade.pnl >= 0 ? "text-gain" : "text-loss")}>
                            {trade.pnl >= 0 ? "+" : ""}{fmt.usd(trade.pnl)}
                          </span>
                        </div>
                      ) : <span className="text-xs text-text-muted">—</span>}
                    </td>
                    <td className="px-4 py-3 text-xs font-mono">
                      {trade.stop_loss_pct ? (
                        <span className="text-loss/70">-{trade.stop_loss_pct}%</span>
                      ) : "—"}
                      {" / "}
                      {trade.take_profit_pct ? (
                        <span className="text-gain/70">+{trade.take_profit_pct}%</span>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn("text-xs px-2 py-0.5 rounded-md border capitalize",
                        STATUS_STYLE[trade.status] ?? "bg-bg-elevated text-text-muted border-border")}>
                        {trade.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {trade.closed_reason ? (
                        <span className={cn("text-xs font-medium", CLOSE_REASON_STYLE[trade.closed_reason] ?? "text-text-muted")}>
                          {trade.closed_reason.replace("_", " ")}
                        </span>
                      ) : <span className="text-xs text-text-muted">—</span>}
                    </td>
                    <td className="px-4 py-3 text-xs text-text-muted">
                      {trade.submitted_at
                        ? new Date(trade.submitted_at).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
                        : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setSelected(trade)}
                        className="flex items-center gap-1 text-xs text-accent-bright hover:underline"
                      >
                        View <ChevronRight size={12} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <AnimatePresence>
        {selected && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/50 z-40"
              onClick={() => setSelected(null)}
            />
            <AuditPanel trade={selected} onClose={() => setSelected(null)} />
          </>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
