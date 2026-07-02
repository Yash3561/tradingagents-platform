import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, TrendingUp, TrendingDown, Loader2, ExternalLink, Brain, RefreshCw, ShieldAlert } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import CandlestickChart, { ChartLevel } from "../../components/charts/CandlestickChart";
import OrderTicket from "../../components/trading/OrderTicket";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

interface SearchResult { symbol: string; name: string; sector: string; }

interface AIRead {
  ticker: string;
  generated_at: string;
  technicals: Record<string, number | boolean | number[] | null>;
  read: {
    trend_bias: "BULLISH" | "BEARISH" | "NEUTRAL";
    confidence: number;
    outlook: string;
    reasons: string[];
    risks: string[];
    support_levels: number[];
    resistance_levels: number[];
  };
}

interface IndexData { symbol: string; label: string; price: number; change_pct: number; week_pct: number; }
interface MoverData { symbol: string; price: number; change_pct: number; volume: number; }
interface TickerStats {
  symbol: string; name: string; sector: string; industry: string;
  market_cap: number | null; pe_ratio: number | null; beta: number | null;
  week_52_high: number; week_52_low: number; current_price: number;
  avg_volume: number | null;
}

const QUICK_TICKERS = [
  "SPY","QQQ","AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AMD",
  "ASML","COIN","PLTR","TSM","NFLX","JPM","GS","V","UNH","XOM",
];

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null) return "—";
  return n.toLocaleString("en-US", { maximumFractionDigits: decimals, minimumFractionDigits: decimals });
}

