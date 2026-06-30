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
} from "lucide-react";
import { cn } from "../../lib/cn";

const NAV = [
  { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/agents", icon: BrainCircuit, label: "Agent Hub" },
  { to: "/options", icon: TrendingUp, label: "Options Desk" },
  { to: "/scanner", icon: Radar, label: "Scanner" },
  { to: "/portfolio", icon: PieChart, label: "Portfolio" },
  { to: "/trades", icon: ScrollText, label: "Trade History" },
  { to: "/backtest", icon: FlaskConical, label: "Backtesting" },
];

function useScanRunning() {
  const [running, setRunning] = useState(false);
  useEffect(() => {
    const check = () => {
      try {
        const raw = localStorage.getItem("scanner_state_v2");
        if (!raw) { setRunning(false); return; }
        const s = JSON.parse(raw);
        setRunning(s.scanStatus === "scanning" || s.scanStatus === "prescreening");
      } catch { setRunning(false); }
    };
    check();
    // Poll every 2s so the indicator updates even when on another page
    const t = setInterval(check, 2000);
    return () => clearInterval(t);
  }, []);
  return running;
}

export default function Sidebar() {
  const scanRunning = useScanRunning();

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
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV.map(({ to, icon: Icon, label }) => (
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
      </nav>

      {/* Bottom */}
      <div className="px-3 pb-4 border-t border-border pt-4 space-y-1">
        <NavLink to="/settings">
          {({ isActive }) => (
            <div className={cn("sidebar-item", isActive && "sidebar-item-active")}>
              <Settings size={18} />
              <span>Settings</span>
            </div>
          )}
        </NavLink>
        <div className="mt-3 mx-0 p-3 rounded-lg bg-bg-elevated border border-border">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2 h-2 rounded-full bg-gain animate-pulse-slow" />
            <span className="text-xs text-text-secondary">Paper Trading</span>
          </div>
          <p className="text-xs text-text-muted">Alpaca connected</p>
        </div>
      </div>
    </aside>
  );
}
