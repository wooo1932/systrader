import asyncio
import threading
import time
import pytest
from src.core.command_queue import CommandQueue


def test_put_and_process():
    cq = CommandQueue()
    def handler(cmd, params):
        return {"result": cmd + "_done"}
    cq.register_handler(handler)
    result_holder = []
    def api_thread():
        future = cq.put("test_cmd", {"a": 1})
        result_holder.append(future.result(timeout=2.0))
    t = threading.Thread(target=api_thread)
    t.start()
    time.sleep(0.02)
    cq.process()
    t.join(timeout=2.0)
    assert len(result_holder) == 1
    assert result_holder[0]["result"] == "test_cmd_done"


def test_process_empty_queue():
    cq = CommandQueue()
    cq.register_handler(lambda cmd, params: None)
    cq.process()


def test_handler_exception_sets_future_exception():
    cq = CommandQueue()
    def bad_handler(cmd, params):
        raise ValueError("oops")
    cq.register_handler(bad_handler)
    future = cq.put("fail", {})
    cq.process()
    with pytest.raises(ValueError, match="oops"):
        future.result(timeout=1.0)


def test_has_pending():
    cq = CommandQueue()
    cq.register_handler(lambda cmd, params: None)
    assert not cq.has_pending()
    cq.put("x", {})
    assert cq.has_pending()
    cq.process()
    assert not cq.has_pending()
