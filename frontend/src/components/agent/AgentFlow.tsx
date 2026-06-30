import { motion, AnimatePresence } from "framer-motion";
import { cn } from "../../lib/cn";
import {
  LineChart, MessageSquare, Newspaper, BarChart2,
  Users, Shield, TrendingUp, CheckCircle, XCircle, Loader2,
} from "lucide-react";

export type AgentStatus = "idle" | "running" | "done" | "error";

export interface AgentNodeState {
  status: AgentStatus;
  role: string;
}

export interface FlowState {
  technical: AgentStatus;
  sentiment: AgentStatus;
  news: AgentStatus;
  fundamental: AgentStatus;
  researcher: AgentStatus;
  risk: AgentStatus;
  pm: AgentStatus;
}

interface AgentNodeProps {
  label: string;
  sublabel: string;
  icon: React.ElementType;
  status: AgentStatus;
  delay?: number;
}

function AgentNode({ label, sublabel, icon: Icon, status, delay = 0 }: AgentNodeProps) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay, duration: 0.3 }}
      className={cn(
        "relative flex flex-col items-center gap-2 p-4 rounded-xl border w-28 transition-all duration-500",
        status === "idle" && "bg-bg-card border-border text-text-muted",
        status === "running" && "bg-accent-muted border-accent text-accent-bright shadow-accent-glow",
        status === "done" && "bg-gain-bg border-gain/40 text-gain",
        status === "error" && "bg-loss-bg border-loss/40 text-loss",
      )}
    >
      {/* Pulse ring when running */}
      {status === "running" && (
        <motion.div
          className="absolute inset-0 rounded-xl border-2 border-accent"
          animate={{ opacity: [0.6, 0, 0.6], scale: [1, 1.06, 1] }}
          transition={{ duration: 1.5, repeat: Infinity }}
        />
      )}

      <div className={cn(
        "w-9 h-9 rounded-lg flex items-center justify-center",
        status === "idle" && "bg-bg-elevated",
        status === "running" && "bg-accent/20",
        status === "done" && "bg-gain/10",
        status === "error" && "bg-loss/10",
      )}>
        {status === "running" ? (
          <Loader2 size={18} className="animate-spin" />
        ) : status === "done" ? (
          <CheckCircle size={18} />
        ) : status === "error" ? (
          <XCircle size={18} />
        ) : (
          <Icon size={18} />
        )}
      </div>

      <div className="text-center">
        <p className="text-xs font-semibold leading-tight">{label}</p>
        <p className="text-2xs text-text-muted mt-0.5">{sublabel}</p>
      </div>
    </motion.div>
  );
}

function Arrow({ active }: { active: boolean }) {
  return (
    <div className="flex items-center justify-center w-8">
      <motion.div
        className={cn("h-px w-full transition-colors duration-500", active ? "bg-accent" : "bg-border")}
        animate={active ? { scaleX: [0, 1] } : {}}
        transition={{ duration: 0.4 }}
      />
      <div className={cn("w-0 h-0 border-y-4 border-y-transparent border-l-4 transition-colors duration-500 shrink-0 -ml-0.5",
        active ? "border-l-accent" : "border-l-border")} />
    </div>
  );
}

function VerticalArrow({ active }: { active: boolean }) {
  return (
    <div className="flex flex-col items-center h-8 justify-center">
      <div className={cn("w-px h-full transition-colors duration-500", active ? "bg-accent" : "bg-border")} />
      <div className={cn("w-0 h-0 border-x-4 border-x-transparent border-t-4 transition-colors duration-500 shrink-0 -mt-0.5",
        active ? "border-t-accent" : "border-t-border")} />
    </div>
  );
}

interface AgentFlowProps {
  state: FlowState;
}

const DEFAULT_STATE: FlowState = {
  technical: "idle", sentiment: "idle", news: "idle",
  fundamental: "idle", researcher: "idle", risk: "idle", pm: "idle",
};

export default function AgentFlow({ state = DEFAULT_STATE }: AgentFlowProps) {
  const analystsDone = ["done", "error"].includes(state.technical) &&
    ["done", "error"].includes(state.sentiment) &&
    ["done", "error"].includes(state.news) &&
    ["done", "error"].includes(state.fundamental);

  const researcherDone = ["done", "error"].includes(state.researcher);
  const riskDone = ["done", "error"].includes(state.risk);

  return (
    <div className="flex flex-col items-center gap-6 py-6 select-none">
      {/* Analyst layer */}
      <div className="flex items-center gap-3">
        <AgentNode label="Technical" sublabel="Analyst" icon={LineChart} status={state.technical} delay={0} />
        <AgentNode label="Sentiment" sublabel="Analyst" icon={MessageSquare} status={state.sentiment} delay={0.1} />
        <AgentNode label="News" sublabel="Analyst" icon={Newspaper} status={state.news} delay={0.2} />
        <AgentNode label="Fundamental" sublabel="Analyst" icon={BarChart2} status={state.fundamental} delay={0.3} />
      </div>

      {/* Analysts → Researcher */}
      <VerticalArrow active={analystsDone} />

      {/* Researcher */}
      <AgentNode label="Researcher" sublabel="Bull vs Bear" icon={Users} status={state.researcher} delay={0.4} />

      {/* Researcher → Risk */}
      <VerticalArrow active={researcherDone} />

      {/* Risk Manager */}
      <AgentNode label="Risk Mgr" sublabel="Portfolio Risk" icon={Shield} status={state.risk} delay={0.5} />

      {/* Risk → PM */}
      <VerticalArrow active={riskDone} />

      {/* Portfolio Manager */}
      <AgentNode label="Portfolio" sublabel="Manager" icon={TrendingUp} status={state.pm} delay={0.6} />
    </div>
  );
}
