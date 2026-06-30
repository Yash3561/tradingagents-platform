import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import Shell from "./components/layout/Shell";
import Dashboard from "./pages/Dashboard";
import AgentHub from "./pages/AgentHub";
import Portfolio from "./pages/Portfolio";
import TradeHistory from "./pages/TradeHistory";
import Backtesting from "./pages/Backtesting";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <Shell>
        <AnimatePresence mode="wait">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/agents" element={<AgentHub />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/trades" element={<TradeHistory />} />
            <Route path="/backtest" element={<Backtesting />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </AnimatePresence>
      </Shell>
    </BrowserRouter>
  );
}
