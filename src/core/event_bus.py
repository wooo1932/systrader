from __future__ import annotations
import asyncio
import logging
import threading
from collections import defaultdict
from typing import Callable

log = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._async_queues: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._lock = threading.Lock()
        self._async_loop: asyncio.AbstractEventLoop | None = None

    def set_async_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._async_loop = loop

    def subscribe(self, event_type: str, callback: Callable) -> None:
        with self._lock:
            self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        with self._lock:
            subs = self._subscribers[event_type]
            if callback in subs:
                subs.remove(callback)

    def publish(self, event_type: str, data: dict) -> None:
        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))
            queues = list(self._async_queues.get(event_type, []))
        for cb in callbacks:
            try:
                cb(data)
            except Exception as e:
                log.warning("Event callback error on '%s': %s", event_type, e)
        for q in queues:
            try:
                if self._async_loop and self._async_loop.is_running():
                    self._async_loop.call_soon_threadsafe(q.put_nowait, data)
                else:
                    q.put_nowait(data)
            except Exception as e:
                log.warning("Event queue error on '%s': %s", event_type, e)

    async def wait_event(self, event_type: str) -> dict:
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._async_queues[event_type].append(q)
        try:
            return await q.get()
        finally:
            with self._lock:
                self._async_queues[event_type].remove(q)
