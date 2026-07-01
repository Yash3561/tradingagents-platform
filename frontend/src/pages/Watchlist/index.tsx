import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus,
  X,
  BarChart2,
  Brain,
  BookMarked,
  Trash2,
  Check,
  Loader2,
  Search,
  TrendingUp,
  TrendingDown,
} from "lucide-react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { fmt } from "../../lib/formatters";

// ── Types ──────────────────────────────────────────────────────────────────────

interface LiveQuote {
  ticker: string;
  price: number;
  change: number;
  change_pct: number;
  volume: number;
  bid: number;
  ask: number;
}

interface TickerStats {
  name: string;
  sector: string;
  pe_ratio: number | null;
  beta: number | null;
  week_52_high: number;
  week_52_low: number;
}

interface FlashState {
  direction: "up" | "down" | null;
  at: number;
}

interface SearchResult {
  ticker: string;
  name: string;
}

// ── Animation variants ─────────────────────────────────────────────────────────

const FADE_UP = {
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
  transition: { duration: 0.3 },
};

const STAGGER_CHILD = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, scale: 0.96 },
};

// ── Skeleton card ──────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="card p-5 space-y-4 animate-pulse">
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <div className="h-5 w-16 bg-bg-elevated rounded" />
          <div className="h-3 w-28 bg-bg-elevated rounded" />
        </div>
        <div className="h-5 w-14 bg-bg-elevated rounded-full" />
      </div>
      <div className="space-y-1.5">
        <div className="h-7 w-24 bg-bg-elevated rounded" />
        <div className="h-4 w-16 bg-bg-elevated rounded" />
      </div>
      <div className="h-2 w-full bg-bg-elevated rounded-full" />
      <div className="flex gap-6">
        <div className="h-3 w-12 bg-bg-elevated rounded" />
        <div className="h-3 w-12 bg-bg-elevated rounded" />
        <div className="h-3 w-16 bg-bg-elevated rounded" />
      </div>
      <div className="flex gap-2 pt-1">
        <div className="h-8 flex-1 bg-bg-elevated rounded-lg" />
        <div className="h-8 flex-1 bg-bg-elevated rounded-lg" />
      </div>
    </div>
  );
}

// ── Add Ticker inline search ───────────────────────────────────────────────────

interface AddTickerPanelProps {
  onAdd: (ticker: string) => void;
  onClose: () => void;
  existingTickers: string[];
}

function AddTickerPanel({ onAdd, onClose, existingTickers }: AddTickerPanelProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.trim().length < 1) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await api.get("/market/search", { params: { q: query.trim() } });
        setResults(res.data?.slice(0, 8) ?? []);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 280);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  const handleSelect = async (ticker: string) => {
    if (existingTickers.includes(ticker)) return;
    setAdding(ticker);
    try {
      await api.post("/settings/watchlist/add", { ticker });
      onAdd(ticker);
    } catch (e) {
      console.error("Failed to add ticker", e);
    } finally {
      setAdding(null);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: -8, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.97 }}
      transition={{ duration: 0.2 }}
      className="absolute right-0 top-12 z-50 w-80 card shadow-xl border border-border-bright overflow-hidden"
    >
      {/* Search input */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border">
        <Search size={14} className="text-text-muted shrink-0" />
        <input
          ref={inputRef}
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search ticker or company…"
          className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none font-mono"
          onKeyDown={e => e.key === "Escape" && onClose()}
        />
        {searching && <Loader2 size={13} className="animate-spin text-accent shrink-0" />}
        <button onClick={onClose} className="text-text-muted hover:text-text-primary transition-colors">
          <X size={14} />
        </button>
      </div>

      {/* Results */}
      <div className="max-h-64 overflow-y-auto">
        {results.length === 0 && query.trim().length > 0 && !searching && (
          <p className="text-xs text-text-muted text-center py-6">No results for "{query}"</p>
        )}
        {results.length === 0 && query.trim().length === 0 && (
          <p className="text-xs text-text-muted text-center py-6">Type to search tickers</p>
        )}
        {results.map(r => {
          const alreadyAdded = existingTickers.includes(r.ticker);
          const isAdding = adding === r.ticker;
          return (
            <button
              key={r.ticker}
              onClick={() => !alreadyAdded && handleSelect(r.ticker)}
              disabled={alreadyAdded || isAdding}
              className={cn(
                "w-full flex items-center justify-between px-3 py-2.5 transition-colors text-left",
                alreadyAdded
                  ? "opacity-50 cursor-default"
                  : "hover:bg-bg-elevated cursor-pointer"
              )}
            >
              <div>
                <span className="text-sm font-mono font-semibold text-accent">{r.ticker}</span>
                <p className="text-xs text-text-muted mt-0.5 truncate max-w-[200px]">{r.name}</p>
              </div>
              {isAdding ? (
                <Loader2 size={13} className="animate-spin text-accent" />
              ) : alreadyAdded ? (
                <Check size={13} className="text-gain" />
              ) : (
                <Plus size={13} className="text-text-muted" />
              )}
            </button>
          );
        })}
      </div>
    </motion.div>
  );
}

