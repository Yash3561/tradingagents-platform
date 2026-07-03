import { ReactNode } from "react";
import { motion } from "framer-motion";
import { TrendingUp } from "lucide-react";

/** Shared centered card layout for unauthenticated pages. */
export default function AuthCard({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-bg-base flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-md"
      >
        <div className="flex items-center gap-3 justify-center mb-8">
          <div className="w-10 h-10 bg-accent rounded-lg flex items-center justify-center">
            <TrendingUp size={20} className="text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">TradingAgents</h1>
            <p className="text-xs text-slate-500">AI-Powered Trading Platform</p>
          </div>
        </div>
        <div className="card p-8">{children}</div>
      </motion.div>
    </div>
  );
}
