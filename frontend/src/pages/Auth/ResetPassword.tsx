import { useState } from "react";
import { Eye, EyeOff, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { api } from "../../lib/api";
import AuthCard from "./AuthCard";

interface Props {
  token: string;
  onGoLogin: () => void;
}

export default function ResetPassword({ token, onGoLogin }: Props) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (password !== confirm) {
      setError("Passwords don't match");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.post("/auth/reset-password", { token, new_password: password });
      setDone(true);
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Reset failed — the link may have expired");
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <AuthCard>
        <div className="flex flex-col items-center text-center py-4">
          <AlertCircle size={28} className="text-loss mb-3" />
          <h2 className="text-lg font-semibold text-white mb-2">Invalid reset link</h2>
          <p className="text-sm text-slate-400 mb-6">
            This link is missing its token. Request a new one from the sign-in page.
          </p>
          <button onClick={onGoLogin} className="text-accent hover:underline text-sm font-medium">
            Back to sign in
          </button>
        </div>
      </AuthCard>
    );
  }

  if (done) {
    return (
      <AuthCard>
        <div className="flex flex-col items-center text-center py-4">
          <div className="w-12 h-12 rounded-full bg-gain/10 flex items-center justify-center mb-4">
            <CheckCircle2 size={22} className="text-gain" />
          </div>
          <h2 className="text-lg font-semibold text-white mb-2">Password updated</h2>
          <p className="text-sm text-slate-400 mb-6">
            Your password has been changed and all previous sessions were signed out.
          </p>
          <button
            onClick={onGoLogin}
            className="w-full bg-accent hover:bg-accent/90 text-white font-medium rounded-lg py-2.5 text-sm transition-colors"
          >
            Sign In
          </button>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard>
      <h2 className="text-lg font-semibold text-white mb-1">Set a new password</h2>
      <p className="text-sm text-slate-400 mb-6">Choose a strong password (min 8 characters)</p>

      {error && (
        <div className="flex items-center gap-2 bg-loss/10 border border-loss/30 rounded-lg px-3 py-2.5 mb-4">
          <AlertCircle size={14} className="text-loss shrink-0" />
          <p className="text-sm text-loss">{error}</p>
        </div>
      )}

      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1.5">New password</label>
          <div className="relative">
            <input
              type={showPw ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Min 8 characters"
              className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2.5 pr-10 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-accent transition-colors"
              required
              autoFocus
            />
            <button
              type="button"
              onClick={() => setShowPw((p) => !p)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
            >
              {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1.5">
            Confirm password
          </label>
          <input
            type={showPw ? "text" : "password"}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Repeat new password"
            className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-accent transition-colors"
            required
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-accent hover:bg-accent/90 text-white font-medium rounded-lg py-2.5 text-sm transition-colors flex items-center justify-center gap-2 disabled:opacity-60"
        >
          {loading && <Loader2 size={15} className="animate-spin" />}
          Update Password
        </button>
      </form>
    </AuthCard>
  );
}
