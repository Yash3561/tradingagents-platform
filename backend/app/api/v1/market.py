from fastapi import APIRouter, HTTPException
import httpx
from datetime import datetime
from datetime import timezone as _tz

UTC = _tz.utc

from app.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/quote/{ticker}")
async def get_quote(ticker: str):
    """Latest quote from Alpaca data API."""
    headers = {
        "APCA-API-KEY-ID": settings.alpaca_api_key,
        "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{settings.alpaca_data_url}/v2/stocks/{ticker.upper()}/quotes/latest",
                headers=headers,
                timeout=5.0,
            )
        if r.status_code == 200:
            return r.json()
        raise HTTPException(r.status_code, r.text)
    except httpx.TimeoutException:
        raise HTTPException(504, "Data feed timeout")


@router.get("/ohlcv/{ticker}")
async def get_ohlcv(ticker: str, period: str = "3mo", interval: str = "1d"):
    """
    Fetch OHLCV bars from yfinance for candlestick charts.
    period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y
    interval: 1m, 5m, 15m, 30m, 1h, 1d, 1wk
    Returns list of {time, open, high, low, close, volume}
    time is a Unix timestamp (seconds) — required by lightweight-charts
    """
    import asyncio
    import yfinance as yf

    def _fetch():
        t = yf.Ticker(ticker.upper())
        hist = t.history(period=period, interval=interval)
        if hist.empty:
            return []

        bars = []
        for idx, row in hist.iterrows():
            # lightweight-charts needs Unix timestamp in seconds
            if hasattr(idx, 'timestamp'):
                ts = int(idx.timestamp())
            else:
                import datetime
                ts = int(datetime.datetime.combine(idx, datetime.time()).timestamp())

            bars.append({
                "time": ts,
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": int(row["Volume"]),
            })
        return bars

    loop = asyncio.get_running_loop()
    try:
        bars = await loop.run_in_executor(None, _fetch)
        return {"ticker": ticker.upper(), "period": period, "interval": interval, "bars": bars}
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch OHLCV: {e}")


@router.get("/quote/{ticker}/live")
async def get_live_quote(ticker: str):
    """
    Get live price from Redis cache (set by price_feed worker).
    Falls back to yfinance last close if Redis miss.
    """
    import json
    try:
        import redis as redis_sync
        from app.config import get_settings as _gs
        s = _gs()
        r = redis_sync.from_url(s.redis_url)
        raw = r.get(f"price:{ticker.upper()}")
        if raw:
            data = json.loads(raw)
            return {"ticker": ticker.upper(), "price": data.get("price"), "source": "live"}
    except Exception:
        pass

    # Fallback to yfinance
    import yfinance as yf
    import asyncio
    def _fetch():
        t = yf.Ticker(ticker.upper())
        hist = t.history(period="1d", interval="1m")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        hist = t.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        return None

    loop = asyncio.get_running_loop()
    price = await loop.run_in_executor(None, _fetch)
    if price is None:
        raise HTTPException(404, f"No price data for {ticker}")
    return {"ticker": ticker.upper(), "price": round(price, 4), "source": "yfinance"}


