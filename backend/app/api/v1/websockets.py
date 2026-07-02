from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError

from app.core.websocket_manager import ws_manager
from app.config import get_settings
import structlog

log = structlog.get_logger()
router = APIRouter()


async def _authenticate_ws(ws: WebSocket) -> bool:
    """Validate the JWT passed as ?token=. Rejects the handshake when invalid."""
    token = ws.query_params.get("token", "")
    if token:
        try:
            jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
            return True
        except JWTError:
            pass
    await ws.close(code=4401, reason="Authentication required")
    return False


@router.websocket("/runs/{run_id}")
async def agent_run_ws(ws: WebSocket, run_id: str):
    if not await _authenticate_ws(ws):
        return
    await ws_manager.connect(ws, room=f"run:{run_id}")
    try:
        while True:
            # Keep alive — client can send pings
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(ws, room=f"run:{run_id}")


@router.websocket("/scans/{scan_id}")
async def scan_ws(ws: WebSocket, scan_id: str):
    if not await _authenticate_ws(ws):
        return
    await ws_manager.connect(ws, room=f"scan:{scan_id}")
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(ws, room=f"scan:{scan_id}")


@router.websocket("/quotes")
async def quotes_ws(ws: WebSocket):
    if not await _authenticate_ws(ws):
        return
    await ws_manager.connect(ws, room="quotes")
    try:
        while True:
            # Client sends subscribe messages: {"action":"subscribe","tickers":["AAPL","TSLA"]}
            import orjson
            raw = await ws.receive_text()
            msg = orjson.loads(raw)
            if msg.get("action") == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        ws_manager.disconnect(ws, room="quotes")


@router.websocket("/portfolio")
async def portfolio_ws(ws: WebSocket):
    if not await _authenticate_ws(ws):
        return
    await ws_manager.connect(ws, room="portfolio")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws, room="portfolio")
