from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.websocket_manager import ws_manager
import structlog

log = structlog.get_logger()
router = APIRouter()


@router.websocket("/runs/{run_id}")
async def agent_run_ws(ws: WebSocket, run_id: str):
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
    await ws_manager.connect(ws, room="portfolio")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws, room="portfolio")