// ── Ticker card ────────────────────────────────────────────────────────────────

interface TickerCardProps {
  ticker: string;
  quote: LiveQuote | null;
  stats: TickerStats | null;
  flash: FlashState;
  onRemove: (ticker: string) => void;
  onNavigate: (path: string) => void;
  index: number;
}

function TickerCard({ ticker, quote, stats, flash, onRemove, onNavigate, index }: TickerCardProps) {
  const [confirmRemove, setConfirmRemove] = useState(false);
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleRemoveClick = () => {
    setConfirmRemove(true);
    if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
    confirmTimerRef.current = setTimeout(() => setConfirmRemove(false), 3000);
  };

  const handleConfirmRemove = () => {
    if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
    onRemove(ticker);
  };

  const handleCancelRemove = () => {
    if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
    setConfirmRemove(false);
  };

  useEffect(() => {
    return () => {
      if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
    };
  }, []);

  // 52w range progress (0–100)
  const rangeProgress = (() => {
    if (!stats || !quote) return null;
    const { week_52_low, week_52_high } = stats;
    if (week_52_high === week_52_low) return 50;
    const pct = ((quote.price - week_52_low) / (week_52_high - week_52_low)) * 100;
    return Math.max(0, Math.min(100, pct));
  })();

  const isGain = (quote?.change_pct ?? 0) >= 0;

  const flashColor =
    flash.direction === "up"
      ? "text-gain"
      : flash.direction === "down"
      ? "text-loss"
      : "text-text-primary";

  const volumeFormatted = quote?.volume
    ? fmt.compact(quote.volume)
    : "—";

  return (
    <motion.div
      variants={STAGGER_CHILD}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={{ duration: 0.3, delay: index * 0.05 }}
      layout
      className="card card-hover p-5 flex flex-col gap-4 relative"
    >
      {/* Top row: ticker + sector + remove */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono font-bold text-lg text-accent tracking-wide">{ticker}</span>
            {stats?.sector && (
              <span className="badge-neutral text-2xs px-1.5 py-0.5 truncate max-w-[120px]">
                {stats.sector}
              </span>
            )}
          </div>
          {stats?.name && (
            <p className="text-xs text-text-muted mt-0.5 truncate">{stats.name}</p>
          )}
        </div>

        {/* Remove button / confirm prompt */}
        <div className="shrink-0 flex items-center gap-1">
          <AnimatePresence mode="wait">
            {confirmRemove ? (
              <motion.div
                key="confirm"
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 8 }}
                transition={{ duration: 0.15 }}
                className="flex items-center gap-1"
              >
                <span className="text-2xs text-loss font-medium mr-0.5">Confirm?</span>
                <button
                  onClick={handleConfirmRemove}
                  className="p-1 rounded text-loss hover:bg-loss/10 transition-colors"
                  title="Confirm remove"
                >
                  <Check size={13} />
                </button>
                <button
                  onClick={handleCancelRemove}
                  className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
                  title="Cancel"
                >
                  <X size={13} />
                </button>
              </motion.div>
            ) : (
              <motion.button
                key="remove"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.1 }}
                onClick={handleRemoveClick}
                className="p-1.5 rounded-lg text-text-muted hover:text-loss hover:bg-loss/10 transition-colors"
                title="Remove from watchlist"
              >
                <X size={14} />
              </motion.button>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Live price + change */}
      <div className="flex items-end justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "text-2xl font-mono font-semibold transition-colors duration-300",
                flashColor
              )}
            >
              {quote ? fmt.price(quote.price) : "—"}
            </span>
            {flash.direction && (
              <span className={cn("text-sm transition-opacity", flashColor)}>
                {flash.direction === "up" ? "▲" : "▼"}
              </span>
            )}
          </div>
          {quote && (
            <div className="flex items-center gap-2 mt-1">
              <span className={cn("text-xs font-mono", isGain ? "text-gain" : "text-loss")}>
                {isGain ? "+" : ""}
                {fmt.price(quote.change)}
              </span>
              <span className={cn(isGain ? "badge-gain" : "badge-loss")}>
                {isGain ? "▲" : "▼"} {Math.abs(quote.change_pct).toFixed(2)}%
              </span>
            </div>
          )}
        </div>

        {/* Bid/Ask */}
        {quote && (
          <div className="text-right">
            <p className="text-2xs text-text-muted">Bid / Ask</p>
            <p className="text-xs font-mono text-text-secondary">
              {fmt.price(quote.bid)} / {fmt.price(quote.ask)}
            </p>
          </div>
        )}
      </div>

      {/* 52-week range bar */}
      {stats && quote && rangeProgress !== null ? (
        <div className="space-y-1.5">
          <div className="flex justify-between text-2xs text-text-muted font-mono">
            <span>{fmt.price(stats.week_52_low)}</span>
            <span className="text-text-muted">52W Range</span>
            <span>{fmt.price(stats.week_52_high)}</span>
          </div>
          <div className="relative h-1.5 w-full bg-bg-elevated rounded-full overflow-visible">
            <div
              className="absolute h-1.5 rounded-full bg-gradient-to-r from-loss via-warn to-gain"
              style={{ width: "100%" }}
            />
            {/* Marker dot */}
            <div
              className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white border-2 border-accent shadow-md transition-all duration-500"
              style={{ left: `calc(${rangeProgress}% - 6px)` }}
            />
          </div>
        </div>
      ) : (
        <div className="h-1.5 w-full bg-bg-elevated rounded-full opacity-30" />
      )}

      {/* Stats row */}
      <div className="flex items-center gap-4 text-2xs">
        <div>
          <span className="text-text-muted uppercase tracking-wide font-medium">PE </span>
          <span className="font-mono text-text-secondary">
            {stats?.pe_ratio != null ? stats.pe_ratio.toFixed(1) : "—"}
          </span>
        </div>
        <div className="w-px h-3 bg-border" />
        <div>
          <span className="text-text-muted uppercase tracking-wide font-medium">Beta </span>
          <span className="font-mono text-text-secondary">
            {stats?.beta != null ? stats.beta.toFixed(2) : "—"}
          </span>
        </div>
        <div className="w-px h-3 bg-border" />
        <div>
          <span className="text-text-muted uppercase tracking-wide font-medium">Vol </span>
          <span className="font-mono text-text-secondary">{volumeFormatted}</span>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex gap-2 pt-0.5">
        <button
          onClick={() => onNavigate(`/markets?ticker=${ticker}`)}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-bg-elevated hover:bg-accent/10 hover:text-accent border border-border hover:border-accent/30 text-text-secondary text-xs font-medium transition-all duration-150"
        >
          <BarChart2 size={13} />
          Chart
        </button>
        <button
          onClick={() => onNavigate(`/agents?ticker=${ticker}`)}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-bg-elevated hover:bg-accent/10 hover:text-accent border border-border hover:border-accent/30 text-text-secondary text-xs font-medium transition-all duration-150"
        >
          <Brain size={13} />
          Analyze
        </button>
      </div>
    </motion.div>
  );
}

