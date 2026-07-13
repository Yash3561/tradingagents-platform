"""
Structured agent runner using Claude's tool_use / json mode
to enforce typed contracts between agents.

Each agent gets:
  - A focused system prompt (its role only)
  - Only the data it needs (not the full state blob)
  - A strict JSON schema it must conform to
  - REAL market data fetched from yfinance

No free-form text parsing between agents.
"""

from __future__ import annotations
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, UTC
from typing import Any

from openai import OpenAI
import structlog

from app.config import get_settings
from app.agents.contracts import (
    TechnicalReport, SentimentReport, NewsReport, FundamentalReport,
    AnalystBundle, ResearcherDebate, RiskAssessment, FinalDecision,
    Signal, Decision, RiskLevel,
)
from app.core.postgres import AsyncSessionLocal
from app.core.websocket_manager import ws_manager
from app.db.models.agent_run import AgentRun

log = structlog.get_logger()
settings = get_settings()


# ── Real market data fetching ──────────────────────────────────────────────────

def _fetch_market_data(ticker: str) -> dict:
    """Fetch real price, technical, and fundamental data via yfinance."""
    try:
        import yfinance as yf
        import numpy as np

        t = yf.Ticker(ticker)
        hist = t.history(period="1y", interval="1d")
        info = t.info or {}

        if hist.empty:
            return {"error": "No price history available"}

        close = hist["Close"]
        volume = hist["Volume"]
        current_price = float(close.iloc[-1])
        prev_close = float(close.iloc[-2]) if len(close) >= 2 else current_price

        # Moving averages
        ma50 = float(close.tail(50).mean()) if len(close) >= 50 else None
        ma200 = float(close.tail(200).mean()) if len(close) >= 200 else None

        # RSI-14
        delta = close.diff()
        gain = delta.clip(lower=0).tail(14).mean()
        loss = (-delta.clip(upper=0)).tail(14).mean()
        rsi = round(100 - (100 / (1 + gain / loss)), 1) if loss != 0 else 50.0

        # MACD
        macd_series = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
        macd_line = round(float(macd_series.iloc[-1]), 3)
        signal_line = round(float(macd_series.ewm(span=9, adjust=False).mean().iloc[-1]), 3)

        # ATR-14 (Average True Range) for dynamic stop sizing
        high_s = hist["High"]
        low_s  = hist["Low"]
        tr = (high_s - low_s).tail(14)
        atr_14 = float(tr.mean())
        atr_pct = round(atr_14 / current_price * 100, 2)  # ATR as % of current price

        # Volume context
        avg_vol_30d = int(volume.tail(30).mean()) if len(volume) >= 30 else int(volume.mean())
        today_vol = int(volume.iloc[-1])
        vol_ratio = round(today_vol / avg_vol_30d, 2) if avg_vol_30d else 1.0

        # Price momentum
        price_1w = float(close.iloc[-6]) if len(close) >= 6 else current_price
        price_1m = float(close.iloc[-22]) if len(close) >= 22 else current_price
        price_3m = float(close.iloc[-66]) if len(close) >= 66 else current_price

        return {
            "current_price": round(current_price, 2),
            "prev_close": round(prev_close, 2),
            "change_today_pct": round((current_price - prev_close) / prev_close * 100, 2),
            "change_1w_pct": round((current_price - price_1w) / price_1w * 100, 2),
            "change_1m_pct": round((current_price - price_1m) / price_1m * 100, 2),
            "change_3m_pct": round((current_price - price_3m) / price_3m * 100, 2),
            "52w_high": round(float(hist["High"].max()), 2),
            "52w_low": round(float(hist["Low"].min()), 2),
            "pct_from_52w_high": round((current_price / float(hist["High"].max()) - 1) * 100, 1),
            "ma_50": round(ma50, 2) if ma50 else None,
            "ma_200": round(ma200, 2) if ma200 else None,
            "above_ma50": bool(current_price > ma50) if ma50 else None,
            "above_ma200": bool(current_price > ma200) if ma200 else None,
            "rsi_14": rsi,
            "macd_line": macd_line,
            "macd_signal": signal_line,
            "macd_bullish": macd_line > signal_line,
            "volume_today": today_vol,
            "avg_volume_30d": avg_vol_30d,
            "volume_ratio": vol_ratio,
            "atr_14": round(atr_14, 4),
            "atr_pct": atr_pct,
            # Fundamentals from info
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "peg_ratio": info.get("pegRatio"),
            "revenue_growth_yoy": info.get("revenueGrowth"),
            "earnings_growth_yoy": info.get("earningsGrowth"),
            "gross_margin": info.get("grossMargins"),
            "operating_margin": info.get("operatingMargins"),
            "profit_margin": info.get("profitMargins"),
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "free_cash_flow": info.get("freeCashflow"),
            "market_cap": info.get("marketCap"),
            "enterprise_value": info.get("enterpriseValue"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "beta": info.get("beta"),
            "short_ratio": info.get("shortRatio"),
            "short_percent_float": info.get("shortPercentOfFloat"),
            "held_by_institutions": info.get("heldPercentInstitutions"),
            "analyst_target_price": info.get("targetMeanPrice"),
            "analyst_recommendation": info.get("recommendationKey"),
            "num_analyst_opinions": info.get("numberOfAnalystOpinions"),
        }
    except Exception as e:
        log.warning("market_data.fetch_error", ticker=ticker, error=str(e))
        return {"error": str(e)}


def _inject_live_price(market_data: dict, ticker: str) -> dict:
    """
    Try to get a fresher price from Redis (populated by price_feed worker).
    If found, overwrite current_price in the market_data dict.
    """
    try:
        from app.broker.alpaca_client import get_live_price
        live = get_live_price(ticker)
        if live and live > 0:
            log.info("market_data.live_price", ticker=ticker, live=live,
                     yfinance=market_data.get("current_price"))
            market_data = dict(market_data)
            market_data["current_price"] = round(live, 2)
    except Exception:
        pass
    return market_data


def _fetch_news(ticker: str) -> list[str]:
    """Fetch recent news headlines via yfinance."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        news_items = getattr(t, "news", []) or []
        headlines = []
        for n in news_items[:10]:
            title = n.get("title", "")
            publisher = n.get("publisher", "")
            if title:
                headlines.append(f"- {title} [{publisher}]")
        return headlines
    except Exception:
        return []


# ── NIM (NVIDIA) structured output helper ─────────────────────────────────────

# The free NIM tier enforces a requests-per-minute cap. Pace all calls
# process-wide so scans (8 tickers × ~8 calls) stay under it.
import threading as _threading
import time as _time_mod
_nim_pace_lock = _threading.Lock()
_nim_last_call = [0.0]
NIM_MIN_CALL_INTERVAL_S = 2.0


def _nim_throttle():
    with _nim_pace_lock:
        wait = _nim_last_call[0] + NIM_MIN_CALL_INTERVAL_S - _time_mod.monotonic()
        if wait > 0:
            _time_mod.sleep(wait)
        _nim_last_call[0] = _time_mod.monotonic()


def _nim_structured(
    system: str,
    user: str,
    schema: type,
    model: str = "deepseek-ai/deepseek-v4-flash",
) -> dict:
    """
    Call DeepSeek via NVIDIA NIM using OpenAI-compatible tool_use.
    Forces the model to respond in the exact contract shape.
    Returns the parsed dict (not yet validated — call schema(**result) after).
    """
    client = OpenAI(
        base_url=settings.nvidia_base_url,
        api_key=settings.nvidia_api_key,
    )

    json_schema = schema.model_json_schema()
    tool_schema = {k: v for k, v in json_schema.items() if k != "$defs"}
    if "$defs" in json_schema:
        tool_schema = _inline_refs(json_schema)
    # OpenAI tool parameters schema must not have a top-level 'title'
    tool_schema.pop("title", None)

    # NIM free tier throws transient 429/5xx under load — retry with backoff
    import time as _time
    import random as _random
    response = None
    for attempt in range(4):
        try:
            _nim_throttle()
            response = client.chat.completions.create(
                model=model,
                max_tokens=2048,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                tools=[{
                    "type": "function",
                    "function": {
                        "name": "submit_report",
                        "description": f"Submit your structured {schema.__name__} report.",
                        "parameters": tool_schema,
                    },
                }],
                tool_choice={"type": "function", "function": {"name": "submit_report"}},
            )
            break
        except Exception as e:
            status = getattr(e, "status_code", None)
            transient = status in (429, 500, 502, 503, 504) \
                or "timed out" in str(e).lower() or "connection" in str(e).lower()
            if not transient or attempt == 3:
                raise
            if status == 429:
                # Rate-limit window: honor Retry-After when given, else wait it out
                retry_after = None
                resp = getattr(e, "response", None)
                if resp is not None:
                    try:
                        retry_after = float(resp.headers.get("retry-after"))
                    except (TypeError, ValueError):
                        pass
                delay = retry_after if retry_after else 15.0 * (attempt + 1)
            else:
                delay = 2 * (2 ** attempt)
            delay += _random.uniform(0, 1.5)
            log.warning("nim.transient_error_retrying", attempt=attempt + 1,
                        status=status, delay_s=round(delay, 1))
            _time.sleep(delay)

    msg = response.choices[0].message
    if msg.tool_calls:
        return json.loads(msg.tool_calls[0].function.arguments)

    # Fallback: model returned JSON in content instead of a tool call —
    # often with stray prose or markdown fences around it (e.g. 'Let{"ticker"...')
    content = (msg.content or "").strip()
    idx = content.find("{")
    if idx != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(content[idx:])
            if isinstance(obj, dict):
                return obj
        except ValueError:
            pass

    raise RuntimeError(f"NIM model did not call submit_report. Response: {response}")


def _inline_refs(schema: dict) -> dict:
    """Recursively resolve $ref references within a JSON schema."""
    defs = schema.get("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_name = node["$ref"].split("/")[-1]
                return resolve(defs.get(ref_name, node))
            return {k: resolve(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [resolve(i) for i in node]
        return node

    return resolve(schema)


# ── DISCIPLINE CONSTANTS ──────────────────────────────────────────────────────

MIN_ANALYST_CONFIDENCE   = 0.50   # Individual analyst min confidence
MIN_TRADE_CONFIDENCE     = 0.48   # Final decision min confidence to trade
MIN_BULLISH_CONSENSUS    = 0      # Hard gate removed — researcher + PM handle consensus
MIN_BEARISH_CONSENSUS    = 0      # Hard gate removed — researcher + PM handle consensus
MAX_POSITION_SIZE_PCT    = 5.0    # Hard cap per position
MANDATORY_STOP_LOSS_PCT  = 7.0    # Always set stop-loss
MAX_RISK_LEVEL_TO_TRADE  = "MEDIUM"


ANALYST_DISCIPLINE = """
DISCIPLINE RULES — NON-NEGOTIABLE:
1. NEVER invent or fabricate data. Use ONLY the real market data provided above.
2. Set confidence BELOW 0.55 only if you have strong uncertainty. Be willing to commit to a directional view.
3. Signal NEUTRAL only when evidence genuinely points in both directions equally. Do NOT default to NEUTRAL out of caution.
4. You are analyzing stocks already pre-screened for momentum and technical strength. Your job is to CONFIRM OR DENY the setup, not to find a reason to avoid it.
5. Your reasoning must cite specific evidence from the data provided. Vague statements are unacceptable.
6. IMPORTANT: If the data shows today's volume is below average, note that intraday volume at market open is naturally lower than full-day averages — do NOT penalize a stock solely for low intraday volume.
7. Strong 3M+ price momentum IS a valid bullish signal. Do not dismiss momentum as "overextended" without concrete valuation evidence.
"""

RESEARCHER_DISCIPLINE = """
DISCIPLINE RULES — NON-NEGOTIABLE:
1. The bear case must be argued with full conviction, not as a formality.
2. Identify at least 2 concrete scenarios where the bull thesis fails completely.
3. Do not let optimism bias the debate. But equally — do not let pessimism bias it.
4. If the evidence leans directional (2+ analysts agree), suggest that direction. NEUTRAL should only result from a genuine draw where bull and bear cases are truly equal.
5. A good BUY requires: technical confirmation OR strong fundamental value AND no immediate binary risk event. You do NOT need all four analysts to agree.
6. Remember: being wrong on a HOLD costs real opportunity. Being wrong on a BUY
   costs real money. These risks are SYMMETRIC — excessive caution is also a failure.
7. Strong multi-month price momentum with improving fundamentals is a valid BUY thesis.
"""

RISK_DISCIPLINE = """
DISCIPLINE RULES — NON-NEGOTIABLE:
1. You have VETO POWER. Use it when risk is clearly unacceptable.
2. Set approved=False if ANY of the following are true:
   - Confidence from debate is below 0.50 (not just uncertain — genuinely low signal)
   - There is a binary risk event in the next 24h (earnings release, FDA decision, etc.)
   - The stock has no clear directional thesis from the debate
3. HIGH risk level alone does NOT auto-reject — factor it into position sizing instead.
   Reduce position to 1% if HIGH risk but thesis is clear. Reject only if thesis is absent.
4. ALWAYS set a stop_loss_pct. A trade with no stop-loss is not a trade — it is gambling.
   Minimum stop-loss: 5%. Maximum: 12%. Default: 7%.
5. Recommended position size: 5-7% of portfolio for normal BUY trades, 3-5% for HIGH risk. Never recommend less than 3% — tiny positions are pointless.
6. Your performance is measured by RISK-ADJUSTED returns, not trades blocked.
"""

PM_DISCIPLINE = """
DISCIPLINE RULES — NON-NEGOTIABLE:
1. If risk.approved is False → decision is HOLD. No exceptions. No overrides.
2. If confidence is below 0.50 → decision is HOLD. Do not rationalize a trade.
3. NEVER chase momentum. If the move has already happened, the trade is too late.
4. NEVER average down on a losing position via agent recommendation.
5. The best trade is often NO trade. HOLD is a valid and often correct decision.
6. Position sizing follows Risk Manager exactly. Do not size up because you feel confident.
7. Document every key risk you are accepting in key_risks_acknowledged.
"""


# ── Individual agent runners ───────────────────────────────────────────────────

def _run_technical_analyst(ticker: str, date: str, model: str, market_data: dict) -> TechnicalReport:
    data_block = json.dumps(market_data, indent=2, default=str)

    system = f"""You are a world-class technical analyst at a professional trading firm.
Your job: analyze price action, volume, and technical indicators with surgical precision.
You have been given REAL, LIVE market data. Use it. Do not fabricate numbers.

MULTI-TIMEFRAME ANALYSIS (MTF):
- Always consider daily, weekly context before acting on shorter timeframes
- Higher timeframe trend takes precedence over lower timeframe signals
- Only trade in the direction of the higher timeframe trend

WYCKOFF METHOD:
- Identify Accumulation (smart money buying quietly) vs Distribution (smart money selling)
- Look for Springs (false breakdowns below support) and Upthrusts (false breaks above resistance)
- Volume confirms price: high volume on up moves (accumulation) is bullish; high volume on down moves is bearish
- "Composite Man" — institutions move price to shake out weak hands before the real move

ICT CONCEPTS (Inner Circle Trader):
- Fair Value Gaps (FVG): 3-candle patterns where price moved so fast it left an imbalance — price tends to return to fill these gaps
- Order Blocks: the last down candle before a strong up move (institutional buying zone)
- Liquidity Sweeps: price briefly breaks a key level (stop-loss cluster) before reversing — this is the real entry signal
- Market Structure Shifts (MSS): when price breaks a prior swing low in uptrend — early warning

TURTLE TRADER RULES (adapted):
- Buy 20-day breakouts with full conviction
- ATR-based position sizing: risk no more than 1% per trade (stop = 2×ATR from entry)
- Pyramid into winning positions, never add to losers
- Always have a pre-defined exit before entering

SMART MONEY CONCEPTS:
- Track where large orders must be hidden (at round numbers, prior highs/lows)
- Stop hunts: sudden moves to obvious levels then reversal = institutional accumulation/distribution
- Premium vs Discount zones: only buy in discount (below equilibrium), sell in premium (above)

Rate signals on these dimensions: trend clarity, entry quality, risk/reward ratio (require minimum 2:1 R:R).

{ANALYST_DISCIPLINE}

Technical-specific rules:
- RSI 30-70 is NEUTRAL range. Only outside this range does it contribute to a signal.
- A MACD crossover alone is NOT a BUY signal. It is one data point.
- Volume must confirm price moves. Price without volume is noise.
- Trend direction takes precedence over oscillators in strong trends.
- Support/resistance levels must be significant (tested multiple times). Do not invent them.
- ATR(14) data is provided — use it for stop placement (2×ATR) and volatility context."""

    user = (
        f"Perform rigorous technical analysis for {ticker} as of {date}.\n\n"
        f"REAL MARKET DATA (use these exact numbers):\n{data_block}\n\n"
        "Analyze: price trend (vs MA50/MA200), RSI(14), MACD signal, "
        "volume confirmation (today vs 30d avg), and key support/resistance from the 52w range.\n"
        "Cite specific numbers from the data provided. "
        "Be skeptical. Look for reasons the setup is NOT clean before calling a signal.\n"
        "Submit your TechnicalReport."
    )
    result = _nim_structured(system, user, TechnicalReport, model)
    result["ticker"] = ticker
    report = TechnicalReport(**result)

    if report.confidence < MIN_ANALYST_CONFIDENCE:
        report.signal = Signal.NEUTRAL
    return report


def _run_sentiment_analyst(ticker: str, date: str, model: str, market_data: dict) -> SentimentReport:
    sentiment_data = {
        "short_ratio": market_data.get("short_ratio"),
        "short_percent_float": market_data.get("short_percent_float"),
        "held_by_institutions": market_data.get("held_by_institutions"),
        "analyst_recommendation": market_data.get("analyst_recommendation"),
        "analyst_target_price": market_data.get("analyst_target_price"),
        "num_analyst_opinions": market_data.get("num_analyst_opinions"),
        "beta": market_data.get("beta"),
        "current_price": market_data.get("current_price"),
    }
    data_block = json.dumps(sentiment_data, indent=2, default=str)

    system = f"""You are the Sentiment Analyst at a professional trading firm.
Your job: assess real market sentiment through institutional flow, options positioning,
short interest, and crowd behavior signals.
You have been given REAL data. Use it. Do not fabricate numbers.

INSTITUTIONAL FLOW ANALYSIS:
- Institutions hold positions for months — their ownership direction signals conviction
- Rising institutional ownership (QoQ) is bullish; declining is bearish/distribution
- "Dumb money" retail flows to a stock after institutions have already positioned
- 13F filings lag by 45 days — treat them as directional bias, not entry timing

OPTIONS FLOW ANALYSIS:
- Put/call ratio (PCR) interpretation: PCR < 0.7 = complacency (contrarian bearish); PCR > 1.3 = fear (contrarian bullish)
- Unusual options activity (UOA): large block call/put sweeps often precede moves — read the flow direction
- High implied volatility (IV) before earnings = market expects a big move; fades after (IV crush)
- Smart money uses options to hedge positions — unusual put volume = insiders protecting gains

FEAR & GREED / CROWD BEHAVIOR:
- When everyone is bullish = danger. When everyone is bearish = opportunity.
- Short squeeze potential: short interest > 20% of float + rising price + high borrow cost
- But: High short interest from dedicated short sellers (Muddy Waters, Citron) is a RED FLAG — they do real homework
- Beta is systematic risk: high beta stocks amplify market moves in both directions

{ANALYST_DISCIPLINE}

Sentiment-specific rules:
- Retail sentiment (Reddit, StockTwits) is a CONTRARIAN indicator, not a confirmation.
- High short interest can mean smart money is short. Do not automatically call it a squeeze.
- Put/call ratio below 0.7 means the market is complacent (bearish contrarian signal).
- Institutional holding % is a key signal — high institutional ownership = professional validation.
- Analyst consensus recommendations are lagging indicators; use them as context only.
- Analyst price targets reflect 12-month horizon — weight less for short-term trades.
- If analyst_recommendation is "sell" or "strong sell" → strong bearish signal, not contrarian."""

    user = (
        f"Assess market sentiment for {ticker} as of {date}.\n\n"
        f"REAL SENTIMENT DATA:\n{data_block}\n\n"
        "Evaluate: institutional ownership, short interest context, analyst consensus, "
        "and beta (systematic risk). Cite the specific numbers from the data.\n"
        "Be skeptical of any bullish signals. Weight institutional data heavily.\n"
        "Submit your SentimentReport."
    )
    result = _nim_structured(system, user, SentimentReport, model)
    result["ticker"] = ticker
    report = SentimentReport(**result)
    if report.confidence < MIN_ANALYST_CONFIDENCE:
        report.signal = Signal.NEUTRAL
    return report


def _run_news_analyst(ticker: str, date: str, model: str, market_data: dict, news_headlines: list[str]) -> NewsReport:
    news_block = "\n".join(news_headlines) if news_headlines else "No recent headlines available."
    context = {
        "sector": market_data.get("sector"),
        "industry": market_data.get("industry"),
        "beta": market_data.get("beta"),
    }

    system = f"""You are the News Analyst at a professional trading firm.
Your job: identify news events that create MATERIAL RISK or GENUINE CATALYSTS.
You are a skeptic. You assume news is noise until proven otherwise.
You have been given REAL recent headlines. Analyze them critically.

{ANALYST_DISCIPLINE}

News-specific rules:
- Upcoming earnings = HIGH RISK EVENT. Always flag catalyst_upcoming=True near earnings.
- Positive press releases from the company itself are marketing, not investment signals.
- Regulatory/legal risk is almost always underestimated by the market. Weight it heavily.
- If there is ANY pending litigation, investigation, or regulatory review → flag it.
- "No news" is not automatically bullish. Absence of bad news ≠ presence of good news.
- Macro events (Fed meetings, CPI, GDP) affect all stocks. Always consider the calendar."""

    user = (
        f"Analyze news context for {ticker} as of {date}.\n\n"
        f"Company context: {json.dumps(context)}\n\n"
        f"REAL RECENT HEADLINES:\n{news_block}\n\n"
        "Identify: any material adverse news, upcoming earnings or catalysts, "
        "regulatory or legal risks, and relevant macro events in the next 30 days.\n"
        "Default to flagging risks. A missed risk is far more costly than a missed opportunity.\n"
        "Submit your NewsReport."
    )
    result = _nim_structured(system, user, NewsReport, model)
    result["ticker"] = ticker
    report = NewsReport(**result)
    if report.confidence < MIN_ANALYST_CONFIDENCE:
        report.signal = Signal.NEUTRAL
    return report


def _run_fundamental_analyst(ticker: str, date: str, model: str, market_data: dict) -> FundamentalReport:
    fund_data = {
        "current_price": market_data.get("current_price"),
        "market_cap": market_data.get("market_cap"),
        "pe_ratio": market_data.get("pe_ratio"),
        "forward_pe": market_data.get("forward_pe"),
        "peg_ratio": market_data.get("peg_ratio"),
        "revenue_growth_yoy": market_data.get("revenue_growth_yoy"),
        "earnings_growth_yoy": market_data.get("earnings_growth_yoy"),
        "gross_margin": market_data.get("gross_margin"),
        "operating_margin": market_data.get("operating_margin"),
        "profit_margin": market_data.get("profit_margin"),
        "debt_to_equity": market_data.get("debt_to_equity"),
        "current_ratio": market_data.get("current_ratio"),
        "free_cash_flow": market_data.get("free_cash_flow"),
        "enterprise_value": market_data.get("enterprise_value"),
        "sector": market_data.get("sector"),
        "industry": market_data.get("industry"),
    }
    data_block = json.dumps(fund_data, indent=2, default=str)

    system = f"""You are the Fundamental Analyst at a professional trading firm.
Your job: determine whether a stock's price is JUSTIFIED by its business quality and financials.
You value businesses, not stock prices. You have been given REAL financial data.

CANSLIM FRAMEWORK (William O'Neil / IBD — framework behind the biggest stock winners):
C — Current Quarterly Earnings: Must be accelerating. 25%+ YoY EPS growth preferred.
A — Annual Earnings Growth: 3-5 years of consistent growth above 25% annually.
N — New Products/Services/Management: Something NEW driving the next growth leg.
S — Supply & Demand: Low float + institutional accumulation = fuel for big moves.
L — Leader or Laggard: Only buy the #1 or #2 stock in a leading sector. Avoid laggards.
I — Institutional Sponsorship: Rising institutional ownership confirms smart-money interest.
M — Market Direction: Only buy in confirmed uptrends. (Handled by regime detector.)

AQR QUALITY FACTOR ANALYSIS:
- Quality = high margins + stable earnings + low leverage + consistent ROE
- High-quality companies outperform across market cycles (academically proven alpha factor)
- Gross margin stability > 40% signals pricing power and moat
- Operating leverage: Revenue growth beating operating expense growth = efficiency

PEAD (Post-Earnings Announcement Drift):
- Stocks that beat earnings estimates by >10% continue to drift up 60+ days on average
- The market systematically underreacts to earnings surprises — this is a persistent anomaly
- Flag if recent earnings beat is large — it is a BULLISH CATALYST, not just noise
- Conversely, large misses drift down. Do not assume earnings shock is "priced in" quickly.

VALUE TRAP DETECTION:
- Declining revenue + low P/E = value trap (cheap because fundamentals deteriorating)
- High debt + falling margins + low P/E = financial distress trap, not a bargain
- Compare forward P/E to 3-year earnings CAGR. If CAGR < P/E / 2 = overvalued.

{ANALYST_DISCIPLINE}

Fundamental-specific rules:
- High P/E alone is not a sell signal IF growth justifies it (check PEG ratio — PEG < 1.0 is undervalued).
- Low P/E alone is not a buy signal IF the business is declining (value trap check).
- Revenue growth means nothing without margin analysis. Growing revenue + shrinking margins = warning.
- Debt-to-equity above 2.0 requires explicit justification (e.g., capital-light SaaS with strong FCF).
- Free cash flow is more important than reported earnings. FCF cannot be managed.
- Compare to direct sector peers, not the S&P 500 average.
- Earnings acceleration (each quarter better than last) is the most powerful signal in CANSLIM."""

    user = (
        f"Perform rigorous fundamental analysis for {ticker} as of {date}.\n\n"
        f"REAL FINANCIAL DATA:\n{data_block}\n\n"
        "Evaluate: valuation (P/E, forward P/E, PEG), revenue and margin trends, "
        "balance sheet health, and FCF generation.\n"
        "Actively look for value traps, accounting red flags, and reasons the valuation "
        "is justified OR unjustified. Cite the specific numbers.\n"
        "Submit your FundamentalReport."
    )
    result = _nim_structured(system, user, FundamentalReport, model)
    result["ticker"] = ticker
    report = FundamentalReport(**result)
    if report.confidence < MIN_ANALYST_CONFIDENCE:
        report.signal = Signal.NEUTRAL
    return report


def _run_researcher_debate(bundle: AnalystBundle, rounds: int, model: str) -> ResearcherDebate:
    system = f"""You are the Chief Investment Researcher running a formal debate at a professional trading firm.
You have received structured, typed reports from 4 specialist analysts.
Your job: conduct a rigorous adversarial debate that STRESS-TESTS the investment case.

{RESEARCHER_DISCIPLINE}

BULL CASE FRAMEWORKS (use these to build the strongest possible bull argument):
- CANSLIM: Is this a sector leader with accelerating earnings, institutional accumulation, and new catalysts?
- PEAD: Did this stock recently beat earnings by a large margin? The drift could last 60+ more days.
- Momentum Factor (AQR): 12-1 month price momentum is one of the most persistent return factors. Is momentum positive?
- Wyckoff Accumulation: Is smart money quietly building a position (rising volume on up days, low volume pullbacks)?
- ICT Order Block: Is price sitting on a known institutional buying zone (last down-candle before major rally)?

BEAR CASE FRAMEWORKS (use these to build the strongest possible bear argument):
- Value Trap Check: Is low valuation masking deteriorating fundamentals (declining revenue + margin compression)?
- Distribution Phase (Wyckoff): Is institutional supply overwhelming demand (high volume on down moves)?
- Liquidity Sweep Reversal: Did price just sweep a key high, triggering stops before reversing? Classic institutional exit.
- CANSLIM Red Flag: Is the stock a laggard in a weak sector, OR does it lack earnings acceleration?
- Momentum Reversal: 12-1 month momentum turning negative is a quantified sell signal across factor models.
- Macro Risk: Is VIX elevated, or is a Fed/CPI event within 2 weeks? Binary events kill setups.

DEBATE QUALITY RULES:
- Each round: Bull argues one specific framework. Bear rebuts with a specific counter-framework or data point.
- No vague arguments. Every claim must reference a specific data point from the analyst reports.
- The stronger side is the one with more data-backed, specific arguments — not more words.
- Risk-asymmetry: A 20% loss takes 25% gain to break even. Weight downside arguments heavier.

Consensus check (from analyst data):
- Bullish analysts: {bundle.bullish_count()} / 4
- Bearish analysts: {bundle.bearish_count()} / 4
- Average confidence: {bundle.avg_confidence:.0%}

If bullish < 3 and bearish < 3 → the evidence is mixed → suggest NEUTRAL unless the debate
produces overwhelming evidence one way. Default to caution — HOLD is always available.
"""

    analyst_summary = {
        "ticker": bundle.ticker,
        "signals": {k: v.value for k, v in bundle.analyst_signals.items()},
        "avg_confidence": bundle.avg_confidence,
        "bullish_analysts": bundle.bullish_count(),
        "bearish_analysts": bundle.bearish_count(),
        "technical": {
            "signal": bundle.technical.signal.value,
            "rsi_14": bundle.technical.rsi_14,
            "macd_crossover": bundle.technical.macd_bullish_crossover,
            "trend": bundle.technical.trend_direction,
            "key_points": bundle.technical.key_points,
        },
        "sentiment": {
            "signal": bundle.sentiment.signal.value,
            "score": bundle.sentiment.sentiment_score,
            "institutional": bundle.sentiment.institutional_flow,
            "key_points": bundle.sentiment.key_points,
        },
        "news": {
            "signal": bundle.news.signal.value,
            "catalyst_upcoming": bundle.news.catalyst_upcoming,
            "material_news": bundle.news.material_news_exists,
            "key_points": bundle.news.key_points,
        },
        "fundamental": {
            "signal": bundle.fundamental.signal.value,
            "pe": bundle.fundamental.pe_ratio,
            "forward_pe": bundle.fundamental.forward_pe,
            "revenue_growth": bundle.fundamental.revenue_growth_yoy,
            "vs_sector": bundle.fundamental.vs_sector_pe,
            "key_points": bundle.fundamental.key_points,
        },
    }

    user = (
        f"Conduct a {rounds}-round bull vs bear debate for {bundle.ticker}.\n\n"
        f"Analyst Summary:\n{json.dumps(analyst_summary, indent=2)}\n\n"
        "For each round, present the strongest bull argument, then the strongest bear counterargument. "
        "After all rounds, determine which side made the stronger case and provide a suggested signal. "
        "Submit your structured ResearcherDebate."
    )
    result = _nim_structured(system, user, ResearcherDebate, model)
    result["ticker"] = bundle.ticker
    return ResearcherDebate(**result)


def _run_risk_manager(bundle: AnalystBundle, debate: ResearcherDebate, model: str) -> RiskAssessment:
    system = f"""You are the Risk Manager at a professional trading firm.
You are the last line of defense before real money is deployed.
Your mandate: PROTECT THE PORTFOLIO. Returns are secondary. Survival is primary.

{RISK_DISCIPLINE}

KELLY CRITERION — POSITION SIZING:
- Kelly formula: f* = (p × b - q) / b where p=win_rate, b=reward/risk_ratio, q=1-p
- Platform uses HALF-KELLY to reduce volatility while preserving ~75% of the mathematical edge
- Example: 60% win rate, 2:1 R:R → Full Kelly = 20% → Half-Kelly = 10% → capped at {MAX_POSITION_SIZE_PCT}%
- High confidence (>80%) + high R:R (>3:1) = larger position (up to cap)
- Low confidence (<65%) + low R:R (<2:1) = minimum position or reject
- Never use Kelly without a hard stop — the math assumes you can survive bad streaks

ATR-BASED DYNAMIC STOP PLACEMENT:
- Default stop = 2×ATR(14) below entry price — this is the Turtle Trader stop
- ATR stop is BETTER than fixed % because it adapts to current volatility
- High volatility stock (ATR = 4%) → stop at 8% below entry (gives room)
- Low volatility stock (ATR = 0.5%) → stop at 1% below entry (tight, as expected)
- If provided ATR data: calculate exact stop = entry - (2 × atr_14)
- NEVER widen a stop to avoid being stopped out — that violates the system

PORTFOLIO-LEVEL RISK CONTROLS (VaR):
- No single position should exceed 5% of portfolio (hard cap)
- Correlated positions (e.g., two semiconductor stocks) count against SECTOR limit (25% max)
- Cash reserve: minimum 20% of portfolio must remain in cash — always
- Daily drawdown circuit breaker: if portfolio drops 5% in one day → flag for immediate review
- VIX gate: if VIX > 30, suppress all BUY signals and halve all position sizes

REGIME-ADJUSTED SIZING:
- BULL_TRENDING regime → standard sizing (up to {MAX_POSITION_SIZE_PCT}%)
- SIDEWAYS regime → reduce to 60% of normal size
- BEAR_TRENDING regime → reduce to 40% of normal size, require 80%+ confidence
- HIGH_VOLATILITY regime → reduce to 25% of normal size, require 85%+ confidence

Hard rules you must enforce right now:
- If debate.confidence < {MIN_TRADE_CONFIDENCE} → approved=False, risk_level=HIGH
- recommended_position_pct must NEVER exceed {MAX_POSITION_SIZE_PCT}%
- stop_loss_pct must ALWAYS be set (default: {MANDATORY_STOP_LOSS_PCT}% — use ATR-based if ATR data available)
- If news.catalyst_upcoming is True AND earnings are within 3 days → approved=False (binary event risk)
- If earnings are 2+ weeks away, catalyst_upcoming alone does NOT block the trade — reduce position size instead
- Minimum R:R of 2:1 required — if take_profit_pct / stop_loss_pct < 2.0 → reject or adjust

Your performance review is based entirely on how well you PREVENT LOSSES.
Every dollar lost due to a trade you approved is on you personally."""

    risk_input = {
        "ticker": bundle.ticker,
        "suggested_signal": debate.suggested_signal.value,
        "debate_confidence": debate.confidence,
        "debate_winner": debate.debate_winner,
        "key_risks": debate.key_risks,
        "key_catalysts": debate.key_catalysts,
        "analyst_agreement": {
            "bullish": bundle.bullish_count(),
            "bearish": bundle.bearish_count(),
            "avg_confidence": bundle.avg_confidence,
        },
    }

    user = (
        f"Assess portfolio risk for a potential {debate.suggested_signal.value} trade on {bundle.ticker}.\n\n"
        f"Input:\n{json.dumps(risk_input, indent=2)}\n\n"
        "Evaluate position sizing, stop-loss levels, VaR impact, correlation risk, "
        "and concentration risk. Approve or reject the trade. Submit your structured RiskAssessment."
    )
    result = _nim_structured(system, user, RiskAssessment, model)
    result["ticker"] = bundle.ticker
    assessment = RiskAssessment(**result)

    # ── Hard enforcement gates ─────────────────────────────────────────────────
    rejection_reasons = []

    if debate.confidence < MIN_TRADE_CONFIDENCE:
        rejection_reasons.append(f"debate confidence {debate.confidence:.0%} below minimum {MIN_TRADE_CONFIDENCE:.0%}")

    if debate.suggested_signal in (Signal.BUY, Signal.STRONG_BUY) and bundle.bullish_count() < MIN_BULLISH_CONSENSUS:
        rejection_reasons.append(f"only {bundle.bullish_count()}/4 analysts bullish (need {MIN_BULLISH_CONSENSUS})")

    if debate.suggested_signal in (Signal.SELL, Signal.STRONG_SELL) and bundle.bearish_count() < MIN_BEARISH_CONSENSUS:
        rejection_reasons.append(f"only {bundle.bearish_count()}/4 analysts bearish (need {MIN_BEARISH_CONSENSUS})")

    # HIGH risk alone no longer auto-vetoes — risk manager already set approved=False if needed.
    # Only hard-block if risk manager explicitly rejected AND confidence is also very low.
    if assessment.risk_level == RiskLevel.HIGH and not assessment.approved and debate.confidence < 0.45:
        rejection_reasons.append("very low confidence with HIGH risk — blocking")

    if rejection_reasons:
        assessment.approved = False
        assessment.risk_level = RiskLevel.HIGH
        assessment.rejection_reason = "; ".join(rejection_reasons)

    if assessment.recommended_position_pct and assessment.recommended_position_pct > MAX_POSITION_SIZE_PCT:
        assessment.recommended_position_pct = MAX_POSITION_SIZE_PCT
    if assessment.max_position_pct and assessment.max_position_pct > MAX_POSITION_SIZE_PCT:
        assessment.max_position_pct = MAX_POSITION_SIZE_PCT

    if assessment.stop_loss_pct is None:
        assessment.stop_loss_pct = MANDATORY_STOP_LOSS_PCT

    return assessment


def _run_portfolio_manager(
    bundle: AnalystBundle,
    debate: ResearcherDebate,
    risk: RiskAssessment,
    model: str,
) -> FinalDecision:
    system = f"""You are the Portfolio Manager at a professional trading firm.
Every decision you make is recorded, audited, and attributed to you personally.
You are accountable for every dollar won and every dollar lost.

{PM_DISCIPLINE}

POSITION PYRAMID RULES (Turtle Trader adaptation):
- Initial entry: 50% of approved position size
- First add: +25% if price moves 1×ATR in our favor (confirmation)
- Second add: +25% if price moves 2×ATR in our favor (momentum confirmed)
- NEVER add to losing positions — averaging down is capital destruction
- Each add raises the cost basis — tighten the stop to protect the full position

EXIT DISCIPLINE — THREE-TARGET SYSTEM:
- T1 (first target): Take 33% off at 1.5:1 R:R → move stop to breakeven
- T2 (main target): Take 50% off at 2.5:1 R:R → trail stop at 1×ATR
- T3 (runner): Let remaining 17% run with trailing ATR stop → captures extended moves
- Hard stop: Full exit at stop_loss_pct — no exceptions, no "let it come back"
- Time stop: If trade hasn't moved in target direction within 10 trading days → exit

CORRELATION-AWARE PORTFOLIO CONSTRUCTION:
- Do not open a new BUY in a sector that already has an open position
- Semiconductors (NVDA, AMD, INTC, AVGO) count as correlated — treat as same sector
- Mega-cap tech (AAPL, MSFT, GOOGL, META) correlate heavily in risk-off environments
- Diversification across sectors: max 25% of portfolio in any single sector at all times
- Long correlation: if two new positions have >0.7 correlation, size both down 50%

SUMMARY QUALITY STANDARD:
- Your summary must include: the setup reason, the R:R ratio, the key risk being accepted
- Example: "BUY NVDA: CANSLIM leader in AI infrastructure, breaking out above 52w high on 2.3× avg volume. R:R 2.8:1 (stop: $X, target: $Y). Key risk accepted: high IV pre-earnings in 18 days."

NON-NEGOTIABLE GATES (enforced in code after your response — do not try to circumvent):
- risk.approved=False → decision=HOLD, always, no exceptions
- debate.confidence < {MIN_TRADE_CONFIDENCE} → decision=HOLD
- position_size_pct must match risk.recommended_position_pct exactly
- stop_loss_pct must be set if decision is BUY or SELL

Remember: the market will be open tomorrow. A HOLD today is not a failure.
A reckless BUY that loses 15% is a failure that takes months to recover from.
Consistency over home runs. 1% per day compounded = 1,000% per year."""

    pm_input = {
        "ticker": bundle.ticker,
        "analyst_signals": {k: v.value for k, v in bundle.analyst_signals.items()},
        "avg_analyst_confidence": bundle.avg_confidence,
        "debate_suggestion": debate.suggested_signal.value,
        "debate_confidence": debate.confidence,
        "debate_winner": debate.debate_winner,
        "risk_approved": risk.approved,
        "risk_level": risk.risk_level.value,
        "recommended_position_pct": risk.recommended_position_pct,
        "stop_loss_pct": risk.stop_loss_pct,
        "take_profit_pct": risk.take_profit_pct,
        "risk_rejection_reason": risk.rejection_reason,
    }

    user = (
        f"Make the final trade decision for {bundle.ticker}.\n\n"
        f"Full picture:\n{json.dumps(pm_input, indent=2)}\n\n"
        "If risk.approved is False, your decision MUST be HOLD. "
        "Otherwise, weigh all inputs and make your final BUY/HOLD/SELL decision. "
        "Submit your structured FinalDecision."
    )
    result = _nim_structured(system, user, FinalDecision, model)
    result["ticker"] = bundle.ticker
    result["analysis_date"] = bundle.analysis_date
    result["analyst_signals"] = {k: v.value for k, v in bundle.analyst_signals.items()}
    result["debate_winner"] = debate.debate_winner
    result["risk_level"] = risk.risk_level.value
    result["risk_approved"] = risk.approved
    decision = FinalDecision(**result)

    # ── Final enforcement gates ────────────────────────────────────────────────
    force_hold_reasons = []

    if not risk.approved:
        force_hold_reasons.append(f"risk rejected: {risk.rejection_reason}")

    if decision.confidence < MIN_TRADE_CONFIDENCE:
        force_hold_reasons.append(f"confidence {decision.confidence:.0%} below minimum {MIN_TRADE_CONFIDENCE:.0%}")

    if force_hold_reasons:
        decision.decision = Decision.HOLD
        decision.order_side = None
        decision.position_size_pct = None
        decision.primary_reason = "HOLD enforced by risk gate: " + "; ".join(force_hold_reasons)
        decision.summary = (
            f"Trade blocked by mandatory risk controls. Reasons: {'; '.join(force_hold_reasons)}. "
            f"Original agent suggestion was {result.get('decision', 'unknown')} — "
            "overridden to protect capital. Re-evaluate when conditions improve."
        )

    if decision.decision != Decision.HOLD and risk.recommended_position_pct:
        decision.position_size_pct = risk.recommended_position_pct

    if decision.decision != Decision.HOLD and decision.stop_loss_pct is None:
        decision.stop_loss_pct = risk.stop_loss_pct or MANDATORY_STOP_LOSS_PCT

    return decision


# ── Main orchestrator ──────────────────────────────────────────────────────────

async def _emit(run_id: str, event: dict):
    await ws_manager.broadcast(f"run:{run_id}", event)


def _run_full_pipeline(run_id: str, ticker: str, date: str, debate_rounds: int, model: str, loop: asyncio.AbstractEventLoop, senior_model: str | None = None) -> dict:
    """
    Synchronous full pipeline. Runs in thread executor.
    Receives the main event loop so sync_emit works correctly.

    analyst_model  (model)        → Technical, Sentiment, News, Fundamental  (fast/cheap)
    senior_model   (senior_model) → Researcher, Risk Manager, PM              (smart/expensive)
    If senior_model is None, falls back to model.
    """
    _senior = senior_model or model

    def sync_emit(event):
        """Fire-and-forget WS emit from a thread."""
        try:
            asyncio.run_coroutine_threadsafe(_emit(run_id, event), loop)
        except Exception:
            pass

    # Fetch real market data ONCE and share across analysts
    log.info("structured_agent.fetching_data", ticker=ticker)
    sync_emit({"type": "status_update", "message": f"Fetching real market data for {ticker}..."})
    market_data = _fetch_market_data(ticker)
    market_data = _inject_live_price(market_data, ticker)
    news_headlines = _fetch_news(ticker)

    if market_data.get("error"):
        log.warning("market_data.unavailable", ticker=ticker, error=market_data["error"])

    # ── Analyst phase: all 4 run in parallel (they are independent) ──────────
    sync_emit({"type": "agent_start", "agent": "Technical Analyst", "role": "analyst"})
    sync_emit({"type": "agent_start", "agent": "Sentiment Analyst", "role": "analyst"})
    sync_emit({"type": "agent_start", "agent": "News Analyst", "role": "analyst"})
    sync_emit({"type": "agent_start", "agent": "Fundamental Analyst", "role": "analyst"})

    with ThreadPoolExecutor(max_workers=4) as pool:
        f_technical   = pool.submit(_run_technical_analyst,   ticker, date, model, market_data)
        f_sentiment   = pool.submit(_run_sentiment_analyst,   ticker, date, model, market_data)
        f_news        = pool.submit(_run_news_analyst,        ticker, date, model, market_data, news_headlines)
        f_fundamental = pool.submit(_run_fundamental_analyst, ticker, date, model, market_data)
        technical   = f_technical.result()
        sentiment   = f_sentiment.result()
        news        = f_news.result()
        fundamental = f_fundamental.result()

    sync_emit({"type": "debate_event", "agent": "Technical Analyst", "role": "analyst",
               "content": technical.reasoning, "signal": technical.signal.value,
               "confidence": technical.confidence})
    sync_emit({"type": "debate_event", "agent": "Sentiment Analyst", "role": "analyst",
               "content": sentiment.reasoning, "signal": sentiment.signal.value,
               "confidence": sentiment.confidence})
    sync_emit({"type": "debate_event", "agent": "News Analyst", "role": "analyst",
               "content": news.reasoning, "signal": news.signal.value,
               "confidence": news.confidence})
    sync_emit({"type": "debate_event", "agent": "Fundamental Analyst", "role": "analyst",
               "content": fundamental.reasoning, "signal": fundamental.signal.value,
               "confidence": fundamental.confidence})

    bundle = AnalystBundle(
        ticker=ticker,
        analysis_date=date,
        technical=technical,
        sentiment=sentiment,
        news=news,
        fundamental=fundamental,
    )

    sync_emit({"type": "agent_start", "agent": "Researcher Team", "role": "researcher"})
    debate = _run_researcher_debate(bundle, debate_rounds, _senior)
    sync_emit({"type": "debate_event", "agent": "Researcher Team", "role": "researcher",
               "content": f"Bull: {debate.bull_final_thesis}\n\nBear: {debate.bear_final_thesis}",
               "signal": debate.suggested_signal.value, "confidence": debate.confidence,
               "debate_winner": debate.debate_winner})

    sync_emit({"type": "agent_start", "agent": "Risk Manager", "role": "risk"})
    risk = _run_risk_manager(bundle, debate, _senior)
    sync_emit({"type": "debate_event", "agent": "Risk Manager", "role": "risk",
               "content": risk.reasoning, "risk_level": risk.risk_level.value,
               "approved": risk.approved, "position_pct": risk.recommended_position_pct})

    sync_emit({"type": "agent_start", "agent": "Portfolio Manager", "role": "pm"})
    final = _run_portfolio_manager(bundle, debate, risk, _senior)
    sync_emit({"type": "debate_event", "agent": "Portfolio Manager", "role": "pm",
               "content": final.summary, "decision": final.decision.value,
               "confidence": final.confidence})

    debate_log = [
        {"agent": "Technical Analyst", "role": "analyst", "content": technical.reasoning,
         "signal": technical.signal.value, "confidence": technical.confidence,
         "data": technical.model_dump(exclude={"reasoning", "ticker"})},
        {"agent": "Sentiment Analyst", "role": "analyst", "content": sentiment.reasoning,
         "signal": sentiment.signal.value, "confidence": sentiment.confidence,
         "data": sentiment.model_dump(exclude={"reasoning", "ticker"})},
        {"agent": "News Analyst", "role": "analyst", "content": news.reasoning,
         "signal": news.signal.value, "confidence": news.confidence,
         "data": news.model_dump(exclude={"reasoning", "ticker"})},
        {"agent": "Fundamental Analyst", "role": "analyst", "content": fundamental.reasoning,
         "signal": fundamental.signal.value, "confidence": fundamental.confidence,
         "data": fundamental.model_dump(exclude={"reasoning", "ticker"})},
        {"agent": "Researcher Team", "role": "researcher",
         "content": f"Bull: {debate.bull_final_thesis}\n\nBear: {debate.bear_final_thesis}",
         "signal": debate.suggested_signal.value, "confidence": debate.confidence,
         "data": debate.model_dump(exclude={"ticker"})},
        {"agent": "Risk Manager", "role": "risk", "content": risk.reasoning,
         "risk_level": risk.risk_level.value, "approved": risk.approved,
         "data": risk.model_dump(exclude={"reasoning", "ticker"})},
        {"agent": "Portfolio Manager", "role": "pm", "content": final.summary,
         "decision": final.decision.value, "confidence": final.confidence,
         "data": final.model_dump(exclude={"summary", "ticker", "analysis_date"})},
    ]

    return {
        "decision": final.decision.value,
        "confidence": final.confidence,
        "summary": final.summary,
        "debate_log": debate_log,
        "reasoning_json": {
            "market_data": market_data,
            "technical": technical.model_dump(),
            "sentiment": sentiment.model_dump(),
            "news": news.model_dump(),
            "fundamental": fundamental.model_dump(),
            "debate": debate.model_dump(),
            "risk": risk.model_dump(),
            "final": final.model_dump(),
        },
    }


async def _close_long_if_held(run_id: str, ticker: str, result: dict,
                              broker, user_id: int | None, confidence: float):
    """
    SELL decision with long_only disabled: liquidate an existing long position.
    Never opens a short — if we don't hold the ticker, do nothing.
    """
    import uuid
    from app.db.models.trade import Trade

    try:
        existing = broker.get_position(ticker)
        qty = float(existing.get("qty", 0)) if existing else 0
        if qty <= 0:
            log.info("broker.sell_no_position", run_id=run_id, ticker=ticker,
                     reason="SELL signal but no long position held — no naked shorts")
            await _emit(run_id, {
                "type": "order_skipped",
                "reason": "no_position_to_sell",
                "message": f"SELL signal on {ticker}, but you hold no shares. Shorting is disabled.",
            })
            return

        order = broker.submit_order(ticker, "sell", qty)

        async with AsyncSessionLocal() as db:
            trade = Trade(
                id=str(uuid.uuid4()),
                user_id=user_id,
                agent_run_id=run_id,
                alpaca_order_id=order.get("id"),
                ticker=ticker,
                side="sell",
                qty=qty,
                order_type="market",
                status="submitted",
                reasoning_json={
                    "decision": "SELL",
                    "confidence": confidence,
                    "action": "close_long",
                    "alpaca_order": order,
                    "agent_summary": result.get("summary"),
                },
            )
            db.add(trade)
            await db.commit()

        log.info("broker.position_closed_by_signal", run_id=run_id, ticker=ticker, qty=qty)
        await _emit(run_id, {
            "type": "order_placed",
            "ticker": ticker,
            "side": "sell",
            "qty": qty,
            "order_id": order.get("id"),
            "status": order.get("status"),
        })

        from app.api.v1.notifications import save_notification
        await save_notification(
            type="trade_placed",
            title=f"Trade placed — SELL {ticker}",
            body=f"Agent SELL signal closed your {qty:g}-share {ticker} position. "
                 f"Order ID: {order.get('id', 'N/A')}",
            ticker=ticker,
            user_id=user_id,
        )
    except Exception as e:
        log.error("broker.sell_close_failed", run_id=run_id, ticker=ticker, error=str(e))
        await _emit(run_id, {"type": "order_failed", "error": str(e)})


async def _place_order_if_approved(run_id: str, ticker: str, result: dict,
                                   user_id: int | None = None):
    """
    After pipeline completes, place a real Alpaca paper order if approved.
    Rules:
    - HOLD or risk_rejected → skip
    - SELL decisions → skip (no short selling — long-only strategy)
    - Already hold a long position in this ticker → skip (no doubling up)
    - Position size: minimum 5% of equity for confident trades
    - Quantity: always whole shares (no fractions)

    Orders go to the *user's* connected Alpaca paper account. Legacy runs
    without a user fall back to the env-configured account.
    """
    import uuid
    from app.db.models.trade import Trade
    from app.broker.credentials import get_client_for_user
    from app.broker.alpaca_client import default_client

    if user_id is not None:
        broker = await get_client_for_user(user_id)
        if broker is None:
            log.info("broker.no_connection", run_id=run_id, user_id=user_id,
                     reason="User has not connected an Alpaca account — analysis only")
            await _emit(run_id, {
                "type": "order_skipped",
                "reason": "broker_not_connected",
                "message": "Connect your Alpaca paper account in Settings to auto-execute trades.",
            })
            return
    else:
        broker = default_client()
        if not broker.configured:
            log.info("broker.no_order", run_id=run_id, reason="no broker configured")
            return

    from app.db.models.user_settings import get_user_setting

    final = result["reasoning_json"].get("final", {})
    decision = final.get("decision", "HOLD")
    risk_approved = final.get("risk_approved", False)
    position_pct = final.get("position_size_pct")
    confidence = final.get("confidence", 0)

    if decision == "HOLD" or not risk_approved:
        log.info("broker.no_order", run_id=run_id, reason=f"decision={decision} approved={risk_approved}")
        return

    # Confidence gate — user-configurable floor for auto-execution
    min_confidence = float(await get_user_setting(user_id, "min_confidence_to_trade", 0.60))
    if confidence < min_confidence:
        log.info("broker.below_min_confidence", run_id=run_id, ticker=ticker,
                 confidence=confidence, required=min_confidence)
        await _emit(run_id, {
            "type": "order_skipped",
            "reason": "below_min_confidence",
            "message": f"Confidence {confidence:.0%} is below your {min_confidence:.0%} auto-trade floor.",
        })
        return

    if decision == "SELL":
        long_only = bool(await get_user_setting(user_id, "long_only", True))
        if long_only:
            log.info("broker.skipping_short", run_id=run_id, ticker=ticker,
                     reason="Long-only strategy — SELL signals skipped")
            return
        # long_only off: SELL closes an existing long position — never a naked short
        await _close_long_if_held(run_id, ticker, result, broker, user_id, confidence)
        return

    if decision != "BUY":
        return

    try:
        # Check ticker-level circuit breakers (earnings blackout etc.)
        try:
            from app.workers.circuit_breakers import check_ticker_blocked
            ticker_blocked, ticker_block_reason = await check_ticker_blocked(ticker, user_id=user_id)
            if ticker_blocked:
                log.warning("broker.ticker_blocked", run_id=run_id, ticker=ticker,
                            reason=ticker_block_reason)
                return
        except Exception as cb_err:
            log.warning("broker.circuit_breaker_check_failed",
                        ticker=ticker, error=str(cb_err))

        # Don't stack positions — skip if we already hold this ticker
        existing = broker.get_position(ticker)
        if existing and float(existing.get("qty", 0)) > 0:
            log.info("broker.already_positioned", run_id=run_id, ticker=ticker,
                     qty=existing.get("qty"))
            return

        market_data = result["reasoning_json"].get("market_data", {})
        current_price = market_data.get("current_price")
        if not current_price:
            log.warning("broker.no_price", ticker=ticker)
            return

        # Load position sizing and stop parameters — user override first, then platform
        from app.db.models.user_settings import get_user_setting as _get_setting
        db_pos_size_pct = await _get_setting(user_id, "position_size_pct", 5.0)
        db_pos_size_high_conf = await _get_setting(user_id, "position_size_high_conf", 7.0)
        db_stop_loss_pct = await _get_setting(user_id, "stop_loss_pct", 7.0)
        db_take_profit_pct = await _get_setting(user_id, "take_profit_pct", 15.0)

        # Boost position size for high-confidence trades (>= 0.70)
        min_pct = float(db_pos_size_high_conf) if confidence >= 0.70 else float(db_pos_size_pct)
        position_pct = max(position_pct or min_pct, min_pct)

        stop_loss_pct = final.get("stop_loss_pct") or float(db_stop_loss_pct)
        take_profit_pct = final.get("take_profit_pct") or float(db_take_profit_pct)

        # Calculate qty and force whole shares only
        import math
        account = broker.get_account()
        equity = float(account.get("equity", 100_000))
        dollar_amount = equity * (position_pct / 100.0)
        qty = max(1, math.floor(dollar_amount / current_price))  # whole shares, minimum 1

        side = "buy"
        # Use bracket order so Alpaca manages stop-loss and take-profit natively
        order = broker.submit_bracket_order(
            ticker, qty, stop_loss_pct, take_profit_pct, current_price
        )

        async with AsyncSessionLocal() as db:
            trade = Trade(
                id=str(uuid.uuid4()),
                user_id=user_id,
                agent_run_id=run_id,
                alpaca_order_id=order.get("id"),
                ticker=ticker,
                side=side,
                qty=qty,
                order_type="market",
                status="submitted",  # normalize — sync worker will update from Alpaca
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                reasoning_json={
                    "decision": decision,
                    "confidence": confidence,
                    "position_pct": position_pct,
                    "current_price": current_price,
                    "stop_loss_pct": stop_loss_pct,
                    "take_profit_pct": take_profit_pct,
                    "alpaca_order": order,
                    "agent_summary": result.get("summary"),
                },
            )
            db.add(trade)
            await db.commit()

        log.info("broker.order_placed", run_id=run_id, ticker=ticker,
                 side=side, qty=qty, order_id=order.get("id"))

        await _emit(run_id, {
            "type": "order_placed",
            "ticker": ticker,
            "side": side,
            "qty": qty,
            "order_id": order.get("id"),
            "status": order.get("status"),
        })

        # Save notification for trade placement
        try:
            from app.api.v1.notifications import save_notification
            from app.api.v1.activity import log_activity
            action_label = "BUY" if side == "buy" else "SELL"
            await save_notification(
                type="trade_placed",
                title=f"Trade placed — {action_label} {ticker}",
                body=(
                    f"Agent approved {action_label} {qty} shares of {ticker} "
                    f"at ~${current_price:,.2f}. Order ID: {order.get('id', 'N/A')}"
                ),
                ticker=ticker,
                user_id=user_id,
            )
            await log_activity(
                feature="agent_hub",
                action="trade_placed",
                ticker=ticker,
                details={
                    "side": side,
                    "qty": qty,
                    "price": current_price,
                    "order_id": order.get("id"),
                    "run_id": run_id,
                },
                result=action_label,
                user_id=user_id,
            )
        except Exception as notif_err:
            log.warning("broker.notification_failed", error=str(notif_err))

    except Exception as e:
        log.error("broker.order_failed", run_id=run_id, ticker=ticker, error=str(e))
        await _emit(run_id, {"type": "order_failed", "error": str(e)})


async def run_structured_agent_analysis(
    run_id: str,
    ticker: str,
    analysis_date: str,
    debate_rounds: int,
    model: str,
    senior_model: str | None = None,
    user_id: int | None = None,
):
    """Async entry point. Updates DB and broadcasts WS events throughout."""
    log.info("structured_agent.run.start", run_id=run_id, ticker=ticker, user_id=user_id)

    async with AsyncSessionLocal() as db:
        run = await db.get(AgentRun, run_id)
        run.status = "running"
        await db.commit()

    await _emit(run_id, {"type": "status", "status": "running", "ticker": ticker})

    try:
        # Capture the running event loop so thread can emit WS events correctly
        loop = asyncio.get_running_loop()

        result = await loop.run_in_executor(
            None, _run_full_pipeline, run_id, ticker, analysis_date, debate_rounds, model, loop, senior_model
        )

        async with AsyncSessionLocal() as db:
            run = await db.get(AgentRun, run_id)
            run.status = "completed"
            run.decision = result["decision"]
            run.confidence = result["confidence"]
            run.summary = result["summary"]
            run.debate_log = result["debate_log"]
            run.reasoning_json = result["reasoning_json"]
            run.completed_at = datetime.now(UTC)
            await db.commit()

        await _emit(run_id, {
            "type": "completed",
            "decision": result["decision"],
            "confidence": result["confidence"],
            "summary": result["summary"],
            "debate_log": result["debate_log"],
        })

        # Place paper order if agents approved a trade
        await _place_order_if_approved(run_id, ticker, result, user_id=user_id)

    except Exception as exc:
        import traceback
        log.error("structured_agent.run.error", run_id=run_id, error=str(exc),
                  traceback=traceback.format_exc())

        async with AsyncSessionLocal() as db:
            run = await db.get(AgentRun, run_id)
            run.status = "failed"
            # Message only — tracebacks (file paths, internals) stay in server logs
            run.error = str(exc)
            run.completed_at = datetime.now(UTC)
            await db.commit()

        await _emit(run_id, {"type": "error", "error": str(exc)})
