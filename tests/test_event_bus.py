import asyncio
import threading
import time
import pytest
from src.core.event_bus import EventBus


def test_subscribe_and_publish():
    bus = EventBus()
    received = []
    bus.subscribe("test", lambda data: received.append(data))
    bus.publish("test", {"msg": "hello"})
    time.sleep(0.05)
    assert len(received) == 1
    assert received[0]["msg"] == "hello"


def test_multiple_subscribers():
    bus = EventBus()
    results_a = []
    results_b = []
    bus.subscribe("evt", lambda d: results_a.append(d))
    bus.subscribe("evt", lambda d: results_b.append(d))
    bus.publish("evt", {"x": 1})
    time.sleep(0.05)
    assert len(results_a) == 1
    assert len(results_b) == 1


def test_different_event_types():
    bus = EventBus()
    a_events = []
    b_events = []
    bus.subscribe("a", lambda d: a_events.append(d))
    bus.subscribe("b", lambda d: b_events.append(d))
    bus.publish("a", {"v": 1})
    bus.publish("b", {"v": 2})
    time.sleep(0.05)
    assert len(a_events) == 1
    assert len(b_events) == 1


def test_publish_from_different_thread():
    bus = EventBus()
    received = []
    bus.subscribe("cross", lambda d: received.append(d))
    def worker():
        bus.publish("cross", {"from": "thread"})
    t = threading.Thread(target=worker)
    t.start()
    t.join()
    time.sleep(0.05)
    assert len(received) == 1


def test_async_wait_event():
    bus = EventBus()
    async def run():
        loop = asyncio.get_event_loop()
        bus.set_async_loop(loop)
        async def publisher():
            await asyncio.sleep(0.02)
            bus.publish("async_evt", {"val": 42})
        asyncio.create_task(publisher())
        data = await asyncio.wait_for(bus.wait_event("async_evt"), timeout=1.0)
        assert data["val"] == 42
    asyncio.run(run())


def test_publish_logs_callback_error(caplog):
    import logging
    bus = EventBus()
    def bad_callback(data):
        raise ValueError("boom")
    bus.subscribe("err", bad_callback)
    with caplog.at_level(logging.WARNING):
        bus.publish("err", {"x": 1})
    assert any("boom" in r.message for r in caplog.records)
