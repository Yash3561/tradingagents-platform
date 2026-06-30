import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Brain, TrendingUp, TrendingDown, Loader2, RefreshCw, Award, AlertTriangle, CheckCircle2, Target, Activity, PieChart } from "lucide-react";
import { api } from "../../lib/api";
import { fmt } from "../../lib/formatters";
import { cn } from "../../lib/cn";

interface Recommendation {
  action: string;
  reason: string;
}

interface Analysis {
  overall_assessment: string;
  whats_working: string[];
  needs_improvement: string[];
  recommendations: Recommendation[];
  performance_grade: string;
}

interface RawStats {
  total_trades: number;
  closed_trades: number;
  win_rate: number;
  total_pnl: number;
  open_positions: number;
  equity?: number;
  day_pnl?: number;
  day_pnl_pct?: number;
}

interface PerfSummary {
  generated_at: string;
  period_days: number;
  raw_stats: RawStats;
  analysis: Analysis;
}

const GRADE_COLOR: Record<string, string> = {
  A: "text-gain",
  B: "text-gain",
  C: "text-warn",
  D: "text-loss",
  F: "text-loss",
  "?": "text-slate-400",
};

const GRADE_BG: Record<string, string> = {
  A: "bg-gain/10 border-gain/30",
  B: "bg-gain/10 border-gain/20",
  C: "bg-warn/10 border-warn/20",
  D: "bg-loss/10 border-loss/20",
  F: "bg-loss/10 border-loss/30",
  "?": "bg-bg-elevated border-border",
};

