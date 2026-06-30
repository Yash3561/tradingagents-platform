import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Radar, Play, RefreshCw, Loader2, TrendingUp, TrendingDown, Minus, Zap, CheckCircle2, XCircle, Clock } from "lucide-react";
import { api, WS_BASE } from "../../lib/api";
import { cn } from "../../lib/cn";

interface ScreenedStock {
  ticker: string;
  score: number;
  direction: "BUY" | "SELL" | "NEUTRAL";
  current_price: number;
  rsi: number;
  ma50: number;
  ma200: number;
  above_ma50: boolean;
  above_ma200: boolean;
  macd_bullish: boolean;
  mom_1w_pct: number;
  mom_1m_pct: number;
  mom_3m_pct: number;
  vol_ratio: number;
}

interface ScanResult {
  ticker: string;
  run_id: string;
  status: "completed" | "failed";
  error?: string;
}

interface ScanSummary {
  status: string;
  screened: number;
  candidates_analyzed: number;
  trades_placed: number;
  duration_s: number;
  results: ScanResult[];
  pre_screen: ScreenedStock[];
}

const DIR_STYLE: Record<string, string> = {
  BUY: "text-gain bg-gain/10 border-gain/30",
  SELL: "text-loss bg-loss/10 border-loss/30",
  NEUTRAL: "text-text-muted bg-bg-elevated border-border",
};

const DIR_ICON = {
  BUY: TrendingUp,
  SELL: TrendingDown,
  NEUTRAL: Minus,
};

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score));
  const color = pct > 62 ? "bg-gain" : pct < 40 ? "bg-loss" : "bg-warn";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className={cn("h-full rounded-full", color)}
        />
      </div>
      <span className="text-xs font-mono text-text-muted w-8 text-right">{score}</span>
    </div>
  );
}

function MomBadge({ value }: { value: number }) {
  const pos = value >= 0;
  return (
    <span className={cn("font-mono text-xs", pos ? "text-gain" : "text-loss")}>
      {pos ? "+" : ""}{value.toFixed(1)}%
    </span>
  );
}

