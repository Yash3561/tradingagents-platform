import { motion } from "framer-motion";
import { useState } from "react";
import { Eye, EyeOff, Save } from "lucide-react";

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
    <div className="flex items-start justify-between gap-6">
      <div>
        <p className="text-sm font-medium text-text-primary">{label}</p>
        {description && <p className="text-xs text-text-muted mt-0.5">{description}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

function ApiKeyField({ label, placeholder }: { label: string; placeholder: string }) {
  const [show, setShow] = useState(false);
  const [val, setVal] = useState("");
  return (
    <div className="space-y-1.5">
      <label className="text-xs text-text-secondary">{label}</label>
      <div className="relative">
        <input
          type={show ? "text" : "password"}
          value={val}
          onChange={e => setVal(e.target.value)}
          placeholder={placeholder}
          className="w-full pr-9 pl-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary
                     placeholder:text-text-muted font-mono focus:outline-none focus:border-accent transition-colors"
        />
        <button
          onClick={() => setShow(s => !s)}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary transition-colors"
        >
          {show ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      </div>
    </div>
  );
}

export default function Settings() {
  const [debateRounds, setDebateRounds] = useState(2);
  const [model, setModel] = useState("claude-sonnet-4-6");
  const [maxPosition, setMaxPosition] = useState(5);
  const [stopLoss, setStopLoss] = useState(8);
  const [dailyLoss, setDailyLoss] = useState(3);

  return (
    <motion.div
      key="settings"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-6 max-w-2xl"
    >
      <div>
        <h1 className="text-xl font-semibold text-text-primary">Settings</h1>
        <p className="text-sm text-text-muted mt-0.5">Configure agents, risk, and integrations</p>
      </div>

      <Section title="Agent Configuration">
        <Field label="LLM Model" description="Model used for all agent reasoning">
          <select
            value={model}
            onChange={e => setModel(e.target.value)}
            className="px-3 py-1.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary
                       focus:outline-none focus:border-accent transition-colors"
          >
            <option value="claude-sonnet-4-6">Claude Sonnet 4.6</option>
            <option value="claude-opus-4-6">Claude Opus 4.6</option>
            <option value="claude-haiku-4-5-20251001">Claude Haiku 4.5</option>
          </select>
        </Field>

        <Field label="Debate Rounds" description="Number of bull/bear debate iterations">
          <div className="flex items-center gap-3">
            <input
              type="range" min={1} max={5} value={debateRounds}
              onChange={e => setDebateRounds(+e.target.value)}
              className="w-28 accent-accent"
            />
            <span className="text-sm font-mono font-semibold text-text-primary w-4">{debateRounds}</span>
          </div>
        </Field>

        <Field label="Online Data Tools" description="Allow agents to fetch live market data">
          <button className="relative w-11 h-6 bg-accent rounded-full transition-colors">
            <span className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full shadow" />
          </button>
        </Field>
      </Section>

      <Section title="Risk Limits">
        {[
          { label: "Max Position Size", desc: "Maximum % of portfolio per position", val: maxPosition, setter: setMaxPosition, min: 1, max: 20, suffix: "%" },
          { label: "Stop-Loss Threshold", desc: "Automatic exit at this drawdown per trade", val: stopLoss, setter: setStopLoss, min: 2, max: 25, suffix: "%" },
          { label: "Daily Loss Limit", desc: "Halt trading if daily P&L drops below", val: dailyLoss, setter: setDailyLoss, min: 1, max: 10, suffix: "%" },
        ].map(({ label, desc, val, setter, min, max, suffix }) => (
          <Field key={label} label={label} description={desc}>
            <div className="flex items-center gap-3">
              <input
                type="range" min={min} max={max} value={val}
                onChange={e => setter(+e.target.value)}
                className="w-28 accent-accent"
              />
              <span className="text-sm font-mono font-semibold text-text-primary w-10">{val}{suffix}</span>
            </div>
          </Field>
        ))}
      </Section>

      <Section title="API Keys">
        <ApiKeyField label="Anthropic API Key" placeholder="sk-ant-..." />
        <ApiKeyField label="Alpaca API Key" placeholder="PK..." />
        <ApiKeyField label="Alpaca API Secret" placeholder="..." />
        <div className="pt-2">
          <label className="text-xs text-text-secondary block mb-1.5">Alpaca Environment</label>
          <select className="px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-accent">
            <option value="paper">Paper Trading (Safe)</option>
            <option value="live">Live Trading</option>
          </select>
        </div>
      </Section>

      <button className="flex items-center gap-2 px-5 py-2.5 bg-accent hover:bg-accent-bright text-white rounded-lg font-semibold text-sm shadow-accent-glow transition-all">
        <Save size={16} />
        Save Settings
      </button>
    </motion.div>
  );
}
