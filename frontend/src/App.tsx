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
import Markets from "./pages/Markets";
import Orders from "./pages/Orders";
import Watchlist from "./pages/Watchlist";
import News from "./pages/News";
import EconomicCalendar from "./pages/Calendar";
import Learn from "./pages/Learn";
import Strategy from "./pages/Strategy";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import ForgotPassword from "./pages/Auth/ForgotPassword";
import ResetPassword from "./pages/Auth/ResetPassword";
import VerifyEmail from "./pages/Auth/VerifyEmail";
import Admin from "./pages/Admin";
import TrackRecord from "./pages/TrackRecord";
import Landing from "./pages/Landing";
import { isAuthenticated, clearAuth, getUser } from "./lib/auth";

type UnauthedView = "landing" | "login" | "signup" | "forgot" | "reset" | "verify";

/** Email links land on real URLs — map them to views before the router mounts. */
function initialUnauthedView(): UnauthedView {
  const path = window.location.pathname;
  if (path === "/reset-password") return "reset";
  if (path === "/verify-email") return "verify";
  // Invite links (/?invite=CODE) land straight on signup with the code pre-filled
  if (new URLSearchParams(window.location.search).has("invite")) return "signup";
  // Marketing page for fresh visitors; deep links (bookmarked app pages) go to login
  if (path === "/") return "landing";
  return "login";
}

function urlToken(): string {
  return new URLSearchParams(window.location.search).get("token") ?? "";
}

function AdminRoute() {
  return getUser()?.is_admin ? <Admin /> : <Navigate to="/dashboard" replace />;
}

export default function App() {
  const [authed, setAuthed] = useState(isAuthenticated());
  const [view, setView] = useState<UnauthedView>(initialUnauthedView);

  // Public shareable page — no login required
  if (!authed && window.location.pathname === "/track-record") {
    return <TrackRecord standalone />;
  }

  const handleAuth = () => setAuthed(true);
  const handleLogout = () => {
    clearAuth();
    setView("login");
    setAuthed(false);
  };
  const goLogin = () => {
    // Clear any /reset-password or /verify-email path from the email link
    window.history.replaceState(null, "", "/");
    setView("login");
  };

  // Verify-email links work signed in or out — let the router handle them when authed
  if (!authed || (view === "verify" && window.location.pathname === "/verify-email")) {
    if (view === "landing") {
      return (
        <Landing
          onGetStarted={() => setView("signup")}
          onSignIn={() => setView("login")}
        />
      );
    }
    if (view === "signup") {
      return <Signup onAuth={handleAuth} onGoLogin={() => setView("login")} />;
    }
    if (view === "forgot") {
      return <ForgotPassword onGoLogin={() => setView("login")} />;
    }
    if (view === "reset") {
      return <ResetPassword token={urlToken()} onGoLogin={goLogin} />;
    }
    if (view === "verify") {
      return <VerifyEmail token={urlToken()} onDone={goLogin} />;
    }
    return (
      <Login
        onAuth={handleAuth}
        onGoSignup={() => setView("signup")}
        onGoForgot={() => setView("forgot")}
      />
    );
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
              <Route path="/markets" element={<Markets />} />
              <Route path="/orders" element={<Orders />} />
              <Route path="/watchlist" element={<Watchlist />} />
              <Route path="/news" element={<News />} />
              <Route path="/calendar" element={<EconomicCalendar />} />
              <Route path="/learn" element={<Learn />} />
              <Route path="/strategy" element={<Strategy />} />
              <Route path="/track-record" element={<TrackRecord />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/admin" element={<AdminRoute />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </AnimatePresence>
        </Shell>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
