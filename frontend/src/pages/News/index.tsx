import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  RefreshCw,
  Newspaper,
  ExternalLink,
} from "lucide-react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

// ── Types ──────────────────────────────────────────────────────────────────────

interface NewsImage {
  url: string;
  size: string;
}

interface NewsItem {
  id: string;
  headline: string;
  summary: string;
  source: string;
  url: string;
  published_at: string;
  tickers: string[];
  images: NewsImage[];
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function timeAgo(isoString: string): string {
  const now = Date.now();
  const past = new Date(isoString).getTime();
  const diffMs = now - past;
  const diffMin = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

function getFirstImage(images: NewsImage[]): string | null {
  if (!images || images.length === 0) return null;
  // Prefer "small" size, otherwise take first
  const small = images.find((img) => img.size === "small");
  return small ? small.url : images[0].url;
}

// ── Skeleton Card ──────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="card p-4 animate-pulse">
      <div className="flex items-start gap-4">
        <div className="flex-1 space-y-3">
          <div className="flex justify-between items-center">
            <div className="h-3 bg-bg-elevated rounded w-24" />
            <div className="h-3 bg-bg-elevated rounded w-16" />
          </div>
          <div className="h-5 bg-bg-elevated rounded w-4/5" />
          <div className="space-y-2">
            <div className="h-3 bg-bg-elevated rounded w-full" />
            <div className="h-3 bg-bg-elevated rounded w-3/4" />
          </div>
          <div className="flex gap-2 pt-1">
            <div className="h-5 bg-bg-elevated rounded w-12" />
            <div className="h-5 bg-bg-elevated rounded w-14" />
          </div>
        </div>
        <div className="hidden sm:block w-20 h-[60px] bg-bg-elevated rounded-lg flex-shrink-0" />
      </div>
    </div>
  );
}

// ── News Card ──────────────────────────────────────────────────────────────────

interface NewsCardProps {
  item: NewsItem;
  onTickerClick: (ticker: string) => void;
}

