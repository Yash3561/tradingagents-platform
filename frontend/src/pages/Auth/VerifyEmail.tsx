import { useEffect, useRef, useState } from "react";
import { Loader2, AlertCircle, MailCheck } from "lucide-react";
import { api } from "../../lib/api";
import { updateUser, isAuthenticated } from "../../lib/auth";
import AuthCard from "./AuthCard";

interface Props {
  token: string;
  onDone: () => void;
}

/** Handles /verify-email?token=... — works signed in or out. */
export default function VerifyEmail({ token, onDone }: Props) {
  const [state, setState] = useState<"working" | "ok" | "error">("working");
  const [message, setMessage] = useState("");
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current || !token) {
      if (!token) {
        setState("error");
        setMessage("This link is missing its token.");
      }
      return;
    }
    ran.current = true;
    api
      .post("/auth/verify-email", { token })
      .then(() => {
        updateUser({ email_verified: true });
        setState("ok");
      })
      .catch((err: any) => {
        setState("error");
        setMessage(err.response?.data?.detail ?? "Verification failed");
      });
  }, [token]);

  const continueLabel = isAuthenticated() ? "Continue to Dashboard" : "Go to Sign In";

  return (
    <AuthCard>
      <div className="flex flex-col items-center text-center py-4">
        {state === "working" && (
          <>
            <Loader2 size={28} className="text-accent animate-spin mb-3" />
            <h2 className="text-lg font-semibold text-white">Verifying your email…</h2>
          </>
        )}
        {state === "ok" && (
          <>
            <div className="w-12 h-12 rounded-full bg-gain/10 flex items-center justify-center mb-4">
              <MailCheck size={22} className="text-gain" />
            </div>
            <h2 className="text-lg font-semibold text-white mb-2">Email verified</h2>
            <p className="text-sm text-slate-400 mb-6">Your account email is confirmed.</p>
          </>
        )}
        {state === "error" && (
          <>
            <AlertCircle size={28} className="text-loss mb-3" />
            <h2 className="text-lg font-semibold text-white mb-2">Verification failed</h2>
            <p className="text-sm text-slate-400 mb-6">{message}</p>
          </>
        )}
        {state !== "working" && (
          <button
            onClick={onDone}
            className="w-full bg-accent hover:bg-accent/90 text-white font-medium rounded-lg py-2.5 text-sm transition-colors"
          >
            {continueLabel}
          </button>
        )}
      </div>
    </AuthCard>
  );
}
