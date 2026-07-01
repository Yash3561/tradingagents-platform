import { useState, useCallback, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  ListX,
  Loader2,
  X,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Order {
  id: string;
  ticker: string;
  side: "buy" | "sell";
  type: "market" | "limit" | "stop" | "stop_limit" | "bracket";
  qty: number;
  filled_qty: number;
  limit_price: number | null;
  stop_price: number | null;
  status:
    | "new"
    | "partially_filled"
    | "filled"
    | "canceled"
    | "expired"
    | "pending_new"
    | "held";
  time_in_force: string;
  created_at: string;
  filled_at: string | null;
  legs: Order[];
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtPrice(v: number | null): string {
  if (v == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(v);
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtType(t: Order["type"]): string {
  return t
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: Order["status"] }) {
  const cfg: Record<Order["status"], { label: string; cls: string }> = {
    new: { label: "New", cls: "bg-warn/10 text-warn border border-warn/20" },
    pending_new: { label: "Pending", cls: "bg-warn/10 text-warn border border-warn/20" },
    held: { label: "Held", cls: "bg-warn/10 text-warn border border-warn/20" },
    partially_filled: {
      label: "Partial",
      cls: "bg-accent/10 text-accent border border-accent/20",
    },
    filled: {
      label: "Filled",
      cls: "bg-gain/10 text-gain border border-gain/20",
    },
    canceled: {
      label: "Canceled",
      cls: "bg-bg-elevated text-text-muted border border-border",
    },
    expired: {
      label: "Expired",
      cls: "bg-bg-elevated text-text-muted border border-border",
    },
  };

  const { label, cls } = cfg[status] ?? {
    label: status,
    cls: "bg-bg-elevated text-text-muted border border-border",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium font-mono",
        cls
      )}
    >
      {label}
    </span>
  );
}

function QtyCell({ order }: { order: Order }) {
  const pct =
    order.qty > 0 ? Math.min(100, (order.filled_qty / order.qty) * 100) : 0;

  return (
    <div className="min-w-[80px]">
      <span className="text-xs font-mono text-text-primary">
        <span className="text-accent">{order.filled_qty}</span>
        <span className="text-text-muted">/{order.qty}</span>
      </span>
      <div className="mt-1 h-1 bg-bg-elevated rounded-full overflow-hidden w-16">
        <div
          className="h-full bg-accent rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ─── Order Row ────────────────────────────────────────────────────────────────

interface OrderRowProps {
  order: Order;
  showActions: boolean;
  isLeg?: boolean;
  cancelingId: string | null;
  onCancel: (id: string) => void;
  names: Record<string, { name: string; sector: string }>;
}

function OrderRow({
  order,
  showActions,
  isLeg = false,
  cancelingId,
  onCancel,
  names,
}: OrderRowProps) {
  const isCanceling = cancelingId === order.id;
  const canCancel = !["filled", "canceled", "expired"].includes(order.status);

  return (
    <motion.tr
      layout
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.2 }}
      className={cn(
        "border-b border-border/40 hover:bg-bg-elevated/40 transition-colors",
        isLeg && "opacity-60"
      )}
    >
      {/* Ticker */}
      <td className="px-4 py-3 whitespace-nowrap">
        {isLeg && (
          <span className="mr-1.5 text-text-muted text-xs font-mono">└</span>
        )}
        <span
          className={cn(
            "font-mono font-bold",
            isLeg ? "text-text-secondary text-xs" : "text-text-primary text-sm"
          )}
        >
          {order.ticker}
        </span>
        {!isLeg && (
          <p className="text-2xs text-text-muted font-normal mt-0.5">{names[order.ticker]?.name ?? ''}</p>
        )}
      </td>

      {/* Side */}
      <td className="px-4 py-3 whitespace-nowrap">
        {order.side === "buy" ? (
          <span className="badge-gain">BUY</span>
        ) : (
          <span className="badge-loss">SELL</span>
        )}
      </td>

      {/* Type */}
      <td className="px-4 py-3 whitespace-nowrap">
        <span className="text-xs text-text-secondary">{fmtType(order.type)}</span>
      </td>

      {/* Qty */}
      <td className="px-4 py-3">
        <QtyCell order={order} />
      </td>

      {/* Limit Price */}
      <td className="px-4 py-3 whitespace-nowrap">
        <span className="text-xs font-mono text-text-secondary">
          {fmtPrice(order.limit_price)}
        </span>
      </td>

      {/* Stop Price */}
      <td className="px-4 py-3 whitespace-nowrap">
        <span className="text-xs font-mono text-text-secondary">
          {fmtPrice(order.stop_price)}
        </span>
      </td>

      {/* Status */}
      <td className="px-4 py-3 whitespace-nowrap">
        <StatusBadge status={order.status} />
      </td>

      {/* Placed */}
      <td className="px-4 py-3 whitespace-nowrap">
        <span className="text-xs font-mono text-text-muted">
          {fmtDate(order.created_at)}
        </span>
      </td>

      {/* Actions */}
      {showActions && (
        <td className="px-4 py-3 whitespace-nowrap">
          {canCancel && (
            <button
              onClick={() => onCancel(order.id)}
              disabled={isCanceling}
              className={cn(
                "flex items-center justify-center w-6 h-6 rounded-md transition-colors",
                isCanceling
                  ? "bg-bg-elevated text-text-muted cursor-not-allowed"
                  : "bg-loss/10 text-loss hover:bg-loss/20 border border-loss/20 hover:border-loss/40"
              )}
              title="Cancel order"
            >
              {isCanceling ? (
                <Loader2 size={11} className="animate-spin" />
              ) : (
                <X size={11} />
              )}
            </button>
          )}
        </td>
      )}
    </motion.tr>
  );
}

// ─── Orders Table ─────────────────────────────────────────────────────────────

interface OrdersTableProps {
  orders: Order[];
  showActions: boolean;
  cancelingId: string | null;
  onCancel: (id: string) => void;
  names: Record<string, { name: string; sector: string }>;
}

function OrdersTable({
  orders,
  showActions,
  cancelingId,
  onCancel,
  names,
}: OrdersTableProps) {
  const headers = [
    "Ticker",
    "Side",
    "Type",
    "Qty (filled/total)",
    "Limit Price",
    "Stop",
    "Status",
    "Placed",
    ...(showActions ? ["Actions"] : []),
  ];

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            {headers.map((h) => (
              <th
                key={h}
                className="metric-label text-left px-4 py-3 font-medium whitespace-nowrap"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/30">
          <AnimatePresence initial={false}>
            {orders.map((order) => (
              <>
                <OrderRow
                  key={order.id}
                  order={order}
                  showActions={showActions}
                  cancelingId={cancelingId}
                  onCancel={onCancel}
                  names={names}
                />
                {order.legs &&
                  order.legs.length > 0 &&
                  order.legs.map((leg) => (
                    <OrderRow
                      key={leg.id}
                      order={leg}
                      showActions={showActions}
                      isLeg
                      cancelingId={cancelingId}
                      onCancel={onCancel}
                      names={names}
                    />
                  ))}
              </>
            ))}
          </AnimatePresence>
        </tbody>
      </table>
    </div>
  );
}

// ─── Empty State ──────────────────────────────────────────────────────────────

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <ListX size={36} className="text-text-muted/40" />
      <p className="text-sm text-text-muted">{message}</p>
    </div>
  );
}

// ─── Toast ────────────────────────────────────────────────────────────────────

function ErrorToast({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8 }}
      className="mt-3 flex items-center gap-2 px-4 py-2.5 bg-loss/10 border border-loss/25 rounded-lg text-xs text-loss"
    >
      <AlertCircle size={13} className="shrink-0" />
      <span className="flex-1">{message}</span>
      <button
        onClick={onDismiss}
        className="text-loss/60 hover:text-loss transition-colors ml-2"
      >
        <X size={12} />
      </button>
    </motion.div>
  );
}

