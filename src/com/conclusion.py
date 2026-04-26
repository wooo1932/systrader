from __future__ import annotations
import logging
import win32com.client
from typing import Callable

log = logging.getLogger(__name__)


class ConclusionHandler:
    def OnReceived(self):
        try:
            conclusion_type = self.GetHeaderValue(0)
            if conclusion_type != "체결":
                return
            code = self.GetHeaderValue(9)
            price = self.GetHeaderValue(4)
            quantity = self.GetHeaderValue(3)
            buy_sell = self.GetHeaderValue(12)
            order_num = self.GetHeaderValue(5)
            side = "BUY" if buy_sell == "2" else "SELL"
            log.info(f"Conclusion: {side} {code} {quantity}@{price} order={order_num}")
            if ConclusionManager.callback:
                ConclusionManager.callback({
                    "code": code, "side": side,
                    "price": price, "quantity": quantity,
                    "order_num": order_num,
                })
        except Exception as e:
            log.error(f"ConclusionHandler error: {e}")


class ConclusionManager:
    callback = None

    def __init__(self, callback: Callable):
        ConclusionManager.callback = callback
        self._obj = None

    def start(self) -> None:
        self._obj = win32com.client.DispatchWithEvents(
            "DsCbo1.CpConclusion", ConclusionHandler
        )
        self._obj.Subscribe()
        log.info("CpConclusion subscribed")

    def stop(self) -> None:
        if self._obj:
            self._obj.Unsubscribe()
            log.info("CpConclusion unsubscribed")
