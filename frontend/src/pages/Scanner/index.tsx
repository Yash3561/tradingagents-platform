import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Radar, Play, RefreshCw, Loader2, TrendingUp, TrendingDown, Minus, Zap, CheckCircle2, XCircle, Clock, BarChart2, Brain, SlidersHorizontal, ChevronDown } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api, wsUrl } from "../../lib/api";
import { cn } from "../../lib/cn";
import { TermTooltip } from "../../components/ui/Tooltip";

interface ScreenedStock {
  ticker: string; score: number; direction: "BUY" | "SELL" | "NEUTRAL";
  current_price: number; rsi: number; ma50: number; ma200: number;
  above_ma50: boolean; above_ma200: boolean; macd_bullish: boolean;
  mom_1w_pct: number; mom_1m_pct: number; mom_3m_pct: number; vol_ratio: number;
}

interface ScanResult { ticker: string; run_id: string; status: "completed" | "failed"; error?: string; }
interface ScanSummary {
  status: string; screened: number; candidates_analyzed: number;
  trades_placed: number; duration_s: number; results: ScanResult[]; pre_screen: ScreenedStock[];
}

// ── Scan criteria ─────────────────────────────────────────────────────────────
interface ScanCriteria {
  rsi_min?: number; rsi_max?: number;
  min_volume_ratio?: number; min_score?: number;
  directions?: string[];
  above_ma50?: boolean; above_ma200?: boolean; macd_bullish?: boolean;
}

const DEFAULT_CRITERIA: ScanCriteria = {};

// ── LocalStorage persistence ──────────────────────────────────────────────────
const CACHE_KEY = "scanner_state_v2";

interface ScannerCache {
  scanId: string | null;
  scanStatus: "idle" | "prescreening" | "scanning" | "done" | "error";
  scanLog: string[];
  prescreen: ScreenedStock[];
  scanSummary: ScanSummary | null;
  progress: { current: number; total: number };
  maxCandidates: number;
  startedAt: string | null;
}

const DEFAULT_CACHE: ScannerCache = {
  scanId: null, scanStatus: "idle", scanLog: [], prescreen: [],
  scanSummary: null, progress: { current: 0, total: 0 }, maxCandidates: 8, startedAt: null,
};

function loadCache(): ScannerCache {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    return raw ? { ...DEFAULT_CACHE, ...JSON.parse(raw) } : DEFAULT_CACHE;
  } catch { return DEFAULT_CACHE; }
}

function saveCache(state: Partial<ScannerCache>) {
  try {
    const current = loadCache();
    localStorage.setItem(CACHE_KEY, JSON.stringify({ ...current, ...state }));
  } catch {}
}

function clearScanCache() {
  saveCache({ scanId: null, scanStatus: "idle", scanLog: [], scanSummary: null,
               progress: { current: 0, total: 0 }, startedAt: null });
}

// ── Style constants ───────────────────────────────────────────────────────────
const DIR_STYLE: Record<string, string> = {
  BUY: "text-gain bg-gain/10 border-gain/30",
  SELL: "text-loss bg-loss/10 border-loss/30",
  NEUTRAL: "text-text-muted bg-bg-elevated border-border",
};
const DIR_ICON = { BUY: TrendingUp, SELL: TrendingDown, NEUTRAL: Minus };

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score));
  const color = pct > 62 ? "bg-gain" : pct < 40 ? "bg-loss" : "bg-warn";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
        <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }} className={cn("h-full rounded-full", color)} />
      </div>
      <span className="text-xs font-mono text-text-muted w-8 text-right">{score}</span>
    </div>
  );
}

