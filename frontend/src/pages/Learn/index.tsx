import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BookOpen, Search, X } from "lucide-react";
import { cn } from "../../lib/cn";

// ── Types ──────────────────────────────────────────────────────────────────────

interface Term {
  id: string;
  name: string;
  tagline: string;
  explanation: string;
  example: string;
  category: "technical" | "fundamental" | "risk" | "options" | "agents" | "orders";
}

// ── Data ───────────────────────────────────────────────────────────────────────

const TERMS: Term[] = [
  // ── Technical Analysis ────────────────────────────────────────────────────
  {
    id: "rsi",
    name: "RSI",
    tagline: "Momentum indicator that spots overbought/oversold conditions",
    explanation:
      "Measures buying and selling momentum on a 0–100 scale. Below 30 means the stock has been sold too aggressively and may bounce back (oversold). Above 70 means it has been bought too aggressively and may pull back (overbought). The sweet spot for many traders is 40–60 — neutral momentum.",
    example: "RSI: 28 on NVDA → oversold, potential reversal",
    category: "technical",
  },
  {
    id: "macd",
    name: "MACD",
    tagline: "Trend-following indicator that shows momentum shifts",
    explanation:
      "MACD (Moving Average Convergence Divergence) shows when short-term momentum is shifting relative to the long-term trend. Bullish when the MACD line crosses above its signal line (▲ crossover). Bearish when it crosses below (▼). One of the most widely used indicators on Wall Street.",
    example: "MACD ▲ bullish crossover on AAPL → buy signal",
    category: "technical",
  },
  {
    id: "ma50",
    name: "MA50 — 50-Day Moving Average",
    tagline: "Short-term trend line used by most active traders",
    explanation:
      "The average closing price over the last 50 trading days. Price consistently above MA50 = bullish short-term trend. Price falling below MA50 = caution signal. Many algorithms and funds auto-buy/sell at this level, making it a self-fulfilling support/resistance zone.",
    example: "Price $185 > MA50 $172 → short-term uptrend confirmed",
    category: "technical",
  },
  {
    id: "ma200",
    name: "MA200 — 200-Day Moving Average",
    tagline: "The most important long-term trend indicator",
    explanation:
      "Average over 200 trading days (~10 months). The single most-watched technical level by institutional investors. 'Golden Cross' = MA50 crosses above MA200 (very bullish, often signals a new uptrend). 'Death Cross' = MA50 drops below MA200 (bearish warning). Price above MA200 = long-term bull market.",
    example: "Price $185 > MA200 $160 → long-term uptrend intact",
    category: "technical",
  },
  {
    id: "volume_ratio",
    name: "Volume Ratio",
    tagline: "Measures trading activity relative to normal levels",
    explanation:
      "Today's trading volume divided by the 30-day average volume. A ratio of 2.0x means twice the normal activity — indicating strong conviction behind the price move. Low volume moves (0.5x) are often unreliable and may reverse. High volume on a breakout = confirmation.",
    example: "Vol: 2.3x on breakout day → high conviction, trend likely continues",
    category: "technical",
  },
  {
    id: "momentum",
    name: "Price Momentum (1W/1M/3M)",
    tagline: "How much a stock has moved over different time frames",
    explanation:
      "The rate of price change over 1 week, 1 month, and 3 months. Stocks with strong positive momentum across all time frames tend to continue rising (momentum effect). Divergence — strong 1M but weak 3M — can signal trend reversals.",
    example: "1W: +4.2%, 1M: +12.1%, 3M: +28.4% → strong across all frames",
    category: "technical",
  },
  {
    id: "support",
    name: "Support Level",
    tagline: "A price floor where buyers consistently step in",
    explanation:
      "A price level where a stock has repeatedly bounced. Buyers outnumber sellers at this price, preventing further decline. The more times a support level holds, the stronger it is. When support breaks, it often becomes new resistance.",
    example: "Support at $150 held 3 times — strong floor",
    category: "technical",
  },
  {
    id: "resistance",
    name: "Resistance Level",
    tagline: "A price ceiling where sellers consistently emerge",
    explanation:
      "A price level where sellers have repeatedly prevented the stock from rising further. Breaking above resistance (especially on high volume) often triggers a sharp rally as short sellers cover their positions. Resistance that breaks often becomes new support.",
    example: "Broke above $200 resistance on 2x volume → bullish breakout",
    category: "technical",
  },
  {
    id: "candlestick",
    name: "Candlestick Chart",
    tagline: "Visual representation of price action over time",
    explanation:
      "Each 'candle' shows the open, high, low, and close price for a time period (1 day, 1 hour, etc.). Green/white candle = price closed higher than it opened (bullish). Red candle = closed lower (bearish). The 'wicks' above and below show the full range traded during that period.",
    example: "Green candle: opened $100, high $110, low $98, closed $108",
    category: "technical",
  },
  {
    id: "vix",
    name: "VIX — Volatility Index",
    tagline: "The market's fear gauge — measures expected turbulence",
    explanation:
      "Measures the market's expectation of S&P 500 volatility over the next 30 days. Sometimes called the 'fear index.' Below 15 = calm and complacent markets. 15–25 = normal uncertainty. Above 30 = elevated fear, often a good contrarian buy signal for long-term investors.",
    example: "VIX 35 → high fear, market may be oversold, consider buying",
    category: "technical",
  },

  // ── Fundamental Analysis ──────────────────────────────────────────────────
  {
    id: "pe",
    name: "P/E Ratio",
    tagline: "How much you pay per dollar of company earnings",
    explanation:
      "Price-to-Earnings ratio = stock price ÷ annual earnings per share. A P/E of 30 means you're paying $30 for each $1 the company earns annually. High P/E can mean the stock is expensive OR that investors expect fast future growth. Always compare to the sector average.",
    example: "NVDA P/E: 45 vs Sector avg: 28 → premium but justified by growth",
    category: "fundamental",
  },
  {
    id: "forward_pe",
    name: "Forward P/E",
    tagline: "P/E based on next year's expected earnings",
    explanation:
      "Same calculation as P/E but uses analysts' earnings estimates for the next 12 months instead of last year's results. Forward P/E below trailing P/E = earnings expected to grow (good sign). Forward P/E above trailing P/E = earnings expected to shrink (warning sign).",
    example: "Trailing P/E: 45, Forward P/E: 32 → earnings expected to grow 40%",
    category: "fundamental",
  },
  {
    id: "revenue_growth",
    name: "Revenue Growth YoY",
    tagline: "How fast a company is growing its sales",
    explanation:
      "Year-over-year revenue growth compares this year's sales to the same period last year. The most direct measure of business momentum. 20%+ growth = fast-growing company. Negative growth = shrinking business. AI agents look for 15%+ to flag a stock as fundamentally strong.",
    example: "Revenue growth: +35% YoY → strong business expansion",
    category: "fundamental",
  },
  {
    id: "gross_margin",
    name: "Gross Margin",
    tagline: "Profitability after direct costs — higher is better",
    explanation:
      "The percentage of revenue left after paying for the direct cost of goods sold. High margins mean the business model is efficient. Software companies often have 70–80% margins (very good). Manufacturing: 20–40% is normal. Falling margins = competitive pressure or rising costs.",
    example: "Gross margin: 76% (software) → highly efficient, scalable business",
    category: "fundamental",
  },
  {
    id: "market_cap",
    name: "Market Cap",
    tagline: "The total market value of a company",
    explanation:
      "Market Cap = share price × total shares outstanding. It's how much the market says the entire company is worth. Large-cap ($10B+) = established, lower risk. Mid-cap ($2–10B) = growth phase. Small-cap (under $2B) = higher risk/reward. Mega-cap ($200B+) = Apple, Microsoft, NVIDIA.",
    example: "AAPL: $3.2 trillion market cap → largest company in the world",
    category: "fundamental",
  },
  {
    id: "beta",
    name: "Beta",
    tagline: "How volatile a stock is vs the overall market",
    explanation:
      "Beta measures a stock's price swings relative to the S&P 500. Beta of 1.0 = moves exactly with the market. Beta of 1.5 = 50% more volatile (amplifies moves). Beta of 0.5 = much calmer. Negative beta = moves opposite to market (rare, e.g. gold miners sometimes). High-beta stocks = more risk and reward.",
    example: "TSLA Beta: 2.1 → very volatile, great for trading, risky for holding",
    category: "fundamental",
  },
  {
    id: "week52",
    name: "52-Week High / Low",
    tagline: "The price range over the past year",
    explanation:
      "The highest and lowest prices a stock has traded at over the last 52 weeks. Stocks trading near 52-week highs show strong momentum. Stocks near 52-week lows may be in distress OR undervalued value opportunities. Breaking to new 52-week highs is often a bullish signal.",
    example: "Current: $188, 52W High: $195 → near highs, strong momentum",
    category: "fundamental",
  },

  // ── Risk & Portfolio ──────────────────────────────────────────────────────
  {
    id: "sharpe",
    name: "Sharpe Ratio",
    tagline: "Returns earned per unit of risk — higher is better",
    explanation:
      "Measures how much return you earn per unit of risk taken, compared to a risk-free rate (like T-bills). Above 1.0 = good. Above 2.0 = excellent. Negative = you're earning less than just holding cash risk-free. A key number for comparing strategies: a 30% return with high volatility may have a worse Sharpe than a 15% return that's very steady.",
    example: "Sharpe: 1.8 → solid risk-adjusted returns, beating the benchmark",
    category: "risk",
  },
  {
    id: "drawdown",
    name: "Max Drawdown",
    tagline: "The worst peak-to-trough loss ever experienced",
    explanation:
      "The largest percentage decline from a portfolio's peak value to its lowest point before recovering. A drawdown of -20% means the portfolio fell 20% from its highest point. Lower max drawdown = better capital preservation. A key risk metric — it tells you the worst-case scenario you would have endured.",
    example: "Max Drawdown: -12.4% → portfolio fell 12.4% at worst before recovering",
    category: "risk",
  },
  {
    id: "unrealized_pnl",
    name: "Unrealized P&L",
    tagline: "Paper profit/loss on positions you still hold",
    explanation:
      "The profit or loss on open positions that you haven't sold yet. It's 'paper' money — it fluctuates every second the market is open. Unrealized gains become realized (and taxable) only when you sell. Unrealized losses become locked in only when you sell.",
    example: "NVDA position: +$2,340 unrealized — still open, could go up or down",
    category: "risk",
  },
  {
    id: "position_size",
    name: "Position Size",
    tagline: "What percentage of your portfolio is in one stock",
    explanation:
      "The percentage of your total portfolio value in a single position. Our AI agents cap this at 5% per stock to prevent overconcentration. Professional traders rarely put more than 5–10% in a single name — losing a position that's 5% of your portfolio stings; losing one that's 30% is devastating.",
    example: "5% max = $5,000 on a $100,000 portfolio per agent rule",
    category: "risk",
  },
  {
    id: "stop_loss",
    name: "Stop-Loss",
    tagline: "Automatic sell that limits your downside",
    explanation:
      "A predetermined price where your position automatically sells to cut losses before they get bigger. A 7% stop-loss on a stock bought at $100 means it auto-sells at $93. Our agents set stop-losses on every trade. It removes emotion from the decision: the exit is planned before entry.",
    example: "Entry: $100 → Stop at $93 → Max loss: $700 on 100 shares (-7%)",
    category: "risk",
  },
  {
    id: "buying_power",
    name: "Buying Power",
    tagline: "Cash available to purchase more securities",
    explanation:
      "The total amount you can deploy to buy more positions. For a cash account, it equals your uninvested cash. You should never deploy 100% of buying power — keeping cash reserves lets you act on opportunities and survive drawdowns without being forced to sell.",
    example: "$100K portfolio, 20% invested = $80K buying power remaining",
    category: "risk",
  },
  {
    id: "day_pnl",
    name: "Day P&L",
    tagline: "Today's profit or loss across all positions",
    explanation:
      "The change in your total portfolio value since yesterday's market close. It resets every trading day at market open. Positive = your positions gained value today. Negative = they lost value. The header shows this prominently as a quick health check. Note: it can change even after market close due to after-hours trading.",
    example: "Day P&L: +$347.20 → your positions are up $347 vs yesterday's close",
    category: "risk",
  },

  // ── Options ───────────────────────────────────────────────────────────────
  {
    id: "call",
    name: "Call Option",
    tagline: "The right to BUY shares at a fixed price",
    explanation:
      "A call option gives you the right (but not obligation) to buy 100 shares of a stock at the strike price before the expiry date. You profit when the stock price rises above the strike price plus the premium you paid. Calls are a leveraged bullish bet.",
    example: "NVDA $850 Call for $15 premium → profitable if NVDA > $865 at expiry",
    category: "options",
  },
  {
    id: "put",
    name: "Put Option",
    tagline: "The right to SELL shares at a fixed price",
    explanation:
      "A put option gives you the right to sell 100 shares at the strike price before expiry. You profit when the stock price falls below the strike price minus the premium paid. Puts are used to bet against a stock OR to protect (hedge) an existing long position.",
    example: "AAPL $180 Put for $8 premium → profitable if AAPL < $172 at expiry",
    category: "options",
  },
  {
    id: "strike",
    name: "Strike Price",
    tagline: "The fixed price at which the option can be exercised",
    explanation:
      "The price at which you can buy (call) or sell (put) the underlying shares. The relationship between the strike price and current stock price determines if an option is in-the-money (ITM), at-the-money (ATM), or out-of-the-money (OTM). ATM options have the highest time value.",
    example: "Strike $200 on a $195 stock → slightly OTM call (stock needs to rise $5)",
    category: "options",
  },
  {
    id: "expiry",
    name: "Expiry Date",
    tagline: "When the option contract expires and becomes worthless",
    explanation:
      "All options have an expiration date. After this date, the option is worthless if it hasn't been exercised or sold. Options lose value faster as expiry approaches (time decay). Buying options with longer expiry gives the stock more time to move in your direction.",
    example: "Expires Jul 18, 2025 — only 12 days left, time decay accelerating",
    category: "options",
  },
  {
    id: "iv",
    name: "Implied Volatility (IV)",
    tagline: "The market's expectation of future price movement",
    explanation:
      "IV is derived from option prices and represents how much the market expects the stock to move. High IV = expensive options (market expects a big move, often before earnings). Low IV = cheap options. 'Selling volatility' (writing options when IV is high) is a common strategy.",
    example: "IV: 85% pre-earnings → options are expensive, big move expected",
    category: "options",
  },
  {
    id: "oi",
    name: "Open Interest (OI)",
    tagline: "Total outstanding contracts at a strike price",
    explanation:
      "The total number of open option contracts that haven't been settled or closed. High open interest at a specific strike means many traders are positioned there — these levels often act as price magnets. A sudden spike in OI shows new money entering positions.",
    example: "OI: 45,230 at $200 strike → key level, many traders watching it",
    category: "options",
  },
  {
    id: "itm",
    name: "ITM — In The Money",
    tagline: "Option with immediate intrinsic value",
    explanation:
      "A call is ITM when the stock price is above the strike price. A put is ITM when the stock price is below the strike price. ITM options have 'intrinsic value' — they'd be worth something if exercised right now. The platform highlights ITM options in the chain table.",
    example: "$180 call on $195 stock → $15 ITM (intrinsic value = $15)",
    category: "options",
  },
  {
    id: "otm",
    name: "OTM — Out of The Money",
    tagline: "Option that needs the stock to move to become profitable",
    explanation:
      "A call is OTM when the stock price is below the strike. A put is OTM when the stock is above the strike. OTM options are cheaper (pure time value) but expire worthless more often. They offer higher leverage but lower probability of profit.",
    example: "$220 call on $195 stock → needs stock to rise $25 more to profit",
    category: "options",
  },

  // ── AI Agents ─────────────────────────────────────────────────────────────
  {
    id: "technical_agent",
    name: "Technical Analyst Agent",
    tagline: "Reads price charts and technical signals",
    explanation:
      "The first of four analyst agents that run in parallel. It analyzes RSI, MACD, moving averages, support/resistance levels, and recent price action. Outputs a directional signal (BUY/SELL/HOLD) with a confidence score. Other agents get this report as input.",
    example: "RSI 28, above MA200, MACD bullish → BUY signal, 78% confidence",
    category: "agents",
  },
  {
    id: "sentiment_agent",
    name: "Sentiment Analyst Agent",
    tagline: "Reads market positioning and institutional behavior",
    explanation:
      "Analyzes institutional fund flows, put/call ratios, short interest percentages, and options positioning. High short interest can lead to short squeezes. Low put/call ratios suggest complacency. This agent catches signals that pure price analysis misses.",
    example: "Institutional buying +$2.3B, put/call 0.65, short interest 8% → bullish",
    category: "agents",
  },
  {
    id: "news_agent",
    name: "News Analyst Agent",
    tagline: "Scans headlines for material events and catalysts",
    explanation:
      "Reads recent news headlines, identifies material events (earnings beats, FDA approvals, lawsuits, CEO changes), flags upcoming catalysts (earnings date, product launches), and identifies risk events (regulatory investigations, macro headwinds). Bad news that's already priced in is not bearish.",
    example:
      "Earnings beat: +12% vs estimates. No material negative news. Upcoming product launch.",
    category: "agents",
  },
  {
    id: "fundamental_agent",
    name: "Fundamental Analyst Agent",
    tagline: "Evaluates company valuation vs sector peers",
    explanation:
      "Checks P/E ratio vs sector average, revenue growth, gross margins, and forward earnings estimates. A stock can have great technicals but be a value trap if fundamentally weak. This agent catches cases where the stock is overbought vs its fundamentals.",
    example:
      "P/E below sector avg, 35% revenue growth, margins expanding → fundamentally strong",
    category: "agents",
  },
  {
    id: "debate",
    name: "Bull vs Bear Debate",
    tagline: "Two AI researchers argue opposite sides",
    explanation:
      "After the four analysts report, a Bull researcher and a Bear researcher debate for N rounds. Bull makes the strongest possible case for buying. Bear argues the strongest case against. Each round, they respond to each other's arguments. The debate winner (Bull or Bear) strongly influences the final decision.",
    example: "Bull: strong momentum + earnings beat. Bear: stretched P/E. Bull wins 2-0.",
    category: "agents",
  },
  {
    id: "risk_manager",
    name: "Risk Manager Agent",
    tagline: "The last line of defense — has veto power",
    explanation:
      "Reviews the proposed trade from all angles. Assesses risk level (LOW/MEDIUM/HIGH). Sets position size (max 5% of portfolio) and stop-loss percentage. Has absolute veto power: if risk level is HIGH, the trade is rejected regardless of bullish signals. This agent protects the portfolio.",
    example: "Risk: MEDIUM, Position: 3%, Stop-loss: 7% → APPROVED",
    category: "agents",
  },
  {
    id: "portfolio_manager",
    name: "Portfolio Manager Agent",
    tagline: "The final decision maker — BUY, HOLD, or SELL",
    explanation:
      "Takes input from all 6 previous agents and makes the final trading decision. Sets the exact order type, position size percentage, limit price (if applicable), and confirms the stop-loss. Requires 70%+ confidence to recommend BUY or SELL. Below that, it outputs HOLD.",
    example: "Decision: BUY 47 shares NVDA @ market, 3% position, stop $831",
    category: "agents",
  },
  {
    id: "opp_score",
    name: "Opportunity Score (0–100)",
    tagline: "Pre-screen score before expensive AI runs",
    explanation:
      "A composite technical score calculated for free before any AI agents are called. Based on RSI position, price vs MA50/MA200, 1-week momentum, MACD direction, and volume ratio. Only stocks scoring above a threshold get sent through the full 7-agent AI pipeline, keeping API costs low.",
    example: "Score 74 → strong buy candidate, runs full AI analysis",
    category: "agents",
  },

  // ── Order Types ───────────────────────────────────────────────────────────
  {
    id: "market_order",
    name: "Market Order",
    tagline: "Execute immediately at the current market price",
    explanation:
      "The simplest order type: buy or sell right now at whatever price the market offers. Guaranteed to fill but price isn't guaranteed — in fast-moving markets, you might get a slightly different price than expected (slippage). Best for liquid stocks during market hours.",
    example: "Market buy 100 AAPL → fills at $189.23 within milliseconds",
    category: "orders",
  },
  {
    id: "limit_order",
    name: "Limit Order",
    tagline: "Buy/sell only at your specified price or better",
    explanation:
      "You set the maximum price you'll pay (buy limit) or minimum price you'll accept (sell limit). Not guaranteed to fill — the stock must reach your price. Gives you price certainty at the cost of execution certainty. Great for volatile stocks or after-hours trading.",
    example: "Limit buy 100 AAPL at $185 → only fills if price drops to $185",
    category: "orders",
  },
  {
    id: "stop_order",
    name: "Stop Order",
    tagline: "Triggers automatically when price hits a level",
    explanation:
      "A stop order becomes a market order when the stock hits your trigger price. Used primarily as stop-losses to automatically cut positions when they move against you. Our agents set stop orders on every trade to enforce the maximum loss rule.",
    example: "Stop sell 100 AAPL at $175 → auto-sells if price drops to $175",
    category: "orders",
  },
  {
    id: "bracket_order",
    name: "Bracket Order",
    tagline: "Entry + take-profit + stop-loss in one package",
    explanation:
      "Three orders in one: (1) the entry order, (2) a take-profit limit order above your entry, and (3) a stop-loss order below. When one of the exit orders fills, the other automatically cancels. This completely automates trade management — you set it and walk away.",
    example: "Buy at $100 → Take-profit at $115 → Stop-loss at $93 → all automated",
    category: "orders",
  },
  {
    id: "paper_trading",
    name: "Paper Trading",
    tagline: "Real trading mechanics, simulated money",
    explanation:
      "Paper trading uses real market prices and real order mechanics but with virtual money — nothing real is at risk. This platform connects to Alpaca's paper trading environment by default. It's the safest way to test AI strategies before committing real capital.",
    example: "Platform default: Alpaca paper account with $100,000 virtual starting balance",
    category: "orders",
  },
  {
    id: "time_in_force",
    name: "Time in Force (TIF)",
    tagline: "How long your order stays active",
    explanation:
      "DAY = order cancels automatically at 4:00 PM ET market close if unfilled. GTC (Good Till Canceled) = stays open until it fills or you cancel manually (can stay open for weeks). IOC (Immediate or Cancel) = fills whatever it can right now, cancels the rest. GTD = Good Till Date.",
    example: "GTC limit order at $185 → stays open until AAPL drops to that price",
    category: "orders",
  },
  {
    id: "fill_price",
    name: "Fill Price",
    tagline: "The actual price your order was executed at",
    explanation:
      "The real price at which your order was matched with a buyer or seller. For market orders, the fill price may differ slightly from the price you saw when you clicked — this difference is called slippage. For limit orders, fill price is always at your limit or better.",
    example: "Market order sent at $189.20, filled at $189.23 (3¢ slippage)",
    category: "orders",
  },
];

