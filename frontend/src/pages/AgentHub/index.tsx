import { useState, useRef, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Play, RefreshCw, Loader2 } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { api, WS_BASE } from "../../lib/api";
import AgentFlow, { type FlowState, type AgentStatus } from "../../components/agent/AgentFlow";
import DebateTimeline, { type DebateEntry } from "../../components/agent/DebateTimeline";
import { cn } from "../../lib/cn";

const ROLE_TO_KEY: Record<string, keyof FlowState> = {
  "Technical Analyst": "technical",
  "Sentiment Analyst": "sentiment",
  "News Analyst": "news",
  "Fundamental Analyst": "fundamental",
  "Researcher Team": "researcher",
  "Bull Researcher": "researcher",
  "Bear Researcher": "researcher",
  "Risk Manager": "risk",
  "Portfolio Manager": "pm",
};

const DEFAULT_FLOW: FlowState = {
  technical: "idle", sentiment: "idle", news: "idle",
  fundamental: "idle", researcher: "idle", risk: "idle", pm: "idle",
};

const DECISION_STYLE: Record<string, string> = {
  BUY: "text-gain border-gain/40 bg-gain/5 shadow-[0_0_20px_rgba(0,230,118,0.15)]",
  SELL: "text-loss border-loss/40 bg-loss/5 shadow-[0_0_20px_rgba(255,61,87,0.15)]",
  HOLD: "text-warn border-warn/40 bg-warn/5",
};

function debateLogToEntries(log: any[], completedAt?: string | null): DebateEntry[] {
  // Anchor timestamps to the actual run completion time, not the current page-load time.
  // If completedAt is unavailable (live run), fall back to now.
  const base = completedAt ? new Date(completedAt).getTime() : Date.now();
  return log.map((e, i) => ({
    agent: e.agent,
    role: e.role,
    content: e.content,
    timestamp: new Date(base - (log.length - i) * 8000)
      .toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }),
  }));
}