function NewsCard({ item, onTickerClick }: NewsCardProps) {
  const [hovered, setHovered] = useState(false);
  const thumbnail = getFirstImage(item.images);

  const handleCardClick = (e: React.MouseEvent) => {
    // Don't open URL if clicking on a ticker pill
    if ((e.target as HTMLElement).closest("[data-ticker-pill]")) return;
    window.open(item.url, "_blank", "noopener,noreferrer");
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.2 }}
      className={cn(
        "card card-hover relative p-4 cursor-pointer group",
        "transition-all duration-200"
      )}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={handleCardClick}
    >
      {/* External link icon — visible on hover */}
      <AnimatePresence>
        {hovered && (
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            transition={{ duration: 0.15 }}
            className="absolute top-3 right-3 text-text-secondary"
          >
            <ExternalLink size={14} />
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex items-start gap-4">
        {/* Main content */}
        <div className="flex-1 min-w-0 space-y-2">
          {/* Source + time */}
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-text-secondary font-medium uppercase tracking-wide truncate">
              {item.source}
            </span>
            <span className="text-xs text-text-secondary whitespace-nowrap flex-shrink-0 font-mono">
              {timeAgo(item.published_at)}
            </span>
          </div>

          {/* Headline */}
          <p className="text-sm font-medium text-text-primary leading-snug pr-5">
            {item.headline}
          </p>

          {/* Summary */}
          {item.summary && (
            <p className="text-xs text-slate-400 leading-relaxed line-clamp-2">
              {item.summary}
            </p>
          )}

          {/* Ticker pills */}
          {item.tickers && item.tickers.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {item.tickers.slice(0, 8).map((ticker) => (
                <button
                  key={ticker}
                  data-ticker-pill="true"
                  onClick={(e) => {
                    e.stopPropagation();
                    onTickerClick(ticker);
                  }}
                  className={cn(
                    "badge-neutral font-mono text-xs px-2 py-0.5 rounded",
                    "hover:border hover:border-accent hover:text-accent",
                    "transition-colors duration-150 cursor-pointer"
                  )}
                >
                  {ticker}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Thumbnail — hidden on mobile */}
        {thumbnail && (
          <div className="hidden sm:block flex-shrink-0">
            <img
              src={thumbnail}
              alt=""
              className="w-20 h-[60px] object-cover rounded-lg bg-bg-elevated"
              loading="lazy"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = "none";
              }}
            />
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────────

const REFRESH_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

export default function News() {
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [activeTicker, setActiveTicker] = useState<string>("SPY");
  const [searchInput, setSearchInput] = useState<string>("");
  const [news, setNews] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // ── Fetch watchlist ─────────────────────────────────────────────────────────

  useEffect(() => {
    api
      .get<{ tickers: string[] }>("/settings/watchlist")
      .then((res) => {
        const tickers = res.data.tickers ?? [];
        setWatchlist(tickers);
        if (tickers.length > 0) {
          setActiveTicker(tickers[0]);
        }
      })
      .catch(() => {
        // Silently ignore — default to SPY
      });
  }, []);

  // ── Fetch news ──────────────────────────────────────────────────────────────

  const fetchNews = useCallback(
    async (ticker: string) => {
      if (!ticker) return;
      setLoading(true);
      setError(null);
      try {
        const res = await api.get<NewsItem[]>(
          `/market/news/${ticker.toUpperCase()}?limit=20`
        );
        setNews(res.data ?? []);
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Failed to load news.";
        setError(message);
        setNews([]);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  // Fetch when activeTicker changes
  useEffect(() => {
    fetchNews(activeTicker);
  }, [activeTicker, fetchNews]);

  // Auto-refresh every 5 minutes
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      fetchNews(activeTicker);
    }, REFRESH_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [activeTicker, fetchNews]);

  // ── Handlers ────────────────────────────────────────────────────────────────

  const handleSearchSubmit = () => {
    const val = searchInput.trim().toUpperCase();
    if (!val) return;
    setActiveTicker(val);
    setSearchInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      handleSearchSubmit();
    }
  };

  const handleTickerSelect = (ticker: string) => {
    setActiveTicker(ticker.toUpperCase());
    setSearchInput("");
  };

  const handleRefresh = () => {
    fetchNews(activeTicker);
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-bg-base p-6 space-y-6">
      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">
            Market News
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            Stay informed on market-moving events
          </p>
        </div>

        {/* Refresh button */}
        <button
          onClick={handleRefresh}
          disabled={loading}
          className={cn(
            "flex items-center gap-2 px-3 py-2 rounded-lg text-sm",
            "bg-bg-elevated text-text-secondary border border-border",
            "hover:border-accent hover:text-accent transition-colors duration-150",
            "disabled:opacity-50 disabled:cursor-not-allowed"
          )}
          title="Refresh news"
        >
          <RefreshCw
            size={14}
            className={cn(loading && "animate-spin")}
          />
          <span className="hidden sm:inline">Refresh</span>
        </button>
      </div>

      {/* ── Search + Watchlist chips ── */}
      <div className="card p-4 space-y-3">
        {/* Search input */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary pointer-events-none"
            />
            <input
              ref={inputRef}
              type="text"
              value={searchInput}
              onChange={(e) =>
                setSearchInput(e.target.value.toUpperCase())
              }
              onKeyDown={handleKeyDown}
              placeholder="Search ticker (e.g. AAPL)…"
              className={cn(
                "w-full pl-9 pr-4 py-2 rounded-lg text-sm font-mono",
                "bg-bg-elevated border border-border text-text-primary",
                "placeholder:text-text-secondary placeholder:font-sans",
                "focus:outline-none focus:border-accent transition-colors duration-150"
              )}
            />
          </div>
          <button
            onClick={handleSearchSubmit}
            disabled={!searchInput.trim()}
            className={cn(
              "px-4 py-2 rounded-lg text-sm font-medium",
              "bg-accent text-white",
              "hover:bg-accent/90 transition-colors duration-150",
              "disabled:opacity-40 disabled:cursor-not-allowed"
            )}
          >
            Search
          </button>
        </div>

        {/* Watchlist quick-select chips */}
        {watchlist.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {watchlist.map((ticker) => (
              <button
                key={ticker}
                onClick={() => handleTickerSelect(ticker)}
                className={cn(
                  "badge-neutral font-mono text-xs cursor-pointer transition-all duration-150",
                  "hover:text-accent",
                  activeTicker === ticker
                    ? "border border-accent text-accent"
                    : "border border-transparent"
                )}
              >
                {ticker}
              </button>
            ))}
          </div>
        )}

        {/* Active ticker label */}
        <div className="flex items-center gap-2 text-xs text-text-secondary">
          <span>Showing news for</span>
          <span className="font-mono font-semibold text-accent">
            {activeTicker}
          </span>
        </div>
      </div>

      {/* ── News Feed ── */}
      <div className="space-y-3">
        {/* Loading skeletons */}
        {loading && (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {/* Error state */}
        {!loading && error && (
          <div className="card p-6 text-center space-y-2">
            <p className="text-loss text-sm font-medium">{error}</p>
            <button
              onClick={handleRefresh}
              className="text-xs text-accent hover:underline"
            >
              Try again
            </button>
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && news.length === 0 && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="card p-12 flex flex-col items-center justify-center text-center space-y-3"
          >
            <Newspaper size={40} className="text-text-secondary opacity-40" />
            <p className="text-text-secondary text-sm">
              No news found for{" "}
              <span className="font-mono font-semibold text-text-primary">
                {activeTicker}
              </span>
            </p>
          </motion.div>
        )}

        {/* News cards */}
        {!loading && !error && news.length > 0 && (
          <AnimatePresence mode="popLayout">
            {news.map((item) => (
              <NewsCard
                key={item.id}
                item={item}
                onTickerClick={handleTickerSelect}
              />
            ))}
          </AnimatePresence>
        )}
      </div>
    </div>
  );
}
