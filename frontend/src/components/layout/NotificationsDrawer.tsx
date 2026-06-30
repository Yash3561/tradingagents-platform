import { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Bell,
  CheckCheck,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Info,
  Newspaper,
} from "lucide-react";
import { api } from "../../lib/api";

interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  ticker: string | null;
  pnl: number | null;
  read: boolean;
  created_at: string;
}

const TYPE_ICON: Record<string, React.ReactNode> = {
  stop_loss: <TrendingDown size={14} className="text-loss" />,
  stop_loss_hit: <TrendingDown size={14} className="text-loss" />,
  take_profit: <TrendingUp size={14} className="text-gain" />,
  take_profit_hit: <TrendingUp size={14} className="text-gain" />,
  alert: <AlertTriangle size={14} className="text-warn" />,
  morning_brief: <Newspaper size={14} className="text-accent" />,
  trade: <TrendingUp size={14} className="text-gain" />,
  trade_placed: <TrendingUp size={14} className="text-gain" />,
};

interface Props {
  open: boolean;
  onClose: () => void;
  onReadAll: () => void;
}

export default function NotificationsDrawer({ open, onClose, onReadAll }: Props) {
  const [notes, setNotes] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);

  const fetchNotes = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/notifications?limit=30");
      setNotes(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) fetchNotes();
  }, [open]);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, onClose]);

  const markRead = async (id: string) => {
    try {
      await api.post(`/notifications/${id}/read`);
      setNotes((prev) =>
        prev.map((n) => (n.id === id ? { ...n, read: true } : n))
      );
    } catch {
      // ignore
    }
  };

  const markAllRead = async () => {
    try {
      await api.post("/notifications/read-all");
      setNotes((prev) => prev.map((n) => ({ ...n, read: true })));
      onReadAll();
    } catch {
      // ignore
    }
  };

  const relativeTime = (iso: string) => {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  };

  const unreadCount = notes.filter((n) => !n.read).length;

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/40 z-40"
            onClick={onClose}
          />

          {/* Drawer */}
          <motion.div
            ref={drawerRef}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="fixed right-0 top-0 h-full w-96 bg-bg-surface border-l border-border z-50 flex flex-col shadow-2xl"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <div className="flex items-center gap-2">
                <Bell size={18} className="text-accent" />
                <span className="font-semibold text-white">Notifications</span>
                {unreadCount > 0 && (
                  <span className="bg-accent text-white text-xs font-bold px-1.5 py-0.5 rounded-full">
                    {unreadCount}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3">
                {unreadCount > 0 && (
                  <button
                    onClick={markAllRead}
                    className="flex items-center gap-1 text-xs text-slate-400 hover:text-white transition-colors"
                  >
                    <CheckCheck size={14} />
                    Mark all read
                  </button>
                )}
                <button
                  onClick={onClose}
                  className="text-slate-400 hover:text-white transition-colors"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto">
              {loading ? (
                <div className="flex items-center justify-center h-32 text-slate-500 text-sm">
                  Loading...
                </div>
              ) : notes.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 gap-2 text-slate-500">
                  <Bell size={32} className="opacity-30" />
                  <p className="text-sm">No notifications yet</p>
                </div>
              ) : (
                <div className="divide-y divide-border">
                  {notes.map((n) => (
                    <div
                      key={n.id}
                      onClick={() => !n.read && markRead(n.id)}
                      className={`px-5 py-4 cursor-pointer transition-colors hover:bg-bg-elevated ${
                        !n.read
                          ? "border-l-2 border-accent"
                          : "border-l-2 border-transparent"
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5 shrink-0">
                          {TYPE_ICON[n.type] ?? (
                            <Info size={14} className="text-slate-400" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <p
                              className={`text-sm font-medium truncate ${
                                n.read ? "text-slate-300" : "text-white"
                              }`}
                            >
                              {n.title}
                            </p>
                            <span className="text-xs text-slate-500 shrink-0">
                              {relativeTime(n.created_at)}
                            </span>
                          </div>
                          <p className="text-xs text-slate-400 mt-0.5 line-clamp-2">
                            {n.body}
                          </p>
                          {n.pnl !== null && (
                            <span
                              className={`text-xs font-mono font-bold mt-1 inline-block ${
                                n.pnl >= 0 ? "text-gain" : "text-loss"
                              }`}
                            >
                              {n.pnl >= 0 ? "+" : ""}${n.pnl.toFixed(2)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
