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
    # Accept CYBOS disclosure events roughly around market hours only. Off-hours
    # (esp. ~20:00 batch disclosures) previously triggered a COM message-pump
    # crash under load — we simply ignore those events before engine processing.
    # Widened on both sides so pre-open news and closing-auction notices still land.
    ACCEPT_OPEN_HHMM = "0830"
    ACCEPT_CLOSE_HHMM = "1600"

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
        # Off-hours gate: skip the off-market batch disclosure flood (see class docstring).
        now_hhmm = time.strftime("%H%M")
        if not (self.ACCEPT_OPEN_HHMM <= now_hhmm <= self.ACCEPT_CLOSE_HHMM):
            return

        # Only process disclosure (공시), ignore general news entirely
        if category != CATEGORY_DISCLOSURE:
            return

        # Filter: only 주권 (common stock). Exclude ETN, ETF, REIT, ELW, 외국주, etc.
        if not self._code_manager.is_tradeable_stock(code):
            return

        name = self._code_manager.code_to_name(code) or ""
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        log.info(f"CYBOS 공시: [{code}] {name} - {title}")

        self._event_bus.publish("news_feed", {
            "stock_code": code, "stock_name": name,
            "source": "cybos", "category": "disclosure",
            "text": title, "timestamp": ts,
        })

        if code and name and "단일판매" in title:
            log.info(f"CYBOS 단일판매 detected: [{code}] {name} -> 매수 시도")
            self._event_bus.publish("news_detected", {
                "code": code, "name": name, "source": "cybos",
                "title": title, "timestamp": ts,
            })
