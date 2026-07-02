import { useEffect, useRef, useState, useCallback } from "react";
import { createChart, ColorType, LineStyle, IPriceLine, UTCTimestamp } from "lightweight-charts";
import { api } from "../../lib/api";
import { Loader2, TrendingUp, CandlestickChart as CandleIcon, LineChart, AreaChart, Pencil, Minus, Eraser } from "lucide-react";
import { cn } from "../../lib/cn";

interface Bar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ChartLevel {
  price: number;
  label: string;
  kind: "support" | "resistance";
}

interface CandlestickChartProps {
  ticker: string;
  period?: string;   // "1mo" | "3mo" | "6mo" | "1y" | "2y"
  interval?: string; // "1d" | "1h" | "1wk"
  height?: number;
  showControls?: boolean;
  levels?: ChartLevel[];   // AI support/resistance lines
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

type ChartStyle = "candles" | "line" | "area";
type DrawMode = "none" | "trendline" | "hline";

const MA_CONFIGS = [
  { key: "ma20", length: 20, color: "#FFB740", label: "MA20" },
  { key: "ma50", length: 50, color: "#2D7DD2", label: "MA50" },
  { key: "ma200", length: 200, color: "#B455F0", label: "MA200" },
] as const;

function computeMA(bars: Bar[], length: number) {
  const out: { time: UTCTimestamp; value: number }[] = [];
  let sum = 0;
  for (let i = 0; i < bars.length; i++) {
    sum += bars[i].close;
    if (i >= length) sum -= bars[i - length].close;
    if (i >= length - 1) out.push({ time: bars[i].time as UTCTimestamp, value: sum / length });
  }
  return out;
}

export default function CandlestickChart({
  ticker,
  period: initialPeriod = "3mo",
  interval: initialInterval = "1d",
  height = 380,
  showControls = true,
  levels = [],
}: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  /* eslint-disable @typescript-eslint/no-explicit-any */
  const seriesRef = useRef<any>(null);
  const volumeSeriesRef = useRef<any>(null);
  const maSeriesRef = useRef<Record<string, any>>({});
  const drawingSeriesRef = useRef<any[]>([]);
  const drawnPriceLinesRef = useRef<IPriceLine[]>([]);
  const levelLinesRef = useRef<IPriceLine[]>([]);
  /* eslint-enable @typescript-eslint/no-explicit-any */
  const barsRef = useRef<Bar[]>([]);
  const pendingPointRef = useRef<{ time: number; price: number } | null>(null);
  const drawModeRef = useRef<DrawMode>("none");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState(initialPeriod);
  const [selectedInterval, setSelectedInterval] = useState(initialInterval);
  const [lastBar, setLastBar] = useState<Bar | null>(null);
  const [chartStyle, setChartStyle] = useState<ChartStyle>("candles");
  const [activeMAs, setActiveMAs] = useState<Set<string>>(new Set(["ma50"]));
  const [drawMode, setDrawMode] = useState<DrawMode>("none");
  const [livePrice, setLivePrice] = useState<number | null>(null);

  drawModeRef.current = drawMode;

  // ── Create chart + main series ────────────────────────────────────────────
  const buildMainSeries = useCallback((chart: ReturnType<typeof createChart>, style: ChartStyle) => {
    if (style === "candles") {
      return chart.addCandlestickSeries({
        upColor: "#00E676", downColor: "#FF3D57",
        borderUpColor: "#00E676", borderDownColor: "#FF3D57",
        wickUpColor: "#00E676", wickDownColor: "#FF3D57",
      });
    }
    if (style === "line") {
      return chart.addLineSeries({ color: "#2D7DD2", lineWidth: 2 });
    }
    return chart.addAreaSeries({
      lineColor: "#2D7DD2", lineWidth: 2,
      topColor: "rgba(45,125,210,0.35)", bottomColor: "rgba(45,125,210,0.02)",
    });
  }, []);

  const setMainSeriesData = useCallback((style: ChartStyle, bars: Bar[]) => {
    if (!seriesRef.current) return;
    if (style === "candles") {
      seriesRef.current.setData(bars);
    } else {
      seriesRef.current.setData(bars.map(b => ({ time: b.time, value: b.close })));
    }
  }, []);

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
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: "#1A2540" },
      timeScale: { borderColor: "#1A2540", timeVisible: true, secondsVisible: false },
      width: containerRef.current.clientWidth,
      height: height,
    });

    seriesRef.current = buildMainSeries(chart, "candles");

    const volumeSeries = chart.addHistogramSeries({
      color: "#2D7DD2",
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    chartRef.current = chart;
    volumeSeriesRef.current = volumeSeries;

    // ── Drawing tools: click handling ──
    chart.subscribeClick(param => {
      const mode = drawModeRef.current;
      if (mode === "none" || !param.point || !seriesRef.current) return;
      const price = seriesRef.current.coordinateToPrice(param.point.y);
      if (price == null) return;

      if (mode === "hline") {
        const pl = seriesRef.current.createPriceLine({
          price: price as number,
          color: "#FFB740",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: "",
        });
        drawnPriceLinesRef.current.push(pl);
        return;
      }

      // trendline: two clicks
      const time = (param.time as number) ?? null;
      if (time == null) return;
      const pending = pendingPointRef.current;
      if (!pending) {
        pendingPointRef.current = { time, price: price as number };
      } else if (time !== pending.time) {
        const lineSeries = chart.addLineSeries({
          color: "#FFB740", lineWidth: 1,
          priceLineVisible: false, lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        const pts = [pending, { time, price: price as number }]
          .sort((a, b) => a.time - b.time)
          .map(p => ({ time: p.time as never, value: p.price }));
        lineSeries.setData(pts);
        drawingSeriesRef.current.push(lineSeries);
        pendingPointRef.current = null;
      }
    });

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
      maSeriesRef.current = {};
      drawingSeriesRef.current = [];
      drawnPriceLinesRef.current = [];
      levelLinesRef.current = [];
    };
  }, [height, buildMainSeries]);

  // ── Chart style switch: rebuild the main series, keep everything else ──────
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !seriesRef.current) return;
    // Re-apply AI levels + clear stale price-line handles (they die with the old series)
    chart.removeSeries(seriesRef.current);
    drawnPriceLinesRef.current = [];
    levelLinesRef.current = [];
    seriesRef.current = buildMainSeries(chart, chartStyle);
    setMainSeriesData(chartStyle, barsRef.current);
    applyLevels();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartStyle]);

  // ── Fetch bars when ticker/period changes ───────────────────────────────────
  const fetchBars = useCallback((showSpinner: boolean) => {
    if (!seriesRef.current) return;
    if (showSpinner) { setLoading(true); setError(null); }

    api
      .get(`/market/ohlcv/${ticker}?period=${selectedPeriod}&interval=${selectedInterval}`)
      .then(({ data }) => {
        const bars: Bar[] = data.bars || [];
        if (bars.length === 0) {
          if (showSpinner) setError("No data available");
          return;
        }
        const sorted = [...bars].sort((a, b) => a.time - b.time);
        barsRef.current = sorted;
        setMainSeriesData(chartStyle, sorted);
        volumeSeriesRef.current?.setData(sorted.map(b => ({
          time: b.time,
          value: b.volume,
          color: b.close >= b.open ? "#00E67640" : "#FF3D5740",
        })));
        refreshMAs(sorted);
        if (showSpinner) chartRef.current?.timeScale().fitContent();
        setLastBar(sorted[sorted.length - 1] ?? null);
      })
      .catch((e: { response?: { data?: { detail?: string } } }) => {
        if (showSpinner) setError(e?.response?.data?.detail ?? "Failed to load chart");
      })
      .finally(() => { if (showSpinner) setLoading(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker, selectedPeriod, selectedInterval, chartStyle]);

  useEffect(() => {
    barsRef.current = [];
    fetchBars(true);
  }, [fetchBars]);

  // ── Live updates: refetch bars every 60s + live price tick every 8s ─────────
  useEffect(() => {
    const barsTimer = setInterval(() => fetchBars(false), 60_000);
    const priceTimer = setInterval(() => {
      api.get(`/market/quote/${ticker}/live`).then(({ data }) => {
        const p = data?.price;
        if (p == null || !barsRef.current.length || !seriesRef.current) return;
        setLivePrice(p);
        const last = barsRef.current[barsRef.current.length - 1];
        const updated = {
          ...last,
          close: p,
          high: Math.max(last.high, p),
          low: Math.min(last.low, p),
        };
        barsRef.current[barsRef.current.length - 1] = updated;
        if (chartStyle === "candles") {
          seriesRef.current.update(updated);
        } else {
          seriesRef.current.update({ time: updated.time, value: p });
        }
        setLastBar(updated);
      }).catch(() => {});
    }, 8_000);
    return () => { clearInterval(barsTimer); clearInterval(priceTimer); };
  }, [ticker, chartStyle, fetchBars]);

  // ── Moving averages ─────────────────────────────────────────────────────────
  const refreshMAs = useCallback((bars: Bar[]) => {
    const chart = chartRef.current;
    if (!chart) return;
    for (const cfg of MA_CONFIGS) {
      const active = activeMAs.has(cfg.key);
      const existing = maSeriesRef.current[cfg.key];
      if (active && bars.length >= cfg.length) {
        const data = computeMA(bars, cfg.length);
        if (existing) {
          existing.setData(data);
        } else {
          const s = chart.addLineSeries({
            color: cfg.color, lineWidth: 1,
            priceLineVisible: false, lastValueVisible: false,
            crosshairMarkerVisible: false,
          });
          s.setData(data);
          maSeriesRef.current[cfg.key] = s;
        }
      } else if (existing) {
        chart.removeSeries(existing);
        delete maSeriesRef.current[cfg.key];
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeMAs]);

  useEffect(() => { refreshMAs(barsRef.current); }, [refreshMAs]);

  // ── AI support/resistance levels ────────────────────────────────────────────
  const applyLevels = useCallback(() => {
    if (!seriesRef.current) return;
    for (const pl of levelLinesRef.current) {
      try { seriesRef.current.removePriceLine(pl); } catch { /* series may be gone */ }
    }
    levelLinesRef.current = [];
    for (const lv of levels) {
      const pl = seriesRef.current.createPriceLine({
        price: lv.price,
        color: lv.kind === "support" ? "#00E676" : "#FF3D57",
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: lv.label,
      });
      levelLinesRef.current.push(pl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [levels]);

  useEffect(() => { applyLevels(); }, [applyLevels]);

  // ── Clear drawings ──────────────────────────────────────────────────────────
  const clearDrawings = () => {
    const chart = chartRef.current;
    if (!chart) return;
    for (const s of drawingSeriesRef.current) chart.removeSeries(s);
    drawingSeriesRef.current = [];
    for (const pl of drawnPriceLinesRef.current) {
      try { seriesRef.current?.removePriceLine(pl); } catch { /* ignore */ }
    }
    drawnPriceLinesRef.current = [];
    pendingPointRef.current = null;
  };

  const changePeriod = (p: (typeof PERIODS)[0]) => {
    setSelectedPeriod(p.period);
    setSelectedInterval(p.interval);
  };

  const toggleMA = (key: string) => {
    setActiveMAs(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const isUp = lastBar ? lastBar.close >= lastBar.open : true;
  const displayPrice = livePrice ?? lastBar?.close;

  const STYLE_BUTTONS: { key: ChartStyle; icon: typeof CandleIcon; title: string }[] = [
    { key: "candles", icon: CandleIcon, title: "Candlesticks" },
    { key: "line", icon: LineChart, title: "Line" },
    { key: "area", icon: AreaChart, title: "Area" },
  ];

  return (
    <div className="card p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <TrendingUp size={16} className="text-accent" />
          <span className="font-mono font-bold text-white">{ticker}</span>
          {displayPrice != null && lastBar && (
            <>
              <span className={`font-mono text-lg font-bold ${isUp ? "text-gain" : "text-loss"}`}>
                ${displayPrice.toFixed(2)}
              </span>
              <span className={`text-xs font-mono ${isUp ? "text-gain" : "text-loss"}`}>
                {isUp ? "▲" : "▼"}{" "}
                {Math.abs(((lastBar.close - lastBar.open) / lastBar.open) * 100).toFixed(2)}%
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

      {/* Toolbar: style, MAs, drawing */}
      {showControls && (
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <div className="flex gap-0.5 bg-bg-elevated rounded-lg p-0.5 border border-border">
            {STYLE_BUTTONS.map(({ key, icon: Icon, title }) => (
              <button
                key={key}
                title={title}
                onClick={() => setChartStyle(key)}
                className={cn(
                  "p-1.5 rounded transition-colors",
                  chartStyle === key ? "bg-accent text-white" : "text-slate-400 hover:text-white"
                )}
              >
                <Icon size={13} />
              </button>
            ))}
          </div>

          <div className="flex gap-1">
            {MA_CONFIGS.map(cfg => (
              <button
                key={cfg.key}
                onClick={() => toggleMA(cfg.key)}
                className={cn(
                  "px-2 py-1 rounded text-xs font-mono border transition-colors",
                  activeMAs.has(cfg.key)
                    ? "border-transparent text-white"
                    : "border-border text-slate-500 hover:text-white bg-bg-elevated"
                )}
                style={activeMAs.has(cfg.key) ? { backgroundColor: cfg.color + "33", color: cfg.color } : undefined}
              >
                {cfg.label}
              </button>
            ))}
          </div>

          <div className="flex gap-0.5 bg-bg-elevated rounded-lg p-0.5 border border-border ml-auto">
            <button
              title="Draw trendline (click two points)"
              onClick={() => setDrawMode(m => m === "trendline" ? "none" : "trendline")}
              className={cn("p-1.5 rounded transition-colors",
                drawMode === "trendline" ? "bg-warn/20 text-warn" : "text-slate-400 hover:text-white")}
            >
              <Pencil size={13} />
            </button>
            <button
              title="Draw horizontal level (click a price)"
              onClick={() => setDrawMode(m => m === "hline" ? "none" : "hline")}
              className={cn("p-1.5 rounded transition-colors",
                drawMode === "hline" ? "bg-warn/20 text-warn" : "text-slate-400 hover:text-white")}
            >
              <Minus size={13} />
            </button>
            <button title="Clear drawings" onClick={clearDrawings}
              className="p-1.5 rounded text-slate-400 hover:text-loss transition-colors">
              <Eraser size={13} />
            </button>
          </div>
        </div>
      )}

      {drawMode !== "none" && (
        <p className="text-[11px] text-warn mb-2">
          {drawMode === "trendline"
            ? "Trendline mode: click two points on the chart. Click the pencil again to exit."
            : "Level mode: click any price on the chart to drop a horizontal line. Click the icon again to exit."}
        </p>
      )}

      {/* Chart container */}
      <div className="relative" style={{ height }}>
        <div ref={containerRef} className="w-full h-full" style={{ cursor: drawMode !== "none" ? "crosshair" : "default" }} />
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
