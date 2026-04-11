from __future__ import annotations
import asyncio
import logging
from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, event_type: str, data: dict) -> None:
        msg = {"type": event_type, "data": data}
        for ws in self._connections[:]:
            try:
                await ws.send_json(msg)
            except Exception:
                self._connections.remove(ws)


class EventBridge:
    def __init__(self, manager: ConnectionManager):
        self._manager = manager
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def push(self, event_type: str, data: dict) -> None:
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._manager.broadcast(event_type, data), self._loop
            )