export default function Scanner() {
  const [scanStatus, setScanStatus] = useState<"idle" | "prescreening" | "scanning" | "done" | "error">("idle");
  const [prescreen, setPrescreen] = useState<ScreenedStock[]>([]);
  const [scanSummary, setScanSummary] = useState<ScanSummary | null>(null);
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [activeTicker, setActiveTicker] = useState<string | null>(null);
  const [scanLog, setScanLog] = useState<string[]>([]);
  const [history, setHistory] = useState<{ ticker: string; decision: string | null; confidence: number | null; created_at: string }[]>([]);

  // Load recent agent runs from DB on mount (persists across refresh)
  useEffect(() => {
    api.get("/agents/runs?limit=30").then(({ data }) => {
      setHistory(data.map((r: any) => ({
        ticker: r.ticker,
        decision: r.decision,
        confidence: r.confidence,
        created_at: r.created_at,
      })));
    }).catch(() => {});
  }, []);
  const [maxCandidates, setMaxCandidates] = useState(8);

  const addLog = (msg: string) => setScanLog(prev => [...prev.slice(-19), msg]);

  const handlePrescreen = async () => {
    setScanStatus("prescreening");
    setPrescreen([]);
    setScanSummary(null);
    setScanLog([]);
    addLog("Running technical pre-screen on 40+ stocks...");
    try {
      const { data } = await api.get("/agents/scan/prescreen");
      setPrescreen(data);
      setScanStatus("idle");
      addLog(`Pre-screen complete — ${data.length} stocks scored`);
    } catch {
      setScanStatus("error");
      addLog("Pre-screen failed");
    }
  };

  const handleFullScan = async () => {
    setScanStatus("scanning");
    setScanSummary(null);
    setScanLog([]);
    setProgress({ current: 0, total: maxCandidates });
    addLog("Starting full market scan...");
    addLog("Step 1: Technical pre-screen (free, ~10s)");

    try {
      const { data } = await api.post("/agents/scan", { max_candidates: maxCandidates });
      const scanId = data.scan_id;

      addLog(`Scan started [${scanId.slice(0, 8)}]`);
      addLog("Step 2: AI pipeline on top candidates...");

      // Subscribe to WS for progress
      const ws = new WebSocket(`${WS_BASE}/scans/${scanId}`);
      let scanCompleted = false;

      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === "scan_progress") {
          setProgress({ current: msg.completed, total: msg.total });
          if (msg.stage === "starting") {
            setActiveTicker(msg.ticker);
            addLog(`[${msg.completed + 1}/${msg.total}] Running AI on ${msg.ticker}...`);
          } else if (msg.stage === "done") {
            setActiveTicker(null);
            addLog(`  ✓ ${msg.ticker} — ${msg.status}`);
          }
        } else if (msg.type === "scan_completed") {
          scanCompleted = true;
          setActiveTicker(null);
          setScanSummary(msg as ScanSummary);
          if (msg.pre_screen) setPrescreen(msg.pre_screen);
          setScanStatus("done");
          addLog(`Scan done — ${msg.candidates_analyzed} analyzed, ${msg.trades_placed} trades placed`);
          ws.close();
        } else if (msg.type === "scan_error") {
          scanCompleted = true;
          setActiveTicker(null);
          setScanStatus("error");
          addLog(`Error: ${msg.error}`);
          ws.close();
        }
      };

      ws.onerror = () => { if (!scanCompleted) pollScan(scanId); };
      ws.onclose = () => { if (!scanCompleted) pollScan(scanId); };

    } catch {
      setScanStatus("error");
      addLog("Failed to start scan");
    }
  };

  const pollScan = async (scanId: string, attempts = 0) => {
    if (attempts > 120) {
      setScanStatus("error");
      return;
    }
    // Backend broadcasts to WS — polling isn't straightforward here.
    // Since scan runs as background task, we just wait for WS.
    // If WS truly fails, show a manual refresh note.
    addLog("WebSocket disconnected — scan still running in background");
    addLog("Results will appear when backend completes.");
  };

  const handleReset = () => {
    setScanStatus("idle");
    setPrescreen([]);
    setScanSummary(null);
    setScanLog([]);
    setProgress({ current: 0, total: 0 });
    setActiveTicker(null);
  };

  const buys = prescreen.filter(s => s.direction === "BUY");
  const sells = prescreen.filter(s => s.direction === "SELL");

  return (
    <motion.div
      key="scanner"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-6"
    >
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary flex items-center gap-2">
            <Radar size={20} className="text-accent" />
            Market Scanner
          </h1>
          <p className="text-sm text-text-muted mt-0.5">
            Scans 40+ stocks, pre-screens with technicals, runs AI on top candidates, auto-executes
          </p>
        </div>
      </div>

      {/* Controls */}
      <div className="card p-5 flex items-end gap-4 flex-wrap">
        <div>
          <label className="metric-label block mb-2">AI Candidates</label>
          <select
            value={maxCandidates}
            onChange={e => setMaxCandidates(+e.target.value)}
            disabled={scanStatus === "scanning"}
            className="px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary
                       focus:outline-none focus:border-accent transition-colors"
          >
            {[4, 6, 8, 10, 12].map(n => (
              <option key={n} value={n}>{n} stocks through AI</option>
            ))}
          </select>
        </div>

        <button
          onClick={handlePrescreen}
          disabled={scanStatus === "prescreening" || scanStatus === "scanning"}
          className={cn(
            "flex items-center gap-2 px-4 py-2 rounded-lg font-semibold text-sm transition-all duration-200 border",
            scanStatus === "prescreening"
              ? "border-accent/40 text-accent cursor-not-allowed bg-accent/5"
              : "border-border hover:border-accent/50 text-text-secondary hover:text-text-primary bg-bg-elevated",
          )}
        >
          {scanStatus === "prescreening" ? (
            <><Loader2 size={15} className="animate-spin" /> Screening...</>
          ) : (
            <><RefreshCw size={15} /> Quick Screen</>
          )}
        </button>

        <button
          onClick={handleFullScan}
          disabled={scanStatus === "prescreening" || scanStatus === "scanning"}
          className={cn(
            "flex items-center gap-2 px-5 py-2 rounded-lg font-semibold text-sm transition-all duration-200",
            scanStatus === "scanning"
              ? "bg-accent/20 text-accent cursor-not-allowed"
              : "bg-accent hover:bg-accent/80 text-white shadow-[0_0_20px_rgba(45,125,210,0.4)]",
          )}
        >
          {scanStatus === "scanning" ? (
            <><Loader2 size={16} className="animate-spin" /> Scanning Market...</>
          ) : (
            <><Zap size={16} /> Full Scan + Trade</>
          )}
        </button>

        {scanStatus !== "idle" && (
          <button
            onClick={handleReset}
            className="p-2 rounded-lg border border-border hover:bg-bg-elevated text-text-muted hover:text-text-primary transition-colors"
          >
            <RefreshCw size={16} />
          </button>
        )}
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Pre-screen results */}
        <div className="col-span-2 space-y-4">
          {/* Summary stats */}
          {prescreen.length > 0 && (
            <div className="grid grid-cols-3 gap-3">
              <div className="card p-4">
                <p className="metric-label">Screened</p>
                <p className="metric-value">{prescreen.length}</p>
                <p className="text-xs text-text-muted mt-0.5">stocks analyzed</p>
              </div>
              <div className="card p-4">
                <p className="metric-label">Buy Signals</p>
                <p className="metric-value text-gain">{buys.length}</p>
                <p className="text-xs text-text-muted mt-0.5">bullish setups</p>
              </div>
              <div className="card p-4">
                <p className="metric-label">Sell Signals</p>
                <p className="metric-value text-loss">{sells.length}</p>
                <p className="text-xs text-text-muted mt-0.5">bearish setups</p>
              </div>
            </div>
          )}

          {/* Scan complete summary */}
          {scanSummary && (
            <div className="card p-4 border-accent/30">
              <div className="flex items-center gap-2 mb-3">
                <CheckCircle2 size={16} className="text-gain" />
                <h3 className="text-sm font-semibold text-text-primary">Scan Complete</h3>
                <span className="ml-auto text-xs text-text-muted">{scanSummary.duration_s}s</span>
              </div>
              <div className="grid grid-cols-3 gap-3 mb-3">
                <div className="text-center">
                  <p className="text-lg font-bold font-mono text-text-primary">{scanSummary.candidates_analyzed}</p>
                  <p className="text-xs text-text-muted">AI analyzed</p>
                </div>
                <div className="text-center">
                  <p className="text-lg font-bold font-mono text-gain">{scanSummary.trades_placed}</p>
                  <p className="text-xs text-text-muted">trades placed</p>
                </div>
                <div className="text-center">
                  <p className="text-lg font-bold font-mono text-text-secondary">{scanSummary.screened}</p>
                  <p className="text-xs text-text-muted">stocks screened</p>
                </div>
              </div>
              {scanSummary.results?.length > 0 && (
                <div className="space-y-1">
                  {scanSummary.results.map(r => (
                    <div key={r.run_id} className="flex items-center gap-2 text-xs">
                      {r.status === "completed"
                        ? <CheckCircle2 size={12} className="text-gain" />
                        : <XCircle size={12} className="text-loss" />}
                      <span className="font-mono font-semibold text-text-primary">{r.ticker}</span>
                      <span className={cn("ml-auto", r.status === "completed" ? "text-gain" : "text-loss")}>
                        {r.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Stock table */}
          {prescreen.length > 0 ? (
            <div className="card overflow-hidden">
              <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                <h3 className="text-sm font-semibold text-text-primary">Technical Pre-Screen</h3>
                <span className="text-xs text-text-muted">Score = opportunity strength</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left px-4 py-2 text-text-muted font-medium">Ticker</th>
                      <th className="text-left px-4 py-2 text-text-muted font-medium">Dir</th>
                      <th className="text-left px-4 py-2 text-text-muted font-medium w-28">Score</th>
                      <th className="text-right px-4 py-2 text-text-muted font-medium">Price</th>
                      <th className="text-right px-4 py-2 text-text-muted font-medium">RSI</th>
                      <th className="text-right px-4 py-2 text-text-muted font-medium">1W</th>
                      <th className="text-right px-4 py-2 text-text-muted font-medium">1M</th>
                      <th className="text-right px-4 py-2 text-text-muted font-medium">3M</th>
                      <th className="text-center px-4 py-2 text-text-muted font-medium">MACD</th>
                      <th className="text-right px-4 py-2 text-text-muted font-medium">Vol×</th>
                    </tr>
                  </thead>
                  <tbody>
                    <AnimatePresence>
                      {prescreen.map((s, i) => {
                        const DirIcon = DIR_ICON[s.direction];
                        return (
                          <motion.tr
                            key={s.ticker}
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: i * 0.02 }}
                            className="border-b border-border/50 hover:bg-bg-elevated/50 transition-colors"
                          >
                            <td className="px-4 py-2.5 font-mono font-bold text-text-primary">{s.ticker}</td>
                            <td className="px-4 py-2.5">
                              <span className={cn(
                                "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-semibold border",
                                DIR_STYLE[s.direction]
                              )}>
                                <DirIcon size={9} />
                                {s.direction}
                              </span>
                            </td>
                            <td className="px-4 py-2.5 w-28">
                              <ScoreBar score={s.score} />
                            </td>
                            <td className="px-4 py-2.5 text-right font-mono text-text-primary">
                              ${s.current_price.toLocaleString()}
                            </td>
                            <td className={cn(
                              "px-4 py-2.5 text-right font-mono",
                              s.rsi < 35 ? "text-gain" : s.rsi > 70 ? "text-loss" : "text-text-secondary"
                            )}>
                              {s.rsi}
                            </td>
                            <td className="px-4 py-2.5 text-right"><MomBadge value={s.mom_1w_pct} /></td>
                            <td className="px-4 py-2.5 text-right"><MomBadge value={s.mom_1m_pct} /></td>
                            <td className="px-4 py-2.5 text-right"><MomBadge value={s.mom_3m_pct} /></td>
                            <td className="px-4 py-2.5 text-center">
                              <span className={s.macd_bullish ? "text-gain" : "text-loss"}>
                                {s.macd_bullish ? "▲" : "▼"}
                              </span>
                            </td>
                            <td className={cn(
                              "px-4 py-2.5 text-right font-mono",
                              s.vol_ratio > 1.5 ? "text-gain" : s.vol_ratio < 0.7 ? "text-text-muted" : "text-text-secondary"
                            )}>
                              {s.vol_ratio}x
                            </td>
                          </motion.tr>
                        );
                      })}
                    </AnimatePresence>
                  </tbody>
                </table>
              </div>
            </div>
          ) : scanStatus === "idle" ? (
            <div className="card p-12 flex flex-col items-center justify-center text-center">
              <Radar size={40} className="text-text-muted/30 mb-4" />
              <p className="text-sm text-text-muted">No scan data yet.</p>
              <p className="text-xs text-text-muted mt-1">
                Click <strong className="text-text-secondary">Quick Screen</strong> to see technical signals,
                or <strong className="text-text-secondary">Full Scan + Trade</strong> to run AI and auto-place trades.
              </p>
            </div>
          ) : null}
        </div>

        {/* Right panel: scan log + legend */}
        <div className="space-y-4">
          {/* Scan log */}
          <div className="card p-4 flex flex-col h-64">
            <div className="flex items-center gap-2 mb-3">
              <Clock size={14} className="text-text-muted" />
              <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wide">Scan Log</h3>
              {(scanStatus === "prescreening" || scanStatus === "scanning") && (
                <Loader2 size={12} className="animate-spin text-accent ml-auto" />
              )}
              {scanStatus === "scanning" && progress.total > 0 && (
                <span className="text-2xs text-accent font-mono ml-1">
                  {progress.current}/{progress.total}
                </span>
              )}
              {scanStatus === "done" && (
                <CheckCircle2 size={12} className="text-gain ml-auto" />
              )}
              {scanStatus === "error" && (
                <XCircle size={12} className="text-loss ml-auto" />
              )}
            </div>
            {/* Progress bar */}
            {scanStatus === "scanning" && progress.total > 0 && (
              <div className="mb-2">
                <div className="flex justify-between text-2xs text-text-muted mb-1">
                  <span>{activeTicker ? `Analyzing ${activeTicker}...` : "Waiting..."}</span>
                  <span>{progress.current}/{progress.total} stocks</span>
                </div>
                <div className="h-1 bg-bg-elevated rounded-full overflow-hidden">
                  <motion.div
                    animate={{ width: `${(progress.current / progress.total) * 100}%` }}
                    transition={{ duration: 0.4 }}
                    className="h-full bg-accent rounded-full"
                  />
                </div>
              </div>
            )}
            <div className="flex-1 overflow-y-auto space-y-1 font-mono text-xs text-text-muted">
              {scanLog.length === 0 ? (
                <p className="text-text-muted/50">Waiting for scan...</p>
              ) : (
                scanLog.map((line, i) => (
                  <motion.p
                    key={i}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="leading-relaxed"
                  >
                    <span className="text-text-muted/40 mr-1">›</span>
                    {line}
                  </motion.p>
                ))
              )}
            </div>
          </div>

          {/* Legend */}
          <div className="card p-4 space-y-3">
            <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wide">How It Works</h3>
            <div className="space-y-2 text-xs text-text-muted">
              <div className="flex items-start gap-2">
                <span className="text-accent font-bold mt-0.5">1</span>
                <p><strong className="text-text-secondary">Pre-screen</strong> — scores 40+ stocks with RSI, MACD, MA trend, momentum, volume (free, no AI)</p>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-accent font-bold mt-0.5">2</span>
                <p><strong className="text-text-secondary">AI Pipeline</strong> — top {maxCandidates} go through full 7-agent debate (Technical + Sentiment + News + Fundamental → Research → Risk → PM)</p>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-accent font-bold mt-0.5">3</span>
                <p><strong className="text-text-secondary">Auto-Execute</strong> — approved trades placed on Alpaca paper account instantly</p>
              </div>
            </div>
            <div className="pt-2 border-t border-border space-y-1.5">
              <p className="text-2xs text-text-muted/60 uppercase tracking-wide font-medium">Score Guide</p>
              <div className="flex items-center gap-2 text-xs">
                <div className="w-2 h-2 rounded-full bg-gain" />
                <span className="text-text-muted">62+ = Strong BUY candidate</span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <div className="w-2 h-2 rounded-full bg-warn" />
                <span className="text-text-muted">40–62 = Neutral / Watch</span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <div className="w-2 h-2 rounded-full bg-loss" />
                <span className="text-text-muted">&lt;40 = Bearish / SELL</span>
              </div>
            </div>
          </div>

          {/* Status */}
          {scanStatus !== "idle" && (
            <div className={cn(
              "card p-4 border",
              scanStatus === "done" ? "border-gain/30 bg-gain/5" :
              scanStatus === "error" ? "border-loss/30 bg-loss/5" :
              "border-accent/30 bg-accent/5"
            )}>
              <div className="flex items-center gap-2">
                {scanStatus === "done" ? <CheckCircle2 size={14} className="text-gain" /> :
                 scanStatus === "error" ? <XCircle size={14} className="text-loss" /> :
                 <Loader2 size={14} className="animate-spin text-accent" />}
                <span className={cn(
                  "text-xs font-semibold",
                  scanStatus === "done" ? "text-gain" :
                  scanStatus === "error" ? "text-loss" : "text-accent"
                )}>
                  {scanStatus === "prescreening" ? "Pre-screening..." :
                   scanStatus === "scanning" ? "Running AI scan..." :
                   scanStatus === "done" ? "Scan complete" :
                   "Scan failed"}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Past Analysis — persists across refresh, loaded from DB */}
      {history.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <h3 className="text-sm font-semibold text-text-primary">Past Analysis</h3>
            <span className="text-xs text-text-muted">From database — survives refresh &amp; restart</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-4 py-2 text-text-muted font-medium">Ticker</th>
                  <th className="text-left px-4 py-2 text-text-muted font-medium">Decision</th>
                  <th className="text-left px-4 py-2 text-text-muted font-medium">Confidence</th>
                  <th className="text-left px-4 py-2 text-text-muted font-medium">Time</th>
                </tr>
              </thead>
              <tbody>
                {history.map((r, i) => (
                  <tr key={i} className="border-b border-border/40 hover:bg-bg-elevated/40 transition-colors">
                    <td className="px-4 py-2 font-mono font-bold text-text-primary">{r.ticker}</td>
                    <td className="px-4 py-2">
                      <span className={cn(
                        "px-1.5 py-0.5 rounded text-2xs font-semibold border",
                        r.decision === "BUY" ? "text-gain bg-gain/10 border-gain/30" :
                        r.decision === "SELL" ? "text-loss bg-loss/10 border-loss/30" :
                        "text-text-muted bg-bg-elevated border-border"
                      )}>
                        {r.decision ?? "HOLD"}
                      </span>
                    </td>
                    <td className="px-4 py-2 font-mono text-text-secondary">
                      {r.confidence != null ? `${Math.round(r.confidence * 100)}%` : "—"}
                    </td>
                    <td className="px-4 py-2 text-text-muted">
                      {new Date(r.created_at).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
                      {" · "}
                      {new Date(r.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </motion.div>
  );
}
