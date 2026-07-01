import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Calendar, Loader2, RefreshCw } from "lucide-react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

// ── Types ─────────────────────────────────────────────────────────────────────

type EventType = "FOMC" | "CPI" | "NFP" | "EARNINGS";
type ImpactLevel = "HIGH" | "MEDIUM";

interface CalendarEvent {
  date: string; // "2026-07-15"
  type: EventType;
  title: string;
  ticker: string | null;
  impact: ImpactLevel;
  description: string;
}

interface DateGroup {
  dateKey: string;      // ISO "2026-07-15"
  label: string;        // "Today", "Tomorrow", "Mon Jul 7"
  isToday: boolean;
  events: CalendarEvent[];
}

// ── Constants ─────────────────────────────────────────────────────────────────

const TYPE_CONFIG: Record<EventType, { label: string; color: string; bg: string; border: string }> = {
  FOMC: {
    label: "FOMC",
    color: "text-accent",
    bg: "bg-accent/10",
    border: "border-accent/30",
  },
  CPI: {
    label: "CPI",
    color: "text-warn",
    bg: "bg-warn/10",
    border: "border-warn/30",
  },
  NFP: {
    label: "NFP",
    color: "text-warn",
    bg: "bg-warn/10",
    border: "border-warn/30",
  },
  EARNINGS: {
    label: "EPS",
    color: "text-slate-300",
    bg: "bg-slate-700/40",
    border: "border-slate-600/40",
  },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function tomorrowISO(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

function formatDateLabel(iso: string): string {
  const today = todayISO();
  const tomorrow = tomorrowISO();
  if (iso === today) return "Today";
  if (iso === tomorrow) return "Tomorrow";
  // "Mon Jul 7"
  const [year, month, day] = iso.split("-").map(Number);
  const d = new Date(year, month - 1, day);
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function daysFromNow(iso: string): number {
  const today = new Date(todayISO());
  const target = new Date(iso);
  return Math.round((target.getTime() - today.getTime()) / 86400000);
}

function groupByDate(events: CalendarEvent[]): DateGroup[] {
  const map = new Map<string, CalendarEvent[]>();
  for (const ev of events) {
    const arr = map.get(ev.date) ?? [];
    arr.push(ev);
    map.set(ev.date, arr);
  }
  const today = todayISO();
  return Array.from(map.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([dateKey, evs]) => ({
      dateKey,
      label: formatDateLabel(dateKey),
      isToday: dateKey === today,
      events: evs,
    }));
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <div className="card p-4 animate-pulse">
      <div className="flex items-center gap-4">
        <div className="w-12 h-5 rounded bg-bg-elevated" />
        <div className="flex-1 space-y-2">
          <div className="w-40 h-4 rounded bg-bg-elevated" />
          <div className="w-64 h-3 rounded bg-bg-elevated" />
        </div>
        <div className="w-16 h-4 rounded bg-bg-elevated" />
      </div>
    </div>
  );
}

function ImpactDot({ impact }: { impact: ImpactLevel }) {
  return (
    <span
      className={cn(
        "inline-block w-2 h-2 rounded-full shrink-0",
        impact === "HIGH" ? "bg-loss" : "bg-warn"
      )}
      title={`${impact} impact`}
    />
  );
}

function EventRow({ event, isToday }: { event: CalendarEvent; isToday: boolean }) {
  const cfg = TYPE_CONFIG[event.type];
  const days = daysFromNow(event.date);
  const isSoon = days >= 0 && days <= 3;

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn(
        "card p-4 flex items-center gap-4",
        isToday && "border-l-2 border-l-accent"
      )}
    >
      {/* Type badge */}
      <span
        className={cn(
          "shrink-0 text-[11px] font-bold font-mono px-2 py-0.5 rounded border",
          cfg.color,
          cfg.bg,
          cfg.border
        )}
      >
        {cfg.label}
      </span>

      {/* Title + description */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-semibold text-white">{event.title}</span>
          {isSoon && days > 0 && (
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-warn/15 text-warn border border-warn/25">
              Soon
            </span>
          )}
          {days === 0 && (
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-accent/15 text-accent border border-accent/25">
              Today
            </span>
          )}
        </div>
        <p className="text-xs text-slate-400 mt-0.5 leading-relaxed line-clamp-1">
          {event.description}
        </p>
      </div>

      {/* Right: ticker pill + impact */}
      <div className="shrink-0 flex items-center gap-2">
        {event.ticker && (
          <span className="font-mono text-xs bg-accent/10 border border-accent/25 text-accent px-2 py-0.5 rounded">
            {event.ticker}
          </span>
        )}
        <div className="flex items-center gap-1.5">
          <ImpactDot impact={event.impact} />
          <span
            className={cn(
              "text-[10px] font-semibold uppercase tracking-wide",
              event.impact === "HIGH" ? "text-loss" : "text-warn"
            )}
          >
            {event.impact}
          </span>
        </div>
      </div>
    </motion.div>
  );
}

function DateSection({ group }: { group: DateGroup }) {
  return (
    <div className="space-y-2">
      {/* Date header */}
      <div className="flex items-center gap-3">
        <h2
          className={cn(
            "text-xs font-semibold uppercase tracking-widest",
            group.isToday ? "text-accent" : "text-slate-500"
          )}
        >
          {group.label}
        </h2>
        <div className="flex-1 h-px bg-border" />
        <span className="text-[10px] text-slate-600 font-mono">{group.dateKey}</span>
      </div>

      {/* Events */}
      <div className="space-y-2">
        {group.events.map((ev, i) => (
          <EventRow key={`${ev.date}-${ev.type}-${ev.ticker ?? i}`} event={ev} isToday={group.isToday} />
        ))}
      </div>
    </div>
  );
}

function TickerChip({
  ticker,
  selected,
  onClick,
}: {
  ticker: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "px-3 py-1 rounded-full text-xs font-mono font-semibold border transition-all duration-150",
        selected
          ? "bg-accent/15 border-accent text-accent"
          : "bg-bg-elevated border-border text-slate-400 hover:border-slate-500 hover:text-slate-300"
      )}
    >
      {ticker}
    </button>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function EconomicCalendar() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Watchlist state
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [selectedTickers, setSelectedTickers] = useState<Set<string>>(new Set());

  // Load watchlist tickers from settings
  useEffect(() => {
    api
      .get("/settings/watchlist")
      .then(({ data }) => {
        const tickers: string[] = Array.isArray(data) ? data : data?.tickers ?? [];
        setWatchlist(tickers);
      })
      .catch(() => {
        // Non-fatal — proceed without watchlist
      });
  }, []);

  const fetchCalendar = useCallback(async (tickers: Set<string>) => {
    setLoading(true);
    setError(null);
    try {
      const tickerParam = Array.from(tickers).join(",");
      const { data } = await api.get<CalendarEvent[]>("/market/calendar", {
        params: tickerParam ? { tickers: tickerParam } : {},
      });
      setEvents(data);
    } catch (e: any) {
      setError(e.response?.data?.detail ?? "Failed to load calendar");
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch when selectedTickers changes
  useEffect(() => {
    fetchCalendar(selectedTickers);
  }, [fetchCalendar, selectedTickers]);

  const toggleTicker = (ticker: string) => {
    setSelectedTickers((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) {
        next.delete(ticker);
      } else {
        next.add(ticker);
      }
      return next;
    });
  };

  const selectAll = () => setSelectedTickers(new Set());

  const groups = groupByDate(events);
  const isAllMode = selectedTickers.size === 0;

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto">
      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Calendar size={22} className="text-accent shrink-0" />
          <div>
            <h1 className="text-xl font-bold text-white">Economic Calendar</h1>
            <p className="text-sm text-slate-400">Upcoming market-moving events</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="badge-neutral text-xs px-3 py-1 rounded-full font-medium">
            Next 90 days
          </span>
          <button
            onClick={() => fetchCalendar(selectedTickers)}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 bg-accent/10 hover:bg-accent/20 border border-accent/30 text-accent rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
          >
            {loading ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <RefreshCw size={13} />
            )}
            Refresh
          </button>
        </div>
      </div>

      {/* ── Ticker filter chips ── */}
      {watchlist.length > 0 && (
        <div className="card p-4">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-3">
            Filter by watchlist ticker
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={selectAll}
              className={cn(
                "px-3 py-1 rounded-full text-xs font-semibold border transition-all duration-150",
                isAllMode
                  ? "bg-accent/15 border-accent text-accent"
                  : "bg-bg-elevated border-border text-slate-400 hover:border-slate-500 hover:text-slate-300"
              )}
            >
              All
            </button>
            {watchlist.map((t) => (
              <TickerChip
                key={t}
                ticker={t}
                selected={selectedTickers.has(t)}
                onClick={() => toggleTicker(t)}
              />
            ))}
          </div>
          {selectedTickers.size > 0 && (
            <p className="text-[10px] text-slate-500 mt-2">
              Showing macro events + earnings for{" "}
              <span className="text-accent font-mono">{Array.from(selectedTickers).join(", ")}</span>
            </p>
          )}
        </div>
      )}

      {/* ── Loading skeleton ── */}
      <AnimatePresence>
        {loading && (
          <motion.div
            key="skeleton"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-3"
          >
            {Array.from({ length: 5 }).map((_, i) => (
              <SkeletonRow key={i} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Error state ── */}
      {error && !loading && (
        <div className="card p-4 border border-loss/30 bg-loss/5 text-loss text-sm">
          {error}
        </div>
      )}

      {/* ── Empty state ── */}
      {!loading && !error && events.length === 0 && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col items-center justify-center py-24 gap-4 text-slate-500"
        >
          <Calendar size={48} className="opacity-30" />
          <div className="text-center">
            <p className="text-base font-medium text-slate-400">No events in the next 90 days</p>
            <p className="text-sm mt-1">Check back closer to the next macro release date.</p>
          </div>
        </motion.div>
      )}

      {/* ── Event groups ── */}
      {!loading && !error && groups.length > 0 && (
        <motion.div
          key="events"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="space-y-6"
        >
          {groups.map((group) => (
            <DateSection key={group.dateKey} group={group} />
          ))}
        </motion.div>
      )}

      {/* ── Legend ── */}
      {!loading && events.length > 0 && (
        <div className="flex flex-wrap items-center gap-4 pt-2 border-t border-border">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-600">
            Legend
          </span>
          {(Object.entries(TYPE_CONFIG) as [EventType, typeof TYPE_CONFIG[EventType]][]).map(
            ([type, cfg]) => (
              <div key={type} className="flex items-center gap-1.5">
                <span
                  className={cn(
                    "text-[10px] font-bold font-mono px-1.5 py-0.5 rounded border",
                    cfg.color,
                    cfg.bg,
                    cfg.border
                  )}
                >
                  {cfg.label}
                </span>
                <span className="text-[10px] text-slate-500">{type}</span>
              </div>
            )
          )}
          <div className="flex items-center gap-1.5 ml-2">
            <span className="w-2 h-2 rounded-full bg-loss inline-block" />
            <span className="text-[10px] text-slate-500">HIGH impact</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-warn inline-block" />
            <span className="text-[10px] text-slate-500">MEDIUM impact</span>
          </div>
        </div>
      )}
    </div>
  );
}
