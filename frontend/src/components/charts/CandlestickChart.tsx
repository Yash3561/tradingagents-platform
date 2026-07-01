import { useEffect, useRef, useState } from "react";
import { createChart, ColorType } from "lightweight-charts";
import { api } from "../../lib/api";
import { Loader2, TrendingUp } from "lucide-react";

interface Bar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface CandlestickChartProps {
  ticker: string;
  period?: string;   // "1mo" | "3mo" | "6mo" | "1y" | "2y"
  interval?: string; // "1d" | "1h" | "1wk"
  height?: number;
  showControls?: boolean;
}

const PERIODS = [
  { label: "1D", period: "1d", interval: "5m" },
  { label: "5D", period: "5d", interval: "15m" },
  { label: "1M", period: "1mo", interval: "1d" },
  { label: "3M", period: "3mo", interval: "1d" },
  { label: "6M", period: "6mo", interval: "1d" },
  { label: "1Y", period: "1y", interval: "1d" },
  { label: "2Y", period: "2y", interval: "1wk" },
];

export default function CandlestickChart({
  ticker,
  period: initialPeriod = "3mo",
  interval: initialInterval = "1d",
  height = 380,
  showControls = true,
}: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const seriesRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const volumeSeriesRef = useRef<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState(initialPeriod);
  const [selectedInterval, setSelectedInterval] = useState(initialInterval);
  const [lastBar, setLastBar] = useState<Bar | null>(null);

  // Create chart once on mount
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#141D30" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "#1A2540" },
        horzLines: { color: "#1A2540" },
      },
      crosshair: {
        mode: 1,
      },
      rightPriceScale: {
        borderColor: "#1A2540",
      },
      timeScale: {
        borderColor: "#1A2540",
        timeVisible: true,
        secondsVisible: false,
      },
      width: containerRef.current.clientWidth,
      height: height,
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#00E676",
      downColor: "#FF3D57",
      borderUpColor: "#00E676",
      borderDownColor: "#FF3D57",
      wickUpColor: "#00E676",
      wickDownColor: "#FF3D57",
    });

    const volumeSeries = chart.addHistogramSeries({
      color: "#2D7DD2",
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    chartRef.current = chart;
    seriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    // Responsive resize
    const ro = new ResizeObserver((entries) => {
      if (entries[0] && chartRef.current) {
        chartRef.current.applyOptions({ width: entries[0].contentRect.width });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [height]);

  // Fetch data when ticker or period changes
  useEffect(() => {
    if (!seriesRef.current) return;
    setLoading(true);
    setError(null);

    api
      .get(`/market/ohlcv/${ticker}?period=${selectedPeriod}&interval=${selectedInterval}`)
      .then(({ data }) => {
        const bars: Bar[] = data.bars || [];
        if (bars.length === 0) {
          setError("No data available");
          return;
        }
        // lightweight-charts needs data sorted ascending by time
        const sorted = [...bars].sort((a, b) => a.time - b.time);
        seriesRef.current?.setData(sorted);
        const volumeData = sorted.map(b => ({
          time: b.time,
          value: b.volume,
          color: b.close >= b.open ? "#00E67640" : "#FF3D5740",
        }));
        volumeSeriesRef.current?.setData(volumeData);
        chartRef.current?.timeScale().fitContent();
        setLastBar(sorted[sorted.length - 1] ?? null);
      })
      .catch((e: { response?: { data?: { detail?: string } } }) =>
        setError(e?.response?.data?.detail ?? "Failed to load chart")
      )
      .finally(() => setLoading(false));
  }, [ticker, selectedPeriod, selectedInterval]);

  const changePeriod = (p: (typeof PERIODS)[0]) => {
    setSelectedPeriod(p.period);
    setSelectedInterval(p.interval);
  };

  const isUp = lastBar ? lastBar.close >= lastBar.open : true;

  return (
    <div className="card p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <TrendingUp size={16} className="text-accent" />
          <span className="font-mono font-bold text-white">{ticker}</span>
          {lastBar && (
            <>
              <span
                className={`font-mono text-lg font-bold ${
                  isUp ? "text-gain" : "text-loss"
                }`}
              >
                ${lastBar.close.toFixed(2)}
              </span>
              <span
                className={`text-xs font-mono ${
                  isUp ? "text-gain" : "text-loss"
                }`}
              >
                {isUp ? "▲" : "▼"}{" "}
                {Math.abs(
                  ((lastBar.close - lastBar.open) / lastBar.open) * 100
                ).toFixed(2)}
                %
              </span>
            </>
          )}
        </div>
        {showControls && (
          <div className="flex gap-1">
            {PERIODS.map((p) => (
              <button
                key={p.label}
                onClick={() => changePeriod(p)}
                className={`px-2 py-0.5 rounded text-xs font-mono transition-colors ${
                  selectedPeriod === p.period
                    ? "bg-accent text-white"
                    : "text-slate-400 hover:text-white hover:bg-bg-elevated"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Chart container */}
      <div className="relative" style={{ height }}>
        <div ref={containerRef} className="w-full h-full" />
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-bg-card/80 rounded">
            <Loader2 size={24} className="text-accent animate-spin" />
          </div>
        )}
        {error && !loading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-slate-500 text-sm">{error}</p>
          </div>
        )}
      </div>
    </div>
  );
}
