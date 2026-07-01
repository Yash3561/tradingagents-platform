import { useState, useRef, useEffect } from "react";
import { HelpCircle } from "lucide-react";
import { cn } from "../../lib/cn";

interface TooltipProps {
  content: string;
  title?: string;
  children?: React.ReactNode;
  className?: string;
  side?: "top" | "bottom" | "left" | "right";
}

/**
 * Hover tooltip with plain-English explanations for financial terms.
 * Usage:
 *   <Tooltip title="RSI" content="Measures momentum 0-100. Below 30 = oversold." />
 *   <Tooltip content="..."><span>Custom trigger</span></Tooltip>
 */
export default function Tooltip({ content, title, children, className, side = "top" }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const show = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setVisible(true);
  };
  const hide = () => {
    timerRef.current = setTimeout(() => setVisible(false), 100);
  };

  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);

  const posClass = {
    top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
    bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
    left: "right-full top-1/2 -translate-y-1/2 mr-2",
    right: "left-full top-1/2 -translate-y-1/2 ml-2",
  }[side];

  const arrowClass = {
    top: "top-full left-1/2 -translate-x-1/2 border-t-[#1A2540] border-x-transparent border-b-transparent border-[5px]",
    bottom: "bottom-full left-1/2 -translate-x-1/2 border-b-[#1A2540] border-x-transparent border-t-transparent border-[5px]",
    left: "left-full top-1/2 -translate-y-1/2 border-l-[#1A2540] border-y-transparent border-r-transparent border-[5px]",
    right: "right-full top-1/2 -translate-y-1/2 border-r-[#1A2540] border-y-transparent border-l-transparent border-[5px]",
  }[side];

  return (
    <div ref={ref} className={cn("relative inline-flex items-center", className)}
      onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}>
      {children ?? (
        <button type="button" className="text-text-muted/50 hover:text-accent transition-colors focus:outline-none ml-1">
          <HelpCircle size={12} />
        </button>
      )}
      {visible && (
        <div className={cn("absolute z-50 w-64 pointer-events-none", posClass)}>
          <div className="bg-[#1A2540] border border-[#2D7DD2]/30 rounded-lg p-3 shadow-xl shadow-black/40">
            {title && (
              <p className="text-xs font-semibold text-accent mb-1">{title}</p>
            )}
            <p className="text-xs text-slate-300 leading-relaxed">{content}</p>
          </div>
          <div className={cn("absolute w-0 h-0 border-solid", arrowClass)} />
        </div>
      )}
    </div>
  );
}

// ── Pre-built tooltips for common financial terms ─────────────────────────────

export const TERM_TOOLTIPS: Record<string, { title: string; content: string }> = {
  rsi: {
    title: "RSI — Relative Strength Index",
    content: "Momentum indicator on a 0–100 scale. Below 30 = oversold (potential bounce). Above 70 = overbought (potential pullback). Neutral zone: 40–60.",
  },
  macd: {
    title: "MACD — Moving Average Convergence Divergence",
    content: "Shows the relationship between two moving averages. Bullish when the MACD line crosses above its signal line (▲). Bearish when it crosses below (▼).",
  },
  ma50: {
    title: "MA50 — 50-Day Moving Average",
    content: "The average closing price over the last 50 trading days. Price trading above MA50 is generally considered bullish short-term momentum.",
  },
  ma200: {
    title: "MA200 — 200-Day Moving Average",
    content: "The average closing price over the last 200 trading days. The most widely watched long-term trend indicator. Above = bull market, Below = bear market.",
  },
  pe: {
    title: "P/E — Price-to-Earnings Ratio",
    content: "How much investors pay per $1 of earnings. P/E of 25 means you're paying $25 for each $1 the company earns. Higher = more expensive (or faster growth expected).",
  },
  beta: {
    title: "Beta — Market Sensitivity",
    content: "How much a stock moves relative to the market. Beta of 1.5 = moves 50% more than the market. Beta of 0.5 = moves 50% less. Negative beta = moves opposite to market.",
  },
  sharpe: {
    title: "Sharpe Ratio",
    content: "Risk-adjusted return. How much return you earn per unit of risk taken. Above 1 = good. Above 2 = very good. Negative = worse than risk-free rate.",
  },
  drawdown: {
    title: "Max Drawdown",
    content: "The largest peak-to-trough decline in portfolio value. A drawdown of -15% means the portfolio fell 15% from its highest point before recovering.",
  },
  vol_ratio: {
    title: "Volume Ratio",
    content: "Today's trading volume divided by the 30-day average volume. 1.5x = 50% more volume than usual — indicates stronger conviction in the price move.",
  },
  vix: {
    title: "VIX — Volatility Index",
    content: "The market's 'fear gauge'. Measures expected 30-day volatility of the S&P 500. Below 15 = calm markets. 15–25 = normal. Above 30 = elevated fear/uncertainty.",
  },
  iv: {
    title: "IV — Implied Volatility",
    content: "The market's expectation of how much an options contract's underlying stock will move. Higher IV = more expensive options. Often spikes before earnings.",
  },
  oi: {
    title: "OI — Open Interest",
    content: "The total number of outstanding options contracts that haven't been settled. High OI at a strike price means many traders are positioned there — acts as support/resistance.",
  },
  itm: {
    title: "ITM — In The Money",
    content: "A call option is ITM when the stock price is above the strike price (profitable if exercised now). A put option is ITM when stock price is below the strike price.",
  },
  momentum: {
    title: "Price Momentum",
    content: "The rate of change in price over a period. 1W = 1-week return, 1M = 1-month return, 3M = 3-month return. Strong positive momentum often continues short-term.",
  },
  score: {
    title: "Opportunity Score (0–100)",
    content: "A composite signal scored by RSI, trend (vs MA50/MA200), price momentum, MACD direction, and volume. 62+ = strong buy candidate. <40 = bearish. 40–62 = neutral.",
  },
  confidence: {
    title: "AI Confidence",
    content: "How certain the AI agent is about its recommendation (0–100%). The platform requires 70%+ confidence to place a real trade. Below 60% = no signal generated.",
  },
  stopLoss: {
    title: "Stop-Loss",
    content: "A price level where a position is automatically sold to limit losses. A 7% stop-loss on a $100 stock means it sells automatically if the price drops to $93.",
  },
  buyingPower: {
    title: "Buying Power",
    content: "The total amount available to purchase securities in your account. For a cash account, this equals your cash balance. For margin accounts, it's typically 2x your cash.",
  },
  unrealizedPnl: {
    title: "Unrealized P&L",
    content: "Paper profit or loss on positions you still hold. It becomes 'realized' only when you sell. Unrealized gains/losses fluctuate with the market price.",
  },
};

export function TermTooltip({ term, side }: { term: keyof typeof TERM_TOOLTIPS; side?: "top" | "bottom" | "left" | "right" }) {
  const t = TERM_TOOLTIPS[term];
  if (!t) return null;
  return <Tooltip title={t.title} content={t.content} side={side} />;
}