function MomBadge({ value }: { value: number }) {
  return (
    <span className={cn("font-mono text-xs", value >= 0 ? "text-gain" : "text-loss")}>
      {value >= 0 ? "+" : ""}{value.toFixed(1)}%
    </span>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function Scanner() {
  const navigate = useNavigate();
  const cache = loadCache();

  const [scanStatus, setScanStatus] = useState<ScannerCache["scanStatus"]>(cache.scanStatus);
  const [prescreen, setPrescreen] = useState<ScreenedStock[]>(cache.prescreen);
  const [scanSummary, setScanSummary] = useState<ScanSummary | null>(cache.scanSummary);
  const [progress, setProgress] = useState(cache.progress);
  const [activeTicker, setActiveTicker] = useState<string | null>(null);
  const [scanLog, setScanLog] = useState<string[]>(cache.scanLog);
  const [maxCandidates, setMaxCandidates] = useState(cache.maxCandidates);
  const [criteria, setCriteria] = useState<ScanCriteria>(DEFAULT_CRITERIA);
  const [showCriteria, setShowCriteria] = useState(false);
  const [history, setHistory] = useState<{ ticker: string; decision: string | null; confidence: number | null; created_at: string }[]>([]);
  const [names, setNames] = useState<Record<string, { name: string; sector: string }>>({});

  const fetchNames = async (tickers: string[]) => {
    if (!tickers.length) return;
    const unique = [...new Set(tickers)].filter(Boolean);
    try {
      const { data } = await api.get(`/market/names?tickers=${unique.join(',')}`);
      setNames(prev => ({ ...prev, ...data }));
    } catch {}
  };

  const scanIdRef = useRef<string | null>(cache.scanId);
  const wsRef = useRef<WebSocket | null>(null);
  const scanCompletedRef = useRef(cache.scanStatus !== "scanning");

  const addLog = (msg: string) => {
    setScanLog(prev => {
      const next = [...prev.slice(-29), msg];
      saveCache({ scanLog: next });
      return next;
    });
  };

  // ── Persist state to localStorage on every change ──────────────────────────
  useEffect(() => { saveCache({ scanStatus, prescreen, scanSummary, progress, maxCandidates }); },
    [scanStatus, prescreen, scanSummary, progress, maxCandidates]);

  // ── Load history from DB on mount ─────────────────────────────────────────
  useEffect(() => {
    api.get("/agents/runs?limit=30").then(({ data }) => {
      setHistory(data.map((r: any) => ({
        ticker: r.ticker, decision: r.decision,
        confidence: r.confidence, created_at: r.created_at,
      })));
    }).catch(() => {});
  }, []);

  // ── On mount: reconnect WS if scan was running when user left ─────────────
  useEffect(() => {
    const cached = loadCache();
    if (cached.scanStatus !== "scanning" || !cached.scanId) return;

    // Scan was in progress when user navigated away — reconnect
    const scanId = cached.scanId;
    scanIdRef.current = scanId;
    scanCompletedRef.current = false;

    addLog("Reconnecting to running scan...");

    const ws = new WebSocket(wsUrl(`/scans/${scanId}`));
    wsRef.current = ws;

    ws.onopen = () => addLog("Reconnected — waiting for results...");

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      handleWsMessage(msg, ws, scanId);
    };

    ws.onerror = () => {
      // Scan may have completed while we were away — poll backend for results
      if (!scanCompletedRef.current) pollForScanResult(scanId);
    };

    ws.onclose = () => {
      if (!scanCompletedRef.current) pollForScanResult(scanId);
    };

    return () => { ws.close(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── WS message handler (shared between new scan and reconnect) ────────────
  const handleWsMessage = (msg: any, ws: WebSocket, scanId: string) => {
    if (msg.type === "scan_progress") {
      setProgress({ current: msg.completed, total: msg.total });
      saveCache({ progress: { current: msg.completed, total: msg.total }, scanId });
      if (msg.stage === "starting") {
        setActiveTicker(msg.ticker);
        addLog(`[${msg.completed + 1}/${msg.total}] Running AI on ${msg.ticker}...`);
      } else if (msg.stage === "done") {
        setActiveTicker(null);
        addLog(`  ✓ ${msg.ticker} — ${msg.status}`);
      }
    } else if (msg.type === "scan_completed") {
      scanCompletedRef.current = true;
      setActiveTicker(null);
      setScanSummary(msg as ScanSummary);
      if (msg.pre_screen) {
        setPrescreen(msg.pre_screen);
        fetchNames(msg.pre_screen.map((s: ScreenedStock) => s.ticker));
        saveCache({ prescreen: msg.pre_screen });
      }
      setScanStatus("done");
      saveCache({ scanStatus: "done", scanId: null, scanSummary: msg as ScanSummary });
      addLog(`✓ Scan done — ${msg.candidates_analyzed} analyzed, ${msg.trades_placed} trades placed`);
      // Refresh history
      api.get("/agents/runs?limit=30").then(({ data }) => {
        setHistory(data.map((r: any) => ({ ticker: r.ticker, decision: r.decision, confidence: r.confidence, created_at: r.created_at })));
      }).catch(() => {});
      ws.close();
    } else if (msg.type === "scan_error") {
      scanCompletedRef.current = true;
      setActiveTicker(null);
      setScanStatus("error");
      saveCache({ scanStatus: "error", scanId: null });
      addLog(`✗ Error: ${msg.error}`);
      ws.close();
    }
  };

  // ── Poll backend when WS fails (scan may have finished while disconnected) ─
  const pollForScanResult = async (scanId: string, attempts = 0) => {
    if (scanCompletedRef.current || attempts > 24) return;
    try {
      // Fetch recent completed runs — if we see runs that completed after scan start, it's done
      const { data } = await api.get("/agents/runs?limit=10");
      const recentCompleted = data.filter((r: any) => r.status === "completed");
      if (recentCompleted.length > 0) {
        setScanStatus("done");
        saveCache({ scanStatus: "done", scanId: null });
        addLog(`✓ Scan completed (recovered from disconnect) — ${recentCompleted.length} runs done`);
        api.get("/agents/runs?limit=30").then(({ data: runs }) => {
          setHistory(runs.map((r: any) => ({ ticker: r.ticker, decision: r.decision, confidence: r.confidence, created_at: r.created_at })));
        }).catch(() => {});
        scanCompletedRef.current = true;
      } else {
        setTimeout(() => pollForScanResult(scanId, attempts + 1), 5000);
      }
    } catch {
      setTimeout(() => pollForScanResult(scanId, attempts + 1), 5000);
    }
  };

  // ── Quick pre-screen (no AI, no cost) ────────────────────────────────────
  const handlePrescreen = async () => {
    setScanStatus("prescreening");
    setPrescreen([]);
    setScanSummary(null);
    setScanLog([]);
    saveCache({ scanStatus: "prescreening", prescreen: [], scanSummary: null, scanLog: [] });
    addLog("Running technical pre-screen on 40+ stocks...");
    try {
      const { data } = await api.get("/agents/scan/prescreen");
      setPrescreen(data);
      fetchNames(data.map((s: ScreenedStock) => s.ticker));
      setScanStatus("idle");
      saveCache({ prescreen: data, scanStatus: "idle" });
      addLog(`Pre-screen complete — ${data.length} stocks scored`);
    } catch {
      setScanStatus("error");
      addLog("Pre-screen failed");
    }
  };

  // ── Full scan + trade ─────────────────────────────────────────────────────
  const handleFullScan = async () => {
    setScanStatus("scanning");
    setScanSummary(null);
    setScanLog([]);
    setProgress({ current: 0, total: maxCandidates });
    scanCompletedRef.current = false;

    const startedAt = new Date().toISOString();
    addLog("Starting full market scan...");
    addLog("Step 1: Technical pre-screen (free, ~10s)");

    try {
      const { data } = await api.post("/agents/scan", {
        max_candidates: maxCandidates,
        criteria: Object.keys(criteria).length > 0 ? criteria : undefined,
      });
      const scanId = data.scan_id;
      scanIdRef.current = scanId;

      saveCache({ scanId, scanStatus: "scanning", scanSummary: null,
                  progress: { current: 0, total: maxCandidates }, startedAt });

      addLog(`Scan started [${scanId.slice(0, 8)}]`);
      addLog("Step 2: AI pipeline on top candidates...");
      addLog("⚡ You can freely navigate — scan runs in background!");

      const ws = new WebSocket(wsUrl(`/scans/${scanId}`));
      wsRef.current = ws;

      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        handleWsMessage(msg, ws, scanId);
      };

      ws.onerror = () => { if (!scanCompletedRef.current) pollForScanResult(scanId); };
      ws.onclose = () => { if (!scanCompletedRef.current) pollForScanResult(scanId); };

    } catch {
      setScanStatus("error");
      saveCache({ scanStatus: "error" });
      addLog("Failed to start scan");
    }
  };

  const handleReset = () => {
    wsRef.current?.close();
    setScanStatus("idle");
    setPrescreen([]);
    setScanSummary(null);
    setScanLog([]);
    setProgress({ current: 0, total: 0 });
    setActiveTicker(null);
    clearScanCache();
  };

  const buys = prescreen.filter(s => s.direction === "BUY");
  const sells = prescreen.filter(s => s.direction === "SELL");

  return (
    <motion.div key="scanner" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      exit={{ opacity: 0 }} transition={{ duration: 0.25 }} className="space-y-6">

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
        {/* Global in-progress banner */}
        {scanStatus === "scanning" && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-accent/10 border border-accent/30">
            <Loader2 size={13} className="animate-spin text-accent" />
            <span className="text-xs text-accent font-semibold">
              Scan running — {progress.current}/{progress.total || maxCandidates} stocks
            </span>
            <span className="text-xs text-text-muted">· safe to navigate away</span>
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="card p-5 flex items-end gap-4 flex-wrap">
        <div>
          <label className="metric-label block mb-2">AI Candidates</label>
          <select value={maxCandidates} onChange={e => setMaxCandidates(+e.target.value)}
            disabled={scanStatus === "scanning"}
            className="px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary
                       focus:outline-none focus:border-accent transition-colors">
            {[4, 6, 8, 10, 12].map(n => (
              <option key={n} value={n}>{n} stocks through AI</option>
            ))}
          </select>
        </div>

        <button onClick={handlePrescreen}
          disabled={scanStatus === "prescreening" || scanStatus === "scanning"}
          className={cn(
            "flex items-center gap-2 px-4 py-2 rounded-lg font-semibold text-sm transition-all duration-200 border",
            scanStatus === "prescreening"
              ? "border-accent/40 text-accent cursor-not-allowed bg-accent/5"
              : "border-border hover:border-accent/50 text-text-secondary hover:text-text-primary bg-bg-elevated",
          )}>
          {scanStatus === "prescreening"
            ? <><Loader2 size={15} className="animate-spin" /> Screening...</>
            : <><RefreshCw size={15} /> Quick Screen</>}
        </button>

        <button onClick={handleFullScan}
          disabled={scanStatus === "prescreening" || scanStatus === "scanning"}
          className={cn(
            "flex items-center gap-2 px-5 py-2 rounded-lg font-semibold text-sm transition-all duration-200",
            scanStatus === "scanning"
              ? "bg-accent/20 text-accent cursor-not-allowed"
              : "bg-accent hover:bg-accent/80 text-white shadow-[0_0_20px_rgba(45,125,210,0.4)]",
          )}>
          {scanStatus === "scanning"
            ? <><Loader2 size={16} className="animate-spin" /> Scanning Market...</>
            : <><Zap size={16} /> Full Scan + Trade</>}
        </button>

          <button onClick={() => setShowCriteria(v => !v)}
          className={cn(
            "flex items-center gap-2 px-3 py-2 rounded-lg text-sm border transition-all",
            showCriteria || Object.keys(criteria).length > 0
              ? "border-accent/50 text-accent bg-accent/10"
              : "border-border text-text-muted hover:text-text-primary bg-bg-elevated"
          )}>
          <SlidersHorizontal size={14} />
          Filters
          {Object.keys(criteria).length > 0 && (
            <span className="ml-1 px-1.5 py-0.5 rounded-full text-2xs bg-accent text-white font-bold">
              {Object.keys(criteria).length}
            </span>
          )}
          <ChevronDown size={12} className={cn("transition-transform", showCriteria && "rotate-180")} />
        </button>

        {showCriteria && (
          <button onClick={() => setCriteria(DEFAULT_CRITERIA)}
            className="text-xs text-text-muted hover:text-loss transition-colors">
            Clear filters
          </button>
        )}

        {scanStatus !== "idle" && (
          <button onClick={handleReset}
            className="p-2 rounded-lg border border-border hover:bg-bg-elevated text-text-muted hover:text-text-primary transition-colors"
            title="Reset scanner">
            <RefreshCw size={16} />
          </button>
        )}
      </div>

      {/* Advanced Filters Panel */}
      <AnimatePresence>
        {showCriteria && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.2 }}
            className="card p-5 overflow-hidden">
            <p className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-4">
              Scan Criteria — only stocks matching ALL selected filters pass pre-screen
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {/* RSI Range */}
              <div>
                <label className="metric-label block mb-1.5">RSI Min</label>
                <input type="number" min={0} max={100} placeholder="e.g. 20"
                  value={criteria.rsi_min ?? ""}
                  onChange={e => setCriteria(c => ({ ...c, rsi_min: e.target.value ? +e.target.value : undefined }))}
                  className="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary
                             focus:outline-none focus:border-accent transition-colors font-mono" />
              </div>
              <div>
                <label className="metric-label block mb-1.5">RSI Max</label>
                <input type="number" min={0} max={100} placeholder="e.g. 35"
                  value={criteria.rsi_max ?? ""}
                  onChange={e => setCriteria(c => ({ ...c, rsi_max: e.target.value ? +e.target.value : undefined }))}
                  className="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary
                             focus:outline-none focus:border-accent transition-colors font-mono" />
              </div>
              {/* Volume ratio */}
              <div>
                <label className="metric-label block mb-1.5">Min Volume ×</label>
                <input type="number" min={0} step={0.1} placeholder="e.g. 1.5"
                  value={criteria.min_volume_ratio ?? ""}
                  onChange={e => setCriteria(c => ({ ...c, min_volume_ratio: e.target.value ? +e.target.value : undefined }))}
                  className="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary
                             focus:outline-none focus:border-accent transition-colors font-mono" />
              </div>
              {/* Min score */}
              <div>
                <label className="metric-label block mb-1.5">Min Score</label>
                <input type="number" min={0} max={100} placeholder="e.g. 60"
                  value={criteria.min_score ?? ""}
                  onChange={e => setCriteria(c => ({ ...c, min_score: e.target.value ? +e.target.value : undefined }))}
                  className="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary
                             focus:outline-none focus:border-accent transition-colors font-mono" />
              </div>
            </div>
            <div className="flex flex-wrap gap-3 mt-4">
              {/* Direction */}
              <div>
                <label className="metric-label block mb-1.5">Direction</label>
                <div className="flex gap-2">
                  {["BUY","SELL"].map(dir => (
                    <button key={dir} onClick={() => setCriteria(c => {
                      const cur = c.directions ?? [];
                      const next = cur.includes(dir) ? cur.filter(d => d !== dir) : [...cur, dir];
                      return { ...c, directions: next.length ? next : undefined };
                    })} className={cn(
                      "px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all",
                      (criteria.directions ?? []).includes(dir)
                        ? dir === "BUY" ? "bg-gain/20 border-gain/50 text-gain" : "bg-loss/20 border-loss/50 text-loss"
                        : "bg-bg-elevated border-border text-text-muted hover:border-accent/50"
                    )}>{dir}</button>
                  ))}
                </div>
              </div>
              {/* Boolean filters */}
              {([
                ["above_ma50", "Above MA50"],
                ["above_ma200", "Above MA200"],
                ["macd_bullish", "MACD Bullish"],
              ] as const).map(([key, label]) => (
                <div key={key}>
                  <label className="metric-label block mb-1.5">{label}</label>
                  <div className="flex gap-2">
                    {["Yes","No","Any"].map(v => (
                      <button key={v} onClick={() => setCriteria(c => ({
                        ...c, [key]: v === "Any" ? undefined : v === "Yes"
                      }))} className={cn(
                        "px-2.5 py-1.5 rounded-lg text-xs border transition-all",
                        (v === "Any" && criteria[key] === undefined) ||
                        (v === "Yes" && criteria[key] === true) ||
                        (v === "No" && criteria[key] === false)
                          ? "bg-accent/20 border-accent/50 text-accent font-semibold"
                          : "bg-bg-elevated border-border text-text-muted hover:border-accent/30"
                      )}>{v}</button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Pre-screen results */}
        <div className="lg:col-span-2 space-y-4">
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
                          <th className="px-4 py-2 text-text-muted font-medium text-left">Ticker</th>
                      <th className="px-4 py-2 text-text-muted font-medium text-left">Dir</th>
                      <th className="px-4 py-2 text-text-muted font-medium text-left w-28">
                        Score <TermTooltip term="score" />
                      </th>
                      <th className="px-4 py-2 text-text-muted font-medium text-right">Price</th>
                      <th className="px-4 py-2 text-text-muted font-medium text-right">
                        RSI <TermTooltip term="rsi" />
                      </th>
                      <th className="px-4 py-2 text-text-muted font-medium text-right">
                        1W <TermTooltip term="momentum" />
                      </th>
                      <th className="px-4 py-2 text-text-muted font-medium text-right">1M</th>
                      <th className="px-4 py-2 text-text-muted font-medium text-right">3M</th>
                      <th className="px-4 py-2 text-text-muted font-medium text-center">MACD</th>
                      <th className="px-4 py-2 text-text-muted font-medium text-right">
                        Vol× <TermTooltip term="vol_ratio" />
                      </th>
                      <th className="px-4 py-2 text-text-muted font-medium text-right w-20"></th>
                    </tr>
                  </thead>
                  <tbody>
                    <AnimatePresence>
                      {prescreen.map((s, i) => {
                        const DirIcon = DIR_ICON[s.direction];
                        return (
                          <motion.tr key={s.ticker} initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.02 }}
                            className="border-b border-border/50 hover:bg-bg-elevated/50 transition-colors">
                            <td className="px-4 py-2.5 text-left">
                              <button
                                onClick={() => navigate(`/markets?ticker=${s.ticker}`)}
                                className="font-mono font-bold text-text-primary hover:text-accent transition-colors"
                                title="View chart"
                              >{s.ticker}</button>
                              <p className="text-2xs text-text-muted font-normal mt-0.5">{names[s.ticker]?.name ?? ''}</p>
                            </td>
                            <td className="px-4 py-2.5 text-left">
                              <span className={cn("inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-semibold border", DIR_STYLE[s.direction])}>
                                <DirIcon size={9} />{s.direction}
                              </span>
                            </td>
                            <td className="px-4 py-2.5 w-28"><ScoreBar score={s.score} /></td>
                            <td className="px-4 py-2.5 text-right font-mono text-text-primary">${s.current_price.toLocaleString()}</td>
                            <td className={cn("px-4 py-2.5 text-right font-mono",
                              s.rsi < 35 ? "text-gain" : s.rsi > 70 ? "text-loss" : "text-text-secondary")}>
                              {s.rsi}
                            </td>
                            <td className="px-4 py-2.5 text-right"><MomBadge value={s.mom_1w_pct} /></td>
                            <td className="px-4 py-2.5 text-right"><MomBadge value={s.mom_1m_pct} /></td>
                            <td className="px-4 py-2.5 text-right"><MomBadge value={s.mom_3m_pct} /></td>
                            <td className="px-4 py-2.5 text-center">
                              <span className={s.macd_bullish ? "text-gain" : "text-loss"}>{s.macd_bullish ? "▲" : "▼"}</span>
                            </td>
                            <td className={cn("px-4 py-2.5 text-right font-mono",
                              s.vol_ratio > 1.5 ? "text-gain" : s.vol_ratio < 0.7 ? "text-text-muted" : "text-text-secondary")}>
                              {s.vol_ratio}x
                            </td>
                            <td className="px-4 py-2.5 text-right">
                              <div className="flex items-center justify-end gap-1">
                                <button
                                  onClick={() => navigate(`/markets?ticker=${s.ticker}`)}
                                  title="View chart"
                                  className="p-1 rounded text-slate-500 hover:text-accent hover:bg-accent/10 transition-colors"
                                >
                                  <BarChart2 size={12} />
                                </button>
                                <button
                                  onClick={() => navigate(`/agents?ticker=${s.ticker}`)}
                                  title="Analyze with AI"
                                  className="p-1 rounded text-slate-500 hover:text-gain hover:bg-gain/10 transition-colors"
                                >
                                  <Brain size={12} />
                                </button>
                              </div>
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

        {/* Right panel */}
        <div className="space-y-4">
          <div className="card p-4 flex flex-col h-72">
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
              {scanStatus === "done" && <CheckCircle2 size={12} className="text-gain ml-auto" />}
              {scanStatus === "error" && <XCircle size={12} className="text-loss ml-auto" />}
            </div>
            {scanStatus === "scanning" && progress.total > 0 && (
              <div className="mb-2">
                <div className="flex justify-between text-2xs text-text-muted mb-1">
                  <span>{activeTicker ? `Analyzing ${activeTicker}...` : "Waiting..."}</span>
                  <span>{progress.current}/{progress.total} stocks</span>
                </div>
                <div className="h-1 bg-bg-elevated rounded-full overflow-hidden">
                  <motion.div animate={{ width: `${(progress.current / progress.total) * 100}%` }}
                    transition={{ duration: 0.4 }} className="h-full bg-accent rounded-full" />
                </div>
              </div>
            )}
            <div className="flex-1 overflow-y-auto space-y-1 font-mono text-xs text-text-muted">
              {scanLog.length === 0
                ? <p className="text-text-muted/50">Waiting for scan...</p>
                : scanLog.map((line, i) => (
                  <motion.p key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="leading-relaxed">
                    <span className="text-text-muted/40 mr-1">›</span>{line}
                  </motion.p>
                ))}
            </div>
          </div>

          <div className="card p-4 space-y-3">
            <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wide">How It Works</h3>
            <div className="space-y-2 text-xs text-text-muted">
              {[
                ["1", "Pre-screen", `scores 40+ stocks with RSI, MACD, MA trend, momentum, volume (free, no AI)`],
                ["2", "AI Pipeline", `top ${maxCandidates} go through full 7-agent debate (Technical + Sentiment + News + Fundamental → Research → Risk → PM)`],
                ["3", "Auto-Execute", `approved trades placed on Alpaca paper account instantly`],
              ].map(([n, title, desc]) => (
                <div key={n} className="flex items-start gap-2">
                  <span className="text-accent font-bold mt-0.5">{n}</span>
                  <p><strong className="text-text-secondary">{title}</strong> — {desc}</p>
                </div>
              ))}
            </div>
            <div className="pt-2 border-t border-border space-y-1.5">
              <p className="text-2xs text-text-muted/60 uppercase tracking-wide font-medium">Score Guide</p>
              {[["bg-gain", "62+ = Strong BUY candidate"], ["bg-warn", "40–62 = Neutral / Watch"], ["bg-loss", "<40 = Bearish / SELL"]].map(([c, l]) => (
                <div key={l} className="flex items-center gap-2 text-xs">
                  <div className={cn("w-2 h-2 rounded-full", c)} />
                  <span className="text-text-muted">{l}</span>
                </div>
              ))}
            </div>
          </div>

          {scanStatus !== "idle" && (
            <div className={cn("card p-4 border",
              scanStatus === "done" ? "border-gain/30 bg-gain/5" :
              scanStatus === "error" ? "border-loss/30 bg-loss/5" :
              "border-accent/30 bg-accent/5")}>
              <div className="flex items-center gap-2">
                {scanStatus === "done" ? <CheckCircle2 size={14} className="text-gain" /> :
                 scanStatus === "error" ? <XCircle size={14} className="text-loss" /> :
                 <Loader2 size={14} className="animate-spin text-accent" />}
                <span className={cn("text-xs font-semibold",
                  scanStatus === "done" ? "text-gain" : scanStatus === "error" ? "text-loss" : "text-accent")}>
                  {scanStatus === "prescreening" ? "Pre-screening..." :
                   scanStatus === "scanning" ? "Running AI scan — navigate freely" :
                   scanStatus === "done" ? "Scan complete" : "Scan failed"}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Past Analysis — loaded from DB */}
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
                  {["Ticker","Decision","Confidence","Time"].map(h => (
                    <th key={h} className="text-left px-4 py-2 text-text-muted font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {history.map((r, i) => (
                  <tr key={i} className="border-b border-border/40 hover:bg-bg-elevated/40 transition-colors">
                    <td className="px-4 py-2 font-mono font-bold text-text-primary">{r.ticker}</td>
                    <td className="px-4 py-2">
                      <span className={cn("px-1.5 py-0.5 rounded text-2xs font-semibold border",
                        r.decision === "BUY" ? "text-gain bg-gain/10 border-gain/30" :
                        r.decision === "SELL" ? "text-loss bg-loss/10 border-loss/30" :
                        "text-text-muted bg-bg-elevated border-border")}>
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
