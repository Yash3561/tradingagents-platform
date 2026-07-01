import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Search, TrendingUp, TrendingDown, Loader2, ExternalLink } from "lucide-react";
import { useNavigate } from "react-router-dom";
import CandlestickChart from "../../components/charts/CandlestickChart";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

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
  const [search, setSearch] = useState("");
  const [activeTicker, setActiveTicker] = useState("SPY");
  const [indices, setIndices] = useState<IndexData[]>([]);
  const [gainers, setGainers] = useState<MoverData[]>([]);
  const [losers, setLosers] = useState<MoverData[]>([]);
  const [stats, setStats] = useState<TickerStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [sectors, setSectors] = useState<IndexData[]>([]);

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

  useEffect(() => {
    setStatsLoading(true);
    setStats(null);
    api.get(`/market/stats/${activeTicker}`)
      .then(r => setStats(r.data))
      .catch(() => {})
      .finally(() => setStatsLoading(false));
  }, [activeTicker]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const t = search.trim().toUpperCase();
    if (t) { setActiveTicker(t); setSearch(""); }
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
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value.toUpperCase())}
              placeholder="Search ticker..."
              className="bg-bg-elevated border border-border rounded-lg pl-8 pr-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-accent font-mono w-44 transition-colors"
            />
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
          <CandlestickChart ticker={activeTicker} period="3mo" height={400} showControls={true} />

          {/* Quick ticker pills */}
          <div className="flex flex-wrap gap-1.5">
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
          </div>
        </div>

        {/* Stats panel — 1 col */}
        <div className="space-y-4">
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
