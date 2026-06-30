"""
Real-time price feed via Alpaca WebSocket stream.

Connects to wss://stream.data.alpaca.markets/v2/iex and subscribes to
quotes for a curated list of tickers. On each quote:
  - Stores latest price in Redis: key "price:{TICKER}" → JSON {price, timestamp}
  - Broadcasts to WS room "prices" for frontend consumption

Reconnects automatically after a 5-second pause if the stream drops.
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime, UTC
import structlog

from app.config import get_settings
from app.core.redis_client import get_redis
from app.core.websocket_manager import ws_manager

log = structlog.get_logger()
settings = get_settings()

# S&P 100 subset + ETFs tracked for live quotes
TRACKED_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AMD",
    "ASML", "TSM", "AVGO", "ORCL", "CRM", "ADBE", "NFLX", "NOW",
    "PANW", "SNOW", "COIN", "PLTR", "UNH", "LLY", "JPM", "GS",
    "V", "MA", "WMT", "COST", "HD", "SPY", "QQQ", "VIX",
]

_STREAM_URL = "wss://stream.data.alpaca.markets/v2/iex"
_RECONNECT_DELAY_S = 5


async def _handle_messages(websocket) -> None:
    """Process incoming messages from the Alpaca data stream."""
    redis = await get_redis()

    async for raw in websocket:
        try:
            messages = json.loads(raw)
            if not isinstance(messages, list):
                messages = [messages]

            for msg in messages:
                msg_type = msg.get("T")

                if msg_type == "q":
                    # Quote message
                    ticker = msg.get("S", "")
                    # bid_price is the most recent best bid — use as proxy for current price
                    bp = msg.get("bp") or msg.get("ap")  # bid price, fallback to ask price
                    timestamp = msg.get("t", datetime.now(UTC).isoformat())

                    if ticker and bp:
                        price = float(bp)
                        payload = json.dumps({"price": price, "timestamp": timestamp})
                        await redis.set(f"price:{ticker}", payload, ex=300)

                        # Broadcast to frontend WS subscribers in "prices" room
                        await ws_manager.broadcast("prices", {
                            "type": "quote",
                            "ticker": ticker,
                            "price": price,
                            "timestamp": timestamp,
                        })

                elif msg_type == "error":
                    log.warning("price_feed.stream_error",
                                code=msg.get("code"), message=msg.get("msg"))

                elif msg_type == "subscription":
                    log.info("price_feed.subscribed",
                             quotes=msg.get("quotes", []),
                             trades=msg.get("trades", []))

                elif msg_type == "success":
                    log.info("price_feed.auth_success", message=msg.get("msg"))

        except Exception as e:
            log.warning("price_feed.message_error", error=str(e))


async def _connect_and_stream() -> None:
    """Open one WebSocket session: authenticate, subscribe, then stream."""
    try:
        import websockets
    except ImportError:
        log.error("price_feed.missing_dependency",
                  detail="websockets library not installed — pip install websockets")
        return

    if not settings.alpaca_api_key or not settings.alpaca_api_secret:
        log.warning("price_feed.no_credentials",
                    detail="ALPACA_API_KEY / ALPACA_API_SECRET not set — skipping price feed")
        return

    async with websockets.connect(_STREAM_URL) as ws:
        log.info("price_feed.connected", url=_STREAM_URL)

        # Step 1: Authenticate
        await ws.send(json.dumps({
            "action": "auth",
            "key": settings.alpaca_api_key,
            "secret": settings.alpaca_api_secret,
        }))

        # Step 2: Subscribe to quotes for all tracked tickers
        await ws.send(json.dumps({
            "action": "subscribe",
            "quotes": TRACKED_TICKERS,
        }))

        log.info("price_feed.subscribed", tickers=len(TRACKED_TICKERS))

        # Step 3: Stream
        await _handle_messages(ws)


async def run_price_feed() -> None:
    """
    Long-running background task — connects to Alpaca data stream and
    automatically reconnects on disconnection.
    """
    log.info("price_feed.starting")
    while True:
        try:
            await _connect_and_stream()
            log.warning("price_feed.stream_ended", action="reconnecting",
                        delay_s=_RECONNECT_DELAY_S)
        except asyncio.CancelledError:
            log.info("price_feed.cancelled")
            return
        except Exception as e:
            log.warning("price_feed.error", error=str(e), action="reconnecting",
                        delay_s=_RECONNECT_DELAY_S)
        await asyncio.sleep(_RECONNECT_DELAY_S)
