from __future__ import annotations
import logging
import time
import win32com.client
from src.core.event_bus import EventBus

log = logging.getLogger(__name__)

# CpSvr8092S category codes
CATEGORY_NEWS = 1
CATEGORY_DISCLOSURE = 2


class CybosNewsHandler:
    callback = None

    def OnReceived(self):
        try:
            code = self.GetHeaderValue(1)
            category = self.GetHeaderValue(4)
            title = self.GetHeaderValue(5)
            if CybosNewsHandler.callback:
                CybosNewsHandler.callback(code, category, title)
        except Exception as e:
            log.error(f"CybosNewsHandler error: {e}")


class CybosNewsSource:
    def __init__(self, event_bus: EventBus, code_manager):
        self._event_bus = event_bus
        self._code_manager = code_manager
        self._obj = None

    def start(self) -> None:
        CybosNewsHandler.callback = self._on_news
        self._obj = win32com.client.DispatchWithEvents(
            "Dscbo1.CpSvr8092S", CybosNewsHandler
        )
        self._obj.Subscribe()
        log.info("CYBOS news subscribed (disclosure only)")

    def stop(self) -> None:
        if self._obj:
            self._obj.Unsubscribe()
            log.info("CYBOS news unsubscribed")

    def _on_news(self, code: str, category: int, title: str) -> None:
        category_name = "disclosure" if category == CATEGORY_DISCLOSURE else "news"

        # Always publish to news_feed for display
        name = self._code_manager.code_to_name(code) or ""
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._event_bus.publish("news_feed", {
            "stock_code": code, "stock_name": name,
            "source": "cybos", "category": category_name,
            "text": title, "timestamp": ts,
        })

        # Only process disclosure (공시) for trading
        if category != CATEGORY_DISCLOSURE:
            return

        log.info(f"CYBOS disclosure: [{code}] {name} - {title}")

        if code and name and "단일판매" in title:
            log.info(f"CYBOS 단일판매 detected: [{code}] {name}")
            self._event_bus.publish("news_detected", {
                "code": code, "name": name, "source": "cybos",
                "title": title, "timestamp": ts,
            })
