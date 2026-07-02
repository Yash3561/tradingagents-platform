import { useEffect, useState } from "react";
import { Activity, Database, Wifi } from "lucide-react";
import { API_ROOT } from "../../lib/api";

export default function StatusBar() {
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [online, setOnline] = useState(true);

  useEffect(() => {
    const ping = async () => {
      const t0 = performance.now();
      try {
        const r = await fetch(`${API_ROOT}/health`);
        if (!r.ok) throw new Error(String(r.status));
        setLatencyMs(Math.round(performance.now() - t0));
        setOnline(true);
      } catch {
        setOnline(false);
        setLatencyMs(null);
      }
    };
    ping();
    const t = setInterval(ping, 30_000);
    return () => clearInterval(t);
  }, []);

  return (
    <footer className="flex items-center gap-6 px-6 py-1.5 bg-bg-surface border-t border-border text-2xs text-text-muted shrink-0">
      <div className="flex items-center gap-1.5">
        <Wifi size={10} className={online ? "text-gain" : "text-loss"} />
        <span>API: {online ? "Online" : "Offline"}</span>
      </div>
      <div className="flex items-center gap-1.5">
        <Database size={10} className="text-accent" />
        <span>Alpaca Paper — simulated money</span>
      </div>
      {latencyMs != null && (
        <div className="flex items-center gap-1.5">
          <Activity size={10} className={latencyMs < 200 ? "text-gain" : "text-warn"} />
          <span>Latency: {latencyMs}ms</span>
        </div>
      )}
      <div className="ml-auto flex items-center gap-4">
        <span>Educational platform — not financial advice</span>
        <span>TradingAgents · v1.0</span>
      </div>
    </footer>
  );
}
