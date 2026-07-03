import { useState } from "react";
import { Loader2, AlertCircle, MailCheck } from "lucide-react";
import { api } from "../../lib/api";
import AuthCard from "./AuthCard";

interface Props {
  onGoLogin: () => void;
}

export default function ForgotPassword({ onGoLogin }: Props) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;
    setLoading(true);
    setError(null);
    try {
      await api.post("/auth/forgot-password", { email });
      setSent(true);
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Something went wrong — try again");
    } finally {
      setLoading(false);
    }
  };

  if (sent) {
    return (
      <AuthCard>
        <div className="flex flex-col items-center text-center py-4">
          <div className="w-12 h-12 rounded-full bg-gain/10 flex items-center justify-center mb-4">
            <MailCheck size={22} className="text-gain" />
          </div>
          <h2 className="text-lg font-semibold text-white mb-2">Check your email</h2>
          <p className="text-sm text-slate-400 mb-6">
            If <span className="text-white">{email}</span> is registered, a reset link is on
            its way. The link expires in 30 minutes.
          </p>
          <button onClick={onGoLogin} className="text-accent hover:underline text-sm font-medium">
            Back to sign in
          </button>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard>
      <h2 className="text-lg font-semibold text-white mb-1">Forgot password</h2>
      <p className="text-sm text-slate-400 mb-6">
        Enter your account email and we'll send a reset link
      </p>

      {error && (
        <div className="flex items-center gap-2 bg-loss/10 border border-loss/30 rounded-lg px-3 py-2.5 mb-4">
          <AlertCircle size={14} className="text-loss shrink-0" />
          <p className="text-sm text-loss">{error}</p>
        </div>
      )}

      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1.5">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-accent transition-colors"
            required
            autoFocus
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-accent hover:bg-accent/90 text-white font-medium rounded-lg py-2.5 text-sm transition-colors flex items-center justify-center gap-2 disabled:opacity-60"
        >
          {loading && <Loader2 size={15} className="animate-spin" />}
          Send Reset Link
        </button>
      </form>

      <p className="text-center text-sm text-slate-500 mt-6">
        Remembered it?{" "}
        <button onClick={onGoLogin} className="text-accent hover:underline font-medium">
          Sign in
        </button>
      </p>
    </AuthCard>
  );
}
