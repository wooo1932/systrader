from __future__ import annotations
import logging
import time
import win32com.client
import pythoncom
from src.com.connection import CybosConnection

log = logging.getLogger(__name__)


class StockMst:
    def __init__(self, connection: CybosConnection):
        self._conn = connection

    def request(self, code: str) -> dict | None:
        self._conn.wait_if_limited(0)
        obj = win32com.client.Dispatch("DsCbo1.StockMst")
        obj.SetInputValue(0, code)
        ret = obj.BlockRequest()
        if ret != 0:
            log.error(f"StockMst BlockRequest failed: {ret}")
            return None
        return {
            "code": code,
            "name": obj.GetHeaderValue(1),
            "current_price": obj.GetHeaderValue(11),
            "diff": obj.GetHeaderValue(12),
            "change_pct": obj.GetHeaderValue(13),
            "volume": obj.GetHeaderValue(18),
            "market_cap": obj.GetHeaderValue(23),
            "upper_limit_price": obj.GetHeaderValue(5),
            "lower_limit_price": obj.GetHeaderValue(6),
        }


class StockCurHandler:
    callbacks: dict[str, callable] = {}

    def OnReceived(self):
        code = self._obj.GetHeaderValue(0)
        data = {
            "code": code,
            "price": self._obj.GetHeaderValue(13),
            "volume": self._obj.GetHeaderValue(17),
            "bid_or_ask": "buy" if self._obj.GetHeaderValue(14) == ord("2") else "sell",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.") + f"{time.time() % 1:.3f}"[2:],
        }
        cb = StockCurHandler.callbacks.get(code)
        if cb:
            cb(code, data)


class StockCurManager:
    def __init__(self, on_tick: callable):
        self._on_tick = on_tick
        self._subscriptions: dict[str, object] = {}

    def subscribe(self, code: str) -> None:
        if code in self._subscriptions:
            return
        StockCurHandler.callbacks[code] = self._on_tick
        obj = win32com.client.DispatchWithEvents("Dscbo1.StockCur", StockCurHandler)
        obj.SetInputValue(0, code)
        obj.Subscribe()
        self._subscriptions[code] = obj
        log.info(f"Subscribed to StockCur: {code}")

    def unsubscribe(self, code: str) -> None:
        obj = self._subscriptions.pop(code, None)
        if obj:
            obj.Unsubscribe()
            StockCurHandler.callbacks.pop(code, None)
            log.info(f"Unsubscribed from StockCur: {code}")

    def unsubscribe_all(self) -> None:
        for code in list(self._subscriptions.keys()):
            self.unsubscribe(code)


class MarketEye:
    def __init__(self, connection: CybosConnection):
        self._conn = connection

    def request(self, codes: list[str], fields: list[int] = None) -> list[dict]:
        if not codes:
            return []
        if fields is None:
            fields = [0, 4, 5, 6, 11, 12, 13, 18, 20]
        self._conn.wait_if_limited(0)
        obj = win32com.client.Dispatch("CpSysDib.MarketEye")
        obj.SetInputValue(0, fields)
        obj.SetInputValue(1, codes)
        ret = obj.BlockRequest()
        if ret != 0:
            log.error(f"MarketEye BlockRequest failed: {ret}")
            return []
        count = obj.GetHeaderValue(2)
        results = []
        for i in range(count):
            row = {}
            for j, field_id in enumerate(fields):
                row[field_id] = obj.GetDataValue(j, i)
            results.append(row)
        return results
