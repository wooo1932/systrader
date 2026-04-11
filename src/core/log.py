from __future__ import annotations
import logging
import os
from collections import deque
from logging.handlers import TimedRotatingFileHandler


class LogBuffer:
    def __init__(self, maxlen: int = 1000):
        self.buffer: deque[dict] = deque(maxlen=maxlen)
        self.seq: int = 0
        self._lock = __import__("threading").Lock()

    def append(self, record: logging.LogRecord) -> None:
        with self._lock:
            self.seq += 1
            self.buffer.append({
                "seq": self.seq,
                "timestamp": record.created,
                "level": record.levelname,
                "message": record.getMessage(),
                "logger": record.name,
            })

    def get_after(self, after_seq: int) -> list[dict]:
        with self._lock:
            return [e for e in self.buffer if e["seq"] > after_seq]


class BufferHandler(logging.Handler):
    def __init__(self, log_buffer: LogBuffer):
        super().__init__()
        self.log_buffer = log_buffer

    def emit(self, record: logging.LogRecord) -> None:
        self.log_buffer.append(record)


_log_buffer: LogBuffer | None = None


def get_log_buffer() -> LogBuffer:
    global _log_buffer
    if _log_buffer is None:
        _log_buffer = LogBuffer()
    return _log_buffer


def setup_logging(log_dir: str = "logs", log_level: str = "INFO") -> LogBuffer:
    global _log_buffer
    os.makedirs(log_dir, exist_ok=True)
    _log_buffer = LogBuffer()

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_path = os.path.join(log_dir, "systrader.log")
    file_handler = TimedRotatingFileHandler(
        file_path, when="midnight", backupCount=365, encoding="utf-8"
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    buffer_handler = BufferHandler(_log_buffer)
    buffer_handler.setFormatter(fmt)
    root.addHandler(buffer_handler)

    return _log_buffer
