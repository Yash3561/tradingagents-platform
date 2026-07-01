import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

interface DayData {
  date: string;
  pnl: number;
  trades: number;
}

function getColor(pnl: number): string {
  if (pnl === 0) return "bg-bg-elevated";
  if (pnl > 500) return "bg-gain opacity-90";
  if (pnl > 100) return "bg-gain opacity-60";
  if (pnl > 0)   return "bg-gain opacity-30";
  if (pnl < -500) return "bg-loss opacity-90";
  if (pnl < -100) return "bg-loss opacity-60";
  return "bg-loss opacity-30";
}

export default function PnLCalendar() {
  const [data, setData] = useState<DayData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/portfolio/pnl-calendar")
      .then(r => setData(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="h-24 flex items-center justify-center text-slate-500 text-sm">Loading calendar...</div>;
  if (data.length === 0) return <div className="h-24 flex items-center justify-center text-slate-500 text-sm">No P&L data yet</div>;

  // Build last 13 weeks grid (Mon-Sun columns)
  const today = new Date();
  const weeks: (DayData | null)[][] = [];
  const dataMap = Object.fromEntries(data.map(d => [d.date, d]));

  // Go back 13 weeks from today
  const startDate = new Date(today);
  startDate.setDate(startDate.getDate() - 13 * 7);
  // Align to Monday
  const dayOfWeek = startDate.getDay();
  startDate.setDate(startDate.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1));

  let currentDate = new Date(startDate);
  for (let w = 0; w < 14; w++) {
    const week: (DayData | null)[] = [];
    for (let d = 0; d < 7; d++) {
      const dateStr = currentDate.toISOString().split("T")[0];
      const isWeekend = currentDate.getDay() === 0 || currentDate.getDay() === 6;
      const isFuture = currentDate > today;
      week.push(isWeekend || isFuture ? null : (dataMap[dateStr] ?? { date: dateStr, pnl: 0, trades: 0 }));
      currentDate.setDate(currentDate.getDate() + 1);
    }
    weeks.push(week);
  }

  const totalPnl = data.reduce((s, d) => s + d.pnl, 0);
  const tradingDays = data.filter(d => d.pnl !== 0).length;
  const winDays = data.filter(d => d.pnl > 0).length;

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white">P&L Calendar</h3>
        <div className="flex gap-4 text-xs">
          <span className={totalPnl >= 0 ? "text-gain font-mono" : "text-loss font-mono"}>
            {totalPnl >= 0 ? "+" : ""}${totalPnl.toFixed(0)} 90d
          </span>
          <span className="text-slate-500">{winDays}/{tradingDays} winning days</span>
        </div>
      </div>

      {/* Day labels */}
      <div className="flex gap-1 mb-1 ml-0">
        <div className="grid grid-rows-7 gap-1 mr-1">
          {["M","","W","","F","",""].map((l, i) => (
            <div key={i} className="h-3 w-3 text-[9px] text-slate-600 flex items-center">{l}</div>
          ))}
        </div>
        <div className="flex gap-1 overflow-x-auto">
          {weeks.map((week, wi) => (
            <div key={wi} className="grid grid-rows-7 gap-1">
              {week.map((day, di) => (
                <div
                  key={di}
                  className={cn(
                    "w-3 h-3 rounded-sm transition-colors",
                    day === null ? "bg-transparent" : getColor(day.pnl)
                  )}
                  title={day ? `${day.date}: ${day.pnl >= 0 ? "+" : ""}$${day.pnl.toFixed(2)} (${day.trades} trades)` : ""}
                />
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-2 mt-3">
        <span className="text-[10px] text-slate-600">Less</span>
        {["bg-loss opacity-90","bg-loss opacity-30","bg-bg-elevated","bg-gain opacity-30","bg-gain opacity-90"].map((c, i) => (
          <div key={i} className={cn("w-3 h-3 rounded-sm", c)} />
        ))}
        <span className="text-[10px] text-slate-600">More</span>
      </div>
    </div>
  );
}
