import { useEffect, useState } from "react";
import { MailWarning, X, Loader2 } from "lucide-react";
import { api } from "../../lib/api";
import { getUser, updateUser } from "../../lib/auth";

/**
 * Slim banner under the header until the user verifies their email.
 * Refreshes verified status from /auth/me once per mount (covers users who
 * verified in another tab), dismissable for the session.
 */
export default function VerifyEmailBanner() {
  const [visible, setVisible] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    if (sessionStorage.getItem("verify_banner_dismissed")) return;
    const cached = getUser();
    // Legacy users (before verification existed) have undefined — check server
    if (cached?.email_verified === true) return;
    api
      .get("/auth/me")
      .then((r) => {
        const verified = r.data?.email_verified === true;
        updateUser({ email_verified: verified, is_admin: r.data?.is_admin === true });
        setVisible(!verified);
      })
      .catch(() => {});
  }, []);

  if (!visible) return null;

  const resend = async () => {
    setSending(true);
    try {
      await api.post("/auth/resend-verification");
      setSent(true);
    } catch {
      // rate-limited or transient — keep the button available
    } finally {
      setSending(false);
    }
  };

  const dismiss = () => {
    sessionStorage.setItem("verify_banner_dismissed", "1");
    setVisible(false);
  };

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-warn/10 border-b border-warn/30 text-sm">
      <MailWarning size={15} className="text-warn shrink-0" />
      <p className="text-warn/90 flex-1">
        Verify your email address to secure your account.
      </p>
      {sent ? (
        <span className="text-xs text-slate-400">Sent — check your inbox</span>
      ) : (
        <button
          onClick={resend}
          disabled={sending}
          className="text-xs font-medium text-warn hover:underline flex items-center gap-1.5 disabled:opacity-60"
        >
          {sending && <Loader2 size={11} className="animate-spin" />}
          Resend email
        </button>
      )}
      <button onClick={dismiss} className="text-slate-500 hover:text-white" title="Dismiss">
        <X size={14} />
      </button>
    </div>
  );
}
