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

    # Common tickers database
    TICKERS = [
        {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology"},
        {"symbol": "MSFT", "name": "Microsoft Corp.", "sector": "Technology"},
        {"symbol": "GOOGL", "name": "Alphabet Inc.", "sector": "Technology"},
        {"symbol": "AMZN", "name": "Amazon.com Inc.", "sector": "Consumer Discretionary"},
        {"symbol": "NVDA", "name": "NVIDIA Corp.", "sector": "Technology"},
        {"symbol": "META", "name": "Meta Platforms Inc.", "sector": "Technology"},
        {"symbol": "TSLA", "name": "Tesla Inc.", "sector": "Consumer Discretionary"},
        {"symbol": "AMD", "name": "Advanced Micro Devices", "sector": "Technology"},
        {"symbol": "AVGO", "name": "Broadcom Inc.", "sector": "Technology"},
        {"symbol": "ORCL", "name": "Oracle Corp.", "sector": "Technology"},
        {"symbol": "ASML", "name": "ASML Holding N.V.", "sector": "Technology"},
        {"symbol": "TSM", "name": "Taiwan Semiconductor", "sector": "Technology"},
        {"symbol": "NFLX", "name": "Netflix Inc.", "sector": "Communication Services"},
        {"symbol": "ADBE", "name": "Adobe Inc.", "sector": "Technology"},
        {"symbol": "CRM", "name": "Salesforce Inc.", "sector": "Technology"},
        {"symbol": "INTC", "name": "Intel Corp.", "sector": "Technology"},
        {"symbol": "QCOM", "name": "Qualcomm Inc.", "sector": "Technology"},
        {"symbol": "TXN", "name": "Texas Instruments", "sector": "Technology"},
        {"symbol": "COIN", "name": "Coinbase Global Inc.", "sector": "Financials"},
        {"symbol": "PLTR", "name": "Palantir Technologies", "sector": "Technology"},
        {"symbol": "SNOW", "name": "Snowflake Inc.", "sector": "Technology"},
        {"symbol": "UBER", "name": "Uber Technologies", "sector": "Technology"},
        {"symbol": "SHOP", "name": "Shopify Inc.", "sector": "Consumer Discretionary"},
        {"symbol": "SQ", "name": "Block Inc.", "sector": "Financials"},
        {"symbol": "PYPL", "name": "PayPal Holdings", "sector": "Financials"},
        {"symbol": "JPM", "name": "JPMorgan Chase & Co.", "sector": "Financials"},
        {"symbol": "GS", "name": "Goldman Sachs Group", "sector": "Financials"},
        {"symbol": "BAC", "name": "Bank of America Corp.", "sector": "Financials"},
        {"symbol": "V", "name": "Visa Inc.", "sector": "Financials"},
        {"symbol": "MA", "name": "Mastercard Inc.", "sector": "Financials"},
        {"symbol": "UNH", "name": "UnitedHealth Group", "sector": "Healthcare"},
        {"symbol": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare"},
        {"symbol": "LLY", "name": "Eli Lilly and Co.", "sector": "Healthcare"},
        {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "sector": "ETF"},
        {"symbol": "QQQ", "name": "Invesco QQQ Trust", "sector": "ETF"},
        {"symbol": "IWM", "name": "iShares Russell 2000 ETF", "sector": "ETF"},
        {"symbol": "XOM", "name": "Exxon Mobil Corp.", "sector": "Energy"},
        {"symbol": "CVX", "name": "Chevron Corp.", "sector": "Energy"},
        {"symbol": "SMCI", "name": "Super Micro Computer", "sector": "Technology"},
        {"symbol": "ARM", "name": "Arm Holdings plc", "sector": "Technology"},
    ]

    matches = [t for t in TICKERS if t["symbol"].startswith(q) or q in t["name"].upper()]
    return matches[:8]


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
