from __future__ import annotations
import time
from fastapi import APIRouter
from src.web.context import get_context

router = APIRouter()

_news_buffer: list[dict] = []
_MAX_NEWS = 200


@router.get("/news-feed")
async def get_news_feed():
    return _news_buffer[-100:]


@router.post("/test/news")
async def test_news(body: dict):
    ctx = get_context()
    event_bus = ctx.get("event_bus")
    if event_bus:
        news_data = {
            "code": body.get("stock_code", ""),
            "name": body.get("stock_name", ""),
            "source": "test",
            "title": body.get("text", "Test news"),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        event_bus.publish("news_detected", news_data)
        event_bus.publish("news_feed", {
            "stock_code": news_data["code"], "stock_name": news_data["name"],
            "source": "test", "text": news_data["title"],
            "timestamp": news_data["timestamp"],
        })
    return {"status": "ok"}


def register_news_buffer(event_bus) -> None:
    def on_news_feed(data):
        _news_buffer.append(data)
        while len(_news_buffer) > _MAX_NEWS:
            _news_buffer.pop(0)
    event_bus.subscribe("news_feed", on_news_feed)