@router.get("/search")
async def search_ticker(q: str):
    """Search for ticker symbols. Returns matches from a curated list + yfinance validation."""
    q = q.upper().strip()
    if not q or len(q) > 10:
        return []

    # Comprehensive ticker database — US large caps, global ADRs, ETFs, commodities, crypto proxies
    TICKERS = [
        # US Mega-cap Tech
        {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology"},
        {"symbol": "MSFT", "name": "Microsoft Corp.", "sector": "Technology"},
        {"symbol": "GOOGL", "name": "Alphabet Inc. (Class A)", "sector": "Technology"},
        {"symbol": "GOOG", "name": "Alphabet Inc. (Class C)", "sector": "Technology"},
        {"symbol": "AMZN", "name": "Amazon.com Inc.", "sector": "Consumer Discretionary"},
        {"symbol": "NVDA", "name": "NVIDIA Corp.", "sector": "Technology"},
        {"symbol": "META", "name": "Meta Platforms Inc.", "sector": "Communication Services"},
        {"symbol": "TSLA", "name": "Tesla Inc.", "sector": "Consumer Discretionary"},
        {"symbol": "AMD", "name": "Advanced Micro Devices Inc.", "sector": "Technology"},
        {"symbol": "AVGO", "name": "Broadcom Inc.", "sector": "Technology"},
        {"symbol": "ORCL", "name": "Oracle Corp.", "sector": "Technology"},
        {"symbol": "NFLX", "name": "Netflix Inc.", "sector": "Communication Services"},
        {"symbol": "ADBE", "name": "Adobe Inc.", "sector": "Technology"},
        {"symbol": "CRM", "name": "Salesforce Inc.", "sector": "Technology"},
        {"symbol": "INTC", "name": "Intel Corp.", "sector": "Technology"},
        {"symbol": "QCOM", "name": "Qualcomm Inc.", "sector": "Technology"},
        {"symbol": "TXN", "name": "Texas Instruments Inc.", "sector": "Technology"},
        {"symbol": "SMCI", "name": "Super Micro Computer Inc.", "sector": "Technology"},
        {"symbol": "ARM", "name": "Arm Holdings plc", "sector": "Technology"},
        {"symbol": "MU", "name": "Micron Technology Inc.", "sector": "Technology"},
        {"symbol": "AMAT", "name": "Applied Materials Inc.", "sector": "Technology"},
        {"symbol": "LRCX", "name": "Lam Research Corp.", "sector": "Technology"},
        {"symbol": "KLAC", "name": "KLA Corp.", "sector": "Technology"},
        {"symbol": "MRVL", "name": "Marvell Technology Inc.", "sector": "Technology"},
        {"symbol": "PANW", "name": "Palo Alto Networks Inc.", "sector": "Technology"},
        {"symbol": "CRWD", "name": "CrowdStrike Holdings Inc.", "sector": "Technology"},
        {"symbol": "ZS", "name": "Zscaler Inc.", "sector": "Technology"},
        {"symbol": "OKTA", "name": "Okta Inc.", "sector": "Technology"},
        {"symbol": "DDOG", "name": "Datadog Inc.", "sector": "Technology"},
        {"symbol": "NET", "name": "Cloudflare Inc.", "sector": "Technology"},
        {"symbol": "SNOW", "name": "Snowflake Inc.", "sector": "Technology"},
        {"symbol": "PLTR", "name": "Palantir Technologies Inc.", "sector": "Technology"},
        {"symbol": "AI", "name": "C3.ai Inc.", "sector": "Technology"},
        {"symbol": "UBER", "name": "Uber Technologies Inc.", "sector": "Technology"},
        {"symbol": "LYFT", "name": "Lyft Inc.", "sector": "Technology"},
        {"symbol": "SHOP", "name": "Shopify Inc.", "sector": "Consumer Discretionary"},
        {"symbol": "MELI", "name": "MercadoLibre Inc.", "sector": "Consumer Discretionary"},
        {"symbol": "SE", "name": "Sea Limited", "sector": "Consumer Discretionary"},
        # Financials
        {"symbol": "COIN", "name": "Coinbase Global Inc.", "sector": "Financials"},
        {"symbol": "SQ", "name": "Block Inc.", "sector": "Financials"},
        {"symbol": "PYPL", "name": "PayPal Holdings Inc.", "sector": "Financials"},
        {"symbol": "JPM", "name": "JPMorgan Chase & Co.", "sector": "Financials"},
        {"symbol": "GS", "name": "Goldman Sachs Group Inc.", "sector": "Financials"},
        {"symbol": "BAC", "name": "Bank of America Corp.", "sector": "Financials"},
        {"symbol": "WFC", "name": "Wells Fargo & Co.", "sector": "Financials"},
        {"symbol": "MS", "name": "Morgan Stanley", "sector": "Financials"},
        {"symbol": "BLK", "name": "BlackRock Inc.", "sector": "Financials"},
        {"symbol": "V", "name": "Visa Inc.", "sector": "Financials"},
        {"symbol": "MA", "name": "Mastercard Inc.", "sector": "Financials"},
        {"symbol": "AXP", "name": "American Express Co.", "sector": "Financials"},
        {"symbol": "SCHW", "name": "Charles Schwab Corp.", "sector": "Financials"},
        {"symbol": "C", "name": "Citigroup Inc.", "sector": "Financials"},
        {"symbol": "USB", "name": "U.S. Bancorp", "sector": "Financials"},
        # Healthcare
        {"symbol": "UNH", "name": "UnitedHealth Group Inc.", "sector": "Healthcare"},
        {"symbol": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare"},
        {"symbol": "LLY", "name": "Eli Lilly and Co.", "sector": "Healthcare"},
        {"symbol": "ABBV", "name": "AbbVie Inc.", "sector": "Healthcare"},
        {"symbol": "MRK", "name": "Merck & Co. Inc.", "sector": "Healthcare"},
        {"symbol": "PFE", "name": "Pfizer Inc.", "sector": "Healthcare"},
        {"symbol": "AMGN", "name": "Amgen Inc.", "sector": "Healthcare"},
        {"symbol": "GILD", "name": "Gilead Sciences Inc.", "sector": "Healthcare"},
        {"symbol": "ISRG", "name": "Intuitive Surgical Inc.", "sector": "Healthcare"},
        {"symbol": "MRNA", "name": "Moderna Inc.", "sector": "Healthcare"},
        {"symbol": "REGN", "name": "Regeneron Pharmaceuticals", "sector": "Healthcare"},
        {"symbol": "VRTX", "name": "Vertex Pharmaceuticals", "sector": "Healthcare"},
        # Consumer
        {"symbol": "AMZN", "name": "Amazon.com Inc.", "sector": "Consumer Discretionary"},
        {"symbol": "HD", "name": "Home Depot Inc.", "sector": "Consumer Discretionary"},
        {"symbol": "MCD", "name": "McDonald's Corp.", "sector": "Consumer Discretionary"},
        {"symbol": "NKE", "name": "Nike Inc.", "sector": "Consumer Discretionary"},
        {"symbol": "SBUX", "name": "Starbucks Corp.", "sector": "Consumer Discretionary"},
        {"symbol": "TGT", "name": "Target Corp.", "sector": "Consumer Discretionary"},
        {"symbol": "WMT", "name": "Walmart Inc.", "sector": "Consumer Staples"},
        {"symbol": "COST", "name": "Costco Wholesale Corp.", "sector": "Consumer Staples"},
        {"symbol": "PG", "name": "Procter & Gamble Co.", "sector": "Consumer Staples"},
        {"symbol": "KO", "name": "Coca-Cola Co.", "sector": "Consumer Staples"},
        {"symbol": "PEP", "name": "PepsiCo Inc.", "sector": "Consumer Staples"},
        # Energy
        {"symbol": "XOM", "name": "Exxon Mobil Corp.", "sector": "Energy"},
        {"symbol": "CVX", "name": "Chevron Corp.", "sector": "Energy"},
        {"symbol": "COP", "name": "ConocoPhillips", "sector": "Energy"},
        {"symbol": "SLB", "name": "SLB (Schlumberger)", "sector": "Energy"},
        {"symbol": "OXY", "name": "Occidental Petroleum Corp.", "sector": "Energy"},
        # Industrials & Other
        {"symbol": "CAT", "name": "Caterpillar Inc.", "sector": "Industrials"},
        {"symbol": "DE", "name": "Deere & Co.", "sector": "Industrials"},
        {"symbol": "HON", "name": "Honeywell International", "sector": "Industrials"},
        {"symbol": "UPS", "name": "United Parcel Service Inc.", "sector": "Industrials"},
        {"symbol": "BA", "name": "Boeing Co.", "sector": "Industrials"},
        {"symbol": "RTX", "name": "RTX Corp.", "sector": "Industrials"},
        {"symbol": "LMT", "name": "Lockheed Martin Corp.", "sector": "Industrials"},
        {"symbol": "GE", "name": "GE Aerospace", "sector": "Industrials"},
        {"symbol": "BRK-B", "name": "Berkshire Hathaway (Class B)", "sector": "Financials"},
        # Global ADRs
        {"symbol": "ASML", "name": "ASML Holding N.V. (Netherlands)", "sector": "Technology"},
        {"symbol": "TSM", "name": "Taiwan Semiconductor Mfg. (Taiwan)", "sector": "Technology"},
        {"symbol": "BABA", "name": "Alibaba Group (China)", "sector": "Consumer Discretionary"},
        {"symbol": "JD", "name": "JD.com Inc. (China)", "sector": "Consumer Discretionary"},
        {"symbol": "PDD", "name": "PDD Holdings (China)", "sector": "Consumer Discretionary"},
        {"symbol": "BIDU", "name": "Baidu Inc. (China)", "sector": "Technology"},
        {"symbol": "NVO", "name": "Novo Nordisk (Denmark)", "sector": "Healthcare"},
        {"symbol": "SAP", "name": "SAP SE (Germany)", "sector": "Technology"},
        {"symbol": "TM", "name": "Toyota Motor Corp. (Japan)", "sector": "Consumer Discretionary"},
        {"symbol": "SONY", "name": "Sony Group Corp. (Japan)", "sector": "Consumer Discretionary"},
        {"symbol": "HMC", "name": "Honda Motor Co. (Japan)", "sector": "Consumer Discretionary"},
        {"symbol": "INFY", "name": "Infosys Ltd. (India)", "sector": "Technology"},
        {"symbol": "WIT", "name": "Wipro Ltd. (India)", "sector": "Technology"},
        {"symbol": "RY", "name": "Royal Bank of Canada", "sector": "Financials"},
        {"symbol": "TD", "name": "Toronto-Dominion Bank (Canada)", "sector": "Financials"},
        {"symbol": "HSBC", "name": "HSBC Holdings (UK)", "sector": "Financials"},
        {"symbol": "BP", "name": "BP plc (UK)", "sector": "Energy"},
        {"symbol": "SHEL", "name": "Shell plc (UK)", "sector": "Energy"},
        {"symbol": "RIO", "name": "Rio Tinto Group (Australia)", "sector": "Materials"},
        {"symbol": "BHP", "name": "BHP Group Ltd. (Australia)", "sector": "Materials"},
        # ETFs — Broad Market
        {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "sector": "ETF"},
        {"symbol": "QQQ", "name": "Invesco QQQ Trust (NASDAQ-100)", "sector": "ETF"},
        {"symbol": "IWM", "name": "iShares Russell 2000 ETF", "sector": "ETF"},
        {"symbol": "DIA", "name": "SPDR Dow Jones Industrial ETF", "sector": "ETF"},
        {"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "sector": "ETF"},
        {"symbol": "VTI", "name": "Vanguard Total Stock Market ETF", "sector": "ETF"},
        {"symbol": "VEA", "name": "Vanguard Developed Markets ETF", "sector": "ETF"},
        {"symbol": "VWO", "name": "Vanguard Emerging Markets ETF", "sector": "ETF"},
        {"symbol": "EFA", "name": "iShares MSCI EAFE ETF (International)", "sector": "ETF"},
        {"symbol": "EEM", "name": "iShares MSCI Emerging Markets ETF", "sector": "ETF"},
        # ETFs — Sector
        {"symbol": "XLK", "name": "SPDR Technology Select ETF", "sector": "ETF"},
        {"symbol": "XLF", "name": "SPDR Financial Select ETF", "sector": "ETF"},
        {"symbol": "XLE", "name": "SPDR Energy Select ETF", "sector": "ETF"},
        {"symbol": "XLV", "name": "SPDR Health Care Select ETF", "sector": "ETF"},
        {"symbol": "XLI", "name": "SPDR Industrials Select ETF", "sector": "ETF"},
        {"symbol": "XLP", "name": "SPDR Consumer Staples ETF", "sector": "ETF"},
        {"symbol": "XLY", "name": "SPDR Consumer Discretionary ETF", "sector": "ETF"},
        {"symbol": "XLU", "name": "SPDR Utilities Select ETF", "sector": "ETF"},
        {"symbol": "ARKK", "name": "ARK Innovation ETF", "sector": "ETF"},
        {"symbol": "ARKQ", "name": "ARK Autonomous Tech & Robotics ETF", "sector": "ETF"},
        # ETFs — Fixed Income & Commodities
        {"symbol": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "sector": "ETF"},
        {"symbol": "AGG", "name": "iShares Core U.S. Aggregate Bond ETF", "sector": "ETF"},
        {"symbol": "GLD", "name": "SPDR Gold Shares ETF", "sector": "ETF"},
        {"symbol": "SLV", "name": "iShares Silver Trust ETF", "sector": "ETF"},
        {"symbol": "USO", "name": "United States Oil Fund ETF", "sector": "ETF"},
        {"symbol": "UNG", "name": "United States Natural Gas Fund", "sector": "ETF"},
        # Crypto proxies (trade on stock exchanges)
        {"symbol": "IBIT", "name": "iShares Bitcoin Trust ETF", "sector": "Crypto"},
        {"symbol": "FBTC", "name": "Fidelity Wise Origin Bitcoin ETF", "sector": "Crypto"},
        {"symbol": "MSTR", "name": "MicroStrategy Inc. (Bitcoin proxy)", "sector": "Technology"},
        {"symbol": "RIOT", "name": "Riot Platforms (Bitcoin mining)", "sector": "Technology"},
        {"symbol": "MARA", "name": "Marathon Digital Holdings (BTC mining)", "sector": "Technology"},
        # Indices (yfinance supports these)
        {"symbol": "^GSPC", "name": "S&P 500 Index", "sector": "Index"},
        {"symbol": "^IXIC", "name": "NASDAQ Composite Index", "sector": "Index"},
        {"symbol": "^DJI", "name": "Dow Jones Industrial Average", "sector": "Index"},
        {"symbol": "^RUT", "name": "Russell 2000 Index", "sector": "Index"},
        {"symbol": "^VIX", "name": "CBOE Volatility Index (VIX)", "sector": "Index"},
        {"symbol": "^TNX", "name": "10-Year Treasury Yield", "sector": "Index"},
        {"symbol": "^FTSE", "name": "FTSE 100 Index (UK)", "sector": "Index"},
        {"symbol": "^N225", "name": "Nikkei 225 Index (Japan)", "sector": "Index"},
        {"symbol": "^HSI", "name": "Hang Seng Index (Hong Kong)", "sector": "Index"},
        {"symbol": "^GDAXI", "name": "DAX Index (Germany)", "sector": "Index"},
        # Real Estate & Utilities
        {"symbol": "O", "name": "Realty Income Corp.", "sector": "Real Estate"},
        {"symbol": "AMT", "name": "American Tower Corp.", "sector": "Real Estate"},
        {"symbol": "PLD", "name": "Prologis Inc.", "sector": "Real Estate"},
        {"symbol": "NEE", "name": "NextEra Energy Inc.", "sector": "Utilities"},
        {"symbol": "DUK", "name": "Duke Energy Corp.", "sector": "Utilities"},
        # Telecom & Media
        {"symbol": "T", "name": "AT&T Inc.", "sector": "Communication Services"},
        {"symbol": "VZ", "name": "Verizon Communications Inc.", "sector": "Communication Services"},
        {"symbol": "TMUS", "name": "T-Mobile US Inc.", "sector": "Communication Services"},
        {"symbol": "DIS", "name": "Walt Disney Co.", "sector": "Communication Services"},
        {"symbol": "CMCSA", "name": "Comcast Corp.", "sector": "Communication Services"},
        {"symbol": "SPOT", "name": "Spotify Technology S.A.", "sector": "Communication Services"},
        {"symbol": "RBLX", "name": "Roblox Corp.", "sector": "Communication Services"},
        {"symbol": "SNAP", "name": "Snap Inc.", "sector": "Communication Services"},
        {"symbol": "PINS", "name": "Pinterest Inc.", "sector": "Communication Services"},
        {"symbol": "TWTR", "name": "X Corp. (formerly Twitter)", "sector": "Communication Services"},
    ]

    # Exact prefix match first (ticker starts with query), then name contains query
    prefix = [t for t in TICKERS if t["symbol"].startswith(q)]
    name_match = [t for t in TICKERS if t not in prefix and q in t["name"].upper()]
    return (prefix + name_match)[:8]


@router.get("/overview")
async def get_market_overview():
    """
    Market overview: major indices + 11 SPDR sector ETFs performance.
    Used by the Markets page header.
    """
    import asyncio
    import yfinance as yf

    INDICES = [
        ("SPY", "S&P 500"), ("QQQ", "NASDAQ"), ("DIA", "DOW"),
        ("IWM", "Russell"), ("^VIX", "VIX"), ("^TNX", "10Y"),
    ]
    SECTORS = [
        ("XLK", "Tech"), ("XLF", "Financials"), ("XLE", "Energy"),
        ("XLV", "Health"), ("XLI", "Industrials"), ("XLP", "Staples"),
        ("XLY", "Discretionary"), ("XLU", "Utilities"), ("XLB", "Materials"),
        ("XLRE", "Real Estate"), ("XLC", "Comms"),
    ]

    def _fetch(symbols_labels):
        results = []
        for sym, label in symbols_labels:
            try:
                hist = yf.Ticker(sym).history(period="5d", interval="1d")
                if len(hist) >= 2:
                    prev = float(hist["Close"].iloc[-2])
                    curr = float(hist["Close"].iloc[-1])
                    chg = (curr - prev) / prev * 100
                    week = (curr / float(hist["Close"].iloc[0]) - 1) * 100
                    results.append({
                        "symbol": sym, "label": label,
                        "price": round(curr, 2),
                        "change_pct": round(chg, 2),
                        "week_pct": round(week, 2),
                    })
            except Exception:
                pass
        return results

    loop = asyncio.get_running_loop()
    indices, sectors = await asyncio.gather(
        loop.run_in_executor(None, _fetch, INDICES),
        loop.run_in_executor(None, _fetch, SECTORS),
    )
    return {"indices": indices, "sectors": sectors, "as_of": datetime.now(UTC).isoformat()}


@router.get("/movers")
async def get_market_movers():
    """
    Top gainers and losers from the scanner watchlist (today's 1d change).
    No AI — pure price data. Returns top 5 gainers + top 5 losers.
    """
    import asyncio
    import yfinance as yf
    from app.workers.scanner import WATCHLIST

    def _fetch_changes():
        results = []
        # Sample 20 tickers for speed
        import random
        sample = random.sample(WATCHLIST, min(20, len(WATCHLIST)))
        for ticker in sample:
            try:
                hist = yf.Ticker(ticker).history(period="2d", interval="1d")
                if len(hist) >= 2:
                    prev = float(hist["Close"].iloc[-2])
                    curr = float(hist["Close"].iloc[-1])
                    chg = (curr - prev) / prev * 100
                    vol = int(hist["Volume"].iloc[-1])
                    results.append({
                        "symbol": ticker,
                        "price": round(curr, 2),
                        "change_pct": round(chg, 2),
                        "volume": vol,
                    })
            except Exception:
                pass
        return results

    loop = asyncio.get_running_loop()
    all_stocks = await loop.run_in_executor(None, _fetch_changes)
    sorted_stocks = sorted(all_stocks, key=lambda x: x["change_pct"], reverse=True)
    return {
        "gainers": sorted_stocks[:5],
        "losers": sorted_stocks[-5:][::-1],
        "as_of": datetime.now(UTC).isoformat(),
    }


@router.get("/stats/{ticker}")
async def get_ticker_stats(ticker: str):
    """
    Key stats for a ticker: 52w high/low, avg volume, market cap, P/E, beta.
    Used by the Markets page detail panel.
    """
    import asyncio
    import yfinance as yf

    def _fetch():
        t = yf.Ticker(ticker.upper())
        info = t.info or {}
        hist = t.history(period="1y", interval="1d")
        stats = {
            "symbol": ticker.upper(),
            "name": info.get("longName") or info.get("shortName", ticker.upper()),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", ""),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "beta": info.get("beta"),
            "dividend_yield": info.get("dividendYield"),
            "avg_volume": info.get("averageVolume"),
            "shares_outstanding": info.get("sharesOutstanding"),
        }
        if not hist.empty:
            stats["week_52_high"] = round(float(hist["High"].max()), 2)
            stats["week_52_low"] = round(float(hist["Low"].min()), 2)
            stats["current_price"] = round(float(hist["Close"].iloc[-1]), 2)
        return stats

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _fetch)
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch stats: {e}")


@router.get("/news/{ticker}")
async def get_news(ticker: str, limit: int = 20):
    """
    Recent news for a ticker via Alpaca News API.
    Falls back to yfinance news if Alpaca not configured.
    """
    import json

    ticker = ticker.upper()

    # Try Alpaca News API first (better quality, more structured)
    if settings.alpaca_api_key:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(
                    "https://data.alpaca.markets/v1beta1/news",
                    headers={
                        "APCA-API-KEY-ID": settings.alpaca_api_key,
                        "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
                    },
                    params={"symbols": ticker, "limit": limit, "sort": "desc"},
                )
            if r.status_code == 200:
                items = r.json().get("news", [])
                return [
                    {
                        "id": str(n.get("id", "")),
                        "headline": n.get("headline", ""),
                        "summary": n.get("summary", ""),
                        "source": n.get("source", ""),
                        "url": n.get("url", ""),
                        "published_at": n.get("created_at", ""),
                        "tickers": n.get("symbols", []),
                        "images": n.get("images", []),
                    }
                    for n in items
                ]
        except Exception:
            pass

    # Fallback: yfinance news
    def _yf_news():
        import yfinance as yf
        tk = yf.Ticker(ticker)
        raw = tk.news or []
        out = []
        for n in raw[:limit]:
            content = n.get("content", {})
            out.append({
                "id": n.get("id", ""),
                "headline": content.get("title", n.get("title", "")),
                "summary": content.get("summary", ""),
                "source": content.get("provider", {}).get("displayName", ""),
                "url": content.get("canonicalUrl", {}).get("url", ""),
                "published_at": content.get("pubDate", ""),
                "tickers": [ticker],
                "images": [],
            })
        return out

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _yf_news)
    except Exception as e:
        raise HTTPException(500, f"News fetch failed: {e}")


@router.get("/calendar")
async def get_economic_calendar(tickers: str = ""):
    """
    Upcoming earnings for watchlist tickers + hardcoded macro events (FOMC, CPI, etc.)
    tickers: comma-separated list e.g. "AAPL,MSFT,NVDA"
    """
    import asyncio
    import datetime as dt

    events = []

    # ── Hardcoded macro calendar (upcoming 2026 dates) ─────────────────────
    today = dt.date.today()
    macro_events = [
        # FOMC meetings 2026
        {"date": "2026-01-29", "type": "FOMC", "title": "FOMC Rate Decision", "impact": "HIGH", "description": "Federal Reserve interest rate decision and press conference"},
        {"date": "2026-03-19", "type": "FOMC", "title": "FOMC Rate Decision", "impact": "HIGH", "description": "Federal Reserve interest rate decision and press conference"},
        {"date": "2026-05-07", "type": "FOMC", "title": "FOMC Rate Decision", "impact": "HIGH", "description": "Federal Reserve interest rate decision and press conference"},
        {"date": "2026-06-18", "type": "FOMC", "title": "FOMC Rate Decision", "impact": "HIGH", "description": "Federal Reserve interest rate decision and press conference"},
        {"date": "2026-07-30", "type": "FOMC", "title": "FOMC Rate Decision", "impact": "HIGH", "description": "Federal Reserve interest rate decision and press conference"},
        {"date": "2026-09-17", "type": "FOMC", "title": "FOMC Rate Decision", "impact": "HIGH", "description": "Federal Reserve interest rate decision and press conference"},
        {"date": "2026-11-05", "type": "FOMC", "title": "FOMC Rate Decision", "impact": "HIGH", "description": "Federal Reserve interest rate decision and press conference"},
        {"date": "2026-12-17", "type": "FOMC", "title": "FOMC Rate Decision", "impact": "HIGH", "description": "Federal Reserve interest rate decision and press conference"},
        # CPI releases 2026 (approximate — 2nd or 3rd week each month)
        {"date": "2026-01-15", "type": "CPI", "title": "CPI Inflation Report", "impact": "HIGH", "description": "Consumer Price Index — monthly inflation reading"},
        {"date": "2026-02-12", "type": "CPI", "title": "CPI Inflation Report", "impact": "HIGH", "description": "Consumer Price Index — monthly inflation reading"},
        {"date": "2026-03-12", "type": "CPI", "title": "CPI Inflation Report", "impact": "HIGH", "description": "Consumer Price Index — monthly inflation reading"},
        {"date": "2026-04-14", "type": "CPI", "title": "CPI Inflation Report", "impact": "HIGH", "description": "Consumer Price Index — monthly inflation reading"},
        {"date": "2026-05-13", "type": "CPI", "title": "CPI Inflation Report", "impact": "HIGH", "description": "Consumer Price Index — monthly inflation reading"},
        {"date": "2026-06-11", "type": "CPI", "title": "CPI Inflation Report", "impact": "HIGH", "description": "Consumer Price Index — monthly inflation reading"},
        {"date": "2026-07-15", "type": "CPI", "title": "CPI Inflation Report", "impact": "HIGH", "description": "Consumer Price Index — monthly inflation reading"},
        {"date": "2026-08-13", "type": "CPI", "title": "CPI Inflation Report", "impact": "HIGH", "description": "Consumer Price Index — monthly inflation reading"},
        {"date": "2026-09-11", "type": "CPI", "title": "CPI Inflation Report", "impact": "HIGH", "description": "Consumer Price Index — monthly inflation reading"},
        {"date": "2026-10-14", "type": "CPI", "title": "CPI Inflation Report", "impact": "HIGH", "description": "Consumer Price Index — monthly inflation reading"},
        {"date": "2026-11-13", "type": "CPI", "title": "CPI Inflation Report", "impact": "HIGH", "description": "Consumer Price Index — monthly inflation reading"},
        {"date": "2026-12-11", "type": "CPI", "title": "CPI Inflation Report", "impact": "HIGH", "description": "Consumer Price Index — monthly inflation reading"},
        # NFP (Non-Farm Payrolls) — first Friday each month
        {"date": "2026-01-09", "type": "NFP", "title": "Non-Farm Payrolls", "impact": "HIGH", "description": "Monthly jobs report — most market-moving macro event"},
        {"date": "2026-02-06", "type": "NFP", "title": "Non-Farm Payrolls", "impact": "HIGH", "description": "Monthly jobs report — most market-moving macro event"},
        {"date": "2026-03-06", "type": "NFP", "title": "Non-Farm Payrolls", "impact": "HIGH", "description": "Monthly jobs report — most market-moving macro event"},
        {"date": "2026-04-03", "type": "NFP", "title": "Non-Farm Payrolls", "impact": "HIGH", "description": "Monthly jobs report — most market-moving macro event"},
        {"date": "2026-05-01", "type": "NFP", "title": "Non-Farm Payrolls", "impact": "HIGH", "description": "Monthly jobs report — most market-moving macro event"},
        {"date": "2026-06-05", "type": "NFP", "title": "Non-Farm Payrolls", "impact": "HIGH", "description": "Monthly jobs report — most market-moving macro event"},
        {"date": "2026-07-10", "type": "NFP", "title": "Non-Farm Payrolls", "impact": "HIGH", "description": "Monthly jobs report — most market-moving macro event"},
        {"date": "2026-08-07", "type": "NFP", "title": "Non-Farm Payrolls", "impact": "HIGH", "description": "Monthly jobs report — most market-moving macro event"},
        {"date": "2026-09-04", "type": "NFP", "title": "Non-Farm Payrolls", "impact": "HIGH", "description": "Monthly jobs report — most market-moving macro event"},
        {"date": "2026-10-02", "type": "NFP", "title": "Non-Farm Payrolls", "impact": "HIGH", "description": "Monthly jobs report — most market-moving macro event"},
        {"date": "2026-11-06", "type": "NFP", "title": "Non-Farm Payrolls", "impact": "HIGH", "description": "Monthly jobs report — most market-moving macro event"},
        {"date": "2026-12-04", "type": "NFP", "title": "Non-Farm Payrolls", "impact": "HIGH", "description": "Monthly jobs report — most market-moving macro event"},
    ]

    # Only include events from today onwards (next 90 days)
    cutoff = today + dt.timedelta(days=90)
    for e in macro_events:
        event_date = dt.date.fromisoformat(e["date"])
        if today <= event_date <= cutoff:
            events.append({**e, "ticker": None})

    # ── Earnings dates from yfinance ───────────────────────────────────────
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()] if tickers else []

    if ticker_list:
        def _fetch_earnings(ticker_list):
            import yfinance as yf
            results = []
            for sym in ticker_list:
                try:
                    tk = yf.Ticker(sym)
                    cal = tk.calendar
                    if cal is None:
                        continue
                    # yfinance returns a dict or DataFrame depending on version
                    if hasattr(cal, 'to_dict'):
                        cal = cal.to_dict()
                    # Earnings Date can be a list or single value
                    earnings_dates = cal.get("Earnings Date", [])
                    if not isinstance(earnings_dates, list):
                        earnings_dates = [earnings_dates]
                    for ed in earnings_dates:
                        if ed is None:
                            continue
                        if hasattr(ed, 'date'):
                            ed = ed.date()
                        elif isinstance(ed, str):
                            ed = dt.date.fromisoformat(ed[:10])
                        if today <= ed <= cutoff:
                            # Get EPS estimate
                            eps_est = cal.get("EPS Estimate")
                            if isinstance(eps_est, (list, )):
                                eps_est = eps_est[0] if eps_est else None
                            results.append({
                                "date": ed.isoformat(),
                                "type": "EARNINGS",
                                "title": f"{sym} Earnings",
                                "ticker": sym,
                                "impact": "MEDIUM",
                                "description": f"Quarterly earnings report. EPS estimate: {f'${eps_est:.2f}' if eps_est else 'N/A'}",
                            })
                except Exception:
                    pass
            return results

        loop = asyncio.get_running_loop()
        try:
            earnings = await loop.run_in_executor(None, _fetch_earnings, ticker_list)
            events.extend(earnings)
        except Exception:
            pass

    # Sort by date
    events.sort(key=lambda x: x["date"])
    return events


