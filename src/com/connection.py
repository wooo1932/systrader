from __future__ import annotations
import logging
import time
import win32com.client
import pythoncom

log = logging.getLogger(__name__)


class CybosConnection:
    def __init__(self):
        self._cybos = win32com.client.Dispatch("CpUtil.CpCybos")

    @property
    def is_connected(self) -> bool:
        return self._cybos.IsConnect == 1

    def remaining_count(self, limit_type: int) -> int:
        return self._cybos.GetLimitRemainCount(limit_type)

    def wait_if_limited(self, limit_type: int) -> None:
        while self.remaining_count(limit_type) <= 0:
            log.debug(f"API rate limited (type={limit_type}), waiting...")
            pythoncom.PumpWaitingMessages()
            time.sleep(0.2)

    def get_server_type(self) -> str:
        return str(self._cybos.GetStockMarketKind("A005930"))