export default function Analytics() {
  const [data, setData] = useState<PerfSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [corrData, setCorrData] = useState<{tickers: string[], matrix: {x:string,y:string,value:number}[]} | null>(null);
  const [corrLoading, setCorrLoading] = useState(false);
  const [sectorData, setSectorData] = useState<{sectors: {sector:string,value:number,pct:number}[], total_value:number} | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data: res } = await api.get("/analytics/performance-summary");
      setData(res);
    } catch (e: any) {
      setError(e.response?.data?.detail ?? "Failed to load analysis");
    } finally {
      setLoading(false);
    }
    try {
      setCorrLoading(true);
      const { data: corrRes } = await api.get("/analytics/correlation");
      setCorrData(corrRes);
    } catch { /* ignore */ } finally { setCorrLoading(false); }
    try {
      const { data: secRes } = await api.get("/analytics/sector-exposure");
      setSectorData(secRes);
    } catch { /* ignore */ }
  };

  useEffect(() => { load(); }, []);

  const s = data?.raw_stats;
  const a = data?.analysis;

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Brain size={22} className="text-accent" />
          <div>
            <h1 className="text-xl font-bold text-white">Performance Analyzer</h1>
            <p className="text-sm text-slate-400">AI-powered analysis of your last 30 days</p>
          </div>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-accent/10 hover:bg-accent/20 border border-accent/30 text-accent rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Refresh Analysis
        </button>
      </div>

      {error && (
        <div className="card p-4 border-loss/30 bg-loss/5 text-loss text-sm">{error}</div>
      )}

      {loading && !data && (
        <div className="flex flex-col items-center justify-center h-64 gap-3">
          <Brain size={32} className="text-accent animate-pulse" />
          <p className="text-slate-400 text-sm">Analyzing your performance with AI...</p>
          <p className="text-slate-500 text-xs">This takes ~10 seconds</p>
        </div>
      )}

      {data && (
        <AnimatePresence>
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-5">

            {/* Stats row */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { label: "Win Rate", value: `${((s?.win_rate ?? 0) * 100).toFixed(1)}%`, color: (s?.win_rate ?? 0) >= 0.5 ? "text-gain" : "text-loss" },
                { label: "Total P&L", value: fmt.signUsd(s?.total_pnl ?? 0), color: (s?.total_pnl ?? 0) >= 0 ? "text-gain" : "text-loss" },
                { label: "Closed Trades", value: String(s?.closed_trades ?? 0), color: "text-white" },
                { label: "Open Positions", value: String(s?.open_positions ?? 0), color: "text-white" },
              ].map(card => (
                <div key={card.label} className="card p-4">
                  <p className="metric-label">{card.label}</p>
                  <p className={cn("text-2xl font-mono font-bold mt-1", card.color)}>{card.value}</p>
                </div>
              ))}
            </div>

            {/* Grade + overall assessment */}
            <div className={cn("card p-6 border", GRADE_BG[a?.performance_grade ?? "?"])}>
              <div className="flex items-start gap-5">
                <div className="shrink-0">
                  <div className={cn("w-16 h-16 rounded-xl border-2 flex items-center justify-center text-3xl font-black", GRADE_BG[a?.performance_grade ?? "?"], GRADE_COLOR[a?.performance_grade ?? "?"])}>
                    {a?.performance_grade ?? "?"}
                  </div>
                  <p className="text-xs text-slate-500 text-center mt-1">Grade</p>
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-slate-300 mb-2">Overall Assessment</h3>
                  <p className="text-white leading-relaxed">{a?.overall_assessment}</p>
                  {data.generated_at && (
                    <p className="text-xs text-slate-500 mt-3">
                      Generated {new Date(data.generated_at).toLocaleString()}
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* What's working + needs improvement */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="card p-5">
                <div className="flex items-center gap-2 mb-3">
                  <CheckCircle2 size={16} className="text-gain" />
                  <h3 className="text-sm font-semibold text-white">What's Working</h3>
                </div>
                <ul className="space-y-2">
                  {(a?.whats_working ?? []).map((item, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                      <span className="text-gain mt-0.5 shrink-0">✓</span>
                      {item}
                    </li>
                  ))}
                  {(a?.whats_working ?? []).length === 0 && (
                    <li className="text-sm text-slate-500">No data yet — run some trades first</li>
                  )}
                </ul>
              </div>

              <div className="card p-5">
                <div className="flex items-center gap-2 mb-3">
                  <AlertTriangle size={16} className="text-warn" />
                  <h3 className="text-sm font-semibold text-white">Needs Improvement</h3>
                </div>
                <ul className="space-y-2">
                  {(a?.needs_improvement ?? []).map((item, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                      <span className="text-warn mt-0.5 shrink-0">!</span>
                      {item}
                    </li>
                  ))}
                  {(a?.needs_improvement ?? []).length === 0 && (
                    <li className="text-sm text-slate-500">No data yet</li>
                  )}
                </ul>
              </div>
            </div>

            {/* Recommendations */}
            <div className="card p-5">
              <div className="flex items-center gap-2 mb-4">
                <Target size={16} className="text-accent" />
                <h3 className="text-sm font-semibold text-white">Next Week's Action Plan</h3>
              </div>
              <div className="space-y-3">
                {(a?.recommendations ?? []).map((rec, i) => (
                  <div key={i} className="flex gap-4 p-3 bg-bg-elevated rounded-lg">
                    <div className="w-7 h-7 bg-accent/20 text-accent rounded-lg flex items-center justify-center text-sm font-bold shrink-0">
                      {i + 1}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-white">{rec.action}</p>
                      <p className="text-xs text-slate-400 mt-0.5">{rec.reason}</p>
                    </div>
                  </div>
                ))}
                {(a?.recommendations ?? []).length === 0 && (
                  <p className="text-sm text-slate-500">No recommendations yet — trade more to get insights</p>
                )}
              </div>
            </div>

            {/* Correlation Heatmap */}
            {corrData && corrData.tickers.length >= 2 && (
              <div className="card p-5">
                <div className="flex items-center gap-2 mb-4">
                  <Activity size={16} className="text-accent" />
                  <h3 className="text-sm font-semibold text-white">Position Correlation Matrix</h3>
                  <span className="text-xs text-slate-500 ml-1">(3-month daily returns)</span>
                </div>
                <div className="overflow-x-auto">
                  <div
                    className="grid gap-0.5"
                    style={{
                      display: "grid",
                      gridTemplateColumns: `80px repeat(${corrData.tickers.length}, minmax(52px, 1fr))`,
                    }}
                  >
                    {/* Header row */}
                    <div /> {/* empty corner */}
                    {corrData.tickers.map(t => (
                      <div key={t} className="text-center text-xs font-mono text-slate-400 pb-1 font-medium">{t}</div>
                    ))}
                    {/* Data rows */}
                    {corrData.tickers.map(rowTicker => (
                      <>
                        <div key={`label-${rowTicker}`} className="text-xs font-mono text-slate-400 flex items-center pr-2 font-medium">{rowTicker}</div>
                        {corrData.tickers.map(colTicker => {
                          const cell = corrData.matrix.find(m => m.x === colTicker && m.y === rowTicker);
                          const v = cell?.value ?? 0;
                          const isDiag = rowTicker === colTicker;
                          // Color: -1 = blue, 0 = neutral, +1 = red (high correlation = risk)
                          const bg = isDiag
                            ? "bg-bg-elevated"
                            : v > 0.7 ? "bg-loss/60"
                            : v > 0.4 ? "bg-warn/30"
                            : v > 0 ? "bg-bg-elevated"
                            : "bg-accent/20";
                          return (
                            <div
                              key={`${rowTicker}-${colTicker}`}
                              className={`${bg} rounded-sm flex items-center justify-center text-xs font-mono py-2`}
                              title={`${rowTicker} × ${colTicker}: ${v.toFixed(2)}`}
                            >
                              <span className={isDiag ? "text-slate-500" : v > 0.7 ? "text-loss font-bold" : v < 0 ? "text-accent" : "text-slate-300"}>
                                {isDiag ? "—" : v.toFixed(2)}
                              </span>
                            </div>
                          );
                        })}
                      </>
                    ))}
                  </div>
                </div>
                <p className="text-xs text-slate-500 mt-3">Red = high correlation (&gt;0.7) = concentrated risk. Blue = negative correlation = diversified.</p>
              </div>
            )}

            {/* Sector Exposure */}
            {sectorData && sectorData.sectors.length > 0 && (
              <div className="card p-5">
                <div className="flex items-center gap-2 mb-4">
                  <PieChart size={16} className="text-accent" />
                  <h3 className="text-sm font-semibold text-white">Sector Exposure</h3>
                  <span className="text-xs text-slate-500 ml-1">Total: ${sectorData.total_value.toLocaleString()}</span>
                </div>
                <div className="space-y-2">
                  {sectorData.sectors.map((s, i) => {
                    const COLORS = ["#2D7DD2","#00E676","#FFB740","#FF3D57","#7C5CBF","#4D6080","#4A9AEF"];
                    const color = COLORS[i % COLORS.length];
                    return (
                      <div key={s.sector} className="flex items-center gap-3">
                        <div className="w-24 text-xs font-medium text-slate-300 shrink-0">{s.sector}</div>
                        <div className="flex-1 bg-bg-elevated rounded-full h-2 overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{ width: `${s.pct}%`, backgroundColor: color }}
                          />
                        </div>
                        <div className="w-20 text-right">
                          <span className="text-xs font-mono text-slate-300">{s.pct.toFixed(1)}%</span>
                          <span className="text-xs text-slate-500 ml-1">${(s.value/1000).toFixed(1)}k</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
                {sectorData.sectors[0]?.pct > 60 && (
                  <p className="text-xs text-warn mt-3 flex items-center gap-1">
                    <span>⚠</span> High concentration in {sectorData.sectors[0].sector} ({sectorData.sectors[0].pct.toFixed(0)}%). Consider diversifying.
                  </p>
                )}
              </div>
            )}

          </motion.div>
        </AnimatePresence>
      )}
    </div>
  );
}
