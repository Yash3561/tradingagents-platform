import { Activity, Database, Wifi } from "lucide-react";

export default function StatusBar() {
  return (
    <footer className="flex items-center gap-6 px-6 py-1.5 bg-bg-surface border-t border-border text-2xs text-text-muted shrink-0">
      <div className="flex items-center gap-1.5">
        <Wifi size={10} className="text-gain" />
        <span>WebSocket: Connected</span>
      </div>
      <div className="flex items-center gap-1.5">
        <Database size={10} className="text-accent" />
        <span>Data: Alpaca Paper</span>
      </div>
      <div className="flex items-center gap-1.5">
        <Activity size={10} className="text-warn" />
        <span>Latency: 12ms</span>
      </div>
      <div className="ml-auto">TradingAgents Platform · v1.0</div>
    </footer>
  );
}
