import { useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import Shell from "./components/layout/Shell";
import ErrorBoundary from "./components/ErrorBoundary";
import Dashboard from "./pages/Dashboard";
import AgentHub from "./pages/AgentHub";
import Portfolio from "./pages/Portfolio";
import TradeHistory from "./pages/TradeHistory";
import Backtesting from "./pages/Backtesting";
import Settings from "./pages/Settings";
import Scanner from "./pages/Scanner";
import OptionsDesk from "./pages/Options";
import Analytics from "./pages/Analytics";
import Alerts from "./pages/Alerts";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import { isAuthenticated, clearAuth } from "./lib/auth";

export default function App() {
  const [authed, setAuthed] = useState(isAuthenticated());
  const [showSignup, setShowSignup] = useState(false);

  const handleAuth = () => setAuthed(true);
  const handleLogout = () => {
    clearAuth();
    setAuthed(false);
  };

  if (!authed) {
    if (showSignup) {
      return <Signup onAuth={handleAuth} onGoLogin={() => setShowSignup(false)} />;
    }
    return <Login onAuth={handleAuth} onGoSignup={() => setShowSignup(true)} />;
  }

  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Shell onLogout={handleLogout}>
          <AnimatePresence mode="wait">
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/agents" element={<AgentHub />} />
              <Route path="/options" element={<OptionsDesk />} />
              <Route path="/scanner" element={<Scanner />} />
              <Route path="/portfolio" element={<Portfolio />} />
              <Route path="/trades" element={<TradeHistory />} />
              <Route path="/backtest" element={<Backtesting />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/alerts" element={<Alerts />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </AnimatePresence>
        </Shell>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