// ─── Tab components ───────────────────────────────────────────────────────────

const TABS = [
  { id: "open", label: "Open Orders" },
  { id: "history", label: "Order History" },
] as const;

type TabId = (typeof TABS)[number]["id"];

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function Orders() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = (searchParams.get("tab") as TabId) ?? "open";
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);

  const [cancelingId, setCancelingId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [names, setNames] = useState<Record<string, { name: string; sector: string }>>({});

  const queryClient = useQueryClient();

  const fetchNames = async (tickers: string[]) => {
    if (!tickers.length) return;
    const unique = [...new Set(tickers)].filter(Boolean);
    try {
      const { data } = await api.get(`/market/names?tickers=${unique.join(',')}`);
      setNames(prev => ({ ...prev, ...data }));
    } catch {}
  };

  // ── Switch tab ────────────────────────────────────────────────────────────
  const switchTab = (tab: TabId) => {
    setActiveTab(tab);
    setSearchParams({ tab });
    setErrorMsg(null);
  };

  // ── Open orders query (polling every 10s) ─────────────────────────────────
  const {
    data: openOrders = [],
    isFetching: openFetching,
    refetch: refetchOpen,
  } = useQuery<Order[]>({
    queryKey: ["orders", "open"],
    queryFn: async () => {
      const res = await api.get<Order[]>("/orders/", { params: { status: "open" } });
      return res.data;
    },
    refetchInterval: 10_000,
    staleTime: 9_000,
  });

  // ── Closed / history query (load once) ───────────────────────────────────
  const {
    data: historyOrders = [],
    isFetching: historyFetching,
    refetch: refetchHistory,
  } = useQuery<Order[]>({
    queryKey: ["orders", "history"],
    queryFn: async () => {
      const res = await api.get<Order[]>("/orders/", {
        params: { status: "closed", limit: 50 },
      });
      // Sort newest first
      return [...res.data].sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
    },
    staleTime: Infinity,
  });

  // ── Fetch company names when orders load ──────────────────────────────────
  useEffect(() => {
    fetchNames(openOrders.map(o => o.ticker));
  }, [openOrders]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetchNames(historyOrders.map(o => o.ticker));
  }, [historyOrders]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Cancel single order ───────────────────────────────────────────────────
  const handleCancel = useCallback(
    async (orderId: string) => {
      const confirmed = window.confirm(
        "Cancel this order? This action cannot be undone."
      );
      if (!confirmed) return;

      setCancelingId(orderId);
      setErrorMsg(null);
      try {
        await api.delete(`/orders/${orderId}`);
        // Optimistically remove from cache
        queryClient.setQueryData<Order[]>(["orders", "open"], (prev) =>
          prev ? prev.filter((o) => o.id !== orderId) : []
        );
      } catch (err: unknown) {
        const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
        const detail =
          axiosErr?.response?.data?.detail ??
          axiosErr?.message ??
          "Failed to cancel order.";
        setErrorMsg(String(detail));
      } finally {
        setCancelingId(null);
      }
    },
    [queryClient]
  );

  // ── Cancel all open orders ────────────────────────────────────────────────
  const handleCancelAll = useCallback(async () => {
    if (openOrders.length === 0) return;
    const confirmed = window.confirm(
      `Cancel all ${openOrders.length} open order${openOrders.length !== 1 ? "s" : ""}? This action cannot be undone.`
    );
    if (!confirmed) return;

    setCancelingId("__all__");
    setErrorMsg(null);
    try {
      await api.delete("/orders/");
      queryClient.setQueryData<Order[]>(["orders", "open"], []);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
      const detail =
        axiosErr?.response?.data?.detail ??
        axiosErr?.message ??
        "Failed to cancel all orders.";
      setErrorMsg(String(detail));
    } finally {
      setCancelingId(null);
    }
  }, [openOrders.length, queryClient]);

  // ── Derived ───────────────────────────────────────────────────────────────
  const isOpen = activeTab === "open";
  const currentOrders = isOpen ? openOrders : historyOrders;
  const isFetching = isOpen ? openFetching : historyFetching;
  const refetch = isOpen ? refetchOpen : refetchHistory;

  return (
    <motion.div
      key="orders-page"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-5"
    >
      {/* ── Page header ───────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Orders</h1>
          <p className="text-sm text-text-muted mt-0.5">
            Manage open orders and view execution history
          </p>
        </div>

        {/* Live indicator (open tab only) */}
        {isOpen && (
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-gain opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-gain" />
            </span>
            <span className="text-xs text-text-muted">Live</span>
          </div>
        )}
      </div>

      {/* ── Tabs ──────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-1 border-b border-border">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => switchTab(tab.id)}
            className={cn(
              "relative px-4 py-2.5 text-sm font-medium transition-colors",
              activeTab === tab.id
                ? "text-text-primary"
                : "text-text-muted hover:text-text-secondary"
            )}
          >
            {tab.label}
            {tab.id === "open" && openOrders.length > 0 && (
              <span className="ml-2 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-accent/20 text-accent text-[10px] font-bold">
                {openOrders.length}
              </span>
            )}
            {activeTab === tab.id && (
              <motion.div
                layoutId="orders-tab-indicator"
                className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent"
                transition={{ duration: 0.2 }}
              />
            )}
          </button>
        ))}
      </div>

      {/* ── Card ──────────────────────────────────────────────────────────── */}
      <div className="card overflow-hidden">
        {/* Card header */}
        <div className="px-5 py-4 border-b border-border flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-text-primary">
              {isOpen ? "Open Orders" : "Order History"}
            </h2>
            {currentOrders.length > 0 && (
              <span className="text-xs text-text-muted font-normal">
                {currentOrders.length}{" "}
                {isOpen ? "active" : "orders"}
              </span>
            )}
            {isFetching && (
              <Loader2 size={12} className="animate-spin text-text-muted ml-1" />
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Cancel All — open tab only */}
            {isOpen && openOrders.length > 0 && (
              <button
                onClick={handleCancelAll}
                disabled={cancelingId !== null}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors",
                  cancelingId === "__all__"
                    ? "bg-loss/10 text-loss/60 border-loss/20 cursor-not-allowed"
                    : "bg-loss/10 text-loss hover:bg-loss/20 border-loss/25 hover:border-loss/50"
                )}
              >
                {cancelingId === "__all__" ? (
                  <Loader2 size={11} className="animate-spin" />
                ) : (
                  <X size={11} />
                )}
                Cancel All
              </button>
            )}

            {/* Refresh */}
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-text-muted hover:text-text-primary border border-border rounded-lg hover:bg-bg-elevated transition-colors"
            >
              <RefreshCw
                size={11}
                className={isFetching ? "animate-spin" : ""}
              />
              Refresh
            </button>
          </div>
        </div>

        {/* Tab content */}
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.18 }}
          >
            {currentOrders.length > 0 ? (
              <OrdersTable
                orders={currentOrders}
                showActions={isOpen}
                cancelingId={cancelingId}
                onCancel={handleCancel}
                names={names}
              />
            ) : (
              <EmptyState
                message={
                  isOpen
                    ? "No open orders"
                    : "No order history found"
                }
              />
            )}
          </motion.div>
        </AnimatePresence>

        {/* Error toast */}
        <AnimatePresence>
          {errorMsg && (
            <div className="px-5 pb-4">
              <ErrorToast
                message={errorMsg}
                onDismiss={() => setErrorMsg(null)}
              />
            </div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
