from __future__ import annotations
import asyncio
import logging
import threading
from telegram import Bot

log = logging.getLogger(__name__)


class AlertBot:
    def __init__(self, token: str, chat_id: int):
        self._token = token
        self._chat_id = chat_id
        self._bot: Bot | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._bot = Bot(token=self._token)
        self._loop.run_forever()

    def send(self, message: str) -> None:
        if not self._bot or not self._loop:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._bot.send_message(self._chat_id, message), self._loop
            )
        except Exception as e:
            log.error(f"Alert send failed: {e}")

    def on_buy_filled(self, data: dict) -> None:
        msg = (f"[매수 체결] {data.get('name', '')} ({data.get('code', '')})\n"
               f"가격: {data.get('price', 0):,}원 x {data.get('qty', 0)}주")
        self.send(msg)

    def on_sell_filled(self, data: dict) -> None:
        pnl = data.get('pnl_pct', 0) * 100
        sign = "+" if pnl >= 0 else ""
        msg = (f"[매도 체결] {data.get('name', '')} ({data.get('code', '')})\n"
               f"가격: {data.get('price', 0):,}원 x {data.get('qty', 0)}주\n"
               f"수익률: {sign}{pnl:.2f}% ({data.get('reason', '')})")
        self.send(msg)

    def on_trade_done(self, data: dict) -> None:
        pass