// ── Categories ────────────────────────────────────────────────────────────────

const CATEGORIES = [
  { id: "all", label: "All Terms" },
  { id: "technical", label: "Technical Analysis" },
  { id: "fundamental", label: "Fundamental Analysis" },
  { id: "risk", label: "Risk & Portfolio" },
  { id: "options", label: "Options" },
  { id: "agents", label: "AI Agents" },
  { id: "orders", label: "Order Types" },
] as const;

type CategoryId = (typeof CATEGORIES)[number]["id"];

// ── Category styling ──────────────────────────────────────────────────────────

const CATEGORY_DOT: Record<Term["category"], string> = {
  technical: "bg-[#2D7DD2]",
  fundamental: "bg-[#FFB740]",
  risk: "bg-[#FF3D57]",
  options: "bg-[#00E676]",
  agents: "bg-[#2D7DD2]",
  orders: "bg-slate-400",
};

const CATEGORY_BADGE: Record<Term["category"], string> = {
  technical: "text-[#2D7DD2] bg-[#2D7DD2]/10 border-[#2D7DD2]/20",
  fundamental: "text-[#FFB740] bg-[#FFB740]/10 border-[#FFB740]/20",
  risk: "text-[#FF3D57] bg-[#FF3D57]/10 border-[#FF3D57]/20",
  options: "text-[#00E676] bg-[#00E676]/10 border-[#00E676]/20",
  agents: "text-[#2D7DD2] bg-[#2D7DD2]/10 border-[#2D7DD2]/20",
  orders: "text-slate-400 bg-slate-400/10 border-slate-400/20",
};