export default function AgentHub() {
  const [searchParams] = useSearchParams();
  const [ticker, setTicker] = useState(searchParams.get("ticker")?.toUpperCase() || "AAPL");
  const [debateRounds, setDebateRounds] = useState(2);
  const [status, setStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [flowState, setFlowState] = useState<FlowState>(DEFAULT_FLOW);
  const [entries, setEntries] = useState<DebateEntry[]>([]);
  const [decision, setDecision] = useState<{ d: string; confidence: number; summary: string } | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const runIdRef = useRef<string | null>(null);
  const statusRef = useRef<"idle" | "running" | "done" | "error">("idle");

  const updateAgent = useCallback((agentName: string, s: AgentStatus) => {
    const key = ROLE_TO_KEY[agentName];
    if (key) setFlowState(prev => ({ ...prev, [key]: s }));
  }, []);

  const setStatusBoth = (s: "idle" | "running" | "done" | "error") => {
    setStatus(s);
    statusRef.current = s;
  };

  // Restore last completed run from DB on mount
  useEffect(() => {
    api.get("/agents/runs?limit=1").then(({ data }) => {
      const last = data[0];
      if (!last || last.status !== "completed") return;
      api.get(`/agents/runs/${last.run_id}`).then(({ data: result }) => {
        if (result.status === "completed" && result.decision) {
          setTicker(result.ticker);
          setDecision({ d: result.decision, confidence: result.confidence, summary: result.summary });
          setFlowState({ technical: "done", sentiment: "done", news: "done", fundamental: "done", researcher: "done", risk: "done", pm: "done" });
          if (result.debate_log?.length > 0) setEntries(debateLogToEntries(result.debate_log, result.completed_at));
          setStatusBoth("done");
        }
      }).catch(() => {});
    }).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleRun = async () => {
    if (statusRef.current === "running") return;

    setStatusBoth("running");
    setFlowState(DEFAULT_FLOW);
    setEntries([]);
    setDecision(null);

    try {
      const { data } = await api.post("/agents/run", {
        ticker: ticker.toUpperCase(),
        debate_rounds: debateRounds,
      });

      runIdRef.current = data.run_id;

      // Open WebSocket for live events
      const ws = new WebSocket(`${WS_BASE}/runs/${data.run_id}`);
      wsRef.current = ws;

      ws.onmessage = async (e) => {
        const msg = JSON.parse(e.data);

        if (msg.type === "status" && msg.status === "running") {
          ["Technical Analyst", "Sentiment Analyst", "News Analyst", "Fundamental Analyst"].forEach(a =>
            updateAgent(a, "running")
          );
        }

        if (msg.type === "agent_start") {
          updateAgent(msg.agent, "running");
          // Mark previous stage done
          if (msg.role === "researcher") {
            ["technical", "sentiment", "news", "fundamental"].forEach(k =>
              setFlowState(prev => ({ ...prev, [k as keyof FlowState]: "done" }))
            );
          }
          if (msg.role === "risk") setFlowState(prev => ({ ...prev, researcher: "done" }));
          if (msg.role === "pm") setFlowState(prev => ({ ...prev, risk: "done" }));
        }

        if (msg.type === "debate_event") {
          // Mark agent done when its report arrives (gives sequential green checkmarks)
          updateAgent(msg.agent, "done");
          setEntries(prev => [...prev, {
            agent: msg.agent,
            role: msg.role,
            content: msg.content,
            timestamp: new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }),
          }]);
        }

        if (msg.type === "completed") {
          setFlowState({
            technical: "done", sentiment: "done", news: "done",
            fundamental: "done", researcher: "done", risk: "done", pm: "done",
          });
          setDecision({ d: msg.decision, confidence: msg.confidence, summary: msg.summary });
          setStatusBoth("done");

          // Always populate debate panel from the full log (handles race where WS events arrived
          // before the connection was established, or were missed)
          if (msg.debate_log && msg.debate_log.length > 0) {
            // Live run just completed — anchor to now (the run finished moments ago)
            setEntries(debateLogToEntries(msg.debate_log, new Date().toISOString()));
          } else {
            // Fallback: fetch from API
            try {
              const { data: result } = await api.get(`/agents/runs/${data.run_id}`);
              if (result.debate_log?.length > 0) {
                setEntries(debateLogToEntries(result.debate_log, result.completed_at));
              }
            } catch {}
          }

          ws.close();
        }

        if (msg.type === "error") {
          setStatusBoth("error");
          ws.close();
        }
      };

      ws.onerror = () => setStatusBoth("error");

      ws.onclose = () => {
        // If WS closes and we never got "completed", poll for result
        if (statusRef.current === "running") {
          pollForResult(data.run_id);
        }
      };

    } catch {
      setStatusBoth("error");
    }
  };

  const pollForResult = async (runId: string, attempts = 0) => {
    if (statusRef.current !== "running" || attempts > 60) return;
    try {
      const { data: result } = await api.get(`/agents/runs/${runId}`);
      if (result.status === "completed") {
        setFlowState({
          technical: "done", sentiment: "done", news: "done",
          fundamental: "done", researcher: "done", risk: "done", pm: "done",
        });
        if (result.debate_log?.length > 0) {
          setEntries(debateLogToEntries(result.debate_log, result.completed_at));
        }
        setDecision({ d: result.decision, confidence: result.confidence, summary: result.summary });
        setStatusBoth("done");
      } else if (result.status === "failed") {
        setStatusBoth("error");
      } else {
        // Still running — poll again in 5s
        setTimeout(() => pollForResult(runId, attempts + 1), 5000);
      }
    } catch {
      setTimeout(() => pollForResult(runId, attempts + 1), 5000);
    }
  };

  const handleReset = () => {
    wsRef.current?.close();
    setStatusBoth("idle");
    setFlowState(DEFAULT_FLOW);
    setEntries([]);
    setDecision(null);
  };

  return (
    <motion.div
      key="agent-hub"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-6"
    >
      <div>
        <h1 className="text-xl font-semibold text-text-primary">Agent Hub</h1>
        <p className="text-sm text-text-muted mt-0.5">Multi-agent debate visualization</p>
      </div>

      {/* Controls */}
      <div className="card p-5 flex items-end gap-4">
        <div className="flex-1 max-w-xs">
          <label className="metric-label block mb-2">Ticker</label>
          <input
            value={ticker}
            onChange={e => setTicker(e.target.value.toUpperCase())}
            placeholder="AAPL"
            className="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg
                       text-text-primary font-mono font-semibold text-sm placeholder:text-text-muted
                       focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 transition-colors"
          />
        </div>

        <div>
          <label className="metric-label block mb-2">Debate Rounds</label>
          <select
            value={debateRounds}
            onChange={e => setDebateRounds(+e.target.value)}
            className="px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary
                       focus:outline-none focus:border-accent transition-colors"
          >
            {[1, 2, 3].map(n => <option key={n} value={n}>{n} round{n > 1 ? "s" : ""}</option>)}
          </select>
        </div>

        <button
          onClick={handleRun}
          disabled={status === "running"}
          className={cn(
            "flex items-center gap-2 px-5 py-2 rounded-lg font-semibold text-sm transition-all duration-200",
            status === "running"
              ? "bg-accent/20 text-accent cursor-not-allowed"
              : "bg-accent hover:bg-accent/80 text-white shadow-[0_0_20px_rgba(45,125,210,0.4)]",
          )}
        >
          {status === "running" ? (
            <><Loader2 size={16} className="animate-spin" /> Running...</>
          ) : (
            <><Play size={16} /> Run Analysis</>
          )}
        </button>

        {status !== "idle" && (
          <button
            onClick={handleReset}
            className="p-2 rounded-lg border border-border hover:bg-bg-elevated text-text-muted hover:text-text-primary transition-colors"
          >
            <RefreshCw size={16} />
          </button>
        )}
      </div>

      <div className="grid grid-cols-5 gap-4">
        {/* Agent Flow diagram */}
        <div className="col-span-2 card p-5">
          <h2 className="text-sm font-semibold text-text-primary mb-1">Agent Pipeline</h2>
          <p className="text-xs text-text-muted mb-4">
            {status === "idle" && "Waiting for analysis"}
            {status === "running" && `Analyzing ${ticker}... (~2 min)`}
            {status === "done" && `Analysis complete for ${ticker}`}
            {status === "error" && "Analysis failed — check API key / credits"}
          </p>
          <AgentFlow state={flowState} />

          {/* Decision card */}
          <AnimatePresence>
            {decision && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={cn(
                  "mt-6 p-4 rounded-xl border-2",
                  DECISION_STYLE[decision.d] ?? "text-text-primary border-border bg-bg-elevated"
                )}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium uppercase tracking-widest opacity-60">Final Decision</span>
                  <span className="text-xs font-mono opacity-70">{Math.round(decision.confidence * 100)}% confidence</span>
                </div>
                <p className="text-2xl font-bold font-mono">{decision.d}</p>
                <p className="text-xs mt-2 opacity-75 leading-relaxed">{decision.summary}</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Debate timeline */}
        <div className="col-span-3 card p-5 flex flex-col">
          <h2 className="text-sm font-semibold text-text-primary mb-4">
            Agent Debate
            {entries.length > 0 && (
              <span className="ml-2 text-xs text-text-muted font-normal">{entries.length} messages</span>
            )}
          </h2>
          <DebateTimeline entries={entries} />
        </div>
      </div>
    </motion.div>
  );
}
