import { useEffect, useState } from "react";
import { Bell, Search } from "lucide-react";
import { fmt } from "../../lib/formatters";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

function MarketClock() {
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const etTime = new Date(time.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const h = etTime.getHours() + etTime.getMinutes() / 60;
  const isMarketOpen = h >= 9.5 && h < 16 && etTime.getDay() >= 1 && etTime.getDay() <= 5;

  return (
    <div className="flex items-center gap-2">
      <div className={cn("w-2 h-2 rounded-full", isMarketOpen ? "bg-gain animate-pulse-slow" : "bg-text-muted")} />
      <span className="text-xs text-text-secondary font-mono">
        {etTime.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })} ET
      </span>
      <span className={cn(
        "text-2xs font-medium px-1.5 py-0.5 rounded",
        isMarketOpen ? "bg-gain/10 text-gain" : "bg-bg-elevated text-text-muted"
      )}>
        {isMarketOpen ? "OPEN" : "CLOSED"}
      </span>
    </div>
  );
}

function LiveIndices() {
  const [indices, setIndices] = useState<{ label: string; value: number; change: number }[]>([]);

  useEffect(() => {
    const load = () => {
      api.get("/dashboard/market-pulse").then(({ data }) => {
        const wanted = ["SPY", "QQQ", "VIX"];
        const filtered = data.filter((d: any) => wanted.includes(d.label));
        setIndices(filtered);
      }).catch(() => {});
    };
    load();
    const t = setInterval(load, 60000); // refresh every minute
    return () => clearInterval(t);
  }, []);

  if (!indices.length) return (
    <div className="flex items-center gap-6 flex-1">
      {["SPY", "QQQ", "VIX"].map(l => (
        <div key={l} className="flex items-center gap-2">
          <span className="text-xs font-semibold text-text-secondary">{l}</span>
          <span className="text-sm font-mono text-text-muted">—</span>
        </div>
      ))}
    </div>
  );

  return (
    <div className="flex items-center gap-6 flex-1">
      {indices.map(({ label, value, change }) => (
        <div key={label} className="flex items-center gap-2">
          <span className="text-xs font-semibold text-text-secondary">{label}</span>
          <span className="text-sm font-mono text-text-primary">{fmt.price(value)}</span>
          <span className={cn("text-xs font-mono", (change ?? 0) >= 0 ? "text-gain" : "text-loss")}>
            {fmt.sign(change ?? 0)}%
          </span>
        </div>
      ))}
    </div>
  );
}

function PortfolioValue() {
  const [equity, setEquity] = useState<number | null>(null);
  const [dayPnl, setDayPnl] = useState<number | null>(null);

  useEffect(() => {
    const load = () => {
      api.get("/portfolio/risk-metrics").then(({ data }) => {
        setEquity(data.equity);
        setDayPnl(data.day_pnl);
      }).catch(() => {});
    };
    load();
    const t = setInterval(load, 30000); // refresh every 30s
    return () => clearInterval(t);
  }, []);

  return (
    <div className="pl-4 border-l border-border">
      <p className="text-2xs text-text-muted leading-tight">Portfolio Value</p>
      <p className="text-sm font-mono font-semibold text-text-primary">
        {equity != null ? fmt.usd(equity) : "—"}
      </p>
      {dayPnl != null && dayPnl !== 0 && (
        <p className={cn("text-2xs font-mono", dayPnl >= 0 ? "text-gain" : "text-loss")}>
          {dayPnl >= 0 ? "+" : ""}{fmt.usd(dayPnl)} today
        </p>
      )}
    </div>
  );
}

export default function Header() {
  return (
    <header className="flex items-center gap-4 px-6 py-3 bg-bg-surface border-b border-border shrink-0">
      <LiveIndices />

      {/* Search */}
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <input
          placeholder="Search ticker..."
          className="w-48 pl-8 pr-3 py-1.5 text-xs bg-bg-elevated border border-border rounded-lg
                     text-text-primary placeholder:text-text-muted
                     focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30
                     transition-colors"
        />
      </div>

      <MarketClock />

      <button className="relative p-2 rounded-lg hover:bg-bg-elevated transition-colors">
        <Bell size={16} className="text-text-secondary" />
        <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-accent rounded-full" />
      </button>

      <PortfolioValue />
    </header>
  );
}
