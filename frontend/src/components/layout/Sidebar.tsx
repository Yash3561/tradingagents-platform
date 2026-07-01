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
} from "lucide-react";
import { cn } from "../../lib/cn";
import { getUser } from "../../lib/auth";

const NAV_GROUPS = [
  {
    label: "Trading",
    items: [
      { to: "/markets", icon: BarChart2, label: "Markets" },
      { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
      { to: "/scanner", icon: Radar, label: "Scanner" },
      { to: "/agents", icon: BrainCircuit, label: "Agent Hub" },
      { to: "/options", icon: TrendingUp, label: "Options Desk" },
    ],
  },
  {
    label: "Portfolio",
    items: [
      { to: "/portfolio", icon: PieChart, label: "Portfolio" },
      { to: "/trades", icon: ScrollText, label: "Trade History" },
      { to: "/alerts", icon: Bell, label: "Alerts" },
      { to: "/backtest", icon: FlaskConical, label: "Backtesting" },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { to: "/analytics", icon: Brain, label: "Analytics" },
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
}

export default function Sidebar({ onLogout }: SidebarProps) {
  const scanRunning = useScanRunning();
  const user = getUser();

  const displayName = user?.full_name || user?.email || "Account";
  const displaySub = user?.full_name ? user.email : null;

  return (
    <aside className="flex flex-col w-60 h-full bg-bg-surface border-r border-border shrink-0">
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
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="mb-4">
            <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-600">
              {group.label}
            </p>
            {group.items.map(({ to, icon: Icon, label }) => (
              <NavLink key={to} to={to}>
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
        <div className="mx-0 p-3 rounded-lg bg-bg-elevated border border-border">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2 h-2 rounded-full bg-gain animate-pulse-slow" />
            <span className="text-xs text-text-secondary">Paper Trading</span>
          </div>
          <p className="text-xs text-text-muted">Alpaca connected</p>
        </div>

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
  );
}
