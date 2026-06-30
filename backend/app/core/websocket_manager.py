import asyncio
from collections import defaultdict
from typing import Any
from fastapi import WebSocket
import orjson
import structlog

log = structlog.get_logger()


class WebSocketManager:
    def __init__(self):
        # room_id → set of WebSocket connections
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, ws: WebSocket, room: str):
        await ws.accept()
        self._rooms[room].add(ws)
        log.info("ws.connect", room=room, total=len(self._rooms[room]))

    def disconnect(self, ws: WebSocket, room: str):
        self._rooms[room].discard(ws)
        if not self._rooms[room]:
            del self._rooms[room]
        log.info("ws.disconnect", room=room)

    async def broadcast(self, room: str, payload: Any):
        dead: list[WebSocket] = []
        data = orjson.dumps(payload).decode()
        for ws in list(self._rooms.get(room, [])):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, room)

    async def broadcast_global(self, payload: Any):
        """Send to all connected clients across all rooms."""
        data = orjson.dumps(payload).decode()
        tasks = []
        for room_sockets in self._rooms.values():
            for ws in list(room_sockets):
                tasks.append(ws.send_text(data))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


ws_manager = WebSocketManager()