const CATEGORY_LABEL: Record<Term["category"], string> = {
  technical: "Technical",
  fundamental: "Fundamental",
  risk: "Risk",
  options: "Options",
  agents: "AI Agents",
  orders: "Orders",
};

// ── TermCard ──────────────────────────────────────────────────────────────────

function TermCard({ term }: { term: Term }) {
  return (
    <div
      className="card flex flex-col gap-3 p-5 rounded-xl transition-all duration-200 hover:border-white/10"
      style={{
        backgroundColor: "#141D30",
        border: "1px solid rgba(255,255,255,0.05)",
      }}
    >
      {/* Header row: dot + name + badge */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <span
            className={cn(
              "w-2 h-2 rounded-full flex-shrink-0 mt-[3px]",
              CATEGORY_DOT[term.category]
            )}
          />
          <h3 className="font-semibold text-sm leading-tight" style={{ color: "#2D7DD2" }}>
            {term.name}
          </h3>
        </div>
        <span
          className={cn(
            "badge-neutral flex-shrink-0 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border uppercase tracking-wide",
            CATEGORY_BADGE[term.category]
          )}
        >
          {CATEGORY_LABEL[term.category]}
        </span>
      </div>

      {/* Tagline */}
      <p className="text-white text-xs font-medium leading-snug -mt-0.5">
        {term.tagline}
      </p>

      {/* Explanation */}
      <p className="text-slate-400 text-sm leading-relaxed flex-1">
        {term.explanation}
      </p>

      {/* Example box */}
      <div
        className="rounded-lg px-3 py-2.5 mt-auto"
        style={{ backgroundColor: "#1A2540" }}
      >
        <p className="font-mono text-xs leading-relaxed" style={{ color: "#00E676" }}>
          <span className="text-slate-500 font-sans not-italic mr-1.5">ex.</span>
          {term.example}
        </p>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Learn() {
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<CategoryId>("all");

  const normalizedSearch = search.trim().toLowerCase();

  const filtered = TERMS.filter((term) => {
    const matchesCategory =
      activeCategory === "all" || term.category === activeCategory;
    if (!matchesCategory) return false;
    if (!normalizedSearch) return true;
    return (
      term.name.toLowerCase().includes(normalizedSearch) ||
      term.tagline.toLowerCase().includes(normalizedSearch) ||
      term.explanation.toLowerCase().includes(normalizedSearch)
    );
  });

  const resultLabel = normalizedSearch
    ? `${filtered.length} result${filtered.length !== 1 ? "s" : ""} for "${search.trim()}"`
    : `Showing ${filtered.length} term${filtered.length !== 1 ? "s" : ""}`;

  return (
    <div className="min-h-screen" style={{ backgroundColor: "#0A0E1A" }}>
      {/* Sticky header */}
      <div
        className="border-b border-white/5 sticky top-0 z-20"
        style={{ backgroundColor: "#0F1629" }}
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {/* Title */}
          <div className="flex items-center gap-3 mb-6">
            <div
              className="p-2 rounded-lg flex items-center justify-center"
              style={{ backgroundColor: "#2D7DD2" }}
            >
              <BookOpen className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white tracking-tight">
                Trading Glossary
              </h1>
              <p className="text-sm text-slate-400 mt-0.5">
                Every term used on this platform, explained clearly
              </p>
            </div>
          </div>

          {/* Search */}
          <div className="relative mb-5">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 pointer-events-none" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search terms, definitions..."
              className="w-full pl-10 pr-10 py-2.5 rounded-lg text-sm text-white placeholder-slate-500 outline-none focus:ring-2 transition-all"
              style={{
                backgroundColor: "#141D30",
                border: "1px solid rgba(255,255,255,0.07)",
                // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                // @ts-ignore
                "--tw-ring-color": "rgba(45,125,210,0.5)",
              }}
            />
            <AnimatePresence>
              {search && (
                <motion.button
                  initial={{ opacity: 0, scale: 0.7 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.7 }}
                  transition={{ duration: 0.15 }}
                  onClick={() => setSearch("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                  aria-label="Clear search"
                >
                  <X className="w-4 h-4" />
                </motion.button>
              )}
            </AnimatePresence>
          </div>

          {/* Category pills */}
          <div className="flex flex-wrap gap-2">
            {CATEGORIES.map((cat) => {
              const isActive = activeCategory === cat.id;
              return (
                <button
                  key={cat.id}
                  onClick={() => setActiveCategory(cat.id)}
                  className={cn(
                    "px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-200 border",
                    isActive
                      ? "text-white border-[#2D7DD2] shadow-lg"
                      : "text-slate-400 border-white/10 hover:text-white hover:border-white/20"
                  )}
                  style={
                    isActive
                      ? {
                          backgroundColor: "#2D7DD2",
                          boxShadow: "0 4px 14px rgba(45,125,210,0.3)",
                        }
                      : { backgroundColor: "#141D30" }
                  }
                >
                  {cat.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Result count */}
        <div className="mb-6">
          <p className="text-sm text-slate-500">{resultLabel}</p>
        </div>

        {/* Grid or empty state */}
        {filtered.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col items-center justify-center py-24 text-center gap-4"
          >
            <BookOpen className="w-10 h-10 text-slate-600" />
            <div>
              <p className="text-white font-semibold">No terms found</p>
              <p className="text-slate-500 text-sm mt-1">
                Try a different search term or clear the filter
              </p>
            </div>
            <button
              onClick={() => {
                setSearch("");
                setActiveCategory("all");
              }}
              className="px-4 py-2 rounded-lg text-sm font-medium transition-colors border"
              style={{
                color: "#2D7DD2",
                backgroundColor: "rgba(45,125,210,0.08)",
                borderColor: "rgba(45,125,210,0.25)",
              }}
            >
              Clear filters
            </button>
          </motion.div>
        ) : (
          <motion.div layout className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <AnimatePresence mode="popLayout">
              {filtered.map((term, i) => (
                <motion.div
                  key={term.id}
                  layout
                  initial={{ opacity: 0, y: 20 }}
                  animate={{
                    opacity: 1,
                    y: 0,
                    transition: {
                      delay: i * 0.04,
                      duration: 0.35,
                      ease: [0.25, 0.46, 0.45, 0.94],
                    },
                  }}
                  exit={{ opacity: 0, y: -10, transition: { duration: 0.2 } }}
                >
                  <TermCard term={term} />
                </motion.div>
              ))}
            </AnimatePresence>
          </motion.div>
        )}
      </div>
    </div>
  );
}
