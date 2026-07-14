import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "../../lib/cn";
import { DUR, EASE } from "../../lib/motion";
import EmptyState from "../ui/EmptyState";
import {
  LineChart, MessageSquare, Newspaper, BarChart2,
  Users, Shield, TrendingUp,
} from "lucide-react";

export interface DebateEntry {
  agent: string;
  role: string;
  content: string;
  timestamp?: string;
}

const ROLE_META: Record<string, { color: string; bg: string; Icon: React.ElementType }> = {
  analyst: { color: "text-accent-bright", bg: "bg-accent/10 border-accent/20", Icon: LineChart },
  researcher: { color: "text-warn", bg: "bg-warn/10 border-warn/20", Icon: Users },
  risk: { color: "text-loss", bg: "bg-loss/10 border-loss/20", Icon: Shield },
  pm: { color: "text-gain", bg: "bg-gain/10 border-gain/20", Icon: TrendingUp },
};

const AGENT_ICONS: Record<string, React.ElementType> = {
  "Technical Analyst": LineChart,
  "Sentiment Analyst": MessageSquare,
  "News Analyst": Newspaper,
  "Fundamental Analyst": BarChart2,
  "Bull Researcher": Users,
  "Bear Researcher": Users,
  "Researcher Team": Users,
  "Risk Manager": Shield,
  "Portfolio Manager": TrendingUp,
};

interface DebateTimelineProps {
  entries: DebateEntry[];
  /** True while a run is streaming — shows a typing indicator and auto-scrolls. */
  running?: boolean;
}

function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: DUR.fast, ease: EASE }}
      className="flex items-center gap-3 p-4 rounded-xl border border-border bg-bg-elevated/50"
    >
      <div className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center bg-bg-card border border-border">
        <Users size={14} className="text-accent-bright" />
      </div>
      <div className="flex items-center gap-1.5">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-accent-bright"
            animate={{ opacity: [0.25, 1, 0.25] }}
            transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
          />
        ))}
        <span className="ml-2 text-xs text-text-muted">agents deliberating…</span>
      </div>
    </motion.div>
  );
}

export default function DebateTimeline({ entries, running = false }: DebateTimelineProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Keep the newest message in view while a run streams
  useEffect(() => {
    if (!running || !scrollRef.current) return;
    scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [entries.length, running]);

  return (
    <div ref={scrollRef} className="flex flex-col gap-3 overflow-y-auto max-h-[600px] pr-1">
      <AnimatePresence initial={false}>
        {entries.map((entry, i) => {
          const meta = ROLE_META[entry.role] ?? ROLE_META.analyst;
          const Icon = AGENT_ICONS[entry.agent] ?? LineChart;

          return (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: DUR.base, ease: EASE }}
              className={cn("flex gap-3 p-4 rounded-xl border", meta.bg)}
            >
              <div className={cn("shrink-0 w-8 h-8 rounded-lg flex items-center justify-center bg-bg-card border border-border mt-0.5")}>
                <Icon size={14} className={meta.color} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1.5">
                  <span className={cn("text-xs font-semibold", meta.color)}>{entry.agent}</span>
                  <span className="text-2xs text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded capitalize">{entry.role}</span>
                  {entry.timestamp && (
                    <span className="text-2xs text-text-muted ml-auto">{entry.timestamp}</span>
                  )}
                </div>
                <p className="text-xs text-text-secondary leading-relaxed">{entry.content}</p>
              </div>
            </motion.div>
          );
        })}
        {running && <TypingIndicator key="typing" />}
      </AnimatePresence>

      {entries.length === 0 && !running && (
        <EmptyState
          icon={<Users size={20} />}
          title="Debate will appear here"
          description="Run an analysis and watch the agents argue in real time."
          className="py-16"
        />
      )}
    </div>
  );
}
