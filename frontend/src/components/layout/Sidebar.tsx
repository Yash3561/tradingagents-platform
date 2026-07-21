import { NavLink } from "react-router-dom";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  BrainCircuit,
  PieChart,
  ScrollText,
  FlaskConical,
  Settings,
  Radar,
  Zap,
  TrendingUp,
  LogOut,
  Brain,
  Bell,
  BarChart2,
  BookMarked,
  Newspaper,
  ClipboardList,
  CalendarDays,
  BookOpen,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { cn } from "../../lib/cn";
import { getUser } from "../../lib/auth";
import { api } from "../../lib/api";

function BrokerStatusCard() {
  const [status, setStatus] = useState<{ connected: boolean; account_number?: string } | null>(null);

  useEffect(() => {
    const load = () =>
      api.get("/broker/status").then(r => setStatus(r.data)).catch(() => setStatus(null));
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, []);

  const connected = status?.connected === true;
  return (
    <NavLink to="/settings" data-tour="broker-status" className="block mx-0 p-3 rounded-lg bg-bg-elevated border border-border hover:border-accent/40 transition-colors">
      <div className="flex items-center gap-2 mb-1">
        <div className={cn("w-2 h-2 rounded-full", connected ? "bg-gain animate-pulse-slow" : "bg-warn")} />
        <span className="text-xs text-text-secondary">Paper Trading</span>
      </div>
      <p className="text-xs text-text-muted">
        {status === null
          ? "Checking broker..."
          : connected
            ? `Alpaca ${status.account_number ?? "connected"}`
            : "No broker — click to connect"}
      </p>
    </NavLink>
  );
}

const NAV_GROUPS = [
  {
    label: "Trading",
    tourId: "nav-trading",
    items: [
      { to: "/markets", icon: BarChart2, label: "Markets" },
      { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
      { to: "/watchlist", icon: BookMarked, label: "Watchlist" },
      { to: "/news", icon: Newspaper, label: "News" },
      { to: "/calendar", icon: CalendarDays, label: "Calendar" },
      { to: "/scanner", icon: Radar, label: "Scanner" },
      { to: "/agents", icon: BrainCircuit, label: "Agent Hub" },
      { to: "/options", icon: TrendingUp, label: "Options Desk" },
    ],
  },
  {
    label: "Portfolio",
    tourId: "nav-portfolio",
    items: [
      { to: "/portfolio", icon: PieChart, label: "Portfolio" },
      { to: "/trades", icon: ScrollText, label: "Trade History" },
      { to: "/orders", icon: ClipboardList, label: "Orders" },
      { to: "/alerts", icon: Bell, label: "Alerts" },
      { to: "/backtest", icon: FlaskConical, label: "Backtesting" },
    ],
  },
  {
    label: "Intelligence",
    tourId: "nav-intelligence",
    items: [
      { to: "/analytics", icon: Brain, label: "Analytics" },
      { to: "/track-record", icon: ScrollText, label: "Track Record" },
      { to: "/strategy", icon: Zap, label: "Strategy" },
      { to: "/how-it-works", icon: Workflow, label: "How It Works" },
      { to: "/learn", icon: BookOpen, label: "Learn" },
      { to: "/settings", icon: Settings, label: "Settings" },
    ],
  },
];

function useScanRunning() {
  const [running, setRunning] = useState(false);
  useEffect(() => {
    const check = () => {
      try {
        const raw = localStorage.getItem("scanner_state_v2");
        if (!raw) { setRunning(false); return; }
        const s = JSON.parse(raw);
        const isActive = s.scanStatus === "scanning" || s.scanStatus === "prescreening";
        // Treat as stale if started more than 30 min ago
        const stale = s.startedAt && (Date.now() - new Date(s.startedAt).getTime()) > 30 * 60 * 1000;
        setRunning(isActive && !stale);
      } catch { setRunning(false); }
    };
    check();
    // Poll every 2s so the indicator updates even when on another page
    const t = setInterval(check, 2000);
    return () => clearInterval(t);
  }, []);
  return running;
}

interface SidebarProps {
  onLogout?: () => void;
  /** Mobile drawer state — below lg the sidebar is an overlay */
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

export default function Sidebar({ onLogout, mobileOpen = false, onMobileClose }: SidebarProps) {
  const scanRunning = useScanRunning();
  const user = getUser();

  const displayName = user?.full_name || user?.email || "Account";
  const displaySub = user?.full_name ? user.email : null;

  const navGroups = user?.is_admin
    ? [
        ...NAV_GROUPS.slice(0, -1),
        {
          ...NAV_GROUPS[NAV_GROUPS.length - 1],
          items: [
            ...NAV_GROUPS[NAV_GROUPS.length - 1].items,
            { to: "/admin", icon: ShieldCheck, label: "Admin" },
          ],
        },
      ]
    : NAV_GROUPS;

  return (
    <>
      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-40 lg:hidden"
          onClick={onMobileClose}
        />
      )}
      <aside
        className={cn(
          "flex flex-col w-60 h-full bg-bg-surface border-r border-border shrink-0",
          "fixed inset-y-0 left-0 z-50 transition-transform duration-200 lg:static lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-border">
        <div className="relative w-8 h-8">
          <div className="absolute inset-0 bg-accent rounded-lg opacity-20 blur-sm" />
          <div className="relative flex items-center justify-center w-8 h-8 bg-accent-muted rounded-lg border border-accent/40">
            <Zap size={16} className="text-accent-bright" />
          </div>
        </div>
        <div>
          <p className="text-sm font-semibold text-text-primary leading-tight">TradingAgents</p>
          <p className="text-2xs text-text-muted">Platform v1.0</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 overflow-y-auto">
        {navGroups.map((group) => (
          <div key={group.label} className="mb-4" data-tour={group.tourId}>
            <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-600">
              {group.label}
            </p>
            {group.items.map(({ to, icon: Icon, label }) => (
              <NavLink key={to} to={to} onClick={onMobileClose}>
                {({ isActive }) => (
                  <motion.div
                    whileHover={{ x: 2 }}
                    transition={{ duration: 0.15 }}
                    className={cn("sidebar-item", isActive && "sidebar-item-active")}
                  >
                    <Icon size={18} className="shrink-0" />
                    <span>{label}</span>
                    {to === "/scanner" && scanRunning && !isActive && (
                      <span className="ml-auto flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-warn animate-pulse-slow" />
                        <span className="text-2xs text-warn font-medium">Live</span>
                      </span>
                    )}
                    {isActive && (
                      <motion.div
                        layoutId="sidebar-indicator"
                        className="ml-auto w-1.5 h-1.5 rounded-full bg-accent-bright"
                      />
                    )}
                  </motion.div>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      {/* Bottom */}
      <div className="px-3 pb-4 border-t border-border pt-4 space-y-1">
        <BrokerStatusCard />

        {/* User section */}
        <div className="mt-2 mx-0 p-3 rounded-lg bg-bg-elevated border border-border">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-text-primary truncate">{displayName}</p>
              {displaySub && (
                <p className="text-2xs text-text-muted truncate">{displaySub}</p>
              )}
            </div>
            {onLogout && (
              <button
                onClick={onLogout}
                className="shrink-0 p-1.5 rounded-md text-text-muted hover:text-loss hover:bg-loss/10 transition-colors"
                title="Sign out"
              >
                <LogOut size={14} />
              </button>
            )}
          </div>
        </div>
      </div>
    </aside>
    </>
  );
}