// ── Empty state ────────────────────────────────────────────────────────────────

function EmptyState({ onAddClick }: { onAddClick: () => void }) {
  return (
    <motion.div
      {...FADE_UP}
      className="flex flex-col items-center justify-center py-24 text-center"
    >
      <div className="w-20 h-20 rounded-2xl bg-bg-card border border-border flex items-center justify-center mb-5 shadow-card">
        <BookMarked size={32} className="text-text-muted" />
      </div>
      <h3 className="text-base font-semibold text-text-primary mb-1">No tickers saved yet</h3>
      <p className="text-sm text-text-muted mb-6 max-w-xs">
        Add your first ticker to start monitoring live prices and key stats.
      </p>
      <button
        onClick={onAddClick}
        className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent/90 text-white text-sm font-medium rounded-lg transition-colors shadow-accent-glow"
      >
        <Plus size={15} />
        Add Ticker
      </button>
    </motion.div>
  );
}

// ── Main Watchlist page ────────────────────────────────────────────────────────

export default function Watchlist() {
  const navigate = useNavigate();

  const [tickers, setTickers] = useState<string[]>([]);
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({});
  const [stats, setStats] = useState<Record<string, TickerStats>>({});
  const [flashes, setFlashes] = useState<Record<string, FlashState>>({});
  const [loading, setLoading] = useState(true);
  const [showAddPanel, setShowAddPanel] = useState(false);
  const [removing, setRemoving] = useState<Set<string>>(new Set());

  const prevPricesRef = useRef<Record<string, number>>({});
  const addButtonRef = useRef<HTMLDivElement>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Load watchlist ────────────────────────────────────────────────────────

  const loadWatchlist = useCallback(async () => {
    try {
      const res = await api.get("/settings/watchlist");
      const tickerList: string[] = res.data?.tickers ?? [];
      setTickers(tickerList);
      return tickerList;
    } catch (e) {
      console.error("Failed to load watchlist", e);
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Load stats for a set of tickers ──────────────────────────────────────

  const loadStats = useCallback(async (tickerList: string[]) => {
    if (tickerList.length === 0) return;
    const results = await Promise.allSettled(
      tickerList.map(t => api.get(`/market/stats/${t}`))
    );
    setStats(prev => {
      const next = { ...prev };
      results.forEach((r, i) => {
        if (r.status === "fulfilled") {
          next[tickerList[i]] = r.value.data as TickerStats;
        }
      });
      return next;
    });
  }, []);

  // ── Poll live quotes ──────────────────────────────────────────────────────

  const pollQuotes = useCallback(async (tickerList: string[]) => {
    if (tickerList.length === 0) return;
    const results = await Promise.allSettled(
      tickerList.map(t => api.get(`/market/quote/${t}/live`))
    );

    const now = Date.now();
    const newFlashes: Record<string, FlashState> = {};

    setQuotes(prev => {
      const next = { ...prev };
      results.forEach((r, i) => {
        if (r.status === "fulfilled") {
          const t = tickerList[i];
          const newQuote = r.value.data as LiveQuote;
          const prevPrice = prevPricesRef.current[t];
          const direction =
            prevPrice !== undefined
              ? newQuote.price > prevPrice
                ? "up"
                : newQuote.price < prevPrice
                ? "down"
                : null
              : null;

          if (direction) {
            newFlashes[t] = { direction, at: now };
          }

          prevPricesRef.current[t] = newQuote.price;
          next[t] = newQuote;
        }
      });
      return next;
    });

    if (Object.keys(newFlashes).length > 0) {
      setFlashes(prev => ({ ...prev, ...newFlashes }));
      // Clear flashes after 800ms
      setTimeout(() => {
        setFlashes(prev => {
          const next = { ...prev };
          Object.keys(newFlashes).forEach(t => {
            if (next[t]?.at === newFlashes[t].at) {
              next[t] = { direction: null, at: 0 };
            }
          });
          return next;
        });
      }, 800);
    }
  }, []);

  // ── Start/restart polling whenever tickers changes ────────────────────────

  const startPolling = useCallback(
    (tickerList: string[]) => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      if (tickerList.length === 0) return;
      pollQuotes(tickerList);
      pollIntervalRef.current = setInterval(() => pollQuotes(tickerList), 8000);
    },
    [pollQuotes]
  );

  // ── Initial load ──────────────────────────────────────────────────────────

  useEffect(() => {
    loadWatchlist().then(tickerList => {
      loadStats(tickerList);
      startPolling(tickerList);
    });
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Restart polling when tickers array changes ────────────────────────────

  useEffect(() => {
    startPolling(tickers);
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [tickers.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Close add panel on outside click ─────────────────────────────────────

  useEffect(() => {
    if (!showAddPanel) return;
    const handler = (e: MouseEvent) => {
      if (addButtonRef.current && !addButtonRef.current.contains(e.target as Node)) {
        setShowAddPanel(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showAddPanel]);

  // ── Handlers ──────────────────────────────────────────────────────────────

  const handleTickerAdded = useCallback(
    (ticker: string) => {
      setTickers(prev => {
        if (prev.includes(ticker)) return prev;
        const next = [...prev, ticker];
        loadStats([ticker]);
        return next;
      });
      setShowAddPanel(false);
    },
    [loadStats]
  );

  const handleRemove = useCallback(async (ticker: string) => {
    setRemoving(prev => new Set(prev).add(ticker));
    try {
      await api.delete(`/settings/watchlist/${ticker}`);
      setTickers(prev => prev.filter(t => t !== ticker));
      setQuotes(prev => {
        const next = { ...prev };
        delete next[ticker];
        return next;
      });
      setStats(prev => {
        const next = { ...prev };
        delete next[ticker];
        return next;
      });
      setFlashes(prev => {
        const next = { ...prev };
        delete next[ticker];
        return next;
      });
      delete prevPricesRef.current[ticker];
    } catch (e) {
      console.error("Failed to remove ticker", e);
    } finally {
      setRemoving(prev => {
        const next = new Set(prev);
        next.delete(ticker);
        return next;
      });
    }
  }, []);

  const handleNavigate = useCallback(
    (path: string) => {
      navigate(path);
    },
    [navigate]
  );

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <motion.div
      key="watchlist"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Watchlist</h1>
          <p className="text-sm text-text-muted mt-0.5 flex items-center gap-1.5">
            <span
              className={cn(
                "inline-block w-1.5 h-1.5 rounded-full",
                tickers.length > 0 ? "bg-gain animate-pulse" : "bg-text-muted"
              )}
            />
            Your saved tickers, live
          </p>
        </div>

        {/* Add ticker button + panel */}
        <div className="relative" ref={addButtonRef}>
          <button
            onClick={() => setShowAddPanel(v => !v)}
            className={cn(
              "flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all duration-150",
              showAddPanel
                ? "bg-accent text-white shadow-accent-glow"
                : "bg-accent hover:bg-accent/90 text-white shadow-accent-glow"
            )}
          >
            <Plus size={15} />
            Add Ticker
          </button>

          <AnimatePresence>
            {showAddPanel && (
              <AddTickerPanel
                onAdd={handleTickerAdded}
                onClose={() => setShowAddPanel(false)}
                existingTickers={tickers}
              />
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Ticker count badge */}
      {!loading && tickers.length > 0 && (
        <div className="flex items-center gap-3">
          <span className="text-xs text-text-muted">
            {tickers.length} ticker{tickers.length !== 1 ? "s" : ""} monitored
          </span>
          <div className="flex items-center gap-1.5 text-xs text-text-muted">
            <TrendingUp size={11} className="text-gain" />
            <span>
              {
                Object.values(quotes).filter(q => q.change_pct >= 0).length
              }{" "}
              gainers
            </span>
            <span className="text-border">·</span>
            <TrendingDown size={11} className="text-loss" />
            <span>
              {
                Object.values(quotes).filter(q => q.change_pct < 0).length
              }{" "}
              losers
            </span>
          </div>
        </div>
      )}

      {/* Loading skeletons */}
      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!loading && tickers.length === 0 && (
        <EmptyState onAddClick={() => setShowAddPanel(true)} />
      )}

      {/* Ticker grid */}
      {!loading && tickers.length > 0 && (
        <motion.div
          layout
          className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
        >
          <AnimatePresence mode="popLayout">
            {tickers
              .filter(t => !removing.has(t))
              .map((ticker, i) => (
                <TickerCard
                  key={ticker}
                  ticker={ticker}
                  quote={quotes[ticker] ?? null}
                  stats={stats[ticker] ?? null}
                  flash={flashes[ticker] ?? { direction: null, at: 0 }}
                  onRemove={handleRemove}
                  onNavigate={handleNavigate}
                  index={i}
                />
              ))}
          </AnimatePresence>
        </motion.div>
      )}
    </motion.div>
  );
}