@router.get("/regime")
async def get_regime():
    """Current market regime — BULL_TRENDING, BEAR_TRENDING, HIGH_VOLATILITY, SIDEWAYS."""
    from app.workers.regime_detector import get_market_regime
    return await get_market_regime()


@router.get("/names")
async def get_ticker_names(tickers: str = ""):
    """
    Batch name + sector lookup for a list of tickers.
    tickers: comma-separated e.g. "AAPL,MSFT,NVDA"
    Returns: { "AAPL": { "name": "Apple Inc.", "sector": "Technology" }, ... }
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        return {}

    # Known names cache for common tickers (instant, no API call)
    KNOWN: dict[str, tuple[str, str]] = {
        "AAPL": ("Apple Inc.", "Technology"), "MSFT": ("Microsoft Corp.", "Technology"),
        "NVDA": ("NVIDIA Corp.", "Technology"), "GOOGL": ("Alphabet Inc.", "Communication Services"),
        "GOOG": ("Alphabet Inc.", "Communication Services"), "META": ("Meta Platforms", "Communication Services"),
        "AMZN": ("Amazon.com Inc.", "Consumer Discretionary"), "TSLA": ("Tesla Inc.", "Consumer Discretionary"),
        "AMD": ("Advanced Micro Devices", "Technology"), "INTC": ("Intel Corp.", "Technology"),
        "QCOM": ("Qualcomm Inc.", "Technology"), "AVGO": ("Broadcom Inc.", "Technology"),
        "CRM": ("Salesforce Inc.", "Technology"), "ORCL": ("Oracle Corp.", "Technology"),
        "NFLX": ("Netflix Inc.", "Communication Services"), "ADBE": ("Adobe Inc.", "Technology"),
        "SNOW": ("Snowflake Inc.", "Technology"), "PLTR": ("Palantir Technologies", "Technology"),
        "UBER": ("Uber Technologies", "Technology"), "MELI": ("MercadoLibre Inc.", "Consumer Discretionary"),
        "JPM": ("JPMorgan Chase", "Financials"), "GS": ("Goldman Sachs", "Financials"),
        "V": ("Visa Inc.", "Financials"), "MA": ("Mastercard Inc.", "Financials"),
        "BAC": ("Bank of America", "Financials"), "COIN": ("Coinbase Global", "Financials"),
        "UNH": ("UnitedHealth Group", "Healthcare"), "LLY": ("Eli Lilly", "Healthcare"),
        "ABBV": ("AbbVie Inc.", "Healthcare"), "MRNA": ("Moderna Inc.", "Healthcare"),
        "JNJ": ("Johnson & Johnson", "Healthcare"), "XOM": ("Exxon Mobil", "Energy"),
        "CVX": ("Chevron Corp.", "Energy"), "WMT": ("Walmart Inc.", "Consumer Staples"),
        "COST": ("Costco Wholesale", "Consumer Staples"), "HD": ("Home Depot", "Consumer Discretionary"),
        "MCD": ("McDonald's Corp.", "Consumer Discretionary"), "NKE": ("Nike Inc.", "Consumer Discretionary"),
        "MU": ("Micron Technology", "Technology"), "TSM": ("Taiwan Semiconductor", "Technology"),
        "ASML": ("ASML Holding", "Technology"), "TXN": ("Texas Instruments", "Technology"),
        "SPY": ("SPDR S&P 500 ETF", "ETF"), "QQQ": ("Invesco QQQ Trust", "ETF"),
        "IWM": ("iShares Russell 2000 ETF", "ETF"), "DIA": ("SPDR Dow Jones ETF", "ETF"),
        "GLD": ("SPDR Gold Trust", "ETF"), "SLV": ("iShares Silver Trust", "ETF"),
        "IBIT": ("iShares Bitcoin Trust", "ETF"), "MSTR": ("MicroStrategy Inc.", "Technology"),
        "MARA": ("Marathon Digital Holdings", "Technology"), "PYPL": ("PayPal Holdings", "Financials"),
        "SQ": ("Block Inc.", "Financials"), "SHOP": ("Shopify Inc.", "Technology"),
        "ARM": ("Arm Holdings", "Technology"), "SMCI": ("Super Micro Computer", "Technology"),
        "HOOD": ("Robinhood Markets", "Financials"), "SOFI": ("SoFi Technologies", "Financials"),
        "^GSPC": ("S&P 500 Index", "Index"), "^IXIC": ("NASDAQ Composite", "Index"),
        "^DJI": ("Dow Jones Industrial", "Index"), "^RUT": ("Russell 2000 Index", "Index"),
        "^VIX": ("CBOE Volatility Index", "Index"), "^TNX": ("10-Year Treasury Yield", "Index"),
    }

    result = {}
    need_fetch = []

    for ticker in ticker_list:
        if ticker in KNOWN:
            result[ticker] = {"name": KNOWN[ticker][0], "sector": KNOWN[ticker][1]}
        else:
            need_fetch.append(ticker)

    # Fetch unknown tickers from yfinance
    if need_fetch:
        def _fetch_names(tickers_to_fetch):
            import yfinance as yf
            out = {}
            for sym in tickers_to_fetch:
                try:
                    info = yf.Ticker(sym).info
                    out[sym] = {
                        "name": info.get("shortName") or info.get("longName") or sym,
                        "sector": info.get("sector") or info.get("quoteType") or "—",
                    }
                except Exception:
                    out[sym] = {"name": sym, "sector": "—"}
            return out

        loop = asyncio.get_running_loop()
        fetched = await loop.run_in_executor(None, _fetch_names, need_fetch)
        result.update(fetched)

    return result


@router.get("/ai-read/{ticker}")
async def ai_chart_read(ticker: str, refresh: bool = False):
    """
    AI reading of a stock's chart: trend bias + confidence, key support/resistance
    levels, and indicator-grounded reasoning. Every reason cites a real computed
    value (RSI, MACD, MAs, volume, momentum) so the user can verify it on the chart.
    Cached in Redis for 10 minutes per ticker (pass ?refresh=true to bypass).
    """
    import asyncio
    import json as _json

    symbol = ticker.upper().strip()
    CACHE_KEY = f"ai_chart_read:{symbol}"

    if not refresh:
        try:
            import redis as _redis
            _r = _redis.from_url(settings.redis_url)
            cached = _r.get(CACHE_KEY)
            if cached:
                return _json.loads(cached)
        except Exception:
            pass

    # ── Compute technicals from 6 months of daily bars ─────────────────────────
    def _compute():
        import yfinance as yf
        import numpy as np

        t = yf.Ticker(symbol)
        hist = t.history(period="6mo", interval="1d")
        if hist.empty or len(hist) < 30:
            raise ValueError(f"Not enough price history for {symbol}")

        closes = hist["Close"]
        highs = hist["High"]
        lows = hist["Low"]
        vols = hist["Volume"]
        price = float(closes.iloc[-1])

        # RSI-14
        delta = closes.diff().dropna()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi = float((100 - 100 / (1 + rs)).iloc[-1])

        # MACD
        ema12 = closes.ewm(span=12).mean()
        ema26 = closes.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9).mean()
        macd_bullish = bool(macd_line.iloc[-1] > signal_line.iloc[-1])
        macd_histogram = float(macd_line.iloc[-1] - signal_line.iloc[-1])

        # Moving averages
        ma20 = float(closes.rolling(20).mean().iloc[-1])
        ma50 = float(closes.rolling(50).mean().iloc[-1]) if len(closes) >= 50 else None
        ma200 = float(closes.rolling(200).mean().iloc[-1]) if len(closes) >= 200 else None

        # Momentum
        mom_1w = float((closes.iloc[-1] / closes.iloc[-5] - 1) * 100) if len(closes) >= 5 else 0.0
        mom_1m = float((closes.iloc[-1] / closes.iloc[-21] - 1) * 100) if len(closes) >= 21 else 0.0

        # Volume trend
        vol_ratio = float(vols.iloc[-5:].mean() / vols.iloc[-30:].mean()) if vols.iloc[-30:].mean() > 0 else 1.0

        # Swing-pivot support/resistance (5-bar pivots, deduped within 1.5%)
        def _pivots(series, window=5, find_high=True):
            levels = []
            vals = series.values
            for i in range(window, len(vals) - window):
                seg = vals[i - window:i + window + 1]
                if (find_high and vals[i] == seg.max()) or (not find_high and vals[i] == seg.min()):
                    levels.append(float(vals[i]))
            deduped = []
            for lv in sorted(levels):
                if not deduped or abs(lv - deduped[-1]) / deduped[-1] > 0.015:
                    deduped.append(lv)
            return deduped

        # Nearest levels first: supports just below price, resistances just above
        supports = [lv for lv in _pivots(lows, find_high=False) if lv < price][-3:][::-1]
        resistances = [lv for lv in _pivots(highs, find_high=True) if lv > price][:3]

        return {
            "price": round(price, 2),
            "rsi_14": round(rsi, 1),
            "macd_bullish": macd_bullish,
            "macd_histogram": round(macd_histogram, 4),
            "ma20": round(ma20, 2),
            "ma50": round(ma50, 2) if ma50 else None,
            "ma200": round(ma200, 2) if ma200 else None,
            "above_ma20": price > ma20,
            "above_ma50": bool(ma50 and price > ma50),
            "above_ma200": bool(ma200 and price > ma200),
            "momentum_1w_pct": round(mom_1w, 2),
            "momentum_1m_pct": round(mom_1m, 2),
            "volume_ratio_5d_vs_30d": round(vol_ratio, 2),
            "support_levels": [round(s, 2) for s in supports],
            "resistance_levels": [round(r, 2) for r in resistances],
        }

    loop = asyncio.get_running_loop()
    try:
        ta = await loop.run_in_executor(None, _compute)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Market data fetch failed: {e}")

    # ── LLM synthesis with strict schema ────────────────────────────────────────
    tool_schema = {
        "name": "chart_read",
        "description": "Structured technical chart reading",
        "parameters": {
            "type": "object",
            "required": ["trend_bias", "confidence", "outlook", "reasons", "risks",
                         "support_levels", "resistance_levels"],
            "properties": {
                "trend_bias": {"type": "string", "enum": ["BULLISH", "BEARISH", "NEUTRAL"]},
                "confidence": {"type": "number", "description": "0.0-1.0"},
                "outlook": {"type": "string", "description": "2-3 sentence outlook for the next 1-4 weeks"},
                "reasons": {
                    "type": "array", "items": {"type": "string"},
                    "description": "3-5 reasons, EACH citing a specific indicator value from the data (e.g. 'RSI at 62 shows...')",
                },
                "risks": {"type": "array", "items": {"type": "string"},
                          "description": "2-3 specific risks that would invalidate the thesis"},
                "support_levels": {"type": "array", "items": {"type": "number"},
                                   "description": "1-3 key support prices, most important first"},
                "resistance_levels": {"type": "array", "items": {"type": "number"},
                                      "description": "1-3 key resistance prices, most important first"},
            },
        },
    }

    def _call_ai():
        from openai import OpenAI
        client = OpenAI(api_key=settings.nvidia_api_key, base_url=settings.nvidia_base_url,
                        timeout=90.0, max_retries=0)
        response = client.chat.completions.create(
            model=settings.llm_model or "deepseek-ai/deepseek-v4-flash",
            max_tokens=900,
            temperature=0.3,
            messages=[
                {"role": "system", "content": (
                    "You are a veteran technical analyst reading a chart for a retail trader. "
                    "Ground EVERY claim in the provided indicator values — cite the numbers. "
                    "Use Wyckoff/ICT concepts where relevant (accumulation, liquidity sweeps, "
                    "premium/discount vs the range). Be honest when signals conflict: say NEUTRAL. "
                    "Pick support/resistance from the provided pivot levels (adjust only slightly if needed)."
                )},
                {"role": "user", "content": (
                    f"Read the chart for {symbol}:\n{_json.dumps(ta, indent=2)}\n\n"
                    "Give your structured chart read."
                )},
            ],
            tools=[{"type": "function", "function": tool_schema}],
            tool_choice="required",
        )
        msg = response.choices[0].message
        if msg.tool_calls:
            return _json.loads(msg.tool_calls[0].function.arguments)
        import re
        m = re.search(r"\{.*\}", msg.content or "", re.DOTALL)
        if not m:
            raise ValueError("No structured output from model")
        return _json.loads(m.group())

    try:
        read = await loop.run_in_executor(None, _call_ai)
    except Exception as e:
        raise HTTPException(502, f"AI analysis failed: {e}")

    result = {
        "ticker": symbol,
        "generated_at": datetime.now(UTC).isoformat(),
        "technicals": ta,
        "read": read,
    }

    try:
        import redis as _redis
        _r = _redis.from_url(settings.redis_url)
        _r.setex(CACHE_KEY, 600, _json.dumps(result))
    except Exception:
        pass

    return result
