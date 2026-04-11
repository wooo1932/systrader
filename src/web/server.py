from __future__ import annotations
import asyncio
import logging
import os
import threading
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from src.web.websocket import ConnectionManager, EventBridge
from src.web.context import _app_context, get_context
from src.web.routes import status, trades, stats, settings, news, logs

log = logging.getLogger(__name__)

ws_manager = ConnectionManager()
event_bridge = EventBridge(ws_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    event_bridge.set_loop(asyncio.get_event_loop())
    yield

app = FastAPI(lifespan=lifespan)

app.include_router(status.router, prefix="/api")
app.include_router(trades.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(news.router, prefix="/api")
app.include_router(logs.router, prefix="/api")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except Exception:
        ws_manager.disconnect(ws)


_static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "web", "dist")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")


def start_server(context: dict, host: str = "0.0.0.0", port: int = 8000) -> threading.Thread:
    _app_context.update(context)

    event_bus = context.get("event_bus")
    if event_bus:
        for evt in ("cybos_status", "engine_status", "news_feed", "news_detected",
                     "worker_state", "buy_filled", "sell_filled", "trade_done"):
            event_bus.subscribe(evt, lambda data, t=evt: event_bridge.push(t, data))

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    log.info(f"Web server started on {host}:{port}")
    return thread
