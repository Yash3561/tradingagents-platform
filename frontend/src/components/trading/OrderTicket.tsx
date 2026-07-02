import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, CheckCircle2, AlertTriangle, ArrowRight } from "lucide-react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { Link } from "react-router-dom";

interface OrderTicketProps {
  ticker: string;
  currentPrice?: number | null;
  onPlaced?: () => void;
}

interface BrokerStatus { connected: boolean; buying_power?: number; }
interface Position { ticker: string; qty: number; avg_entry_price: number; }

type Side = "buy" | "sell";
type OrderType = "market" | "limit";
type Step = "form" | "confirm" | "done";

export default function OrderTicket({ ticker, currentPrice, onPlaced }: OrderTicketProps) {
  const [side, setSide] = useState<Side>("buy");
  const [qty, setQty] = useState<string>("1");
  const [orderType, setOrderType] = useState<OrderType>("market");
  const [limitPrice, setLimitPrice] = useState<string>("");
  const [tif, setTif] = useState<"day" | "gtc">("day");
  const [step, setStep] = useState<Step>("form");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [placedId, setPlacedId] = useState<string | null>(null);

  const [broker, setBroker] = useState<BrokerStatus | null>(null);
  const [held, setHeld] = useState<number>(0);
  const [livePrice, setLivePrice] = useState<number | null>(null);

  const refresh = useCallback(() => {
    api.get("/broker/status").then(r => setBroker(r.data)).catch(() => setBroker({ connected: false }));
    api.get("/portfolio/positions").then(r => {
      const pos: Position | undefined = (r.data as Position[]).find(p => p.ticker === ticker);
      setHeld(pos ? pos.qty : 0);
    }).catch(() => setHeld(0));
    api.get(`/market/quote/${ticker}/live`).then(r => setLivePrice(r.data?.price ?? null)).catch(() => {});
  }, [ticker]);

  useEffect(() => {
    setStep("form");
    setError(null);
    setPlacedId(null);
    setQty("1");
    setLimitPrice("");
    refresh();
  }, [refresh]);

  const price = livePrice ?? currentPrice ?? null;
  const qtyNum = Math.floor(Number(qty) || 0);
  const limitNum = Number(limitPrice) || 0;
  const refPrice = orderType === "limit" && limitNum > 0 ? limitNum : price;
  const estTotal = refPrice != null && qtyNum > 0 ? qtyNum * refPrice : null;

  const validation: string | null = (() => {
    if (qtyNum < 1) return "Quantity must be at least 1 share";
    if (orderType === "limit" && limitNum <= 0) return "Enter a limit price";
    if (side === "sell" && held < 1) return `You don't hold ${ticker} — shorting is not supported`;
    if (side === "sell" && qtyNum > held) return `You hold ${held.toLocaleString()} shares — reduce quantity`;
    if (side === "buy" && estTotal != null && broker?.buying_power != null && estTotal > broker.buying_power)
      return `Estimated cost exceeds buying power ($${broker.buying_power.toLocaleString(undefined, { maximumFractionDigits: 0 })})`;
    return null;
  })();

  const placeOrder = async () => {
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.post("/orders/", {
        ticker,
        side,
        qty: qtyNum,
        order_type: orderType,
        limit_price: orderType === "limit" ? limitNum : null,
        time_in_force: tif,
      });
      setPlacedId(data.order_id);
      setStep("done");
      refresh();
      onPlaced?.();
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === "string" ? detail : detail?.message ?? "Order failed — try again");
      setStep("form");
    } finally {
      setBusy(false);
    }
  };

  if (broker && !broker.connected) {
    return (
      <div className="card p-5 space-y-3">
        <h3 className="text-sm font-semibold text-white">Trade {ticker}</h3>
        <p className="text-xs text-text-muted">
          Connect your Alpaca paper account to place trades.
        </p>
        <Link to="/settings"
          className="inline-block px-3 py-1.5 text-xs font-medium text-white bg-accent hover:bg-accent/90 rounded-lg transition-colors">
          Connect Broker
        </Link>
      </div>
    );
  }

  return (
    <div className="card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">Trade {ticker}</h3>
        {price != null && (
          <span className="text-xs font-mono text-text-secondary">${price.toFixed(2)}</span>
        )}
      </div>

      <AnimatePresence mode="wait">
        {step === "done" ? (
          <motion.div key="done" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-3">
            <div className="flex items-center gap-2 text-gain">
              <CheckCircle2 size={16} />
              <p className="text-sm font-medium">Order submitted</p>
            </div>
            <p className="text-xs text-text-muted font-mono break-all">
              {side.toUpperCase()} {qtyNum} {ticker} · {orderType}{placedId ? ` · ${placedId.slice(0, 8)}…` : ""}
            </p>
            <p className="text-xs text-text-muted">Track it on the Orders page. Fills sync automatically.</p>
            <button
              onClick={() => { setStep("form"); setPlacedId(null); }}
              className="px-3 py-1.5 text-xs font-medium text-text-secondary border border-border rounded-lg hover:bg-bg-elevated transition-colors"
            >
              New Order
            </button>
          </motion.div>
        ) : step === "confirm" ? (
          <motion.div key="confirm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-3">
            <div className="p-3 rounded-lg bg-bg-elevated border border-border space-y-1.5">
              {[
                ["Action", `${side.toUpperCase()} ${qtyNum} share${qtyNum !== 1 ? "s" : ""}`],
                ["Symbol", ticker],
                ["Type", orderType === "market" ? "Market" : `Limit @ $${limitNum.toFixed(2)}`],
                ["Duration", tif === "day" ? "Day" : "Good-til-cancelled"],
                ["Est. total", estTotal != null ? `$${estTotal.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : "—"],
              ].map(([label, value]) => (
                <div key={label} className="flex items-center justify-between">
                  <span className="text-xs text-text-muted">{label}</span>
                  <span className={cn("text-xs font-mono font-semibold",
                    label === "Action" ? (side === "buy" ? "text-gain" : "text-loss") : "text-white")}>
                    {value}
                  </span>
                </div>
              ))}
            </div>
            <p className="text-[10px] text-text-muted">Paper trading — simulated money, real market prices.</p>
            <div className="flex gap-2">
              <button
                onClick={() => setStep("form")}
                disabled={busy}
                className="flex-1 px-3 py-2 text-xs font-medium text-text-secondary border border-border rounded-lg hover:bg-bg-elevated transition-colors disabled:opacity-50"
              >
                Back
              </button>
              <button
                onClick={placeOrder}
                disabled={busy}
                className={cn(
                  "flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold text-white rounded-lg transition-colors disabled:opacity-50",
                  side === "buy" ? "bg-gain/80 hover:bg-gain" : "bg-loss/80 hover:bg-loss"
                )}
              >
                {busy ? <Loader2 size={12} className="animate-spin" /> : null}
                {busy ? "Placing..." : `Confirm ${side.toUpperCase()}`}
              </button>
            </div>
          </motion.div>
        ) : (
          <motion.div key="form" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-3">
            {/* Buy / Sell tabs */}
            <div className="grid grid-cols-2 gap-1 bg-bg-elevated rounded-lg p-1 border border-border">
              {(["buy", "sell"] as Side[]).map(s => (
                <button
                  key={s}
                  onClick={() => setSide(s)}
                  className={cn(
                    "py-1.5 rounded text-xs font-bold uppercase tracking-wide transition-colors",
                    side === s
                      ? s === "buy" ? "bg-gain/20 text-gain" : "bg-loss/20 text-loss"
                      : "text-text-muted hover:text-white"
                  )}
                >
                  {s}
                </button>
              ))}
            </div>

            {/* Qty */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs text-text-muted">Shares</label>
                {side === "sell" && held > 0 && (
                  <button onClick={() => setQty(String(Math.floor(held)))}
                    className="text-[10px] text-accent hover:underline">
                    Max: {Math.floor(held).toLocaleString()}
                  </button>
                )}
              </div>
              <input
                type="number" min={1} step={1} value={qty}
                onChange={e => setQty(e.target.value)}
                className="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm font-mono text-white focus:outline-none focus:border-accent"
              />
            </div>

            {/* Order type + TIF */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-text-muted block mb-1">Type</label>
                <select value={orderType} onChange={e => setOrderType(e.target.value as OrderType)}
                  className="w-full px-2 py-2 bg-bg-elevated border border-border rounded-lg text-xs text-white focus:outline-none focus:border-accent">
                  <option value="market">Market</option>
                  <option value="limit">Limit</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-text-muted block mb-1">Duration</label>
                <select value={tif} onChange={e => setTif(e.target.value as "day" | "gtc")}
                  className="w-full px-2 py-2 bg-bg-elevated border border-border rounded-lg text-xs text-white focus:outline-none focus:border-accent">
                  <option value="day">Day</option>
                  <option value="gtc">GTC</option>
                </select>
              </div>
            </div>

            {orderType === "limit" && (
              <div>
                <label className="text-xs text-text-muted block mb-1">Limit price</label>
                <input
                  type="number" min={0.01} step={0.01} value={limitPrice}
                  onChange={e => setLimitPrice(e.target.value)}
                  placeholder={price != null ? price.toFixed(2) : "0.00"}
                  className="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm font-mono text-white placeholder:text-text-muted focus:outline-none focus:border-accent"
                />
              </div>
            )}

            {/* Summary line */}
            <div className="flex items-center justify-between text-xs">
              <span className="text-text-muted">
                {side === "buy"
                  ? `Buying power: $${(broker?.buying_power ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                  : `You hold: ${Math.floor(held).toLocaleString()} shares`}
              </span>
              <span className="font-mono text-white">
                {estTotal != null ? `≈ $${estTotal.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : ""}
              </span>
            </div>

            {(error || validation) && (
              <p className="flex items-start gap-1.5 text-xs text-warn">
                <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                {error ?? validation}
              </p>
            )}

            <button
              onClick={() => { setError(null); setStep("confirm"); }}
              disabled={validation != null || busy}
              className={cn(
                "w-full flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-bold text-white rounded-lg transition-colors disabled:opacity-40",
                side === "buy" ? "bg-gain/80 hover:bg-gain" : "bg-loss/80 hover:bg-loss"
              )}
            >
              Review {side.toUpperCase()} order <ArrowRight size={12} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
