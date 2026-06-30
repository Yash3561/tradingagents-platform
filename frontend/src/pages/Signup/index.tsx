import { useState } from "react";
import { motion } from "framer-motion";
import { Eye, EyeOff, Loader2, TrendingUp, AlertCircle } from "lucide-react";
import { api } from "../../lib/api";
import { saveAuth } from "../../lib/auth";

interface Props {
  onAuth: () => void;
  onGoLogin: () => void;
}

export default function Signup({ onAuth, onGoLogin }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.post("/auth/signup", {
        email,
        password,
        full_name: fullName,
      });
      saveAuth(data.access_token, {
        user_id: data.user_id,
        email: data.email,
        full_name: data.full_name,
      });
      onAuth();
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Signup failed");
    } finally {
      setLoading(false);
    }
  };

  const pwStrength =
    password.length === 0
      ? null
      : password.length < 8
      ? "weak"
      : password.length < 12
      ? "good"
      : "strong";

  return (
    <div className="min-h-screen bg-bg-base flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-md"
      >
        {/* Logo */}
        <div className="flex items-center gap-3 justify-center mb-8">
          <div className="w-10 h-10 bg-accent rounded-lg flex items-center justify-center">
            <TrendingUp size={20} className="text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">TradingAgents</h1>
            <p className="text-xs text-slate-500">AI-Powered Trading Platform</p>
          </div>
        </div>

        {/* Card */}
        <div className="card p-8">
          <h2 className="text-lg font-semibold text-white mb-1">Create account</h2>
          <p className="text-sm text-slate-400 mb-6">Start trading with AI in seconds</p>

          {error && (
            <div className="flex items-center gap-2 bg-loss/10 border border-loss/30 rounded-lg px-3 py-2.5 mb-4">
              <AlertCircle size={14} className="text-loss shrink-0" />
              <p className="text-sm text-loss">{error}</p>
            </div>
          )}

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">
                Full name (optional)
              </label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Yash"
                className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-accent transition-colors"
                autoFocus
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-accent transition-colors"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Password</label>
              <div className="relative">
                <input
                  type={showPw ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Min 8 characters"
                  className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2.5 pr-10 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-accent transition-colors"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPw((p) => !p)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
                >
                  {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
              {pwStrength && (
                <div className="flex items-center gap-2 mt-1.5">
                  <div className="flex gap-1">
                    {(["weak", "good", "strong"] as const).map((s, i) => (
                      <div
                        key={s}
                        className={`h-1 w-8 rounded-full transition-colors ${
                          i <= ["weak", "good", "strong"].indexOf(pwStrength)
                            ? pwStrength === "weak"
                              ? "bg-loss"
                              : pwStrength === "good"
                              ? "bg-warn"
                              : "bg-gain"
                            : "bg-bg-elevated"
                        }`}
                      />
                    ))}
                  </div>
                  <span
                    className={`text-xs ${
                      pwStrength === "weak"
                        ? "text-loss"
                        : pwStrength === "good"
                        ? "text-warn"
                        : "text-gain"
                    }`}
                  >
                    {pwStrength}
                  </span>
                </div>
              )}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-accent hover:bg-accent/90 text-white font-medium rounded-lg py-2.5 text-sm transition-colors flex items-center justify-center gap-2 disabled:opacity-60"
            >
              {loading && <Loader2 size={15} className="animate-spin" />}
              Create Account
            </button>
          </form>

          <p className="text-center text-sm text-slate-500 mt-6">
            Already have an account?{" "}
            <button onClick={onGoLogin} className="text-accent hover:underline font-medium">
              Sign in
            </button>
          </p>
        </div>
      </motion.div>
    </div>
  );
}
