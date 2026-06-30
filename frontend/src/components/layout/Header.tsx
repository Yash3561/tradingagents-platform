import { useEffect, useRef, useState } from "react";
import { Bell, Search, X, CheckCheck, TrendingUp, TrendingDown, AlertTriangle, Zap, Calendar, BarChart2 } from "lucide-react";
import { fmt } from "../../lib/formatters";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

// ── Notification helpers ──────────────────────────────────────────────────────

interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  ticker: string | null;
  pnl: number | null;
  read: boolean;
  created_at: string;
}

function timeAgo(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function NotifIcon({ type }: { type: string }) {
  const cls = "w-4 h-4 shrink-0";
  if (type === "stop_loss_hit") return <TrendingDown className={cn(cls, "text-loss")} />;
  if (type === "take_profit_hit") return <TrendingUp className={cn(cls, "text-gain")} />;
  if (type === "trade_placed") return <Zap className={cn(cls, "text-accent")} />;
  if (type === "scan_complete") return <BarChart2 className={cn(cls, "text-accent")} />;
  if (type === "scheduled_scan") return <Calendar className={cn(cls, "text-warn")} />;
  if (type === "position_closed") return <AlertTriangle className={cn(cls, "text-warn")} />;
  return <Bell className={cn(cls, "text-text-muted")} />;
}

// ── NotificationDropdown ──────────────────────────────────────────────────────

function NotificationDropdown({ onClose }: { onClose: () => void }) {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    api.get("/notifications/?limit=5").then(({ data }) => {
      setNotifications(data);
    }).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const markAllRead = async () => {
    await api.post("/notifications/read-all").catch(() => {});
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  };

  const markRead = async (id: string) => {
    await api.post(`/notifications/${id}/read`).catch(() => {});
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
  };

  return (
    <div className="absolute right-0 top-full mt-2 w-80 bg-bg-surface border border-border rounded-xl shadow-2xl z-50 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <span className="text-sm font-semibold text-text-primary">Notifications</span>
        <div className="flex items-center gap-2">
          <button
            onClick={markAllRead}
            className="flex items-center gap-1 text-2xs text-text-muted hover:text-text-secondary transition-colors"
          >
            <CheckCheck size={12} />
            Mark all read
          </button>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary transition-colors">
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Notification list */}
      <div className="max-h-72 overflow-y-auto">
        {loading ? (
          <div className="px-4 py-6 text-center text-xs text-text-muted">Loading...</div>
        ) : notifications.length === 0 ? (
          <div className="px-4 py-6 text-center text-xs text-text-muted">No notifications yet</div>
        ) : (
          notifications.map((n) => (
            <button
              key={n.id}
              onClick={() => markRead(n.id)}
              className={cn(
                "w-full text-left flex items-start gap-3 px-4 py-3 border-b border-border/50 hover:bg-bg-elevated transition-colors",
                !n.read && "bg-accent/5"
              )}
            >
              <div className="mt-0.5">
                <NotifIcon type={n.type} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2">
                  <p className={cn(
                    "text-xs leading-tight",
                    n.read ? "text-text-secondary" : "text-text-primary font-medium"
                  )}>
                    {n.title}
                  </p>
                  {!n.read && (
                    <span className="w-1.5 h-1.5 bg-accent rounded-full shrink-0 mt-1" />
                  )}
                </div>
                <p className="text-2xs text-text-muted mt-0.5 leading-relaxed line-clamp-2">{n.body}</p>
                <p className="text-2xs text-text-muted mt-1">{timeAgo(n.created_at)}</p>
              </div>
            </button>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2.5 border-t border-border">
        <p className="text-2xs text-text-muted text-center">Last 5 notifications shown</p>
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

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
    const t = setInterval(load, 60000);
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
    const t = setInterval(load, 30000);
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

// ── Header ────────────────────────────────────────────────────────────────────

export default function Header() {
  const [unreadCount, setUnreadCount] = useState(0);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Poll unread count every 30 seconds
  useEffect(() => {
    const fetchCount = () => {
      api.get("/notifications/unread-count").then(({ data }) => {
        setUnreadCount(data.count ?? 0);
      }).catch(() => {});
    };
    fetchCount();
    const t = setInterval(fetchCount, 30000);
    return () => clearInterval(t);
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    if (!dropdownOpen) return;
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [dropdownOpen]);

  const handleBellClick = () => {
    setDropdownOpen(prev => !prev);
    // Refresh count after opening (notifications might get marked read)
    if (!dropdownOpen) {
      setTimeout(() => {
        api.get("/notifications/unread-count").then(({ data }) => {
          setUnreadCount(data.count ?? 0);
        }).catch(() => {});
      }, 1500);
    }
  };

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

      {/* Bell with notification badge and dropdown */}
      <div className="relative" ref={dropdownRef}>
        <button
          onClick={handleBellClick}
          className="relative p-2 rounded-lg hover:bg-bg-elevated transition-colors"
          aria-label="Notifications"
        >
          <Bell size={16} className={cn(
            "transition-colors",
            dropdownOpen ? "text-accent" : "text-text-secondary"
          )} />
          {unreadCount > 0 ? (
            <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-0.5 flex items-center justify-center
                             bg-loss text-white text-2xs font-bold rounded-full leading-none">
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          ) : (
            <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-accent rounded-full" />
          )}
        </button>

        {dropdownOpen && (
          <NotificationDropdown onClose={() => setDropdownOpen(false)} />
        )}
      </div>

      <PortfolioValue />
    </header>
  );
}
