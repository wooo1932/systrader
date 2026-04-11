from __future__ import annotations
import queue
import threading
from concurrent.futures import Future
from typing import Callable, Any


class CommandQueue:
    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._handler: Callable | None = None
        self._event = threading.Event()

    def register_handler(self, handler: Callable[[str, dict], Any]) -> None:
        self._handler = handler

    def put(self, command: str, params: dict) -> Future:
        future = Future()
        self._queue.put((command, params, future))
        self._event.set()
        return future

    def has_pending(self) -> bool:
        return not self._queue.empty()

    def get_event(self) -> threading.Event:
        return self._event

    def process(self) -> None:
        while not self._queue.empty():
            try:
                command, params, future = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                result = self._handler(command, params)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)
        self._event.clear()
