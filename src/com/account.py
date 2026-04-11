from __future__ import annotations
import logging
import win32com.client

log = logging.getLogger(__name__)


class CybosAccount:
    def __init__(self):
        self._trade_util = win32com.client.Dispatch("CpTrade.CpTdUtil")

    def init(self) -> None:
        result = self._trade_util.TradeInit(0)
        if result != 0:
            raise RuntimeError(f"TradeInit failed: {result}")
        log.info("Trade initialized")

    @property
    def account_number(self) -> str:
        return self._trade_util.AccountNumber[0]

    @property
    def goods_code(self) -> str:
        acc = self.account_number
        goods_list = self._trade_util.GoodsList(acc, 1)
        return goods_list[0]
