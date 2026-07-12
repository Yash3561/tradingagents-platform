import { motion, AnimatePresence } from "framer-motion";
import { useState, useEffect, useRef, useCallback } from "react";
import { CheckCircle, KeyRound, Link2, Loader2, ShieldAlert, ShieldCheck, ShieldX, Unplug } from "lucide-react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { saveAuth } from "../../lib/auth";

// ── Helpers ───────────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-6 space-y-5">
      <h2 className="text-sm font-semibold text-text-primary border-b border-border pb-3">{title}</h2>
      {children}
    </div>
  );
}

function Field({ label, description, children }: { label: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-6">
      <div className="min-w-0">
        <p className="text-sm font-medium text-text-primary">{label}</p>
        {description && <p className="text-xs text-text-muted mt-0.5">{description}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

function Toggle({ enabled, onChange }: { enabled: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!enabled)}
      className={cn(
        "relative w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none",
        enabled ? "bg-accent" : "bg-bg-elevated border border-border"
      )}
    >
      <span
        className={cn(
          "absolute left-0 top-1 w-4 h-4 bg-white rounded-full shadow transition-transform duration-200",
          enabled ? "translate-x-6" : "translate-x-1"
        )}
      />
    </button>
  );
}

function SliderField({
  label,
  description,
  value,
  min,
  max,
  step,
  format,
  onChange,
}: {
  label: string;
  description?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  onChange: (v: number) => void;
}) {
  return (
    <Field label={label} description={description}>
      <div className="flex items-center gap-3">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={e => onChange(parseFloat(e.target.value))}
          className="w-36 accent-accent cursor-pointer"
        />
        <span className="text-sm font-mono font-semibold text-text-primary w-36 text-right whitespace-nowrap">
          {format(value)}
        </span>
      </div>
    </Field>
  );
}

// ── Default settings ───────────────────────────────────────────────────────────

// Keys match the backend settings store 1:1 — every control here drives real behavior.
const DEFAULTS = {
  // Risk Management
  position_size_pct: 5,
  position_size_high_conf: 7,
  stop_loss_pct: 7,
  take_profit_pct: 15,
  max_position_pct: 20,
  daily_loss_limit_pct: 3,
  // Strategy Engine
  strategy_mode: "agents",
  // AI Model
  llm_model: "deepseek-ai/deepseek-v4-flash",
  debate_rounds: 2,
  min_confidence_to_trade: 0.60,
  // Scanner
  scan_max_candidates: 8,
  scan_enabled: false,
  long_only: true,
  // Autonomous Agents
  intraday_monitor_enabled: true,
  overnight_agent_enabled: true,
  earnings_blackout_days: 5,
};

type Settings = typeof DEFAULTS;

// ── Circuit Breaker Display ────────────────────────────────────────────────────

interface SystemStatus {
  circuit_breakers: {
    blocked: boolean;
    reasons: string[];
    warnings: string[];
  };
  market_open: boolean;
  today_pnl_pct: number;
  positions_count: number;
}

function CBIndicator({ state }: { state: "green" | "amber" | "red" }) {
  if (state === "green") return <ShieldCheck size={16} className="text-gain" />;
  if (state === "amber") return <ShieldAlert size={16} className="text-warn" />;
  return <ShieldX size={16} className="text-loss" />;
}

function CircuitBreakers() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/system/status")
      .then(({ data }) => setStatus(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-xs text-text-muted">
        <Loader2 size={14} className="animate-spin" /> Loading circuit breakers...
      </div>
    );
  }

  if (!status) {
    return <p className="text-xs text-text-muted">Could not load circuit breaker status.</p>;
  }

  const cb = status.circuit_breakers;
  const overallState = cb.blocked ? "red" : cb.warnings.length > 0 ? "amber" : "green";
  const marketState: "green" | "amber" | "red" = status.market_open ? "green" : "amber";
  const pnlState: "green" | "amber" | "red" =
    status.today_pnl_pct < -2 ? "red" : status.today_pnl_pct < -1 ? "amber" : "green";

  return (
    <div className="space-y-3">
      <p className="text-xs text-text-muted">Read-only — circuit breakers fire automatically based on portfolio rules.</p>

      <div className="space-y-2">
        {/* Main breaker */}
        <div className="flex items-center justify-between py-2 px-3 bg-bg-elevated rounded-lg">
          <div className="flex items-center gap-2">
            <CBIndicator state={overallState} />
            <span className="text-sm text-text-primary">Trading Halt</span>
          </div>
          <span className={cn(
            "text-xs font-semibold",
            overallState === "green" ? "text-gain" : overallState === "amber" ? "text-warn" : "text-loss"
          )}>
            {cb.blocked ? "HALTED" : "CLEAR"}
          </span>
        </div>

        {/* Market open */}
        <div className="flex items-center justify-between py-2 px-3 bg-bg-elevated rounded-lg">
          <div className="flex items-center gap-2">
            <CBIndicator state={marketState} />
            <span className="text-sm text-text-primary">Market Status</span>
          </div>
          <span className={cn("text-xs font-semibold", status.market_open ? "text-gain" : "text-warn")}>
            {status.market_open ? "OPEN" : "CLOSED"}
          </span>
        </div>

        {/* Daily P&L */}
        <div className="flex items-center justify-between py-2 px-3 bg-bg-elevated rounded-lg">
          <div className="flex items-center gap-2">
            <CBIndicator state={pnlState} />
            <span className="text-sm text-text-primary">Daily P&L Limit</span>
          </div>
          <span className={cn(
            "text-xs font-mono font-semibold",
            status.today_pnl_pct >= 0 ? "text-gain" : "text-loss"
          )}>
            {status.today_pnl_pct >= 0 ? "+" : ""}{status.today_pnl_pct.toFixed(2)}%
          </span>
        </div>

        {/* Positions */}
        <div className="flex items-center justify-between py-2 px-3 bg-bg-elevated rounded-lg">
          <div className="flex items-center gap-2">
            <CBIndicator state="green" />
            <span className="text-sm text-text-primary">Open Positions</span>
          </div>
          <span className="text-xs font-mono font-semibold text-text-primary">
            {status.positions_count}
          </span>
        </div>
      </div>

      {/* Warnings / Reasons */}
      {cb.warnings.length > 0 && (
        <div className="space-y-1">
          {cb.warnings.map((w, i) => (
            <p key={i} className="text-xs text-warn flex items-start gap-1.5">
              <span className="shrink-0 mt-0.5">⚠</span>{w}
            </p>
          ))}
        </div>
      )}
      {cb.reasons.length > 0 && (
        <div className="space-y-1">
          {cb.reasons.map((r, i) => (
            <p key={i} className="text-xs text-loss flex items-start gap-1.5">
              <span className="shrink-0 mt-0.5">✕</span>{r}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Broker Connection ──────────────────────────────────────────────────────────

interface BrokerStatus {
  connected: boolean;
  account_number?: string;
  equity?: number;
  buying_power?: number;
  status?: string;
  last_verified_at?: string | null;
}

function BrokerConnection() {
  const [status, setStatus] = useState<BrokerStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api.get("/broker/status")
      .then(({ data }) => setStatus(data))
      .catch(() => setStatus({ connected: false }))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const connect = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post("/broker/connect", { api_key: apiKey, api_secret: apiSecret });
      setApiKey("");
      setApiSecret("");
      refresh();
    } catch (e: any) {
      setError(e.response?.data?.detail ?? "Connection failed — check your keys.");
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!window.confirm("Disconnect your Alpaca account? Stored keys will be deleted.")) return;
    setBusy(true);
    try {
      await api.delete("/broker/disconnect");
      setStatus({ connected: false });
    } catch {}
    setBusy(false);
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-xs text-text-muted">
        <Loader2 size={14} className="animate-spin" /> Loading broker status...
      </div>
    );
  }

  if (status?.connected) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between py-2 px-3 bg-bg-elevated rounded-lg">
          <div className="flex items-center gap-2">
            <ShieldCheck size={16} className="text-gain" />
            <span className="text-sm text-text-primary">Alpaca Paper Account</span>
            <span className="badge-gain text-[10px] px-1.5 py-0.5 rounded">PAPER</span>
          </div>
          <span className="text-xs font-mono text-text-primary">{status.account_number}</span>
        </div>

        {status.equity !== undefined && (
          <div className="grid grid-cols-2 gap-2">
            <div className="py-2 px-3 bg-bg-elevated rounded-lg">
              <p className="metric-label">Equity</p>
              <p className="text-sm font-mono font-semibold text-text-primary">
                ${status.equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </p>
            </div>
            <div className="py-2 px-3 bg-bg-elevated rounded-lg">
              <p className="metric-label">Buying Power</p>
              <p className="text-sm font-mono font-semibold text-text-primary">
                ${(status.buying_power ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </p>
            </div>
          </div>
        )}

        <button
          onClick={disconnect}
          disabled={busy}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-loss
                     bg-loss/10 hover:bg-loss/20 rounded-lg transition-colors disabled:opacity-50"
        >
          <Unplug size={12} /> Disconnect
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-text-muted">
        Connect your own Alpaca <span className="text-warn font-semibold">paper trading</span> account —
        the AI agents will analyze and place trades in it. Get free paper keys at{" "}
        <a href="https://app.alpaca.markets" target="_blank" rel="noreferrer" className="text-accent hover:underline">
          app.alpaca.markets
        </a>{" "}
        (select “Paper” in the top-left, then Generate API Keys). No real money is ever involved.
      </p>

      <div className="space-y-2">
        <input
          type="text"
          placeholder="API Key ID (starts with PK...)"
          value={apiKey}
          onChange={e => setApiKey(e.target.value)}
          className="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm font-mono
                     text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent"
        />
        <input
          type="password"
          placeholder="API Secret Key"
          value={apiSecret}
          onChange={e => setApiSecret(e.target.value)}
          className="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm font-mono
                     text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent"
        />
      </div>

      {error && <p className="text-xs text-loss">{typeof error === "string" ? error : JSON.stringify(error)}</p>}

      <button
        onClick={connect}
        disabled={busy || !apiKey.trim() || !apiSecret.trim()}
        className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-accent
                   hover:bg-accent/90 rounded-lg transition-colors disabled:opacity-50"
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Link2 size={14} />}
        {busy ? "Verifying with Alpaca..." : "Connect Paper Account"}
      </button>
    </div>
  );
}

// ── Main Settings Page ─────────────────────────────────────────────────────────

export default function Settings() {
  const [settings, setSettings] = useState<Settings>(DEFAULTS);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveStateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Watchlist state
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [watchlistCustom, setWatchlistCustom] = useState(false);
  const [newTicker, setNewTicker] = useState("");
  const [watchlistSaving, setWatchlistSaving] = useState(false);

  // Load settings on mount
  useEffect(() => {
    api.get("/settings/")
      .then(({ data }) => {
        setSettings(prev => ({ ...prev, ...data }));
      })
      .catch(() => {});

    api.get("/settings/watchlist").then(r => {
      setWatchlist(r.data.tickers);
      setWatchlistCustom(r.data.is_custom);
    }).catch(() => {});
  }, []);

  const persist = useCallback((patch: Partial<Settings>) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (saveStateTimer.current) clearTimeout(saveStateTimer.current);

    setSaveState("saving");

    debounceRef.current = setTimeout(async () => {
      try {
        await api.post("/settings/", patch);
        setSaveState("saved");
        saveStateTimer.current = setTimeout(() => setSaveState("idle"), 2500);
      } catch {
        setSaveState("idle");
      }
    }, 500);
  }, []);

  function update<K extends keyof Settings>(key: K, value: Settings[K]) {
    setSettings(prev => ({ ...prev, [key]: value }));
    persist({ [key]: value });
  }

  const addTicker = async () => {
    const t = newTicker.trim().toUpperCase();
    if (!t) return;
    try {
      const { data } = await api.post("/settings/watchlist/add", { ticker: t });
      setWatchlist(data.tickers);
      setWatchlistCustom(true);
      setNewTicker("");
    } catch {}
  };

  const removeTicker = async (ticker: string) => {
    try {
      const { data } = await api.delete(`/settings/watchlist/${ticker}`);
      setWatchlist(data.tickers);
    } catch {}
  };

  const resetWatchlist = async () => {
    try {
      const { data } = await api.post("/settings/watchlist/reset");
      setWatchlist(data.tickers);
      setWatchlistCustom(false);
    } catch {}
  };

  return (
    <motion.div
      key="settings"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-6 max-w-2xl"
    >
      {/* Page title + save indicator */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Settings</h1>
          <p className="text-sm text-text-muted mt-0.5">Configure risk, AI model, and agent behaviour</p>
        </div>

        <AnimatePresence>
          {saveState !== "idle" && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.2 }}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium",
                saveState === "saving"
                  ? "bg-accent/10 text-accent"
                  : "bg-gain/10 text-gain"
              )}
            >
              {saveState === "saving" ? (
                <><Loader2 size={12} className="animate-spin" /> Saving...</>
              ) : (
                <><CheckCircle size={12} /> Saved</>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Broker Connection ────────────────────────────────────────────────── */}
      <Section title="Broker Connection">
        <BrokerConnection />
      </Section>

      {/* ── Risk Management ─────────────────────────────────────────────────── */}
      <Section title="Risk Management">
        <SliderField
          label="Position Size (default)"
          description="% of portfolio per trade"
          value={settings.position_size_pct}
          min={1} max={10} step={0.5}
          format={v => `${v}% per trade`}
          onChange={v => update("position_size_pct", v)}
        />
        <SliderField
          label="Position Size (high confidence ≥70%)"
          description="Larger size when AI conviction is high"
          value={settings.position_size_high_conf}
          min={1} max={15} step={0.5}
          format={v => `${v}% per trade`}
          onChange={v => update("position_size_high_conf", v)}
        />
        <SliderField
          label="Stop Loss %"
          description="Auto-close position if it falls this far"
          value={settings.stop_loss_pct}
          min={3} max={15} step={0.5}
          format={v => `−${v}% stop`}
          onChange={v => update("stop_loss_pct", v)}
        />
        <SliderField
          label="Take Profit %"
          description="Auto-close position at this gain"
          value={settings.take_profit_pct}
          min={5} max={50} step={1}
          format={v => `+${v}% target`}
          onChange={v => update("take_profit_pct", v)}
        />
        <SliderField
          label="Max Single Position"
          description="Concentration warning — no single stock should exceed this"
          value={settings.max_position_pct}
          min={10} max={30} step={1}
          format={v => `${v}% max`}
          onChange={v => update("max_position_pct", v)}
        />
        <SliderField
          label="Daily Loss Limit"
          description="Circuit breaker — new trades halt if portfolio falls this much today"
          value={settings.daily_loss_limit_pct}
          min={1} max={10} step={0.5}
          format={v => `−${v}% halts trading`}
          onChange={v => update("daily_loss_limit_pct", v)}
        />
      </Section>

      {/* ── AI Model ────────────────────────────────────────────────────────── */}
      <Section title="AI Model">
        <Field
          label="Strategy Engine"
          description="AI Agents = full LLM debate pipeline. Quant Baseline = deterministic regime-filtered trend + mean-reversion rules (no AI credits) — the control group the agents must beat."
        >
          <select
            value={settings.strategy_mode}
            onChange={e => update("strategy_mode", e.target.value)}
            className="px-3 py-1.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary
                       focus:outline-none focus:border-accent transition-colors"
          >
            <option value="agents">AI Agents (LLM pipeline)</option>
            <option value="quant">Quant Baseline (rules only, free)</option>
          </select>
        </Field>

        <Field label="Model" description="LLM used for all agent reasoning">
          <select
            value={settings.llm_model}
            onChange={e => update("llm_model", e.target.value)}
            className="px-3 py-1.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary
                       focus:outline-none focus:border-accent transition-colors"
          >
            <option value="deepseek-ai/deepseek-v4-flash">DeepSeek V4 Flash (Free, Fast)</option>
            <option value="deepseek-ai/deepseek-v4-pro">DeepSeek V4 Pro (Free, Smarter, Slower)</option>
          </select>
        </Field>

        <Field label="Debate Rounds" description="Bull/bear debate iterations per analysis">
          <select
            value={settings.debate_rounds}
            onChange={e => update("debate_rounds", parseInt(e.target.value))}
            className="px-3 py-1.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary
                       focus:outline-none focus:border-accent transition-colors"
          >
            {[1, 2, 3].map(n => (
              <option key={n} value={n}>{n} round{n > 1 ? "s" : ""}</option>
            ))}
          </select>
        </Field>

        <SliderField
          label="Min Confidence to Trade"
          description="AI must exceed this confidence to place any order"
          value={settings.min_confidence_to_trade}
          min={0.40} max={0.90} step={0.02}
          format={v => `${Math.round(v * 100)}% confidence required`}
          onChange={v => update("min_confidence_to_trade", v)}
        />
      </Section>

      {/* ── Scanner ─────────────────────────────────────────────────────────── */}
      <Section title="Scanner">
        <Field label="AI Candidates" description="How many stocks pass through full AI analysis per scan">
          <select
            value={settings.scan_max_candidates}
            onChange={e => update("scan_max_candidates", parseInt(e.target.value))}
            className="px-3 py-1.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary
                       focus:outline-none focus:border-accent transition-colors"
          >
            {[4, 6, 8, 10, 12].map(n => (
              <option key={n} value={n}>{n} stocks</option>
            ))}
          </select>
        </Field>

        <Field label="Scheduled Auto-Scans" description="Scan + trade automatically at 9:35 AM and 1:00 PM ET (uses AI credits)">
          <Toggle
            enabled={settings.scan_enabled}
            onChange={v => update("scan_enabled", v)}
          />
        </Field>

        <Field label="Long-Only Mode" description="When off, SELL signals liquidate existing positions (never opens shorts)">
          <Toggle
            enabled={settings.long_only}
            onChange={v => update("long_only", v)}
          />
        </Field>
      </Section>

      {/* ── Autonomous Agents ───────────────────────────────────────────────── */}
      <Section title="Autonomous Agents">
        <Field label="Intraday Monitor" description="Watch open positions every 15 min during market hours">
          <Toggle
            enabled={settings.intraday_monitor_enabled}
            onChange={v => update("intraday_monitor_enabled", v)}
          />
        </Field>

        <Field label="Overnight Research Agent" description="Evening research brief at 4:30 PM ET on positions + watchlist">
          <Toggle
            enabled={settings.overnight_agent_enabled}
            onChange={v => update("overnight_agent_enabled", v)}
          />
        </Field>

        <SliderField
          label="Earnings Blackout Days"
          description="Avoid opening new positions within N days of earnings"
          value={settings.earnings_blackout_days}
          min={2} max={10} step={1}
          format={v => `${v} day${v !== 1 ? "s" : ""} before earnings`}
          onChange={v => update("earnings_blackout_days", v)}
        />
      </Section>

      {/* ── Circuit Breakers ─────────────────────────────────────────────────── */}
      <Section title="Circuit Breakers">
        <CircuitBreakers />
      </Section>

      {/* ── Account Security ─────────────────────────────────────────────────── */}
      <Section title="Account Security">
        <ChangePassword />
      </Section>
    </motion.div>
  );
}

// ── Change Password ───────────────────────────────────────────────────────────

function ChangePassword() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const inputCls =
    "w-full bg-bg-elevated border border-border rounded-lg px-3 py-2 text-sm text-text-primary " +
    "placeholder-slate-500 focus:outline-none focus:border-accent transition-colors";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg(null);
    if (next.length < 8) {
      setMsg({ ok: false, text: "New password must be at least 8 characters" });
      return;
    }
    if (next !== confirm) {
      setMsg({ ok: false, text: "New passwords don't match" });
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.post("/auth/change-password", {
        current_password: current,
        new_password: next,
      });
      // Old tokens are revoked server-side — swap in the fresh pair
      saveAuth(data.access_token, {
        user_id: data.user_id,
        email: data.email,
        full_name: data.full_name,
        is_admin: data.is_admin,
        email_verified: data.email_verified,
      }, data.refresh_token);
      setCurrent("");
      setNext("");
      setConfirm("");
      setMsg({ ok: true, text: "Password changed — other sessions were signed out" });
    } catch (err: any) {
      setMsg({ ok: false, text: err.response?.data?.detail ?? "Password change failed" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex items-start gap-2 text-xs text-text-muted">
        <KeyRound size={13} className="mt-0.5 shrink-0" />
        <p>Changing your password signs out every other device and session.</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <input
          type="password"
          value={current}
          onChange={e => setCurrent(e.target.value)}
          placeholder="Current password"
          className={inputCls}
          autoComplete="current-password"
          required
        />
        <input
          type="password"
          value={next}
          onChange={e => setNext(e.target.value)}
          placeholder="New password"
          className={inputCls}
          autoComplete="new-password"
          required
        />
        <input
          type="password"
          value={confirm}
          onChange={e => setConfirm(e.target.value)}
          placeholder="Confirm new password"
          className={inputCls}
          autoComplete="new-password"
          required
        />
      </div>
      <div className="flex items-center justify-between gap-4">
        {msg ? (
          <p className={cn("text-xs", msg.ok ? "text-gain" : "text-loss")}>{msg.text}</p>
        ) : (
          <span />
        )}
        <button
          type="submit"
          disabled={busy || !current || !next || !confirm}
          className="shrink-0 px-4 py-2 bg-accent hover:bg-accent/90 text-white text-sm font-medium
                     rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50"
        >
          {busy && <Loader2 size={13} className="animate-spin" />}
          Change Password
        </button>
      </div>
    </form>
  );
}
