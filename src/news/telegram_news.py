from __future__ import annotations
import asyncio
import logging
import threading
import time
from telethon import TelegramClient, events
from src.core.event_bus import EventBus

log = logging.getLogger(__name__)


class TelegramNewsSource:
    def __init__(self, api_id: int, api_hash: str, phone: str,
                 session_name: str, event_bus: EventBus, code_manager):
        self._api_id = api_id
        self._api_hash = api_hash
        self._phone = phone
        self._session_name = session_name
        self._event_bus = event_bus
        self._code_manager = code_manager
        self._channels: list[str] = []
        self._client: TelegramClient | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._auth_code_future: asyncio.Future | None = None

    def set_channels(self, channels: list[str]) -> None:
        self._channels = channels

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info("Telegram news listener started")

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._listen())

    async def _listen(self) -> None:
        self._client = TelegramClient(
            self._session_name, self._api_id, self._api_hash
        )
        await self._client.start(phone=self._phone, code_callback=self._code_callback)
        log.info("Telegram client connected")

        @self._client.on(events.NewMessage(chats=self._channels))
        async def handler(event):
            text = event.message.text or ""
            channel_name = getattr(event.chat, "title", "unknown")
            self._on_message(text, channel_name)

        await self._client.run_until_disconnected()

    async def _code_callback(self) -> str:
        log.info("Telegram 2FA code requested")
        self._event_bus.publish("telegram_code_pending", {"pending": True})
        self._auth_code_future = self._loop.create_future()
        code = await self._auth_code_future
        self._event_bus.publish("telegram_code_pending", {"pending": False})
        return code

    def submit_auth_code(self, code: str) -> None:
        if self._auth_code_future and self._loop:
            self._loop.call_soon_threadsafe(self._auth_code_future.set_result, code)

    def _on_message(self, text: str, channel_name: str) -> None:
        log.info(f"Telegram [{channel_name}]: {text[:80]}")
        self._event_bus.publish("news_feed", {
            "stock_code": "", "stock_name": "",
            "source": "telegram", "category": channel_name,
            "text": text, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        matches = self._extract_stocks(text)
        for code, name in matches:
            self._event_bus.publish("news_detected", {
                "code": code, "name": name, "source": "telegram",
                "channel": channel_name, "title": text[:100],
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })

    def _extract_stocks(self, text: str) -> list[tuple[str, str]]:
        results = []
        seen = set()
        for name, code in self._code_manager.all_stocks():
            if len(name) >= 2 and name in text and code not in seen:
                results.append((code, name))
                seen.add(code)
        return results