function fmtLarge(n: number | null): string {
  if (n == null) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toLocaleString()}`;
}

export default function Markets() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [activeTicker, setActiveTicker] = useState(
    () => searchParams.get("ticker")?.toUpperCase() || "SPY"
  );
  const [aiRead, setAiRead] = useState<AIRead | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [indices, setIndices] = useState<IndexData[]>([]);
  const [gainers, setGainers] = useState<MoverData[]>([]);
  const [losers, setLosers] = useState<MoverData[]>([]);
  const [stats, setStats] = useState<TickerStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [sectors, setSectors] = useState<IndexData[]>([]);
  const [suggestions, setSuggestions] = useState<SearchResult[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const fetchSuggestions = useCallback((q: string) => {
    if (q.length < 1) { setSuggestions([]); setShowSuggestions(false); return; }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      api.get(`/market/search?q=${q}`).then(r => {
        setSuggestions(r.data);
        setShowSuggestions(r.data.length > 0);
      }).catch(() => {});
    }, 200);
  }, []);

  const pickTicker = (symbol: string) => {
    setActiveTicker(symbol);
    setSearch("");
    setSuggestions([]);
    setShowSuggestions(false);
  };

  useEffect(() => {
    // Fetch overview + movers in parallel
    Promise.all([
      api.get("/market/overview"),
      api.get("/market/movers"),
    ]).then(([ov, mv]) => {
      setIndices(ov.data.indices || []);
      setSectors(ov.data.sectors || []);
      setGainers(mv.data.gainers || []);
      setLosers(mv.data.losers || []);
    }).catch(() => {}).finally(() => setOverviewLoading(false));
  }, []);

  // React to ?ticker= navigation (e.g. Watchlist → Chart)
  useEffect(() => {
    const t = searchParams.get("ticker");
    if (t && t.toUpperCase() !== activeTicker) setActiveTicker(t.toUpperCase());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Restore last viewed ticker (unless deep-linked), persist changes
  const tickerRestoredRef = useRef(false);
  useEffect(() => {
    if (searchParams.get("ticker")) { tickerRestoredRef.current = true; return; }
    api.get("/settings/last_market_ticker")
      .then(r => { if (r.data?.value) setActiveTicker(String(r.data.value).toUpperCase()); })
      .catch(() => {})
      .finally(() => { tickerRestoredRef.current = true; });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!tickerRestoredRef.current) return;
    const t = setTimeout(() => {
      api.post("/settings/", { last_market_ticker: activeTicker }).catch(() => {});
    }, 1000);
    return () => clearTimeout(t);
  }, [activeTicker]);

  useEffect(() => {
    setStatsLoading(true);
    setStats(null);
    setAiRead(null);
    setAiError(null);
    api.get(`/market/stats/${activeTicker}`)
      .then(r => setStats(r.data))
      .catch(() => {})
      .finally(() => setStatsLoading(false));
  }, [activeTicker]);

  const fetchAiRead = (refresh = false) => {
    setAiLoading(true);
    setAiError(null);
    api.get(`/market/ai-read/${activeTicker}${refresh ? "?refresh=true" : ""}`)
      .then(r => setAiRead(r.data))
      .catch(e => setAiError(e.response?.data?.detail ?? "AI read failed — try again"))
      .finally(() => setAiLoading(false));
  };

  const chartLevels: ChartLevel[] = aiRead
    ? [
        ...aiRead.read.support_levels.map((p, i) => ({ price: p, label: `S${i + 1}`, kind: "support" as const })),
        ...aiRead.read.resistance_levels.map((p, i) => ({ price: p, label: `R${i + 1}`, kind: "resistance" as const })),
      ]
    : [];

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const t = search.trim().toUpperCase();
    if (t) { pickTicker(t); }
  };

  return (
    <motion.div
      key="markets"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="p-6 space-y-5"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Markets</h1>
          <p className="text-sm text-slate-400">Charts and data for any stock, ETF, or index</p>
        </div>
        <form onSubmit={handleSearch} className="flex gap-2">
          <div className="relative" ref={searchRef}>
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 z-10" />
            <input
              value={search}
              onChange={e => { const v = e.target.value.toUpperCase(); setSearch(v); fetchSuggestions(v); }}
              onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
              placeholder="Search any ticker..."
              className="bg-bg-elevated border border-border rounded-lg pl-8 pr-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-accent font-mono w-52 transition-colors"
              autoComplete="off"
            />
            {showSuggestions && (
              <div className="absolute top-full left-0 mt-1 w-72 bg-bg-elevated border border-border rounded-lg shadow-xl z-50 overflow-hidden">
                {suggestions.map(s => (
                  <button
                    key={s.symbol}
                    type="button"
                    onClick={() => pickTicker(s.symbol)}
                    className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-bg-card transition-colors text-left"
                  >
                    <div>
                      <span className="font-mono font-bold text-white text-sm">{s.symbol}</span>
                      <p className="text-xs text-slate-400 truncate max-w-40">{s.name}</p>
                    </div>
                    <span className="text-xs text-slate-500 bg-bg-base px-1.5 py-0.5 rounded">{s.sector}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <button type="submit" className="px-4 py-2 bg-accent hover:bg-accent/90 text-white rounded-lg text-sm font-medium transition-colors">
            Go
          </button>
        </form>
      </div>

      {/* Indices strip */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
        {overviewLoading
          ? Array(6).fill(0).map((_, i) => <div key={i} className="card p-3 animate-pulse h-16" />)
          : indices.map(idx => (
            <button
              key={idx.symbol}
              onClick={() => setActiveTicker(idx.symbol)}
              className={cn("card p-3 text-left transition-colors hover:border-accent/50", activeTicker === idx.symbol && "border-accent")}
            >
              <p className="text-xs text-slate-400">{idx.label}</p>
              <p className="font-mono font-bold text-white text-sm">${fmt(idx.price)}</p>
              <p className={cn("text-xs font-mono", idx.change_pct >= 0 ? "text-gain" : "text-loss")}>
                {idx.change_pct >= 0 ? "+" : ""}{fmt(idx.change_pct)}%
              </p>
            </button>
          ))
        }
      </div>

      {/* Main chart + stats */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
        {/* Chart — takes 3 cols */}
        <div className="lg:col-span-3 space-y-3">
          <CandlestickChart ticker={activeTicker} period="3mo" height={400} showControls={true} levels={chartLevels} />

          {/* Quick ticker pills + AI Read trigger */}
          <div className="flex flex-wrap items-center gap-1.5">
            {QUICK_TICKERS.map(t => (
              <button
                key={t}
                onClick={() => setActiveTicker(t)}
                className={cn(
                  "px-2.5 py-1 rounded-lg text-xs font-mono font-medium transition-colors",
                  activeTicker === t
                    ? "bg-accent text-white"
                    : "bg-bg-elevated text-slate-400 hover:text-white hover:bg-bg-card border border-border"
                )}
              >
                {t}
              </button>
            ))}
            <button
              onClick={() => fetchAiRead(false)}
              disabled={aiLoading}
              className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                         bg-accent/10 hover:bg-accent/20 border border-accent/30 text-accent
                         transition-colors disabled:opacity-50"
            >
              {aiLoading ? <Loader2 size={12} className="animate-spin" /> : <Brain size={12} />}
              {aiLoading ? "Reading chart..." : `AI Read: ${activeTicker}`}
            </button>
          </div>

          {aiError && <p className="text-xs text-loss">{aiError}</p>}

          {/* AI chart read panel */}
          <AnimatePresence>
            {aiRead && aiRead.ticker === activeTicker && (
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="card p-5 space-y-4"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Brain size={16} className="text-accent" />
                    <h3 className="text-sm font-semibold text-white">AI Chart Read — {aiRead.ticker}</h3>
                    <span className={cn(
                      "px-2 py-0.5 rounded-full text-xs font-bold",
                      aiRead.read.trend_bias === "BULLISH" && "bg-gain/15 text-gain",
                      aiRead.read.trend_bias === "BEARISH" && "bg-loss/15 text-loss",
                      aiRead.read.trend_bias === "NEUTRAL" && "bg-warn/15 text-warn",
                    )}>
                      {aiRead.read.trend_bias}
                    </span>
                    <span className="text-xs font-mono text-slate-400">
                      {Math.round(aiRead.read.confidence * 100)}% confidence
                    </span>
                  </div>
                  <button
                    onClick={() => fetchAiRead(true)}
                    disabled={aiLoading}
                    title="Regenerate (bypasses 10-min cache)"
                    className="p-1.5 rounded text-slate-400 hover:text-white transition-colors disabled:opacity-50"
                  >
                    <RefreshCw size={13} className={aiLoading ? "animate-spin" : ""} />
                  </button>
                </div>

                <p className="text-sm text-slate-300 leading-relaxed">{aiRead.read.outlook}</p>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                      Why the AI thinks this
                    </h4>
                    <ul className="space-y-1.5">
                      {aiRead.read.reasons.map((r, i) => (
                        <li key={i} className="text-xs text-slate-300 flex items-start gap-2">
                          <span className="text-accent shrink-0 mt-0.5">▸</span>{r}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="space-y-3">
                    <div>
                      <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                        <ShieldAlert size={11} className="inline mr-1 -mt-0.5" />
                        What would invalidate it
                      </h4>
                      <ul className="space-y-1.5">
                        {aiRead.read.risks.map((r, i) => (
                          <li key={i} className="text-xs text-slate-400 flex items-start gap-2">
                            <span className="text-loss shrink-0 mt-0.5">▸</span>{r}
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {aiRead.read.support_levels.map((p, i) => (
                        <span key={`s${i}`} className="text-xs font-mono px-2 py-0.5 rounded bg-gain/10 text-gain border border-gain/20">
                          S{i + 1} ${p.toFixed(2)}
                        </span>
                      ))}
                      {aiRead.read.resistance_levels.map((p, i) => (
                        <span key={`r${i}`} className="text-xs font-mono px-2 py-0.5 rounded bg-loss/10 text-loss border border-loss/20">
                          R{i + 1} ${p.toFixed(2)}
                        </span>
                      ))}
                    </div>
                    <p className="text-[10px] text-slate-500">
                      Levels are drawn on the chart (green = support, red = resistance). Not financial advice.
                    </p>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Stats panel — 1 col */}
        <div className="space-y-4">
          <OrderTicket ticker={activeTicker} currentPrice={stats?.current_price ?? null} />

          {statsLoading ? (
            <div className="card p-5 flex items-center justify-center h-64">
              <Loader2 size={20} className="animate-spin text-accent" />
            </div>
          ) : stats ? (
            <div className="card p-5">
              <div className="mb-4">
                <h3 className="font-bold text-white text-lg font-mono">{stats.symbol}</h3>
                <p className="text-xs text-slate-400 mt-0.5 leading-tight">{stats.name}</p>
                {stats.sector && <span className="text-xs bg-accent/20 text-accent px-2 py-0.5 rounded-full mt-1 inline-block">{stats.sector}</span>}
              </div>

              <div className="space-y-2.5">
                {[
                  ["Price", `$${fmt(stats.current_price)}`],
                  ["Mkt Cap", fmtLarge(stats.market_cap)],
                  ["P/E", fmt(stats.pe_ratio)],
                  ["Beta", fmt(stats.beta)],
                  ["52W High", `$${fmt(stats.week_52_high)}`],
                  ["52W Low", `$${fmt(stats.week_52_low)}`],
                  ["Avg Vol", stats.avg_volume ? `${(stats.avg_volume / 1e6).toFixed(1)}M` : "—"],
                ].map(([label, value]) => (
                  <div key={label} className="flex items-center justify-between">
                    <span className="text-xs text-slate-500">{label}</span>
                    <span className="text-xs font-mono text-white font-medium">{value}</span>
                  </div>
                ))}
              </div>

              <button
                onClick={() => navigate(`/agents?ticker=${stats.symbol}`)}
                className="w-full mt-4 flex items-center justify-center gap-2 px-3 py-2.5 bg-accent/10 hover:bg-accent/20 border border-accent/30 text-accent rounded-lg text-xs font-medium transition-colors"
              >
                <ExternalLink size={12} />
                Analyze with AI
              </button>
            </div>
          ) : null}

          {/* Sector heatmap */}
          {sectors.length > 0 && (
            <div className="card p-4">
              <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Sectors Today</h4>
              <div className="space-y-1.5">
                {sectors.map(s => (
                  <button
                    key={s.symbol}
                    onClick={() => setActiveTicker(s.symbol)}
                    className="w-full flex items-center justify-between hover:bg-bg-elevated rounded px-1 py-0.5 transition-colors"
                  >
                    <span className="text-xs text-slate-300">{s.label}</span>
                    <span className={cn("text-xs font-mono font-medium", s.change_pct >= 0 ? "text-gain" : "text-loss")}>
                      {s.change_pct >= 0 ? "+" : ""}{fmt(s.change_pct)}%
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Movers */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Gainers */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp size={15} className="text-gain" />
            <h3 className="text-sm font-semibold text-white">Top Gainers</h3>
            <span className="text-xs text-slate-500">(from watchlist)</span>
          </div>
          <div className="space-y-2">
            {gainers.map(g => (
              <button
                key={g.symbol}
                onClick={() => setActiveTicker(g.symbol)}
                className="w-full flex items-center justify-between hover:bg-bg-elevated rounded-lg px-2 py-1.5 transition-colors"
              >
                <span className="font-mono font-bold text-sm text-white">{g.symbol}</span>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-400 font-mono">${fmt(g.price)}</span>
                  <span className="text-xs font-mono font-bold text-gain">+{fmt(g.change_pct)}%</span>
                </div>
              </button>
            ))}
            {gainers.length === 0 && <p className="text-xs text-slate-500">Loading movers...</p>}
          </div>
        </div>

        {/* Losers */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-3">
            <TrendingDown size={15} className="text-loss" />
            <h3 className="text-sm font-semibold text-white">Top Losers</h3>
            <span className="text-xs text-slate-500">(from watchlist)</span>
          </div>
          <div className="space-y-2">
            {losers.map(g => (
              <button
                key={g.symbol}
                onClick={() => setActiveTicker(g.symbol)}
                className="w-full flex items-center justify-between hover:bg-bg-elevated rounded-lg px-2 py-1.5 transition-colors"
              >
                <span className="font-mono font-bold text-sm text-white">{g.symbol}</span>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-400 font-mono">${fmt(g.price)}</span>
                  <span className="text-xs font-mono font-bold text-loss">{fmt(g.change_pct)}%</span>
                </div>
              </button>
            ))}
            {losers.length === 0 && <p className="text-xs text-slate-500">Loading movers...</p>}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
