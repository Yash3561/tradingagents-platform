import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronRight, X } from "lucide-react";
import PnLBadge from "../../components/data-display/PnLBadge";
import { fmt } from "../../lib/formatters";
import { cn } from "../../lib/cn";

const TRADES = [
  {
    id: "t1", ticker: "NVDA", side: "buy", qty: 20, filled_price: 128.40, pnl: 59.60, pct: 2.32,
    status: "filled", submitted_at: "2025-06-28 10:32 AM",
    reasoning: [
      { agent: "Technical Analyst", role: "analyst", content: "RSI(14)=58, MACD bullish crossover on 4H chart. 50-SMA acting as dynamic support at $127.20." },
      { agent: "Fundamental Analyst", role: "analyst", content: "NVDA forward P/E of 38x justified by 85% YoY data center revenue growth. Gross margin expansion to 78.4%." },
      { agent: "Sentiment Analyst", role: "analyst", content: "Institutional flow +$2.1B over 5 days. Put/call ratio at 0.72 (bullish). StockTwits sentiment score: 0.81." },
      { agent: "News Analyst", role: "analyst", content: "Blackwell GPU demand commentary from management confirms supercycle thesis. No negative headlines in last 48 hours." },
      { agent: "Bull Researcher", role: "researcher", content: "Conviction BUY. AI capex cycle intact. NVDA pricing power remains unmatched in accelerated compute." },
      { agent: "Bear Researcher", role: "researcher", content: "Valuation premium requires perfect execution. Export restriction risk from US-China tensions remains tail risk." },
      { agent: "Risk Manager", role: "risk", content: "Position size approved: 1.5% portfolio weight. Stop-loss recommended at $118.00 (-8%). VaR contribution within limits." },
      { agent: "Portfolio Manager", role: "pm", content: "Approved BUY 20 shares NVDA at market. Risk/reward: 3.2x at $145 target. Confidence: 84%." },
    ],
  },
  {
    id: "t2", ticker: "TSLA", side: "buy", qty: 15, filled_price: 280.00, pnl: -402.30, pct: -9.58,
    status: "filled", submitted_at: "2025-06-20 09:15 AM",
    reasoning: [
      { agent: "Technical Analyst", role: "analyst", content: "Breakout above $275 resistance with volume confirmation. Target $310." },
      { agent: "Fundamental Analyst", role: "analyst", content: "Vehicle delivery beat expected. Energy business growing 40% YoY." },
      { agent: "Risk Manager", role: "risk", content: "High beta position (β=1.8). Maximum allocation 1% portfolio. Stop-loss $258." },
      { agent: "Portfolio Manager", role: "pm", content: "Approved BUY 15 shares TSLA. Confidence: 61%. Tight stop in place." },
    ],
  },
];

function AuditPanel({ trade, onClose }: { trade: typeof TRADES[0]; onClose: () => void }) {
  const ROLE_META: Record<string, { color: string }> = {
    analyst: { color: "text-accent-bright" },
    researcher: { color: "text-warn" },
    risk: { color: "text-loss" },
    pm: { color: "text-gain" },
  };

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
            <span className={cn("text-sm font-semibold capitalize", trade.side === "buy" ? "text-gain" : "text-loss")}>{trade.side.toUpperCase()}</span>
          </div>
          <p className="text-xs text-text-muted mt-0.5">{trade.submitted_at}</p>
        </div>
        <button onClick={onClose} className="p-2 rounded-lg hover:bg-bg-elevated text-text-muted hover:text-text-primary transition-colors">
          <X size={18} />
        </button>
      </div>

      <div className="flex gap-4 p-5 border-b border-border">
        {[
          ["Qty", trade.qty],
          ["Fill Price", fmt.price(trade.filled_price)],
          ["P&L", <PnLBadge value={trade.pct} />],
        ].map(([label, val]) => (
          <div key={String(label)}>
            <p className="metric-label mb-1">{label}</p>
            <div className="text-sm font-mono font-semibold text-text-primary">{val}</div>
          </div>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-4">Agent Reasoning</h3>
        <div className="space-y-3">
          {trade.reasoning.map((r, i) => (
            <div key={i} className={cn("p-3 rounded-lg border text-xs",
              r.role === "analyst" && "bg-accent/5 border-accent/15",
              r.role === "researcher" && "bg-warn/5 border-warn/15",
              r.role === "risk" && "bg-loss/5 border-loss/15",
              r.role === "pm" && "bg-gain/5 border-gain/15",
            )}>
              <span className={cn("font-semibold block mb-1", ROLE_META[r.role]?.color)}>{r.agent}</span>
              <p className="text-text-secondary leading-relaxed">{r.content}</p>
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}

export default function TradeHistory() {
  const [selected, setSelected] = useState<typeof TRADES[0] | null>(null);

  return (
    <motion.div
      key="trades"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-6"
    >
      <div>
        <h1 className="text-xl font-semibold text-text-primary">Trade History</h1>
        <p className="text-sm text-text-muted mt-0.5">Full audit trail with agent reasoning</p>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full">
          <thead className="border-b border-border">
            <tr>
              {["Ticker", "Side", "Qty", "Fill Price", "P&L", "Status", "Time", "Reasoning"].map(h => (
                <th key={h} className="metric-label text-left px-5 py-3 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {TRADES.map(trade => (
              <tr key={trade.id} className="hover:bg-bg-elevated/40 transition-colors">
                <td className="px-5 py-4 font-mono font-bold text-sm text-text-primary">{trade.ticker}</td>
                <td className="px-5 py-4">
                  <span className={cn("text-xs font-semibold uppercase", trade.side === "buy" ? "text-gain" : "text-loss")}>{trade.side}</span>
                </td>
                <td className="px-5 py-4 font-mono text-sm text-text-secondary">{trade.qty}</td>
                <td className="px-5 py-4 font-mono text-sm text-text-primary">{fmt.price(trade.filled_price)}</td>
                <td className="px-5 py-4"><PnLBadge value={trade.pct} /></td>
                <td className="px-5 py-4">
                  <span className="text-xs px-2 py-1 rounded-md bg-gain-bg text-gain border border-gain/20 capitalize">{trade.status}</span>
                </td>
                <td className="px-5 py-4 text-xs text-text-muted">{trade.submitted_at}</td>
                <td className="px-5 py-4">
                  <button
                    onClick={() => setSelected(trade)}
                    className="flex items-center gap-1 text-xs text-accent-bright hover:underline"
                  >
                    View <ChevronRight size={12} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

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
